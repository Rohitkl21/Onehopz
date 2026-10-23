"""Automated tests for user registration, authentication, JWT tokens, and security."""

import uuid
from datetime import timedelta

import jwt
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework import status

from apps.identity.models import RefreshToken, UserRole
from apps.identity.services import AuthService

User = get_user_model()


@pytest.fixture
def api_client() -> Client:
    return Client()


@pytest.fixture
def registered_user(db: None) -> User:
    return User.objects.create_user(
        email="verified@example.com",
        phone_number="+919876543210",
        password="SecurePassword#2026",
        first_name="Arjun",
        last_name="Mehta",
        role=UserRole.CUSTOMER,
    )


@pytest.mark.django_db
def test_valid_registration(api_client: Client) -> None:
    """TC-01: Valid user registration succeeds and returns tokens."""
    payload = {
        "email": "newuser@example.com",
        "phone_number": "+919811122233",
        "password": "StrongPassword#2026",
        "first_name": "Priya",
        "last_name": "Sharma",
    }
    response = api_client.post(
        "/api/v1/auth/register", data=payload, content_type="application/json"
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert data["data"]["user"]["email"] == "newuser@example.com"
    assert "onehopz_refresh_token" in response.cookies


@pytest.mark.django_db
def test_invalid_registration_duplicate_email(api_client: Client, registered_user: User) -> None:
    """TC-02: Registration fails when email already exists."""
    payload = {
        "email": "verified@example.com",
        "phone_number": "+919999988888",
        "password": "StrongPassword#2026",
        "first_name": "Duplicate",
        "last_name": "User",
    }
    response = api_client.post(
        "/api/v1/auth/register", data=payload, content_type="application/json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["success"] is False
    assert "email" in str(data["error"])


@pytest.mark.django_db
def test_invalid_registration_weak_password(api_client: Client) -> None:
    """TC-03: Registration fails when password does not meet complexity/length."""
    payload = {
        "email": "weak@example.com",
        "phone_number": "+919811122234",
        "password": "123",  # Too short
        "first_name": "Weak",
        "last_name": "Password",
    }
    response = api_client.post(
        "/api/v1/auth/register", data=payload, content_type="application/json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["success"] is False
    assert "password" in str(data["error"])


@pytest.mark.django_db
def test_invalid_registration_invalid_phone(api_client: Client) -> None:
    """TC-04: Registration fails when phone number format is invalid."""
    payload = {
        "email": "phone@example.com",
        "phone_number": "invalid-phone",
        "password": "StrongPassword#2026",
        "first_name": "Invalid",
        "last_name": "Phone",
    }
    response = api_client.post(
        "/api/v1/auth/register", data=payload, content_type="application/json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["success"] is False
    assert "phone" in str(data["error"])


@pytest.mark.django_db
def test_password_hashing_and_no_plaintext(registered_user: User) -> None:
    """TC-05: Passwords must be hashed using PBKDF2/Argon2 and never stored as plaintext."""
    assert registered_user.password != "SecurePassword#2026"
    assert registered_user.password.startswith("pbkdf2_") or registered_user.password.startswith(
        "argon2"
    )
    assert registered_user.check_password("SecurePassword#2026") is True
    assert registered_user.check_password("WrongPassword#2026") is False


@pytest.mark.django_db
def test_login_success(api_client: Client, registered_user: User) -> None:
    """TC-06: Login succeeds with correct credentials and returns JWT access token."""
    payload = {
        "email": "verified@example.com",
        "password": "SecurePassword#2026",
    }
    response = api_client.post("/api/v1/auth/login", data=payload, content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "onehopz_refresh_token" in response.cookies


@pytest.mark.django_db
def test_login_failure_safe_error(api_client: Client, registered_user: User) -> None:
    """TC-07: Login failure returns safe, uniform error without leaking account existence."""
    # Case 1: Wrong password for existing user
    resp1 = api_client.post(
        "/api/v1/auth/login",
        data={"email": "verified@example.com", "password": "WrongPassword#999"},
        content_type="application/json",
    )
    # Case 2: Non-existent email
    resp2 = api_client.post(
        "/api/v1/auth/login",
        data={"email": "nonexistent@example.com", "password": "AnyPassword#999"},
        content_type="application/json",
    )

    assert resp1.status_code == status.HTTP_401_UNAUTHORIZED
    assert resp2.status_code == status.HTTP_401_UNAUTHORIZED
    # Safe error messages must be identical
    assert resp1.json()["error"]["message"] == resp2.json()["error"]["message"]


@pytest.mark.django_db
def test_access_token_expiration(registered_user: User) -> None:
    """TC-08: Expired access tokens are rejected."""
    # Craft an expired token directly
    payload = {
        "user_id": str(registered_user.id),
        "email": registered_user.email,
        "role": registered_user.role,
        "is_active": True,
        "exp": timezone.now() - timedelta(minutes=5),
        "iat": timezone.now() - timedelta(minutes=20),
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }
    expired_token = jwt.encode(payload, AuthService.get_signing_key(), algorithm="HS256")

    client = Client()
    response = client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {expired_token}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_token_rotation(api_client: Client, registered_user: User) -> None:
    """TC-09: Refresh token rotation issues a new access token and new single-use refresh token."""
    _, raw_refresh_token = AuthService.issue_refresh_token(registered_user)
    api_client.cookies["onehopz_refresh_token"] = raw_refresh_token

    response = api_client.post("/api/v1/auth/refresh", data={}, content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data["data"]
    assert "onehopz_refresh_token" in response.cookies
    new_raw_token = response.cookies["onehopz_refresh_token"].value
    assert new_raw_token != raw_refresh_token

    # Verify old token is now marked revoked in DB
    old_hash = RefreshToken.hash_token(raw_refresh_token)
    old_record = RefreshToken.objects.get(token_hash=old_hash)
    assert old_record.is_revoked is True
    assert old_record.replaced_by_token is not None


@pytest.mark.django_db
def test_refresh_token_reuse_detection_and_revocation(
    api_client: Client, registered_user: User
) -> None:
    """TC-10: Reusing an already revoked refresh token triggers reuse detection and revokes all active tokens."""
    # Step 1: Issue token A
    _, raw_token_a = AuthService.issue_refresh_token(registered_user)

    # Step 2: Rotate token A -> token B
    api_client.cookies["onehopz_refresh_token"] = raw_token_a
    resp1 = api_client.post("/api/v1/auth/refresh", data={}, content_type="application/json")
    assert resp1.status_code == status.HTTP_200_OK

    # Step 3: Issue another concurrent token C (e.g. from another valid device session)
    _, raw_token_c = AuthService.issue_refresh_token(registered_user)
    assert RefreshToken.objects.filter(user=registered_user, is_revoked=False).count() >= 2

    # Step 4: Attacker replays revoked token A!
    api_client.cookies["onehopz_refresh_token"] = raw_token_a
    replay_resp = api_client.post("/api/v1/auth/refresh", data={}, content_type="application/json")
    assert replay_resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert replay_resp.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    # Step 5: Assert that ALL active refresh tokens for this user have been invalidated
    active_tokens = RefreshToken.objects.filter(user=registered_user, is_revoked=False)
    assert active_tokens.count() == 0


@pytest.mark.django_db
def test_logout_and_refresh_token_invalidation(api_client: Client, registered_user: User) -> None:
    """TC-11: Logout revokes the refresh token and clears the cookie."""
    _, raw_refresh_token = AuthService.issue_refresh_token(registered_user)
    api_client.cookies["onehopz_refresh_token"] = raw_refresh_token

    response = api_client.post("/api/v1/auth/logout", data={}, content_type="application/json")
    assert response.status_code == status.HTTP_200_OK

    # Token must be revoked in DB
    token_hash = RefreshToken.hash_token(raw_refresh_token)
    assert RefreshToken.objects.get(token_hash=token_hash).is_revoked is True


@pytest.mark.django_db
def test_anonymous_access_to_protected_endpoints(api_client: Client) -> None:
    """TC-12: Anonymous requests to protected endpoints return 401 Unauthorized."""
    response = api_client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_privileged_role_registration_blocked(api_client: Client) -> None:
    """TC-13: Public registration with privileged roles (SUPER_ADMIN, FINANCE_ADMIN, etc.) is rejected."""
    for privileged_role in [
        UserRole.SUPER_ADMIN,
        UserRole.FINANCE_ADMIN,
        UserRole.PLATFORM_SUPPORT,
    ]:
        payload = {
            "email": f"attacker_{privileged_role.lower()}@example.com",
            "phone_number": "+919800000001",
            "password": "StrongPassword#2026",
            "first_name": "Bad",
            "last_name": "Actor",
            "role": privileged_role,
        }
        response = api_client.post(
            "/api/v1/auth/register", data=payload, content_type="application/json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Public registration permits only" in str(response.json()["error"])


@pytest.mark.django_db
def test_refresh_token_not_in_json_response(api_client: Client, registered_user: User) -> None:
    """TC-14: Refresh response never exposes raw refresh token in JSON data to browser clients."""
    _, raw_refresh_token = AuthService.issue_refresh_token(registered_user)
    api_client.cookies["onehopz_refresh_token"] = raw_refresh_token

    response = api_client.post("/api/v1/auth/refresh", data={}, content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data["data"]
    # Refresh token must be absent from JSON body for cookie-based clients
    assert "refresh_token" not in data["data"]
    # But present in secure HttpOnly cookie
    assert "onehopz_refresh_token" in response.cookies


@pytest.mark.django_db
def test_csrf_origin_validation_on_cookie_refresh(
    api_client: Client, registered_user: User
) -> None:
    """TC-15: Cross-origin requests with cookie auth but mismatched Origin are rejected."""
    _, raw_refresh_token = AuthService.issue_refresh_token(registered_user)
    api_client.cookies["onehopz_refresh_token"] = raw_refresh_token

    # Malicious external origin attempt
    response = api_client.post(
        "/api/v1/auth/refresh",
        data={},
        content_type="application/json",
        HTTP_ORIGIN="https://evil-attacker.com",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "CSRF_FAILED"


@pytest.mark.django_db
def test_url_trailing_slash_flexibility(registered_user: User) -> None:
    """TC-16: API endpoints accept both trailing slash and non-trailing slash without 301 redirects."""
    client = Client()
    # Without slash
    r1 = client.post(
        "/api/v1/auth/login",
        data={"email": registered_user.email, "password": "SecurePassword#2026"},
        content_type="application/json",
    )
    assert r1.status_code == status.HTTP_200_OK

    # With slash
    r2 = client.post(
        "/api/v1/auth/login/",
        data={"email": registered_user.email, "password": "SecurePassword#2026"},
        content_type="application/json",
    )
    assert r2.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_case_insensitive_email_db_constraint(registered_user: User) -> None:
    """TC-17: Case-insensitive email unique constraint prevents duplicate emails with different casing at DB level."""
    from django.db import IntegrityError

    # Attempt to insert same email in uppercase directly via model
    with pytest.raises(IntegrityError):
        User.objects.create(
            email=registered_user.email.upper(),
            phone_number="+919899999999",
            password="AnyPassword#2026",
            first_name="Duplicate",
            last_name="Case",
            role=UserRole.CUSTOMER,
        )


@pytest.mark.django_db
def test_auth_throttling_on_login(registered_user: User) -> None:
    """TC-18: Rapid consecutive authentication requests trigger DRF rate throttling."""
    from django.core.cache import cache

    cache.clear()
    client = Client()

    # Rate is configured to 10/minute for auth_login
    hit_throttle = False
    for _i in range(15):
        resp = client.post(
            "/api/v1/auth/login",
            data={"email": "throttletest@example.com", "password": "WrongPassword#123"},
            content_type="application/json",
            REMOTE_ADDR="198.51.100.5",
        )
        if resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            hit_throttle = True
            break

    assert hit_throttle is True
    cache.clear()
