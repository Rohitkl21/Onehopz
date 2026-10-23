"""Central inventory registry routing category queries to appropriate vertical adapters."""

from typing import Any

from apps.merchants.models import OutletCategory

from .adapters import (
    CinemaInventoryAdapter,
    EventInventoryAdapter,
    HotelInventoryAdapter,
    RestaurantInventoryAdapter,
    SalonInventoryAdapter,
    SurplusFoodInventoryAdapter,
    TravelInventoryAdapter,
)
from .contracts import BaseInventoryAdapter


class InventoryRegistry:
    """Registry maintaining active inventory adapters for all seven platform categories."""

    _ADAPTERS: dict[str, BaseInventoryAdapter] = {
        OutletCategory.CINEMA: CinemaInventoryAdapter(),
        OutletCategory.RESTAURANT: RestaurantInventoryAdapter(),
        OutletCategory.SURPLUS_FOOD: SurplusFoodInventoryAdapter(),
        OutletCategory.HOTEL: HotelInventoryAdapter(),
        OutletCategory.SALON: SalonInventoryAdapter(),
        OutletCategory.EVENT: EventInventoryAdapter(),
        OutletCategory.TRAVEL: TravelInventoryAdapter(),
    }

    @classmethod
    def get_adapter(cls, category: str) -> BaseInventoryAdapter:
        """
        Lookup the inventory adapter for a given category.

        Raises:
            KeyError: if the category is unsupported.
        """
        normalized_cat = category.upper()
        if normalized_cat not in cls._ADAPTERS:
            raise KeyError(
                f"Unsupported inventory category '{category}'. "
                f"Available: {list(cls._ADAPTERS.keys())}"
            )
        return cls._ADAPTERS[normalized_cat]

    @classmethod
    def is_supported(cls, category: str) -> bool:
        """Check if category is registered in the inventory domain."""
        return category.upper() in cls._ADAPTERS

    @classmethod
    def list_supported_categories(cls) -> list[str]:
        """Return list of all registered inventory category keys."""
        return list(cls._ADAPTERS.keys())

    @classmethod
    def get_all_capabilities(cls) -> dict[str, dict[str, Any]]:
        """Return dictionary of capabilities across all category adapters."""
        return {category: adapter.get_capabilities() for category, adapter in cls._ADAPTERS.items()}
