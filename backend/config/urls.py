"""URL configuration for OneHopz backend project."""

from django.urls import include, path

urlpatterns = [
    # Health and readiness endpoints
    path("api/health/", include("apps.core.urls")),
    # Future versioned APIs will be routed under /api/v1/
]
