"""Automated test suite for Offers domain, dynamic yield pricing, currency consistency, and calculation integrity."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import CatalogItem
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
from apps.offers.services import calculate_discounted_price


@pytest.fixture
def merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="offer_owner@example.com",
        phone_number="+919222222201",
        password="Password#2026",
        first_name="Offer",
        last_name="Manager",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def competitor_owner(db: None) -> User:
    return User.objects.create_user(
        email="offer_comp@example.com",
        phone_number="+919222222202",
        password="Password#2026",
        first_name="Competitor",
        last_name="Owner",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def regular_customer(db: None) -> User:
    return User.objects.create_user(
        email="customer@example.com",
        phone_number="+919222222203",
        password="Password#2026",
        first_name="Regular",
        last_name="Customer",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def platform_admin(db: None) -> User:
    return User.objects.create_user(
        email="admin@example.com",
        phone_number="+919222222204",
        password="Password#2026",
        first_name="Platform",
        last_name="Admin",
        role=UserRole.SUPER_ADMIN,
    )


@pytest.fixture
def merchant_a(merchant_owner: User) -> Merchant:
    merchant = Merchant.objects.create(
        business_name="Spice Kitchen Organics",
        legal_entity_name="Spice Kitchen Organics Pvt Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    return merchant


@pytest.fixture
def merchant_b(competitor_owner: User) -> Merchant:
    merchant = Merchant.objects.create(
        business_name="Green Harvest Food",
        legal_entity_name="Green Harvest Ltd",
        primary_contact=competitor_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=competitor_owner,
        role=MerchantMembershipRole.OWNER,
    )
    return merchant


@pytest.fixture
def outlet_a(merchant_a: Merchant) -> Outlet:
    return Outlet.objects.create(
        merchant=merchant_a,
        name="Indiranagar Branch",
        category=OutletCategory.SURPLUS_FOOD,
        address_line_1="12 100ft Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560038",
    )


@pytest.fixture
def item_a(merchant_a: Merchant, outlet_a: Outlet) -> CatalogItem:
    return CatalogItem.objects.create(
        merchant=merchant_a,
        outlet=outlet_a,
        category=OutletCategory.SURPLUS_FOOD,
        title="Surplus Organic Grocery Box",
        base_price=Decimal("600.00"),
        currency="INR",
    )


def auth_headers(user: User) -> dict[str, str]:
    token = AuthService.create_access_token(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db
def test_create_percentage_offer_success(
    merchant_owner: User,
    merchant_a: Merchant,
    item_a: CatalogItem,
) -> None:
    """Merchant owner can create a percentage-based offer specification with derived currency."""
    client = Client()
    now = timezone.now()
    payload = {
        "merchant": str(merchant_a.id),
        "catalog_item": str(item_a.id),
        "category": OutletCategory.SURPLUS_FOOD,
        "title": "Evening Surplus 40% Off",
        "description": "40% discount for pickup during last hour",
        "offer_type": OfferType.PERCENTAGE,
        "discount_value": "40.00",
        "max_discount_amount": "300.00",
        "floor_price": "200.00",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(hours=4)).isoformat(),
    }
    response = client.post(
        "/api/v1/offers/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    assert Decimal(data["data"]["discount_value"]) == Decimal("40.00")
    assert Decimal(data["data"]["max_discount_amount"]) == Decimal("300.00")
    assert data["data"]["currency"] == "INR"


@pytest.mark.django_db
def test_offer_currency_consistency_validation(
    merchant_owner: User,
    merchant_a: Merchant,
    item_a: CatalogItem,
) -> None:
    """Offer currency must match the bound catalog item currency."""
    client = Client()
    now = timezone.now()
    payload = {
        "merchant": str(merchant_a.id),
        "catalog_item": str(item_a.id),  # item_a has currency INR
        "title": "USD Mismatch Attempt",
        "offer_type": OfferType.FIXED_AMOUNT,
        "discount_value": "50.00",
        "currency": "USD",  # Mismatched currency
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(hours=2)).isoformat(),
    }
    response = client.post(
        "/api/v1/offers/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "currency" in data["error"]["details"]


@pytest.mark.django_db
def test_offer_floor_price_validation_rules(
    merchant_owner: User,
    merchant_a: Merchant,
    item_a: CatalogItem,
) -> None:
    """Floor price cannot be negative, cannot exceed base price, and fixed discount cannot breach floor."""
    client = Client()
    now = timezone.now()
    base_payload = {
        "merchant": str(merchant_a.id),
        "catalog_item": str(item_a.id),  # base_price = 600.00
        "title": "Floor Price Test",
        "offer_type": OfferType.PERCENTAGE,
        "discount_value": "20.00",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(hours=2)).isoformat(),
    }

    # Negative floor price
    res_neg = client.post(
        "/api/v1/offers/",
        data={**base_payload, "floor_price": "-10.00"},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert res_neg.status_code == status.HTTP_400_BAD_REQUEST

    # Floor price > base price (600.00)
    res_exceed = client.post(
        "/api/v1/offers/",
        data={**base_payload, "floor_price": "750.00"},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert res_exceed.status_code == status.HTTP_400_BAD_REQUEST
    assert "floor_price" in res_exceed.json()["error"]["details"]

    # Fixed discount that inherently breaches floor price (600 - 450 = 150 < 200 floor)
    res_breach = client.post(
        "/api/v1/offers/",
        data={
            **base_payload,
            "offer_type": OfferType.FIXED_AMOUNT,
            "discount_value": "450.00",
            "floor_price": "200.00",
        },
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert res_breach.status_code == status.HTTP_400_BAD_REQUEST
    assert "discount_value" in res_breach.json()["error"]["details"]


@pytest.mark.django_db
def test_pricing_calculation_service_floor_price_clamping(merchant_a: Merchant) -> None:
    """Test pricing calculation service sets is_floor_price_clamped and actual savings percentage."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="50% Off with Floor 150",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("50.00"),
        floor_price=Decimal("150.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    # Base price 200: 50% discount would be 100, which puts price at 100 (below floor 150).
    # Clamps discount to 50, final price 150.
    result = calculate_discounted_price(Decimal("200.00"), offer)
    assert result.discount_amount == Decimal("50.00")
    assert result.final_price == Decimal("150.00")
    assert result.is_floor_price_clamped is True
    assert result.actual_savings_percentage == Decimal("25.00")
    assert result.advertised_discount_value == Decimal("50.00")


@pytest.mark.django_db
def test_pricing_calculation_service_currency_mismatch_rejected(merchant_a: Merchant) -> None:
    """Calling calculation service with mismatched currency raises ValueError."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="INR Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        currency="INR",
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    with pytest.raises(ValueError, match="Currency mismatch"):
        calculate_discounted_price(Decimal("100.00"), offer, currency="USD")


@pytest.mark.django_db
def test_offer_visibility_anonymous_cannot_query_inactive(merchant_a: Merchant) -> None:
    """Anonymous user querying ?is_active=false receives 403 Forbidden."""
    now = timezone.now()
    OfferSpecification.objects.create(
        merchant=merchant_a,
        title="Inactive Draft Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("15.00"),
        is_active=False,
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    client = Client()
    res = client.get("/api/v1/offers/?is_active=false")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_offer_visibility_invalid_boolean_param_returns_400() -> None:
    """Supplying a malformed boolean for is_active returns 400 Bad Request."""
    client = Client()
    res = client.get("/api/v1/offers/?is_active=invalid_param")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_offer_visibility_merchant_omitted_param_scoped_to_own_merchants(
    merchant_owner: User,
    merchant_a: Merchant,
    merchant_b: Merchant,
) -> None:
    """Merchant A owner querying offers without merchant_id only receives Merchant A offers."""
    now = timezone.now()
    OfferSpecification.objects.create(
        merchant=merchant_a,
        title="Merchant A Inactive Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        is_active=False,
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    OfferSpecification.objects.create(
        merchant=merchant_b,
        title="Merchant B Inactive Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("25.00"),
        is_active=False,
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    client = Client()
    res = client.get("/api/v1/offers/?is_active=false", **auth_headers(merchant_owner))
    assert res.status_code == status.HTTP_200_OK
    titles = [o["title"] for o in res.json()["data"]]
    assert "Merchant A Inactive Offer" in titles
    assert "Merchant B Inactive Offer" not in titles


@pytest.mark.django_db
def test_offer_logical_deletion_preserves_row(
    merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """Deleting an offer logically deactivates it without deleting the database row."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="Offer To Soft Delete",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("30.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    client = Client()
    del_res = client.delete(f"/api/v1/offers/{offer.id}/", **auth_headers(merchant_owner))
    assert del_res.status_code == status.HTTP_200_OK
    assert del_res.json()["message"] == "Offer specification successfully deactivated."

    # Row remains in database
    refreshed = OfferSpecification.objects.get(id=offer.id)
    assert refreshed.is_active is False


@pytest.mark.django_db
def test_authoritative_offer_calculation_prevents_price_tampering(
    merchant_a: Merchant,
    item_a: CatalogItem,
) -> None:
    """Caller-provided base_price cannot contradict authoritative bound catalog item base price."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        catalog_item=item_a,  # base_price = 600.00
        title="Bound Item Offer 20%",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    client = Client()

    # Attempting to tamper base_price to 100.00 fails with PRICE_MISMATCH
    tamper_res = client.post(
        "/api/v1/offers/calculate/",
        data={"offer_id": str(offer.id), "base_price": "100.00"},
        content_type="application/json",
    )
    assert tamper_res.status_code == status.HTTP_400_BAD_REQUEST
    assert tamper_res.json()["error"]["code"] == "PRICE_MISMATCH"

    # Authoritative calculation without passing base_price succeeds using item_a.base_price
    auth_res = client.post(
        "/api/v1/offers/calculate/",
        data={"offer_id": str(offer.id)},
        content_type="application/json",
    )
    assert auth_res.status_code == status.HTTP_200_OK
    data = auth_res.json()["data"]
    assert Decimal(data["base_price"]) == Decimal("600.00")
    assert Decimal(data["discount_amount"]) == Decimal("120.00")
    assert Decimal(data["final_price"]) == Decimal("480.00")
    assert data["is_floor_price_clamped"] is False


@pytest.mark.django_db
def test_authoritative_offer_calculation_rejects_inactive_or_expired(
    merchant_a: Merchant,
    item_a: CatalogItem,
) -> None:
    """Inactive or expired offers cannot be calculated for customers."""
    now = timezone.now()
    inactive_offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        catalog_item=item_a,
        title="Inactive Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        is_active=False,
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    expired_offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        catalog_item=item_a,
        title="Expired Offer",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        valid_from=now - timedelta(hours=5),
        valid_to=now - timedelta(hours=1),
    )
    client = Client()

    res_inact = client.post(
        "/api/v1/offers/calculate/",
        data={"offer_id": str(inactive_offer.id)},
        content_type="application/json",
    )
    assert res_inact.status_code == status.HTTP_400_BAD_REQUEST
    assert res_inact.json()["error"]["code"] == "OFFER_INACTIVE"

    res_exp = client.post(
        "/api/v1/offers/calculate/",
        data={"offer_id": str(expired_offer.id)},
        content_type="application/json",
    )
    assert res_exp.status_code == status.HTTP_400_BAD_REQUEST
    assert res_exp.json()["error"]["code"] == "OFFER_EXPIRED"


@pytest.mark.django_db
def test_authoritative_offer_calculation_rejects_inactive_bound_item(
    merchant_a: Merchant,
    outlet_a: Outlet,
) -> None:
    """An offer bound to a deactivated catalog item cannot be calculated."""
    inactive_item = CatalogItem.objects.create(
        merchant=merchant_a,
        outlet=outlet_a,
        category=OutletCategory.SURPLUS_FOOD,
        title="Deactivated Grocery Item",
        base_price=Decimal("400.00"),
        is_active=False,
    )
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        catalog_item=inactive_item,
        title="Offer on Inactive Item",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("25.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )
    client = Client()
    res = client.post(
        "/api/v1/offers/calculate/",
        data={"offer_id": str(offer.id)},
        content_type="application/json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["error"]["code"] == "ITEM_INACTIVE"
