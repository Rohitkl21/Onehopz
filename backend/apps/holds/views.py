"""Views for ephemeral hold lifecycle management."""

from uuid import UUID

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.offers.models import OfferSpecification

from .exceptions import (
    HoldDomainError,
    HoldExpiredError,
    HoldNotFoundError,
    HoldPermissionDeniedError,
    HoldStateError,
    IdempotencyConflictError,
    InsufficientInventoryError,
    InventoryAlreadyLockedError,
    UnsupportedInventoryCategoryError,
)
from .serializers import HoldAcquireSerializer, HoldDetailSerializer
from .services import acquire_hold, get_hold_detail, release_hold


class HoldAcquireView(APIView):
    """Acquire an ephemeral reservation hold backed by PostgreSQL ACID locks."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        customer = request.user
        if not customer.is_authenticated or not isinstance(customer, User):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication credentials were not provided.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data_dict = request.data if isinstance(request.data, dict) else {}
        idempotency_key = (
            request.headers.get("Idempotency-Key")
            or request.headers.get("X-Idempotency-Key")
            or data_dict.get("idempotency_key")
        )

        if not idempotency_key:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "MISSING_IDEMPOTENCY_KEY",
                        "message": "Idempotency-Key header is required for acquiring a hold.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HoldAcquireSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid hold acquisition parameters.",
                        "details": serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated_data = serializer.validated_data
        catalog_item = validated_data["catalog_item"]
        category = validated_data["category"]
        selection_parameters = validated_data["selection_parameters"]
        quantity = validated_data["quantity"]
        offer_id = validated_data.get("offer_id")

        offer = None
        if offer_id:
            try:
                offer = OfferSpecification.objects.get(id=offer_id, is_active=True)
            except OfferSpecification.DoesNotExist:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "OFFER_NOT_FOUND",
                            "message": "Specified offer does not exist or is inactive.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            hold, is_created = acquire_hold(
                customer=customer,
                catalog_item=catalog_item,
                category=category,
                selection_parameters=selection_parameters,
                quantity=quantity,
                idempotency_key=str(idempotency_key),
                offer=offer,
            )
            response_status = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
            return Response(
                {
                    "success": True,
                    "data": HoldDetailSerializer(hold).data,
                },
                status=response_status,
            )

        except InventoryAlreadyLockedError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except InsufficientInventoryError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except IdempotencyConflictError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        except HoldExpiredError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_410_GONE,
            )
        except UnsupportedInventoryCategoryError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except HoldDomainError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class HoldDetailView(APIView):
    """Retrieve details of an authoritative hold."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, hold_id: UUID) -> Response:
        customer = request.user
        if not customer.is_authenticated or not isinstance(customer, User):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication credentials were not provided.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            hold = get_hold_detail(hold_id=hold_id, customer=customer)
            return Response(
                {
                    "success": True,
                    "data": HoldDetailSerializer(hold).data,
                },
                status=status.HTTP_200_OK,
            )
        except HoldNotFoundError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "HOLD_NOT_FOUND",
                        "message": "Hold does not exist.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except HoldPermissionDeniedError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "You do not have permission to view this hold.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    def delete(self, request: Request, hold_id: UUID) -> Response:
        """Release the hold (DELETE method)."""
        return self._do_release(request, hold_id)

    def post(self, request: Request, hold_id: UUID) -> Response:
        """Release the hold (POST release method alias)."""
        return self._do_release(request, hold_id)

    def _do_release(self, request: Request, hold_id: UUID) -> Response:
        customer = request.user
        if not customer.is_authenticated or not isinstance(customer, User):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication credentials were not provided.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            hold = release_hold(hold_id=hold_id, customer=customer)
            return Response(
                {
                    "success": True,
                    "data": {
                        "hold_id": str(hold.id),
                        "status": hold.status,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except HoldNotFoundError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "HOLD_NOT_FOUND",
                        "message": "Hold does not exist.",
                    },
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except HoldPermissionDeniedError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "You do not have permission to release this hold.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except HoldStateError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
