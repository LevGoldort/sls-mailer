"""Unit tests for JWT authentication module"""
import os
import time
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ставим JWT_SECRET до импорта модуля
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests"

from utils.auth_jwt import (
    generate_access_token,
    generate_refresh_token,
    validate_token,
    decode_access_token,
    decode_refresh_token,
    TokenExpiredError,
    TokenInvalidError,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def access_token():
    return generate_access_token(
        user_id="user-123",
        tenant_id="yallabalagan",
        email="admin@yallabalagan.org",
        role="admin",
    )


@pytest.fixture
def refresh_token():
    return generate_refresh_token(
        user_id="user-123",
        tenant_id="yallabalagan",
    )


# ---------------------------------------------------------------------------
# generate_access_token
# ---------------------------------------------------------------------------

class TestGenerateAccessToken:
    def test_returns_string(self, access_token):
        assert isinstance(access_token, str)

    def test_has_three_jwt_parts(self, access_token):
        assert len(access_token.split(".")) == 3

    def test_payload_sub(self, access_token):
        payload = decode_access_token(access_token)
        assert payload["sub"] == "user-123"

    def test_payload_tenant_id(self, access_token):
        payload = decode_access_token(access_token)
        assert payload["tenant_id"] == "yallabalagan"

    def test_payload_email(self, access_token):
        payload = decode_access_token(access_token)
        assert payload["email"] == "admin@yallabalagan.org"

    def test_payload_role(self, access_token):
        payload = decode_access_token(access_token)
        assert payload["role"] == "admin"

    def test_payload_type_is_access(self, access_token):
        payload = decode_access_token(access_token)
        assert payload["type"] == "access"

    def test_payload_has_exp(self, access_token):
        payload = decode_access_token(access_token)
        assert "exp" in payload

    def test_payload_has_iat(self, access_token):
        payload = decode_access_token(access_token)
        assert "iat" in payload

    def test_expiry_is_15_minutes(self, access_token):
        payload = decode_access_token(access_token)
        delta = payload["exp"] - payload["iat"]
        assert delta == ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_organizer_role(self):
        token = generate_access_token("u1", "yallabalagan", "org@test.com", "organizer")
        payload = decode_access_token(token)
        assert payload["role"] == "organizer"

    def test_different_tokens_for_different_users(self):
        t1 = generate_access_token("u1", "yallabalagan", "a@test.com", "admin")
        t2 = generate_access_token("u2", "yallabalagan", "b@test.com", "admin")
        assert t1 != t2


# ---------------------------------------------------------------------------
# generate_refresh_token
# ---------------------------------------------------------------------------

class TestGenerateRefreshToken:
    def test_returns_string(self, refresh_token):
        assert isinstance(refresh_token, str)

    def test_payload_sub(self, refresh_token):
        payload = decode_refresh_token(refresh_token)
        assert payload["sub"] == "user-123"

    def test_payload_tenant_id(self, refresh_token):
        payload = decode_refresh_token(refresh_token)
        assert payload["tenant_id"] == "yallabalagan"

    def test_payload_type_is_refresh(self, refresh_token):
        payload = decode_refresh_token(refresh_token)
        assert payload["type"] == "refresh"

    def test_payload_has_jti(self, refresh_token):
        """jti нужен для отзыва токена через DynamoDB"""
        payload = decode_refresh_token(refresh_token)
        assert "jti" in payload
        assert len(payload["jti"]) == 64  # secrets.token_hex(32)

    def test_expiry_is_7_days(self, refresh_token):
        payload = decode_refresh_token(refresh_token)
        delta = payload["exp"] - payload["iat"]
        assert delta == REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    def test_unique_jti_per_token(self):
        """Каждый refresh token уникален — защита от replay атак"""
        t1 = generate_refresh_token("u1", "yallabalagan")
        t2 = generate_refresh_token("u1", "yallabalagan")
        p1 = decode_refresh_token(t1)
        p2 = decode_refresh_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_no_email_in_refresh_token(self, refresh_token):
        """Refresh token намеренно не содержит email — минимальный payload"""
        payload = decode_refresh_token(refresh_token)
        assert "email" not in payload

    def test_no_role_in_refresh_token(self, refresh_token):
        payload = decode_refresh_token(refresh_token)
        assert "role" not in payload


# ---------------------------------------------------------------------------
# validate_token
# ---------------------------------------------------------------------------

class TestValidateToken:
    def test_valid_access_token(self, access_token):
        payload = validate_token(access_token)
        assert payload["sub"] == "user-123"

    def test_valid_with_expected_type(self, access_token):
        payload = validate_token(access_token, expected_type="access")
        assert payload["type"] == "access"

    def test_wrong_type_raises(self, access_token, refresh_token):
        with pytest.raises(TokenInvalidError, match="Expected token type"):
            validate_token(access_token, expected_type="refresh")

        with pytest.raises(TokenInvalidError, match="Expected token type"):
            validate_token(refresh_token, expected_type="access")

    def test_tampered_token_raises(self, access_token):
        tampered = access_token[:-5] + "XXXXX"
        with pytest.raises(TokenInvalidError):
            validate_token(tampered)

    def test_garbage_string_raises(self):
        with pytest.raises(TokenInvalidError):
            validate_token("not.a.token")

    def test_empty_string_raises(self):
        with pytest.raises(TokenInvalidError):
            validate_token("")

    def test_wrong_secret_raises(self):
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        bad_token = pyjwt.encode(
            {"sub": "u1", "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
            "wrong-secret",
            algorithm="HS256",
        )
        with pytest.raises(TokenInvalidError):
            validate_token(bad_token)


# ---------------------------------------------------------------------------
# TokenExpiredError
# ---------------------------------------------------------------------------

class TestExpiredToken:
    def test_expired_access_token_raises(self):
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        expired_token = pyjwt.encode(
            {
                "sub": "u1",
                "tenant_id": "yallabalagan",
                "email": "a@b.com",
                "role": "admin",
                "type": "access",
                "iat": datetime.now(timezone.utc) - timedelta(hours=1),
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            },
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        with pytest.raises(TokenExpiredError):
            validate_token(expired_token)


# ---------------------------------------------------------------------------
# Missing JWT_SECRET
# ---------------------------------------------------------------------------

class TestMissingSecret:
    def test_missing_secret_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        # Перезагружаем _get_secret напрямую
        from utils import auth_jwt
        original = auth_jwt._get_secret
        auth_jwt._get_secret = lambda: (_ for _ in ()).throw(
            RuntimeError("JWT_SECRET environment variable is not set")
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            auth_jwt._get_secret()
        auth_jwt._get_secret = original
