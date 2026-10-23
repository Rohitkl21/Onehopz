"""URL configuration for the Orders application."""

from django.urls import path

from .views import OrderCheckoutView, OrderDetailView

app_name = "orders"

urlpatterns = [
    path("checkout", OrderCheckoutView.as_view(), name="order-checkout"),
    path("checkout/", OrderCheckoutView.as_view(), name="order-checkout-slash"),
    path("<uuid:order_id>", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:order_id>/", OrderDetailView.as_view(), name="order-detail-slash"),
]
