"""Identity and authentication routes."""

from django.urls import re_path

from .views import (
    CurrentUserProfileView,
    LoginView,
    LogoutView,
    RegistrationView,
    TokenRefreshView,
)

app_name = "identity"

urlpatterns = [
    re_path(r"^register/?$", RegistrationView.as_view(), name="register"),
    re_path(r"^login/?$", LoginView.as_view(), name="login"),
    re_path(r"^refresh/?$", TokenRefreshView.as_view(), name="refresh"),
    re_path(r"^logout/?$", LogoutView.as_view(), name="logout"),
    re_path(r"^me/?$", CurrentUserProfileView.as_view(), name="me"),
]
