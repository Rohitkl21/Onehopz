"""Automated test suite for Inventory domain, adapters, and availability querying."""

import pytest
from django.test import Client
from rest_framework import status

from apps.inventory.adapters import (
    CinemaInventoryAdapter,
    EventInventoryAdapter,
    HotelInventoryAdapter,
    RestaurantInventoryAdapter,
    SalonInventoryAdapter,
    SurplusFoodInventoryAdapter,
    TravelInventoryAdapter,
)
from apps.inventory.contracts import AvailabilityQuery
from apps.inventory.registry import InventoryRegistry
from apps.merchants.models import OutletCategory


def test_inventory_registry_resolves_all_seven_categories() -> None:
    """Verify InventoryRegistry resolves adapters for all 7 verticals."""
    supported = InventoryRegistry.list_supported_categories()
    assert len(supported) == 7

    assert isinstance(InventoryRegistry.get_adapter(OutletCategory.CINEMA), CinemaInventoryAdapter)
    assert isinstance(
        InventoryRegistry.get_adapter(OutletCategory.RESTAURANT), RestaurantInventoryAdapter
    )
    assert isinstance(
        InventoryRegistry.get_adapter(OutletCategory.SURPLUS_FOOD), SurplusFoodInventoryAdapter
    )
    assert isinstance(InventoryRegistry.get_adapter(OutletCategory.HOTEL), HotelInventoryAdapter)
    assert isinstance(InventoryRegistry.get_adapter(OutletCategory.SALON), SalonInventoryAdapter)
    assert isinstance(InventoryRegistry.get_adapter(OutletCategory.EVENT), EventInventoryAdapter)
    assert isinstance(InventoryRegistry.get_adapter(OutletCategory.TRAVEL), TravelInventoryAdapter)


def test_inventory_registry_rejects_unknown_category() -> None:
    """Verify unknown category raises KeyError."""
    assert InventoryRegistry.is_supported("UNKNOWN_CATEGORY") is False
    with pytest.raises(KeyError):
        InventoryRegistry.get_adapter("UNKNOWN_CATEGORY")


def test_cinema_inventory_adapter() -> None:
    """Verify cinema adapter returns discrete seat breakdown with simulated flag."""
    adapter = CinemaInventoryAdapter()
    query = AvailabilityQuery(category=OutletCategory.CINEMA, quantity=2)
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.CINEMA
    assert result.is_simulated is True
    assert "screen_number" in result.breakdown
    assert "sample_allocated_seats" in result.breakdown
    assert result.breakdown["hold_window_minutes"] == 8

    caps = adapter.get_capabilities()
    assert caps["unit_of_sale"] == "discrete_seat"
    assert caps["has_seat_map"] is True


def test_restaurant_inventory_adapter() -> None:
    """Verify restaurant adapter returns table cover slot and pacing status."""
    adapter = RestaurantInventoryAdapter()
    query = AvailabilityQuery(category=OutletCategory.RESTAURANT, quantity=4)
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.RESTAURANT
    assert result.is_simulated is True
    assert result.breakdown["dining_window_minutes"] == 90
    assert result.breakdown["arrival_grace_minutes"] == 15
    assert result.breakdown["pacing_control_status"] == "NORMAL"


def test_surplus_food_inventory_adapter() -> None:
    """Verify surplus food adapter returns pickup window and FSSAI status."""
    adapter = SurplusFoodInventoryAdapter()
    query = AvailabilityQuery(category=OutletCategory.SURPLUS_FOOD, quantity=3)
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.SURPLUS_FOOD
    assert result.is_simulated is True
    assert "pickup_window" in result.breakdown
    assert result.breakdown["fssai_verified"] is True
    assert result.breakdown["pickup_window"]["pickup_start"] == "21:30:00"


def test_hotel_inventory_adapter() -> None:
    """Verify hotel adapter returns room type and night audit cutoff."""
    adapter = HotelInventoryAdapter()
    query = AvailabilityQuery(category=OutletCategory.HOTEL, date="2026-10-25", quantity=1)
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.HOTEL
    assert result.is_simulated is True
    assert result.breakdown["night_audit_cutoff_hour"] == "04:00"
    assert result.breakdown["room_type"] == "DELUXE_KING"


def test_salon_inventory_adapter() -> None:
    """Verify salon adapter returns stylist schedule and cleanup buffer."""
    adapter = SalonInventoryAdapter()
    query = AvailabilityQuery(category=OutletCategory.SALON, quantity=1)
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.SALON
    assert result.is_simulated is True
    assert result.breakdown["cleanup_buffer_minutes"] == 15
    assert "stylist" in result.breakdown


def test_event_inventory_adapter() -> None:
    """Verify event adapter returns tiered quota and burst allocation model."""
    adapter = EventInventoryAdapter()
    query = AvailabilityQuery(
        category=OutletCategory.EVENT,
        quantity=2,
        parameters={"tier": "VIP"},
    )
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.EVENT
    assert result.is_simulated is True
    assert result.breakdown["event_tier"] == "VIP"
    assert result.breakdown["burst_decrement_model"] == "ATOMIC_POSTGRES_CHECK"


def test_travel_inventory_adapter() -> None:
    """Verify travel adapter indicates mock provider and timeout ceiling."""
    adapter = TravelInventoryAdapter()
    query = AvailabilityQuery(
        category=OutletCategory.TRAVEL,
        quantity=2,
        parameters={"transport_type": "BUS", "route": "BLR-HYD"},
    )
    result = adapter.check_availability(query)

    assert result.is_available is True
    assert result.category == OutletCategory.TRAVEL
    assert result.is_simulated is True
    assert result.breakdown["provider_adapter"] == "MOCK_TRAVEL_PROVIDER"
    assert result.breakdown["timeout_ceiling_ms"] == 5000


@pytest.mark.django_db
def test_inventory_availability_api_endpoint() -> None:
    """Verify POST /api/v1/inventory/availability/ dispatches to vertical adapters."""
    client = Client()

    # Query cinema availability
    cinema_res = client.post(
        "/api/v1/inventory/availability/",
        data={"category": OutletCategory.CINEMA, "quantity": 2},
        content_type="application/json",
    )
    assert cinema_res.status_code == status.HTTP_200_OK
    cinema_data = cinema_res.json()
    assert cinema_data["success"] is True
    assert cinema_data["data"]["is_available"] is True
    assert cinema_data["data"]["is_simulated"] is True
    assert cinema_data["data"]["category"] == OutletCategory.CINEMA

    # Query invalid category returns 400 validation error
    invalid_res = client.post(
        "/api/v1/inventory/availability/",
        data={"category": "INVALID_CAT", "quantity": 1},
        content_type="application/json",
    )
    assert invalid_res.status_code == status.HTTP_400_BAD_REQUEST
    assert invalid_res.json()["success"] is False


@pytest.mark.django_db
def test_inventory_capabilities_api_endpoint() -> None:
    """Verify GET /api/v1/inventory/capabilities/ returns all vertical capabilities."""
    client = Client()
    response = client.get("/api/v1/inventory/capabilities/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 7
    assert OutletCategory.CINEMA in data["data"]
    assert OutletCategory.TRAVEL in data["data"]
