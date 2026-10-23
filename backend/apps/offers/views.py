"""Views for Offer specifications, tenant isolation, and authoritative dynamic pricing calculations."""

from decimal import Decimal
from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import CatalogItem
from apps.identity.models import User
from apps.merchants.models import Merchant, MerchantMembership
from apps.merchants.views import user_can_manage_merchant, user_can_view_merchant

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
    or create a new offer specification under an authorized merchant organization.
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
                            "message": "Public users and unauthorized members cannot query inactive offer specifications.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            queryset = queryset.filter(is_active=True)
        else:
            if is_active_filter is not None:
                queryset = queryset.filter(is_active=is_active_filter)

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
    """Retrieve, update, or deactivate an offer specification with tenant verification."""

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
        user = request.user

        if not offer.is_active and (
            not isinstance(user, User)
            or not user.is_authenticated
            or not user_can_view_merchant(user, offer.merchant)
        ):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Offer specification not found or inactive.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

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
        """Logically deactivate the offer specification to preserve historical integrity."""
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

        offer.is_active = False
        offer.save(update_fields=["is_active", "updated_at"])
        return Response(
            {
                "success": True,
                "message": "Offer specification successfully deactivated.",
                "data": OfferSpecificationSerializer(offer).data,
            },
            status=status.HTTP_200_OK,
        )


class OfferCalculateView(APIView):
    """
    Public price-preview endpoint calculating authoritative offer discounts.
    Enforces validity windows, bound catalog-item price integrity, and floor price tracking.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        req_serializer = OfferCalculationRequestSerializer(data=request.data)
        if not req_serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "details": req_serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        offer_id = req_serializer.validated_data["offer_id"]
        catalog_item_id = req_serializer.validated_data.get("catalog_item_id")
        provided_base_price: Decimal | None = req_serializer.validated_data.get("base_price")

        try:
            offer = OfferSpecification.objects.select_related(
                "merchant", "outlet", "catalog_item"
            ).get(id=offer_id)
        except OfferSpecification.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Offer specification not found.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        now = timezone.now()
        if not offer.is_active:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "OFFER_INACTIVE",
                        "message": "The requested offer is not currently active.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if now < offer.valid_from or now > offer.valid_to:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "OFFER_EXPIRED",
                        "message": "The requested offer is not valid at the current time.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Authoritative resolution of base price and currency
        authoritative_price: Decimal
        currency: str
        resolved_item_id: UUID | None = None

        if offer.catalog_item is not None:
            item = offer.catalog_item
            if not item.is_active:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "ITEM_INACTIVE",
                            "message": "The catalog item bound to this offer is not active.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if catalog_item_id and catalog_item_id != item.id:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "ITEM_OFFER_MISMATCH",
                            "message": "Supplied catalog_item_id does not match the item bound to this offer.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if provided_base_price is not None and provided_base_price != item.base_price:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "PRICE_MISMATCH",
                            "message": (
                                f"Provided base price ({provided_base_price}) contradicts the "
                                f"authoritative catalog item base price ({item.base_price})."
                            ),
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            authoritative_price = item.base_price
            currency = item.currency
            resolved_item_id = item.id
        else:
            # Unbound offer (merchant or outlet level)
            if catalog_item_id:
                try:
                    item = CatalogItem.objects.get(
                        id=catalog_item_id, merchant_id=offer.merchant_id
                    )
                except CatalogItem.DoesNotExist:
                    return Response(
                        {
                            "success": False,
                            "error": {
                                "code": "NOT_FOUND",
                                "message": "Catalog item not found or does not belong to the offer's merchant organization.",
                            },
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if not item.is_active:
                    return Response(
                        {
                            "success": False,
                            "error": {
                                "code": "ITEM_INACTIVE",
                                "message": "The specified catalog item is not active.",
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if provided_base_price is not None and provided_base_price != item.base_price:
                    return Response(
                        {
                            "success": False,
                            "error": {
                                "code": "PRICE_MISMATCH",
                                "message": (
                                    f"Provided base price ({provided_base_price}) contradicts the "
                                    f"item base price ({item.base_price})."
                                ),
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                authoritative_price = item.base_price
                currency = item.currency
                resolved_item_id = item.id
            elif provided_base_price is not None:
                authoritative_price = provided_base_price
                currency = offer.currency
            else:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Either catalog_item_id or base_price must be provided for un-bound offers.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = calculate_discounted_price(authoritative_price, offer, currency=currency)
        except ValueError as err:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "CURRENCY_MISMATCH",
                        "message": str(err),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_data = {
            "offer_id": offer.id,
            "catalog_item_id": resolved_item_id,
            **result.to_dict(),
        }
        res_serializer = OfferCalculationResponseSerializer(response_data)
        return Response({"success": True, "data": res_serializer.data}, status=status.HTTP_200_OK)
