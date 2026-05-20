"""Tests for migrate_user_management.py"""
import importlib.util
import os
import sys
import pytest
from moto import mock_aws
import boto3

USERS_TABLE  = "yallabalagan-users-test"
EVENTS_TABLE = "yallabalagan-events-test"
TENANT = "yallabalagan"


def _load_script():
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "scripts", "migrate_user_management.py",
    )
    spec = importlib.util.spec_from_file_location("migrate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ["USERS_TABLE"]  = USERS_TABLE
    os.environ["EVENTS_TABLE"] = EVENTS_TABLE
    os.environ["ADMIN_EMAIL"]    = "admin@example.com"
    os.environ["ADMIN_NAME"]     = "Test Admin"
    os.environ["ADMIN_PASSWORD"] = "testpassword1"


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
    return dynamodb_mock


def _seed_event(db, event_id, with_owner=False):
    item = {
        "PK": f"EVENT#{event_id}", "SK": "METADATA",
        "event_id": event_id, "title": "Test",
        "GSI1PK": "EVENT", "GSI1SK": "2099-01-01T00:00:00Z",
    }
    if with_owner:
        item["owner_id"] = "existing-owner"
        item["tenant_id"] = TENANT
    db.Table(EVENTS_TABLE).put_item(Item=item)


class TestCreateAdminUser:
    def test_creates_admin_user(self, tables):
        m = _load_script()
        admin = m.create_admin_user(tables)
        assert admin.email == "admin@example.com"
        assert admin.role == "admin"
        assert admin.tenant_id == TENANT

    def test_idempotent_second_run(self, tables):
        m = _load_script()
        user1 = m.create_admin_user(tables)
        user2 = m.create_admin_user(tables)
        assert user1.user_id == user2.user_id  # same user, not duplicated

    def test_password_hashed(self, tables):
        from utils.auth_password import verify_password
        m = _load_script()
        admin = m.create_admin_user(tables)
        # Fetch from DB to verify hash
        item = tables.Table(USERS_TABLE).get_item(
            Key={"PK": f"TENANT#{TENANT}#USER#{admin.user_id}", "SK": "METADATA"}
        )["Item"]
        assert verify_password("testpassword1", item["password_hash"])


class TestBackfillEvents:
    def test_assigns_owner_to_unowned_events(self, tables):
        _seed_event(tables, "ev1")
        _seed_event(tables, "ev2")
        m = _load_script()
        admin = m.create_admin_user(tables)
        updated, _ = m.backfill_events(tables, admin)
        assert updated == 2

        for eid in ["ev1", "ev2"]:
            item = tables.Table(EVENTS_TABLE).get_item(
                Key={"PK": f"EVENT#{eid}", "SK": "METADATA"}
            )["Item"]
            assert item["owner_id"] == admin.user_id
            assert item["tenant_id"] == TENANT

    def test_skips_already_owned_events(self, tables):
        _seed_event(tables, "ev1", with_owner=True)
        m = _load_script()
        admin = m.create_admin_user(tables)
        updated, _ = m.backfill_events(tables, admin)
        assert updated == 0

        # Owner unchanged
        item = tables.Table(EVENTS_TABLE).get_item(
            Key={"PK": "EVENT#ev1", "SK": "METADATA"}
        )["Item"]
        assert item["owner_id"] == "existing-owner"

    def test_idempotent_double_run(self, tables):
        _seed_event(tables, "ev1")
        m = _load_script()
        admin = m.create_admin_user(tables)
        updated1, _ = m.backfill_events(tables, admin)
        updated2, _ = m.backfill_events(tables, admin)
        assert updated1 == 1
        assert updated2 == 0  # already owned on second run

    def test_mixed_events(self, tables):
        _seed_event(tables, "ev1")            # unowned
        _seed_event(tables, "ev2", with_owner=True)  # already owned
        _seed_event(tables, "ev3")            # unowned
        m = _load_script()
        admin = m.create_admin_user(tables)
        updated, _ = m.backfill_events(tables, admin)
        assert updated == 2
