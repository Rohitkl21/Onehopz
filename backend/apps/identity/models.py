"""Identity models: custom User, UserRole choices, and secure RefreshToken."""

import hashlib
import uuid
from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models


class UserRole(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    MERCHANT_STAFF = "MERCHANT_STAFF", "Merchant Staff"
    MERCHANT_ADMIN = "MERCHANT_ADMIN", "Merchant Admin"
    PLATFORM_SUPPORT = "PLATFORM_SUPPORT", "Platform Support"
    FINANCE_ADMIN = "FINANCE_ADMIN", "Finance Admin"
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"


class UserManager(BaseUserManager["User"]):
    """Custom user manager using normalized email as unique identifier."""

    def create_user(
        self,
        email: str,
        phone_number: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        if not email:
            raise ValueError("The Email field must be set.")
        if not phone_number:
            raise ValueError("The Phone Number field must be set.")

        email = self.normalize_email(email).lower()
        extra_fields.setdefault("role", UserRole.CUSTOMER)
        extra_fields.setdefault("is_active", True)

        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        phone_number: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        extra_fields.setdefault("role", UserRole.SUPER_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Authoritative Custom User model for OneHopz.
    Decoupled from merchant organizations and outlets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255, db_index=True)
    phone_number = models.CharField(unique=True, max_length=20, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: UserManager = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone_number", "first_name", "last_name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["email", "role"], name="idx_users_email_role"),
            models.Index(fields=["phone_number"], name="idx_users_phone"),
            models.Index(fields=["is_demo"], name="idx_users_is_demo"),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_merchant_user(self) -> bool:
        return self.role in (UserRole.MERCHANT_ADMIN, UserRole.MERCHANT_STAFF)

    @property
    def is_platform_admin(self) -> bool:
        return self.role in (
            UserRole.SUPER_ADMIN,
            UserRole.FINANCE_ADMIN,
            UserRole.PLATFORM_SUPPORT,
        )


class RefreshToken(models.Model):
    """
    Secure Refresh Token storage with SHA-256 hash representation.
    Enforces single-use rotation, reuse detection, and revocation tracking.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_revoked = models.BooleanField(default=False, db_index=True)
    replaced_by_token = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replaces_token",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Refresh Token"
        verbose_name_plural = "Refresh Tokens"
        indexes = [
            models.Index(fields=["token_hash", "is_revoked"], name="idx_reftok_hash_revoked"),
            models.Index(fields=["user", "expires_at"], name="idx_reftok_user_expires"),
        ]

    def __str__(self) -> str:
        status_str = "revoked" if self.is_revoked else "active"
        return f"RefreshToken({self.user_id}, {status_str})"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Derive a deterministic SHA-256 hex digest from the raw token string."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
