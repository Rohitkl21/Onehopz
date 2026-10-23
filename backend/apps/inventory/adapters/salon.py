"""Salon and beauty appointment inventory adapter (stylist and chair resource graph)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class SalonInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Salon stylist appointment slots with cleanup buffer."""

    category = OutletCategory.SALON
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_slots = max(1, query.quantity)
        total_stylist_slots = 8
        booked_slots = 5
        available_slots = max(0, total_stylist_slots - booked_slots)
        is_avail = available_slots >= requested_slots

        service_duration = int(query.parameters.get("service_duration_mins", 45))
        cleanup_buffer = 15
        stylist_name = query.parameters.get("stylist_name", "Senior Stylist Priya")

        breakdown: dict[str, Any] = {
            "stylist": stylist_name,
            "service_duration_minutes": service_duration,
            "cleanup_buffer_minutes": cleanup_buffer,
            "total_block_minutes": service_duration + cleanup_buffer,
            "total_shift_slots": total_stylist_slots,
            "booked_slots": booked_slots,
            "available_slots": available_slots,
            "slot_window": {
                "start": str(query.start_time or "14:00:00"),
                "end": str(query.end_time or "15:00:00"),
            },
            "chair_assigned": "Station-3",
        }

        messages = [
            f"Simulated salon inventory: Stylist '{stylist_name}' has {available_slots} slots available."
        ]
        if not is_avail:
            messages.append("Stylist schedule conflict for the requested appointment interval.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_slots,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "stylist_slot",
            "has_resource_graph": True,
            "requires_cleanup_buffer": True,
            "stylist_specific_locking": True,
        }
