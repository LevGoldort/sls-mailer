#!/usr/bin/env python3
"""
Lambda function to automatically update event statuses
Runs every hour via EventBridge schedule
Marks events as 'completed' if event_date + 1 hour < now
"""
import os
import json
import boto3
from datetime import datetime, timedelta, timezone

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'yallabalagan-events')
table = dynamodb.Table(TABLE_NAME)


def is_event_past(event_date_str):
    """Check if event is past (event_date + 30 minutes < now)"""
    try:
        import pytz

        # Parse as naive datetime, then localize to Israel timezone
        naive_dt = datetime.fromisoformat(event_date_str.replace('Z', ''))
        israel_tz = pytz.timezone('Asia/Jerusalem')
        event_dt = israel_tz.localize(naive_dt)
        event_end_time = event_dt + timedelta(minutes=30)  # Fixed: 30 minutes
        now = datetime.now(israel_tz)
        return event_end_time <= now
    except Exception as e:
        print(f"Error parsing date {event_date_str}: {e}")
        return False


def get_all_events():
    """Fetch all events from DynamoDB"""
    try:
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={
                ':pk': 'EVENT'
            }
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"Error fetching events: {e}")
        return []


def update_event_status(event_id, new_status):
    """Update event status in DynamoDB"""
    try:
        table.update_item(
            Key={
                'PK': f'EVENT#{event_id}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': new_status,
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
        print(f"Updated event {event_id} status to {new_status}")
        return True
    except Exception as e:
        print(f"Error updating event {event_id}: {e}")
        return False


def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        print("Starting event status update...")
        start_time = datetime.now()

        # Get all events
        events = get_all_events()
        print(f"Found {len(events)} total events")

        # Find and update past events that are still active
        updated_count = 0
        for event_data in events:
            event_id = event_data.get('event_id')
            event_date = event_data.get('date')
            current_status = event_data.get('status', 'active')

            # Only update active events that have passed
            if current_status == 'active' and is_event_past(event_date):
                print(f"Event {event_id} ({event_data.get('title')}) has passed - updating status")
                if update_event_status(event_id, 'completed'):
                    updated_count += 1

        duration = (datetime.now() - start_time).total_seconds()

        result = {
            'status': 'success',
            'message': f'Event status update completed in {duration:.2f}s',
            'total_events': len(events),
            'updated_count': updated_count,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        print(json.dumps(result))
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': str(e)
            })
        }
