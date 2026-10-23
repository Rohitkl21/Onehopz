"""Authoritative business logic for checkout, order creation, and reservation lifecycles."""

import hashlib
import json
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.holds.models import Hold, HoldStatus
from apps.holds.services import _release_allocations_for_hold
from apps.identity.models import User
from apps.inventory.models import (
    CinemaSeatAllocation,
    CinemaShowtime,
    EventTicketAllocation,
    HotelBookingHold,
    RestaurantCoverSlot,
    SalonStylistSlotAllocation,
    SurplusAllocation,
    SurplusBatch,
)
from apps.merchants.models import OutletCategory

from .exceptions import (
    HoldAlreadyConvertedError,
    HoldExpiredForCheckoutError,
    HoldNotOwnedError,
    IdempotencyConflictError,
    InventoryCutoffExceededError,
    InventoryReservationUnavailableError,
    OrderNotFoundError,
    UnsupportedCheckoutCategoryError,
)
from .models import (
    CheckoutIdempotency,
    Order,
    OrderItem,
    OrderReservation,
    OrderReservationStatus,
    OrderStatus,
)


def compute_checkout_request_hash(
    customer_id: UUID | str,
    hold_id: UUID | str,
    customer_contact: dict[str, Any],
) -> str:
    """Produce deterministic SHA-256 fingerprint for a checkout request."""
    normalized = {
        "customer_id": str(customer_id),
        "hold_id": str(hold_id),
        "customer_contact": customer_contact,
    }
    payload_str = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def generate_order_number() -> str:
    """Generate human-readable, high-entropy unique order number: OH-YYYYMMDD-XXXX."""
    date_str = timezone.now().strftime("%Y%m%d")
    random_suffix = secrets.token_hex(3).upper()
    return f"OH-{date_str}-{random_suffix}"


def compute_payment_deadline(
    category: str,
    hold: Hold,
    created_at: datetime,
) -> datetime:
    """
    Calculate bounded payment reservation deadline based on category fulfillment deadlines.
    Default bounded reservation window is 15 minutes from order creation.
    """
    base_deadline = created_at + timedelta(minutes=15)
    params = hold.selection_parameters or {}

    cutoff: datetime | None = None

    if category == OutletCategory.CINEMA:
        showtime_id = params.get("showtime_id")
        if showtime_id:
            showtime = CinemaShowtime.objects.filter(id=showtime_id).first()
            if showtime and showtime.start_time:
                cutoff = showtime.start_time - timedelta(minutes=10)

    elif category == OutletCategory.EVENT:
        et_raw = params.get("event_start")
        if et_raw:
            et = parse_datetime(str(et_raw)) if isinstance(et_raw, str) else et_raw
            if isinstance(et, datetime):
                cutoff = et - timedelta(minutes=30)

    elif category == OutletCategory.RESTAURANT:
        st_raw = params.get("slot_start_time")
        if st_raw:
            rst = parse_datetime(str(st_raw)) if isinstance(st_raw, str) else st_raw
            if isinstance(rst, datetime):
                cutoff = rst - timedelta(minutes=15)

    elif category == OutletCategory.SALON:
        st_raw = params.get("start_time")
        if st_raw:
            sst = parse_datetime(str(st_raw)) if isinstance(st_raw, str) else st_raw
            if isinstance(sst, datetime):
                cutoff = sst - timedelta(minutes=15)

    elif category == OutletCategory.SURPLUS_FOOD:
        batch_id = params.get("batch_id")
        batch = SurplusBatch.objects.filter(id=batch_id).first() if batch_id else None
        if batch and batch.pickup_window_end:
            cutoff = batch.pickup_window_end - timedelta(minutes=15)

    elif category == OutletCategory.HOTEL:
        cin_raw = params.get("check_in_date")
        if cin_raw:
            d_in = parse_date(str(cin_raw)) if isinstance(cin_raw, str) else cin_raw
            if isinstance(d_in, date):
                local_cutoff = datetime.combine(d_in, time(18, 0))
                if timezone.is_naive(local_cutoff):
                    cutoff = timezone.make_aware(local_cutoff) - timedelta(hours=1)
                else:
                    cutoff = local_cutoff - timedelta(hours=1)

    elif category == OutletCategory.TRAVEL:
        # Simulated category adapter: base deadline is authoritative
        cutoff = None

    if cutoff is not None:
        if cutoff <= created_at:
            raise InventoryCutoffExceededError(
                "Fulfillment cutoff deadline for this inventory has already passed."
            )
        return min(base_deadline, cutoff)

    return base_deadline


