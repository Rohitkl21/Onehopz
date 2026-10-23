"""Domain exceptions for the Orders application."""


class OrderDomainError(Exception):
    """Base exception for all order and checkout domain errors."""

    def __init__(self, message: str, code: str = "ORDER_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class HoldExpiredForCheckoutError(OrderDomainError):
    """Raised when a hold cannot be converted because it has expired."""

    def __init__(self, message: str = "The reservation hold has expired.") -> None:
        super().__init__(message, code="HOLD_EXPIRED")


class HoldNotOwnedError(OrderDomainError):
    """Raised when an authenticated user attempts to checkout a hold owned by another user."""

    def __init__(self, message: str = "You do not have permission to checkout this hold.") -> None:
        super().__init__(message, code="HOLD_NOT_OWNED")


class HoldAlreadyConvertedError(OrderDomainError):
    """Raised when a hold has already been converted to an order."""

    def __init__(self, message: str = "This reservation hold has already been converted to an order.") -> None:
        super().__init__(message, code="HOLD_ALREADY_CONVERTED")


class InventoryReservationUnavailableError(OrderDomainError):
    """Raised when underlying inventory allocations are missing, corrupted, or unavailable."""

    def __init__(self, message: str = "Inventory reservation is no longer available.") -> None:
        super().__init__(message, code="INVENTORY_RESERVATION_UNAVAILABLE")


class IdempotencyConflictError(OrderDomainError):
    """Raised when an idempotency key is reused with a different request payload."""

    def __init__(self, message: str = "Idempotency key was previously used with a different request payload.") -> None:
        super().__init__(message, code="IDEMPOTENCY_CONFLICT")


class OrderReservationExpiredError(OrderDomainError):
    """Raised when an operation is attempted on an order whose payment deadline has passed."""

    def __init__(self, message: str = "The payment deadline for this order reservation has expired.") -> None:
        super().__init__(message, code="ORDER_RESERVATION_EXPIRED")


class OrderNotFoundError(OrderDomainError):
    """Raised when an order cannot be found."""

    def __init__(self, message: str = "Order not found.") -> None:
        super().__init__(message, code="ORDER_NOT_FOUND")


class OrderPermissionDeniedError(OrderDomainError):
    """Raised when an actor lacks authorization to inspect or manipulate an order."""

    def __init__(self, message: str = "You do not have permission to access this order.") -> None:
        super().__init__(message, code="ORDER_PERMISSION_DENIED")


class UnsupportedCheckoutCategoryError(OrderDomainError):
    """Raised when a category does not support durable checkout order conversion."""

    def __init__(self, message: str = "Category is not supported for checkout.") -> None:
        super().__init__(message, code="UNSUPPORTED_CATEGORY")


class InventoryCutoffExceededError(OrderDomainError):
    """Raised when the booking cutoff or event start time has already passed."""

    def __init__(self, message: str = "Inventory booking cutoff deadline has passed.") -> None:
        super().__init__(message, code="INVENTORY_CUTOFF_EXCEEDED")
