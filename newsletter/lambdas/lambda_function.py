"""
Lambda Function: newsletter-api
HTTP API for newsletter web admin interface

Environment Variables:
- CONTACTS_TABLE: DynamoDB table for contacts
- CAMPAIGNS_TABLE: DynamoDB table for campaigns
- EVENTS_TABLE: DynamoDB table for events
- NEWSLETTER_SENDER_LAMBDA: Name of sender Lambda function
- SECRET_KEY: Secret key for HMAC token generation

Endpoints:
- POST /campaigns - Create campaign
- GET /campaigns - List campaigns
- GET /campaigns/{campaign_id} - Get campaign details
- POST /campaigns/{campaign_id}/send - Send campaign
- GET /contacts/preview - Preview contacts by tags
- POST /unsubscribe - Unsubscribe contact
"""

import json
import os
import hmac
import hashlib
from datetime import datetime
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Attr

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# Environment variables
CONTACTS_TABLE = os.environ['CONTACTS_TABLE']
CAMPAIGNS_TABLE = os.environ['CAMPAIGNS_TABLE']
EVENTS_TABLE = os.environ['EVENTS_TABLE']
NEWSLETTER_SENDER_LAMBDA = os.environ['NEWSLETTER_SENDER_LAMBDA']
SECRET_KEY = os.environ['SECRET_KEY']

# DynamoDB tables
contacts_table = dynamodb.Table(CONTACTS_TABLE)
campaigns_table = dynamodb.Table(CAMPAIGNS_TABLE)
events_table = dynamodb.Table(EVENTS_TABLE)


class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert DynamoDB Decimal to JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


def generate_token(email):
    """Generate HMAC token for email"""
    return hmac.new(
        SECRET_KEY.encode(),
        email.encode(),
        hashlib.sha256
    ).hexdigest()


def generate_campaign_id():
    """Generate campaign ID in format CAMP-YYYYMMDD-XXXX"""
    now = datetime.utcnow()
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M')
    return f"CAMP-{date_str}-{time_str}"


