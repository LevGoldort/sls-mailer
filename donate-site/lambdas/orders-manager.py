import json
import os
import time
import random
import boto3
import requests
from datetime import datetime

NOTION_TOKEN = os.environ['NOTION_TOKEN']
PRODUCTS_DB_ID = os.environ['PRODUCTS_DB_ID']
ORDERS_DB_ID = os.environ['ORDERS_DB_ID']
DYNAMODB_TABLE = os.environ['DYNAMODB_TABLE']

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def get_purchase_from_dynamodb(purchase_id):
    """Получает Purchase из DynamoDB"""
    try:
        response = table.query(
            KeyConditionExpression='purchase_id = :pid',
            ExpressionAttributeValues={
                ':pid': purchase_id
            }
        )

        items = response.get('Items', [])

        if not items:
            print(f"Purchase not found: {purchase_id}")
            return None

        # Должен быть только один item с таким purchase_id
        return items[0]

    except Exception as e:
        print(f"Error getting purchase from DynamoDB: {str(e)}")
        return None


def get_product_from_notion(product_id):
    """Получает Product из Notion"""
    try:
        response = requests.get(
            f"{NOTION_API_URL}/pages/{product_id}",
            headers=notion_headers(),
            timeout=10
        )

        if response.status_code != 200:
            print(f"Error fetching product: {response.text}")
            return None

        page = response.json()
        props = page['properties']

        def get_text(rich_text_array):
            if not rich_text_array:
                return ""
            return "".join([t.get('plain_text', '') for t in rich_text_array])

        product = {
            'id': page['id'],
            'name': props.get('Name', {}).get('title', [{}])[0].get('plain_text', ''),
            'type': props.get('Type', {}).get('select', {}).get('name', 'Individual'),
            'group_size': props.get('Group_Size', {}).get('number'),
        }

        # Получаем talent_id из Relation
        talent_relation = props.get('Talent', {}).get('relation', [])
        product['talent_id'] = talent_relation[0]['id'] if talent_relation else None

        return product

    except Exception as e:
        print(f"Exception getting product: {str(e)}")
        return None


def query_purchases_by_product(product_id):
    """Получает все completed покупки без order_id для товара"""
    try:
        # Исправленный фильтр: поддерживает и отсутствие атрибута, и пустую строку
        response = table.query(
            IndexName='product-index',
            KeyConditionExpression='product_id = :pid',
            FilterExpression='#status = :status AND (attribute_not_exists(order_id) OR order_id = :empty)',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':pid': product_id,
                ':status': 'completed',
                ':empty': ''  # Пустая строка
            }
        )

        return response.get('Items', [])

    except Exception as e:
        print(f"Error querying purchases: {str(e)}")
        return []


def create_order_in_notion(order_id, product_id, buyers_info, buyers_count):
    """Создает Order в Notion"""
    try:
        response = requests.post(
            f"{NOTION_API_URL}/pages",
            headers=notion_headers(),
            json={
                "parent": {"database_id": ORDERS_DB_ID},
                "properties": {
                    "ID": {
                        "title": [
                            {
                                "text": {
                                    "content": order_id
                                }
                            }
                        ]
                    },
                    "Product": {
                        "relation": [
                            {
                                "id": product_id
                            }
                        ]
                    },
                    "Buyers_Info": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": buyers_info[:2000]  # Notion limit
                                }
                            }
                        ]
                    },
                    "Buyers_Count": {
                        "number": buyers_count
                    },
                    "Status": {
                        "select": {
                            "name": "New"
                        }
                    }
                }
            },
            timeout=10
        )

        if response.status_code == 200:
            print(f"Created order in Notion: {order_id}")
            return response.json()['id']
        else:
            print(f"Error creating order: {response.text}")
            return None

    except Exception as e:
        print(f"Exception creating order: {str(e)}")
        return None


def update_purchase_order_id(purchase_id, created_at, order_id):
    """Обновляет order_id в Purchase в DynamoDB"""
    try:
        table.update_item(
            Key={
                'purchase_id': purchase_id,
                'created_at': created_at
            },
            UpdateExpression='SET order_id = :order_id',
            ExpressionAttributeValues={
                ':order_id': order_id
            }
        )
        print(f"Updated purchase {purchase_id} with order_id {order_id}")
        return True
    except Exception as e:
        print(f"Error updating purchase: {str(e)}")
        return False


