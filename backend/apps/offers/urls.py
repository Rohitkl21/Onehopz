"""URL routing for Offers and Dynamic Yield domain."""

from django.urls import re_path

from .views import OfferCalculateView, OfferDetailView, OfferListCreateView

app_name = "offers"

urlpatterns = [
    re_path(r"^/?$", OfferListCreateView.as_view(), name="offer-list-create"),
    re_path(r"^calculate/?$", OfferCalculateView.as_view(), name="offer-calculate"),
    re_path(r"^(?P<pk>[0-9a-f-]+)/?$", OfferDetailView.as_view(), name="offer-detail"),
]
