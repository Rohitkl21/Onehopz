"""Views for Offer specifications and dynamic yield calculations."""

from decimal import Decimal
from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.views import user_can_manage_merchant

from .models import OfferSpecification
from .serializers import (
    OfferCalculationRequestSerializer,
    OfferCalculationResponseSerializer,
    OfferSpecificationSerializer,
)
from .services import calculate_discounted_price


class OfferListCreateView(APIView):
    """
    List offers (scoped to merchant, catalog item, or public active offers)
    or create a new offer specification.
    """

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request: Request) -> Response:
        queryset = OfferSpecification.objects.select_related(
            "merchant", "outlet", "catalog_item"
        ).all()

        merchant_id = request.query_params.get("merchant_id")
        outlet_id = request.query_params.get("outlet_id")
        catalog_item_id = request.query_params.get("catalog_item_id")
        category = request.query_params.get("category")
        is_active_param = request.query_params.get("is_active")

        user = request.user
        is_merchant_user = (
            isinstance(user, User)
            and user.is_authenticated
            and MerchantMembership.objects.filter(user=user, is_active=True).exists()
        )

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

        if catalog_item_id:
            try:
                item_uuid = UUID(catalog_item_id)
                queryset = queryset.filter(catalog_item_id=item_uuid)
            except ValueError:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "INVALID_UUID",
                            "message": "Invalid catalog_item_id format.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if category:
            queryset = queryset.filter(category=category.upper())

        if is_active_param is not None:
            active_bool = is_active_param.lower() in ("true", "1")
            queryset = queryset.filter(is_active=active_bool)
        elif not is_merchant_user and not (
            isinstance(user, User) and user.is_authenticated and user.is_platform_admin
        ):
            queryset = queryset.filter(is_active=True)

        serializer = OfferSpecificationSerializer(queryset.order_by("-created_at"), many=True)
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
                        "message": "You do not have permission to create offers for this merchant.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OfferSpecificationSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        offer = serializer.save()
        return Response(
            {"success": True, "data": OfferSpecificationSerializer(offer).data},
            status=status.HTTP_201_CREATED,
        )


class OfferDetailView(APIView):
    """Retrieve, update, or delete an offer specification."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_object(self, pk: str) -> OfferSpecification:
        try:
            offer_uuid = UUID(pk)
        except ValueError as err:
            raise Http404("Invalid UUID format.") from err
        return get_object_or_404(
            OfferSpecification.objects.select_related("merchant", "outlet", "catalog_item"),
            id=offer_uuid,
        )

    def get(self, request: Request, pk: str) -> Response:
        offer = self.get_object(pk)
        serializer = OfferSpecificationSerializer(offer)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: str) -> Response:
        return self._update(request, pk, partial=True)

    def put(self, request: Request, pk: str) -> Response:
        return self._update(request, pk, partial=False)

    def _update(self, request: Request, pk: str, partial: bool) -> Response:
        offer = self.get_object(pk)
        user = request.user

        if not isinstance(user, User) or not user_can_manage_merchant(user, offer.merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to modify this offer.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OfferSpecificationSerializer(
            offer, data=request.data, partial=partial, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_offer = serializer.save()
        return Response(
            {"success": True, "data": OfferSpecificationSerializer(updated_offer).data},
            status=status.HTTP_200_OK,
        )

    def delete(self, request: Request, pk: str) -> Response:
        offer = self.get_object(pk)
        user = request.user

        if not isinstance(user, User) or not user_can_manage_merchant(user, offer.merchant):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "You do not have permission to delete this offer.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        offer.delete()
        return Response(
            {"success": True, "message": "Offer specification successfully deleted."},
            status=status.HTTP_200_OK,
        )


class OfferCalculateView(APIView):
    """Preview or calculate discounted price for a given base price and offer."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        req_serializer = OfferCalculationRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": req_serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        offer_id = req_serializer.validated_data["offer_id"]
        base_price: Decimal = req_serializer.validated_data["base_price"]

        try:
            offer = OfferSpecification.objects.get(id=offer_id, is_active=True)
        except OfferSpecification.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Active offer specification not found.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        discount_amount, final_price = calculate_discounted_price(base_price, offer)

        savings_percentage = Decimal("0.00")
        if base_price > Decimal("0.00"):
            savings_percentage = ((discount_amount / base_price) * Decimal("100.00")).quantize(
                Decimal("0.01")
            )

        data = {
            "base_price": base_price,
            "discount_amount": discount_amount,
            "final_price": final_price,
            "savings_percentage": savings_percentage,
        }
        res_serializer = OfferCalculationResponseSerializer(data)
        return Response({"success": True, "data": res_serializer.data}, status=status.HTTP_200_OK)
