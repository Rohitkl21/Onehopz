"""Direct outlet routes."""

from django.urls import path

from .views import (
    OutletDetailView,
    OutletStaffDetailView,
    OutletStaffListCreateView,
)

urlpatterns = [
    path("<uuid:pk>", OutletDetailView.as_view(), name="outlet-detail"),
    path("<uuid:pk>/staff", OutletStaffListCreateView.as_view(), name="outlet-staff-list-create"),
    path(
        "<uuid:pk>/staff/<uuid:user_id>",
        OutletStaffDetailView.as_view(),
        name="outlet-staff-detail",
    ),
]
