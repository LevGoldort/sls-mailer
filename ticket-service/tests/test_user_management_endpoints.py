"""Integration tests for /api/users CRUD endpoints."""
import importlib.util
import json
import os
import pytest

USERS_TABLE = "yallabalagan-users-test"
TOKENS_TABLE = "yallabalagan-refresh-tokens-test"
TENANT = "yallabalagan"
JWT_SECRET = "test-secret-user-mgmt-endpoints32!!"
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
def admin_user(tables):
    from models.user import User
    from utils.auth_password import hash_password
    from repositories import user_repository
    user = User.create(
        email="admin@example.com",
        password_hash=hash_password("adminpass1"),
        name="Admin",
        role="admin",
        tenant_id=TENANT,
    )
    user_repository.create_user(user)
    return user


@pytest.fixture
def organizer_user(tables):
    from models.user import User
    from utils.auth_password import hash_password
    from repositories import user_repository
    user = User.create(
        email="org@example.com",
        password_hash=hash_password("orgpass1234"),
        name="Organizer",
        role="organizer",
        tenant_id=TENANT,
    )
    user_repository.create_user(user)
    return user


def _token_for(handler, email, password):
    resp = handler.lambda_handler(
        _event("POST", "/api/auth/login", {"email": email, "password": password}),
        None,
    )
    return json.loads(resp["body"])["access_token"]


def _event(method, path, body=None, headers=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": json.dumps(body) if body else None,
    }


def _parse(resp):
    return json.loads(resp["body"])


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ===== List users =====

class TestListUsers:
    def test_admin_can_list_users(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(_event("GET", "/api/users", headers=_auth(token)), None)
        assert resp["statusCode"] == 200
        users = _parse(resp)["users"]
        emails = {u["email"] for u in users}
        assert "admin@example.com" in emails
        assert "org@example.com" in emails

    def test_organizer_cannot_list_users(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "org@example.com", "orgpass1234")
        resp = handler.lambda_handler(_event("GET", "/api/users", headers=_auth(token)), None)
        assert resp["statusCode"] == 403

    def test_unauthenticated_returns_401(self, handler, tables):
        resp = handler.lambda_handler(_event("GET", "/api/users"), None)
        assert resp["statusCode"] == 401

    def test_api_key_admin_can_list_users(self, handler, admin_user):
        resp = handler.lambda_handler(
            _event("GET", "/api/users", headers={"X-API-Key": ADMIN_KEY}), None
        )
        assert resp["statusCode"] == 200


# ===== Create user =====

class TestCreateUser:
    def test_admin_creates_user(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("POST", "/api/users",
                   {"email": "new@example.com", "name": "New User", "role": "organizer", "password": "secure123"},
                   _auth(token)),
            None,
        )
        assert resp["statusCode"] == 201
        user = _parse(resp)["user"]
        assert user["email"] == "new@example.com"
        assert user["role"] == "organizer"
        assert "password_hash" not in user

    def test_duplicate_email_returns_409(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        payload = {"email": "admin@example.com", "name": "Dup", "role": "organizer", "password": "secure123"}
        resp = handler.lambda_handler(_event("POST", "/api/users", payload, _auth(token)), None)
        assert resp["statusCode"] == 409

    def test_missing_field_returns_400(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("POST", "/api/users", {"email": "x@x.com", "role": "admin"}, _auth(token)), None
        )
        assert resp["statusCode"] == 400

    def test_invalid_role_returns_400(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        payload = {"email": "x@x.com", "name": "X", "role": "superuser", "password": "secure123"}
        resp = handler.lambda_handler(_event("POST", "/api/users", payload, _auth(token)), None)
        assert resp["statusCode"] == 400

    def test_short_password_returns_400(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        payload = {"email": "x@x.com", "name": "X", "role": "organizer", "password": "short"}
        resp = handler.lambda_handler(_event("POST", "/api/users", payload, _auth(token)), None)
        assert resp["statusCode"] == 400

    def test_organizer_cannot_create_user(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "org@example.com", "orgpass1234")
        payload = {"email": "x@x.com", "name": "X", "role": "organizer", "password": "secure123"}
        resp = handler.lambda_handler(_event("POST", "/api/users", payload, _auth(token)), None)
        assert resp["statusCode"] == 403


# ===== Get user =====

class TestGetUser:
    def test_admin_gets_user_by_id(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("GET", f"/api/users/{organizer_user.user_id}", headers=_auth(token)), None
        )
        assert resp["statusCode"] == 200
        assert _parse(resp)["user"]["email"] == "org@example.com"

    def test_nonexistent_user_returns_404(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("GET", "/api/users/ghost-id", headers=_auth(token)), None
        )
        assert resp["statusCode"] == 404


# ===== Update user =====

class TestUpdateUser:
    def test_admin_updates_user_name(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/users/{organizer_user.user_id}",
                   {"name": "Updated Name"}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 200
        assert _parse(resp)["user"]["name"] == "Updated Name"

    def test_admin_updates_role(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/users/{organizer_user.user_id}",
                   {"role": "admin"}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 200
        assert _parse(resp)["user"]["role"] == "admin"

    def test_invalid_role_update_returns_400(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/users/{organizer_user.user_id}",
                   {"role": "superuser"}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 400

    def test_nonexistent_update_returns_404(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("PUT", "/api/users/ghost", {"name": "X"}, _auth(token)), None
        )
        assert resp["statusCode"] == 404


# ===== Deactivate user =====

class TestDeactivateUser:
    def test_delete_deactivates_not_removes(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("DELETE", f"/api/users/{organizer_user.user_id}", headers=_auth(token)), None
        )
        assert resp["statusCode"] == 200
        assert _parse(resp)["user"]["status"] == "inactive"

    def test_deactivated_user_cannot_login(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        handler.lambda_handler(
            _event("DELETE", f"/api/users/{organizer_user.user_id}", headers=_auth(token)), None
        )
        login_resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "org@example.com", "password": "orgpass1234"}),
            None,
        )
        assert login_resp["statusCode"] == 401

    def test_nonexistent_delete_returns_404(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("DELETE", "/api/users/ghost", headers=_auth(token)), None
        )
        assert resp["statusCode"] == 404


# ===== Reset password =====

class TestResetPassword:
    def test_admin_resets_password(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("POST", f"/api/users/{organizer_user.user_id}/reset-password",
                   {"new_password": "resetpass99"}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 200

        # login with new password works
        login_resp = handler.lambda_handler(
            _event("POST", "/api/auth/login", {"email": "org@example.com", "password": "resetpass99"}),
            None,
        )
        assert login_resp["statusCode"] == 200

    def test_missing_password_returns_400(self, handler, admin_user, organizer_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("POST", f"/api/users/{organizer_user.user_id}/reset-password", {}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 400

    def test_nonexistent_user_returns_404(self, handler, admin_user):
        token = _token_for(handler, "admin@example.com", "adminpass1")
        resp = handler.lambda_handler(
            _event("POST", "/api/users/ghost/reset-password",
                   {"new_password": "newpass123"}, _auth(token)),
            None,
        )
        assert resp["statusCode"] == 404
