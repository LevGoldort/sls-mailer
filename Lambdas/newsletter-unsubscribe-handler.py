"""
Lambda Function: newsletter-unsubscribe-handler
Handles unsubscribe requests (alternative to newsletter-api POST /unsubscribe)

Environment Variables:
- CONTACTS_TABLE: DynamoDB table for contacts
- SECRET_KEY: Secret key for HMAC token generation

Can be invoked directly or via API Gateway
Payload: {"email": "user@example.com", "token": "abc123..."}
"""

import json
import os
import hmac
import hashlib
from datetime import datetime
import boto3

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CONTACTS_TABLE = os.environ['CONTACTS_TABLE']
SECRET_KEY = os.environ['SECRET_KEY']

# DynamoDB tables
contacts_table = dynamodb.Table(CONTACTS_TABLE)


def generate_token(email):
    """Generate HMAC token for email"""
    return hmac.new(
        SECRET_KEY.encode(),
        email.encode(),
        hashlib.sha256
    ).hexdigest()


def validate_token(email, token):
    """Validate HMAC token"""
    expected_token = generate_token(email)
    return token == expected_token


def unsubscribe_contact(email, token):
    """Unsubscribe contact from mailing list"""

    # Validate token
    if not validate_token(email, token):
        return {
            'success': False,
            'error': 'Invalid token'
        }

    # Update contact status
    try:
        contacts_table.update_item(
            Key={'email': email},
            UpdateExpression='SET #status = :status, unsubscribed_at = :unsubscribed_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'unsubscribed',
                ':unsubscribed_at': int(datetime.utcnow().timestamp())
            }
        )

        print(f"Successfully unsubscribed {email}")

        return {
            'success': True,
            'email': email,
            'timestamp': int(datetime.utcnow().timestamp())
        }

    except Exception as e:
        print(f"Error unsubscribing {email}: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    try:
        # Handle both direct invocation and API Gateway
        if 'body' in event:
            # API Gateway
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            # Direct invocation
            body = event

        email = body.get('email')
        token = body.get('token')

        if not email or not token:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing email or token'
                })
            }

        # Process unsubscribe
        result = unsubscribe_contact(email, token)

        return {
            'statusCode': 200 if result['success'] else 403,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
