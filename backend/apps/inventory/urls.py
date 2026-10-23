"""URL routing for Inventory domain."""

from django.urls import re_path

from .views import AvailabilityCheckView, InventoryCapabilitiesView

app_name = "inventory"

urlpatterns = [
    re_path(r"^availability/?$", AvailabilityCheckView.as_view(), name="inventory-availability"),
    re_path(
        r"^capabilities/?$", InventoryCapabilitiesView.as_view(), name="inventory-capabilities"
    ),
]
