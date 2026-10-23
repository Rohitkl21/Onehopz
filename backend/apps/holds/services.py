"""Hold engine services implementing authoritative PostgreSQL ACID holds."""

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.catalog.models import CatalogItem
from apps.identity.models import User
from apps.inventory.models import (
    CinemaSeatAllocation,
    CinemaShowtime,
    EventTicketAllocation,
    EventTier,
    HotelBookingHold,
    HotelInventoryCalendar,
    RestaurantCoverSlot,
    SalonStylistSlotAllocation,
    SurplusAllocation,
    SurplusBatch,
    TravelInventoryUnit,
)
from apps.merchants.models import OutletCategory
from apps.offers.models import OfferSpecification
from apps.offers.services import calculate_discounted_price

from .exceptions import (
    HoldExpiredError,
    HoldNotFoundError,
    HoldPermissionDeniedError,
    HoldStateError,
    IdempotencyConflictError,
    InsufficientInventoryError,
    InventoryAlreadyLockedError,
    UnsupportedInventoryCategoryError,
)
from .models import Hold, HoldStatus

CATEGORY_HOLD_TTL_SECONDS: dict[str, int] = {
    OutletCategory.CINEMA: 600,  # 10 minutes
    OutletCategory.RESTAURANT: 600,  # 10 minutes
    OutletCategory.SURPLUS_FOOD: 600,  # 10 minutes
    OutletCategory.HOTEL: 900,  # 15 minutes
    OutletCategory.SALON: 600,  # 10 minutes
    OutletCategory.EVENT: 600,  # 10 minutes
    OutletCategory.TRAVEL: 600,  # 10 minutes
}


def compute_request_hash(
    customer_id: UUID | str,
    catalog_item_id: UUID | str,
    category: str,
    selection_parameters: dict[str, Any],
    quantity: int,
) -> str:
    """Produce deterministic SHA-256 fingerprint of the hold acquisition request."""
    normalized = {
        "customer_id": str(customer_id),
        "catalog_item_id": str(catalog_item_id),
        "category": str(category).upper(),
        "quantity": int(quantity),
        "selection_parameters": selection_parameters,
    }
    payload_str = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def _release_allocations_for_hold(hold: Hold) -> None:
    """
    Safely and idempotently release any inventory units or quotas held by this hold.
    Must be called inside an active transaction.
    """
    # 1. Cinema seats
    CinemaSeatAllocation.objects.filter(current_hold=hold).update(
        status=CinemaSeatAllocation.SeatStatus.AVAILABLE,
        current_hold=None,
    )

    # 2. Surplus food batches
    for s_alloc in SurplusAllocation.objects.filter(hold=hold, status="HELD"):
        SurplusBatch.objects.filter(id=s_alloc.batch_id).update(
            held_quantity=Greatest(Value(0), F("held_quantity") - s_alloc.quantity)
        )
        s_alloc.status = "RELEASED"
        s_alloc.save(update_fields=["status"])

    # 3. Event tickets
    for e_alloc in EventTicketAllocation.objects.filter(hold=hold, status="HELD"):
        EventTier.objects.filter(id=e_alloc.tier_id).update(
            held_tickets=Greatest(Value(0), F("held_tickets") - e_alloc.quantity)
        )
        e_alloc.status = "RELEASED"
        e_alloc.save(update_fields=["status"])

    # 4. Hotel calendar entries
    for booking in HotelBookingHold.objects.filter(hold=hold):
        d_start = booking.check_in_date
        d_end = booking.check_out_date
        nights = (d_end - d_start).days
        stay_dates = [d_start + timedelta(days=i) for i in range(nights)]
        HotelInventoryCalendar.objects.filter(
            room_type_id=booking.room_type_id,
            stay_date__in=stay_dates,
        ).update(held_count=Greatest(Value(0), F("held_count") - booking.rooms_count))

    # 5. Salon stylist slots
    SalonStylistSlotAllocation.objects.filter(current_hold=hold).update(
        status="AVAILABLE",
        current_hold=None,
    )

    # 6. Restaurant cover slots
    RestaurantCoverSlot.objects.filter(current_hold=hold).update(
        status="AVAILABLE",
        current_hold=None,
    )

    # 7. Travel units
    TravelInventoryUnit.objects.filter(current_hold=hold).update(
        status="AVAILABLE",
        current_hold=None,
    )


