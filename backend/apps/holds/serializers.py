"""Serializers for Hold creation, retrieval, and status reporting."""

from typing import Any

from rest_framework import serializers

from apps.catalog.models import CatalogItem
from apps.merchants.models import OutletCategory

from .models import Hold


class HoldAcquireSerializer(serializers.Serializer[Any]):
    """Payload validation for ephemeral hold acquisition."""

    listing_id = serializers.UUIDField(required=False, help_text="Alias for catalog_item_id.")
    catalog_item_id = serializers.UUIDField(required=False)
    category = serializers.ChoiceField(choices=OutletCategory.choices)
    selection_parameters = serializers.DictField(default=dict)
    quantity = serializers.IntegerField(default=1, min_value=1)
    offer_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        item_id = attrs.get("catalog_item_id") or attrs.get("listing_id")
        if not item_id:
            raise serializers.ValidationError(
                {"catalog_item_id": "Either catalog_item_id or listing_id must be provided."}
            )
        attrs["catalog_item_id"] = item_id

        # Validate that catalog item exists
        try:
            catalog_item = CatalogItem.objects.select_related("outlet", "merchant").get(id=item_id)
        except CatalogItem.DoesNotExist:
            raise serializers.ValidationError(
                {"catalog_item_id": "Catalog item not found."}
            ) from None

        if not catalog_item.is_active:
            raise serializers.ValidationError({"catalog_item_id": "Catalog item is inactive."})

        if catalog_item.category != attrs["category"]:
            raise serializers.ValidationError(
                {"category": f"Item belongs to {catalog_item.category}, not {attrs['category']}."}
            )

        attrs["catalog_item"] = catalog_item
        return attrs


class HoldDetailSerializer(serializers.ModelSerializer[Hold]):
    """Output serializer for authoritative ephemeral hold details."""

    hold_id = serializers.UUIDField(source="id", read_only=True)
    status = serializers.CharField(source="effective_status", read_only=True)
    ttl_remaining_seconds = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Hold
        fields = [
            "hold_id",
            "category",
            "status",
            "held_at",
            "expires_at",
            "ttl_remaining_seconds",
            "locked_units",
            "total_price",
            "currency",
            "is_expired",
            "lock_reference",
            "is_demo",
        ]
        read_only_fields = fields
