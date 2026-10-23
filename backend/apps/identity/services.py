"""Authentication, JWT token issuance, rotation, and revocation services."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from django.conf import settings
from django.utils import timezone as django_timezone

from .models import RefreshToken, User


class TokenError(Exception):
    """Base class for token-related errors."""

    pass


class InvalidTokenError(TokenError):
    pass


class ExpiredTokenError(TokenError):
    pass


class TokenReuseError(TokenError):
    """Raised when an already revoked refresh token is presented."""

    pass


class AuthService:
    """Core identity service handling JWTs and secure refresh token lifecycles."""

    ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
    REFRESH_TOKEN_LIFETIME = timedelta(days=30)
    ALGORITHM = "HS256"

    @classmethod
    def get_signing_key(cls) -> str:
        return getattr(settings, "SECRET_KEY", "fallback-insecure-dev-key")

    @classmethod
    def create_access_token(cls, user: User) -> str:
        """Create a short-lived JWT access token."""
        now = datetime.now(UTC)
        payload = {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "exp": now + cls.ACCESS_TOKEN_LIFETIME,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "token_type": "access",
        }
        return jwt.encode(payload, cls.get_signing_key(), algorithm=cls.ALGORITHM)

    @classmethod
    def decode_access_token(cls, token: str) -> dict[str, Any]:
        """Decode and cryptographically verify an access token."""
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                cls.get_signing_key(),
                algorithms=[cls.ALGORITHM],
                options={"require": ["exp", "iat", "user_id", "token_type"]},
            )
            if payload.get("token_type") != "access":
                raise InvalidTokenError("Invalid token type")
            return payload
        except jwt.ExpiredSignatureError as e:
            raise ExpiredTokenError("Access token has expired") from e
        except jwt.PyJWTError as e:
            raise InvalidTokenError("Invalid access token") from e

    @classmethod
    def issue_refresh_token(cls, user: User) -> tuple[RefreshToken, str]:
        """
        Generate a cryptographically secure random refresh token.
        Persist only its SHA-256 hash in the database.
        """
        raw_secret = secrets.token_urlsafe(64)
        token_hash = RefreshToken.hash_token(raw_secret)
        expires_at = django_timezone.now() + cls.REFRESH_TOKEN_LIFETIME

        refresh_token = RefreshToken.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return refresh_token, raw_secret

    @classmethod
    def rotate_refresh_token(cls, raw_refresh_token: str) -> tuple[str, str, User]:
        """
        Verify a raw refresh token, rotate it single-use, detect replay/reuse,
        and return (new_access_token, new_raw_refresh_token, user).
        """
        token_hash = RefreshToken.hash_token(raw_refresh_token)
        token_record = (
            RefreshToken.objects.select_related("user").filter(token_hash=token_hash).first()
        )

        if not token_record:
            raise InvalidTokenError("Invalid refresh token")

        # Reuse Detection: If this token was already revoked, a replay attack is occurring!
        if token_record.is_revoked:
            # Revoke ALL existing active refresh tokens for this user immediately
            RefreshToken.objects.filter(user=token_record.user, is_revoked=False).update(
                is_revoked=True,
                revoked_at=django_timezone.now(),
            )
            raise TokenReuseError(
                "Refresh token reuse detected. All active sessions have been invalidated."
            )

        # Expiry Check
        if token_record.expires_at < django_timezone.now():
            token_record.is_revoked = True
            token_record.revoked_at = django_timezone.now()
            token_record.save(update_fields=["is_revoked", "revoked_at"])
            raise ExpiredTokenError("Refresh token has expired")

        user = token_record.user
        if not user.is_active:
            raise InvalidTokenError("User account is inactive")

        # Mark current token revoked as part of rotation
        token_record.is_revoked = True
        token_record.revoked_at = django_timezone.now()

        # Generate new replacement refresh token
        new_record, new_raw_token = cls.issue_refresh_token(user)
        token_record.replaced_by_token = new_record
        token_record.save(update_fields=["is_revoked", "revoked_at", "replaced_by_token"])

        # Generate new access token
        new_access_token = cls.create_access_token(user)

        return new_access_token, new_raw_token, user

    @classmethod
    def revoke_refresh_token(cls, raw_refresh_token: str) -> bool:
        """Revoke a refresh token on logout."""
        token_hash = RefreshToken.hash_token(raw_refresh_token)
        token_record = RefreshToken.objects.filter(token_hash=token_hash, is_revoked=False).first()
        if token_record:
            token_record.is_revoked = True
            token_record.revoked_at = django_timezone.now()
            token_record.save(update_fields=["is_revoked", "revoked_at"])
            return True
        return False
