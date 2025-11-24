"""
Lambda Function: newsletter-image-upload
Generates pre-signed URLs for uploading images to S3

Environment Variables:
- IMAGES_BUCKET: S3 bucket for storing images
- REGION: AWS region

Endpoints:
- POST /images/upload-url - Generate pre-signed upload URL
"""

import json
import os
import uuid
from datetime import datetime
import boto3
from botocore.config import Config

# Environment variables
IMAGES_BUCKET = os.environ.get('IMAGES_BUCKET', 'yallabalagan-newsletter-images')
REGION = os.environ.get('AWS_REGION', 'eu-north-1')

# Initialize AWS clients with regional endpoint
s3_client = boto3.client(
    's3',
    region_name=REGION,
    config=Config(
        signature_version='s3v4',
        s3={'addressing_style': 'virtual'}
    )
)


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
        'body': json.dumps(body)
    }


def generate_upload_url(event):
    """POST /images/upload-url - Generate pre-signed URL for upload"""
    try:
        body = json.loads(event['body'])

        # Get filename and content type
        original_filename = body.get('filename', 'image.jpg')
        content_type = body.get('contentType', 'image/jpeg')

        # Validate content type
        allowed_types = [
            'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
            'image/webp', 'image/svg+xml'
        ]
        if content_type not in allowed_types:
            return cors_response(400, {
                'error': f'Invalid content type. Allowed: {", ".join(allowed_types)}'
            })

        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        extension = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else 'jpg'
        key = f"uploads/{timestamp}-{unique_id}.{extension}"

        # Generate pre-signed URL for PUT operation
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': IMAGES_BUCKET,
                'Key': key,
                'ContentType': content_type,
            },
            ExpiresIn=3600  # URL valid for 1 hour
        )

        # Generate public URL
        public_url = f"https://{IMAGES_BUCKET}.s3.{REGION}.amazonaws.com/{key}"

        return cors_response(200, {
            'uploadUrl': presigned_url,
            'publicUrl': public_url,
            'key': key
        })

    except Exception as e:
        print(f"Error generating upload URL: {str(e)}")
        return cors_response(500, {'error': str(e)})


def lambda_handler(event, context):
    """Main Lambda handler"""
    print(f"Event: {json.dumps(event)}")

    # Handle OPTIONS for CORS
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return cors_response(200, {})

    # Route based on path and method
    raw_path = event.get('rawPath', '')
    path = raw_path.replace('/prod', '') if raw_path.startswith('/prod') else raw_path
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')

    print(f"Method: {method}, Raw Path: {raw_path}, Normalized Path: {path}")

    try:
        if method == 'POST' and path == '/images/upload-url':
            return generate_upload_url(event)
        else:
            return cors_response(404, {'error': 'Not found', 'path': raw_path, 'method': method})

    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        import traceback
        traceback.print_exc()
        return cors_response(500, {'error': str(e)})
