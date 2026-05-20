"""Data access layer for Users table"""
import os
from typing import List, Optional

import boto3

from models.user import User


def _get_table():
    region = os.environ.get("AWS_REGION", "eu-north-1")
    table_name = os.environ.get("USERS_TABLE", "yallabalagan-users")
    return boto3.resource("dynamodb", region_name=region).Table(table_name)


def create_user(user: User) -> User:
    _get_table().put_item(Item=user.to_dynamodb_item())
    return user


def get_user_by_id(user_id: str, tenant_id: str) -> Optional[User]:
    response = _get_table().get_item(
        Key={
            "PK": f"TENANT#{tenant_id}#USER#{user_id}",
            "SK": "METADATA",
        }
    )
    item = response.get("Item")
    return User.from_dynamodb_item(item) if item else None


def get_user_by_email(email: str, tenant_id: str) -> Optional[User]:
    response = _get_table().query(
        IndexName="EmailIndex",
        KeyConditionExpression="email = :email",
        ExpressionAttributeValues={":email": email},
    )
    items = response.get("Items", [])
    # EmailIndex is shared across tenants in SaaS; filter by tenant_id
    for item in items:
        if item.get("tenant_id") == tenant_id:
            return User.from_dynamodb_item(item)
    return None


def list_users_by_tenant(tenant_id: str) -> List[User]:
    response = _get_table().query(
        IndexName="TenantIndex",
        KeyConditionExpression="tenant_id = :tenant_id",
        ExpressionAttributeValues={":tenant_id": tenant_id},
    )
    return [User.from_dynamodb_item(item) for item in response.get("Items", [])]


def update_user(user: User) -> User:
    _get_table().put_item(Item=user.to_dynamodb_item())
    return user


def deactivate_user(user_id: str, tenant_id: str) -> Optional[User]:
    from datetime import datetime

    response = _get_table().update_item(
        Key={
            "PK": f"TENANT#{tenant_id}#USER#{user_id}",
            "SK": "METADATA",
        },
        UpdateExpression="SET #status = :inactive, updated_at = :now",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":inactive": "inactive",
            ":now": datetime.utcnow().isoformat(),
        },
        ConditionExpression="attribute_exists(PK)",
        ReturnValues="ALL_NEW",
    )
    item = response.get("Attributes")
    return User.from_dynamodb_item(item) if item else None
