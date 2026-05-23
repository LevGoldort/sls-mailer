"""
Migrate Performers (Talents) and Products from the donate-site Notion databases
into DynamoDB.

Idempotent:
  - Performers: skipped if slug already exists in yallabalagan-performers
  - Products:   skipped if slug already exists in yallabalagan-products

Usage:
    python scripts/migrate_from_donate_site.py dev
    python scripts/migrate_from_donate_site.py prod

Required env vars (in .env.dev / .env.prod at repo root):
    NOTION_TOKEN
    NOTION_DATABASE_ID_TALENTS
    NOTION_DATABASE_ID_PRODUCTS
"""
import sys
import os
import re
import uuid
import requests
import boto3
from datetime import datetime
from decimal import Decimal
from pathlib import Path


NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TENANT_ID = "yallabalagan"


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


def rich_text(prop: dict) -> str:
    parts = prop.get('rich_text', []) or prop.get('title', [])
    return "".join(t.get('plain_text', '') for t in parts)


def extract_youtube_id(url: str):
    if not url:
        return None
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def fetch_all_pages(token: str, database_id: str, filter_body: dict = None) -> list:
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = notion_headers(token)
    pages = []
    payload = filter_body or {}
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
        payload = dict(payload)
        payload['start_cursor'] = cursor
    return pages


def fetch_talents(token: str, db_id: str) -> list:
    filter_body = {
        "filter": {"property": "Status", "select": {"equals": "Active"}},
        "sorts": [{"property": "Order", "direction": "ascending"}],
    }
    pages = fetch_all_pages(token, db_id, filter_body)
    talents = []
    for page in pages:
        props = page['properties']
        name = rich_text(props.get('Name', {}))
        slug = rich_text(props.get('Slug', {}))
        if not name or not slug:
            continue
        featured_url = props.get('Featured_Video', {}).get('url', '')
        yt_id = extract_youtube_id(featured_url)
        talents.append({
            'notion_id': page['id'],
            'name': name,
            'slug': slug,
            'bio': rich_text(props.get('Bio', {})),
            'role': rich_text(props.get('Role', {})),
            'photo_url': props.get('Photo_URL', {}).get('url', '') or '',
            'instagram': props.get('Instagram', {}).get('url', '') or '',
            'telegram': props.get('Telegram', {}).get('url', '') or '',
            'youtube': props.get('YouTube', {}).get('url', '') or '',
            'facebook': props.get('Facebook', {}).get('url', '') or '',
            'youtube_embed': yt_id,
        })
    print(f"  Fetched {len(talents)} active talents from Notion")
    return talents


def fetch_products(token: str, db_id: str) -> list:
    filter_body = {
        "filter": {"property": "Status", "select": {"equals": "Active"}},
        "sorts": [{"property": "Order", "direction": "ascending"}],
    }
    pages = fetch_all_pages(token, db_id, filter_body)
    products = []
    for page in pages:
        props = page['properties']
        name = rich_text(props.get('Name', {}))
        slug = rich_text(props.get('Slug', {}))
        if not name or not slug:
            continue

        talent_ids = [r['id'] for r in props.get('Talent', {}).get('relation', [])]
        notion_type = props.get('Type', {}).get('select', {}).get('name', 'Individual')
        product_type = 'personal' if notion_type == 'Individual' else 'group'

        gallery_raw = rich_text(props.get('Gallery_URLs', {}))
        gallery_urls = [u.strip() for u in gallery_raw.split(',') if u.strip()] if gallery_raw else []

        products.append({
            'name': name,
            'slug': slug,
            'notion_talent_ids': talent_ids,
            'product_type': product_type,
            'short_description': rich_text(props.get('Short_Description', {})),
            'full_description': rich_text(props.get('Full_Description', {})),
            'what_you_get': rich_text(props.get('What_You_Get', {})),
            'price_ils': props.get('Price_ILS', {}).get('number', 0) or 0,
            'total_slots': props.get('Total_Slots', {}).get('number'),
            'sold_slots': int(props.get('Sold_Slots', {}).get('number', 0) or 0),
            'group_size': props.get('Group_Size', {}).get('number'),
            'photo_url': props.get('Photo_URL', {}).get('url', '') or '',
            'gallery_urls': gallery_urls,
        })
    print(f"  Fetched {len(products)} active products from Notion")
    return products


def get_existing_slugs(table, index_name: str, pk_attr: str) -> set:
    slugs = set()
    kwargs = {
        'ProjectionExpression': 'slug',
    }
    # Scan is acceptable for migration scripts on small tables
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get('Items', []):
            if 'slug' in item:
                slugs.add(item['slug'])
        last_key = resp.get('LastEvaluatedKey')
        if not last_key:
            break
        kwargs['ExclusiveStartKey'] = last_key
    return slugs


def build_performer_item(talent: dict, performer_id: str) -> dict:
    now = datetime.utcnow().isoformat()
    social = {}
    for key in ('instagram', 'telegram', 'youtube', 'facebook'):
        if talent.get(key):
            social[key] = talent[key]

    item = {
        'PK': f"PERFORMER#{performer_id}",
        'SK': 'METADATA',
        'performer_id': performer_id,
        'tenant_id': TENANT_ID,
        'name': talent['name'],
        'slug': talent['slug'],
        'bio': talent['bio'],
        'role': talent['role'],
        'photo_url': talent['photo_url'],
        'photos': [],
        'social': social,
        'status': 'active',
        'created_at': now,
        'updated_at': now,
        # GSI keys
        'GSI1PK': f'TENANT#{TENANT_ID}',
        'GSI1SK': f'active#{performer_id}',
    }
    if talent.get('youtube_embed'):
        item['youtube_embed'] = talent['youtube_embed']
    return item


