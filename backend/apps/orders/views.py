"""REST API views for order checkout and retrieval."""

from uuid import UUID

from django.db import IntegrityError
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.merchants.models import MerchantMembership, OutletStaff

from .exceptions import (
    HoldAlreadyConvertedError,
    HoldExpiredForCheckoutError,
    HoldNotOwnedError,
    IdempotencyConflictError,
    InventoryCutoffExceededError,
    InventoryReservationUnavailableError,
    OrderNotFoundError,
    UnsupportedCheckoutCategoryError,
)
from .models import Order
from .serializers import CheckoutRequestSerializer, OrderDetailSerializer
from .services import checkout


class OrderCheckoutView(APIView):
    """
    POST /api/v1/orders/checkout
    Convert an active hold into an order and establish a durable reservation.
    """

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

        idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "MISSING_IDEMPOTENCY_KEY",
                        "message": "Idempotency-Key header is required for checkout.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CheckoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid checkout payload.",
                        "details": serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        hold_id = serializer.validated_data["hold_id"]
        customer_contact = serializer.validated_data.get("customer_contact", {})

        try:
            order, is_created = checkout(
                customer=customer,
                hold_id=hold_id,
                customer_contact=customer_contact,
                idempotency_key=str(idempotency_key).strip(),
            )
        except HoldExpiredForCheckoutError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_409_CONFLICT,
            )
        except HoldNotOwnedError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_403_FORBIDDEN,
            )
        except HoldAlreadyConvertedError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_409_CONFLICT,
            )
        except InventoryReservationUnavailableError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_409_CONFLICT,
            )
        except IdempotencyConflictError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_409_CONFLICT,
            )
        except InventoryCutoffExceededError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_409_CONFLICT,
            )
        except OrderNotFoundError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except UnsupportedCheckoutCategoryError as exc:
            return Response(
                {"success": False, "error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            # Concurrency race on customer idempotency key
            try:
                order, is_created = checkout(
                    customer=customer,
                    hold_id=hold_id,
                    customer_contact=customer_contact,
                    idempotency_key=str(idempotency_key).strip(),
                )
            except Exception:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "CONCURRENCY_CONFLICT",
                            "message": "Checkout is currently processing. Please retry.",
                        },
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        response_status = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
        data = OrderDetailSerializer(order).data
        return Response({"success": True, "data": data}, status=response_status)


class OrderDetailView(APIView):
    """
    GET /api/v1/orders/{order_id}
    Retrieve order details with strict tenant and RBAC scoping.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, order_id: UUID) -> Response:
        order = (
            Order.objects.filter(id=order_id)
            .select_related("merchant", "outlet")
            .prefetch_related("items")
            .first()
        )
        if not order:
            return Response(
                {"success": False, "error": {"code": "ORDER_NOT_FOUND", "message": "Order not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Scoping check
        user = request.user
        if not user.is_authenticated or not isinstance(user, User):
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

        is_owner = order.customer_id == user.id
        is_admin = getattr(user, "is_platform_admin", False) or getattr(user, "is_staff", False)

        is_merchant_authorized = False
        if not is_owner and not is_admin:
            # Check outlet staff or merchant membership
            is_merchant_authorized = (
                OutletStaff.objects.filter(
                    outlet=order.outlet,
                    user=user,
                    is_active=True,
                ).exists()
                or MerchantMembership.objects.filter(
                    merchant=order.merchant,
                    user=user,
                    is_active=True,
                ).exists()
            )

        if not (is_owner or is_admin or is_merchant_authorized):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "ORDER_PERMISSION_DENIED",
                        "message": "You do not have permission to view this order.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        data = OrderDetailSerializer(order).data
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)
