"""Unit tests for user_repository and token_repository"""
import os
import pytest
from moto import mock_aws
import boto3

from models.user import User


TENANT = "yallabalagan"
REGION = "eu-north-1"
USERS_TABLE = "yallabalagan-users-test"
TOKENS_TABLE = "yallabalagan-refresh-tokens-test"


@pytest.fixture(autouse=True)
def aws_env(aws_credentials):
    os.environ["USERS_TABLE"] = USERS_TABLE
    os.environ["REFRESH_TOKENS_TABLE"] = TOKENS_TABLE


@pytest.fixture
def users_table(dynamodb_mock):
    return dynamodb_mock.create_table(
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


@pytest.fixture
def tokens_table(dynamodb_mock):
    return dynamodb_mock.create_table(
        TableName=TOKENS_TABLE,
        KeySchema=[{"AttributeName": "token_hash", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "token_hash", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def sample_user():
    return User.create(
        email="alice@example.com",
        password_hash="hashed",
        name="Alice",
        role="admin",
        tenant_id=TENANT,
    )


# ===== user_repository =====

class TestCreateAndGet:
    def test_create_and_get_by_id(self, users_table, sample_user):
        from repositories import user_repository as repo
        repo.create_user(sample_user)
        result = repo.get_user_by_id(sample_user.user_id, TENANT)
        assert result is not None
        assert result.user_id == sample_user.user_id
        assert result.email == sample_user.email

    def test_get_by_id_missing_returns_none(self, users_table):
        from repositories import user_repository as repo
        assert repo.get_user_by_id("nonexistent", TENANT) is None

    def test_get_by_email(self, users_table, sample_user):
        from repositories import user_repository as repo
        repo.create_user(sample_user)
        result = repo.get_user_by_email(sample_user.email, TENANT)
        assert result is not None
        assert result.user_id == sample_user.user_id

    def test_get_by_email_missing_returns_none(self, users_table):
        from repositories import user_repository as repo
        assert repo.get_user_by_email("nobody@example.com", TENANT) is None

    def test_get_by_email_wrong_tenant_returns_none(self, users_table, sample_user):
        from repositories import user_repository as repo
        repo.create_user(sample_user)
        assert repo.get_user_by_email(sample_user.email, "other-tenant") is None


class TestListByTenant:
    def test_list_returns_all_tenant_users(self, users_table):
        from repositories import user_repository as repo
        u1 = User.create(email="a@x.com", password_hash="h", name="A", role="admin", tenant_id=TENANT)
        u2 = User.create(email="b@x.com", password_hash="h", name="B", role="organizer", tenant_id=TENANT)
        repo.create_user(u1)
        repo.create_user(u2)
        results = repo.list_users_by_tenant(TENANT)
        ids = {u.user_id for u in results}
        assert u1.user_id in ids
        assert u2.user_id in ids

    def test_list_empty_tenant_returns_empty(self, users_table):
        from repositories import user_repository as repo
        assert repo.list_users_by_tenant("empty-tenant") == []

    def test_list_does_not_cross_tenants(self, users_table):
        from repositories import user_repository as repo
        u_other = User.create(email="c@x.com", password_hash="h", name="C", role="admin", tenant_id="other")
        repo.create_user(u_other)
        results = repo.list_users_by_tenant(TENANT)
        assert all(u.tenant_id == TENANT for u in results)


class TestUpdateAndDeactivate:
    def test_update_user(self, users_table, sample_user):
        from repositories import user_repository as repo
        repo.create_user(sample_user)
        sample_user.name = "Alice Updated"
        repo.update_user(sample_user)
        result = repo.get_user_by_id(sample_user.user_id, TENANT)
        assert result.name == "Alice Updated"

    def test_deactivate_user(self, users_table, sample_user):
        from repositories import user_repository as repo
        repo.create_user(sample_user)
        result = repo.deactivate_user(sample_user.user_id, TENANT)
        assert result is not None
        assert result.status == "inactive"
        # Verify persisted
        persisted = repo.get_user_by_id(sample_user.user_id, TENANT)
        assert persisted.status == "inactive"

    def test_deactivate_nonexistent_raises(self, users_table):
        from botocore.exceptions import ClientError
        from repositories import user_repository as repo
        with pytest.raises(ClientError):
            repo.deactivate_user("ghost", TENANT)


# ===== token_repository =====

class TestTokenRepository:
    def test_store_and_get(self, tokens_table):
        from repositories import token_repository as repo
        repo.store_refresh_token(
            token_hash="abc123",
            user_id="user-1",
            tenant_id=TENANT,
            expires_at=9999999999,
        )
        result = repo.get_refresh_token("abc123")
        assert result is not None
        assert result["user_id"] == "user-1"
        assert result["tenant_id"] == TENANT
        assert result["expires_at"] == 9999999999

    def test_get_missing_returns_none(self, tokens_table):
        from repositories import token_repository as repo
        assert repo.get_refresh_token("nonexistent") is None

    def test_revoke_removes_token(self, tokens_table):
        from repositories import token_repository as repo
        repo.store_refresh_token("tok", "user-1", TENANT, 9999999999)
        repo.revoke_refresh_token("tok")
        assert repo.get_refresh_token("tok") is None

    def test_revoke_nonexistent_is_idempotent(self, tokens_table):
        from repositories import token_repository as repo
        repo.revoke_refresh_token("ghost")  # should not raise
