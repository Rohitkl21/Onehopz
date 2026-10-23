"""Serializers for Merchant organizations, Outlets, and Staff memberships."""

from typing import Any

from rest_framework import serializers

from apps.identity.models import User

from .models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletStaff,
)


class MerchantSerializer(serializers.ModelSerializer[Merchant]):
    """Serializer for Merchant organizations."""

    class Meta:
        model = Merchant
        fields = [
            "id",
            "business_name",
            "legal_entity_name",
            "gstin",
            "pan",
            "fssai_license_number",
            "primary_contact_id",
            "verification_status",
            "is_active",
            "is_demo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "primary_contact_id",
            "verification_status",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data: dict[str, Any]) -> Merchant:
        user = self.context["request"].user
        validated_data["primary_contact"] = user
        merchant = Merchant.objects.create(**validated_data)
        # Automatically make creator the OWNER of the merchant organization
        MerchantMembership.objects.create(
            merchant=merchant,
            user=user,
            role=MerchantMembershipRole.OWNER,
        )
        return merchant


class MerchantMembershipSerializer(serializers.ModelSerializer[MerchantMembership]):
    """Serializer for managing team members within a merchant organization."""

    user_email = serializers.EmailField(write_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = MerchantMembership
        fields = [
            "id",
            "merchant_id",
            "user_id",
            "user_email",
            "user_name",
            "role",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "merchant_id", "user_id", "user_name", "created_at"]

    def validate_user_email(self, value: str) -> User:
        user = User.objects.filter(email=value.strip().lower()).first()
        if not user:
            raise serializers.ValidationError("User with this email does not exist.")
        return user

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = attrs.get("user_email")
        merchant = self.context.get("merchant")
        if (
            merchant
            and user
            and MerchantMembership.objects.filter(merchant=merchant, user=user).exists()
        ):
            raise serializers.ValidationError(
                {"user_email": ["User is already a member of this merchant."]}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> MerchantMembership:
        user: User = validated_data.pop("user_email")
        merchant = self.context["merchant"]
        return MerchantMembership.objects.create(
            merchant=merchant,
            user=user,
            **validated_data,
        )


class OutletSerializer(serializers.ModelSerializer[Outlet]):
    """Serializer for Outlets (physical venues/branches)."""

    class Meta:
        model = Outlet
        fields = [
            "id",
            "merchant_id",
            "name",
            "category",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "latitude",
            "longitude",
            "is_active",
            "is_demo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "merchant_id", "created_at", "updated_at"]

    def create(self, validated_data: dict[str, Any]) -> Outlet:
        merchant = self.context["merchant"]
        return Outlet.objects.create(merchant=merchant, **validated_data)


class OutletStaffSerializer(serializers.ModelSerializer[OutletStaff]):
    """Serializer for assigning staff to specific outlets."""

    user_email = serializers.EmailField(write_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = OutletStaff
        fields = [
            "id",
            "outlet_id",
            "user_id",
            "user_email",
            "user_name",
            "staff_role",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "outlet_id", "user_id", "user_name", "created_at"]

    def validate_user_email(self, value: str) -> User:
        user = User.objects.filter(email=value.strip().lower()).first()
        if not user:
            raise serializers.ValidationError("User with this email does not exist.")
        return user

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = attrs.get("user_email")
        outlet = self.context.get("outlet")
        if outlet and user and OutletStaff.objects.filter(outlet=outlet, user=user).exists():
            raise serializers.ValidationError(
                {"user_email": ["Staff member is already assigned to this outlet."]}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> OutletStaff:
        user: User = validated_data.pop("user_email")
        outlet = self.context["outlet"]
        return OutletStaff.objects.create(
            outlet=outlet,
            user=user,
            **validated_data,
        )
