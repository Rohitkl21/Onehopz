"""URL configuration for OneHopz backend project."""

from django.urls import include, path

urlpatterns = [
    # Health and readiness endpoints
    path("api/health/", include("apps.core.urls")),
    # Version 1 Core APIs
    path("api/v1/auth/", include("apps.identity.urls", namespace="identity")),
    path("api/v1/merchants/", include("apps.merchants.urls", namespace="merchants")),
    path("api/v1/outlets/", include("apps.merchants.outlet_urls")),
]
