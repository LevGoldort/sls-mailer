"""DynamoDB utility functions"""
import boto3
from typing import Dict, List, Optional
import os


class DynamoDBClient:
    """Wrapper для работы с DynamoDB"""

    def __init__(self, region: str = None):
        self.region = region or os.environ.get('AWS_REGION', 'eu-north-1')
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)

        # Названия таблиц из environment или дефолтные
        self.events_table_name = os.environ.get('EVENTS_TABLE', 'yallabalagan-events')
        self.locations_table_name = os.environ.get('LOCATIONS_TABLE', 'yallabalagan-locations')
        self.orders_table_name = os.environ.get('ORDERS_TABLE', 'yallabalagan-orders')
        self.coupons_table_name = os.environ.get('COUPONS_TABLE', 'yallabalagan-coupons')

        self.events_table = self.dynamodb.Table(self.events_table_name)
        self.locations_table = self.dynamodb.Table(self.locations_table_name)
        self.orders_table = self.dynamodb.Table(self.orders_table_name)
        self.coupons_table = self.dynamodb.Table(self.coupons_table_name)

    # ===== Events =====
    def put_event(self, event_item: Dict):
        """Создает или обновляет событие"""
        return self.events_table.put_item(Item=event_item)

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Получает событие по ID"""
        response = self.events_table.get_item(
            Key={
                'PK': f'EVENT#{event_id}',
                'SK': 'METADATA'
            }
        )
        return response.get('Item')

    def list_events(self, limit: int = 50) -> List[Dict]:
        """Получает список всех событий"""
        response = self.events_table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={
                ':pk': 'EVENT'
            },
            Limit=limit,
            ScanIndexForward=True  # Сортировка по дате
        )
        return response.get('Items', [])

    def delete_event(self, event_id: str):
        """Удаляет событие"""
        return self.events_table.delete_item(
            Key={
                'PK': f'EVENT#{event_id}',
                'SK': 'METADATA'
            }
        )

    # ===== Locations =====
    def put_location(self, location_item: Dict):
        """Создает или обновляет локацию"""
        return self.locations_table.put_item(Item=location_item)

    def get_location(self, location_id: str) -> Optional[Dict]:
        """Получает локацию по ID"""
        response = self.locations_table.get_item(
            Key={
                'PK': f'LOCATION#{location_id}',
                'SK': 'METADATA'
            }
        )
        return response.get('Item')

    def get_location_by_slug(self, slug: str) -> Optional[Dict]:
        """Получает локацию по slug"""
        response = self.locations_table.query(
            IndexName='SlugIndex',
            KeyConditionExpression='slug = :slug',
            ExpressionAttributeValues={
                ':slug': slug
            },
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def list_locations(self, limit: int = 50) -> List[Dict]:
        """Получает список всех локаций"""
        response = self.locations_table.scan(Limit=limit)
        return response.get('Items', [])

    def delete_location(self, location_id: str):
        """Удаляет локацию"""
        return self.locations_table.delete_item(
            Key={
                'PK': f'LOCATION#{location_id}',
                'SK': 'METADATA'
            }
        )

    # ===== Orders =====
    def put_order(self, order_item: Dict):
        """Создает заказ"""
        return self.orders_table.put_item(Item=order_item)

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Получает заказ по ID"""
        response = self.orders_table.get_item(
            Key={
                'PK': f'ORDER#{order_id}',
                'SK': 'METADATA'
            }
        )
        return response.get('Item')

    def get_orders_by_event(self, event_id: str, limit: int = 100) -> List[Dict]:
        """Получает все заказы для события"""
        response = self.orders_table.query(
            IndexName='EventIndex',
            KeyConditionExpression='event_id = :event_id',
            ExpressionAttributeValues={
                ':event_id': event_id
            },
            Limit=limit
        )
        return response.get('Items', [])

    def get_orders_by_email(self, email: str, limit: int = 50) -> List[Dict]:
        """Получает все заказы клиента по email"""
        response = self.orders_table.query(
            IndexName='EmailIndex',
            KeyConditionExpression='customer_email = :email',
            ExpressionAttributeValues={
                ':email': email
            },
            Limit=limit,
            ScanIndexForward=False  # Сортировка по дате (новые первые)
        )
        return response.get('Items', [])

    def update_order_payment_status(self, order_id: str, status: str, transaction_id: str = None):
        """Обновляет статус оплаты заказа"""
        update_expr = 'SET payment.#status = :status'
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {':status': status}

        if transaction_id:
            update_expr += ', payment.allpay_transaction_id = :txn_id'
            expr_attr_values[':txn_id'] = transaction_id

        if status == 'completed':
            from datetime import datetime
            update_expr += ', payment.paid_at = :paid_at'
            expr_attr_values[':paid_at'] = datetime.utcnow().isoformat()

        return self.orders_table.update_item(
            Key={
                'PK': f'ORDER#{order_id}',
                'SK': 'METADATA'
            },
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

    def list_orders(self, limit: int = 100) -> List[Dict]:
        """Получает список всех заказов"""
        response = self.orders_table.scan(Limit=limit)
        return response.get('Items', [])

    # ===== Coupons =====
    def put_coupon(self, coupon_item: Dict):
        """Создает или обновляет купон"""
        return self.coupons_table.put_item(Item=coupon_item)

    def get_coupon(self, coupon_code: str) -> Optional[Dict]:
        """Получает купон по коду"""
        response = self.coupons_table.get_item(
            Key={
                'PK': f'COUPON#{coupon_code}',
                'SK': 'METADATA'
            }
        )
        return response.get('Item')

    def list_coupons(self, status: str = None, limit: int = 100) -> List[Dict]:
        """Получает список купонов, опционально фильтрует по статусу"""
        if status:
            # Используем GSI для фильтрации по статусу
            response = self.coupons_table.query(
                IndexName='StatusIndex',
                KeyConditionExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': status},
                Limit=limit,
                ScanIndexForward=False  # Сортировка по valid_until (новые первые)
            )
        else:
            # Сканируем всю таблицу
            response = self.coupons_table.scan(Limit=limit)

        return response.get('Items', [])

    def delete_coupon(self, coupon_code: str):
        """Удаляет купон"""
        return self.coupons_table.delete_item(
            Key={
                'PK': f'COUPON#{coupon_code}',
                'SK': 'METADATA'
            }
        )

    def increment_coupon_uses(self, coupon_code: str) -> Dict:
        """Увеличивает счетчик использований купона"""
        from datetime import datetime

        response = self.coupons_table.update_item(
            Key={
                'PK': f'COUPON#{coupon_code}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET current_uses = current_uses + :inc, updated_at = :now',
            ExpressionAttributeValues={
                ':inc': 1,
                ':now': datetime.utcnow().isoformat()
            },
            ReturnValues='ALL_NEW'
        )
        return response.get('Attributes', {})

    def update_coupon_status(self, coupon_code: str, status: str):
        """Обновляет статус купона"""
        from datetime import datetime

        return self.coupons_table.update_item(
            Key={
                'PK': f'COUPON#{coupon_code}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET #status = :status, updated_at = :now',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': status,
                ':now': datetime.utcnow().isoformat()
            }
        )
