"""DRF Authentication backend for JWT Bearer tokens."""

from rest_framework import authentication, exceptions
from rest_framework.request import Request

from .models import User
from .services import AuthService, ExpiredTokenError, InvalidTokenError


class JSONWebTokenAuthentication(authentication.BaseAuthentication):
    """
    Stateless JWT Bearer token authentication.
    Header format: `Authorization: Bearer <token>`
    """

    keyword = "Bearer"

    def authenticate_header(self, request: Request) -> str:
        return self.keyword

    def authenticate(self, request: Request) -> tuple[User, None] | None:
        auth_header = authentication.get_authorization_header(request).split()

        if not auth_header:
            return None

        if auth_header[0].decode().lower() != self.keyword.lower():
            return None

        if len(auth_header) == 1:
            raise exceptions.AuthenticationFailed("Invalid Bearer header: token missing.")
        elif len(auth_header) > 2:
            raise exceptions.AuthenticationFailed("Invalid Bearer header: token contains spaces.")

        token = auth_header[1].decode()

        try:
            payload = AuthService.decode_access_token(token)
        except ExpiredTokenError as exc:
            raise exceptions.AuthenticationFailed("Access token has expired.") from exc
        except InvalidTokenError as exc:
            raise exceptions.AuthenticationFailed("Invalid access token.") from exc

        user_id = payload.get("user_id")
        if not user_id:
            raise exceptions.AuthenticationFailed("Token missing user identifier.")

        user = User.objects.filter(id=user_id).first()
        if not user or not user.is_active:
            raise exceptions.AuthenticationFailed("User not found or inactive.")

        return user, None
