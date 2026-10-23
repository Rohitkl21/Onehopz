"""Automated test suite for Offers domain and dynamic yield pricing calculations."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import CatalogItem
from apps.identity.models import UserRole
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

User = get_user_model()


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
    """Merchant owner can create a percentage-based offer specification."""
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


@pytest.mark.django_db
def test_create_offer_invalid_percentage_rejected(
    merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """Percentage discount value cannot exceed 100% or be <= 0%."""
    client = Client()
    now = timezone.now()
    base_payload = {
        "merchant": str(merchant_a.id),
        "category": OutletCategory.SURPLUS_FOOD,
        "title": "Invalid Discount",
        "offer_type": OfferType.PERCENTAGE,
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(hours=2)).isoformat(),
    }

    # > 100% discount
    res_high = client.post(
        "/api/v1/offers/",
        data={**base_payload, "discount_value": "125.00"},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert res_high.status_code == status.HTTP_400_BAD_REQUEST
    assert "discount_value" in res_high.json()["error"]["details"]

    # <= 0% discount
    res_zero = client.post(
        "/api/v1/offers/",
        data={**base_payload, "discount_value": "0.00"},
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert res_zero.status_code == status.HTTP_400_BAD_REQUEST
    assert "discount_value" in res_zero.json()["error"]["details"]


@pytest.mark.django_db
def test_create_offer_invalid_dates_rejected(
    merchant_owner: User,
    merchant_a: Merchant,
) -> None:
    """valid_to must be strictly after valid_from."""
    client = Client()
    now = timezone.now()
    payload = {
        "merchant": str(merchant_a.id),
        "title": "Invalid Dates",
        "offer_type": OfferType.PERCENTAGE,
        "discount_value": "20.00",
        "valid_from": now.isoformat(),
        "valid_to": (now - timedelta(hours=1)).isoformat(),  # in past relative to from
    }
    response = client.post(
        "/api/v1/offers/",
        data=payload,
        content_type="application/json",
        **auth_headers(merchant_owner),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "valid_to" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_cross_tenant_offer_creation_blocked(
    competitor_owner: User,
    merchant_a: Merchant,
) -> None:
    """Competitor cannot create offers on another merchant organization."""
    client = Client()
    now = timezone.now()
    payload = {
        "merchant": str(merchant_a.id),
        "title": "Hijacked Offer",
        "offer_type": OfferType.FIXED_AMOUNT,
        "discount_value": "50.00",
        "valid_from": now.isoformat(),
        "valid_to": (now + timedelta(hours=2)).isoformat(),
    }
    response = client.post(
        "/api/v1/offers/",
        data=payload,
        content_type="application/json",
        **auth_headers(competitor_owner),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_pricing_calculation_service_percentage(merchant_a: Merchant) -> None:
    """Test pricing calculation service with percentage discounts and cap."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="30% Off capped at 100",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("30.00"),
        max_discount_amount=Decimal("100.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    # Base price 200: 30% of 200 = 60 (below cap of 100) -> final = 140
    discount, final_price = calculate_discounted_price(Decimal("200.00"), offer)
    assert discount == Decimal("60.00")
    assert final_price == Decimal("140.00")

    # Base price 500: 30% of 500 = 150 (capped at 100) -> final = 400
    discount, final_price = calculate_discounted_price(Decimal("500.00"), offer)
    assert discount == Decimal("100.00")
    assert final_price == Decimal("400.00")


@pytest.mark.django_db
def test_pricing_calculation_service_floor_price(merchant_a: Merchant) -> None:
    """Test pricing calculation service enforces minimum floor price."""
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

    # Base price 200: 50% discount would be 100, bringing price to 100, which is below floor 150.
    # Therefore discount is capped to 50, final price stays at 150.
    discount, final_price = calculate_discounted_price(Decimal("200.00"), offer)
    assert discount == Decimal("50.00")
    assert final_price == Decimal("150.00")


@pytest.mark.django_db
def test_pricing_calculation_service_fixed_amount(merchant_a: Merchant) -> None:
    """Test fixed amount discount calculation and non-negative clamping."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="100 INR Off",
        offer_type=OfferType.FIXED_AMOUNT,
        discount_value=Decimal("100.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    # Base price 350 -> final 250
    discount, final_price = calculate_discounted_price(Decimal("350.00"), offer)
    assert discount == Decimal("100.00")
    assert final_price == Decimal("250.00")

    # Base price 60 with 100 off -> final 0.00 (not -40)
    discount, final_price = calculate_discounted_price(Decimal("60.00"), offer)
    assert discount == Decimal("60.00")
    assert final_price == Decimal("0.00")


@pytest.mark.django_db
def test_pricing_calculation_api_endpoint(merchant_a: Merchant) -> None:
    """Test POST /api/v1/offers/calculate/ endpoint."""
    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=merchant_a,
        title="Flash 25% Off",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("25.00"),
        valid_from=now,
        valid_to=now + timedelta(hours=2),
    )

    client = Client()
    payload = {
        "offer_id": str(offer.id),
        "base_price": "400.00",
    }
    response = client.post(
        "/api/v1/offers/calculate/",
        data=payload,
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert Decimal(data["data"]["base_price"]) == Decimal("400.00")
    assert Decimal(data["data"]["discount_amount"]) == Decimal("100.00")
    assert Decimal(data["data"]["final_price"]) == Decimal("300.00")
    assert Decimal(data["data"]["savings_percentage"]) == Decimal("25.00")
