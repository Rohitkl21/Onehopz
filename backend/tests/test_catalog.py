"""Automated test suite for Catalog domain, category registry, and tenant isolation."""

from decimal import Decimal

import pytest
from django.test import Client
from rest_framework import status

from apps.catalog.models import CatalogItem
from apps.catalog.registry import CategoryRegistry
from apps.identity.models import User, UserRole
from apps.identity.services import AuthService
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletCategory,
)
from apps.offers.models import OfferSpecification, OfferType


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
def platform_admin(db: None) -> User:
    return User.objects.create_user(
        email="admin@example.com",
        phone_number="+919111111104",
        password="Password#2026",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
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
        "outlet": str(outlet_b.id),
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
def test_catalog_item_update_and_logical_deletion(
    merchant_owner: User,
    other_merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """Catalog item is logically deactivated upon DELETE, keeping DB row and linked offers."""
    item = CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Original Movie",
        base_price=Decimal("300.00"),
    )
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        catalog_item=item,
        title="Movie 10% Off",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        valid_from="2026-10-01T00:00:00Z",
        valid_to="2026-10-31T23:59:59Z",
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

    # Owner soft delete succeeds
    del_res = client.delete(
        f"/api/v1/catalog/items/{item.id}/",
        **auth_headers(merchant_owner),
    )
    assert del_res.status_code == status.HTTP_200_OK
    assert del_res.json()["message"] == "Catalog item successfully deactivated."

    # Row STILL exists in database, with is_active=False
    refreshed_item = CatalogItem.objects.get(id=item.id)
    assert refreshed_item.is_active is False

    # Linked offer specification remains intact (NOT cascade deleted)
    assert OfferSpecification.objects.filter(id=offer.id).exists()

    # Repeated deactivation behaves predictably (idempotent 200 OK)
    repeat_del = client.delete(
        f"/api/v1/catalog/items/{item.id}/",
        **auth_headers(merchant_owner),
    )
    assert repeat_del.status_code == status.HTTP_200_OK

    # Deactivated item does NOT appear in public active listings
    public_res = client.get("/api/v1/catalog/items/")
    active_ids = [i["id"] for i in public_res.json()["data"]]
    assert str(item.id) not in active_ids


@pytest.mark.django_db
def test_catalog_visibility_anonymous_cannot_query_inactive(
    merchant_a: Merchant,
) -> None:
    """Anonymous user querying ?is_active=false receives 403 Forbidden."""
    CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Inactive Movie",
        base_price=Decimal("200.00"),
        is_active=False,
    )
    client = Client()
    res = client.get("/api/v1/catalog/items/?is_active=false")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_catalog_visibility_invalid_boolean_param_returns_400() -> None:
    """Supplying a malformed boolean filter for is_active returns 400 Bad Request."""
    client = Client()
    res = client.get("/api/v1/catalog/items/?is_active=notabool")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_catalog_visibility_customer_cannot_query_inactive(
    regular_customer: User,
    merchant_a: Merchant,
) -> None:
    """Ordinary authenticated customer querying ?is_active=false receives 403 Forbidden."""
    client = Client()
    res = client.get("/api/v1/catalog/items/?is_active=false", **auth_headers(regular_customer))
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_catalog_visibility_cross_tenant_merchant_cannot_query_inactive(
    merchant_owner: User,
    merchant_b: Merchant,
) -> None:
    """Merchant A owner cannot query competitor Merchant B's inactive catalog items."""
    CatalogItem.objects.create(
        merchant=merchant_b,
        category=OutletCategory.CINEMA,
        title="Competitor Secret Draft",
        base_price=Decimal("500.00"),
        is_active=False,
    )
    client = Client()
    res = client.get(
        f"/api/v1/catalog/items/?merchant_id={merchant_b.id}&is_active=false",
        **auth_headers(merchant_owner),
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_catalog_visibility_merchant_omitted_param_scoped_to_own_merchants(
    merchant_owner: User,
    merchant_a: Merchant,
    merchant_b: Merchant,
) -> None:
    """Merchant A querying management view without merchant_id receives only their own items."""
    CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Merchant A Inactive Item",
        base_price=Decimal("200.00"),
        is_active=False,
    )
    CatalogItem.objects.create(
        merchant=merchant_b,
        category=OutletCategory.CINEMA,
        title="Merchant B Inactive Item",
        base_price=Decimal("300.00"),
        is_active=False,
    )

    client = Client()
    res = client.get("/api/v1/catalog/items/?is_active=false", **auth_headers(merchant_owner))
    assert res.status_code == status.HTTP_200_OK
    items = res.json()["data"]
    # Should only contain Merchant A items, never Merchant B items
    item_titles = [i["title"] for i in items]
    assert "Merchant A Inactive Item" in item_titles
    assert "Merchant B Inactive Item" not in item_titles


@pytest.mark.django_db
def test_catalog_visibility_platform_admin_can_query_all_inactive(
    platform_admin: User,
    merchant_a: Merchant,
    merchant_b: Merchant,
) -> None:
    """Platform administrator can view inactive items across all merchant organizations."""
    CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Alpha Draft",
        base_price=Decimal("150.00"),
        is_active=False,
    )
    CatalogItem.objects.create(
        merchant=merchant_b,
        category=OutletCategory.HOTEL,
        title="Beta Draft Suite",
        base_price=Decimal("3500.00"),
        is_active=False,
    )
    client = Client()
    res = client.get("/api/v1/catalog/items/?is_active=false", **auth_headers(platform_admin))
    assert res.status_code == status.HTTP_200_OK
    titles = [i["title"] for i in res.json()["data"]]
    assert "Alpha Draft" in titles
    assert "Beta Draft Suite" in titles


@pytest.mark.django_db
def test_catalog_inactive_item_detail_view_permissions(
    merchant_owner: User,
    regular_customer: User,
    merchant_a: Merchant,
) -> None:
    """Inactive catalog item detail view returns 404 for customers, 200 for merchant owner."""
    item = CatalogItem.objects.create(
        merchant=merchant_a,
        category=OutletCategory.CINEMA,
        title="Private Item",
        base_price=Decimal("250.00"),
        is_active=False,
    )
    client = Client()

    # Anonymous user gets 404
    anon_res = client.get(f"/api/v1/catalog/items/{item.id}/")
    assert anon_res.status_code == status.HTTP_404_NOT_FOUND

    # Customer gets 404
    cust_res = client.get(f"/api/v1/catalog/items/{item.id}/", **auth_headers(regular_customer))
    assert cust_res.status_code == status.HTTP_404_NOT_FOUND

    # Merchant owner gets 200 OK
    owner_res = client.get(f"/api/v1/catalog/items/{item.id}/", **auth_headers(merchant_owner))
    assert owner_res.status_code == status.HTTP_200_OK
    assert owner_res.json()["data"]["title"] == "Private Item"
