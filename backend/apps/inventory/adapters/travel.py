"""Travel inventory adapter (supplier-managed bus routes and airline schedules)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class TravelInventoryAdapter(BaseInventoryAdapter):
    """
    Adapter for Travel routes, berths, and flight seats.
    Operates as MOCK_TRAVEL_PROVIDER in local/demo environment.
    """

    category = OutletCategory.TRAVEL
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_seats = max(1, query.quantity)
        transport_type = query.parameters.get("transport_type", "BUS")  # BUS or AIRLINE
        route = query.parameters.get("route", "DEL-BOM")

        total_seats = 40 if transport_type == "BUS" else 180
        booked_seats = 28 if transport_type == "BUS" else 155
        available_seats = max(0, total_seats - booked_seats)
        is_avail = available_seats >= requested_seats

        breakdown: dict[str, Any] = {
            "provider_adapter": "MOCK_TRAVEL_PROVIDER",
            "transport_type": transport_type,
            "route": route,
            "departure_date": str(query.date or "2026-10-25"),
            "departure_time": str(query.start_time or "06:00:00"),
            "total_route_capacity": total_seats,
            "confirmed_pnr_count": booked_seats,
            "available_seats": available_seats,
            "sample_seat_ids": ["12A", "12B", "14C"][:requested_seats],
            "timeout_ceiling_ms": 5000,
            "saga_reconciliation_supported": True,
        }

        messages = [
            f"Simulated travel inventory (MOCK_TRAVEL_PROVIDER): {available_seats} {transport_type} seats available on {route}."
        ]
        if not is_avail:
            messages.append("Selected route leg is fully booked.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_seats,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "route_schedule_pnr",
            "is_supplier_managed": True,
            "gds_timeout_ms": 5000,
            "supports_bus": True,
            "supports_airline": True,
            "regulatory_rules": ["Motor Vehicles Act (Bus)", "DGCA CAR Section 3 (Airline)"],
        }
