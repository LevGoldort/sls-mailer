"""Data access layer for Tenants table"""
import os
from typing import List, Optional
from datetime import datetime

import boto3

from models.tenant import Tenant


def _get_table():
    region = os.environ.get("AWS_REGION", "eu-north-1")
    table_name = os.environ.get("TENANTS_TABLE", "yallabalagan-tenants")
    return boto3.resource("dynamodb", region_name=region).Table(table_name)


def create_tenant(tenant: Tenant) -> Tenant:
    _get_table().put_item(Item=tenant.to_dynamodb_item())
    return tenant


def get_tenant_by_id(tenant_id: str) -> Optional[Tenant]:
    response = _get_table().get_item(
        Key={"PK": f"TENANT#{tenant_id}", "SK": "METADATA"}
    )
    item = response.get("Item")
    return Tenant.from_dynamodb_item(item) if item else None


def get_tenant_by_slug(slug: str) -> Optional[Tenant]:
    response = _get_table().query(
        IndexName="SlugIndex",
        KeyConditionExpression="slug = :slug",
        ExpressionAttributeValues={":slug": slug},
        Limit=1,
    )
    items = response.get("Items", [])
    return Tenant.from_dynamodb_item(items[0]) if items else None


def list_tenants() -> List[Tenant]:
    response = _get_table().scan()
    return [Tenant.from_dynamodb_item(item) for item in response.get("Items", [])]


def update_tenant(tenant: Tenant) -> Tenant:
    tenant.updated_at = datetime.utcnow().isoformat()
    _get_table().put_item(Item=tenant.to_dynamodb_item())
    return tenant
