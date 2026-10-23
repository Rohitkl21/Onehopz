"""Views for checking inventory availability and vertical capabilities."""

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .registry import InventoryRegistry
from .serializers import AvailabilityQuerySerializer, AvailabilityResultSerializer


class AvailabilityCheckView(APIView):
    """
    Polymorphic endpoint to evaluate inventory availability across all 7 verticals.
    Dispatches to appropriate domain adapter without creating transactional locks.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = AvailabilityQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid availability query parameters.",
                        "details": serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = serializer.to_domain_query()

        try:
            adapter = InventoryRegistry.get_adapter(query.category)
        except KeyError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "UNSUPPORTED_CATEGORY",
                        "message": f"No inventory adapter registered for category '{query.category}'.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = adapter.check_availability(query)
        result_serializer = AvailabilityResultSerializer(result.to_dict())

        return Response(
            {
                "success": True,
                "data": result_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class InventoryCapabilitiesView(APIView):
    """Retrieve operational capabilities and allocation models for all inventory verticals."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response:
        capabilities = InventoryRegistry.get_all_capabilities()
        return Response(
            {
                "success": True,
                "data": capabilities,
            },
            status=status.HTTP_200_OK,
        )
