"""Health check and readiness endpoints for OneHopz."""

from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """
    Application health and readiness check endpoint.
    Verifies service status without leaking credentials or environment secrets.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request: Request) -> Response:
        now_utc = datetime.now(UTC).isoformat()

        # Test database connectivity safely
        db_status = "unconfigured"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row and row[0] == 1:
                    db_status = "healthy"
        except Exception:
            db_status = "disconnected"

        # Check Celery broker reachability safely
        broker_status = "unconfigured"
        try:
            from config.celery import app as celery_app

            conn = celery_app.connection()
            conn.connect()
            broker_status = "healthy"
            conn.release()
        except Exception:
            broker_status = "unavailable"

        payload: dict[str, Any] = {
            "status": "ok",
            "service": "onehopz-backend",
            "environment": getattr(settings, "ONEHOPZ_ENV", "development"),
            "timestamp": now_utc,
            "components": {
                "database": db_status,
                "celery_broker": broker_status,
            },
        }

        return Response(payload, status=status.HTTP_200_OK)
