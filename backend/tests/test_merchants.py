"""Automated tests for multi-tenant merchant organizations, outlets, staff, and RBAC."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework import status

from apps.identity.models import UserRole
from apps.identity.services import AuthService
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletCategory,
    OutletStaff,
    StaffRole,
)

User = get_user_model()


@pytest.fixture
def merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="owner_a@example.com",
        phone_number="+919000000001",
        password="Password#2026",
        first_name="Owner",
        last_name="Alpha",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def competitor_owner(db: None) -> User:
    return User.objects.create_user(
        email="owner_b@example.com",
        phone_number="+919000000002",
        password="Password#2026",
        first_name="Competitor",
        last_name="Beta",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def regular_customer(db: None) -> User:
    return User.objects.create_user(
        email="customer@example.com",
        phone_number="+919000000003",
        password="Password#2026",
        first_name="Regular",
        last_name="Customer",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def merchant_staff_user(db: None) -> User:
    return User.objects.create_user(
        email="staff_user@example.com",
        phone_number="+919000000004",
        password="Password#2026",
        first_name="Staff",
        last_name="Member",
        role=UserRole.MERCHANT_STAFF,
    )


def auth_headers(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_merchant_creation_and_automatic_ownership(merchant_owner: User) -> None:
    """TC-13: Merchant creation automatically establishes creator as OWNER."""
    client = Client()
    payload = {
        "business_name": "Alpha Cineplex Ltd",
        "legal_entity_name": "Alpha Entertainment Pvt Ltd",
        "gstin": "29ABCDE1234F1Z5",
    }
    response = client.post(
        "/api/v1/merchants/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    merchant_id = data["data"]["id"]

    # Verify membership created in DB
    membership = MerchantMembership.objects.filter(
        merchant_id=merchant_id, user=merchant_owner
    ).first()
    assert membership is not None
    assert membership.role == MerchantMembershipRole.OWNER


@pytest.mark.django_db
def test_merchant_tenant_isolation(merchant_owner: User, competitor_owner: User) -> None:
    """TC-14: One merchant cannot view or access another merchant's organization data."""
    # Create Merchant A for Owner A
    merchant_a = Merchant.objects.create(
        business_name="Merchant Alpha",
        legal_entity_name="Alpha Pvt Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant_a,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )

    client = Client()
    # Competitor attempts to access Merchant A's details
    response = client.get(
        f"/api/v1/merchants/{merchant_a.id}",
        **auth_headers(competitor_owner),
    )
    # Must be rejected with 403 Forbidden
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_unauthorized_membership_addition_blocked(
    merchant_owner: User, merchant_staff_user: User, regular_customer: User
) -> None:
    """TC-15: Regular staff member cannot add new members to merchant organization."""
    merchant = Merchant.objects.create(
        business_name="Alpha Dining",
        legal_entity_name="Alpha Foods Ltd",
        primary_contact=merchant_owner,
    )
    # merchant_owner is OWNER
    MerchantMembership.objects.create(
        merchant=merchant, user=merchant_owner, role=MerchantMembershipRole.OWNER
    )
    # merchant_staff_user is STAFF
    MerchantMembership.objects.create(
        merchant=merchant, user=merchant_staff_user, role=MerchantMembershipRole.STAFF
    )

    client = Client()
    # Staff attempts to add customer as an admin
    response = client.post(
        f"/api/v1/merchants/{merchant.id}/members",
        data={"user_email": regular_customer.email, "role": MerchantMembershipRole.ADMIN},
        content_type="application/json",
        **auth_headers(merchant_staff_user),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_duplicate_membership_constraint(merchant_owner: User, merchant_staff_user: User) -> None:
    """TC-16: Cannot add duplicate membership for the same user in a merchant organization."""
    merchant = Merchant.objects.create(
        business_name="Alpha Salons",
        legal_entity_name="Alpha Beauty Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant, user=merchant_owner, role=MerchantMembershipRole.OWNER
    )

    client = Client()
    # Add staff user first time
    resp1 = client.post(
        f"/api/v1/merchants/{merchant.id}/members",
        data={"user_email": merchant_staff_user.email, "role": MerchantMembershipRole.STAFF},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert resp1.status_code == status.HTTP_201_CREATED

    # Attempt to add same staff user second time
    resp2 = client.post(
        f"/api/v1/merchants/{merchant.id}/members",
        data={"user_email": merchant_staff_user.email, "role": MerchantMembershipRole.STAFF},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already a member" in str(resp2.json()["error"])


@pytest.mark.django_db
def test_outlet_creation_and_scoping(merchant_owner: User, competitor_owner: User) -> None:
    """TC-17: Outlet creation is scoped to authorized merchant administrators."""
    merchant = Merchant.objects.create(
        business_name="Alpha Hotels",
        legal_entity_name="Alpha Hospitality Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant, user=merchant_owner, role=MerchantMembershipRole.OWNER
    )

    client = Client()
    outlet_payload = {
        "name": "Alpha Grand Indiranagar",
        "category": OutletCategory.HOTEL,
        "address_line_1": "100 Feet Road, Indiranagar",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560038",
        "latitude": 12.9784,
        "longitude": 77.6408,
    }

    # Competitor cannot create outlet under Merchant A
    resp_unauth = client.post(
        f"/api/v1/merchants/{merchant.id}/outlets",
        data=outlet_payload,
        content_type="application/json",
        **auth_headers(competitor_owner),
    )
    assert resp_unauth.status_code == status.HTTP_403_FORBIDDEN

    # Owner creates outlet successfully
    resp_owner = client.post(
        f"/api/v1/merchants/{merchant.id}/outlets",
        data=outlet_payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert resp_owner.status_code == status.HTTP_201_CREATED
    assert resp_owner.json()["data"]["name"] == "Alpha Grand Indiranagar"


@pytest.mark.django_db
def test_outlet_staff_scoping_and_management(
    merchant_owner: User, merchant_staff_user: User, regular_customer: User
) -> None:
    """TC-18: Outlet staff can be assigned and removed by authorized managers."""
    merchant = Merchant.objects.create(
        business_name="Alpha Retail",
        legal_entity_name="Alpha Retail Pvt Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant, user=merchant_owner, role=MerchantMembershipRole.OWNER
    )
    outlet = Outlet.objects.create(
        merchant=merchant,
        name="Alpha Store Koramangala",
        category=OutletCategory.SURPLUS_FOOD,
        address_line_1="Koramangala 4th Block",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560034",
    )

    client = Client()
    # Owner assigns staff to outlet
    resp_assign = client.post(
        f"/api/v1/outlets/{outlet.id}/staff",
        data={"user_email": merchant_staff_user.email, "staff_role": StaffRole.SCANNER_OPERATOR},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert resp_assign.status_code == status.HTTP_201_CREATED

    # Attempt to assign the same staff member again
    resp_dup = client.post(
        f"/api/v1/outlets/{outlet.id}/staff",
        data={"user_email": merchant_staff_user.email, "staff_role": StaffRole.SCANNER_OPERATOR},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert resp_dup.status_code == status.HTTP_400_BAD_REQUEST

    # Remove staff from outlet
    resp_remove = client.delete(
        f"/api/v1/outlets/{outlet.id}/staff/{merchant_staff_user.id}",
        **auth_headers(merchant_owner),
    )
    assert resp_remove.status_code == status.HTTP_200_OK
    assert OutletStaff.objects.filter(outlet=outlet, user=merchant_staff_user).count() == 0


@pytest.mark.django_db
def test_absence_of_secret_leakage(merchant_owner: User) -> None:
    """TC-19: Response payloads never leak password hashes, token secrets, or keys."""
    client = Client()
    response = client.get("/api/v1/auth/me", **auth_headers(merchant_owner))
    assert response.status_code == status.HTTP_200_OK
    content = str(response.content)
    assert "password" not in content.lower()
    assert "pbkdf2" not in content.lower()
    assert "SECRET_KEY" not in content
