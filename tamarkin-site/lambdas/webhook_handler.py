import hashlib
import hmac
import json
import os
import urllib.parse

import boto3

DONATIONS_TABLE = os.environ['DONATIONS_TABLE']
ALLPAY_API_KEY = os.environ['ALLPAY_API_KEY']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DONATIONS_TABLE)


def _verify_signature(params: dict) -> bool:
    request_sig = str(params.get('sign', ''))
    params_copy = {k: v for k, v in params.items() if k != 'sign'}
    sorted_keys = sorted(
        k for k in params_copy
        if params_copy[k] is not None and str(params_copy[k]).strip() != ''
    )
    chunks = [str(params_copy[k]).strip() for k in sorted_keys]
    base_string = ':'.join(chunks) + ':' + ALLPAY_API_KEY
    expected = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
    return hmac.compare_digest(expected, request_sig)


def lambda_handler(event, context):
    raw_body = event.get('body') or ''
    if event.get('isBase64Encoded'):
        import base64
        raw_body = base64.b64decode(raw_body).decode('utf-8')

    content_type = ''
    for k, v in (event.get('headers') or {}).items():
        if k.lower() == 'content-type':
            content_type = v.lower()
            break

    print(f'Webhook received: content-type={content_type!r} body_len={len(raw_body)} body_preview={raw_body[:300]!r}')

    try:
        if 'application/json' in content_type:
            body = json.loads(raw_body or '{}')
        elif 'application/x-www-form-urlencoded' in content_type:
            body = {k: v[0] if isinstance(v, list) else v
                    for k, v in urllib.parse.parse_qs(raw_body, keep_blank_values=True).items()}
        else:
            # Try JSON first, fall back to form-encoded
            try:
                body = json.loads(raw_body or '{}')
            except (json.JSONDecodeError, ValueError):
                body = {k: v[0] if isinstance(v, list) else v
                        for k, v in urllib.parse.parse_qs(raw_body, keep_blank_values=True).items()}
    except Exception as e:
        print(f'Body parse error: {e}')
        return {'statusCode': 400, 'body': 'Bad request'}

    print(f'Parsed body keys: {list(body.keys())}')

    if not _verify_signature(body):
        print('Webhook signature verification failed')
        return {'statusCode': 403, 'body': 'Forbidden'}

    status = str(body.get('status', ''))
    order_id = str(body.get('order_id', '')).strip()

    if status != '1':
        print(f'Non-success webhook status={status} order_id={order_id}')
        return {'statusCode': 200, 'body': 'OK'}

    if not order_id:
        return {'statusCode': 400, 'body': 'Missing order_id'}

    try:
        table.update_item(
            Key={'donation_id': order_id},
            UpdateExpression='SET #s = :s, payment_data = :pd',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'completed', ':pd': body},
            ConditionExpression='attribute_exists(donation_id)',
        )
        print(f'Donation {order_id} marked completed')
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f'Webhook for unknown donation_id={order_id}, ignoring')
    except Exception as e:
        print(f'DynamoDB update error for {order_id}: {e}')
        return {'statusCode': 500, 'body': 'Internal error'}

    return {'statusCode': 200, 'body': 'OK'}