def notify_comedian(order_id, product_name, buyers_count):
    """TODO: Уведомляет комика о новом заказе"""
    # Placeholder для будущих уведомлений
    print(f"TODO: Notify comedian about order {order_id} ({product_name}, {buyers_count} buyers)")
    pass


def lambda_handler(event, context):
    """
    Main handler для order-manager
    Принимает purchase_id и создает Orders
    """

    print(f"Received event: {json.dumps(event)}")

    try:
        purchase_id = event.get('purchase_id')

        if not purchase_id:
            print("Error: purchase_id not provided")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'purchase_id required'})
            }

        # 1. Получаем Purchase из DynamoDB
        purchase = get_purchase_from_dynamodb(purchase_id)
        if not purchase:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Purchase not found'})
            }

        # Если уже есть order_id - пропускаем
        if purchase.get('order_id') and purchase.get('order_id') != '':
            print(f"Purchase {purchase_id} already has order_id: {purchase['order_id']}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Purchase already has order',
                    'order_id': purchase['order_id']
                })
            }

        product_id = purchase['product_id']

        # 2. Получаем Product из Notion
        product = get_product_from_notion(product_id)
        if not product:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Product not found'})
            }

        print(f"Product type: {product['type']}, group_size: {product.get('group_size')}")

        # 3. Логика создания Order в зависимости от типа
        if product['type'] == 'Individual':
            # Individual товар - сразу создаем Order
            print(f"Individual product - creating order immediately")

            order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

            buyers_info = json.dumps([{
                'name': purchase['buyer_name'],
                'email': purchase['buyer_email'],
                'telegram': purchase['buyer_telegram'],
                'phone': purchase.get('buyer_phone', ''),
                'purchase_id': purchase['purchase_id']
            }], ensure_ascii=False, indent=2)

            # Создаем Order в Notion
            notion_order_id = create_order_in_notion(
                order_id=order_id,
                product_id=product_id,
                buyers_info=buyers_info,
                buyers_count=1
            )

            if not notion_order_id:
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Failed to create order in Notion'})
                }

            # Обновляем Purchase
            update_purchase_order_id(purchase_id, purchase['created_at'], order_id)

            # Уведомляем комика
            notify_comedian(order_id, product['name'], 1)

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Individual order created',
                    'order_id': order_id,
                    'notion_order_id': notion_order_id
                })
            }

        elif product['type'] == 'Group':
            # Group товар - проверяем набралась ли группа
            group_size = product.get('group_size')

            if not group_size:
                print("Warning: Group product without group_size")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Group product missing group_size'})
                }

            print(f"Group product - checking if group is full (size: {group_size})")

            # Получаем все покупки без order_id для этого товара
            pending_purchases = query_purchases_by_product(product_id)

            print(f"Found {len(pending_purchases)} pending purchases for product {product_id}")

            if len(pending_purchases) >= group_size:
                # Группа набралась!
                print(f"Group is full! Creating order for {group_size} buyers")

                # Берем первые group_size покупок
                group_purchases = sorted(pending_purchases, key=lambda x: x['created_at'])[:group_size]

                order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

                buyers_info = json.dumps([{
                    'name': p['buyer_name'],
                    'email': p['buyer_email'],
                    'telegram': p['buyer_telegram'],
                    'phone': p.get('buyer_phone', ''),
                    'purchase_id': p['purchase_id']
                } for p in group_purchases], ensure_ascii=False, indent=2)

                # Создаем Order в Notion
                notion_order_id = create_order_in_notion(
                    order_id=order_id,
                    product_id=product_id,
                    buyers_info=buyers_info,
                    buyers_count=len(group_purchases)
                )

                if not notion_order_id:
                    return {
                        'statusCode': 500,
                        'body': json.dumps({'error': 'Failed to create order in Notion'})
                    }

                # Обновляем все Purchases в группе
                for p in group_purchases:
                    update_purchase_order_id(p['purchase_id'], p['created_at'], order_id)

                # Уведомляем комика
                notify_comedian(order_id, product['name'], len(group_purchases))

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Group order created',
                        'order_id': order_id,
                        'notion_order_id': notion_order_id,
                        'buyers_count': len(group_purchases)
                    })
                }
            else:
                # Группа еще не набралась
                print(f"Group not full yet: {len(pending_purchases)}/{group_size}")

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Waiting for more buyers',
                        'current_count': len(pending_purchases),
                        'required_count': group_size
                    })
                }

        else:
            print(f"Unknown product type: {product['type']}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unknown product type: {product["type"]}'})
            }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }