"""Identity and authentication routes."""

from django.urls import path

from .views import (
    CurrentUserProfileView,
    LoginView,
    LogoutView,
    RegistrationView,
    TokenRefreshView,
)

app_name = "identity"

urlpatterns = [
    path("register", RegistrationView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("refresh", TokenRefreshView.as_view(), name="refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", CurrentUserProfileView.as_view(), name="me"),
]
