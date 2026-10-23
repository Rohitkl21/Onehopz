"""Tenant-isolated views for Merchants, Outlets, and Staff management."""

from typing import Any
from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User

from .models import (
    Merchant,
    MerchantMembership,
    MerchantMembershipRole,
    Outlet,
    OutletStaff,
    StaffRole,
)
from .serializers import (
    MerchantMembershipSerializer,
    MerchantSerializer,
    OutletSerializer,
    OutletStaffSerializer,
)


def user_can_manage_merchant(user: Any, merchant: Merchant) -> bool:
    """Check if user is OWNER or ADMIN of the merchant, or platform admin."""
    if not isinstance(user, User):
        return False
    if user.is_platform_admin:
        return True
    return MerchantMembership.objects.filter(
        merchant=merchant,
        user=user,
        role__in=[MerchantMembershipRole.OWNER, MerchantMembershipRole.ADMIN],
        is_active=True,
    ).exists()


def user_can_view_merchant(user: Any, merchant: Merchant) -> bool:
    """Check if user has any active membership with the merchant, or is platform admin."""
    if not isinstance(user, User):
        return False
    if user.is_platform_admin:
        return True
    return MerchantMembership.objects.filter(
        merchant=merchant,
        user=user,
        is_active=True,
    ).exists()


def user_can_manage_outlet(user: Any, outlet: Outlet) -> bool:
    """Check if user can manage staff at an outlet."""
    if not isinstance(user, User):
        return False
    if user_can_manage_merchant(user, outlet.merchant):
        return True
    return OutletStaff.objects.filter(
        outlet=outlet,
        user=user,
        staff_role=StaffRole.MANAGER,
        is_active=True,
    ).exists()


class MerchantListCreateView(APIView):
    """List user's merchants or create a new merchant organization."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User):
            return Response(
                {
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.is_platform_admin:
            merchants = Merchant.objects.all().order_by("-created_at")
        else:
            merchant_ids = MerchantMembership.objects.filter(user=user, is_active=True).values_list(
                "merchant_id", flat=True
            )
            merchants = Merchant.objects.filter(id__in=merchant_ids).order_by("-created_at")

        serializer = MerchantSerializer(merchants, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        serializer = MerchantSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        merchant = serializer.save()
        return Response(
            {"success": True, "data": MerchantSerializer(merchant).data},
            status=status.HTTP_201_CREATED,
        )


class MerchantDetailView(APIView):
    """Retrieve details for a specific merchant with strict tenant isolation."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: UUID) -> Response:
        merchant = get_object_or_404(Merchant, pk=pk)
        if not user_can_view_merchant(request.user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {"code": "ACCESS_DENIED", "message": "Tenant access denied."},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            {"success": True, "data": MerchantSerializer(merchant).data},
            status=status.HTTP_200_OK,
        )


class MerchantMembershipListCreateView(APIView):
    """List members or add team members to a merchant organization."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, merchant_id: UUID) -> Response:
        merchant = get_object_or_404(Merchant, pk=merchant_id)
        if not user_can_view_merchant(request.user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {"code": "ACCESS_DENIED", "message": "Tenant access denied."},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        memberships = merchant.memberships.select_related("user").order_by("created_at")
        serializer = MerchantMembershipSerializer(memberships, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request: Request, merchant_id: UUID) -> Response:
        merchant = get_object_or_404(Merchant, pk=merchant_id)
        if not user_can_manage_merchant(request.user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Only merchant owners and admins can add members.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MerchantMembershipSerializer(data=request.data, context={"merchant": merchant})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = serializer.save()
        return Response(
            {"success": True, "data": MerchantMembershipSerializer(membership).data},
            status=status.HTTP_201_CREATED,
        )


class MerchantOutletListCreateView(APIView):
    """List outlets for a merchant or create a new outlet under this merchant."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, merchant_id: UUID) -> Response:
        merchant = get_object_or_404(Merchant, pk=merchant_id)
        if not user_can_view_merchant(request.user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {"code": "ACCESS_DENIED", "message": "Tenant access denied."},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        outlets = merchant.outlets.all().order_by("created_at")
        serializer = OutletSerializer(outlets, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request: Request, merchant_id: UUID) -> Response:
        merchant = get_object_or_404(Merchant, pk=merchant_id)
        if not user_can_manage_merchant(request.user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Only merchant owners and admins can create outlets.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OutletSerializer(data=request.data, context={"merchant": merchant})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        outlet = serializer.save()
        return Response(
            {"success": True, "data": OutletSerializer(outlet).data},
            status=status.HTTP_201_CREATED,
        )


class OutletDetailView(APIView):
    """Retrieve details for a specific outlet."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: UUID) -> Response:
        outlet = get_object_or_404(Outlet, pk=pk)
        user = request.user
        if not isinstance(user, User):
            return Response(
                {
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user_can_view_merchant(user, outlet.merchant):
            # Check if user is staff at this specific outlet
            is_staff = OutletStaff.objects.filter(outlet=outlet, user=user, is_active=True).exists()
            if not is_staff:
                return Response(
                    {
                        "success": False,
                        "error": {"code": "ACCESS_DENIED", "message": "Tenant access denied."},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        return Response(
            {"success": True, "data": OutletSerializer(outlet).data},
            status=status.HTTP_200_OK,
        )


class OutletStaffListCreateView(APIView):
    """List or assign staff members to an outlet."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: UUID) -> Response:
        outlet = get_object_or_404(Outlet, pk=pk)
        user = request.user
        if not isinstance(user, User):
            return Response(
                {
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user_can_view_merchant(user, outlet.merchant):
            is_staff = OutletStaff.objects.filter(outlet=outlet, user=user, is_active=True).exists()
            if not is_staff:
                return Response(
                    {
                        "success": False,
                        "error": {"code": "ACCESS_DENIED", "message": "Access denied."},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        staff = outlet.staff_memberships.select_related("user").order_by("created_at")
        serializer = OutletStaffSerializer(staff, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request: Request, pk: UUID) -> Response:
        outlet = get_object_or_404(Outlet, pk=pk)
        if not user_can_manage_outlet(request.user, outlet):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Only merchant managers or outlet managers can assign staff.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OutletStaffSerializer(data=request.data, context={"outlet": outlet})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        staff = serializer.save()
        return Response(
            {"success": True, "data": OutletStaffSerializer(staff).data},
            status=status.HTTP_201_CREATED,
        )


class OutletStaffDetailView(APIView):
    """Remove a staff member from an outlet."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request: Request, pk: UUID, user_id: UUID) -> Response:
        outlet = get_object_or_404(Outlet, pk=pk)
        if not user_can_manage_outlet(request.user, outlet):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Only merchant managers or outlet managers can remove staff.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        membership = get_object_or_404(OutletStaff, outlet=outlet, user_id=user_id)
        membership.delete()
        return Response(
            {"success": True, "data": {"message": "Staff member removed successfully."}},
            status=status.HTTP_200_OK,
        )
