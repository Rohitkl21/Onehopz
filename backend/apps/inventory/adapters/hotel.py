"""Hotel room inventory adapter (calendar room-nights and stay blocks)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class HotelInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Hotel room type calendar blocks and night-audit rules."""

    category = OutletCategory.HOTEL
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_rooms = max(1, query.quantity)
        total_rooms = 20
        booked_rooms = 14
        available_rooms = max(0, total_rooms - booked_rooms)
        is_avail = available_rooms >= requested_rooms

        stay_date = str(query.date or "2026-10-24")
        room_type = query.parameters.get("room_type", "DELUXE_KING")

        breakdown: dict[str, Any] = {
            "room_type": room_type,
            "stay_date": stay_date,
            "total_inventory": total_rooms,
            "booked_or_held": booked_rooms,
            "available_rooms": available_rooms,
            "night_audit_cutoff_hour": "04:00",
            "max_occupancy_per_room": 2,
            "cancellation_tier": "FLEXIBLE_UNTIL_1800",
        }

        messages = [
            f"Simulated hotel inventory: {available_rooms} {room_type} rooms available for {stay_date}."
        ]
        if not is_avail:
            messages.append(f"No available rooms of type {room_type} for date {stay_date}.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_rooms,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "room_night",
            "has_date_range": True,
            "night_audit_cutoff_supported": True,
            "multi_night_locking": True,
        }
