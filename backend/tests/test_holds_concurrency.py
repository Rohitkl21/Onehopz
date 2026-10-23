"""High-concurrency multithreaded race condition tests against PostgreSQL ACID engine."""

import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.models import CatalogItem
from apps.holds.exceptions import (
    HoldDomainError,
    InsufficientInventoryError,
    InventoryAlreadyLockedError,
)
from apps.holds.models import Hold
from apps.holds.services import (
    acquire_hold,
    release_hold,
    sweep_expired_holds,
)
from apps.identity.models import User, UserRole
from apps.inventory.models import (
    CinemaScreen,
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


def _close_thread_db_connections() -> None:
    """Explicitly reset thread-local database connections for genuinely independent PostgreSQL sessions."""
    for _conn in connection.settings_dict.values():
        connection.close()


@pytest.fixture
def setup_concurrency_fixtures(db: None) -> dict[str, Any]:
    """Base setup for merchant, outlet, and users."""
    suffix = uuid.uuid4().hex[:6]
    merchant_owner = User.objects.create_user(
        email=f"concurrent_merchant_{suffix}@example.com",
        phone_number=f"+9188{uuid.uuid4().int % 100000000:08d}",
        password="Password#2026",
        role=UserRole.MERCHANT_ADMIN,
    )
    merchant = Merchant.objects.create(
        business_name="Grand Multiplex Corp",
        legal_entity_name="Grand Multiplex Corp Ltd",
        primary_contact=merchant_owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=merchant_owner,
        role=MerchantMembershipRole.OWNER,
    )
    outlet = Outlet.objects.create(
        merchant=merchant,
        name="Grand PVR Residency",
        category=OutletCategory.CINEMA,
        address_line_1="MG Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
    )
    customers = [
        User.objects.create_user(
            email=f"concurrent_cust_{suffix}_{i}@example.com",
            phone_number=f"+9177{uuid.uuid4().int % 100000000:08d}",
            password="Password#2026",
            role=UserRole.CUSTOMER,
        )
        for i in range(10)
    ]
    return {
        "merchant": merchant,
        "outlet": outlet,
        "customers": customers,
    }


@pytest.mark.django_db(transaction=True)
def test_concurrent_exclusive_cinema_seat_claim(setup_concurrency_fixtures: dict[str, Any]) -> None:
    """
    Concurrency Proof 1:
    Two concurrent threads attempt to hold the identical cinema seat.
    Strictly exactly one thread must succeed, and the other must be rejected with INVENTORY_ALREADY_LOCKED.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    cust_a = setup_concurrency_fixtures["customers"][0]
    cust_b = setup_concurrency_fixtures["customers"][1]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.CINEMA,
        title="Avatar: Fire and Ash",
        base_price=Decimal("500.00"),
        is_active=True,
    )
    screen = CinemaScreen.objects.create(outlet=outlet, name="Screen 1", total_capacity=50)
    showtime = CinemaShowtime.objects.create(
        screen=screen,
        catalog_item=catalog_item,
        movie_title="Avatar: Fire and Ash",
        start_time=timezone.now() + timedelta(days=1),
        end_time=timezone.now() + timedelta(days=1, hours=3),
    )

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def attempt_claim(customer: User, key: str) -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            hold, created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=OutletCategory.CINEMA,
                selection_parameters={
                    "showtime_id": str(showtime.id),
                    "seats": [{"row": "C", "number": 7}],
                },
                quantity=1,
                idempotency_key=key,
            )
            with lock:
                results.append({"success": True, "customer": customer.email, "hold_id": hold.id})
        except Exception as exc:
            with lock:
                results.append({"success": False, "customer": customer.email, "error": exc})
        finally:
            _close_thread_db_connections()

    t1 = threading.Thread(target=attempt_claim, args=(cust_a, str(uuid.uuid4())))
    t2 = threading.Thread(target=attempt_claim, args=(cust_b, str(uuid.uuid4())))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"
    assert isinstance(failures[0]["error"], InventoryAlreadyLockedError)


@pytest.mark.django_db(transaction=True)
def test_concurrent_surplus_food_quota_race(setup_concurrency_fixtures: dict[str, Any]) -> None:
    """
    Concurrency Proof 2:
    Batch has total_quantity = 5.
    5 threads simultaneously attempt to claim 2 units each (total demand = 10).
    Under atomic concurrency, held_quantity must never exceed 5.
    At most 2 threads can succeed (2 * 2 = 4 units held). 3 threads must be rejected.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    customers = setup_concurrency_fixtures["customers"][:5]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SURPLUS_FOOD,
        title="Artisan Bread Bag",
        base_price=Decimal("120.00"),
        is_active=True,
    )
    now = timezone.now()
    batch = SurplusBatch.objects.create(
        catalog_item=catalog_item,
        batch_title="Surplus Breads",
        pickup_window_start=now + timedelta(hours=1),
        pickup_window_end=now + timedelta(hours=2),
        total_quantity=5,
        held_quantity=0,
    )

    barrier = threading.Barrier(5)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def claim_surplus(customer: User) -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            hold, created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=OutletCategory.SURPLUS_FOOD,
                selection_parameters={"batch_id": str(batch.id)},
                quantity=2,
                idempotency_key=str(uuid.uuid4()),
            )
            with lock:
                results.append({"success": True, "hold_id": hold.id})
        except Exception as exc:
            with lock:
                results.append({"success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    threads = [threading.Thread(target=claim_surplus, args=(c,)) for c in customers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    batch.refresh_from_db()
    # At most 2 threads succeed (4 held units); cannot hold 6!
    assert len(successes) == 2
    assert len(failures) == 3
    assert batch.held_quantity <= batch.total_quantity
    assert batch.held_quantity == 4
    for f in failures:
        assert isinstance(f["error"], InsufficientInventoryError)


@pytest.mark.django_db(transaction=True)
def test_concurrent_event_ticket_quota_race(setup_concurrency_fixtures: dict[str, Any]) -> None:
    """
    Concurrency Proof 3:
    Event tier has 3 total allocations.
    6 concurrent threads attempt to claim 1 ticket each.
    Exactly 3 must succeed and exactly 3 must be rejected with InsufficientInventoryError.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    customers = setup_concurrency_fixtures["customers"][:6]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.EVENT,
        title="Jazz Under The Stars",
        base_price=Decimal("800.00"),
        is_active=True,
    )
    tier = EventTier.objects.create(
        catalog_item=catalog_item,
        tier_name="General Admission",
        total_allocation=3,
        held_tickets=0,
    )

    barrier = threading.Barrier(6)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def claim_ticket(customer: User) -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            hold, created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=OutletCategory.EVENT,
                selection_parameters={"tier_id": str(tier.id)},
                quantity=1,
                idempotency_key=str(uuid.uuid4()),
            )
            with lock:
                results.append({"success": True, "hold_id": hold.id})
        except Exception as exc:
            with lock:
                results.append({"success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    threads = [threading.Thread(target=claim_ticket, args=(c,)) for c in customers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    tier.refresh_from_db()
    assert len(successes) == 3
    assert len(failures) == 3
    assert tier.held_tickets == 3
    for f in failures:
        assert isinstance(f["error"], InsufficientInventoryError)


@pytest.mark.django_db(transaction=True)
def test_concurrent_hotel_multi_night_locking(setup_concurrency_fixtures: dict[str, Any]) -> None:
    """
    Concurrency Proof 4:
    Room type has 1 room available on 2026-12-01 and 2026-12-02.
    Two concurrent threads attempt to hold a 2-night stay overlapping both dates.
    Exactly 1 thread succeeds, 1 fails without deadlock due to deterministic date sorting.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    cust_a = setup_concurrency_fixtures["customers"][0]
    cust_b = setup_concurrency_fixtures["customers"][1]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.HOTEL,
        title="Presidency Suite",
        base_price=Decimal("12000.00"),
        is_active=True,
    )
    room_type = HotelRoomType.objects.create(
        catalog_item=catalog_item,
        outlet=outlet,
        name="Penthouse Suite",
        total_rooms_in_inventory=1,
    )
    d1 = date(2026, 12, 1)
    d2 = date(2026, 12, 2)
    HotelInventoryCalendar.objects.create(
        room_type=room_type, stay_date=d1, total_available=1, held_count=0, booked_count=0
    )
    HotelInventoryCalendar.objects.create(
        room_type=room_type, stay_date=d2, total_available=1, held_count=0, booked_count=0
    )

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def attempt_hotel_hold(customer: User) -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            hold, created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=OutletCategory.HOTEL,
                selection_parameters={
                    "room_type_id": str(room_type.id),
                    "check_in_date": "2026-12-01",
                    "check_out_date": "2026-12-03",
                    "rooms_count": 1,
                },
                quantity=1,
                idempotency_key=str(uuid.uuid4()),
            )
            with lock:
                results.append({"success": True, "hold_id": hold.id})
        except Exception as exc:
            with lock:
                results.append({"success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    t1 = threading.Thread(target=attempt_hotel_hold, args=(cust_a,))
    t2 = threading.Thread(target=attempt_hotel_hold, args=(cust_b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0]["error"], InsufficientInventoryError)


@pytest.mark.django_db(transaction=True)
def test_concurrent_idempotent_duplicate_requests(
    setup_concurrency_fixtures: dict[str, Any],
) -> None:
    """
    Concurrency Proof 5:
    Same customer fires 5 simultaneous requests with the SAME idempotency key.
    Zero duplicate claims created; all successful responses reference the exact same hold_id.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    customer = setup_concurrency_fixtures["customers"][0]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.EVENT,
        title="Standup Comedy Special",
        base_price=Decimal("499.00"),
        is_active=True,
    )
    tier = EventTier.objects.create(
        catalog_item=catalog_item,
        tier_name="Front Row",
        total_allocation=10,
        held_tickets=0,
    )
    idempotency_key = str(uuid.uuid4())

    barrier = threading.Barrier(4)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def fire_duplicate() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            hold, created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=OutletCategory.EVENT,
                selection_parameters={"tier_id": str(tier.id)},
                quantity=1,
                idempotency_key=idempotency_key,
            )
            with lock:
                results.append({"success": True, "hold_id": hold.id})
        except Exception as exc:
            with lock:
                results.append({"success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    threads = [threading.Thread(target=fire_duplicate) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All successes must share the exact same hold_id
    successes = [r for r in results if r["success"]]
    assert len(successes) >= 1
    unique_hold_ids = {s["hold_id"] for s in successes}
    assert len(unique_hold_ids) == 1

    # Total held tickets in tier must be exactly 1, NOT 4!
    tier.refresh_from_db()
    assert tier.held_tickets == 1


@pytest.mark.django_db(transaction=True)
def test_race_between_release_and_expiration(setup_concurrency_fixtures: dict[str, Any]) -> None:
    """
    Concurrency Proof 6:
    Release operation races against sweep_expired_holds.
    Under no circumstances is inventory double-released or negative held_quantity produced.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    customer = setup_concurrency_fixtures["customers"][0]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SURPLUS_FOOD,
        title="Croissant Box",
        base_price=Decimal("200.00"),
        is_active=True,
    )
    now = timezone.now()
    batch = SurplusBatch.objects.create(
        catalog_item=catalog_item,
        batch_title="Morning Croissants",
        pickup_window_start=now,
        pickup_window_end=now + timedelta(hours=2),
        total_quantity=10,
        held_quantity=0,
    )

    hold, created = acquire_hold(
        customer=customer,
        catalog_item=catalog_item,
        category=OutletCategory.SURPLUS_FOOD,
        selection_parameters={"batch_id": str(batch.id)},
        quantity=3,
        idempotency_key=str(uuid.uuid4()),
    )
    batch.refresh_from_db()
    assert batch.held_quantity == 3

    # Force expiration timestamp
    Hold.objects.filter(id=hold.id).update(
        held_at=timezone.now() - timedelta(minutes=20),
        expires_at=timezone.now() - timedelta(minutes=5),
    )

    barrier = threading.Barrier(2)

    def do_user_release() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            release_hold(hold_id=hold.id, customer=customer)
        except Exception:
            pass
        finally:
            _close_thread_db_connections()

    def do_sweep() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            sweep_expired_holds()
        except Exception:
            pass
        finally:
            _close_thread_db_connections()

    t1 = threading.Thread(target=do_user_release)
    t2 = threading.Thread(target=do_sweep)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    batch.refresh_from_db()
    # Quantity must be exactly 0, never negative or double-decremented!
    assert batch.held_quantity == 0


@pytest.mark.django_db(transaction=True)
def test_forced_exception_leaves_zero_orphaned_inventory(
    setup_concurrency_fixtures: dict[str, Any],
) -> None:
    """
    Concurrency Proof 7:
    If an unexpected error occurs during hold acquisition,
    the entire PostgreSQL transaction aborts, leaving no orphaned hold or allocated inventory.
    """
    merchant = setup_concurrency_fixtures["merchant"]
    outlet = setup_concurrency_fixtures["outlet"]
    customer = setup_concurrency_fixtures["customers"][0]

    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.SURPLUS_FOOD,
        title="Gourmet Cheese",
        base_price=Decimal("300.00"),
        is_active=True,
    )
    now = timezone.now()
    batch = SurplusBatch.objects.create(
        catalog_item=catalog_item,
        batch_title="Artisan Cheeses",
        pickup_window_start=now,
        pickup_window_end=now + timedelta(hours=2),
        total_quantity=5,
        held_quantity=0,
    )

    initial_hold_count = Hold.objects.count()

    with pytest.raises(HoldDomainError), transaction.atomic():
        # Acquire hold with invalid selection parameter format designed to fail
        acquire_hold(
            customer=customer,
            catalog_item=catalog_item,
            category=OutletCategory.SURPLUS_FOOD,
            selection_parameters={"batch_id": "00000000-0000-0000-0000-000000000000"},
            quantity=2,
            idempotency_key=str(uuid.uuid4()),
        )

    batch.refresh_from_db()
    assert batch.held_quantity == 0
    assert Hold.objects.count() == initial_hold_count
