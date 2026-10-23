"""High-concurrency multithreaded integration tests for Orders and Checkout against PostgreSQL."""

import threading
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from apps.catalog.models import CatalogItem
from apps.holds.models import Hold, HoldStatus
from apps.holds.services import acquire_hold, sweep_expired_holds
from apps.identity.models import User, UserRole
from apps.inventory.models import (
    CinemaScreen,
    CinemaShowtime,
)
from apps.merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletCategory,
)
from apps.orders.models import (
    CheckoutIdempotency,
    Order,
    OrderItem,
    OrderReservation,
    OrderReservationStatus,
)
from apps.orders.services import checkout


def _close_thread_db_connections() -> None:
    """Explicitly reset thread-local database connections for independent PostgreSQL sessions."""
    for _conn in connection.settings_dict.values():
        connection.close()


@pytest.fixture
def concurrency_fixtures(db: None) -> dict[str, Any]:
    owner = User.objects.create_user(
        email="multiplex_admin@example.com",
        phone_number="+919876543299",
        password="Password#2026",
        role=UserRole.MERCHANT_ADMIN,
    )
    merchant = Merchant.objects.create(
        business_name="PVR Inox Concurrency",
        legal_entity_name="PVR Inox Concurrency Ltd",
        primary_contact=owner,
    )
    MerchantMembership.objects.create(
        merchant=merchant,
        user=owner,
        role=MerchantMembershipRole.OWNER,
    )
    outlet = Outlet.objects.create(
        merchant=merchant,
        name="PVR Forum Mall",
        category=OutletCategory.CINEMA,
        address_line_1="Hosur Rd, Koramangala",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560095",
    )
    catalog_item = CatalogItem.objects.create(
        merchant=merchant,
        outlet=outlet,
        category=OutletCategory.CINEMA,
        title="Interstellar IMAX 70mm",
        base_price=Decimal("500.00"),
        currency="INR",
        is_active=True,
    )
    screen = CinemaScreen.objects.create(
        outlet=outlet,
        name="IMAX Laser Screen 1",
        total_capacity=200,
    )
    show_time = timezone.now() + timezone.timedelta(days=2)
    showtime = CinemaShowtime.objects.create(
        catalog_item=catalog_item,
        screen=screen,
        movie_title="Interstellar IMAX 70mm",
        start_time=show_time,
        end_time=show_time + timezone.timedelta(hours=3),
    )
    customer = User.objects.create_user(
        email="concurrency_buyer@example.com",
        phone_number="+919876543201",
        password="Password#2026",
        role=UserRole.CUSTOMER,
    )
    return {
        "customer": customer,
        "catalog_item": catalog_item,
        "showtime": showtime,
    }


