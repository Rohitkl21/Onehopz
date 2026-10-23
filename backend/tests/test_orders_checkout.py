"""Comprehensive automated tests for Orders, Checkout, and Durable Inventory Reservations."""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.catalog.models import CatalogItem
from apps.holds.models import Hold, HoldStatus
from apps.holds.services import acquire_hold
from apps.identity.models import User, UserRole
from apps.identity.services import AuthService
from apps.inventory.models import (
    CinemaScreen,
    CinemaSeatAllocation,
    CinemaShowtime,
    EventTier,
    HotelInventoryCalendar,
    HotelRoomType,
    RestaurantTableLayout,
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
from apps.orders.models import (
    Order,
    OrderReservation,
    OrderReservationStatus,
    OrderStatus,
)
from apps.orders.services import sweep_expired_order_reservations


@pytest.fixture
def customer(db: None) -> User:
    return User.objects.create_user(
        email="buyer1@example.com",
        phone_number="+919876543210",
        password="Password#2026",
        first_name="Buyer",
        last_name="One",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def other_customer(db: None) -> User:
    return User.objects.create_user(
        email="buyer2@example.com",
        phone_number="+919876543211",
        password="Password#2026",
        first_name="Buyer",
        last_name="Two",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def merchant_owner(db: None) -> User:
    return User.objects.create_user(
        email="merchant_admin@example.com",
        phone_number="+919876543212",
        password="Password#2026",
        first_name="Merchant",
        last_name="Owner",
        role=UserRole.MERCHANT_ADMIN,
    )


@pytest.fixture
def merchant_and_outlet(merchant_owner: User) -> tuple[Merchant, Outlet]:
    merchant = Merchant.objects.create(
        business_name="CineStar Multiplexes",
        legal_entity_name="CineStar Entertainment Private Limited",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    outlet = Outlet.objects.create(
        merchant=merchant,
        name="CineStar Orion Mall",
        category=OutletCategory.CINEMA,
        address_line_1="Dr Rajkumar Road, Rajajinagar",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560055",
    )
    return merchant, outlet


@pytest.fixture
def cinema_catalog_item(merchant_and_outlet: tuple[Merchant, Outlet]) -> CatalogItem:
    merchant, outlet = merchant_and_outlet
    return CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.CINEMA,
        title="Oppenheimer: The IMAX Experience",
        base_price=Decimal("400.00"),
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
        name="Screen 1 (IMAX Laser)",
        total_capacity=150,
    )
    show_start = timezone.now() + timedelta(days=1, hours=3)
    return CinemaShowtime.objects.create(
        catalog_item=cinema_catalog_item,
        screen=screen,
        movie_title=cinema_catalog_item.title,
        start_time=show_start,
        end_time=show_start + timedelta(hours=3),
    )


@pytest.fixture
def active_cinema_hold(
    customer: User, cinema_catalog_item: CatalogItem, cinema_showtime: CinemaShowtime
) -> Hold:
    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=cinema_catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(cinema_showtime.id),
            "seats": [
                {"row": "E", "number": 10},
                {"row": "E", "number": 11},
            ],
        },
        quantity=2,
        idempotency_key=str(uuid.uuid4()),
    )
    return hold


@pytest.mark.django_db
def test_checkout_valid_active_hold_creates_order_and_reservation(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    idemp_key = str(uuid.uuid4())
    payload = {
        "hold_id": str(active_cinema_hold.id),
        "customer_contact": {
            "name": "Arjun Mehta",
            "email": "arjun@example.com",
            "phone": "+919876543210",
        },
    }

    response = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=idemp_key,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()["data"]

    assert data["status"] == OrderStatus.PENDING_PAYMENT
    assert data["category"] == OutletCategory.CINEMA
    assert Decimal(data["gross_amount"]) == Decimal("800.00")
    assert Decimal(data["net_payable_amount"]) == Decimal("800.00")
    assert Decimal(data["discount_amount"]) == Decimal("0.00")
    assert len(data["items"]) == 2

    # Assert source hold transitioned to CONVERTED_TO_ORDER
    active_cinema_hold.refresh_from_db()
    assert active_cinema_hold.status == HoldStatus.CONVERTED_TO_ORDER

    # Assert durable OrderReservation created
    order = Order.objects.get(id=data["id"])
    assert hasattr(order, "reservation")
    assert order.reservation.status == OrderReservationStatus.ACTIVE
    assert order.reservation.hold_id == active_cinema_hold.id
    assert order.reservation.locked_units == ["E-10", "E-11"]


@pytest.mark.django_db
def test_checkout_missing_idempotency_key_fails(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}

    response = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.django_db
def test_checkout_idempotent_retry_returns_same_order(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    idemp_key = str(uuid.uuid4())
    payload = {
        "hold_id": str(active_cinema_hold.id),
        "customer_contact": {"name": "Arjun Mehta"},
    }

    # First request
    res1 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=idemp_key,
    )
    assert res1.status_code == status.HTTP_201_CREATED
    order_id = res1.json()["data"]["id"]

    # Second identical request
    res2 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=idemp_key,
    )
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["data"]["id"] == order_id
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_checkout_idempotency_conflict_with_different_payload(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    idemp_key = str(uuid.uuid4())
    payload1 = {
        "hold_id": str(active_cinema_hold.id),
        "customer_contact": {"name": "First Name"},
    }
    payload2 = {
        "hold_id": str(active_cinema_hold.id),
        "customer_contact": {"name": "Mismatched Name"},
    }

    res1 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload1),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=idemp_key,
    )
    assert res1.status_code == status.HTTP_201_CREATED

    res2 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload2),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=idemp_key,
    )
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert res2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.django_db
def test_checkout_hold_owned_by_another_customer_rejected(
    customer: User, other_customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    # Log in as other_customer
    token = AuthService.create_access_token(other_customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}

    response = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "HOLD_NOT_OWNED"


@pytest.mark.django_db
def test_checkout_already_converted_hold_rejected(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}

    # Convert hold to order
    res1 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res1.status_code == status.HTTP_201_CREATED

    # Attempt to convert again with a new idempotency key
    res2 = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert res2.json()["error"]["code"] == "HOLD_ALREADY_CONVERTED"


@pytest.mark.django_db
def test_checkout_expired_hold_rejected_and_inventory_reclaimed(
    customer: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    # Advance hold into expired state (satisfying chk_hold_expires_after_held)
    past_held = timezone.now() - timedelta(minutes=20)
    past_time = timezone.now() - timedelta(minutes=5)
    Hold.objects.filter(id=active_cinema_hold.id).update(held_at=past_held, expires_at=past_time)

    payload = {"hold_id": str(active_cinema_hold.id)}

    response = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "HOLD_EXPIRED"

    # Assert hold is now EXPIRED and allocations freed
    active_cinema_hold.refresh_from_db()
    assert active_cinema_hold.status == HoldStatus.EXPIRED
    allocs = CinemaSeatAllocation.objects.filter(current_hold=active_cinema_hold)
    assert not allocs.exists()


@pytest.mark.django_db
def test_converted_hold_protects_inventory_beyond_hold_ttl(
    customer: User,
    other_customer: User,
    cinema_catalog_item: CatalogItem,
    cinema_showtime: CinemaShowtime,
    active_cinema_hold: Hold,
) -> None:
    """
    Critical Invariant: When Hold A is converted to an Order, its inventory
    remains protected even after the initial hold TTL (10 minutes) expires,
    preventing Customer B from stealing the seat.
    """
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}
    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED

    # Advance time past hold.expires_at (satisfying chk_hold_expires_after_held)
    past_held = timezone.now() - timedelta(minutes=20)
    past_hold_time = timezone.now() - timedelta(minutes=2)
    Hold.objects.filter(id=active_cinema_hold.id).update(held_at=past_held, expires_at=past_hold_time)

    # Customer B now attempts to acquire the exact same seat
    from apps.holds.exceptions import InventoryAlreadyLockedError

    with pytest.raises(InventoryAlreadyLockedError):
        acquire_hold(
            customer=other_customer,
            catalog_item=cinema_catalog_item,
            category=OutletCategory.CINEMA,
            selection_parameters={
                "showtime_id": str(cinema_showtime.id),
                "seats": [{"row": "E", "number": 10}],
            },
            quantity=1,
            idempotency_key=str(uuid.uuid4()),
        )


@pytest.mark.django_db
def test_sweep_expired_order_reservations_reclaims_inventory(
    customer: User,
    other_customer: User,
    cinema_catalog_item: CatalogItem,
    cinema_showtime: CinemaShowtime,
    active_cinema_hold: Hold,
) -> None:
    """
    Verify that when an order's payment deadline expires, the sweep service
    atomically cancels the order and reclaims the seats.
    """
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}
    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    order_id = res.json()["data"]["id"]

    # Advance payment deadline into the past
    past_deadline = timezone.now() - timedelta(minutes=1)
    Order.objects.filter(id=order_id).update(payment_deadline=past_deadline)
    OrderReservation.objects.filter(order_id=order_id).update(payment_deadline=past_deadline)

    # Run sweep
    swept = sweep_expired_order_reservations(batch_size=10)
    assert swept == 1

    # Order should now be CANCELLED_PAYMENT_TIMEOUT
    order = Order.objects.get(id=order_id)
    assert order.status == OrderStatus.CANCELLED_PAYMENT_TIMEOUT
    assert order.reservation.status == OrderReservationStatus.EXPIRED

    # Customer B can now acquire the seat!
    new_hold, created = acquire_hold(
        customer=other_customer,
        catalog_item=cinema_catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "E", "number": 10}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )
    assert created is True
    assert new_hold.status == HoldStatus.ACTIVE


