"""Serializers for Catalog domain."""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.merchants.models import OutletCategory

from .models import CatalogItem
from .registry import CategoryRegistry


class CategoryCapabilitySerializer(serializers.Serializer[Any]):
    """Serializer representing declared capabilities of a business category."""

    category = serializers.CharField()
    display_name = serializers.CharField()
    allocation_unit = serializers.CharField()
    has_seat_map = serializers.BooleanField()
    has_time_slots = serializers.BooleanField()
    has_date_range = serializers.BooleanField()
    has_expiry_window = serializers.BooleanField()
    is_supplier_managed = serializers.BooleanField()
    concurrency_model = serializers.CharField()
    cancellation_rules_summary = serializers.CharField()
    requires_fssai = serializers.BooleanField()


class CatalogItemSerializer(serializers.ModelSerializer[CatalogItem]):
    """Serializer for CatalogItem with multi-tenant validations."""

    merchant_name = serializers.CharField(source="merchant.business_name", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True, allow_null=True)

    class Meta:
        model = CatalogItem
        fields = [
            "id",
            "merchant",
            "merchant_name",
            "outlet",
            "outlet_name",
            "category",
            "title",
            "description",
            "base_price",
            "currency",
            "is_active",
            "is_demo",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_category(self, value: str) -> str:
        if not CategoryRegistry.is_valid_category(value):
            raise serializers.ValidationError(
                f"Invalid category '{value}'. Allowed: {OutletCategory.values}"
            )
        return value

    def validate_base_price(self, value: Decimal) -> Decimal:
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Base price cannot be negative.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        merchant = attrs.get("merchant") or (self.instance.merchant if self.instance else None)
        outlet = attrs.get("outlet", getattr(self.instance, "outlet", None))

        if outlet and merchant and outlet.merchant_id != merchant.id:
            raise serializers.ValidationError(
                {"outlet": "Specified outlet does not belong to the selected merchant."}
            )

        return attrs
