"""Direct outlet routes."""

from django.urls import re_path

from .views import (
    OutletDetailView,
    OutletStaffDetailView,
    OutletStaffListCreateView,
)

urlpatterns = [
    re_path(r"^(?P<pk>[0-9a-f-]+)/?$", OutletDetailView.as_view(), name="outlet-detail"),
    re_path(
        r"^(?P<pk>[0-9a-f-]+)/staff/?$",
        OutletStaffListCreateView.as_view(),
        name="outlet-staff-list-create",
    ),
    re_path(
        r"^(?P<pk>[0-9a-f-]+)/staff/(?P<user_id>[0-9a-f-]+)/?$",
        OutletStaffDetailView.as_view(),
        name="outlet-staff-detail",
    ),
]
