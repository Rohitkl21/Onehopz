"""URL routing for Merchants, Outlets, and Staff management."""

from django.urls import path

from .views import (
    MerchantDetailView,
    MerchantListCreateView,
    MerchantMembershipListCreateView,
    MerchantOutletListCreateView,
)

app_name = "merchants"

urlpatterns = [
    # Merchants
    path("", MerchantListCreateView.as_view(), name="merchant-list-create"),
    path("<uuid:pk>", MerchantDetailView.as_view(), name="merchant-detail"),
    path(
        "<uuid:merchant_id>/members",
        MerchantMembershipListCreateView.as_view(),
        name="merchant-members",
    ),
    path(
        "<uuid:merchant_id>/outlets",
        MerchantOutletListCreateView.as_view(),
        name="merchant-outlets",
    ),
]