@pytest.mark.django_db(transaction=True)
def test_concurrent_idempotent_checkout_requests_single_order(
    concurrency_fixtures: dict[str, Any]
) -> None:
    """
    Test that 5 concurrent threads firing checkout with the exact same
    Idempotency-Key and payload create exactly one Order row on PostgreSQL.
    """
    customer = concurrency_fixtures["customer"]
    catalog_item = concurrency_fixtures["catalog_item"]
    showtime = concurrency_fixtures["showtime"]

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(showtime.id),
            "seats": [{"row": "F", "number": 12}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    thread_count = 5
    barrier = threading.Barrier(thread_count)
    shared_idempotency_key = str(uuid.uuid4())
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def _worker() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            order, is_created = checkout(
                customer=customer,
                hold_id=hold.id,
                customer_contact={"name": "Concurrent Buyer"},
                idempotency_key=shared_idempotency_key,
            )
            with lock:
                results.append({"success": True, "order_id": order.id, "created": is_created})
        except Exception as exc:
            with lock:
                results.append({"success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    threads = [threading.Thread(target=_worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Assert exactly 1 order row in PostgreSQL
    assert Order.objects.count() == 1
    assert OrderReservation.objects.count() == 1
    assert CheckoutIdempotency.objects.count() == 1

    # Assert all successful results received the exact same order_id
    successes = [r for r in results if r["success"]]
    assert len(successes) == thread_count
    created_count = sum(1 for r in successes if r["created"])
    assert created_count == 1
    assert len({r["order_id"] for r in successes}) == 1


@pytest.mark.django_db(transaction=True)
def test_checkout_racing_with_hold_expiration(
    concurrency_fixtures: dict[str, Any]
) -> None:
    """
    Simulate a race where Thread 1 calls checkout on a hold with expiring TTL,
    while Thread 2 runs the expiration sweep simultaneously.
    Asserts exactly one valid outcome: either order is created or hold is expired.
    Zero orphaned allocations or corrupt states.
    """
    customer = concurrency_fixtures["customer"]
    catalog_item = concurrency_fixtures["catalog_item"]
    showtime = concurrency_fixtures["showtime"]

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(showtime.id),
            "seats": [{"row": "G", "number": 15}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    # Set hold expiry to right now (satisfying chk_hold_expires_after_held)
    past_held = timezone.now() - timezone.timedelta(minutes=20)
    past_expires = timezone.now() - timezone.timedelta(milliseconds=50)
    Hold.objects.filter(id=hold.id).update(held_at=past_held, expires_at=past_expires)

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def _checkout_worker() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            order, is_created = checkout(
                customer=customer,
                hold_id=hold.id,
                customer_contact={"name": "Racer"},
                idempotency_key=str(uuid.uuid4()),
            )
            with lock:
                results.append({"action": "checkout", "success": True, "order_id": order.id})
        except Exception as exc:
            with lock:
                results.append({"action": "checkout", "success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    def _sweep_worker() -> None:
        _close_thread_db_connections()
        barrier.wait()
        try:
            reclaimed = sweep_expired_holds(batch_size=10)
            with lock:
                results.append({"action": "sweep", "success": True, "reclaimed": reclaimed})
        except Exception as exc:
            with lock:
                results.append({"action": "sweep", "success": False, "error": exc})
        finally:
            _close_thread_db_connections()

    t1 = threading.Thread(target=_checkout_worker)
    t2 = threading.Thread(target=_sweep_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Invariants verification
    hold.refresh_from_db()
    if Order.objects.count() == 1:
        # Checkout won the race: order exists, reservation active, hold converted
        assert hold.status == HoldStatus.CONVERTED_TO_ORDER
        assert OrderReservation.objects.filter(hold=hold, status=OrderReservationStatus.ACTIVE).exists()
    else:
        # Sweeper won the race: hold is expired, 0 orders
        assert hold.status == HoldStatus.EXPIRED
        assert Order.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_checkout_atomic_rollback_on_failure(
    concurrency_fixtures: dict[str, Any]
) -> None:
    """
    Test that an unexpected exception during checkout rolls back the Order,
    OrderItem, OrderReservation, and Idempotency record, leaving Hold ACTIVE.
    """
    customer = concurrency_fixtures["customer"]
    catalog_item = concurrency_fixtures["catalog_item"]
    showtime = concurrency_fixtures["showtime"]

    hold, _ = acquire_hold(
        customer=customer,
        catalog_item=catalog_item,
        category=OutletCategory.CINEMA,
        selection_parameters={
            "showtime_id": str(showtime.id),
            "seats": [{"row": "H", "number": 20}],
        },
        quantity=1,
        idempotency_key=str(uuid.uuid4()),
    )

    with (
        patch("apps.orders.services.OrderReservation.objects.create", side_effect=RuntimeError("Simulated DB Disk Crash")),
        pytest.raises(RuntimeError, match="Simulated DB Disk Crash"),
    ):
        checkout(
            customer=customer,
            hold_id=hold.id,
            customer_contact={"name": "Failing Customer"},
            idempotency_key=str(uuid.uuid4()),
        )

    # Invariants verification: zero partial records, hold preserved
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert OrderReservation.objects.count() == 0
    assert CheckoutIdempotency.objects.count() == 0

    hold.refresh_from_db()
    assert hold.status == HoldStatus.ACTIVE
