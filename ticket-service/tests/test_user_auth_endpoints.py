"""Integration tests for user-api-handler auth endpoints."""
import importlib.util
import json
import os
import sys
import pytest
from moto import mock_aws
import boto3

USERS_TABLE = "yallabalagan-users-test"
TOKENS_TABLE = "yallabalagan-refresh-tokens-test"
TENANT = "yallabalagan"
JWT_SECRET = "test-secret-auth-endpoints-32chars!!"
ADMIN_KEY = "test-admin-key"


def _load_handler():
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "lambdas", "user-api-handler.py",
    )
    spec = importlib.util.spec_from_file_location("user_api_handler", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ["JWT_SECRET"] = JWT_SECRET
    os.environ["ADMIN_API_KEYS"] = ADMIN_KEY
    os.environ["USERS_TABLE"] = USERS_TABLE
    os.environ["REFRESH_TOKENS_TABLE"] = TOKENS_TABLE
    os.environ["TENANT_ID"] = TENANT
    import utils.auth as _auth
    _auth._admin_auth = None


@pytest.fixture
def tables(dynamodb_mock):
    dynamodb_mock.create_table(
        TableName=USERS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
            {"AttributeName": "tenant_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=[
            {
                "IndexName": "EmailIndex",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "TenantIndex",
                "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )
    dynamodb_mock.create_table(
        TableName=TOKENS_TABLE,
        KeySchema=[{"AttributeName": "token_hash", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "token_hash", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def handler(tables):
    return _load_handler()


@pytest.fixture
def alice(tables):
    from models.user import User
    from utils.auth_password import hash_password
    from repositories import user_repository
    user = User.create(
        email="alice@example.com",
        password_hash=hash_password("password123"),
        name="Alice",
        role="admin",
        tenant_id=TENANT,
    )
    user_repository.create_user(user)
    return user


def _event(method: str, path: str, body: dict = None, headers: dict = None) -> dict:
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": json.dumps(body) if body else None,
    }


def _parse(response: dict) -> dict:
    return json.loads(response["body"])


# ===== Login =====

class TestLogin:
    def test_valid_credentials_return_tokens(self, handler, alice):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "password123"}),
            None,
        )
        assert resp["statusCode"] == 200
        body = _parse(resp)
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["user"]["email"] == "alice@example.com"

    def test_wrong_password_returns_401(self, handler, alice):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "wrong"}),
            None,
        )
        assert resp["statusCode"] == 401

    def test_unknown_email_returns_401(self, handler, tables):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "nobody@example.com", "password": "pass"}),
            None,
        )
        assert resp["statusCode"] == 401

    def test_missing_fields_returns_400(self, handler, tables):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com"}),
            None,
        )
        assert resp["statusCode"] == 400

    def test_email_case_insensitive(self, handler, alice):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "ALICE@EXAMPLE.COM", "password": "password123"}),
            None,
        )
        assert resp["statusCode"] == 200


# ===== Refresh =====

class TestRefresh:
    def test_valid_refresh_token_returns_new_access_token(self, handler, alice):
        login_resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "password123"}),
            None,
        )
        refresh_token = _parse(login_resp)["refresh_token"]

        resp = handler.lambda_handler(
            _event("POST", "/api/auth/refresh", {"refresh_token": refresh_token}),
            None,
        )
        assert resp["statusCode"] == 200
        assert "access_token" in _parse(resp)

    def test_invalid_refresh_token_returns_401(self, handler, tables):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/refresh", {"refresh_token": "invalid.token.here"}),
            None,
        )
        assert resp["statusCode"] == 401

    def test_missing_refresh_token_returns_400(self, handler, tables):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/refresh", {}),
            None,
        )
        assert resp["statusCode"] == 400


# ===== Logout =====

class TestLogout:
    def test_logout_revokes_refresh_token(self, handler, alice):
        login_resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "password123"}),
            None,
        )
        refresh_token = _parse(login_resp)["refresh_token"]

        logout_resp = handler.lambda_handler(
            _event("POST", "/api/auth/logout", {"refresh_token": refresh_token}),
            None,
        )
        assert logout_resp["statusCode"] == 200

        # refresh should now fail
        refresh_resp = handler.lambda_handler(
            _event("POST", "/api/auth/refresh", {"refresh_token": refresh_token}),
            None,
        )
        assert refresh_resp["statusCode"] == 401

    def test_missing_refresh_token_returns_400(self, handler, tables):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/logout", {}),
            None,
        )
        assert resp["statusCode"] == 400


# ===== Change password =====

class TestChangePassword:
    def _login(self, handler):
        resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "password123"}),
            None,
        )
        return _parse(resp)["access_token"]

    def test_change_password_success(self, handler, alice):
        token = self._login(handler)
        resp = handler.lambda_handler(
            _event(
                "POST", "/api/auth/change-password",
                {"current_password": "password123", "new_password": "newpassword99"},
                {"Authorization": f"Bearer {token}"},
            ),
            None,
        )
        assert resp["statusCode"] == 200

        # old password no longer works
        old_resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "alice@example.com", "password": "password123"}),
            None,
        )
        assert old_resp["statusCode"] == 401

    def test_wrong_current_password_returns_401(self, handler, alice):
        token = self._login(handler)
        resp = handler.lambda_handler(
            _event(
                "POST", "/api/auth/change-password",
                {"current_password": "wrongpass", "new_password": "newpassword99"},
                {"Authorization": f"Bearer {token}"},
            ),
            None,
        )
        assert resp["statusCode"] == 401

    def test_short_new_password_returns_400(self, handler, alice):
        token = self._login(handler)
        resp = handler.lambda_handler(
            _event(
                "POST", "/api/auth/change-password",
                {"current_password": "password123", "new_password": "short"},
                {"Authorization": f"Bearer {token}"},
            ),
            None,
        )
        assert resp["statusCode"] == 400

    def test_no_auth_returns_401(self, handler, alice):
        resp = handler.lambda_handler(
            _event(
                "POST", "/api/auth/change-password",
                {"current_password": "password123", "new_password": "newpassword99"},
            ),
            None,
        )
        assert resp["statusCode"] == 401

    def test_api_key_auth_returns_403(self, handler, alice):
        resp = handler.lambda_handler(
            _event(
                "POST", "/api/auth/change-password",
                {"current_password": "password123", "new_password": "newpassword99"},
                {"X-API-Key": ADMIN_KEY},
            ),
            None,
        )
        assert resp["statusCode"] == 403


# ===== Routing =====

class TestRouting:
    def test_options_returns_200(self, handler, tables):
        resp = handler.lambda_handler(_event("OPTIONS", "/api/auth/login"), None)
        assert resp["statusCode"] == 200

    def test_unknown_path_returns_404(self, handler, tables):
        resp = handler.lambda_handler(_event("GET", "/api/auth/unknown"), None)
        assert resp["statusCode"] == 404
