"""Category registry and capabilities specification for OneHopz multi-category platform."""

from dataclasses import asdict, dataclass
from typing import Any

from apps.merchants.models import OutletCategory


@dataclass(frozen=True)
class CategoryCapabilities:
    """Declared capabilities and domain characteristics of a marketplace category."""

    category: str
    display_name: str
    allocation_unit: str
    has_seat_map: bool
    has_time_slots: bool
    has_date_range: bool
    has_expiry_window: bool
    is_supplier_managed: bool
    concurrency_model: str
    cancellation_rules_summary: str
    requires_fssai: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CategoryRegistry:
    """Registry maintaining capability declarations for all seven OneHopz verticals."""

    _CAPABILITIES: dict[str, CategoryCapabilities] = {
        OutletCategory.CINEMA: CategoryCapabilities(
            category=OutletCategory.CINEMA,
            display_name="Cinema Ticket Booking",
            allocation_unit="seat",
            has_seat_map=True,
            has_time_slots=True,
            has_date_range=False,
            has_expiry_window=False,
            is_supplier_managed=False,
            concurrency_model="discrete_seat_lock",
            cancellation_rules_summary="Permitted up to 2 hours before showtime",
        ),
        OutletCategory.RESTAURANT: CategoryCapabilities(
            category=OutletCategory.RESTAURANT,
            display_name="Restaurant Table Reservations",
            allocation_unit="table_covers",
            has_seat_map=False,
            has_time_slots=True,
            has_date_range=False,
            has_expiry_window=False,
            is_supplier_managed=False,
            concurrency_model="capacity_pacing",
            cancellation_rules_summary="Free cancellation up to 1 hour before dining slot; 15-min grace window",
            requires_fssai=True,
        ),
        OutletCategory.SURPLUS_FOOD: CategoryCapabilities(
            category=OutletCategory.SURPLUS_FOOD,
            display_name="Surplus Food Listings & Discounted Pickup",
            allocation_unit="quantity_batch",
            has_seat_map=False,
            has_time_slots=False,
            has_date_range=False,
            has_expiry_window=True,
            is_supplier_managed=False,
            concurrency_model="atomic_stock_decrement",
            cancellation_rules_summary="Permitted up to 30 mins before pickup window; perishable once packed",
            requires_fssai=True,
        ),
        OutletCategory.HOTEL: CategoryCapabilities(
            category=OutletCategory.HOTEL,
            display_name="Hotel Room Bookings",
            allocation_unit="room_night",
            has_seat_map=False,
            has_time_slots=False,
            has_date_range=True,
            has_expiry_window=False,
            is_supplier_managed=False,
            concurrency_model="multi_night_calendar_lock",
            cancellation_rules_summary="Flash deals non-refundable; standard refundable up to 18:00 check-in day",
        ),
        OutletCategory.SALON: CategoryCapabilities(
            category=OutletCategory.SALON,
            display_name="Salon & Beauty Appointments",
            allocation_unit="stylist_service_slot",
            has_seat_map=False,
            has_time_slots=True,
            has_date_range=False,
            has_expiry_window=False,
            is_supplier_managed=False,
            concurrency_model="composite_resource_graph",
            cancellation_rules_summary="Free cancellation up to 2 hours before; late cancel incurs 30% fee",
        ),
        OutletCategory.EVENT: CategoryCapabilities(
            category=OutletCategory.EVENT,
            display_name="Event Ticketing",
            allocation_unit="ticket_tier",
            has_seat_map=True,
            has_time_slots=True,
            has_date_range=False,
            has_expiry_window=False,
            is_supplier_managed=False,
            concurrency_model="burst_atomic_quota_decrement",
            cancellation_rules_summary="Non-refundable unless organizer cancels or reschedules",
        ),
        OutletCategory.TRAVEL: CategoryCapabilities(
            category=OutletCategory.TRAVEL,
            display_name="Travel Bookings (Bus & Airline)",
            allocation_unit="route_schedule_pnr",
            has_seat_map=True,
            has_time_slots=True,
            has_date_range=True,
            has_expiry_window=False,
            is_supplier_managed=True,
            concurrency_model="external_supplier_gds_sync",
            cancellation_rules_summary="Subject to Motor Vehicles Act for bus and DGCA regulations for airlines",
        ),
    }

    @classmethod
    def get_capabilities(cls, category: str) -> CategoryCapabilities | None:
        """Return capabilities for a specific category or None if invalid."""
        return cls._CAPABILITIES.get(category)

    @classmethod
    def list_all(cls) -> list[CategoryCapabilities]:
        """Return declared capabilities for all seven marketplace verticals."""
        return list(cls._CAPABILITIES.values())

    @classmethod
    def is_valid_category(cls, category: str) -> bool:
        """Check if category string is registered in the taxonomy."""
        return category in cls._CAPABILITIES
