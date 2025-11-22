"""
Lambda Function: newsletter-tracker
Tracks email opens and clicks

Environment Variables:
- CAMPAIGNS_TABLE: DynamoDB table for campaigns
- EVENTS_TABLE: DynamoDB table for events
- SECRET_KEY: Secret key for HMAC token generation

Endpoints:
- GET /track/open/{campaign_id}/{email_hash} - Track email open
- GET /track/click/{campaign_id}/{email_hash}?url=XXX - Track click and redirect
"""

import json
import os
import base64
from datetime import datetime
from urllib.parse import unquote
import boto3
from boto3.dynamodb.conditions import Key

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CAMPAIGNS_TABLE = os.environ['CAMPAIGNS_TABLE']
EVENTS_TABLE = os.environ['EVENTS_TABLE']
SECRET_KEY = os.environ['SECRET_KEY']

# DynamoDB tables
campaigns_table = dynamodb.Table(CAMPAIGNS_TABLE)
events_table = dynamodb.Table(EVENTS_TABLE)

# 1x1 transparent GIF in base64
TRACKING_GIF = base64.b64decode(
    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
)


def record_event_deduplicated(campaign_id, email_hash, event_type, metadata=None):
    """Record event in DynamoDB with deduplication"""
    timestamp = int(datetime.utcnow().timestamp())
    event_id = f"{email_hash}#{event_type}"

    # Check if event already exists
    try:
        response = events_table.get_item(
            Key={
                'campaign_id': campaign_id,
                'event_id': event_id
            }
        )
        if 'Item' in response:
            print(f"Event {event_id} already exists for campaign {campaign_id}")
            return False  # Already recorded
    except Exception as e:
        print(f"Error checking event: {str(e)}")

    # Record new event
    event = {
        'campaign_id': campaign_id,
        'event_id': event_id,
        'email_hash': email_hash,
        'event': event_type,
        'timestamp': timestamp
    }

    if metadata:
        event['metadata'] = metadata

    try:
        events_table.put_item(Item=event)
        return True
    except Exception as e:
        print(f"Error recording event: {str(e)}")
        return False


def update_campaign_count(campaign_id, field):
    """Update campaign counter"""
    try:
        campaigns_table.update_item(
            Key={'campaign_id': campaign_id},
            UpdateExpression=f'ADD {field} :inc SET updated_at = :updated_at',
            ExpressionAttributeValues={
                ':inc': 1,
                ':updated_at': int(datetime.utcnow().timestamp())
            }
        )
        return True
    except Exception as e:
        print(f"Error updating campaign count: {str(e)}")
        return False


def track_open(event):
    """Track email open"""
    try:
        campaign_id = event['pathParameters']['campaign_id']
        email_hash = event['pathParameters']['email_hash']

        print(f"Tracking open: campaign={campaign_id}, email_hash={email_hash}")

        # Record event (with deduplication)
        if record_event_deduplicated(campaign_id, email_hash, 'opened'):
            # Update campaign counter only if new event
            update_campaign_count(campaign_id, 'opened_count')
            print(f"Recorded new open event for {email_hash}")
        else:
            print(f"Open already recorded for {email_hash}")

        # Return 1x1 transparent GIF
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'image/gif',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            },
            'body': base64.b64encode(TRACKING_GIF).decode('utf-8'),
            'isBase64Encoded': True
        }

    except Exception as e:
        print(f"Error tracking open: {str(e)}")
        # Still return GIF even on error
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'image/gif'},
            'body': base64.b64encode(TRACKING_GIF).decode('utf-8'),
            'isBase64Encoded': True
        }


def track_click(event):
    """Track click and redirect"""
    try:
        campaign_id = event['pathParameters']['campaign_id']
        email_hash = event['pathParameters']['email_hash']

        # Get target URL from query string
        query_params = event.get('queryStringParameters', {}) or {}
        target_url = query_params.get('url', 'https://yallabalagan.org')
        target_url = unquote(target_url)

        print(f"Tracking click: campaign={campaign_id}, email_hash={email_hash}, url={target_url}")

        # Record event (with deduplication for each unique URL)
        event_id_suffix = f"clicked#{target_url[:50]}"  # Include URL in dedup
        if record_event_deduplicated(campaign_id, email_hash, event_id_suffix, {'url': target_url}):
            # Update campaign counter only if new event
            update_campaign_count(campaign_id, 'clicked_count')
            print(f"Recorded new click event for {email_hash}")
        else:
            print(f"Click already recorded for {email_hash} on {target_url}")

        # Redirect to target URL
        return {
            'statusCode': 302,
            'headers': {
                'Location': target_url,
                'Cache-Control': 'no-cache'
            },
            'body': ''
        }

    except Exception as e:
        print(f"Error tracking click: {str(e)}")
        # Redirect to homepage on error
        return {
            'statusCode': 302,
            'headers': {'Location': 'https://yallabalagan.org'},
            'body': ''
        }


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    path = event.get('rawPath', '')
    print(f"Path: {path}")

    try:
        if '/track/open/' in path:
            return track_open(event)
        elif '/track/click/' in path:
            return track_click(event)
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not found'})
            }

    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
