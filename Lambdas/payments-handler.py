import json
import os
import time
import random
import hashlib
import boto3
import requests
from datetime import datetime

# Environment variables
ALLPAY_WEBHOOK_SECRET = os.environ['ALLPAY_WEBHOOK_SECRET']
NOTION_TOKEN = os.environ['NOTION_TOKEN']
PRODUCTS_DB_ID = os.environ['PRODUCTS_DB_ID']
DYNAMODB_TABLE = os.environ['DYNAMODB_TABLE']
ORDER_MANAGER_LAMBDA = os.environ.get('ORDER_MANAGER_LAMBDA', '')
SITE_GENERATOR_LAMBDA = os.environ.get('SITE_GENERATOR_LAMBDA', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'yalla@yallabalagan.org')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'yalla@yallabalagan.org')

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)
lambda_client = boto3.client('lambda')
ses_client = boto3.client('ses')


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def verify_allpay_signature(params, webhook_secret):
    """
    Проверяет HMAC подпись от AllPay по алгоритму SHA256
    Реализует точно тот же алгоритм что в документации AllPay
    """
    # Сохраняем оригинальную подпись
    request_signature = params.get('sign')
    if not request_signature:
        print("Error: Missing 'sign' parameter")
        return False

    # Создаём копию параметров без sign
    params_copy = {k: v for k, v in params.items() if k != 'sign'}

    # Фильтруем пустые значения и сортируем ключи
    sorted_keys = sorted([
        k for k in params_copy.keys()
        if params_copy[k] is not None and str(params_copy[k]).strip() != ''
    ])

    # Собираем значения по алгоритму AllPay
    chunks = []
    for key in sorted_keys:
        value = params_copy[key]

        # Если это массив - разворачиваем вложенные объекты
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    # Сортируем ключи вложенного объекта и добавляем значения
                    for sub_key in sorted(item.keys()):
                        val = item[sub_key]
                        if val is not None and str(val).strip() != '':
                            chunks.append(str(val).strip())
                else:
                    chunks.append(str(item).strip())
        else:
            chunks.append(str(value).strip())

    # Формируем строку для хеширования
    base_string = ':'.join(chunks) + ':' + webhook_secret

    # Генерируем SHA256 хеш
    calculated_signature = hashlib.sha256(base_string.encode('utf-8')).hexdigest()

    # Сравниваем подписи
    is_valid = calculated_signature == request_signature

    print(f"Signature verification: {'VALID' if is_valid else 'INVALID'}")
    if not is_valid:
        print(f"Base string: {base_string}")
        print(f"Calculated: {calculated_signature}")
        print(f"Received: {request_signature}")

    return is_valid


def find_product_by_slug(slug):
    """
    Ищет продукт в Notion по Slug
    """
    try:
        response = requests.post(
            f"{NOTION_API_URL}/databases/{PRODUCTS_DB_ID}/query",
            headers=notion_headers(),
            json={
                "filter": {
                    "property": "Slug",
                    "rich_text": {
                        "equals": slug
                    }
                }
            },
            timeout=10
        )

        if response.status_code != 200:
            print(f"Error querying products: {response.text}")
            return None

        results = response.json().get('results', [])

        if not results:
            print(f"Product not found by slug: {slug}")
            return None

        # Берём первый результат
        page = results[0]
        props = page['properties']

        def get_text(rich_text_array):
            if not rich_text_array:
                return ""
            return "".join([t.get('plain_text', '') for t in rich_text_array])

        product = {
            'id': page['id'],
            'name': props.get('Name', {}).get('title', [{}])[0].get('plain_text', ''),
            'slug': get_text(props.get('Slug', {}).get('rich_text', [])),
            'type': props.get('Type', {}).get('select', {}).get('name', 'Individual'),
            'price_ils': props.get('Price_ILS', {}).get('number', 0),
            'price_stars': props.get('Price_Stars', {}).get('number', 0),
            'total_slots': props.get('Total_Slots', {}).get('number', 0),
            'sold_slots': props.get('Sold_Slots', {}).get('number', 0),
            'group_size': props.get('Group_Size', {}).get('number'),
            'tg_code': get_text(props.get('Tg_Code', {}).get('rich_text', [])),
            'photo_url': props.get('Photo_URL', {}).get('url', ''),
            'short_description': get_text(props.get('Short_Description', {}).get('rich_text', [])),
        }

        # Получаем talent_id из Relation
        talent_relation = props.get('Talent', {}).get('relation', [])
        product['talent_id'] = talent_relation[0]['id'] if talent_relation else None

        return product

    except Exception as e:
        print(f"Exception finding product by slug: {str(e)}")
        return None


