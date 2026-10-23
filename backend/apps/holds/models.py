"""Hold model and state machine for ephemeral inventory reservations."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.merchants.models import OutletCategory


class HoldStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CONVERTED_TO_ORDER = "CONVERTED_TO_ORDER", "Converted to Order"
    EXPIRED = "EXPIRED", "Expired"
    RELEASED_BY_USER = "RELEASED_BY_USER", "Released by User"


class Hold(models.Model):
    """
    Authoritative ephemeral inventory reservation claim.
    Persisted and validated inside PostgreSQL.
    Guarantees temporary claim before order placement.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="holds",
    )
    catalog_item = models.ForeignKey(
        "catalog.CatalogItem",
        on_delete=models.CASCADE,
        related_name="holds",
    )
    category = models.CharField(
        max_length=50,
        choices=OutletCategory.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=30,
        choices=HoldStatus.choices,
        default=HoldStatus.ACTIVE,
        db_index=True,
    )
    held_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    lock_reference = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="INR")
    idempotency_key = models.CharField(max_length=255, db_index=True)
    request_hash = models.CharField(max_length=64, blank=True, default="")
    locked_units = models.JSONField(default=list, blank=True)
    selection_parameters = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Hold"
        verbose_name_plural = "Holds"
        indexes = [
            models.Index(fields=["id", "status", "expires_at"], name="idx_holds_active_lookup"),
            models.Index(fields=["status", "expires_at"], name="idx_holds_cleanup_sweep"),
            models.Index(fields=["customer", "status"], name="idx_holds_user_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                name="uq_holds_customer_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="chk_hold_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("held_at")),
                name="chk_hold_expires_after_held",
            ),
        ]

    @property
    def is_expired(self) -> bool:
        """
        Evaluate authoritative expiration against current timezone-aware timestamp.
        Returns True if the hold is marked EXPIRED or if an ACTIVE hold has passed expires_at.
        Converted holds are governed by their order reservations and do not expire via hold TTL.
        """
        if self.status == HoldStatus.EXPIRED:
            return True
        if self.status == HoldStatus.ACTIVE:
            return timezone.now() >= self.expires_at
        return False

    @property
    def effective_status(self) -> str:
        """
        Authoritative effective status.
        If marked ACTIVE in the database but expired by timestamp,
        it evaluates authoritatively as EXPIRED.
        """
        if self.status == HoldStatus.ACTIVE and self.is_expired:
            return HoldStatus.EXPIRED
        return self.status

    @property
    def ttl_remaining_seconds(self) -> int:
        """Return remaining seconds until hold expiration, or 0 if expired/inactive."""
        if self.status != HoldStatus.ACTIVE or self.is_expired:
            return 0
        diff = int((self.expires_at - timezone.now()).total_seconds())
        return max(0, diff)

    def __str__(self) -> str:
        return f"Hold {self.id} [{self.category}] - {self.effective_status} ({self.lock_reference})"
