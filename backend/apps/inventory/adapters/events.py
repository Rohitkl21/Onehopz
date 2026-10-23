"""Event ticket inventory adapter (tiered quotas and high-concurrency burst allocation)."""

from typing import Any

from apps.merchants.models import OutletCategory

from ..contracts import AvailabilityQuery, AvailabilityResult, BaseInventoryAdapter


class EventInventoryAdapter(BaseInventoryAdapter):
    """Adapter for Event tiered ticket quotas and gate release rules."""

    category = OutletCategory.EVENT
    is_simulated = True

    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        requested_tickets = max(1, query.quantity)
        tier_name = query.parameters.get("tier", "GENERAL_ADMISSION")

        tiers: dict[str, dict[str, int]] = {
            "VIP": {"total": 50, "sold": 42},
            "EARLY_BIRD": {"total": 200, "sold": 200},
            "GENERAL_ADMISSION": {"total": 500, "sold": 380},
        }

        tier_info = tiers.get(tier_name, {"total": 100, "sold": 50})
        available_tier_tickets = max(0, tier_info["total"] - tier_info["sold"])
        is_avail = available_tier_tickets >= requested_tickets

        breakdown: dict[str, Any] = {
            "event_tier": tier_name,
            "total_quota": tier_info["total"],
            "sold_or_held": tier_info["sold"],
            "available_quota": available_tier_tickets,
            "all_tiers_summary": {
                k: {"total": v["total"], "available": max(0, v["total"] - v["sold"])}
                for k, v in tiers.items()
            },
            "burst_decrement_model": "ATOMIC_POSTGRES_CHECK",
            "hold_window_seconds": 480,
        }

        messages = [
            f"Simulated event inventory: {available_tier_tickets} tickets available in tier '{tier_name}'."
        ]
        if not is_avail:
            messages.append(f"Tier '{tier_name}' sold out or insufficient quota.")

        return AvailabilityResult(
            is_available=is_avail,
            available_units=available_tier_tickets,
            category=self.category,
            breakdown=breakdown,
            is_simulated=True,
            messages=messages,
        )

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "unit_of_sale": "ticket_tier_quota",
            "supports_seat_selection": False,
            "supports_tiered_quotas": True,
            "burst_concurrency_mode": "atomic_sql_decrement",
        }