def update_sold_slots(product_id, increment=1):
    """Обновляет Sold_Slots в Notion"""
    try:
        # Сначала получаем текущее значение
        response = requests.get(
            f"{NOTION_API_URL}/pages/{product_id}",
            headers=notion_headers(),
            timeout=10
        )

        if response.status_code != 200:
            return False

        page = response.json()
        current_sold = page['properties'].get('Sold_Slots', {}).get('number', 0)
        new_sold_slots = current_sold + increment

        # Обновляем в Notion
        response = requests.patch(
            f"{NOTION_API_URL}/pages/{product_id}",
            headers=notion_headers(),
            json={
                "properties": {
                    "Sold_Slots": {
                        "number": new_sold_slots
                    }
                }
            },
            timeout=10
        )

        if response.status_code == 200:
            print(f"Updated Sold_Slots for {product_id}: {new_sold_slots}")
            return True
        else:
            print(f"Error updating Sold_Slots: {response.text}")
            return False

    except Exception as e:
        print(f"Exception updating Sold_Slots: {str(e)}")
        return False


def create_purchase_in_dynamodb(purchase_data):
    """Создает Purchase в DynamoDB"""
    try:
        table.put_item(Item=purchase_data)
        print(f"Created purchase in DynamoDB: {purchase_data['purchase_id']}")
        return True
    except Exception as e:
        print(f"Error creating purchase in DynamoDB: {str(e)}")
        return False


def invoke_order_manager(purchase_id):
    """Вызывает order-manager Lambda асинхронно"""
    if not ORDER_MANAGER_LAMBDA:
        print("ORDER_MANAGER_LAMBDA not configured, skipping")
        return

    try:
        lambda_client.invoke(
            FunctionName=ORDER_MANAGER_LAMBDA,
            InvocationType='Event',  # Асинхронный вызов
            Payload=json.dumps({
                'purchase_id': purchase_id
            })
        )
        print(f"Invoked order-manager for purchase {purchase_id}")
    except Exception as e:
        print(f"Error invoking order-manager: {str(e)}")


def invoke_site_generator():
    """Вызывает donate-site-generator Lambda асинхронно"""
    if not SITE_GENERATOR_LAMBDA:
        print("SITE_GENERATOR_LAMBDA not configured, skipping")
        return

    try:
        lambda_client.invoke(
            FunctionName=SITE_GENERATOR_LAMBDA,
            InvocationType='Event',  # Асинхронный вызов
            Payload=json.dumps({})  # donate-site-generator не требует параметров
        )
        print(f"Invoked donate-site-generator to refresh website")
    except Exception as e:
        print(f"Error invoking site-generator: {str(e)}")


