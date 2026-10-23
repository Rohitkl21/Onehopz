"""Automated tests for Authoritative Hold Engine lifecycle, API contracts, and idempotency."""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import CatalogItem
from apps.holds.models import Hold
from apps.holds.services import sweep_expired_holds
from apps.identity.models import User, UserRole
from apps.identity.services import AuthService
from apps.inventory.models import (
    CinemaScreen,
    CinemaSeatAllocation,
    CinemaShowtime,
    EventTier,
    HotelInventoryCalendar,
    HotelRoomType,
    SurplusBatch,
)
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletCategory,
)
from apps.offers.models import OfferSpecification, OfferType


@pytest.fixture
def customer(db: None) -> User:
    return User.objects.create_user(
        email="customer1@example.com",
        phone_number="+919876543210",
        password="Password#2026",
        first_name="Customer",
        last_name="One",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def other_customer(db: None) -> User:
    return User.objects.create_user(
        email="customer2@example.com",
        phone_number="+919876543211",
        password="Password#2026",
        first_name="Customer",
        last_name="Two",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="merchant@example.com",
        phone_number="+919876543212",
        password="Password#2026",
        first_name="Merchant",
        last_name="Boss",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def merchant_and_outlet(merchant_owner: User) -> tuple[Merchant, Outlet]:
    merchant = Merchant.objects.create(
        business_name="PVR Inox Cinemas",
        legal_entity_name="PVR Inox Limited",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    outlet = Outlet.objects.create(
        merchant=merchant,
        name="PVR Phoenix Marketcity",
        category=OutletCategory.CINEMA,
        address_line_1="Whitefield Main Rd",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560048",
    )
    return merchant, outlet


@pytest.fixture
def cinema_catalog_item(merchant_and_outlet: tuple[Merchant, Outlet]) -> CatalogItem:
    merchant, outlet = merchant_and_outlet
    return CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.CINEMA,
        title="Dune: Part Two (IMAX)",
        base_price=Decimal("450.00"),
        currency="INR",
        is_active=True,
    )


@pytest.fixture
def cinema_showtime(
    cinema_catalog_item: CatalogItem, merchant_and_outlet: tuple[Merchant, Outlet]
) -> CinemaShowtime:
    _, outlet = merchant_and_outlet
    screen = CinemaScreen.objects.create(
        outlet=outlet,
        name="Screen 1 (IMAX)",
        total_capacity=100,
    )
    now = timezone.now()
    return CinemaShowtime.objects.create(
        screen=screen,
        catalog_item=cinema_catalog_item,
        movie_title="Dune: Part Two",
        movie_duration_minutes=166,
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=5),
    )


@pytest.mark.django_db
def test_acquire_hold_success(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    idempotency_key = str(uuid.uuid4())

    payload = {
        "catalog_item_id": str(cinema_catalog_item.id),
        "category": OutletCategory.CINEMA,
        "selection_parameters": {
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "E", "number": 10}, {"row": "E", "number": 11}],
        },
        "quantity": 2,
    }

    response = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )

    assert response.status_code == status.HTTP_201_CREATED
    res_data = response.json()
    assert res_data["success"] is True
    data = res_data["data"]
    assert data["status"] == "ACTIVE"
    assert data["category"] == OutletCategory.CINEMA
    assert data["ttl_remaining_seconds"] > 0
    assert "E-10" in data["locked_units"]
    assert "E-11" in data["locked_units"]
    assert Decimal(data["total_price"]) == Decimal("900.00")
    assert data["currency"] == "INR"


@pytest.mark.django_db
def test_acquire_hold_missing_idempotency_key_fails(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)

    payload = {
        "catalog_item_id": str(cinema_catalog_item.id),
        "category": OutletCategory.CINEMA,
        "selection_parameters": {
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "E", "number": 10}],
        },
        "quantity": 1,
    }

    response = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.django_db
def test_idempotent_retry_returns_original_hold(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    idempotency_key = str(uuid.uuid4())

    payload = {
        "catalog_item_id": str(cinema_catalog_item.id),
        "category": OutletCategory.CINEMA,
        "selection_parameters": {
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "F", "number": 1}],
        },
        "quantity": 1,
    }

    # First call -> 201 Created
    res1 = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    assert res1.status_code == status.HTTP_201_CREATED
    hold_id_1 = res1.json()["data"]["hold_id"]

    # Identical retry -> 200 OK with same hold_id
    res2 = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["data"]["hold_id"] == hold_id_1


@pytest.mark.django_db
def test_idempotency_conflict_with_different_payload(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    idempotency_key = str(uuid.uuid4())

    payload1 = {
        "catalog_item_id": str(cinema_catalog_item.id),
        "category": OutletCategory.CINEMA,
        "selection_parameters": {
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "G", "number": 1}],
        },
        "quantity": 1,
    }

    res1 = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload1),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    assert res1.status_code == status.HTTP_201_CREATED

    # Different payload with identical idempotency key -> 409 Conflict
    payload2 = {
        "catalog_item_id": str(cinema_catalog_item.id),
        "category": OutletCategory.CINEMA,
        "selection_parameters": {
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "G", "number": 2}],
        },
        "quantity": 1,
    }
    res2 = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(payload2),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert res2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.django_db
