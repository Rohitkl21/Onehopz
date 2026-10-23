"""Tests for the application readiness health check endpoint."""

from django.test import Client
from rest_framework import status


def test_health_check_endpoint() -> None:
    """Verify that the health check returns 200 OK and expected structure."""
    client = Client()
    response = client.get("/api/health/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "onehopz-backend"
    assert "environment" in data
    assert "timestamp" in data
    assert "components" in data
    assert "database" in data["components"]
    assert "celery_broker" in data["components"]

    # Ensure no secrets or sensitive settings are exposed
    assert "SECRET_KEY" not in str(data)
    assert "password" not in str(data).lower()
