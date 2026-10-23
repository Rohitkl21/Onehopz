"""Restaurant inventory adapter (table covers and dining shift slots)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class RestaurantInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Restaurant cover slot and table allocation."""

    category = OutletCategory.RESTAURANT
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        party_size = max(1, query.quantity)
        slot_time = str(query.start_time or "20:00:00")
        max_covers_per_slot = 30
        reserved_covers = 18
        available_covers = max_covers_per_slot - reserved_covers
        is_avail = available_covers >= party_size

        breakdown: dict[str, Any] = {
            "dining_window_minutes": 90,
            "slot_time": slot_time,
            "party_size": party_size,
            "max_slot_capacity": max_covers_per_slot,
            "current_reserved_covers": reserved_covers,
            "available_covers": available_covers,
            "pacing_control_status": "NORMAL" if is_avail else "CAPACITY_EXCEEDED",
            "table_candidate": {"table_number": "T4", "min_party": 2, "max_party": 4}
            if is_avail
            else None,
            "arrival_grace_minutes": 15,
        }

        messages = [
            f"Simulated restaurant inventory: {available_covers} covers available for slot {slot_time}."
        ]
        if not is_avail:
            messages.append(f"Slot capacity reached. Cannot seat party size {party_size}.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_covers,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "table_covers",
            "has_pacing_control": True,
            "grace_period_minutes": 15,
            "dining_block_duration_minutes": 90,
        }