def send_email_notification(buyer_email, buyer_name, product_name, purchase_id, product_data=None, buyer_data=None):
    """
    Отправка email уведомлений через SES
    - Покупателю: благодарность + детали заказа
    - Админу: полная информация о заказе
    """
    if not product_data:
        print("Warning: product_data not provided, sending minimal email")
        product_data = {'name': product_name, 'type': 'Individual'}

    if not buyer_data:
        buyer_data = {
            'name': buyer_name,
            'email': buyer_email,
            'telegram': '',
            'phone': ''
        }

    # Определяем текст в зависимости от типа товара
    product_type = product_data.get('type', 'Individual')
    if product_type == 'Individual':
        delivery_text = """
        <p style="color: #4a5568; line-height: 1.6;">
            Это индивидуальный товар, так что в ближайшее время комик или какой-то другой наш человек 
            с вами свяжутся чтобы обеспечить получение товара.
        </p>
        """
    else:  # Group
        delivery_text = """
        <p style="color: #4a5568; line-height: 1.6;">
            Это групповой товар, так что вы его получите когда наберется группа. 
            Это то самое место позвать друзей! Как только наберется группа, мы вам напишем!
        </p>
        """

    # HTML письмо для покупателя
    buyer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #e535ab 0%, #c72d93 100%); padding: 40px 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Спасибо за поддержку! 🎉</h1>
            </div>

            <!-- Content -->
            <div style="padding: 40px 30px;">
                <p style="color: #1a202c; font-size: 18px; margin-bottom: 20px;">
                    Здравствуйте, {buyer_name}!
                </p>

                <p style="color: #4a5568; line-height: 1.6; margin-bottom: 30px;">
                    Мы получили ваш заказ и очень благодарны за вашу поддержку! 
                    Вот детали вашего заказа:
                </p>

                <!-- Product Details -->
                <div style="background: #f7fafc; border-radius: 12px; padding: 25px; margin-bottom: 30px;">
                    {f'<img src="{product_data.get("photo_url", "")}" style="width: 100%; border-radius: 8px; margin-bottom: 20px;" alt="{product_name}">' if product_data.get('photo_url') else ''}

                    <h2 style="color: #1a202c; margin: 0 0 15px 0; font-size: 22px;">{product_name}</h2>

                    <p style="color: #4a5568; line-height: 1.6; margin-bottom: 15px;">
                        {product_data.get('short_description', '')}
                    </p>

                    <div style="border-top: 2px solid #e2e8f0; padding-top: 15px; margin-top: 15px;">
                        <p style="color: #718096; margin: 5px 0;">
                            <strong>Номер заказа:</strong> {purchase_id}
                        </p>
                        <p style="color: #718096; margin: 5px 0;">
                            <strong>Тип:</strong> {('Персональный' if product_type == 'Individual' else 'Групповой')}
                        </p>
                    </div>
                </div>

                <!-- Delivery Info -->
                <div style="background: #fef5fb; border: 2px solid #e535ab; border-radius: 12px; padding: 20px; margin-bottom: 30px;">
                    <h3 style="color: #e535ab; margin: 0 0 15px 0; font-size: 18px;">📦 Что дальше?</h3>
                    {delivery_text}
                </div>

                <!-- Contact Info -->
                <div style="text-align: center; padding: 20px; background: #f7fafc; border-radius: 8px;">
                    <p style="color: #4a5568; margin-bottom: 15px;">
                        <strong>По всем вопросам:</strong>
                    </p>
                    <p style="margin: 5px 0;">
                        <a href="mailto:yalla@yallabalagan.org" style="color: #e535ab; text-decoration: none;">
                            📧 yalla@yallabalagan.org
                        </a>
                    </p>
                    <p style="margin: 5px 0;">
                        <a href="https://t.me/excremental" style="color: #0088cc; text-decoration: none;">
                            ✈️ Telegram: @excremental
                        </a>
                    </p>
                </div>
            </div>

            <!-- Footer -->
            <div style="background: #f7fafc; padding: 20px 30px; text-align: center; border-top: 2px solid #e2e8f0;">
                <p style="color: #718096; font-size: 14px; margin: 0;">
                    С любовью, команда Yalla Balagan 💜
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # HTML письмо для админа
    payment_method = buyer_data.get('payment_method', 'Unknown')
    amount = buyer_data.get('amount', 'N/A')
    currency = buyer_data.get('currency', '')

    admin_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%); padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🛒 Новый заказ!</h1>
            </div>

            <!-- Content -->
            <div style="padding: 30px;">
                <h2 style="color: #1a202c; margin: 0 0 20px 0;">Детали заказа</h2>

                <!-- Purchase Info -->
                <div style="background: #f7fafc; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Purchase ID:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{purchase_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Продукт:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{product_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Тип:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{product_type}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Способ оплаты:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{payment_method}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Сумма:</td>
                            <td style="padding: 8px 0; color: #1a202c; font-weight: 700;">{amount} {currency}</td>
                        </tr>
                    </table>
                </div>

                <!-- Buyer Info -->
                <h3 style="color: #1a202c; margin: 30px 0 15px 0;">👤 Покупатель</h3>
                <div style="background: #fef5fb; border-radius: 8px; padding: 20px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Имя:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{buyer_data.get('name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Email:</td>
                            <td style="padding: 8px 0; color: #1a202c;">
                                <a href="mailto:{buyer_data.get('email', '')}" style="color: #e535ab; text-decoration: none;">
                                    {buyer_data.get('email', 'N/A')}
                                </a>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Telegram:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{buyer_data.get('telegram', 'Не указан')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #718096; font-weight: 600;">Телефон:</td>
                            <td style="padding: 8px 0; color: #1a202c;">{buyer_data.get('phone', 'Не указан')}</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        # Отправка письма покупателю
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [buyer_email]},
            Message={
                'Subject': {
                    'Data': f'Спасибо за заказ! {product_name}',
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': buyer_html,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Email sent to buyer: {buyer_email}")

        # Отправка письма админу
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [ADMIN_EMAIL]},
            Message={
                'Subject': {
                    'Data': f'Новый заказ: {product_name} ({purchase_id})',
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': admin_html,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Email sent to admin: {ADMIN_EMAIL}")

        return True

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def handle_telegram_payment(body):
    """
    Обработчик Telegram Stars оплаты
    Принимает: product_slug, buyer_name, buyer_email, buyer_telegram, buyer_phone, tg_code
    """
    print(f"Processing Telegram payment: {json.dumps(body)}")

    # 1. Валидация обязательных полей
    required_fields = ['product_slug', 'buyer_name', 'buyer_email', 'tg_code']
    for field in required_fields:
        if not body.get(field):
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Missing required field: {field}'})
            }

    product_slug = body['product_slug']
    tg_code_submitted = body['tg_code'].strip()

    # 2. Находим продукт в Notion
    product = find_product_by_slug(product_slug)

    if not product:
        return {
            'statusCode': 404,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Product not found: {product_slug}'})
        }

    print(f"Found product: {product['name']} (ID: {product['id']})")

    # 3. Проверяем что у продукта есть Tg_Code
    if not product.get('tg_code'):
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Telegram payment not available for this product'})
        }

    # 4. Проверяем валидность кода (case-insensitive)
    if tg_code_submitted.lower() != product['tg_code'].lower():
        print(f"Invalid code: submitted='{tg_code_submitted}', expected='{product['tg_code']}'")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Неверный код. Проверьте код в Telegram и попробуйте снова.'})
        }

    # 5. Проверяем что есть свободные слоты
    if product['sold_slots'] >= product['total_slots']:
        print("ERROR: Product is sold out")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Все места заняты'})
        }

    # 6. Генерируем purchase_id
    timestamp = datetime.now().strftime('%Y%m%d')
    random_num = random.randint(1000, 9999)
    purchase_id = f"PUR-TG-{timestamp}-{random_num}"

    # 7. Создаем Purchase для DynamoDB
    purchase_data = {
        'purchase_id': purchase_id,
        'created_at': int(time.time()),
        'product_id': product['id'],
        'product_slug': product_slug,
        'talent_id': product.get('talent_id', ''),
        'buyer_name': body.get('buyer_name', ''),
        'buyer_email': body.get('buyer_email', ''),
        'buyer_telegram': body.get('buyer_telegram', ''),
        'buyer_phone': body.get('buyer_phone', ''),
        'amount': str(product['price_stars']),  # Цена в звёздах
        'currency': 'TG_STARS',
        'payment_method': 'Telegram',
        'payment_id': f"tg-code-{tg_code_submitted}",
        'status': 'completed',
        'metadata': {
            'source': 'telegram-payment',
            'tg_code_used': tg_code_submitted
        }
    }

    # 8. Сохраняем в DynamoDB
    if not create_purchase_in_dynamodb(purchase_data):
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Failed to create purchase'})
        }

    # 9. Обновляем Sold_Slots в Notion
    if not update_sold_slots(product['id'], increment=1):
        print("Warning: Failed to update Sold_Slots in Notion")

    # 10. Регенерируем сайт
    invoke_site_generator()

    # 11. Отправляем email
    send_email_notification(
        buyer_email=body.get('buyer_email', ''),
        buyer_name=body.get('buyer_name', ''),
        product_name=product['name'],
        purchase_id=purchase_id,
        product_data={
            'name': product['name'],
            'type': product['type'],
            'photo_url': product.get('photo_url', ''),
            'short_description': product.get('short_description', ''),
        },
        buyer_data={
            'name': body.get('buyer_name', ''),
            'email': body.get('buyer_email', ''),
            'telegram': body.get('buyer_telegram', ''),
            'phone': body.get('buyer_phone', ''),
            'payment_method': 'Telegram Stars',
            'amount': str(product['price_stars']),
            'currency': '⭐'
        }
    )

    # 12. Вызываем order-manager асинхронно
    if ORDER_MANAGER_LAMBDA:
        invoke_order_manager(purchase_id)

    # 13. Успех!
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': True,
            'purchase_id': purchase_id,
            'message': 'Payment successful'
        })
    }


