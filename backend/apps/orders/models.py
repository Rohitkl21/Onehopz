"""Authoritative order and durable reservation domain models."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.merchants.models import OutletCategory


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment"
    PAID_CONFIRMED = "PAID_CONFIRMED", "Paid & Confirmed"
    CANCELLED_PAYMENT_TIMEOUT = "CANCELLED_PAYMENT_TIMEOUT", "Cancelled (Payment Timeout)"
    CANCELLED_USER_REQUESTED = "CANCELLED_USER_REQUESTED", "Cancelled by User"
    COMPLETED_REDEEMED = "COMPLETED_REDEEMED", "Completed & Redeemed"
    EXPIRED_NO_SHOW = "EXPIRED_NO_SHOW", "Expired (No Show)"


class OrderReservationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    FULFILLED = "FULFILLED", "Fulfilled"
    RELEASED = "RELEASED", "Released"
    EXPIRED = "EXPIRED", "Expired"


class Order(models.Model):
    """
    Authoritative order record representing legal buyer commitment and financial terms.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    checkout_session_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="orders",
    )
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.RESTRICT,
        related_name="orders",
    )
    outlet = models.ForeignKey(
        "merchants.Outlet",
        on_delete=models.RESTRICT,
        related_name="orders",
    )
    hold = models.ForeignKey(
        "holds.Hold",
        on_delete=models.RESTRICT,
        related_name="orders",
        null=True,
        blank=True,
    )
    category = models.CharField(
        max_length=50,
        choices=OutletCategory.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=40,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
        db_index=True,
    )

    # Financial snapshots
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    platform_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_payable_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")

    # Bounded reservation window
    payment_deadline = models.DateTimeField(db_index=True)
    cancellation_deadline = models.DateTimeField(null=True, blank=True)
    cancellation_policy_type = models.CharField(
        max_length=50,
        default="STRICT_NON_REFUNDABLE",
    )

    # Audit snapshots
    customer_contact = models.JSONField(default=dict, blank=True)
    lock_reference_snapshot = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        indexes = [
            models.Index(fields=["customer", "status"], name="idx_orders_customer_status"),
            models.Index(fields=["merchant", "created_at"], name="idx_orders_merchant_created"),
            models.Index(fields=["status", "payment_deadline"], name="idx_orders_status_deadline"),
            models.Index(fields=["is_demo"], name="idx_orders_is_demo"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    net_payable_amount=(
                        F("gross_amount") - F("discount_amount") + F("platform_fee") + F("tax_amount")
                    )
                ),
                name="chk_order_net_calc",
            ),
            models.CheckConstraint(
                condition=Q(gross_amount__gte=Decimal("0.00")),
                name="chk_order_gross_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(net_payable_amount__gte=Decimal("0.00")),
                name="chk_order_net_non_negative",
            ),
        ]

    @property
    def is_payment_expired(self) -> bool:
        """Check if payment deadline has elapsed."""
        return timezone.now() >= self.payment_deadline

    @property
    def effective_status(self) -> str:
        """
        Authoritative effective status.
        If marked PENDING_PAYMENT but payment deadline has passed,
        it evaluates authoritatively as CANCELLED_PAYMENT_TIMEOUT.
        """
        if self.status == OrderStatus.PENDING_PAYMENT and self.is_payment_expired:
            return OrderStatus.CANCELLED_PAYMENT_TIMEOUT
        return self.status

    def __str__(self) -> str:
        return f"Order {self.order_number} [{self.category}] - {self.effective_status}"


class OrderItem(models.Model):
    """
    Immutable line item snapshot capturing exact pricing, quantity, and booking terms.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.RESTRICT,
        related_name="order_items",
    )
    unit_identifier = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)
    unit_base_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_applied = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(max_length=3, default="INR")
    booking_terms = models.JSONField(default=dict, blank=True)
    item_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="chk_order_item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_sale_price__gte=Decimal("0.00")),
                name="chk_order_item_sale_price_non_neg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order.order_number} Item: {self.unit_identifier} (x{self.quantity})"


class OrderReservation(models.Model):
    """
    Durable link between an order, its converted hold, and the active inventory lease.
    Prevents other customers from reclaiming or acquiring the inventory during the payment window.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="reservation",
    )
    hold = models.OneToOneField(
        "holds.Hold",
        on_delete=models.RESTRICT,
        related_name="order_reservation",
    )
    status = models.CharField(
        max_length=30,
        choices=OrderReservationStatus.choices,
        default=OrderReservationStatus.ACTIVE,
        db_index=True,
    )
    payment_deadline = models.DateTimeField(db_index=True)
    lock_reference = models.CharField(max_length=255)
    locked_units = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Reservation"
        verbose_name_plural = "Order Reservations"
        indexes = [
            models.Index(fields=["status", "payment_deadline"], name="idx_order_res_status_deadline"),
        ]

    @property
    def is_expired(self) -> bool:
        """Evaluate authoritative expiration of the order reservation lease."""
        return self.status == OrderReservationStatus.ACTIVE and timezone.now() >= self.payment_deadline

    def __str__(self) -> str:
        return f"Reservation for {self.order.order_number} [{self.status}]"


class CheckoutIdempotency(models.Model):
    """
    Authoritative idempotency record for checkout requests.
    Prevents duplicate order creation and binds request fingerprints.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkout_idempotencies",
    )
    idempotency_key = models.CharField(max_length=255, db_index=True)
    request_hash = models.CharField(max_length=64)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Checkout Idempotency"
        verbose_name_plural = "Checkout Idempotencies"
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                name="uq_checkout_customer_idempotency",
            )
        ]

    def __str__(self) -> str:
        return f"Idempotency {self.idempotency_key} -> Order {self.order.order_number}"
