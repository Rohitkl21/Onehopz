"""Serializers for Offers and Dynamic Yield domain."""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.merchants.models import OutletCategory

from .models import OfferSpecification, OfferType


class OfferSpecificationSerializer(serializers.ModelSerializer[OfferSpecification]):
    """Serializer for OfferSpecification with tenant and constraint validation."""

    merchant_name = serializers.CharField(source="merchant.business_name", read_only=True)
    outlet_name = serializers.CharField(source="outlet.name", read_only=True, allow_null=True)
    catalog_item_title = serializers.CharField(
        source="catalog_item.title", read_only=True, allow_null=True
    )

    class Meta:
        model = OfferSpecification
        fields = [
            "id",
            "merchant",
            "merchant_name",
            "outlet",
            "outlet_name",
            "catalog_item",
            "catalog_item_title",
            "category",
            "title",
            "description",
            "offer_type",
            "discount_value",
            "max_discount_amount",
            "floor_price",
            "valid_from",
            "valid_to",
            "is_active",
            "is_demo",
            "parameters",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_category(self, value: str | None) -> str | None:
        if value and value not in OutletCategory.values:
            raise serializers.ValidationError(
                f"Invalid category '{value}'. Allowed: {OutletCategory.values}"
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))

        if valid_from and valid_to and valid_to <= valid_from:
            raise serializers.ValidationError(
                {"valid_to": "Offer valid_to timestamp must be strictly after valid_from."}
            )

        offer_type = attrs.get(
            "offer_type", getattr(self.instance, "offer_type", OfferType.PERCENTAGE)
        )
        discount_value = attrs.get("discount_value", getattr(self.instance, "discount_value", None))

        if discount_value is not None:
            if discount_value <= Decimal("0.00"):
                raise serializers.ValidationError(
                    {"discount_value": "Discount value must be strictly positive."}
                )
            if offer_type == OfferType.PERCENTAGE and discount_value > Decimal("100.00"):
                raise serializers.ValidationError(
                    {"discount_value": "Percentage discount cannot exceed 100.00%."}
                )

        merchant = attrs.get("merchant") or (self.instance.merchant if self.instance else None)
        outlet = attrs.get("outlet", getattr(self.instance, "outlet", None))
        catalog_item = attrs.get("catalog_item", getattr(self.instance, "catalog_item", None))

        if outlet and merchant and outlet.merchant_id != merchant.id:
            raise serializers.ValidationError(
                {"outlet": "Specified outlet does not belong to the selected merchant."}
            )

        if catalog_item and merchant and catalog_item.merchant_id != merchant.id:
            raise serializers.ValidationError(
                {"catalog_item": "Specified catalog item does not belong to the selected merchant."}
            )

        return attrs


class OfferCalculationRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Payload to calculate or preview discounted pricing."""

    offer_id = serializers.UUIDField(required=True)
    base_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), required=True
    )


class OfferCalculationResponseSerializer(serializers.Serializer[dict[str, Any]]):
    """Calculated pricing breakdown."""

    base_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    savings_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
