"""Unit tests for utils/auth_middleware.py"""
import os
import pytest

from utils.auth_middleware import authenticate, AuthError


JWT_SECRET = "test-secret-middleware"
TENANT = "yallabalagan"
API_KEY = "test-admin-key"


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ["JWT_SECRET"] = JWT_SECRET
    os.environ["ADMIN_API_KEYS"] = API_KEY
    # reset singleton so it picks up new env
    import utils.auth as _auth
    _auth._admin_auth = None


def _make_event(headers: dict) -> dict:
    return {"headers": headers}


def _valid_access_token(user_id="u1", role="admin") -> str:
    from utils.auth_jwt import generate_access_token
    return generate_access_token(
        user_id=user_id,
        tenant_id=TENANT,
        email="user@example.com",
        role=role,
    )


# ===== JWT Bearer =====

class TestJwtAuth:
    def test_valid_jwt_returns_context(self):
        token = _valid_access_token(user_id="u1", role="admin")
        ctx = authenticate(_make_event({"Authorization": f"Bearer {token}"}))
        assert ctx["user_id"] == "u1"
        assert ctx["tenant_id"] == TENANT
        assert ctx["email"] == "user@example.com"
        assert ctx["role"] == "admin"
        assert ctx["auth_method"] == "jwt"

    def test_organizer_role_preserved(self):
        token = _valid_access_token(user_id="u2", role="organizer")
        ctx = authenticate(_make_event({"Authorization": f"Bearer {token}"}))
        assert ctx["role"] == "organizer"

    def test_header_case_insensitive(self):
        token = _valid_access_token()
        ctx = authenticate(_make_event({"authorization": f"bearer {token}"}))
        assert ctx["auth_method"] == "jwt"

    def test_expired_jwt_raises_auth_error(self):
        import jwt
        from datetime import datetime, timezone, timedelta
        payload = {
            "sub": "u1", "tenant_id": TENANT, "email": "x@x.com",
            "role": "admin", "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        with pytest.raises(AuthError) as exc:
            authenticate(_make_event({"Authorization": f"Bearer {expired}"}))
        assert exc.value.status_code == 401
        assert "expired" in str(exc.value).lower()

    def test_invalid_jwt_raises_auth_error(self):
        with pytest.raises(AuthError):
            authenticate(_make_event({"Authorization": "Bearer not.a.token"}))

    def test_refresh_token_rejected_as_access(self):
        from utils.auth_jwt import generate_refresh_token
        refresh = generate_refresh_token(user_id="u1", tenant_id=TENANT)
        with pytest.raises(AuthError):
            authenticate(_make_event({"Authorization": f"Bearer {refresh}"}))


# ===== API Key fallback =====

class TestApiKeyAuth:
    def test_valid_api_key_returns_admin_context(self):
        ctx = authenticate(_make_event({"X-API-Key": API_KEY}))
        assert ctx["role"] == "admin"
        assert ctx["auth_method"] == "api_key"
        assert ctx["tenant_id"] == TENANT
        assert ctx["user_id"] is None

    def test_x_admin_key_header_also_works(self):
        ctx = authenticate(_make_event({"X-Admin-Key": API_KEY}))
        assert ctx["auth_method"] == "api_key"

    def test_api_key_header_case_insensitive(self):
        ctx = authenticate(_make_event({"x-api-key": API_KEY}))
        assert ctx["auth_method"] == "api_key"

    def test_invalid_api_key_raises_auth_error(self):
        with pytest.raises(AuthError):
            authenticate(_make_event({"X-API-Key": "wrong-key"}))

    def test_api_key_logs_deprecation_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="utils.auth_middleware"):
            authenticate(_make_event({"X-API-Key": API_KEY}))
        assert any("deprecated" in r.message.lower() for r in caplog.records)


# ===== No credentials =====

class TestNoAuth:
    def test_no_headers_raises_auth_error(self):
        with pytest.raises(AuthError) as exc:
            authenticate(_make_event({}))
        assert exc.value.status_code == 401

    def test_jwt_takes_priority_over_api_key(self):
        token = _valid_access_token()
        ctx = authenticate(_make_event({
            "Authorization": f"Bearer {token}",
            "X-API-Key": API_KEY,
        }))
        assert ctx["auth_method"] == "jwt"
