import json
import os

import boto3

DONATIONS_TABLE = os.environ['DONATIONS_TABLE']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DONATIONS_TABLE)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
}


def lambda_handler(event, context):
    params = event.get('queryStringParameters') or {}
    donation_id = params.get('id', '').strip()

    if not donation_id:
        return {'statusCode': 400, 'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Missing id'})}

    try:
        result = table.get_item(Key={'donation_id': donation_id})
        item = result.get('Item')
    except Exception as e:
        print(f'DynamoDB error: {e}')
        return {'statusCode': 500, 'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Internal error'})}

    if not item:
        return {'statusCode': 404, 'headers': CORS_HEADERS,
                'body': json.dumps({'status': 'not_found'})}

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({'status': item.get('status', 'pending')}),
    }