def acquire_hold(
    customer: User,
    catalog_item: CatalogItem,
    category: str,
    selection_parameters: dict[str, Any],
    quantity: int,
    idempotency_key: str,
    offer: OfferSpecification | None = None,
) -> tuple[Hold, bool]:
    """
    Acquire an authoritative PostgreSQL inventory hold inside an ACID transaction.
    Guarantees zero double-booking and strict idempotency fingerprinting.

    Returns:
        tuple[Hold, bool]: (hold_instance, is_created)
    """
    if quantity <= 0:
        raise InsufficientInventoryError("Hold quantity must be greater than zero.")

    if not catalog_item.is_active:
        raise InsufficientInventoryError("Catalog item is inactive and cannot be held.")

    if catalog_item.category != category:
        raise UnsupportedInventoryCategoryError(
            f"Catalog item category '{catalog_item.category}' does not match requested category '{category}'."
        )

    req_hash = compute_request_hash(
        customer_id=customer.id,
        catalog_item_id=catalog_item.id,
        category=category,
        selection_parameters=selection_parameters,
        quantity=quantity,
    )

    with transaction.atomic():
        # Check idempotency under row-level customer hold lock
        existing_hold = (
            Hold.objects.select_for_update()
            .filter(customer=customer, idempotency_key=idempotency_key)
            .first()
        )

        if existing_hold is not None:
            if existing_hold.request_hash != req_hash:
                raise IdempotencyConflictError(
                    "Idempotency key already used with different request parameters."
                )

            # Idempotent match: check hold status
            if existing_hold.status == HoldStatus.ACTIVE:
                if existing_hold.is_expired:
                    # Authoritatively expire it and free inventory
                    _release_allocations_for_hold(existing_hold)
                    existing_hold.status = HoldStatus.EXPIRED
                    existing_hold.save(update_fields=["status", "updated_at"])
                    raise HoldExpiredError("The hold for this idempotency key has expired.")
                return existing_hold, False

            # Existing hold was already terminated (RELEASED, EXPIRED, etc.)
            raise IdempotencyConflictError(
                f"Hold associated with this idempotency key is already {existing_hold.status.lower()}."
            )

        # 1. Authoritative Pricing Calculation
        base_price = catalog_item.base_price
        currency = catalog_item.currency
        if offer is not None:
            now_dt = timezone.now()
            if not offer.is_active or now_dt < offer.valid_from or now_dt > offer.valid_to:
                raise InsufficientInventoryError(
                    "Associated offer is not currently valid or active."
                )
            if offer.catalog_item_id and offer.catalog_item_id != catalog_item.id:
                raise InsufficientInventoryError("Offer does not apply to this catalog item.")
            pricing_res = calculate_discounted_price(
                base_price=base_price, offer=offer, currency=currency
            )
            unit_price = pricing_res.final_price
        else:
            unit_price = base_price

        total_price = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

        # 2. TTL calculation
        ttl_seconds = CATEGORY_HOLD_TTL_SECONDS.get(category, 600)
        held_at = timezone.now()
        expires_at = held_at + timedelta(seconds=ttl_seconds)

        # 3. Create initial Hold instance
        hold = Hold.objects.create(
            customer=customer,
            catalog_item=catalog_item,
            category=category,
            status=HoldStatus.ACTIVE,
            held_at=held_at,
            expires_at=expires_at,
            lock_reference="",
            quantity=quantity,
            total_price=total_price,
            currency=currency,
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            locked_units=[],
            selection_parameters=selection_parameters,
            is_demo=catalog_item.is_demo,
            metadata={},
        )

        locked_units: list[str] = []
        lock_ref = ""

        # 4. Vertical ACID Allocation
        if category == OutletCategory.CINEMA:
            showtime_id_str = selection_parameters.get("showtime_id")
            seats_param = selection_parameters.get("seats", [])
            if not showtime_id_str or not seats_param:
                raise InsufficientInventoryError("Cinema hold requires showtime_id and seats list.")

            showtime = (
                CinemaShowtime.objects.select_for_update()
                .filter(id=showtime_id_str, catalog_item=catalog_item)
                .first()
            )
            if not showtime:
                raise InsufficientInventoryError("Cinema showtime not found for this catalog item.")

            # Sort seats deterministically to avoid deadlocks
            sorted_seats = sorted(seats_param, key=lambda s: (s.get("row", ""), s.get("number", 0)))
            for s in sorted_seats:
                row = str(s.get("row", "")).strip().upper()
                num = int(s.get("number", 0))
                seat_label = f"{row}-{num}"

                seat_alloc = (
                    CinemaSeatAllocation.objects.select_for_update()
                    .filter(showtime=showtime, row_code=row, seat_number=num)
                    .first()
                )

                if seat_alloc is not None:
                    if seat_alloc.status == CinemaSeatAllocation.SeatStatus.HELD:
                        # Check if holding hold has expired
                        if seat_alloc.current_hold and seat_alloc.current_hold.is_expired:
                            # Reclaim expired seat
                            _release_allocations_for_hold(seat_alloc.current_hold)
                            seat_alloc.current_hold.status = HoldStatus.EXPIRED
                            seat_alloc.current_hold.save(update_fields=["status", "updated_at"])
                            seat_alloc.status = CinemaSeatAllocation.SeatStatus.AVAILABLE
                            seat_alloc.current_hold = None
                        else:
                            raise InventoryAlreadyLockedError(
                                f"Seat {seat_label} is currently held by another customer.",
                                conflicting_unit=seat_label,
                            )
                    elif seat_alloc.status in [
                        CinemaSeatAllocation.SeatStatus.RESERVED,
                        CinemaSeatAllocation.SeatStatus.MAINTENANCE_BLOCKED,
                    ]:
                        raise InventoryAlreadyLockedError(
                            f"Seat {seat_label} is not available.",
                            conflicting_unit=seat_label,
                        )

                    seat_alloc.status = CinemaSeatAllocation.SeatStatus.HELD
                    seat_alloc.current_hold = hold
                    seat_alloc.save(update_fields=["status", "current_hold", "updated_at"])
                else:
                    # Dynamically initialize seat allocation as HELD
                    CinemaSeatAllocation.objects.create(
                        showtime=showtime,
                        row_code=row,
                        seat_number=num,
                        status=CinemaSeatAllocation.SeatStatus.HELD,
                        current_hold=hold,
                    )
                locked_units.append(seat_label)

            lock_ref = f"CINEMA:{showtime.id}:" + ",".join(locked_units)

        elif category == OutletCategory.SURPLUS_FOOD:
            batch_id_str = selection_parameters.get("batch_id")
            batch_qs = SurplusBatch.objects.select_for_update().filter(catalog_item=catalog_item)
            batch = batch_qs.filter(id=batch_id_str).first() if batch_id_str else batch_qs.first()

            if not batch:
                raise InsufficientInventoryError(
                    "No surplus food batch found for this catalog item."
                )

            # ACID check: held + sold + requested <= total
            if batch.held_quantity + batch.sold_quantity + quantity > batch.total_quantity:
                raise InsufficientInventoryError(
                    "Requested quantity exceeds available surplus food inventory."
                )

            SurplusBatch.objects.filter(id=batch.id).update(
                held_quantity=F("held_quantity") + quantity
            )
            SurplusAllocation.objects.create(
                batch=batch,
                hold=hold,
                quantity=quantity,
                status="HELD",
            )
            locked_units = [f"SURPLUS:{batch.id}:{quantity}"]
            lock_ref = f"SURPLUS:{batch.id}:{quantity}"

        elif category == OutletCategory.EVENT:
            tier_id_str = selection_parameters.get("tier_id")
            tier_qs = EventTier.objects.select_for_update().filter(catalog_item=catalog_item)
            tier = tier_qs.filter(id=tier_id_str).first() if tier_id_str else tier_qs.first()

            if not tier:
                raise InsufficientInventoryError("No event tier found for this catalog item.")

            if tier.held_tickets + tier.sold_tickets + quantity > tier.total_allocation:
                raise InsufficientInventoryError(
                    "Requested ticket quantity exceeds available tier quota."
                )

            EventTier.objects.filter(id=tier.id).update(held_tickets=F("held_tickets") + quantity)
            EventTicketAllocation.objects.create(
                tier=tier,
                hold=hold,
                quantity=quantity,
                status="HELD",
            )
            locked_units = [f"EVENT_TIER:{tier.id}:{quantity}"]
            lock_ref = f"EVENT:{tier.id}:{quantity}"

        elif category == OutletCategory.HOTEL:
            room_type_id_str = selection_parameters.get("room_type_id")
            cin_str = selection_parameters.get("check_in_date")
            cout_str = selection_parameters.get("check_out_date")
            rooms_count = int(selection_parameters.get("rooms_count", quantity or 1))

            if not cin_str or not cout_str:
                raise InsufficientInventoryError(
                    "Hotel hold requires check_in_date and check_out_date."
                )

            d_in = parse_date(str(cin_str)) if isinstance(cin_str, str) else cin_str
            d_out = parse_date(str(cout_str)) if isinstance(cout_str, str) else cout_str

            if not isinstance(d_in, date) or not isinstance(d_out, date) or d_out <= d_in:
                raise InsufficientInventoryError("Invalid check-in/check-out dates.")

            nights = (d_out - d_in).days
            stay_dates = [d_in + timedelta(days=i) for i in range(nights)]

            room_qs = HotelInventoryCalendar.objects.select_for_update()
            if room_type_id_str:
                room_qs = room_qs.filter(room_type_id=room_type_id_str)
            else:
                room_qs = room_qs.filter(room_type__catalog_item=catalog_item)

            # Deterministic lock ordering: ordered by stay_date
            calendar_rows = list(room_qs.filter(stay_date__in=stay_dates).order_by("stay_date"))

            if len(calendar_rows) < len(stay_dates):
                raise InsufficientInventoryError(
                    "Hotel inventory calendar is not configured for all requested stay dates."
                )

            for cal_row in calendar_rows:
                if (
                    cal_row.held_count + cal_row.booked_count + rooms_count
                    > cal_row.total_available
                ):
                    raise InsufficientInventoryError(
                        f"Hotel room type is fully booked on {cal_row.stay_date}."
                    )

            for cal_row in calendar_rows:
                HotelInventoryCalendar.objects.filter(id=cal_row.id).update(
                    held_count=F("held_count") + rooms_count
                )

            first_room_type = calendar_rows[0].room_type
            HotelBookingHold.objects.create(
                room_type=first_room_type,
                hold=hold,
                check_in_date=d_in,
                check_out_date=d_out,
                rooms_count=rooms_count,
            )
            locked_units = [d.isoformat() for d in stay_dates]
            lock_ref = f"HOTEL:{first_room_type.id}:{d_in}:{d_out}"

        elif category == OutletCategory.SALON:
            stylist = selection_parameters.get("stylist_name", "PRIMARY")
            start_str = selection_parameters.get("start_time")
            end_str = selection_parameters.get("end_time")

            if not start_str or not end_str:
                raise InsufficientInventoryError(
                    "Salon hold requires stylist_name, start_time, and end_time."
                )

            st = parse_datetime(str(start_str)) if isinstance(start_str, str) else start_str
            et = parse_datetime(str(end_str)) if isinstance(end_str, str) else end_str

            if not isinstance(st, datetime) or not isinstance(et, datetime) or et <= st:
                raise InsufficientInventoryError("Invalid salon start/end timestamps.")

            slot = (
                SalonStylistSlotAllocation.objects.select_for_update()
                .filter(catalog_item=catalog_item, stylist_name=stylist, start_time=st)
                .first()
            )
            if slot is not None:
                if slot.status == "HELD":
                    if slot.current_hold and slot.current_hold.is_expired:
                        _release_allocations_for_hold(slot.current_hold)
                        slot.current_hold.status = HoldStatus.EXPIRED
                        slot.current_hold.save(update_fields=["status", "updated_at"])
                        slot.status = "AVAILABLE"
                        slot.current_hold = None
                    else:
                        raise InventoryAlreadyLockedError(
                            f"Stylist {stylist} is already held for {st.isoformat()}.",
                            conflicting_unit=f"{stylist}@{st.isoformat()}",
                        )
                elif slot.status != "AVAILABLE":
                    raise InventoryAlreadyLockedError(
                        f"Stylist {stylist} is not available for {st.isoformat()}."
                    )

                slot.status = "HELD"
                slot.current_hold = hold
                slot.save(update_fields=["status", "current_hold"])
            else:
                outlet = catalog_item.outlet
                if not outlet:
                    raise InsufficientInventoryError(
                        "Catalog item has no associated outlet for salon booking."
                    )
                SalonStylistSlotAllocation.objects.create(
                    catalog_item=catalog_item,
                    outlet=outlet,
                    stylist_name=stylist,
                    start_time=st,
                    end_time=et,
                    status="HELD",
                    current_hold=hold,
                )

            slot_label = f"{stylist}@{st.isoformat()}"
            locked_units = [slot_label]
            lock_ref = f"SALON:{catalog_item.id}:{slot_label}"

        elif category == OutletCategory.RESTAURANT:
            table_id = selection_parameters.get("table_id")
            slot_start = selection_parameters.get("slot_start_time")
            slot_end = selection_parameters.get("slot_end_time")

            if not table_id or not slot_start:
                raise InsufficientInventoryError(
                    "Restaurant hold requires table_id and slot_start_time."
                )

            st_res = parse_datetime(str(slot_start)) if isinstance(slot_start, str) else slot_start
            if not isinstance(st_res, datetime):
                raise InsufficientInventoryError("Invalid restaurant slot_start_time timestamp.")
            r_slot = (
                RestaurantCoverSlot.objects.select_for_update()
                .filter(table_id=table_id, slot_start_time=st_res)
                .first()
            )
            if r_slot is not None:
                if r_slot.status == "HELD":
                    if r_slot.current_hold and r_slot.current_hold.is_expired:
                        _release_allocations_for_hold(r_slot.current_hold)
                        r_slot.current_hold.status = HoldStatus.EXPIRED
                        r_slot.current_hold.save(update_fields=["status", "updated_at"])
                        r_slot.status = "AVAILABLE"
                        r_slot.current_hold = None
                    else:
                        raise InventoryAlreadyLockedError(
                            f"Table slot {table_id}@{st_res} is currently held.",
                            conflicting_unit=f"TABLE:{table_id}",
                        )
                elif r_slot.status != "AVAILABLE":
                    raise InventoryAlreadyLockedError(
                        f"Table slot {table_id}@{st_res} is not available."
                    )

                r_slot.status = "HELD"
                r_slot.current_hold = hold
                r_slot.save(update_fields=["status", "current_hold"])
            else:
                outlet = catalog_item.outlet
                if not outlet:
                    raise InsufficientInventoryError(
                        "Catalog item must belong to an outlet for table reservations."
                    )
                from apps.inventory.models import RestaurantTableLayout

                table = RestaurantTableLayout.objects.filter(id=table_id, outlet=outlet).first()
                if not table:
                    raise InsufficientInventoryError("Restaurant table not found for this outlet.")
                parsed_end = parse_datetime(str(slot_end)) if slot_end else None
                et_res = (
                    parsed_end
                    if isinstance(parsed_end, datetime)
                    else (st_res + timedelta(hours=2))
                )
                RestaurantCoverSlot.objects.create(
                    catalog_item=catalog_item,
                    outlet=outlet,
                    table=table,
                    slot_start_time=st_res,
                    slot_end_time=et_res,
                    status="HELD",
                    current_hold=hold,
                )

            locked_units = [f"TABLE:{table_id}"]
            lock_ref = f"RESTAURANT:{table_id}:{slot_start}"

        elif category == OutletCategory.TRAVEL:
            # Explicitly mark simulated hold for Travel vertical
            route_code = selection_parameters.get("route_code", "GENERIC_ROUTE")
            seat = selection_parameters.get("seat_identifier", "SEAT-1")
            locked_units = [seat]
            lock_ref = f"TRAVEL:{route_code}:{seat}"
            hold.metadata = {
                "is_simulated": True,
                "supplier_status": "PROVISIONAL",
                "note": "Local simulated hold; requires external supplier GDS confirmation before ticketing.",
            }

        else:
            raise UnsupportedInventoryCategoryError(
                f"Category '{category}' is not supported by the hold engine."
            )

        # Update final hold details
        hold.lock_reference = lock_ref
        hold.locked_units = locked_units
        hold.save(update_fields=["lock_reference", "locked_units", "metadata", "updated_at"])

        return hold, True


