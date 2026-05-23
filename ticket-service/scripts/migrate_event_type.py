"""
Backfill event_type='internal' on all existing events that don't have the field.
Idempotent: skips events that already have event_type set.

Usage:
    python scripts/migrate_event_type.py dev
    python scripts/migrate_event_type.py prod
"""
import sys
import os
import boto3
from pathlib import Path

# Load .env.<env> if present
def load_env(env: str):
    env_file = Path(__file__).parent.parent / f'.env.{env}'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())


def run(env: str):
    load_env(env)

    profile = f'yallabalagan-{env}' if env != 'prod' else 'yallabalagan-prod'
    region = os.environ.get('AWS_REGION', 'eu-north-1')
    table_name = os.environ.get('EVENTS_TABLE', 'yallabalagan-events')

    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    print(f"Scanning {table_name} (profile={profile})...")

    updated = 0
    skipped = 0
    errors = 0

    scan_kwargs = {}
    while True:
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])

        for item in items:
            pk = item.get('PK', '')
            if not pk.startswith('EVENT#'):
                continue
            if item.get('SK') != 'METADATA':
                continue

            if item.get('event_type'):
                skipped += 1
                continue

            event_id = item.get('event_id')
            if not event_id:
                continue

            try:
                table.update_item(
                    Key={'PK': pk, 'SK': 'METADATA'},
                    UpdateExpression='SET event_type = :et',
                    ConditionExpression='attribute_not_exists(event_type)',
                    ExpressionAttributeValues={':et': 'internal'},
                )
                print(f"  Backfilled event_type=internal for {event_id}")
                updated += 1
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                # Already set by a concurrent run — safe to skip
                skipped += 1
            except Exception as e:
                print(f"  ERROR on {event_id}: {e}")
                errors += 1

        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break
        scan_kwargs['ExclusiveStartKey'] = last_key

    print(f"\nDone. Updated={updated}, Skipped={skipped}, Errors={errors}")


if __name__ == '__main__':
    env = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    if env not in ('dev', 'prod'):
        print("Usage: python migrate_event_type.py [dev|prod]")
        sys.exit(1)
    run(env)
