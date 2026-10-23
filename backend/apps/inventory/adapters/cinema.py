"""Cinema inventory adapter (seat-based, showtime-scheduled)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class CinemaInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Cinema seat allocations and showtime screens."""

    category = OutletCategory.CINEMA
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_qty = max(1, query.quantity)
        total_seats = 120
        occupied_seats = 45
        available_seats = total_seats - occupied_seats
        is_avail = available_seats >= requested_qty

        # Simulated seat map layout with available sample seats
        sample_seats = [
            {"row": "E", "seat_number": 12 + i, "tier": "PREMIUM", "status": "AVAILABLE"}
            for i in range(min(requested_qty, available_seats))
        ]

        breakdown: dict[str, Any] = {
            "screen_number": query.parameters.get("screen", 1),
            "showtime": str(query.start_time or "19:30:00"),
            "total_capacity": total_seats,
            "occupied_seats": occupied_seats,
            "available_seats": available_seats,
            "sample_allocated_seats": sample_seats,
            "hold_window_minutes": 8,
            "single_seat_gap_policy": "NO_ORPHAN_SEATS",
        }

        messages = [
            f"Simulated cinema inventory: {available_seats} of {total_seats} seats available."
        ]
        if not is_avail:
            messages.append(
                f"Insufficient contiguous seats for requested quantity {requested_qty}."
            )

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
            "unit_of_sale": "discrete_seat",
            "has_seat_map": True,
            "hold_duration_seconds": 480,
            "supports_multi_tier": True,
        }
