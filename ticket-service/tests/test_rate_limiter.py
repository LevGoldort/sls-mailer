"""Tests for rate_limiter.py"""
import os
import pytest
import boto3
from moto import mock_aws

USERS_TABLE = "yallabalagan-users-test"


@pytest.fixture(autouse=True)
def env_setup(aws_credentials):
    os.environ["USERS_TABLE"] = USERS_TABLE


@pytest.fixture
def users_table(dynamodb_mock):
    table = dynamodb_mock.create_table(
        TableName=USERS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table


def _make_limiter():
    """Import fresh copy of rate_limiter (reset module-level _dynamodb cache)."""
    import importlib
    import utils.rate_limiter as rl
    rl._dynamodb = None  # reset cached resource
    importlib.reload(rl)
    return rl


class TestRateLimiter:
    def test_allows_within_limit(self, users_table):
        rl = _make_limiter()
        for _ in range(5):
            assert rl.is_rate_limited("1.2.3.4") is False

    def test_blocks_after_max_attempts(self, users_table):
        rl = _make_limiter()
        # MAX_ATTEMPTS defaults to 10
        for _ in range(10):
            rl.is_rate_limited("1.2.3.4")
        # 11th attempt should be blocked
        assert rl.is_rate_limited("1.2.3.4") is True

    def test_different_ips_are_independent(self, users_table):
        rl = _make_limiter()
        for _ in range(10):
            rl.is_rate_limited("1.2.3.4")
        # Different IP should not be rate-limited
        assert rl.is_rate_limited("5.6.7.8") is False

    def test_reset_clears_counter(self, users_table):
        rl = _make_limiter()
        for _ in range(10):
            rl.is_rate_limited("1.2.3.4")
        assert rl.is_rate_limited("1.2.3.4") is True

        rl.reset_rate_limit("1.2.3.4")
        # After reset, first attempt should be allowed
        assert rl.is_rate_limited("1.2.3.4") is False
