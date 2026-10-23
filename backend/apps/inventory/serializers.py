"""Serializers for Inventory domain requests and responses."""

from typing import Any

from rest_framework import serializers

from apps.merchants.models import OutletCategory

from .contracts import AvailabilityQuery


class AvailabilityQuerySerializer(serializers.Serializer[dict[str, Any]]):
    """Payload to check inventory availability across any marketplace vertical."""

    category = serializers.ChoiceField(choices=OutletCategory.choices, required=True)
    item_id = serializers.UUIDField(required=False, allow_null=True)
    outlet_id = serializers.UUIDField(required=False, allow_null=True)
    date = serializers.DateField(required=False, allow_null=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    quantity = serializers.IntegerField(required=False, default=1, min_value=1)
    parameters = serializers.DictField(required=False, default=dict)

    def to_domain_query(self) -> AvailabilityQuery:
        data: dict[str, Any] = self.validated_data
        return AvailabilityQuery(
            category=data["category"],
            item_id=data.get("item_id"),
            outlet_id=data.get("outlet_id"),
            date=data.get("date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            quantity=data.get("quantity", 1),
            parameters=data.get("parameters", {}),
        )


class AvailabilityResultSerializer(serializers.Serializer[dict[str, Any]]):
    """Normalized response representation for inventory availability checks."""

    is_available = serializers.BooleanField()
    available_units = serializers.IntegerField()
    category = serializers.CharField()
    breakdown = serializers.DictField()
    is_simulated = serializers.BooleanField()
    messages = serializers.ListField(child=serializers.CharField())
