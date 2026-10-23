"""Surplus food inventory adapter (perishable batches and pickup windows)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class SurplusFoodInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Surplus Food batch allocations and strict pickup cutoffs."""

    category = OutletCategory.SURPLUS_FOOD
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_units = max(1, query.quantity)
        total_batch_units = 15
        sold_and_held_units = 9
        available_units = max(0, total_batch_units - sold_and_held_units)
        is_avail = available_units >= requested_units

        pickup_window = {
            "pickup_start": "21:30:00",
            "pickup_end": "22:15:00",
            "order_cutoff_minutes_before_window": 15,
        }

        breakdown: dict[str, Any] = {
            "batch_type": "Surplus Magic Bag",
            "total_prepared": total_batch_units,
            "sold_and_held": sold_and_held_units,
            "available_stock": available_units,
            "pickup_window": pickup_window,
            "dietary_classification": query.parameters.get("dietary", "VEG"),
            "requires_refrigeration": True,
            "fssai_verified": True,
        }

        messages = [
            f"Simulated surplus inventory: {available_units} bags available for pickup between 21:30-22:15."
        ]
        if not is_avail:
            messages.append("Batch sold out or insufficient quantity remaining.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_units,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "perishable_pack",
            "has_expiry_window": True,
            "strict_pickup_cutoff": True,
            "fssai_required": True,
        }
