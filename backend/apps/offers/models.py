"""Offer models for OneHopz Last-Chance dynamic pricing engine."""

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import CatalogItem
from apps.merchants.models import Merchant, Outlet, OutletCategory


class OfferType(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", "Percentage Discount"
    FIXED_AMOUNT = "FIXED_AMOUNT", "Fixed Amount Discount"


class OfferSpecification(models.Model):
    """
    Specification for discounts and dynamic pricing policies.
    Can be scoped to an entire merchant, a specific outlet, or an individual catalog item.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offers",
    )
    catalog_item = models.ForeignKey(
        CatalogItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="offers",
    )
    category = models.CharField(
        max_length=50,
        choices=OutletCategory.choices,
        blank=True,
        null=True,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    offer_type = models.CharField(
        max_length=20,
        choices=OfferType.choices,
        default=OfferType.PERCENTAGE,
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Percentage value (e.g. 25.00 for 25%) or fixed currency discount (e.g. 150.00).",
    )
    currency = models.CharField(
        max_length=3,
        default="INR",
        help_text="Currency ISO code (INR, USD, etc.). For item-bound offers, derived from the catalog item.",
    )
    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Upper monetary cap on percentage discount savings.",
    )
    floor_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum allowed checkout price; prevents selling below cost.",
    )
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True, db_index=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dynamic parameters for yield curves, step decay, or off-peak conditions.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Offer Specification"
        verbose_name_plural = "Offer Specifications"
        indexes = [
            models.Index(
                fields=["merchant", "is_active", "valid_from", "valid_to"],
                name="idx_offer_merch_active_dates",
            ),
            models.Index(fields=["catalog_item", "is_active"], name="idx_offer_item_active"),
            models.Index(fields=["category", "is_active"], name="idx_offer_cat_active"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_value__gt=Decimal("0.00")),
                name="chk_offer_discount_val_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__gt=F("valid_from")),
                name="chk_offer_valid_dates",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            errors["valid_to"] = "Offer valid_to timestamp must be strictly after valid_from."

        if self.discount_value is not None:
            if self.discount_value <= Decimal("0.00"):
                errors["discount_value"] = "Discount value must be strictly positive."
            elif self.offer_type == OfferType.PERCENTAGE and self.discount_value > Decimal(
                "100.00"
            ):
                errors["discount_value"] = "Percentage discount cannot exceed 100.00%."

        if (
            self.outlet_id
            and self.merchant_id
            and self.outlet
            and self.outlet.merchant_id != self.merchant_id
        ):
            errors["outlet"] = "Outlet must belong to the specified merchant."

        if (
            self.catalog_item_id
            and self.merchant_id
            and self.catalog_item
            and self.catalog_item.merchant_id != self.merchant_id
        ):
            errors["catalog_item"] = "Catalog item must belong to the specified merchant."

        # Currency consistency with bound catalog item
        if self.catalog_item_id and self.catalog_item:
            if not self.currency:
                self.currency = self.catalog_item.currency
            elif self.currency.upper() != self.catalog_item.currency.upper():
                errors["currency"] = (
                    f"Offer currency '{self.currency}' must match bound catalog item "
                    f"currency '{self.catalog_item.currency}'."
                )

        # Floor price validations
        if self.floor_price is not None:
            if self.floor_price < Decimal("0.00"):
                errors["floor_price"] = "Floor price cannot be negative."
            elif (
                self.catalog_item_id
                and self.catalog_item
                and self.floor_price > self.catalog_item.base_price
            ):
                errors["floor_price"] = (
                    f"Floor price ({self.floor_price}) cannot exceed the bound catalog item "
                    f"base price ({self.catalog_item.base_price})."
                )
            elif (
                self.offer_type == OfferType.FIXED_AMOUNT
                and self.catalog_item_id
                and self.catalog_item
                and (self.catalog_item.base_price - self.discount_value) < self.floor_price
            ):
                errors["discount_value"] = (
                    f"Fixed discount ({self.discount_value}) on base price "
                    f"({self.catalog_item.base_price}) breaches floor price ({self.floor_price})."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.catalog_item_id and self.catalog_item and not self.currency:
            self.currency = self.catalog_item.currency
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} ({self.offer_type} {self.discount_value} {self.currency})"
