import json
import os

import boto3
from boto3.dynamodb.conditions import Attr

DONATIONS_TABLE = os.environ['DONATIONS_TABLE']
DONATION_GOAL = int(os.environ.get('DONATION_GOAL', '20000'))

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DONATIONS_TABLE)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
}


def lambda_handler(event, context):
    try:
        scan_kwargs = {
            'FilterExpression': Attr('status').eq('completed'),
            'ProjectionExpression': 'amount',
        }
        items = []
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                **scan_kwargs,
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))

        collected = sum(int(item['amount']) for item in items)
        count = len(items)
    except Exception as e:
        print(f'DynamoDB scan error: {e}')
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': 'Internal error'}),
        }

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'collected': collected,
            'goal': DONATION_GOAL,
            'count': count,
        }),
    }
