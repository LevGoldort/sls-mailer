"""
Migrate merch orders from the donate-site DynamoDB + Notion into
the ticket-service yallabalagan-merchandise-orders table.

For each completed purchase in the old donations table:
  - Resolves the new product/performer via product_slug
  - Resolves fulfillment_status from the linked Notion order (Status != "New" → fulfilled)
  - Inserts a MerchandiseOrder record (idempotent: skips if order_id already exists)

Usage:
    python scripts/migrate_merch_orders.py dev [--dry-run]
    python scripts/migrate_merch_orders.py prod [--dry-run]

Required env vars (read from .env.dev / .env.prod at repo root):
    NOTION_TOKEN                          Notion API token
    ORDERS_DB_ID or NOTION_DATABASE_ID_ORDERS   Notion Orders database ID
    DYNAMODB_TABLE or SOURCE_TABLE        Old donations DynamoDB table name
"""
import sys
import os
import json
import uuid
import requests
import boto3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from boto3.dynamodb.conditions import Attr


NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# ── Env / config ─────────────────────────────────────────────────────────────

def load_env(env: str):
    env_file = Path(__file__).parent.parent.parent / f'.env.{env}'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())


def notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def rich_text_value(prop: dict) -> str:
    parts = prop.get('rich_text', []) or prop.get('title', [])
    return "".join(t.get('plain_text', '') for t in parts)


# ── Notion ────────────────────────────────────────────────────────────────────

def fetch_all_notion_pages(token: str, database_id: str) -> list:
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = notion_headers(token)
    pages, payload = [], {}
    while True:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"  Notion API error {resp.status_code}: {resp.text}")
            break
        data = resp.json()
        pages.extend(data.get('results', []))
        cursor = data.get('next_cursor')
        if not cursor:
            break
        payload = {'start_cursor': cursor}
    return pages


def build_notion_order_status_map(token: str, orders_db_id: str) -> dict:
    """Returns {order_id_str: notion_status_str} for all Notion orders."""
    print(f"  Fetching Notion orders from {orders_db_id}...")
    pages = fetch_all_notion_pages(token, orders_db_id)
    status_map = {}
    for page in pages:
        props = page.get('properties', {})
        order_id = rich_text_value(props.get('ID', {}))
        status = props.get('Status', {}).get('select', {}) or {}
        status_name = status.get('name', 'New')
        if order_id:
            status_map[order_id] = status_name
    print(f"  Found {len(status_map)} Notion orders")
    return status_map


# ── DynamoDB helpers ──────────────────────────────────────────────────────────

def scan_all(table, filter_expression=None) -> list:
    items, kwargs = [], {}
    if filter_expression is not None:
        kwargs['FilterExpression'] = filter_expression
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get('Items', []))
        last_key = resp.get('LastEvaluatedKey')
        if not last_key:
            break
        kwargs['ExclusiveStartKey'] = last_key
    return items


def build_product_slug_map(products_table) -> dict:
    """Returns {slug: {product_id, performer_id}} for all products in new table."""
    items = scan_all(products_table)
    return {
        item['slug']: {
            'product_id': item['product_id'],
            'performer_id': item.get('performer_id', ''),
        }
        for item in items
        if item.get('slug') and item.get('product_id')
    }


def build_existing_order_ids(merch_table) -> set:
    """Returns set of existing order_ids in the merch orders table (for idempotency)."""
    items = scan_all(merch_table, filter_expression=Attr('order_id').exists())
    return {item['order_id'] for item in items if item.get('order_id')}


