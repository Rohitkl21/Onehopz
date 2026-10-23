"""Catalog models for OneHopz multi-category marketplace."""

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.merchants.models import Merchant, Outlet, OutletCategory


class CatalogItem(models.Model):
    """
    Core catalog listing representing a sellable item, ticket, room, appointment, or seat.
    Directly owned by a Merchant and optionally scoped to a specific physical Outlet.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="catalog_items",
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catalog_items",
    )
    category = models.CharField(
        max_length=50,
        choices=OutletCategory.choices,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Standard non-discounted base price in INR or specified currency.",
    )
    currency = models.CharField(max_length=3, default="INR")
    is_active = models.BooleanField(default=True, db_index=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vertical-specific attributes (e.g. duration_mins, meal_type, room_amenities, seat_class).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Catalog Item"
        verbose_name_plural = "Catalog Items"
        indexes = [
            models.Index(fields=["merchant", "is_active"], name="idx_cat_item_merchant_active"),
            models.Index(fields=["category", "is_active"], name="idx_cat_item_cat_active"),
            models.Index(fields=["outlet", "is_active"], name="idx_cat_item_outlet_active"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(base_price__gte=Decimal("0.00")),
                name="chk_catalog_item_base_price_non_negative",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.base_price is not None and self.base_price < Decimal("0.00"):
            raise ValidationError({"base_price": "Base price cannot be negative."})

        if (
            self.outlet_id
            and self.merchant_id
            and self.outlet
            and self.outlet.merchant_id != self.merchant_id
        ):
            raise ValidationError(
                {"outlet": "Outlet must belong to the specified merchant organization."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} [{self.category}] - {self.currency} {self.base_price}"
