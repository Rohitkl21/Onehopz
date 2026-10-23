"""Automated test suite for Catalog domain, category registry, and tenant isolation."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework import status

from apps.catalog.models import CatalogItem
from apps.catalog.registry import CategoryRegistry
from apps.identity.models import UserRole
from apps.identity.services import AuthService
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletCategory,
)

User = get_user_model()


@pytest.fixture
def merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="cat_owner@example.com",
        phone_number="+919111111101",
        password="Password#2026",
        first_name="Catalog",
        last_name="Owner",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def other_merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="other_owner@example.com",
        phone_number="+919111111102",
        password="Password#2026",
        first_name="Other",
        last_name="Owner",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def regular_customer(db: None) -> User:
    return User.objects.create_user(
        email="shopper@example.com",
        phone_number="+919111111103",
        password="Password#2026",
        first_name="Shopper",
        last_name="One",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def merchant_a(merchant_owner: User) -> Merchant:
    merchant = Merchant.objects.create(
        business_name="Alpha Entertainment",
        legal_entity_name="Alpha Entertainment Pvt Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    return merchant


@pytest.fixture
def merchant_b(other_merchant_owner: User) -> Merchant:
    merchant = Merchant.objects.create(
        business_name="Beta Cinema Corp",
        legal_entity_name="Beta Cinema Corp Ltd",
        primary_contact=other_merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=other_merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    return merchant


@pytest.fixture
def outlet_a(merchant_a: Merchant) -> Outlet:
    return Outlet.objects.create(
        merchant=merchant_a,
        name="Alpha Mall Multiplex",
        category=OutletCategory.CINEMA,
        address_line_1="100 MG Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
    )


@pytest.fixture
def outlet_b(merchant_b: Merchant) -> Outlet:
    return Outlet.objects.create(
        merchant=merchant_b,
        name="Beta Screen 1",
        category=OutletCategory.CINEMA,
        address_line_1="200 Brigade Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560025",
    )


def auth_headers(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_category_registry_covers_all_seven_verticals() -> None:
    """Verify category registry defines capabilities for all 7 platform categories."""
    categories = CategoryRegistry.list_all()
    assert len(categories) == 7

    cat_keys = {c.category for c in categories}
    expected = {
        OutletCategory.CINEMA,
        OutletCategory.RESTAURANT,
        OutletCategory.SURPLUS_FOOD,
        OutletCategory.HOTEL,
        OutletCategory.SALON,
        OutletCategory.EVENT,
        OutletCategory.TRAVEL,
    }
    assert cat_keys == expected

    # Verify specific capability flags
    cinema_cap = CategoryRegistry.get_capabilities(OutletCategory.CINEMA)
    assert cinema_cap is not None
    assert cinema_cap.has_seat_map is True
    assert cinema_cap.allocation_unit == "seat"

    food_cap = CategoryRegistry.get_capabilities(OutletCategory.SURPLUS_FOOD)
    assert food_cap is not None
    assert food_cap.has_expiry_window is True
    assert food_cap.requires_fssai is True

    hotel_cap = CategoryRegistry.get_capabilities(OutletCategory.HOTEL)
    assert hotel_cap is not None
    assert hotel_cap.has_date_range is True

    travel_cap = CategoryRegistry.get_capabilities(OutletCategory.TRAVEL)
    assert travel_cap is not None
    assert travel_cap.is_supplier_managed is True


@pytest.mark.django_db
def test_category_registry_rejects_unsupported() -> None:
    """Verify invalid category keys return None and evaluate as invalid."""
    assert CategoryRegistry.get_capabilities("CRYPTO_EXCHANGE") is None
    assert CategoryRegistry.is_valid_category("INVALID_CAT") is False


@pytest.mark.django_db
def test_category_list_api_endpoint() -> None:
    """Verify GET /api/v1/catalog/categories/ returns all categories publicly."""
    client = Client()
    response = client.get("/api/v1/catalog/categories/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 7


@pytest.mark.django_db
def test_create_catalog_item_success(
    merchant_owner: User,
    merchant_a: Merchant,
    outlet_a: Outlet,
) -> None:
    """Merchant owner can create a catalog item for their organization."""
    client = Client()
    payload = {
        "merchant": str(merchant_a.id),
        "outlet": str(outlet_a.id),
        "category": OutletCategory.CINEMA,
        "title": "Evening IMAX Show - Interstellar",
        "description": "Late-evening IMAX 70mm screening",
        "base_price": "450.00",
        "currency": "INR",
        "metadata": {"screen": 1, "format": "IMAX 2D"},
    }
    response = client.post(
        "/api/v1/catalog/items/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    assert data["data"]["title"] == "Evening IMAX Show - Interstellar"
    assert Decimal(data["data"]["base_price"]) == Decimal("450.00")
    assert data["data"]["merchant_name"] == "Alpha Entertainment"
    assert data["data"]["outlet_name"] == "Alpha Mall Multiplex"


@pytest.mark.django_db
def test_create_catalog_item_unauthorized_user_blocked(
    other_merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """User B cannot create a catalog item under User A's merchant."""
    client = Client()
    payload = {
        "merchant": str(merchant_a.id),
        "category": OutletCategory.CINEMA,
        "title": "Illicit Listing",
        "base_price": "100.00",
    }
    response = client.post(
        "/api/v1/catalog/items/",
        data=payload,
        content_type="application/json",
        **auth_headers(other_merchant_owner),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_cross_tenant_outlet_association_rejected(
    merchant_owner: User,
    merchant_a: Merchant,
    outlet_b: Outlet,
) -> None:
    """Cannot attach an outlet from a competitor merchant to a catalog item."""
    client = Client()
    payload = {
        "merchant": str(merchant_a.id),
        "outlet": str(outlet_b.id),  # Belongs to merchant_b
        "category": OutletCategory.CINEMA,
        "title": "Cross Tenant Attempt",
        "base_price": "200.00",
    }
    response = client.post(
        "/api/v1/catalog/items/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "outlet" in data["error"]["details"]


@pytest.mark.django_db
def test_negative_base_price_rejected(
    merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """Base price cannot be negative."""
    client = Client()
    payload = {
        "merchant": str(merchant_a.id),
        "category": OutletCategory.CINEMA,
        "title": "Negative Price Item",
        "base_price": "-50.00",
    }
    response = client.post(
        "/api/v1/catalog/items/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "base_price" in data["error"]["details"]


@pytest.mark.django_db
def test_catalog_item_update_and_delete(
    merchant_owner: User,
    other_merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """Catalog item can be updated and deleted by owner, but not by unauthorized competitor."""
    item = CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Original Movie",
        base_price=Decimal("300.00"),
    )

    client = Client()

    # Competitor update attempt blocked
    comp_res = client.patch(
        f"/api/v1/catalog/items/{item.id}/",
        data={"base_price": "1.00"},
        content_type="application/json",
        **auth_headers(other_merchant_owner),
    )
    assert comp_res.status_code == status.HTTP_403_FORBIDDEN

    # Owner update succeeds
    owner_res = client.patch(
        f"/api/v1/catalog/items/{item.id}/",
        data={"base_price": "350.00", "title": "Updated Movie Title"},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert owner_res.status_code == status.HTTP_200_OK
    assert Decimal(owner_res.json()["data"]["base_price"]) == Decimal("350.00")
    assert owner_res.json()["data"]["title"] == "Updated Movie Title"

    # Owner delete succeeds
    del_res = client.delete(
        f"/api/v1/catalog/items/{item.id}/",
        **auth_headers(merchant_owner),
    )
    assert del_res.status_code == status.HTTP_200_OK
    assert not CatalogItem.objects.filter(id=item.id).exists()


@pytest.mark.django_db
def test_catalog_filtering(merchant_a: Merchant, merchant_b: Merchant) -> None:
    """Filtering catalog items by merchant_id and category."""
    CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Cinema Item A",
        base_price=Decimal("200.00"),
    )
    CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.RESTAURANT,
        title="Buffet Dinner A",
        base_price=Decimal("800.00"),
    )
    CatalogItem.objects.create(
        merchant=merchant_b,
        category=OutletCategory.CINEMA,
        title="Cinema Item B",
        base_price=Decimal("250.00"),
    )

    client = Client()

    # Filter by merchant_a
    res_a = client.get(f"/api/v1/catalog/items/?merchant_id={merchant_a.id}")
    assert res_a.status_code == status.HTTP_200_OK
    items_a = res_a.json()["data"]
    assert len(items_a) == 2

    # Filter by merchant_a and category RESTAURANT
    res_restaurant = client.get(
        f"/api/v1/catalog/items/?merchant_id={merchant_a.id}&category=RESTAURANT"
    )
    assert res_restaurant.status_code == status.HTTP_200_OK
    restaurant_items = res_restaurant.json()["data"]
    assert len(restaurant_items) == 1
    assert restaurant_items[0]["title"] == "Buffet Dinner A"
