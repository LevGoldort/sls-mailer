"""Data access layer for RefreshTokens table"""
import hashlib
import os
from typing import Optional

import boto3


def _get_table():
    region = os.environ.get("AWS_REGION", "eu-north-1")
    table_name = os.environ.get("REFRESH_TOKENS_TABLE", "yallabalagan-refresh-tokens")
    return boto3.resource("dynamodb", region_name=region).Table(table_name)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def store_refresh_token(
    token_hash: str,
    user_id: str,
    tenant_id: str,
    expires_at: int,
) -> None:
    _get_table().put_item(
        Item={
            "token_hash": token_hash,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "expires_at": expires_at,
        }
    )


def get_refresh_token(token_hash: str) -> Optional[dict]:
    response = _get_table().get_item(Key={"token_hash": token_hash})
    return response.get("Item")


def revoke_refresh_token(token_hash: str) -> None:
    _get_table().delete_item(Key={"token_hash": token_hash})
