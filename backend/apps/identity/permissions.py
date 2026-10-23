"""Role-based access control (RBAC) permission classes."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import UserRole


class IsCustomer(BasePermission):
    """Allows access only to authenticated customer accounts."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.CUSTOMER
        )


class IsMerchantAdmin(BasePermission):
    """Allows access to merchant administrators or platform super admins."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.MERCHANT_ADMIN, UserRole.SUPER_ADMIN)
        )


class IsMerchantStaff(BasePermission):
    """Allows access to merchant staff, merchant admins, or platform super admins."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role
            in (UserRole.MERCHANT_STAFF, UserRole.MERCHANT_ADMIN, UserRole.SUPER_ADMIN)
        )


class IsPlatformAdmin(BasePermission):
    """Allows access only to privileged platform operations and financial administration."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role
            in (UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN, UserRole.PLATFORM_SUPPORT)
        )


class IsSuperAdmin(BasePermission):
    """Allows access only to super administrators."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPER_ADMIN
        )
