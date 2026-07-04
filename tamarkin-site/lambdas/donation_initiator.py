import hashlib
import json
import os
import time
import uuid

import boto3
import requests

DONATIONS_TABLE = os.environ['DONATIONS_TABLE']
ALLPAY_LOGIN = os.environ['ALLPAY_LOGIN']
ALLPAY_API_KEY = os.environ['ALLPAY_API_KEY']
API_URL = os.environ['API_URL']

ALLPAY_ENDPOINT = 'https://allpay.to/app/?show=getpayment&mode=api10'
SITE_URL = 'https://tamarkin.yallabalagan.org'
PAYMENT_EXPIRE_MINUTES = 30

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DONATIONS_TABLE)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
}


def _generate_signature(params: dict) -> str:
    params_copy = {k: v for k, v in params.items() if k != 'sign'}
    sorted_keys = sorted(
        k for k in params_copy
        if params_copy[k] is not None and str(params_copy[k]).strip() != ''
    )
    chunks = []
    for key in sorted_keys:
        value = params_copy[key]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    for sub_key in sorted(item.keys()):
                        val = item[sub_key]
                        if val is not None and str(val).strip() != '':
                            chunks.append(str(val).strip())
                else:
                    chunks.append(str(item).strip())
        else:
            chunks.append(str(value).strip())
    base_string = ':'.join(chunks) + ':' + ALLPAY_API_KEY
    return hashlib.sha256(base_string.encode('utf-8')).hexdigest()


def _error(status, message):
    return {
        'statusCode': status,
        'headers': CORS_HEADERS,
        'body': json.dumps({'error': message}),
    }


def lambda_handler(event, context):
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

    try:
        body = json.loads(event.get('body') or '{}')
    except (json.JSONDecodeError, TypeError):
        return _error(400, 'Invalid JSON')

    name = str(body.get('name', '')).strip()
    email = str(body.get('email', '')).strip()
    needs_receipt = bool(body.get('needs_receipt', False))

    try:
        amount = int(body.get('amount', 0))
    except (ValueError, TypeError):
        amount = 0

    if not name:
        return _error(400, 'Укажите имя')
    if not email or '@' not in email:
        return _error(400, 'Укажите корректный email')
    if amount < 10 or amount > 50000:
        return _error(400, 'Сумма должна быть от 10 до 50 000 ₪')

    now = int(time.time())
    donation_id = f"DON-{now}-{uuid.uuid4().hex[:8]}"

    table.put_item(Item={
        'donation_id': donation_id,
        'created_at': now,
        'name': name,
        'email': email,
        'amount': str(amount),
        'needs_receipt': needs_receipt,
        'status': 'pending',
    })

    request_body = {
        'login': ALLPAY_LOGIN,
        'order_id': donation_id,
        'items': [{'name': 'Цифровой продукт Вовы Тамаркина', 'qty': 1,
                   'price': f'{amount:.2f}', 'vat': 'Y'}],
        'currency': 'ILS',
        'notifications_url': f'{API_URL}/webhook/allpay',
        'success_url': f'{SITE_URL}/success.html?id={donation_id}',
        'client_email': email,
        'client_name': name,
        'expire': now + PAYMENT_EXPIRE_MINUTES * 60,
        'lang': 'RU',
    }
    request_body['sign'] = _generate_signature(request_body)

    try:
        resp = requests.post(
            ALLPAY_ENDPOINT,
            json=request_body,
            headers={'Content-Type': 'application/json'},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        payment_url = result.get('payment_url')
        if not payment_url:
            raise ValueError(f'AllPay missing payment_url: {result}')
    except Exception as e:
        print(f'AllPay API error for {donation_id}: {e}')
        return _error(502, 'Ошибка платёжного сервиса, попробуйте позже')

    print(f'Created donation {donation_id} amount={amount} needs_receipt={needs_receipt}')
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({'payment_url': payment_url}),
    }
