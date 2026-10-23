"""Views for Catalog domain with tenant isolation and category capability inspection."""

from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.views import user_can_manage_merchant, user_can_view_merchant

from .models import CatalogItem
from .registry import CategoryRegistry
from .serializers import CatalogItemSerializer, CategoryCapabilitySerializer


class CategoryListView(APIView):
    """List all supported marketplace categories and their declared capabilities."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response:
        categories = [cap.to_dict() for cap in CategoryRegistry.list_all()]
        serializer = CategoryCapabilitySerializer(categories, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)


class CatalogItemListCreateView(APIView):
    """
    List catalog items (filtered by category, outlet, or tenant)
    or create a new catalog item under an authenticated merchant.
    """

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request: Request) -> Response:
        queryset = CatalogItem.objects.select_related("merchant", "outlet").all()

        # Query parameter filters
        merchant_id = request.query_params.get("merchant_id")
        outlet_id = request.query_params.get("outlet_id")
        category = request.query_params.get("category")
        is_active_param = request.query_params.get("is_active")

        user = request.user
        is_authenticated = isinstance(user, User) and user.is_authenticated
        is_platform_admin = (
            isinstance(user, User) and user.is_authenticated and user.is_platform_admin
        )

        # Validate is_active boolean filter if provided
        is_active_filter: bool | None = None
        if is_active_param is not None:
            val = is_active_param.strip().lower()
            if val in ("true", "1"):
                is_active_filter = True
            elif val in ("false", "0"):
                is_active_filter = False
            else:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Invalid boolean value for is_active. Allowed: true, false, 1, 0.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Retrieve user active merchant memberships
        user_merchant_ids: set[UUID] = set()
        if isinstance(user, User) and user.is_authenticated:
            user_merchant_ids = set(
                MerchantMembership.objects.filter(user=user, is_active=True).values_list(
                    "merchant_id", flat=True
                )
            )

        merchant_uuid: UUID | None = None
        if merchant_id:
            try:
                merchant_uuid = UUID(merchant_id)
                queryset = queryset.filter(merchant_id=merchant_uuid)
            except ValueError:
                return Response(
                    {
                        "success": False,
                        "error": {"code": "INVALID_UUID", "message": "Invalid merchant_id format."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if outlet_id:
            try:
                outlet_uuid = UUID(outlet_id)
                queryset = queryset.filter(outlet_id=outlet_uuid)
            except ValueError:
                return Response(
                    {
                        "success": False,
                        "error": {"code": "INVALID_UUID", "message": "Invalid outlet_id format."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if category:
            queryset = queryset.filter(category=category.upper())

        # Determine caller's operational context
        is_privileged_merchant_query = False
        if (
            is_platform_admin
            or is_authenticated
            and merchant_uuid
            and merchant_uuid in user_merchant_ids
        ):
            is_privileged_merchant_query = True
        elif (
            is_authenticated
            and not merchant_uuid
            and user_merchant_ids
            and is_active_filter is not True
        ):
            # Management query across caller's merchants
            queryset = queryset.filter(merchant_id__in=user_merchant_ids)
            is_privileged_merchant_query = True

        # Enforce visibility rules
        if not is_privileged_merchant_query:
            if is_active_filter is False:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "Public users and unauthorized members cannot query inactive catalog items.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            queryset = queryset.filter(is_active=True)
        else:
            if is_active_filter is not None:
                queryset = queryset.filter(is_active=is_active_filter)

        serializer = CatalogItemSerializer(queryset.order_by("-created_at"), many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User) or not user.is_authenticated:
            return Response(
                {
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = request.data if isinstance(request.data, dict) else {}
        merchant_id = data.get("merchant")
        if not merchant_id:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "details": {"merchant": ["Merchant ID is required."]},
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except (Merchant.DoesNotExist, ValueError):
            return Response(
                {
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Merchant does not exist."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user_can_manage_merchant(user, merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to manage this merchant's catalog.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CatalogItemSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = serializer.save()
        return Response(
            {"success": True, "data": CatalogItemSerializer(item).data},
            status=status.HTTP_201_CREATED,
        )


class CatalogItemDetailView(APIView):
    """Retrieve, update, or deactivate a catalog item with tenant verification."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_object(self, pk: str) -> CatalogItem:
        try:
            item_uuid = UUID(pk)
        except ValueError as err:
            raise Http404("Invalid UUID format.") from err
        return get_object_or_404(
            CatalogItem.objects.select_related("merchant", "outlet"), id=item_uuid
        )

    def get(self, request: Request, pk: str) -> Response:
        item = self.get_object(pk)
        user = request.user

        if not item.is_active and (
            not isinstance(user, User)
            or not user.is_authenticated
            or not user_can_view_merchant(user, item.merchant)
        ):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Catalog item not found or inactive.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CatalogItemSerializer(item)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: str) -> Response:
        return self._update(request, pk, partial=True)

    def put(self, request: Request, pk: str) -> Response:
        return self._update(request, pk, partial=False)

    def _update(self, request: Request, pk: str, partial: bool) -> Response:
        item = self.get_object(pk)
        user = request.user

        if not isinstance(user, User) or not user_can_manage_merchant(user, item.merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to modify this catalog item.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CatalogItemSerializer(
            item, data=request.data, partial=partial, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_item = serializer.save()
        return Response(
            {"success": True, "data": CatalogItemSerializer(updated_item).data},
            status=status.HTTP_200_OK,
        )

    def delete(self, request: Request, pk: str) -> Response:
        """Logically deactivate the catalog item to preserve historical audit integrity."""
        item = self.get_object(pk)
        user = request.user

        if not isinstance(user, User) or not user_can_manage_merchant(user, item.merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to delete this catalog item.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        item.is_active = False
        item.save(update_fields=["is_active", "updated_at"])
        return Response(
            {
                "success": True,
                "message": "Catalog item successfully deactivated.",
                "data": CatalogItemSerializer(item).data,
            },
            status=status.HTTP_200_OK,
        )
