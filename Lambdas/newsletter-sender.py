"""
Lambda Function: newsletter-sender
Sends emails in batches through AWS SES

Environment Variables:
- CONTACTS_TABLE: DynamoDB table for contacts
- CAMPAIGNS_TABLE: DynamoDB table for campaigns
- EVENTS_TABLE: DynamoDB table for events
- SES_FROM_EMAIL: Email address to send from
- TRACKING_BASE_URL: Base URL for tracking links
- SECRET_KEY: Secret key for HMAC token generation

Invoked asynchronously by newsletter-api
Payload: {"campaign_id": "CAMP-20241122-1234"}
"""

import json
import os
import hmac
import hashlib
import time
import re
from datetime import datetime
from decimal import Decimal
import boto3
from urllib.parse import quote

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
CONTACTS_TABLE = os.environ['CONTACTS_TABLE']
CAMPAIGNS_TABLE = os.environ['CAMPAIGNS_TABLE']
EVENTS_TABLE = os.environ['EVENTS_TABLE']
SES_FROM_EMAIL = os.environ['SES_FROM_EMAIL']
TRACKING_BASE_URL = os.environ['TRACKING_BASE_URL']
SECRET_KEY = os.environ['SECRET_KEY']

# DynamoDB tables
contacts_table = dynamodb.Table(CONTACTS_TABLE)
campaigns_table = dynamodb.Table(CAMPAIGNS_TABLE)
events_table = dynamodb.Table(EVENTS_TABLE)

# Batch settings
BATCH_SIZE = 50
BATCH_DELAY = 1.0  # seconds


def generate_token(email):
    """Generate HMAC token for email"""
    return hmac.new(
        SECRET_KEY.encode(),
        email.encode(),
        hashlib.sha256
    ).hexdigest()


def generate_email_hash(email):
    """Generate hash for email tracking"""
    return hmac.new(
        SECRET_KEY.encode(),
        email.encode(),
        hashlib.sha256
    ).hexdigest()[:16]


def get_active_contacts(tags_filter, match_mode='ANY', exclude_tags=None):
    """Get all active contacts matching tags filter with advanced logic"""
    if exclude_tags is None:
        exclude_tags = []

    response = contacts_table.scan()
    all_contacts = response.get('Items', [])

    # Filter by status=active
    active_contacts = [c for c in all_contacts if c.get('status') == 'active']

    # Filter by tags if specified
    if tags_filter:
        filtered_contacts = []
        for contact in active_contacts:
            contact_tags = contact.get('tags', [])

            # Check match mode
            if match_mode == 'ALL':
                # ALL: contact must have all specified tags
                tags_match = all(tag in contact_tags for tag in tags_filter)
            else:
                # ANY: contact must have at least one specified tag
                tags_match = any(tag in contact_tags for tag in tags_filter)

            # Check exclude tags
            if exclude_tags:
                has_excluded_tag = any(tag in contact_tags for tag in exclude_tags)
                if has_excluded_tag:
                    continue  # Skip this contact

            if tags_match:
                filtered_contacts.append(contact)
        return filtered_contacts
    else:
        # No tags filter - use all active contacts (but still check exclude)
        if exclude_tags:
            filtered_contacts = []
            for contact in active_contacts:
                contact_tags = contact.get('tags', [])
                has_excluded_tag = any(tag in contact_tags for tag in exclude_tags)
                if not has_excluded_tag:
                    filtered_contacts.append(contact)
            return filtered_contacts
        else:
            return active_contacts


def personalize_html(html_body, email, campaign_id, preview_text=''):
    """Personalize HTML with tracking links, unsubscribe, and preview text"""
    email_hash = generate_email_hash(email)
    token = generate_token(email)

    # Add preview text at the beginning if provided
    if preview_text:
        preview_div = f'<div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;">{preview_text}</div>'
        # Insert after <body> tag
        if '<body>' in html_body:
            html = html_body.replace('<body>', f'<body>{preview_div}', 1)
        elif '<body ' in html_body:
            # Handle <body with attributes>
            html = re.sub(r'(<body[^>]*>)', r'\1' + preview_div, html_body, count=1)
        else:
            # No body tag - prepend
            html = preview_div + html_body
    else:
        html = html_body

    # Replace unsubscribe link
    unsubscribe_url = f"https://newsletter.yallabalagan.org/unsubscribe.html?email={quote(email)}&token={token}"
    html = html.replace('{{UNSUBSCRIBE_LINK}}', unsubscribe_url)

    # Add tracking pixel before </body>
    tracking_pixel = f'<img src="{TRACKING_BASE_URL}/track/open/{campaign_id}/{email_hash}" width="1" height="1" style="display:none;" />'

    if '</body>' in html:
        html = html.replace('</body>', f'{tracking_pixel}</body>')
    else:
        html += tracking_pixel

    # Replace links with tracking links
    def replace_link(match):
        original_url = match.group(1)
        tracked_url = f"{TRACKING_BASE_URL}/track/click/{campaign_id}/{email_hash}?url={quote(original_url)}"
        return f'<a href="{tracked_url}"'

    html = re.sub(r'<a href="([^"]+)"', replace_link, html)

    return html