def handle_allpay_webhook(body):
    """
    Обработчик AllPay webhook (существующий код)
    """
    print(f"Processing AllPay webhook: {json.dumps(body)}")

    # 1. Проверяем HMAC подпись
    if not verify_allpay_signature(body, ALLPAY_WEBHOOK_SECRET):
        print("ERROR: Invalid signature!")
        return {
            'statusCode': 403,
            'body': json.dumps({'error': 'Invalid signature'})
        }

    # 2. Проверяем статус оплаты
    if body.get('status') != 1:
        print(f"Payment not successful, status: {body.get('status')}")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Payment not successful, ignored'})
        }

    # 3. Парсим add_field для получения slug и telegram
    add_field = body.get('add_field', '')

    if not add_field:
        print("ERROR: Missing add_field parameter")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing add_field parameter'})
        }

    # Парсим add_field: "product-slug,telegram,phone"
    parts = add_field.split(',')

    if len(parts) < 1:
        print("ERROR: Invalid add_field format")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid add_field format'})
        }

    product_slug = parts[0].strip()
    buyer_telegram = parts[1].strip() if len(parts) > 1 else ''
    buyer_phone = parts[2].strip() if len(parts) > 2 else ''

    print(f"Parsed: slug={product_slug}, telegram={buyer_telegram}, phone={buyer_phone}")

    # 4. Находим продукт в Notion по Slug
    product = find_product_by_slug(product_slug)

    if not product:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': f'Product not found: {product_slug}'})
        }

    print(f"Found product: {product['name']} (ID: {product['id']})")

    # 5. Проверяем что есть свободные слоты
    if product['sold_slots'] >= product['total_slots']:
        print("ERROR: Product is sold out")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Product is sold out'})
        }

    # 6. Генерируем purchase_id
    timestamp = datetime.now().strftime('%Y%m%d')
    random_num = random.randint(1000, 9999)
    purchase_id = f"PUR-{timestamp}-{random_num}"

    # 7. Создаем Purchase для DynamoDB
    purchase_data = {
        'purchase_id': purchase_id,
        'created_at': int(time.time()),
        'product_id': product['id'],
        'product_slug': product_slug,
        'talent_id': product.get('talent_id', ''),
        'buyer_name': body.get('client_name', ''),
        'buyer_email': body.get('client_email', ''),
        'buyer_telegram': buyer_telegram,
        'buyer_phone': buyer_phone,
        'amount': body.get('amount', '0'),
        'currency': 'ILS',
        'payment_method': 'AllPay',
        'payment_id': body.get('receipt', ''),
        'status': 'completed',
        'metadata': {
            'source': 'allpay-webhook',
            'card_mask': body.get('card_mask', ''),
            'card_brand': body.get('card_brand', ''),
            'foreign_card': body.get('foreign_card', ''),
            'allpay_receipt': body.get('receipt', ''),
            'raw_webhook': body
        }
    }

    # 8. Сохраняем в DynamoDB
    if not create_purchase_in_dynamodb(purchase_data):
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to create purchase'})
        }

    # 9. Обновляем Sold_Slots в Notion
    if not update_sold_slots(product['id'], increment=1):
        print("Warning: Failed to update Sold_Slots in Notion")

    # 10. Регенерируем сайт
    invoke_site_generator()

    # 11. Отправляем email
    send_email_notification(
        buyer_email=body.get('client_email', ''),
        buyer_name=body.get('client_name', ''),
        product_name=product['name'],
        purchase_id=purchase_id,
        product_data={
            'name': product['name'],
            'type': product['type'],
            'photo_url': product.get('photo_url', ''),
            'short_description': product.get('short_description', ''),
        },
        buyer_data={
            'name': body.get('client_name', ''),
            'email': body.get('client_email', ''),
            'telegram': buyer_telegram,
            'phone': buyer_phone,
            'payment_method': 'AllPay (Credit Card)',
            'amount': body.get('amount', '0'),
            'currency': '₪'
        }
    )

    # 12. Вызываем order-manager асинхронно
    if ORDER_MANAGER_LAMBDA:
        invoke_order_manager(purchase_id)

    # 13. Успех!
    return {
        'statusCode': 200,
        'body': json.dumps({
            'success': True,
            'purchase_id': purchase_id,
            'message': 'Webhook processed successfully'
        })
    }


def lambda_handler(event, context):
    """
    Main handler - маршрутизирует запросы
    """
    print(f"Received event: {json.dumps(event)}")

    try:
        # Определяем тип запроса
        http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method', 'POST'))
        path = event.get('path', event.get('rawPath', '/'))

        print(f"Method: {http_method}, Path: {path}")

        # Парсим body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        # Маршрутизация
        if path == '/telegram-payment' or body.get('payment_type') == 'telegram':
            # Telegram Stars оплата
            return handle_telegram_payment(body)
        else:
            # AllPay webhook (по умолчанию)
            return handle_allpay_webhook(body)

    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }