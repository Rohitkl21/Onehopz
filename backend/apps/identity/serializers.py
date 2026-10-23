"""Serializers for user registration, authentication, and profile retrieval."""

import re
from typing import Any

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User, UserRole


class UserRegistrationSerializer(serializers.ModelSerializer[User]):
    """Serializer for customer registration with strict password validation."""

    password = serializers.CharField(write_only=True, required=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "role",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "first_name": {"required": True},
            "last_name": {"required": True},
            "phone_number": {"required": True},
            "role": {"default": UserRole.CUSTOMER},
        }

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def validate_phone_number(self, value: str) -> str:
        # Enforce international format: +[country_code][number] or clean 10-15 digits
        cleaned = re.sub(r"[\s\-\(\)]", "", value.strip())
        if not re.match(r"^\+?[1-9]\d{9,14}$", cleaned):
            raise serializers.ValidationError(
                "Phone number must be valid international format (e.g. +919876543210)."
            )
        if User.objects.filter(phone_number=cleaned).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return cleaned

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_role(self, value: str) -> str:
        # Public self-registration only permits CUSTOMER or MERCHANT_ADMIN role creation
        if value not in (UserRole.CUSTOMER, UserRole.MERCHANT_ADMIN):
            raise serializers.ValidationError(
                "Public registration permits only CUSTOMER or MERCHANT_ADMIN roles."
            )
        return value

    def create(self, validated_data: dict[str, Any]) -> User:
        return User.objects.create_user(**validated_data)


class UserLoginSerializer(serializers.Serializer[Any]):
    """Serializer for user login credentials."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            # Universal error message to prevent account enumeration
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("User account is inactive.")

        attrs["user"] = user
        return attrs


class RefreshTokenRequestSerializer(serializers.Serializer[Any]):
    """Serializer accepting refresh token in request body as fallback to cookie."""

    refresh_token = serializers.CharField(required=False, allow_blank=True)


class UserProfileSerializer(serializers.ModelSerializer[User]):
    """Serializer for current authenticated user profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_demo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
