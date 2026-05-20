"""Unit tests for utils/refresh_token_service.py"""
import os
import time
import pytest
from moto import mock_aws
import boto3

TOKENS_TABLE = "yallabalagan-refresh-tokens-test"
TENANT = "yallabalagan"
USER_ID = "user-abc"


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ["JWT_SECRET"] = "test-secret-for-refresh-token-service"
    os.environ["REFRESH_TOKENS_TABLE"] = TOKENS_TABLE


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
def refresh_token():
    from utils.auth_jwt import generate_refresh_token
    return generate_refresh_token(user_id=USER_ID, tenant_id=TENANT)


class TestStoreRefreshToken:
    def test_store_persists_hashed_token(self, tokens_table, refresh_token):
        import hashlib
        from utils.refresh_token_service import store_refresh_token
        from repositories import token_repository

        store_refresh_token(refresh_token, USER_ID, TENANT)

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        record = token_repository.get_refresh_token(token_hash)
        assert record is not None
        assert record["user_id"] == USER_ID
        assert record["tenant_id"] == TENANT

    def test_store_sets_future_ttl(self, tokens_table, refresh_token):
        import hashlib
        from utils.refresh_token_service import store_refresh_token
        from repositories import token_repository

        store_refresh_token(refresh_token, USER_ID, TENANT)

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        record = token_repository.get_refresh_token(token_hash)
        assert record["expires_at"] > int(time.time())


class TestValidateRefreshToken:
    def test_validate_valid_token(self, tokens_table, refresh_token):
        from utils.refresh_token_service import store_refresh_token, validate_refresh_token

        store_refresh_token(refresh_token, USER_ID, TENANT)
        payload = validate_refresh_token(refresh_token)
        assert payload["sub"] == USER_ID
        assert payload["tenant_id"] == TENANT

    def test_validate_revoked_token_raises(self, tokens_table, refresh_token):
        from utils.auth_jwt import TokenInvalidError
        from utils.refresh_token_service import store_refresh_token, revoke_refresh_token, validate_refresh_token

        store_refresh_token(refresh_token, USER_ID, TENANT)
        revoke_refresh_token(refresh_token)

        with pytest.raises(TokenInvalidError):
            validate_refresh_token(refresh_token)

    def test_validate_never_stored_token_raises(self, tokens_table, refresh_token):
        from utils.auth_jwt import TokenInvalidError
        from utils.refresh_token_service import validate_refresh_token

        with pytest.raises(TokenInvalidError):
            validate_refresh_token(refresh_token)

    def test_validate_invalid_jwt_raises(self, tokens_table):
        from utils.auth_jwt import TokenInvalidError
        from utils.refresh_token_service import validate_refresh_token

        with pytest.raises(TokenInvalidError):
            validate_refresh_token("not.a.jwt")

    def test_validate_expired_jwt_raises(self, tokens_table):
        import jwt
        from datetime import datetime, timezone, timedelta
        from utils.auth_jwt import TokenExpiredError
        from utils.refresh_token_service import validate_refresh_token

        payload = {
            "sub": USER_ID,
            "tenant_id": TENANT,
            "type": "refresh",
            "iat": datetime.now(timezone.utc) - timedelta(days=10),
            "exp": datetime.now(timezone.utc) - timedelta(days=3),
        }
        expired_token = jwt.encode(payload, "test-secret-for-refresh-token-service", algorithm="HS256")

        with pytest.raises(TokenExpiredError):
            validate_refresh_token(expired_token)


class TestRevokeRefreshToken:
    def test_revoke_removes_from_db(self, tokens_table, refresh_token):
        import hashlib
        from utils.refresh_token_service import store_refresh_token, revoke_refresh_token
        from repositories import token_repository

        store_refresh_token(refresh_token, USER_ID, TENANT)
        revoke_refresh_token(refresh_token)

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        assert token_repository.get_refresh_token(token_hash) is None

    def test_revoke_nonexistent_is_idempotent(self, tokens_table, refresh_token):
        from utils.refresh_token_service import revoke_refresh_token
        revoke_refresh_token(refresh_token)  # should not raise