@pytest.mark.django_db
def test_checkout_snapshots_authoritative_pricing_and_discount(
    customer: User,
    cinema_catalog_item: CatalogItem,
    cinema_showtime: CinemaShowtime,
    merchant_and_outlet: tuple[Merchant, Outlet],
) -> None:
    merchant, outlet = merchant_and_outlet
    # Attach an active 50% discount offer
    offer = OfferSpecification.objects.create(
        merchant=merchant,
        outlet=outlet,
        catalog_item=cinema_catalog_item,
        category=OutletCategory.CINEMA,
        title="50% Off Blockbuster",
        offer_type=OfferType.PERCENTAGE,
        discount_value=Decimal("50.00"),
        floor_price=Decimal("150.00"),
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=2),
        is_active=True,
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=cinema_catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(cinema_showtime.id),
            "seats": [{"row": "A", "number": 1}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
        offer=offer,
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(hold.id)}
    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()["data"]

    assert Decimal(data["gross_amount"]) == Decimal("400.00")
    assert Decimal(data["discount_amount"]) == Decimal("200.00")
    assert Decimal(data["net_payable_amount"]) == Decimal("200.00")


@pytest.mark.django_db
def test_order_detail_view_permissions_and_scoping(
    customer: User, other_customer: User, merchant_owner: User, active_cinema_hold: Hold
) -> None:
    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    payload = {"hold_id": str(active_cinema_hold.id)}
    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    order_id = res.json()["data"]["id"]

    # 1. Owner customer can access order detail
    res_owner = client.get(f"/api/v1/orders/{order_id}")
    assert res_owner.status_code == status.HTTP_200_OK
    assert res_owner.json()["data"]["id"] == order_id

    # 2. Unrelated customer is denied access
    client_other = Client()
    token_other = AuthService.create_access_token(other_customer)
    client_other.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token_other}"
    res_other = client_other.get(f"/api/v1/orders/{order_id}")
    assert res_other.status_code == status.HTTP_403_FORBIDDEN

    # 3. Merchant owner can access order detail
    client_merchant = Client()
    token_merchant = AuthService.create_access_token(merchant_owner)
    client_merchant.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token_merchant}"
    res_merchant = client_merchant.get(f"/api/v1/orders/{order_id}")
    assert res_merchant.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_checkout_surplus_food_batch(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SURPLUS_FOOD,
        title="Baker's Surplus Pastry Box",
        base_price=Decimal("150.00"),
        currency="INR",
        is_active=True,
    )
    batch = SurplusBatch.objects.create(
        catalog_item=item,
        batch_title="Evening Box 1",
        total_quantity=10,
        pickup_window_start=timezone.now() + timedelta(hours=1),
        pickup_window_end=timezone.now() + timedelta(hours=3),
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.SURPLUS_FOOD,
        selection_parameters={"batch_id": str(batch.id)},
        quantity=2,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["data"]["category"] == OutletCategory.SURPLUS_FOOD
    assert Decimal(res.json()["data"]["net_payable_amount"]) == Decimal("300.00")


@pytest.mark.django_db
def test_checkout_event_ticket_tier(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.EVENT,
        title="Indie Rock Concert Pass",
        base_price=Decimal("999.00"),
        currency="INR",
        is_active=True,
    )
    tier = EventTier.objects.create(
        catalog_item=item,
        tier_name="General Admission",
        total_allocation=50,
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.EVENT,
        selection_parameters={"tier_id": str(tier.id)},
        quantity=3,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert Decimal(res.json()["data"]["net_payable_amount"]) == Decimal("2997.00")


@pytest.mark.django_db
def test_checkout_hotel_calendar(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.HOTEL,
        title="Deluxe Ocean Suite",
        base_price=Decimal("3500.00"),
        currency="INR",
        is_active=True,
    )
    room_type = HotelRoomType.objects.create(
        catalog_item=item,
        name="Deluxe Ocean Suite",
        total_rooms_in_inventory=5,
    )
    d_in = date.today() + timedelta(days=5)
    d_out = date.today() + timedelta(days=7)
    HotelInventoryCalendar.objects.create(
        room_type=room_type, stay_date=d_in, total_available=5, nightly_base_rate=Decimal("3500.00")
    )
    HotelInventoryCalendar.objects.create(
        room_type=room_type, stay_date=d_in + timedelta(days=1), total_available=5, nightly_base_rate=Decimal("3500.00")
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.HOTEL,
        selection_parameters={
            "room_type_id": str(room_type.id),
            "check_in_date": d_in.isoformat(),
            "check_out_date": d_out.isoformat(),
            "rooms_count": 1,
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["data"]["category"] == OutletCategory.HOTEL


@pytest.mark.django_db
def test_checkout_travel_simulated(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.TRAVEL,
        title="Express Intercity Bus",
        base_price=Decimal("750.00"),
        currency="INR",
        is_active=True,
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.TRAVEL,
        selection_parameters={
            "route_code": "BLR-HYD-01",
            "seat_identifier": "12B",
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["data"]["category"] == OutletCategory.TRAVEL


@pytest.mark.django_db
def test_checkout_restaurant_table(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    outlet.category = OutletCategory.RESTAURANT
    outlet.save(update_fields=["category"])

    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.RESTAURANT,
        title="Fine Dining 4-Course Dinner",
        base_price=Decimal("1200.00"),
        currency="INR",
        is_active=True,
    )
    table = RestaurantTableLayout.objects.create(
        outlet=outlet,
        table_number="T-04",
        min_covers=2,
        max_covers=4,
    )
    slot_time = timezone.now() + timedelta(days=1, hours=2)

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.RESTAURANT,
        selection_parameters={
            "table_id": str(table.id),
            "slot_start_time": slot_time.isoformat(),
        },
        quantity=2,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["data"]["category"] == OutletCategory.RESTAURANT
    assert Decimal(res.json()["data"]["net_payable_amount"]) == Decimal("2400.00")


@pytest.mark.django_db
def test_checkout_salon_slot(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    outlet.category = OutletCategory.SALON
    outlet.save(update_fields=["category"])

    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SALON,
        title="Luxury Haircut & Beard Grooming",
        base_price=Decimal("600.00"),
        currency="INR",
        is_active=True,
    )
    st = timezone.now() + timedelta(days=1, hours=4)
    et = st + timedelta(hours=1)

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.SALON,
        selection_parameters={
            "stylist_name": "Vikram",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["data"]["category"] == OutletCategory.SALON


@pytest.mark.django_db
def test_checkout_past_cutoff_rejected(
    customer: User, merchant_and_outlet: tuple[Merchant, Outlet]
) -> None:
    merchant, outlet = merchant_and_outlet
    item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.CINEMA,
        title="Midnight Premiere",
        base_price=Decimal("350.00"),
        currency="INR",
        is_active=True,
    )
    screen = CinemaScreen.objects.create(
        outlet=outlet,
        name="Screen 3",
        total_capacity=100,
    )
    # Showtime starts in 5 minutes (less than the 10-minute cinema cutoff buffer)
    near_start = timezone.now() + timedelta(minutes=5)
    showtime = CinemaShowtime.objects.create(
        catalog_item=item,
        screen=screen,
        movie_title="Midnight Premiere",
        start_time=near_start,
        end_time=near_start + timedelta(hours=2),
    )

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(showtime.id),
            "seats": [{"row": "C", "number": 5}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    client = Client()
    token = AuthService.create_access_token(customer)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    res = client.post(
        "/api/v1/orders/checkout",
        data=json.dumps({"hold_id": str(hold.id)}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["error"]["code"] == "INVENTORY_CUTOFF_EXCEEDED"