def unix_to_iso(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


def build_merch_order_item(purchase: dict, product_info: dict, fulfillment_status: str) -> dict:
    order_id = f"merch-{purchase['purchase_id']}"
    created_at = unix_to_iso(purchase.get('created_at', 0))
    buyer_email = purchase.get('buyer_email', '')

    try:
        amount = float(str(purchase.get('amount', '0')))
    except (ValueError, TypeError):
        amount = 0.0

    payment_method = purchase.get('payment_method', 'allpay').lower()
    if payment_method not in ('allpay', 'mock', 'telegram'):
        payment_method = 'allpay'

    item = {
        'PK': f'MERCH_ORDER#{order_id}',
        'SK': 'METADATA',
        'order_id': order_id,
        'product_id': product_info['product_id'],
        'product_slug': purchase.get('product_slug', ''),
        'performer_id': product_info['performer_id'],
        'buyer': {
            'name': purchase.get('buyer_name', ''),
            'email': buyer_email,
        },
        'buyer_email': buyer_email,
        'amount_ils': Decimal(str(amount)),
        'payment_method': payment_method,
        'status': 'completed',
        'fulfillment_status': fulfillment_status,
        'created_at': created_at,
        # GSI keys
        'GSI1PK': buyer_email,
        'GSI1SK': created_at,
        'GSI2PK': f"PRODUCT#{product_info['product_id']}",
        'GSI2SK': created_at,
    }

    if purchase.get('payment_id'):
        item['payment_id'] = purchase['payment_id']
    if purchase.get('buyer_telegram'):
        item['buyer']['telegram'] = purchase['buyer_telegram']
    if purchase.get('buyer_phone'):
        item['buyer']['phone'] = purchase['buyer_phone']

    return item


# ── Main ──────────────────────────────────────────────────────────────────────

def run(env: str, dry_run: bool):
    load_env(env)

    # NOTION_TOKEN_DONATE in .env.prod is the same token the Lambda uses as NOTION_TOKEN
    notion_token = (
        os.environ.get('NOTION_TOKEN')
        or os.environ.get('NOTION_TOKEN_DONATE')
    )
    orders_db_id = (
        os.environ.get('ORDERS_DB_ID')
        or os.environ.get('NOTION_DATABASE_ID_ORDERS')
    )
    # Old purchases table — use SOURCE_TABLE or fall back to the real table name
    # (DYNAMODB_TABLE in .env.prod points to events table — don't use it here)
    source_table_name = os.environ.get('SOURCE_TABLE', 'yallabalagan-purchases')

    if not notion_token:
        print("ERROR: NOTION_TOKEN or NOTION_TOKEN_DONATE must be set")
        sys.exit(1)
    if not orders_db_id:
        print("ERROR: ORDERS_DB_ID or NOTION_DATABASE_ID_ORDERS must be set")
        sys.exit(1)

    profile = os.environ.get('AWS_PROFILE') or ('prod' if env == 'prod' else f'yallabalagan-{env}')
    region = os.environ.get('AWS_REGION', 'eu-north-1')
    products_table_name = os.environ.get('PRODUCTS_TABLE', 'yallabalagan-products')
    merch_table_name = os.environ.get('MERCHANDISE_ORDERS_TABLE', 'yallabalagan-merchandise-orders')

    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb', region_name=region)

    source_table = dynamodb.Table(source_table_name)
    products_table = dynamodb.Table(products_table_name)
    merch_table = dynamodb.Table(merch_table_name)

    if dry_run:
        print("*** DRY RUN — no writes will happen ***\n")

    # ── Step 1: Notion order statuses ─────────────────────────────────────────
    print("=== Step 1: Fetch Notion order statuses ===")
    notion_status_map = build_notion_order_status_map(notion_token, orders_db_id)

    # ── Step 2: New product slug map ──────────────────────────────────────────
    print(f"\n=== Step 2: Load products from {products_table_name} ===")
    slug_to_product = build_product_slug_map(products_table)
    print(f"  Found {len(slug_to_product)} products")

    # ── Step 3: Existing merch order IDs (idempotency) ────────────────────────
    print(f"\n=== Step 3: Load existing merch order IDs from {merch_table_name} ===")
    existing_ids = build_existing_order_ids(merch_table)
    print(f"  Found {len(existing_ids)} existing merch orders")

    # ── Step 4: Scan old purchases ────────────────────────────────────────────
    print(f"\n=== Step 4: Scan old purchases from {source_table_name} ===")
    all_purchases = scan_all(source_table, filter_expression=Attr('status').eq('completed'))
    print(f"  Found {len(all_purchases)} completed purchases")

    # ── Step 5: Migrate ───────────────────────────────────────────────────────
    print(f"\n=== Step 5: Migrate ===")
    inserted = skipped_exists = skipped_no_product = errors = 0

    for purchase in all_purchases:
        purchase_id = purchase.get('purchase_id', '')
        product_slug = purchase.get('product_slug', '')
        order_id = f"merch-{purchase_id}"

        if order_id in existing_ids:
            print(f"  SKIP (exists): {order_id}")
            skipped_exists += 1
            continue

        product_info = slug_to_product.get(product_slug)
        if not product_info:
            print(f"  SKIP (product not found for slug='{product_slug}'): {order_id}")
            skipped_no_product += 1
            continue

        # fulfillment_status: look up via Notion order_id on the purchase
        old_order_id = purchase.get('order_id', '')
        if old_order_id and old_order_id in notion_status_map:
            notion_status = notion_status_map[old_order_id]
            fulfillment_status = 'new' if notion_status == 'New' else 'fulfilled'
        else:
            fulfillment_status = 'new'

        try:
            item = build_merch_order_item(purchase, product_info, fulfillment_status)
            buyer_name = purchase.get('buyer_name', '')
            print(
                f"  {'[DRY] ' if dry_run else ''}INSERT {order_id} "
                f"| {buyer_name} | {product_slug} | fulfillment={fulfillment_status}"
            )
            if not dry_run:
                merch_table.put_item(
                    Item=item,
                    ConditionExpression=Attr('PK').not_exists(),
                )
            inserted += 1
        except merch_table.meta.client.exceptions.ConditionalCheckFailedException:
            print(f"  SKIP (race/exists): {order_id}")
            skipped_exists += 1
        except Exception as exc:
            print(f"  ERROR {order_id}: {exc}")
            errors += 1

    print(f"\n{'DRY RUN ' if dry_run else ''}Summary:")
    print(f"  Inserted:              {inserted}")
    print(f"  Skipped (exists):      {skipped_exists}")
    print(f"  Skipped (no product):  {skipped_no_product}")
    print(f"  Errors:                {errors}")
    print(f"\nDone.")


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]

    env = args[0] if args else 'dev'
    if env not in ('dev', 'prod'):
        print("Usage: python scripts/migrate_merch_orders.py [dev|prod] [--dry-run]")
        sys.exit(1)

    dry_run = '--dry-run' in flags
    run(env, dry_run)