def cors_response(status_code, body):
    """Create response with CORS headers"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS,PUT,DELETE',
            'Access-Control-Max-Age': '3600'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def create_campaign(event):
    """POST /campaigns - Create new campaign"""
    try:
        body = json.loads(event['body'])

        # Validate required fields
        if 'subject' not in body or 'html_body' not in body:
            return cors_response(400, {'error': 'Missing required fields: subject, html_body'})

        campaign_id = generate_campaign_id()
        now = int(datetime.utcnow().timestamp())

        campaign = {
            'campaign_id': campaign_id,
            'subject': body['subject'],
            'html_body': body['html_body'],
            'preview_text': body.get('preview_text', ''),  # NEW: Email preview text
            'tags_filter': body.get('tags_filter', []),
            'tags_match_mode': body.get('tags_match_mode', 'ANY'),  # NEW: ANY or ALL
            'exclude_tags': body.get('exclude_tags', []),  # NEW: Tags to exclude
            'status': 'draft',
            'sent_count': 0,
            'opened_count': 0,
            'clicked_count': 0,
            'created_at': now,
            'updated_at': now
        }

        campaigns_table.put_item(Item=campaign)

        return cors_response(200, {'campaign_id': campaign_id})

    except Exception as e:
        print(f"Error creating campaign: {str(e)}")
        return cors_response(500, {'error': str(e)})


def list_campaigns(event):
    """GET /campaigns - List all campaigns"""
    try:
        response = campaigns_table.scan()
        campaigns = response.get('Items', [])

        # Sort by created_at descending, limit to 20
        campaigns_sorted = sorted(
            campaigns,
            key=lambda x: x.get('created_at', 0),
            reverse=True
        )[:20]

        # Return simplified list
        result = [{
            'campaign_id': c.get('campaign_id', ''),
            'subject': c.get('subject', 'Untitled Campaign'),
            'status': c.get('status', 'draft'),
            'sent_count': c.get('sent_count', 0),
            'opened_count': c.get('opened_count', 0),
            'clicked_count': c.get('clicked_count', 0),
            'created_at': c.get('created_at', 0)
        } for c in campaigns_sorted]

        return cors_response(200, result)

    except Exception as e:
        print(f"Error listing campaigns: {str(e)}")
        return cors_response(500, {'error': str(e)})


def get_campaign(event):
    """GET /campaigns/{campaign_id} - Get campaign details"""
    try:
        campaign_id = event['pathParameters']['campaign_id']

        # Get campaign
        response = campaigns_table.get_item(Key={'campaign_id': campaign_id})
        campaign = response.get('Item')

        if not campaign:
            return cors_response(404, {'error': 'Campaign not found'})

        # Get events for this campaign
        events_response = events_table.query(
            KeyConditionExpression='campaign_id = :cid',
            ExpressionAttributeValues={':cid': campaign_id},
            Limit=100
        )
        events = events_response.get('Items', [])

        campaign['events'] = events
        campaign['stats'] = {
            'sent': campaign.get('sent_count', 0),
            'opened': campaign.get('opened_count', 0),
            'clicked': campaign.get('clicked_count', 0)
        }

        return cors_response(200, campaign)

    except Exception as e:
        print(f"Error getting campaign: {str(e)}")
        return cors_response(500, {'error': str(e)})


def send_campaign(event):
    """POST /campaigns/{campaign_id}/send - Trigger campaign sending"""
    try:
        campaign_id = event['pathParameters']['campaign_id']

        # Get campaign
        response = campaigns_table.get_item(Key={'campaign_id': campaign_id})
        campaign = response.get('Item')

        if not campaign:
            return cors_response(404, {'error': 'Campaign not found'})

        if campaign['status'] == 'sent':
            return cors_response(400, {'error': 'Campaign already sent'})

        # Update status to sending
        campaigns_table.update_item(
            Key={'campaign_id': campaign_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'sending',
                ':updated_at': int(datetime.utcnow().timestamp())
            }
        )

        # Invoke sender Lambda asynchronously
        lambda_client.invoke(
            FunctionName=NEWSLETTER_SENDER_LAMBDA,
            InvocationType='Event',
            Payload=json.dumps({'campaign_id': campaign_id})
        )

        return cors_response(200, {'message': 'Sending started'})

    except Exception as e:
        print(f"Error sending campaign: {str(e)}")
        return cors_response(500, {'error': str(e)})


def preview_contacts(event):
    """GET /contacts/preview - Preview contacts by tags with advanced filtering"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        tags_str = query_params.get('tags', '')
        exclude_tags_str = query_params.get('exclude_tags', '')
        match_mode = query_params.get('match_mode', 'ANY')  # ANY or ALL

        tags = [t.strip() for t in tags_str.split(',') if t.strip()]
        exclude_tags = [t.strip() for t in exclude_tags_str.split(',') if t.strip()]

        # Scan contacts
        response = contacts_table.scan()
        all_contacts = response.get('Items', [])

        # Filter by status=active
        active_contacts = [c for c in all_contacts if c.get('status') == 'active']

        # Filter by tags if specified
        if tags:
            filtered_contacts = []
            for contact in active_contacts:
                contact_tags = contact.get('tags', [])

                # Check match mode
                if match_mode == 'ALL':
                    # ALL: contact must have all specified tags
                    tags_match = all(tag in contact_tags for tag in tags)
                else:
                    # ANY: contact must have at least one specified tag
                    tags_match = any(tag in contact_tags for tag in tags)

                # Check exclude tags
                if exclude_tags:
                    has_excluded_tag = any(tag in contact_tags for tag in exclude_tags)
                    if has_excluded_tag:
                        continue  # Skip this contact

                if tags_match:
                    filtered_contacts.append(contact)
        else:
            # No tags filter - use all active contacts (but still check exclude)
            if exclude_tags:
                filtered_contacts = []
                for contact in active_contacts:
                    contact_tags = contact.get('tags', [])
                    has_excluded_tag = any(tag in contact_tags for tag in exclude_tags)
                    if not has_excluded_tag:
                        filtered_contacts.append(contact)
            else:
                filtered_contacts = active_contacts

        # Get sample emails
        sample_emails = [c['email'] for c in filtered_contacts[:5]]

        # Count unsubscribed contacts
        unsubscribed_count = len([c for c in all_contacts if c.get('status') == 'unsubscribed'])

        return cors_response(200, {
            'count': len(filtered_contacts),
            'sample_emails': sample_emails,
            'all_tags': get_all_tags(all_contacts),
            'total_contacts': len(all_contacts),
            'unsubscribed_contacts': unsubscribed_count
        })

    except Exception as e:
        print(f"Error previewing contacts: {str(e)}")
        return cors_response(500, {'error': str(e)})


