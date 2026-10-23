"""API Views for identity, authentication, session tokens, and user profiles."""

from urllib.parse import urlparse

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
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


def delete_refresh_cookie(response: Response) -> None:
    """Clear refresh cookie with matching path and security attributes."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api/v1/auth/",
        samesite="Strict",
    )


def validate_origin(request: Request) -> bool:
    """
    Validate Origin or Referer header for cookie-authenticated requests.
    Mitigates CSRF against browser-held cookies.
    """
    origin = request.headers.get("Origin")
    if not origin:
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"

    if not origin:
        # Non-browser or direct API clients without Origin header are permitted
        return True

    allowed_origins = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    host = request.get_host().split(":")[0]
    allowed_origins.add(f"http://{host}")
    allowed_origins.add(f"https://{host}")
    allowed_origins.add(f"http://{request.get_host()}")
    allowed_origins.add(f"https://{request.get_host()}")
    allowed_origins.add("http://testserver")

    return origin in allowed_origins


class RegistrationView(APIView):
    """
    Public registration endpoint.
    Creates new customer or merchant owner accounts and returns auth tokens.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"

    def post(self, request: Request) -> Response:
        from_cookie = COOKIE_NAME in request.COOKIES
        raw_token = request.COOKIES.get(COOKIE_NAME)

        # Validate origin for cookie-authenticated browser requests (CSRF mitigation)
        if from_cookie and not validate_origin(request):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "CSRF_FAILED",
                        "message": "Cross-origin request rejected for cookie-based authentication.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

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
            delete_refresh_cookie(response)
            return response
        except ExpiredTokenError as e:
            response = Response(
                {"success": False, "error": {"code": "REFRESH_TOKEN_EXPIRED", "message": str(e)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            delete_refresh_cookie(response)
            return response
        except InvalidTokenError as e:
            return Response(
                {"success": False, "error": {"code": "INVALID_REFRESH_TOKEN", "message": str(e)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response_data = {
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in_seconds": int(AuthService.ACCESS_TOKEN_LIFETIME.total_seconds()),
        }
        # Only return refresh_token in response body if request did NOT use cookies (e.g. native/mobile client)
        if not from_cookie:
            response_data["refresh_token"] = new_raw_token

        response = Response(
            {
                "success": True,
                "data": response_data,
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
        from_cookie = COOKIE_NAME in request.COOKIES
        if from_cookie and not validate_origin(request):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "CSRF_FAILED",
                        "message": "Cross-origin request rejected for cookie-based authentication.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_token = request.COOKIES.get(COOKIE_NAME)
        if not raw_token and isinstance(request.data, dict):
            raw_token = request.data.get("refresh_token")

        if raw_token:
            AuthService.revoke_refresh_token(raw_token)

        response = Response(
            {"success": True, "data": {"message": "Logged out successfully."}},
            status=status.HTTP_200_OK,
        )
        delete_refresh_cookie(response)
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
