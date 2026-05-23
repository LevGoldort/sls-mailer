"""
Migrate external events from the events-site Notion database into DynamoDB.

Each Notion page becomes an Event with event_type='external' and the Notion
URL as external_url.  Idempotent: pages whose external_url already exists in
DynamoDB are skipped.

Usage:
    python scripts/migrate_from_events_site.py dev
    python scripts/migrate_from_events_site.py prod

Required env vars (in .env.dev / .env.prod at repo root):
    NOTION_TOKEN
    NOTION_DATABASE_ID_EVENTS
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


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[\s\-]+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    return text[:80]


def fetch_notion_events(token: str, database_id: str) -> list:
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = notion_headers(token)
    events = []
    payload = {"sorts": [{"property": "Date", "direction": "ascending"}]}

    while True:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"  Notion API error {resp.status_code}: {resp.text}")
            break

        data = resp.json()
        for page in data.get('results', []):
            props = page['properties']

            title_prop = props.get('Name', {}).get('title', [])
            title = title_prop[0]['text']['content'] if title_prop else ''
            if not title:
                continue

            date_prop = props.get('Date', {}).get('date')
            date_str = date_prop.get('start') if date_prop else None
            if not date_str:
                continue

            external_url = props.get('URL', {}).get('url', '')
            if not external_url:
                continue

            cover = page.get('cover')
            image_url = None
            if cover:
                if cover['type'] == 'external':
                    image_url = cover['external']['url']
                elif cover['type'] == 'file':
                    image_url = cover['file']['url']

            # Normalise date to ISO with time if it's date-only
            if 'T' not in date_str:
                date_str = date_str + 'T00:00:00Z'

            events.append({
                'title': title,
                'date': date_str,
                'external_url': external_url,
                'image_url': image_url,
            })

        cursor = data.get('next_cursor')
        if not cursor:
            break
        payload['start_cursor'] = cursor

    print(f"  Fetched {len(events)} events from Notion")
    return events


def get_existing_external_urls(table) -> set:
    existing = set()
    kwargs = {
        'FilterExpression': 'event_type = :et AND attribute_exists(external_url)',
        'ExpressionAttributeValues': {':et': 'external'},
        'ProjectionExpression': 'external_url',
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get('Items', []):
            url = item.get('external_url')
            if url:
                existing.add(url)
        last_key = resp.get('LastEvaluatedKey')
        if not last_key:
            break
        kwargs['ExclusiveStartKey'] = last_key
    return existing


def build_event_item(event: dict) -> dict:
    now = datetime.utcnow().isoformat()
    event_id = str(uuid.uuid4())
    slug = slugify(event['title'])

    item = {
        'PK': f"EVENT#{event_id}",
        'SK': 'METADATA',
        'event_id': event_id,
        'tenant_id': TENANT_ID,
        'title': event['title'],
        'description': '',
        'date': event['date'],
        'location_id': '',
        'ticket_types': [],
        'currency': 'ILS',
        'images': [event['image_url']] if event.get('image_url') else [],
        'status': 'active',
        'event_type': 'external',
        'external_url': event['external_url'],
        'tags': [],
        'created_at': now,
        'updated_at': now,
        'refund_policy': {'enabled': False, 'hours_before': 0},
        # GSI for date-sorted queries
        'GSI1PK': 'EVENT',
        'GSI1SK': event['date'],
    }
    if slug:
        item['slug'] = slug
    return item


def run(env: str):
    load_env(env)

    token = os.environ.get('NOTION_TOKEN')
    database_id = os.environ.get('NOTION_DATABASE_ID_EVENTS')
    if not token or not database_id:
        print("ERROR: NOTION_TOKEN and NOTION_DATABASE_ID_EVENTS must be set")
        sys.exit(1)

    profile = os.environ.get('AWS_PROFILE', 'prod' if env == 'prod' else f'yallabalagan-{env}')
    region = os.environ.get('AWS_REGION', 'eu-north-1')
    events_table_name = os.environ.get('EVENTS_TABLE', 'yallabalagan-events')

    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb', region_name=region)
    table = dynamodb.Table(events_table_name)

    print(f"Fetching events from Notion database {database_id}...")
    notion_events = fetch_notion_events(token, database_id)

    print(f"Loading existing external events from {events_table_name}...")
    existing_urls = get_existing_external_urls(table)
    print(f"  Found {len(existing_urls)} existing external events")

    inserted = skipped = errors = 0

    for event in notion_events:
        url = event['external_url']
        if url in existing_urls:
            print(f"  SKIP (exists): {event['title']}")
            skipped += 1
            continue

        try:
            item = build_event_item(event)
            table.put_item(Item=item)
            print(f"  INSERT: {event['title']} ({event['date'][:10]})")
            inserted += 1
        except Exception as exc:
            print(f"  ERROR: {event['title']}: {exc}")
            errors += 1

    print(f"\nDone. Inserted={inserted}, Skipped={skipped}, Errors={errors}")


if __name__ == '__main__':
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    if env not in ('dev', 'prod'):
        print("Usage: python migrate_from_events_site.py [dev|prod]")
        sys.exit(1)
    run(env)
