"""Multi-tenant merchant organization, outlet, and membership models."""

import uuid

from django.conf import settings
from django.db import models


class MerchantVerificationStatus(models.TextChoices):
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending Verification"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


class MerchantMembershipRole(models.TextChoices):
    OWNER = "OWNER", "Owner"
    ADMIN = "ADMIN", "Admin"
    FINANCE = "FINANCE", "Finance"
    STAFF = "STAFF", "Staff"


class OutletCategory(models.TextChoices):
    CINEMA = "CINEMA", "Cinema"
    RESTAURANT = "RESTAURANT", "Restaurant"
    SURPLUS_FOOD = "SURPLUS_FOOD", "Surplus Food"
    HOTEL = "HOTEL", "Hotel"
    SALON = "SALON", "Salon"
    EVENT = "EVENT", "Event"
    TRAVEL = "TRAVEL", "Travel"


class StaffRole(models.TextChoices):
    MANAGER = "MANAGER", "Manager"
    CASHIER = "CASHIER", "Cashier"
    SCANNER_OPERATOR = "SCANNER_OPERATOR", "Scanner Operator"


class Merchant(models.Model):
    """
    Merchant organization entity.
    Owns multiple outlets, inventory policies, and settlement bank profiles.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_name = models.CharField(max_length=255)
    legal_entity_name = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    fssai_license_number = models.CharField(max_length=14, blank=True, null=True)
    primary_contact = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="managed_merchants",
    )
    verification_status = models.CharField(
        max_length=50,
        choices=MerchantVerificationStatus.choices,
        default=MerchantVerificationStatus.PENDING_VERIFICATION,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Merchant"
        verbose_name_plural = "Merchants"
        indexes = [
            models.Index(fields=["verification_status"], name="idx_merch_verification"),
            models.Index(fields=["is_demo"], name="idx_merch_is_demo"),
        ]

    def __str__(self) -> str:
        return f"{self.business_name} ({self.verification_status})"


class MerchantMembership(models.Model):
    """
    Explicit membership linking user to a merchant organization.
    Enforces multi-tenant organizational access control.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="merchant_memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=MerchantMembershipRole.choices,
        default=MerchantMembershipRole.STAFF,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Merchant Membership"
        verbose_name_plural = "Merchant Memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "user"],
                name="uq_merchant_membership",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.merchant} ({self.role})"


class Outlet(models.Model):
    """
    Physical venue, restaurant branch, theater screen location, or salon studio.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="outlets",
    )
    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=50,
        choices=OutletCategory.choices,
    )
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country_code = models.CharField(max_length=2, default="IN")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Outlet"
        verbose_name_plural = "Outlets"
        indexes = [
            models.Index(fields=["category", "city"], name="idx_outlet_cat_city"),
            models.Index(fields=["is_demo"], name="idx_outlet_is_demo"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}) [{self.category}]"


class OutletStaff(models.Model):
    """
    Staff assignment to a specific outlet location.
    Enforces terminal and gate redemption scoping.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name="staff_memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="outlet_memberships",
    )
    staff_role = models.CharField(
        max_length=50,
        choices=StaffRole.choices,
        default=StaffRole.CASHIER,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Outlet Staff Assignment"
        verbose_name_plural = "Outlet Staff Assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["outlet", "user"],
                name="uq_outlet_staff",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} -> {self.outlet} ({self.staff_role})"
