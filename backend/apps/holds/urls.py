"""URL routing for ephemeral hold endpoints."""

from django.urls import path

from .views import HoldAcquireView, HoldDetailView

app_name = "holds"

urlpatterns = [
    # Acquire endpoints (both /acquire and root / for client flexibility)
    path("acquire", HoldAcquireView.as_view(), name="acquire"),
    path("", HoldAcquireView.as_view(), name="create"),
    # Retrieve & Release endpoints
    path("<uuid:hold_id>/", HoldDetailView.as_view(), name="detail"),
    path("<uuid:hold_id>/release/", HoldDetailView.as_view(), name="release"),
]