def release_hold(hold_id: UUID | str, customer: User) -> Hold:
    """
    Release an active hold.
    Guarantees idempotent re-release and zero double-releasing of underlying inventory.
    """
    with transaction.atomic():
        hold = Hold.objects.select_for_update().filter(id=hold_id).first()
        if not hold:
            raise HoldNotFoundError("Hold not found.")

        if hold.customer_id != customer.id and not (
            customer.is_platform_admin or customer.is_staff
        ):
            raise HoldPermissionDeniedError("You do not have permission to release this hold.")

        # Double-release protection: already released
        if hold.status == HoldStatus.RELEASED_BY_USER:
            return hold

        if hold.status == HoldStatus.CONVERTED_TO_ORDER:
            raise HoldStateError(
                "Cannot release a hold that has already been converted to an order."
            )

        if hold.status == HoldStatus.EXPIRED or hold.is_expired:
            _release_allocations_for_hold(hold)
            hold.status = HoldStatus.EXPIRED
            hold.save(update_fields=["status", "updated_at"])
            return hold

        # Active hold release
        _release_allocations_for_hold(hold)
        hold.status = HoldStatus.RELEASED_BY_USER
        hold.save(update_fields=["status", "updated_at"])
        return hold


def get_hold_detail(hold_id: UUID | str, customer: User) -> Hold:
    """
    Retrieve hold detail with authoritative timestamp expiration verification.
    """
    hold = Hold.objects.filter(id=hold_id).first()
    if not hold:
        raise HoldNotFoundError("Hold not found.")

    if hold.customer_id != customer.id and not (customer.is_platform_admin or customer.is_staff):
        raise HoldPermissionDeniedError("You do not have permission to view this hold.")

    # Check and authoritatively transition if expired
    if hold.status == HoldStatus.ACTIVE and hold.is_expired:
        with transaction.atomic():
            locked_hold = Hold.objects.select_for_update().filter(id=hold_id).first()
            if locked_hold and locked_hold.status == HoldStatus.ACTIVE and locked_hold.is_expired:
                _release_allocations_for_hold(locked_hold)
                locked_hold.status = HoldStatus.EXPIRED
                locked_hold.save(update_fields=["status", "updated_at"])
                return locked_hold

    return hold


def sweep_expired_holds(batch_size: int = 500) -> int:
    """
    Background sweep service for reclaiming expired active holds.
    Safe to retry, non-blocking, and transactional.
    """
    expired_candidates = list(
        Hold.objects.filter(
            status=HoldStatus.ACTIVE,
            expires_at__lte=timezone.now(),
        ).values_list("id", flat=True)[:batch_size]
    )

    reclaimed_count = 0
    for h_id in expired_candidates:
        with transaction.atomic():
            locked_hold = Hold.objects.select_for_update().filter(id=h_id).first()
            if locked_hold and locked_hold.status == HoldStatus.ACTIVE and locked_hold.is_expired:
                _release_allocations_for_hold(locked_hold)
                locked_hold.status = HoldStatus.EXPIRED
                locked_hold.save(update_fields=["status", "updated_at"])
                reclaimed_count += 1

    return reclaimed_count