def send_email(email, subject, html_body):
    """Send single email via SES"""
    try:
        # Format sender with display name
        sender = f'"Ялла, Балаган" <{SES_FROM_EMAIL}>'

        response = ses_client.send_email(
            Source=sender,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_body, 'Charset': 'UTF-8'}
                }
            }
        )
        return True, response['MessageId']
    except Exception as e:
        print(f"Error sending email to {email}: {str(e)}")
        return False, str(e)


def record_event(campaign_id, email, event_type, metadata=None):
    """Record event in DynamoDB"""
    timestamp = int(datetime.utcnow().timestamp())
    event_id = f"{email}#{event_type}#{timestamp}"

    event = {
        'campaign_id': campaign_id,
        'event_id': event_id,
        'email': email,
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


def update_campaign_count(campaign_id, field, increment=1):
    """Update campaign counter"""
    try:
        campaigns_table.update_item(
            Key={'campaign_id': campaign_id},
            UpdateExpression=f'ADD {field} :inc SET updated_at = :updated_at',
            ExpressionAttributeValues={
                ':inc': increment,
                ':updated_at': int(datetime.utcnow().timestamp())
            }
        )
    except Exception as e:
        print(f"Error updating campaign count: {str(e)}")


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    try:
        campaign_id = event['campaign_id']

        # Get campaign from DynamoDB
        response = campaigns_table.get_item(Key={'campaign_id': campaign_id})
        campaign = response.get('Item')

        if not campaign:
            print(f"Campaign {campaign_id} not found")
            return {'statusCode': 404, 'body': 'Campaign not found'}

        subject = campaign['subject']
        html_body = campaign['html_body']
        preview_text = campaign.get('preview_text', '')
        tags_filter = campaign.get('tags_filter', [])
        tags_match_mode = campaign.get('tags_match_mode', 'ANY')
        exclude_tags = campaign.get('exclude_tags', [])

        print(f"Processing campaign: {campaign_id}")
        print(f"Tags filter: {tags_filter}, Match mode: {tags_match_mode}, Exclude: {exclude_tags}")

        # Get contacts
        contacts = get_active_contacts(tags_filter, tags_match_mode, exclude_tags)
        total_contacts = len(contacts)

        print(f"Found {total_contacts} contacts to send to")

        if total_contacts == 0:
            # Update status to sent (even though nothing sent)
            campaigns_table.update_item(
                Key={'campaign_id': campaign_id},
                UpdateExpression='SET #status = :status, updated_at = :updated_at',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'sent',
                    ':updated_at': int(datetime.utcnow().timestamp())
                }
            )
            return {'statusCode': 200, 'body': 'No contacts to send to'}

        # Send emails in batches
        sent_count = 0
        failed_count = 0

        for i, contact in enumerate(contacts):
            email = contact['email']

            # Personalize HTML
            personalized_html = personalize_html(html_body, email, campaign_id, preview_text)

            # Send email
            success, message_id = send_email(email, subject, personalized_html)

            if success:
                # Record sent event
                record_event(campaign_id, email, 'sent', {'message_id': message_id})
                sent_count += 1

                # Update campaign count
                update_campaign_count(campaign_id, 'sent_count', 1)

                print(f"Sent to {email} ({sent_count}/{total_contacts})")
            else:
                failed_count += 1
                print(f"Failed to send to {email}: {message_id}")

            # Batch delay: pause every BATCH_SIZE emails
            if (i + 1) % BATCH_SIZE == 0 and (i + 1) < total_contacts:
                print(f"Batch complete: {i + 1}/{total_contacts}. Waiting {BATCH_DELAY}s...")
                time.sleep(BATCH_DELAY)

        # Update campaign status to sent
        campaigns_table.update_item(
            Key={'campaign_id': campaign_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'sent',
                ':updated_at': int(datetime.utcnow().timestamp())
            }
        )

        print(f"Campaign {campaign_id} complete: {sent_count} sent, {failed_count} failed")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'campaign_id': campaign_id,
                'sent': sent_count,
                'failed': failed_count
            })
        }

    except Exception as e:
        print(f"Error in sender Lambda: {str(e)}")

        # Try to update campaign status to failed
        try:
            if 'campaign_id' in event:
                campaigns_table.update_item(
                    Key={'campaign_id': event['campaign_id']},
                    UpdateExpression='SET #status = :status, updated_at = :updated_at',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'failed',
                        ':updated_at': int(datetime.utcnow().timestamp())
                    }
                )
        except:
            pass

        return {'statusCode': 500, 'body': str(e)}