def build_product_item(product: dict, product_id: str, performer_id: str) -> dict:
    now = datetime.utcnow().isoformat()
    item = {
        'PK': f"PRODUCT#{product_id}",
        'SK': 'METADATA',
        'product_id': product_id,
        'tenant_id': TENANT_ID,
        'performer_id': performer_id,
        'name': product['name'],
        'slug': product['slug'],
        'short_description': product['short_description'],
        'full_description': product['full_description'],
        'what_you_get': product['what_you_get'],
        'price_ils': Decimal(str(product['price_ils'])),
        'photo_url': product['photo_url'],
        'gallery_urls': product['gallery_urls'],
        'sold_slots': product['sold_slots'],
        'product_type': product['product_type'],
        'status': 'active',
        'created_at': now,
        'updated_at': now,
        # GSI keys
        'GSI1PK': f'PERFORMER#{performer_id}',
        'GSI1SK': now,
        'GSI2PK': 'active',
        'GSI2SK': now,
    }
    if product.get('total_slots') is not None:
        item['total_slots'] = product['total_slots']
    if product.get('group_size') is not None:
        item['group_size'] = product['group_size']
    return item


def run(env: str):
    load_env(env)

    token = os.environ.get('NOTION_TOKEN')
    talents_db = os.environ.get('NOTION_DATABASE_ID_TALENTS')
    products_db = os.environ.get('NOTION_DATABASE_ID_PRODUCTS')
    if not token or not talents_db or not products_db:
        print("ERROR: NOTION_TOKEN, NOTION_DATABASE_ID_TALENTS, and NOTION_DATABASE_ID_PRODUCTS must be set")
        sys.exit(1)

    profile = os.environ.get('AWS_PROFILE', 'prod' if env == 'prod' else f'yallabalagan-{env}')
    region = os.environ.get('AWS_REGION', 'eu-north-1')
    performers_table_name = os.environ.get('PERFORMERS_TABLE', 'yallabalagan-performers')
    products_table_name = os.environ.get('PRODUCTS_TABLE', 'yallabalagan-products')

    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb', region_name=region)
    performers_table = dynamodb.Table(performers_table_name)
    products_table = dynamodb.Table(products_table_name)

    # ── Performers ──────────────────────────────────────────────────────────
    print(f"\n=== Performers ===")
    print(f"Fetching talents from Notion ({talents_db})...")
    talents = fetch_talents(token, talents_db)

    print(f"Loading existing performer slugs from {performers_table_name}...")
    existing_performer_slugs = get_existing_slugs(performers_table, 'SlugIndex', 'slug')
    print(f"  Found {len(existing_performer_slugs)} existing performers")

    # notion_id → performer_id mapping (for products linking)
    notion_id_to_performer_id = {}  # type: dict

    p_inserted = p_skipped = p_errors = 0
    for talent in talents:
        if talent['slug'] in existing_performer_slugs:
            print(f"  SKIP (exists): {talent['name']} ({talent['slug']})")
            # Still need performer_id for product linking — query by slug
            try:
                resp = performers_table.query(
                    IndexName='SlugIndex',
                    KeyConditionExpression='slug = :s',
                    ExpressionAttributeValues={':s': talent['slug']},
                    Limit=1,
                )
                existing = resp.get('Items', [])
                if existing:
                    notion_id_to_performer_id[talent['notion_id']] = existing[0]['performer_id']
            except Exception:
                pass
            p_skipped += 1
            continue

        performer_id = str(uuid.uuid4())
        try:
            item = build_performer_item(talent, performer_id)
            performers_table.put_item(Item=item)
            notion_id_to_performer_id[talent['notion_id']] = performer_id
            print(f"  INSERT performer: {talent['name']} ({talent['slug']})")
            p_inserted += 1
        except Exception as exc:
            print(f"  ERROR performer {talent['name']}: {exc}")
            p_errors += 1

    print(f"Performers — Inserted={p_inserted}, Skipped={p_skipped}, Errors={p_errors}")

    # ── Products ─────────────────────────────────────────────────────────────
    print(f"\n=== Products ===")
    print(f"Fetching products from Notion ({products_db})...")
    products = fetch_products(token, products_db)

    print(f"Loading existing product slugs from {products_table_name}...")
    existing_product_slugs = get_existing_slugs(products_table, 'SlugIndex', 'slug')
    print(f"  Found {len(existing_product_slugs)} existing products")

    pr_inserted = pr_skipped = pr_errors = 0
    for product in products:
        if product['slug'] in existing_product_slugs:
            print(f"  SKIP (exists): {product['name']} ({product['slug']})")
            pr_skipped += 1
            continue

        # Resolve performer_id from first linked talent
        performer_id = ''
        for notion_tid in product.get('notion_talent_ids', []):
            if notion_tid in notion_id_to_performer_id:
                performer_id = notion_id_to_performer_id[notion_tid]
                break

        if not performer_id:
            print(f"  WARN: no performer found for product '{product['name']}' — using empty performer_id")

        product_id = str(uuid.uuid4())
        try:
            item = build_product_item(product, product_id, performer_id)
            products_table.put_item(Item=item)
            print(f"  INSERT product: {product['name']} ({product['slug']})")
            pr_inserted += 1
        except Exception as exc:
            print(f"  ERROR product {product['name']}: {exc}")
            pr_errors += 1

    print(f"Products — Inserted={pr_inserted}, Skipped={pr_skipped}, Errors={pr_errors}")
    print(f"\nDone.")


if __name__ == '__main__':
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    if env not in ('dev', 'prod'):
        print("Usage: python migrate_from_donate_site.py [dev|prod]")
        sys.exit(1)
    run(env)