def test_hold_detail_and_tenant_isolation(
    customer: User,
    other_customer: User,
    cinema_catalog_item: CatalogItem,
    cinema_showtime: CinemaShowtime,
) -> None:
    client = Client()
    cust1_token = AuthService.create_access_token(customer)
    cust2_token = AuthService.create_access_token(other_customer)

    # Customer 1 acquires hold
    res_create = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(cinema_catalog_item.id),
                "category": OutletCategory.CINEMA,
                "selection_parameters": {
                    "showtime_id": str(cinema_showtime.id),
                    "seats": [{"row": "H", "number": 1}],
                },
                "quantity": 1,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {cust1_token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    hold_id = res_create.json()["data"]["hold_id"]

    # Customer 1 can read hold
    res_get_owner = client.get(
        f"/api/v1/holds/{hold_id}/",
        HTTP_AUTHORIZATION=f"Bearer {cust1_token}",
    )
    assert res_get_owner.status_code == status.HTTP_200_OK
    assert res_get_owner.json()["data"]["hold_id"] == hold_id

    # Customer 2 cannot read Customer 1's hold (403 Forbidden)
    res_get_other = client.get(
        f"/api/v1/holds/{hold_id}/",
        HTTP_AUTHORIZATION=f"Bearer {cust2_token}",
    )
    assert res_get_other.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_release_hold_and_idempotent_double_release(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)

    res_create = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(cinema_catalog_item.id),
                "category": OutletCategory.CINEMA,
                "selection_parameters": {
                    "showtime_id": str(cinema_showtime.id),
                    "seats": [{"row": "J", "number": 10}],
                },
                "quantity": 1,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    hold_id = res_create.json()["data"]["hold_id"]

    # Release hold via DELETE
    res_rel1 = client.delete(
        f"/api/v1/holds/{hold_id}/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert res_rel1.status_code == status.HTTP_200_OK
    assert res_rel1.json()["data"]["status"] == "RELEASED_BY_USER"

    # Verify seat was freed
    seat = CinemaSeatAllocation.objects.get(showtime=cinema_showtime, row_code="J", seat_number=10)
    assert seat.status == CinemaSeatAllocation.SeatStatus.AVAILABLE
    assert seat.current_hold is None

    # Idempotent re-release does not error
    res_rel2 = client.post(
        f"/api/v1/holds/{hold_id}/release/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert res_rel2.status_code == status.HTTP_200_OK
    assert res_rel2.json()["data"]["status"] == "RELEASED_BY_USER"


@pytest.mark.django_db
def test_authoritative_hold_expiration_and_seat_reclaim(
    customer: User,
    other_customer: User,
    cinema_catalog_item: CatalogItem,
    cinema_showtime: CinemaShowtime,
) -> None:
    client = Client()
    cust1_token = AuthService.create_access_token(customer)
    cust2_token = AuthService.create_access_token(other_customer)

    res_create = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(cinema_catalog_item.id),
                "category": OutletCategory.CINEMA,
                "selection_parameters": {
                    "showtime_id": str(cinema_showtime.id),
                    "seats": [{"row": "K", "number": 1}],
                },
                "quantity": 1,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {cust1_token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    hold_id = res_create.json()["data"]["hold_id"]

    # Force hold expiration in database (simulating elapsed TTL without background worker)
    Hold.objects.filter(id=hold_id).update(
        held_at=timezone.now() - timedelta(minutes=20),
        expires_at=timezone.now() - timedelta(minutes=10),
    )

    # Customer 1 reads hold -> evaluated authoritatively as EXPIRED
    res_read = client.get(
        f"/api/v1/holds/{hold_id}/",
        HTTP_AUTHORIZATION=f"Bearer {cust1_token}",
    )
    assert res_read.status_code == status.HTTP_200_OK
    assert res_read.json()["data"]["status"] == "EXPIRED"
    assert res_read.json()["data"]["is_expired"] is True
    assert res_read.json()["data"]["ttl_remaining_seconds"] == 0

    # Customer 2 attempts to claim the expired seat -> succeeds and reclaims seat
    res_reclaim = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(cinema_catalog_item.id),
                "category": OutletCategory.CINEMA,
                "selection_parameters": {
                    "showtime_id": str(cinema_showtime.id),
                    "seats": [{"row": "K", "number": 1}],
                },
                "quantity": 1,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {cust2_token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res_reclaim.status_code == status.HTTP_201_CREATED
    assert res_reclaim.json()["data"]["status"] == "ACTIVE"


@pytest.mark.django_db
def test_surplus_food_hold_and_sweep(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    client = Client()
    merchant, outlet = merchant_and_outlet
    token = AuthService.create_access_token(customer)

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SURPLUS_FOOD,
        title="Evening Magic Bag",
        base_price=Decimal("150.00"),
        currency="INR",
        is_active=True,
    )
    now = timezone.now()
    batch = SurplusBatch.objects.create(
        catalog_item=catalog_item,
        batch_title="Bakery Surprise Box",
        pickup_window_start=now + timedelta(hours=1),
        pickup_window_end=now + timedelta(hours=3),
        total_quantity=5,
        held_quantity=0,
    )

    # Hold 2 units
    res = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(catalog_item.id),
                "category": OutletCategory.SURPLUS_FOOD,
                "selection_parameters": {"batch_id": str(batch.id)},
                "quantity": 2,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    batch.refresh_from_db()
    assert batch.held_quantity == 2

    # Expire and run sweep
    hold_id = res.json()["data"]["hold_id"]
    Hold.objects.filter(id=hold_id).update(
        held_at=timezone.now() - timedelta(minutes=20),
        expires_at=timezone.now() - timedelta(minutes=5),
    )
    reclaimed = sweep_expired_holds()
    assert reclaimed >= 1

    batch.refresh_from_db()
    assert batch.held_quantity == 0


@pytest.mark.django_db
def test_event_ticket_hold_quota_enforcement(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    client = Client()
    merchant, outlet = merchant_and_outlet
    token = AuthService.create_access_token(customer)

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.EVENT,
        title="Rock Festival Pass",
        base_price=Decimal("1200.00"),
        currency="INR",
        is_active=True,
    )
    tier = EventTier.objects.create(
        catalog_item=catalog_item,
        tier_name="VIP Pass",
        total_allocation=3,
        held_tickets=0,
    )

    # Attempt to hold 4 tickets when only 3 exist -> 409 Conflict
    res_exceed = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(catalog_item.id),
                "category": OutletCategory.EVENT,
                "selection_parameters": {"tier_id": str(tier.id)},
                "quantity": 4,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res_exceed.status_code == status.HTTP_409_CONFLICT
    assert res_exceed.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

    # Hold 2 tickets -> succeeds
    res_ok = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(catalog_item.id),
                "category": OutletCategory.EVENT,
                "selection_parameters": {"tier_id": str(tier.id)},
                "quantity": 2,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res_ok.status_code == status.HTTP_201_CREATED
    tier.refresh_from_db()
    assert tier.held_tickets == 2


@pytest.mark.django_db
def test_hotel_multi_night_hold_enforcement(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    client = Client()
    merchant, outlet = merchant_and_outlet
    token = AuthService.create_access_token(customer)

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.HOTEL,
        title="Deluxe Ocean Suite",
        base_price=Decimal("4500.00"),
        currency="INR",
        is_active=True,
    )
    room_type = HotelRoomType.objects.create(
        catalog_item=catalog_item,
        outlet=outlet,
        name="Ocean Suite",
        total_rooms_in_inventory=2,
    )

    d1 = date(2026, 11, 1)
    d2 = date(2026, 11, 2)
    HotelInventoryCalendar.objects.create(
        room_type=room_type,
        stay_date=d1,
        total_available=2,
        held_count=0,
        booked_count=0,
        nightly_base_rate=Decimal("4500.00"),
    )
    HotelInventoryCalendar.objects.create(
        room_type=room_type,
        stay_date=d2,
        total_available=2,
        held_count=0,
        booked_count=0,
        nightly_base_rate=Decimal("4500.00"),
    )

    # Hold 1 room for 2 nights
    res = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(catalog_item.id),
                "category": OutletCategory.HOTEL,
                "selection_parameters": {
                    "room_type_id": str(room_type.id),
                    "check_in_date": "2026-11-01",
                    "check_out_date": "2026-11-03",
                    "rooms_count": 1,
                },
                "quantity": 1,
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    cal1 = HotelInventoryCalendar.objects.get(room_type=room_type, stay_date=d1)
    cal2 = HotelInventoryCalendar.objects.get(room_type=room_type, stay_date=d2)
    assert cal1.held_count == 1
    assert cal2.held_count == 1


@pytest.mark.django_db
def test_authoritative_offer_discount_applied_on_hold(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)

    now = timezone.now()
    offer = OfferSpecification.objects.create(
        merchant=cinema_catalog_item.merchant,
        outlet=cinema_catalog_item.outlet,
        catalog_item=cinema_catalog_item,
        category=OutletCategory.CINEMA,
        title="20% Early Bird",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        currency="INR",
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=5),
        is_active=True,
    )

    # Base price: 450.00; with 20% discount: 360.00
    res = client.post(
        "/api/v1/holds/acquire",
        data=json.dumps(
            {
                "catalog_item_id": str(cinema_catalog_item.id),
                "category": OutletCategory.CINEMA,
                "selection_parameters": {
                    "showtime_id": str(cinema_showtime.id),
                    "seats": [{"row": "L", "number": 1}],
                },
                "quantity": 1,
                "offer_id": str(offer.id),
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert Decimal(res.json()["data"]["total_price"]) == Decimal("360.00")
