#!/usr/bin/env python3
"""
Migration script: Phase 2 User Management
==========================================
1. Creates the first admin user (idempotent — skips if already exists).
2. Assigns owner_id + tenant_id to all events that lack them.

Usage:
    # Interactive
    python scripts/migrate_user_management.py

    # Non-interactive (CI/CD)
    ADMIN_EMAIL=admin@example.com \
    ADMIN_NAME="Admin User" \
    ADMIN_PASSWORD=securepass123 \
    AWS_PROFILE=yallabalagan-dev \
    python scripts/migrate_user_management.py

Environment variables:
    ADMIN_EMAIL      New admin email (prompted if missing)
    ADMIN_NAME       New admin name  (prompted if missing)
    ADMIN_PASSWORD   New admin password (prompted if missing)
    USERS_TABLE      DynamoDB table name (default: yallabalagan-users)
    EVENTS_TABLE     DynamoDB table name (default: yallabalagan-events)
    AWS_REGION       AWS region (default: eu-north-1)
    AWS_PROFILE      AWS profile (optional)
"""
import getpass
import os
import sys
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Attr

# Allow running from repo root or from ticket-service/
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # ticket-service/
sys.path.insert(0, _ROOT)

from models.user import User, TENANT_ID
from utils.auth_password import hash_password


# ── Config ────────────────────────────────────────────────────────────────────

REGION       = os.environ.get("AWS_REGION", "eu-north-1")
USERS_TABLE  = os.environ.get("USERS_TABLE",  "yallabalagan-users")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "yallabalagan-events")


def _dynamodb():
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.resource("dynamodb", region_name=REGION)


# ── Step 1: Create first admin user ──────────────────────────────────────────

def _prompt(var: str, label: str, secret: bool = False) -> str:
    value = os.environ.get(var, "").strip()
    if value:
        return value
    if secret:
        return getpass.getpass(f"{label}: ")
    return input(f"{label}: ").strip()


def _find_existing_admin(table) -> Optional[dict]:
    """Scan UsersTable for any active admin (idempotency check)."""
    resp = table.scan(
        FilterExpression=Attr("role").eq("admin") & Attr("status").eq("active"),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def create_admin_user(db) -> User:
    users_table = db.Table(USERS_TABLE)

    existing = _find_existing_admin(users_table)
    if existing:
        user = User.from_dynamodb_item(existing)
        print(f"  ✓ Admin user already exists: {user.email} ({user.user_id}) — skipping creation.")
        return user

    print("\n── Create first admin user ──────────────────────────────────────")
    email    = _prompt("ADMIN_EMAIL",    "Admin email")
    name     = _prompt("ADMIN_NAME",     "Admin name")
    password = _prompt("ADMIN_PASSWORD", "Admin password", secret=True)

    if len(password) < 8:
        sys.exit("Error: password must be at least 8 characters.")

    user = User.create(
        email=email.lower(),
        password_hash=hash_password(password),
        name=name,
        role="admin",
        tenant_id=TENANT_ID,
    )
    users_table.put_item(Item=user.to_dynamodb_item())
    print(f"  ✓ Created admin user: {user.email} ({user.user_id})")
    return user


# ── Step 2: Backfill events ──────────────────────────────────────────────────

def _scan_all(table, **kwargs) -> list:
    """Full table scan with pagination."""
    items = []
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def backfill_events(db, admin_user: User) -> tuple[int, int]:
    """
    Assign owner_id + tenant_id to events that lack them.
    Returns (updated, skipped) counts.
    """
    events_table = db.Table(EVENTS_TABLE)

    # Only fetch events missing owner_id — saves write units
    items = _scan_all(
        events_table,
        FilterExpression=Attr("PK").begins_with("EVENT#") & Attr("owner_id").not_exists(),
    )

    updated = skipped = 0
    for item in items:
        pk = item.get("PK", "")
        if not pk.startswith("EVENT#"):
            skipped += 1
            continue

        events_table.update_item(
            Key={"PK": pk, "SK": "METADATA"},
            UpdateExpression="SET owner_id = :oid, tenant_id = :tid",
            ExpressionAttributeValues={
                ":oid": admin_user.user_id,
                ":tid": TENANT_ID,
            },
            ConditionExpression=Attr("owner_id").not_exists(),  # idempotent guard
        )
        updated += 1
        print(f"  ✓ Event {item.get('event_id', pk)} → owner={admin_user.user_id}")

    return updated, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("═" * 60)
    print("YallaBalagan — User Management Migration")
    print(f"  Region:       {REGION}")
    print(f"  Users table:  {USERS_TABLE}")
    print(f"  Events table: {EVENTS_TABLE}")
    print("═" * 60)

    db = _dynamodb()

    print("\n[1/2] Admin user")
    admin = create_admin_user(db)

    print("\n[2/2] Backfill events")
    updated, skipped = backfill_events(db, admin)
    print(f"  ✓ Events updated: {updated}, already owned: {skipped}")

    print("\n✅ Migration complete.")
    print(f"   Admin user ID: {admin.user_id}")
    print(f"   Admin email:   {admin.email}")


if __name__ == "__main__":
    main()
