"""DynamoDB-backed fixed-window rate limiter for login attempts."""
import os
import time
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_USERS_TABLE = os.environ.get("USERS_TABLE", "yallabalagan-users")
_MAX_ATTEMPTS = int(os.environ.get("LOGIN_RATE_LIMIT_MAX", "10"))
_WINDOW_SECONDS = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW", "300"))  # 5 min

_dynamodb = None


def _table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(_USERS_TABLE)


def is_rate_limited(identifier: str) -> bool:
    """Return True if the identifier has exceeded the login attempt limit."""
    pk = f"RATELIMIT#{identifier}"
    now = int(time.time())
    window_ttl = now + _WINDOW_SECONDS

    try:
        resp = _table().update_item(
            Key={"PK": pk, "SK": "AUTH"},
            UpdateExpression=(
                "SET #cnt = if_not_exists(#cnt, :zero) + :one, "
                "#ttl = if_not_exists(#ttl, :exp)"
            ),
            ExpressionAttributeNames={"#cnt": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":exp": window_ttl,
            },
            ReturnValues="UPDATED_NEW",
        )
        count = int(resp["Attributes"]["count"])
        if count > _MAX_ATTEMPTS:
            logger.warning("Rate limit exceeded for identifier: %s (count=%d)", identifier, count)
            return True
        return False
    except ClientError as e:
        logger.error("Rate limiter error (allowing request): %s", e)
        return False  # fail open — don't block on DynamoDB errors


def reset_rate_limit(identifier: str) -> None:
    """Remove rate limit counter after successful auth."""
    try:
        _table().delete_item(Key={"PK": f"RATELIMIT#{identifier}", "SK": "AUTH"})
    except ClientError as e:
        logger.warning("Failed to reset rate limit: %s", e)
