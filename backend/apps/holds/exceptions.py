"""Hold engine domain exceptions."""

from typing import Any


class HoldDomainError(Exception):
    """Base exception for hold domain failures."""

    default_code = "HOLD_ERROR"

    def __init__(
        self, message: str, code: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}


class IdempotencyConflictError(HoldDomainError):
    default_code = "IDEMPOTENCY_CONFLICT"


class InventoryAlreadyLockedError(HoldDomainError):
    default_code = "INVENTORY_ALREADY_LOCKED"

    def __init__(
        self,
        message: str,
        conflicting_unit: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        det = details or {}
        if conflicting_unit:
            det["conflicting_unit"] = conflicting_unit
        super().__init__(message, code=self.default_code, details=det)


class InsufficientInventoryError(HoldDomainError):
    default_code = "INSUFFICIENT_INVENTORY"


class HoldNotFoundError(HoldDomainError):
    default_code = "HOLD_NOT_FOUND"


class HoldExpiredError(HoldDomainError):
    default_code = "HOLD_EXPIRED"


class HoldPermissionDeniedError(HoldDomainError):
    default_code = "HOLD_PERMISSION_DENIED"


class HoldStateError(HoldDomainError):
    default_code = "INVALID_HOLD_STATE"


class UnsupportedInventoryCategoryError(HoldDomainError):
    default_code = "UNSUPPORTED_INVENTORY_CATEGORY"
