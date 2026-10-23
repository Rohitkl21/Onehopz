"""Inventory domain contracts and polymorphic adapter interfaces."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, time
from typing import Any
from uuid import UUID


@dataclass
class AvailabilityQuery:
    """Standardized multi-category query for checking inventory availability."""

    category: str
    item_id: UUID | None = None
    outlet_id: UUID | None = None
    date: date | str | None = None
    start_time: time | str | None = None
    end_time: time | str | None = None
    quantity: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class AvailabilityResult:
    """Standardized representation of inventory availability response."""

    is_available: bool
    available_units: int
    category: str
    breakdown: dict[str, Any] = field(default_factory=dict)
    is_simulated: bool = True
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseInventoryAdapter(ABC):
    """Abstract base class for all category-specific inventory adapters."""

    category: str
    is_simulated: bool = True

    @abstractmethod
    def check_availability(self, query: AvailabilityQuery) -> AvailabilityResult:
        """
        Evaluate availability for the given category-specific query.
        Must be idempotent and non-locking.
        """
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> dict[str, Any]:
        """Return structural capabilities and constraints for this inventory vertical."""
        raise NotImplementedError
