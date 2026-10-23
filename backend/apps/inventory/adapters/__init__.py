"""Category-specific inventory adapters for OneHopz."""

from .cinema import CinemaInventoryAdapter
from .events import EventInventoryAdapter
from .hotel import HotelInventoryAdapter
from .restaurant import RestaurantInventoryAdapter
from .salon import SalonInventoryAdapter
from .surplus_food import SurplusFoodInventoryAdapter
from .travel import TravelInventoryAdapter

__all__ = [
    "CinemaInventoryAdapter",
    "RestaurantInventoryAdapter",
    "SurplusFoodInventoryAdapter",
    "HotelInventoryAdapter",
    "SalonInventoryAdapter",
    "EventInventoryAdapter",
    "TravelInventoryAdapter",
]
