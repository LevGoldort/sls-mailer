"""Integration tests for RBAC on events API (Task 10)."""
import json
import os
import importlib.util
import pytest
from decimal import Decimal
from moto import mock_aws
import boto3

EVENTS_TABLE = "yallabalagan-events-test"
ORDERS_TABLE = "yallabalagan-orders-test"
LOCATIONS_TABLE = "yallabalagan-locations-test"
TOKENS_TABLE = "yallabalagan-refresh-tokens-test"
USERS_TABLE = "yallabalagan-users-test"
SEAT_RESERVATIONS_TABLE = "yallabalagan-seat-reservations-test"
COUPONS_TABLE = "yallabalagan-coupons-test"
TENANT = "yallabalagan"
JWT_SECRET = "test-secret-events-rbac-32chars!!!"
ADMIN_KEY = "test-admin-key"


def _import_handler():
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "lambdas", "api-handler.py",
    )
    spec = importlib.util.spec_from_file_location("api_handler_rbac", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ.update({
        "JWT_SECRET": JWT_SECRET,
        "ADMIN_API_KEYS": ADMIN_KEY,
        "EVENTS_TABLE": EVENTS_TABLE,
        "ORDERS_TABLE": ORDERS_TABLE,
        "LOCATIONS_TABLE": LOCATIONS_TABLE,
        "SEAT_RESERVATIONS_TABLE": SEAT_RESERVATIONS_TABLE,
        "COUPONS_TABLE": COUPONS_TABLE,
        "USERS_TABLE": USERS_TABLE,
        "REFRESH_TOKENS_TABLE": TOKENS_TABLE,
        "TENANT_ID": TENANT,
        "PAYMENT_MODE": "mock",
    })
    import utils.auth as _auth
    _auth._admin_auth = None


@pytest.fixture
def tables(dynamodb_mock):
    dynamodb_mock.create_table(
        TableName=EVENTS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
            {"AttributeName": "slug", "AttributeType": "S"},
            {"AttributeName": "owner_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "SlugIndex",
                "KeySchema": [{"AttributeName": "slug", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "OwnerIndex",
                "KeySchema": [{"AttributeName": "owner_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )
    for tbl_name, schema in [
        (ORDERS_TABLE, [
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "event_id", "AttributeType": "S"},
            {"AttributeName": "customer_email", "AttributeType": "S"},
        ]),
        (LOCATIONS_TABLE, [
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ]),
        (SEAT_RESERVATIONS_TABLE, [
            {"AttributeName": "event_id", "AttributeType": "S"},
            {"AttributeName": "seat_id", "AttributeType": "S"},
        ]),
        (COUPONS_TABLE, [
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ]),
    ]:
        key_schema = [{"AttributeName": a["AttributeName"], "KeyType": k}
                      for a, k in zip(schema[:2], ["HASH", "RANGE"])]
        kwargs = dict(
            TableName=tbl_name,
            KeySchema=key_schema,
            AttributeDefinitions=schema[:2],
            BillingMode="PAY_PER_REQUEST",
        )
        if tbl_name == ORDERS_TABLE:
            kwargs["AttributeDefinitions"] = schema
            kwargs["GlobalSecondaryIndexes"] = [
                {"IndexName": "EventIndex",
                 "KeySchema": [{"AttributeName": "event_id", "KeyType": "HASH"}],
                 "Projection": {"ProjectionType": "ALL"}},
                {"IndexName": "EmailIndex",
                 "KeySchema": [{"AttributeName": "customer_email", "KeyType": "HASH"}],
                 "Projection": {"ProjectionType": "ALL"}},
            ]
        if tbl_name == SEAT_RESERVATIONS_TABLE:
            kwargs["KeySchema"] = [
                {"AttributeName": "event_id", "KeyType": "HASH"},
                {"AttributeName": "seat_id", "KeyType": "RANGE"},
            ]
        dynamodb_mock.create_table(**kwargs)


@pytest.fixture
def handler(tables):
    mod = _import_handler()
    from utils.dynamodb import DynamoDBClient
    mod.db = DynamoDBClient()
    return mod


def _access_token(user_id, role):
    from utils.auth_jwt import generate_access_token
    return generate_access_token(user_id=user_id, tenant_id=TENANT,
                                 email=f"{user_id}@example.com", role=role)


def _event(method, path, body=None, headers=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": json.dumps(body) if body else None,
    }


def _parse(resp):
    return json.loads(resp["body"])


def _seed_event(handler, owner_id=None):
    """Create an event via db directly, return its event_id."""
    import uuid
    from datetime import datetime
    eid = str(uuid.uuid4())
    item = {
        "PK": f"EVENT#{eid}", "SK": "METADATA",
        "event_id": eid,
        "title": "Test Event",
        "description": "desc",
        "date": "2099-12-31T20:00:00Z",
        "location_id": "loc-1",
        "ticket_types": [],
        "currency": "ILS",
        "status": "active",
        "images": [],
        "GSI1PK": "EVENT",
        "GSI1SK": "2099-12-31T20:00:00Z",
    }
    if owner_id:
        item["owner_id"] = owner_id
    if owner_id:
        item["tenant_id"] = TENANT
    handler.db.put_event(item)
    return eid


# ===== list_events filtering =====

class TestListEventsRBAC:
    def test_unauthenticated_sees_all_events(self, handler):
        e1 = _seed_event(handler, owner_id="u1")
        e2 = _seed_event(handler, owner_id="u2")
        resp = handler.lambda_handler(_event("GET", "/api/events"), None)
        assert resp["statusCode"] == 200
        ids = {e["event_id"] for e in _parse(resp)["events"]}
        assert e1 in ids and e2 in ids

    def test_admin_sees_all_events(self, handler):
        e1 = _seed_event(handler, owner_id="u1")
        e2 = _seed_event(handler, owner_id="u2")
        token = _access_token("admin-1", "admin")
        resp = handler.lambda_handler(
            _event("GET", "/api/events", headers={"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200
        ids = {e["event_id"] for e in _parse(resp)["events"]}
        assert e1 in ids and e2 in ids

    def test_organizer_sees_only_own_events(self, handler):
        own = _seed_event(handler, owner_id="org-1")
        other = _seed_event(handler, owner_id="u2")
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("GET", "/api/events", headers={"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200
        ids = {e["event_id"] for e in _parse(resp)["events"]}
        assert own in ids
        assert other not in ids

    def test_api_key_admin_sees_all_events(self, handler):
        e1 = _seed_event(handler, owner_id="u1")
        resp = handler.lambda_handler(
            _event("GET", "/api/events", headers={"X-API-Key": ADMIN_KEY}), None
        )
        ids = {e["event_id"] for e in _parse(resp)["events"]}
        assert e1 in ids


# ===== create_event auth =====

class TestCreateEventRBAC:
    _BODY = {
        "title": "New Event", "description": "desc",
        "date": "2099-06-01T20:00:00Z", "location_id": "loc-1",
        "ticket_types": [{"id": "tt1", "name": "GA", "price": 100, "total": 50}],
    }

    def test_admin_jwt_creates_event(self, handler):
        token = _access_token("admin-1", "admin")
        resp = handler.lambda_handler(
            _event("POST", "/api/events", self._BODY, {"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 201
        body = _parse(resp)
        assert body["event"]["owner_id"] == "admin-1"

    def test_organizer_creates_event_as_owner(self, handler):
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("POST", "/api/events", self._BODY, {"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 201
        assert _parse(resp)["event"]["owner_id"] == "org-1"

    def test_api_key_creates_event_backward_compat(self, handler):
        resp = handler.lambda_handler(
            _event("POST", "/api/events", self._BODY, {"X-API-Key": ADMIN_KEY}), None
        )
        assert resp["statusCode"] == 201

    def test_unauthenticated_returns_401(self, handler):
        resp = handler.lambda_handler(_event("POST", "/api/events", self._BODY), None)
        assert resp["statusCode"] == 401


# ===== update_event RBAC =====

class TestUpdateEventRBAC:
    def test_admin_can_update_any_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        token = _access_token("admin-1", "admin")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/events/{eid}", {"title": "Updated"},
                   {"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200

    def test_owner_can_update_own_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/events/{eid}", {"title": "Updated"},
                   {"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200

    def test_organizer_cannot_update_other_event(self, handler):
        eid = _seed_event(handler, owner_id="org-2")
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/events/{eid}", {"title": "Hacked"},
                   {"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 403

    def test_api_key_can_update_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        resp = handler.lambda_handler(
            _event("PUT", f"/api/events/{eid}", {"title": "Updated"},
                   {"X-API-Key": ADMIN_KEY}), None
        )
        assert resp["statusCode"] == 200

    def test_unauthenticated_update_returns_401(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        resp = handler.lambda_handler(_event("PUT", f"/api/events/{eid}", {"title": "X"}), None)
        assert resp["statusCode"] == 401


# ===== delete_event RBAC =====

class TestDeleteEventRBAC:
    def test_admin_can_delete_any_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        token = _access_token("admin-1", "admin")
        resp = handler.lambda_handler(
            _event("DELETE", f"/api/events/{eid}", headers={"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200

    def test_owner_can_delete_own_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("DELETE", f"/api/events/{eid}", headers={"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 200

    def test_organizer_cannot_delete_other_event(self, handler):
        eid = _seed_event(handler, owner_id="org-2")
        token = _access_token("org-1", "organizer")
        resp = handler.lambda_handler(
            _event("DELETE", f"/api/events/{eid}", headers={"Authorization": f"Bearer {token}"}), None
        )
        assert resp["statusCode"] == 403

    def test_api_key_can_delete_event(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        resp = handler.lambda_handler(
            _event("DELETE", f"/api/events/{eid}", headers={"X-API-Key": ADMIN_KEY}), None
        )
        assert resp["statusCode"] == 200

    def test_unauthenticated_delete_returns_401(self, handler):
        eid = _seed_event(handler, owner_id="org-1")
        resp = handler.lambda_handler(_event("DELETE", f"/api/events/{eid}"), None)
        assert resp["statusCode"] == 401
