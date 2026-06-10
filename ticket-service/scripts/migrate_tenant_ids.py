#!/usr/bin/env python3
"""
Migration script: Backfill tenant_id on pre-multi-tenant records
=================================================================
Scans Location, Coupon, Show, Influencer, and social connection tables
and stamps tenant_id='yallabalagan' on every item that is missing it.

Usage:
    # Dry-run (no writes)
    python scripts/migrate_tenant_ids.py --dry-run

    # Live run
    AWS_PROFILE=yallabalagan-dev python scripts/migrate_tenant_ids.py

Environment variables:
    AWS_PROFILE        AWS profile (optional)
    AWS_REGION         AWS region (default: eu-north-1)
    TENANT_ID          Tenant ID to stamp (default: yallabalagan)
"""
import argparse
import os
import sys

import boto3
from boto3.dynamodb.conditions import Attr

REGION = os.environ.get("AWS_REGION", "eu-north-1")
TENANT_ID = os.environ.get("TENANT_ID", "yallabalagan")

TABLES = [
    os.environ.get("LOCATIONS_TABLE",  "yallabalagan-locations"),
    os.environ.get("COUPONS_TABLE",    "yallabalagan-coupons"),
    os.environ.get("SHOWS_TABLE",      "yallabalagan-shows"),
    os.environ.get("INFLUENCERS_TABLE","yallabalagan-influencers"),
    os.environ.get("INSTAGRAM_TABLE",  "yallabalagan-instagram"),
    os.environ.get("TIKTOK_TABLE",     "yallabalagan-tiktok"),
    os.environ.get("YOUTUBE_TABLE",    "yallabalagan-youtube"),
]


def _get_dynamodb():
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile, region_name=REGION) if profile else boto3.Session(region_name=REGION)
    return session.resource("dynamodb")


def migrate_table(table_resource, dry_run: bool) -> int:
    """Scan table, update items missing tenant_id. Returns count of items updated."""
    paginator = table_resource.meta.client.get_paginator("scan")
    pages = paginator.paginate(
        TableName=table_resource.name,
        FilterExpression="attribute_not_exists(tenant_id)",
    )

    updated = 0
    for page in pages:
        for item in page.get("Items", []):
            pk = item.get("PK", "?")
            sk = item.get("SK", "?")
            print(f"  {'[DRY]' if dry_run else '[SET]'} {table_resource.name} PK={pk} SK={sk}")
            if not dry_run:
                table_resource.update_item(
                    Key={"PK": item["PK"], "SK": item["SK"]},
                    UpdateExpression="SET tenant_id = :tid",
                    ConditionExpression=Attr("tenant_id").not_exists(),
                    ExpressionAttributeValues={":tid": TENANT_ID},
                )
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill tenant_id on legacy records")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()

    dynamodb = _get_dynamodb()
    total = 0

    for table_name in TABLES:
        print(f"\nTable: {table_name}")
        try:
            table = dynamodb.Table(table_name)
            count = migrate_table(table, args.dry_run)
            print(f"  → {count} item(s) {'would be' if args.dry_run else 'were'} updated")
            total += count
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)

    print(f"\nDone. Total: {total} item(s) {'would be' if args.dry_run else 'were'} updated.")
    if args.dry_run:
        print("Re-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
