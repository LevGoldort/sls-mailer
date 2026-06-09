"""
One-time migration: write TICKET#{code} lookup items for all existing orders.

Usage:
    AWS_PROFILE=yallabalagan-prod python scripts/migrate_ticket_lookups.py
    AWS_PROFILE=yallabalagan-dev TABLE_NAME=yallabalagan-orders python scripts/migrate_ticket_lookups.py
"""
import os
import boto3

TABLE_NAME = os.environ.get('TABLE_NAME', 'yallabalagan-orders')
REGION = 'eu-north-1'


def migrate():
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    scan_kwargs = {}
    orders_seen = 0
    lookups_written = 0

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            if not item.get('PK', '').startswith('ORDER#'):
                continue
            orders_seen += 1
            order_id = item.get('order_id')
            if not order_id:
                continue
            for qr in item.get('qr_codes', []):
                code = qr.get('code')
                if code:
                    table.put_item(Item={
                        'PK': f'TICKET#{code}',
                        'SK': 'LOOKUP',
                        'order_id': order_id,
                    })
                    lookups_written += 1

        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    print(f"Done: {orders_seen} orders scanned, {lookups_written} lookup items written")


if __name__ == '__main__':
    print(f"Migrating table: {TABLE_NAME}")
    migrate()
