"""API Views for identity, authentication, session tokens, and user profiles."""

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import (
    RefreshTokenRequestSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
)
from .services import AuthService, ExpiredTokenError, InvalidTokenError, TokenReuseError

COOKIE_NAME = "onehopz_refresh_token"


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Set secure HttpOnly refresh cookie."""
    is_secure = not getattr(settings, "DEBUG", True)
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        max_age=int(AuthService.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=is_secure,
        samesite="Strict",
        path="/api/v1/auth/",
    )


class RegistrationView(APIView):
    """
    Public registration endpoint.
    Creates new customer or merchant owner accounts and returns auth tokens.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": "VALIDATION_ERROR", "details": serializer.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user: User = serializer.save()
        access_token = AuthService.create_access_token(user)
        _, raw_refresh_token = AuthService.issue_refresh_token(user)

        response = Response(
            {
                "success": True,
                "data": {
                    "user": UserProfileSerializer(user).data,
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in_seconds": int(AuthService.ACCESS_TOKEN_LIFETIME.total_seconds()),
                },
            },
            status=status.HTTP_201_CREATED,
        )
        set_refresh_cookie(response, raw_refresh_token)
        return response


class LoginView(APIView):
    """
    User login endpoint.
    Verifies credentials and issues short-lived access token + HttpOnly refresh cookie.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        serializer = UserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_CREDENTIALS",
                        "message": "Invalid email or password.",
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user: User = serializer.validated_data["user"]
        access_token = AuthService.create_access_token(user)
        _, raw_refresh_token = AuthService.issue_refresh_token(user)

        response = Response(
            {
                "success": True,
                "data": {
                    "user": UserProfileSerializer(user).data,
                    "access_token": access_token,
                    "token_type": "Bearer",
                    "expires_in_seconds": int(AuthService.ACCESS_TOKEN_LIFETIME.total_seconds()),
                },
            },
            status=status.HTTP_200_OK,
        )
        set_refresh_cookie(response, raw_refresh_token)
        return response


class TokenRefreshView(APIView):
    """
    Refresh access token using single-use rotating refresh token.
    Reads from HttpOnly cookie or request body. Enforces replay detection.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if not raw_token:
            serializer = RefreshTokenRequestSerializer(data=request.data)
            if serializer.is_valid():
                raw_token = serializer.validated_data.get("refresh_token")

        if not raw_token:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "REFRESH_TOKEN_REQUIRED",
                        "message": "Refresh token is missing.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_access_token, new_raw_token, user = AuthService.rotate_refresh_token(raw_token)
        except TokenReuseError as e:
            response = Response(
                {"success": False, "error": {"code": "REFRESH_TOKEN_REUSED", "message": str(e)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(COOKIE_NAME, path="/api/v1/auth/")
            return response
        except ExpiredTokenError as e:
            response = Response(
                {"success": False, "error": {"code": "REFRESH_TOKEN_EXPIRED", "message": str(e)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(COOKIE_NAME, path="/api/v1/auth/")
            return response
        except InvalidTokenError as e:
            return Response(
                {"success": False, "error": {"code": "INVALID_REFRESH_TOKEN", "message": str(e)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response = Response(
            {
                "success": True,
                "data": {
                    "access_token": new_access_token,
                    "token_type": "Bearer",
                    "expires_in_seconds": int(AuthService.ACCESS_TOKEN_LIFETIME.total_seconds()),
                    "refresh_token": new_raw_token,
                },
            },
            status=status.HTTP_200_OK,
        )
        set_refresh_cookie(response, new_raw_token)
        return response


class LogoutView(APIView):
    """
    User logout endpoint.
    Revokes the refresh token and clears the HttpOnly cookie.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        raw_token = request.COOKIES.get(COOKIE_NAME)
        if not raw_token and isinstance(request.data, dict):
            raw_token = request.data.get("refresh_token")

        if raw_token:
            AuthService.revoke_refresh_token(raw_token)

        response = Response(
            {"success": True, "data": {"message": "Logged out successfully."}},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie(COOKIE_NAME, path="/api/v1/auth/")
        return response


class CurrentUserProfileView(APIView):
    """
    Current user profile endpoint.
    Requires valid JWT authentication.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if not isinstance(user, User):
            return Response(
                {
                    "success": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        serializer = UserProfileSerializer(user)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)
