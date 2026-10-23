"""Serializers for the Orders application."""

from typing import Any

from rest_framework import serializers

from .models import Order, OrderItem


class CheckoutRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Serializer validating incoming checkout requests."""

    hold_id = serializers.UUIDField(required=True)
    customer_contact = serializers.DictField(required=False, default=dict)

    def validate_customer_contact(self, value: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize customer contact details."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Customer contact must be a JSON object.")
        sanitized = {
            "name": str(value.get("name", "")).strip(),
            "email": str(value.get("email", "")).strip().lower(),
            "phone": str(value.get("phone", "")).strip(),
        }
        return sanitized


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    """Serializer representing an immutable order line item snapshot."""

    unit_base_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_sale_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_applied = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "unit_identifier",
            "quantity",
            "unit_base_price",
            "unit_sale_price",
            "discount_applied",
            "currency",
            "booking_terms",
            "item_metadata",
        ]


class OrderDetailSerializer(serializers.ModelSerializer[Order]):
    """Serializer representing authoritative order detail and financial snapshots."""

    items = OrderItemSerializer(many=True, read_only=True)
    gross_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_payable_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_payment_expired = serializers.BooleanField(read_only=True)
    effective_status = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "checkout_session_id",
            "category",
            "status",
            "effective_status",
            "gross_amount",
            "discount_amount",
            "platform_fee",
            "tax_amount",
            "net_payable_amount",
            "currency",
            "payment_deadline",
            "is_payment_expired",
            "cancellation_deadline",
            "cancellation_policy_type",
            "customer_contact",
            "lock_reference_snapshot",
            "is_demo",
            "items",
            "created_at",
            "updated_at",
        ]
