"""URL routing for Merchants, Outlets, and Staff management."""

from django.urls import re_path

from .views import (
    MerchantDetailView,
    MerchantListCreateView,
    MerchantMembershipListCreateView,
    MerchantOutletListCreateView,
)

app_name = "merchants"

urlpatterns = [
    # Merchants
    re_path(r"^/?$", MerchantListCreateView.as_view(), name="merchant-list-create"),
    re_path(r"^(?P<pk>[0-9a-f-]+)/?$", MerchantDetailView.as_view(), name="merchant-detail"),
    re_path(
        r"^(?P<merchant_id>[0-9a-f-]+)/members/?$",
        MerchantMembershipListCreateView.as_view(),
        name="merchant-members",
    ),
    re_path(
        r"^(?P<merchant_id>[0-9a-f-]+)/outlets/?$",
        MerchantOutletListCreateView.as_view(),
        name="merchant-outlets",
    ),
]