def checkout(
    customer: User,
    hold_id: UUID | str,
    customer_contact: dict[str, Any],
    idempotency_key: str,
) -> tuple[Order, bool]:
    """
    Authoritatively convert an active hold into an order and transfer inventory reservation.
    Executes in a single atomic PostgreSQL transaction adhering to global locking hierarchy.

    Returns:
        tuple[Order, bool]: (order_instance, is_created)
    """
    req_hash = compute_checkout_request_hash(
        customer_id=customer.id,
        hold_id=hold_id,
        customer_contact=customer_contact,
    )

    # 1. Pre-check authoritative hold expiration to commit reclamation before checkout transaction
    pre_hold = Hold.objects.filter(id=hold_id).first()
    if pre_hold is not None and pre_hold.status == HoldStatus.ACTIVE and timezone.now() >= pre_hold.expires_at:
        with transaction.atomic():
            locked_h = Hold.objects.select_for_update().filter(id=hold_id).first()
            if locked_h and locked_h.status == HoldStatus.ACTIVE and timezone.now() >= locked_h.expires_at:
                _release_allocations_for_hold(locked_h)
                locked_h.status = HoldStatus.EXPIRED
                locked_h.save(update_fields=["status", "updated_at"])
        raise HoldExpiredForCheckoutError("Reservation hold has expired.")

    with transaction.atomic():
        # Check idempotency under customer lock
        existing_idempotency = (
            CheckoutIdempotency.objects.select_for_update()
            .filter(customer=customer, idempotency_key=idempotency_key)
            .first()
        )
        if existing_idempotency is not None:
            if existing_idempotency.request_hash != req_hash:
                raise IdempotencyConflictError(
                    "Idempotency key was previously used with a different request payload."
                )
            return existing_idempotency.order, False

        # 2. Lock Source Hold (Lock 1 in global hierarchy)
        hold = Hold.objects.select_for_update().filter(id=hold_id).first()
        if hold is None:
            raise OrderNotFoundError("Reservation hold not found.")

        # Ownership validation
        if hold.customer_id != customer.id:
            raise HoldNotOwnedError("You do not have permission to checkout this hold.")

        # State machine validation
        if hold.status == HoldStatus.CONVERTED_TO_ORDER:
            # Check if this hold was converted by a concurrent request with the same idempotency key
            concurrent_match = (
                CheckoutIdempotency.objects.filter(
                    customer=customer,
                    idempotency_key=idempotency_key,
                    order__hold=hold,
                )
                .select_related("order")
                .first()
            )
            if concurrent_match is not None:
                if concurrent_match.request_hash != req_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was previously used with a different request payload."
                    )
                return concurrent_match.order, False

            raise HoldAlreadyConvertedError(
                "This reservation hold has already been converted to an order."
            )

        if hold.status != HoldStatus.ACTIVE:
            raise HoldExpiredForCheckoutError(
                f"Reservation hold is {hold.status.lower()} and cannot be checked out."
            )

        # Clock-based authoritative expiration check
        if timezone.now() >= hold.expires_at:
            _release_allocations_for_hold(hold)
            hold.status = HoldStatus.EXPIRED
            hold.save(update_fields=["status", "updated_at"])
            raise HoldExpiredForCheckoutError("Reservation hold has expired.")

        # 3. Category Inventory Reservation Verification
        category = hold.category
        locked_units = hold.locked_units or []

        if category == OutletCategory.CINEMA:
            cinema_allocs = CinemaSeatAllocation.objects.filter(current_hold=hold)
            if not cinema_allocs.exists() or cinema_allocs.count() != len(locked_units):
                raise InventoryReservationUnavailableError(
                    "Cinema seat allocations for this hold are missing or corrupted."
                )
        elif category == OutletCategory.SURPLUS_FOOD:
            surplus_alloc = SurplusAllocation.objects.filter(hold=hold, status="HELD").first()
            if not surplus_alloc:
                raise InventoryReservationUnavailableError(
                    "Surplus food batch allocation for this hold is no longer intact."
                )
        elif category == OutletCategory.EVENT:
            event_alloc = EventTicketAllocation.objects.filter(hold=hold, status="HELD").first()
            if not event_alloc:
                raise InventoryReservationUnavailableError(
                    "Event ticket allocation for this hold is no longer intact."
                )
        elif category == OutletCategory.HOTEL:
            hotel_hold = HotelBookingHold.objects.filter(hold=hold).first()
            if not hotel_hold:
                raise InventoryReservationUnavailableError(
                    "Hotel calendar allocation for this hold is no longer intact."
                )
        elif category == OutletCategory.SALON:
            salon_slot = SalonStylistSlotAllocation.objects.filter(current_hold=hold, status="HELD").first()
            if not salon_slot:
                raise InventoryReservationUnavailableError(
                    "Salon stylist slot allocation for this hold is no longer intact."
                )
        elif category == OutletCategory.RESTAURANT:
            rest_slot = RestaurantCoverSlot.objects.filter(current_hold=hold, status="HELD").first()
            if not rest_slot:
                raise InventoryReservationUnavailableError(
                    "Restaurant table cover slot allocation for this hold is no longer intact."
                )
        elif category == OutletCategory.TRAVEL:
            # Simulated category adapter
            pass
        else:
            raise UnsupportedCheckoutCategoryError(
                f"Category '{category}' does not support order checkout."
            )

        # 4. Authoritative Financial Snapshot Calculation
        catalog_item = hold.catalog_item
        merchant = catalog_item.merchant
        outlet = catalog_item.outlet
        if not outlet:
            raise InventoryReservationUnavailableError(
                "Catalog item is not bound to a valid merchant outlet."
            )

        unit_base_price = catalog_item.base_price
        gross_amount = (unit_base_price * Decimal(hold.quantity)).quantize(Decimal("0.01"))
        net_payable_amount = hold.total_price
        discount_amount = max(Decimal("0.00"), gross_amount - net_payable_amount)
        unit_sale_price = (net_payable_amount / Decimal(hold.quantity)).quantize(Decimal("0.01"))
        unit_discount = max(Decimal("0.00"), unit_base_price - unit_sale_price)

        # 5. Persist Bounded Payment Deadline
        now = timezone.now()
        payment_deadline = compute_payment_deadline(category, hold, now)

        # 6. Create Order (Lock 2 in global hierarchy)
        order_num = generate_order_number()
        # Guarantee uniqueness across generation collisions
        while Order.objects.filter(order_number=order_num).exists():
            order_num = generate_order_number()

        order = Order.objects.create(
            order_number=order_num,
            customer=customer,
            merchant=merchant,
            outlet=outlet,
            hold=hold,
            category=category,
            status=OrderStatus.PENDING_PAYMENT,
            gross_amount=gross_amount,
            discount_amount=discount_amount,
            platform_fee=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            net_payable_amount=net_payable_amount,
            currency=hold.currency,
            payment_deadline=payment_deadline,
            cancellation_policy_type="STRICT_NON_REFUNDABLE",
            customer_contact=customer_contact,
            lock_reference_snapshot=hold.lock_reference,
            metadata={
                "source_hold_id": str(hold.id),
                "selection_parameters": hold.selection_parameters,
            },
            is_demo=hold.is_demo,
        )

        # 7. Create Line Item Snapshots
        if locked_units and len(locked_units) == hold.quantity:
            for unit_id in locked_units:
                OrderItem.objects.create(
                    order=order,
                    catalog_item=catalog_item,
                    unit_identifier=unit_id,
                    quantity=1,
                    unit_base_price=unit_base_price,
                    unit_sale_price=unit_sale_price,
                    discount_applied=unit_discount,
                    currency=hold.currency,
                    booking_terms=catalog_item.metadata.get("booking_terms", {}),
                    item_metadata={"unit": unit_id},
                )
        else:
            OrderItem.objects.create(
                order=order,
                catalog_item=catalog_item,
                unit_identifier=hold.lock_reference or str(catalog_item.id),
                quantity=hold.quantity,
                unit_base_price=unit_base_price,
                unit_sale_price=unit_sale_price,
                discount_applied=unit_discount,
                currency=hold.currency,
                booking_terms=catalog_item.metadata.get("booking_terms", {}),
                item_metadata={"locked_units": locked_units},
            )

        # 8. Create Order-Linked Durable Reservation
        OrderReservation.objects.create(
            order=order,
            hold=hold,
            status=OrderReservationStatus.ACTIVE,
            payment_deadline=payment_deadline,
            lock_reference=hold.lock_reference,
            locked_units=locked_units,
        )

        # 9. Record Idempotency Fingerprint
        try:
            with transaction.atomic():
                CheckoutIdempotency.objects.create(
                    customer=customer,
                    idempotency_key=idempotency_key,
                    request_hash=req_hash,
                    order=order,
                )
        except IntegrityError as exc:
            # Race condition: another concurrent thread completed idempotency record first
            existing = (
                CheckoutIdempotency.objects.filter(
                    customer=customer,
                    idempotency_key=idempotency_key,
                )
                .select_related("order")
                .first()
            )
            if existing is not None:
                if existing.request_hash != req_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key was previously used with a different request payload."
                    ) from exc
                return existing.order, False
            raise

        # 10. Transition Source Hold State
        hold.status = HoldStatus.CONVERTED_TO_ORDER
        hold.save(update_fields=["status", "updated_at"])

        return order, True


def sweep_expired_order_reservations(batch_size: int = 200) -> int:
    """
    Background sweep service for reclaiming inventory from expired pending orders.
    Reclaims associated inventory allocations and updates status atomically.
    """
    expired_order_ids = list(
        Order.objects.filter(
            status=OrderStatus.PENDING_PAYMENT,
            payment_deadline__lte=timezone.now(),
        ).values_list("id", flat=True)[:batch_size]
    )

    swept_count = 0
    for o_id in expired_order_ids:
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .filter(id=o_id, status=OrderStatus.PENDING_PAYMENT)
                .first()
            )
            if order and timezone.now() >= order.payment_deadline:
                # Release underlying inventory allocations
                if order.hold:
                    _release_allocations_for_hold(order.hold)

                # Transition Order Reservation
                if hasattr(order, "reservation"):
                    res = order.reservation
                    res.status = OrderReservationStatus.EXPIRED
                    res.save(update_fields=["status", "updated_at"])

                # Transition Order
                order.status = OrderStatus.CANCELLED_PAYMENT_TIMEOUT
                order.save(update_fields=["status", "updated_at"])
                swept_count += 1

    return swept_count