def get_all_tags(contacts):
    """Get all unique tags from contacts"""
    tags_set = set()
    for contact in contacts:
        tags_set.update(contact.get('tags', []))
    return sorted(list(tags_set))


def unsubscribe_contact(event):
    """POST /unsubscribe - Unsubscribe contact"""
    try:
        body = json.loads(event['body'])

        email = body.get('email')
        token = body.get('token')

        if not email or not token:
            return cors_response(400, {'error': 'Missing email or token'})

        # Validate token
        expected_token = generate_token(email)
        if token != expected_token:
            return cors_response(403, {'error': 'Invalid token'})

        # Update contact status
        contacts_table.update_item(
            Key={'email': email},
            UpdateExpression='SET #status = :status, unsubscribed_at = :unsubscribed_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'unsubscribed',
                ':unsubscribed_at': int(datetime.utcnow().timestamp())
            }
        )

        return cors_response(200, {'success': True})

    except Exception as e:
        print(f"Error unsubscribing: {str(e)}")
        return cors_response(500, {'error': str(e)})


def delete_campaign(event):
    """DELETE /campaigns/{campaign_id} - Delete campaign and all related events"""
    try:
        campaign_id = event['pathParameters']['campaign_id']

        # Get campaign to verify it exists
        response = campaigns_table.get_item(Key={'campaign_id': campaign_id})
        campaign = response.get('Item')

        if not campaign:
            return cors_response(404, {'error': 'Campaign not found'})

        # Delete campaign
        campaigns_table.delete_item(Key={'campaign_id': campaign_id})
        print(f"Deleted campaign: {campaign_id}")

        # Delete all related events
        # Query events by campaign_id
        events_response = events_table.query(
            KeyConditionExpression='campaign_id = :cid',
            ExpressionAttributeValues={':cid': campaign_id}
        )
        events = events_response.get('Items', [])

        # Delete events in batches
        deleted_count = 0
        with events_table.batch_writer() as batch:
            for event_item in events:
                batch.delete_item(Key={
                    'campaign_id': event_item['campaign_id'],
                    'event_id': event_item['event_id']
                })
                deleted_count += 1

        print(f"Deleted {deleted_count} events for campaign {campaign_id}")

        return cors_response(200, {
            'success': True,
            'campaign_id': campaign_id,
            'events_deleted': deleted_count
        })

    except Exception as e:
        print(f"Error deleting campaign: {str(e)}")
        import traceback
        traceback.print_exc()
        return cors_response(500, {'error': str(e)})


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    # Handle OPTIONS for CORS
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return cors_response(200, {})

    # Route based on path and method
    raw_path = event.get('rawPath', '')
    # Remove /prod prefix if present
    path = raw_path.replace('/prod', '') if raw_path.startswith('/prod') else raw_path
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')

    print(f"Method: {method}, Raw Path: {raw_path}, Normalized Path: {path}")

    try:
        if method == 'POST' and path == '/campaigns':
            return create_campaign(event)

        elif method == 'GET' and path == '/campaigns':
            return list_campaigns(event)

        elif method == 'GET' and path.startswith('/campaigns/') and not path.endswith('/send'):
            return get_campaign(event)

        elif method == 'POST' and path.endswith('/send'):
            return send_campaign(event)

        elif method == 'DELETE' and path.startswith('/campaigns/'):
            return delete_campaign(event)

        elif method == 'GET' and path == '/contacts/preview':
            return preview_contacts(event)

        elif method == 'POST' and path == '/unsubscribe':
            return unsubscribe_contact(event)

        else:
            return cors_response(404, {'error': 'Not found', 'path': raw_path, 'method': method})

    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        import traceback
        traceback.print_exc()
        return cors_response(500, {'error': str(e)})
