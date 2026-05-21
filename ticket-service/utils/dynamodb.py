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
        self.seat_reservations_table_name = os.environ.get('SEAT_RESERVATIONS_TABLE', 'yallabalagan-seat-reservations')
        self.performers_table_name = os.environ.get('PERFORMERS_TABLE', 'yallabalagan-performers')
        self.products_table_name = os.environ.get('PRODUCTS_TABLE', 'yallabalagan-products')
        self.merchandise_orders_table_name = os.environ.get('MERCHANDISE_ORDERS_TABLE', 'yallabalagan-merchandise-orders')

        self.events_table = self.dynamodb.Table(self.events_table_name)
        self.locations_table = self.dynamodb.Table(self.locations_table_name)
        self.orders_table = self.dynamodb.Table(self.orders_table_name)
        self.coupons_table = self.dynamodb.Table(self.coupons_table_name)
        self.seat_reservations_table = self.dynamodb.Table(self.seat_reservations_table_name)
        self.performers_table = self.dynamodb.Table(self.performers_table_name)
        self.products_table = self.dynamodb.Table(self.products_table_name)
        self.merchandise_orders_table = self.dynamodb.Table(self.merchandise_orders_table_name)

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

    def get_event_by_slug(self, slug: str) -> Optional[Dict]:
        """Получает событие по slug (требует GSI `SlugIndex` по атрибуту slug)"""
        if not slug:
            return None

        response = self.events_table.query(
            IndexName='SlugIndex',
            KeyConditionExpression='slug = :slug',
            ExpressionAttributeValues={
                ':slug': slug
            },
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def is_event_slug_taken(self, slug: str, exclude_event_id: str = None) -> bool:
        """Проверяет, занят ли slug другим событием"""
        item = self.get_event_by_slug(slug)
        if not item:
            return False
        if exclude_event_id and item.get('event_id') == exclude_event_id:
            return False
        return True

    def list_events_by_owner(self, owner_id: str) -> List[Dict]:
        """Получает события принадлежащие конкретному владельцу (OwnerIndex GSI)"""
        response = self.events_table.query(
            IndexName='OwnerIndex',
            KeyConditionExpression='owner_id = :owner_id',
            ExpressionAttributeValues={':owner_id': owner_id}
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
        print(f"[DEBUG] put_order called for order_id: {order_item.get('order_id')}")
        print(f"[DEBUG] Table name: {self.orders_table_name}")
        print(f"[DEBUG] Order item PK: {order_item.get('PK')}, SK: {order_item.get('SK')}")
        print(f"[DEBUG] Order item keys: {list(order_item.keys())}")

        try:
            response = self.orders_table.put_item(Item=order_item)
            print(f"[DEBUG] put_item response: {response}")
            print(f"[DEBUG] Successfully saved order {order_item.get('order_id')} to DynamoDB")
            return response
        except Exception as e:
            print(f"[ERROR] Failed to save order {order_item.get('order_id')}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Получает заказ по ID"""
        print(f"[DEBUG] get_order called for order_id: {order_id}")
        print(f"[DEBUG] Table name: {self.orders_table_name}")
        print(f"[DEBUG] Looking for PK: ORDER#{order_id}, SK: METADATA")

        response = self.orders_table.get_item(
            Key={
                'PK': f'ORDER#{order_id}',
                'SK': 'METADATA'
            }
        )

        item = response.get('Item')
        if item:
            print(f"[DEBUG] ✓ Order {order_id} found in DynamoDB")
        else:
            print(f"[DEBUG] ✗ Order {order_id} NOT FOUND in DynamoDB")
            print(f"[DEBUG] Response: {response}")

        return item

    def get_orders_by_event(self, event_id: str, limit: int = None) -> List[Dict]:
        """Получает все заказы для события (с пагинацией)"""
        items = []
        query_params = {
            'IndexName': 'EventIndex',
            'KeyConditionExpression': 'event_id = :event_id',
            'ExpressionAttributeValues': {
                ':event_id': event_id
            }
        }

        while True:
            response = self.orders_table.query(**query_params)
            items.extend(response.get('Items', []))

            if limit and len(items) >= limit:
                return items[:limit]

            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break
            query_params['ExclusiveStartKey'] = last_key

        return items

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

    def update_order_notification_status(self, order_id: str, email_sent: bool = None, sms_sent: bool = None):
        """Обновляет статус уведомлений заказа"""
        from datetime import datetime
        
        update_expr_parts = []
        expr_attr_values = {}
        
        if email_sent is not None:
            update_expr_parts.append('notifications.email_sent = :email_sent')
            expr_attr_values[':email_sent'] = email_sent
        
        if sms_sent is not None:
            update_expr_parts.append('notifications.sms_sent = :sms_sent')
            expr_attr_values[':sms_sent'] = sms_sent
        
        if not update_expr_parts:
            return  # Nothing to update
        
        update_expr = 'SET ' + ', '.join(update_expr_parts)
        
        return self.orders_table.update_item(
            Key={
                'PK': f'ORDER#{order_id}',
                'SK': 'METADATA'
            },
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_attr_values
        )

    def get_order_by_ticket_code(self, ticket_code: str) -> Optional[Dict]:
        """Находит заказ по коду билета (сканирует все заказы)"""
        # Scan orders table and filter by ticket code
        # Note: This is not efficient for large datasets, but works for MVP
        # TODO: Consider adding GSI for ticket codes if needed
        
        response = self.orders_table.scan()
        
        for item in response.get('Items', []):
            qr_codes = item.get('qr_codes', [])
            for qr in qr_codes:
                if qr.get('code') == ticket_code:
                    return item
        
        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = self.orders_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            for item in response.get('Items', []):
                qr_codes = item.get('qr_codes', [])
                for qr in qr_codes:
                    if qr.get('code') == ticket_code:
                        return item
        
        return None

    def update_ticket_scanned_status(self, order_id: str, ticket_code: str, scanned: bool = True):
        """Обновляет статус сканирования билета"""
        from datetime import datetime
        
        # Get order first
        order_data = self.get_order(order_id)
        if not order_data:
            return None
        
        # Update the specific QR code in the list
        qr_codes = order_data.get('qr_codes', [])
        updated = False
        
        for i, qr in enumerate(qr_codes):
            if qr.get('code') == ticket_code:
                qr_codes[i]['scanned'] = scanned
                if scanned:
                    qr_codes[i]['scanned_at'] = datetime.utcnow().isoformat()
                updated = True
                break
        
        if not updated:
            return None
        
        # Update the order
        return self.orders_table.update_item(
            Key={
                'PK': f'ORDER#{order_id}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET qr_codes = :qr_codes',
            ExpressionAttributeValues={
                ':qr_codes': qr_codes
            }
        )

    def list_orders(self, limit: int = None) -> List[Dict]:
        """Получает список всех заказов (с пагинацией)"""
        items = []
        scan_params = {}

        while True:
            response = self.orders_table.scan(**scan_params)
            items.extend(response.get('Items', []))

            if limit and len(items) >= limit:
                return items[:limit]

            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break
            scan_params['ExclusiveStartKey'] = last_key

        return items

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

    # ===== Performers =====
    def put_performer(self, performer_item: Dict):
        return self.performers_table.put_item(Item=performer_item)

    def get_performer(self, performer_id: str) -> Optional[Dict]:
        response = self.performers_table.get_item(
            Key={'PK': f'PERFORMER#{performer_id}', 'SK': 'METADATA'}
        )
        return response.get('Item')

    def get_performer_by_slug(self, slug: str) -> Optional[Dict]:
        response = self.performers_table.query(
            IndexName='SlugIndex',
            KeyConditionExpression='slug = :slug',
            ExpressionAttributeValues={':slug': slug},
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def list_performers(self, tenant_id: str = 'yallabalagan', status: str = None) -> List[Dict]:
        gsi1pk = f'TENANT#{tenant_id}'
        kwargs = {
            'IndexName': 'TenantIndex',
            'KeyConditionExpression': 'GSI1PK = :pk',
            'ExpressionAttributeValues': {':pk': gsi1pk},
        }
        if status:
            kwargs['KeyConditionExpression'] += ' AND begins_with(GSI1SK, :status_prefix)'
            kwargs['ExpressionAttributeValues'][':status_prefix'] = f'{status}#'
        response = self.performers_table.query(**kwargs)
        return response.get('Items', [])

    def delete_performer(self, performer_id: str):
        return self.performers_table.delete_item(
            Key={'PK': f'PERFORMER#{performer_id}', 'SK': 'METADATA'}
        )

    # ===== Products =====
    def put_product(self, product_item: Dict):
        return self.products_table.put_item(Item=product_item)

    def get_product(self, product_id: str) -> Optional[Dict]:
        response = self.products_table.get_item(
            Key={'PK': f'PRODUCT#{product_id}', 'SK': 'METADATA'}
        )
        return response.get('Item')

    def get_product_by_slug(self, slug: str) -> Optional[Dict]:
        response = self.products_table.query(
            IndexName='SlugIndex',
            KeyConditionExpression='slug = :slug',
            ExpressionAttributeValues={':slug': slug},
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None

    def list_products(self, status: str = 'active') -> List[Dict]:
        response = self.products_table.query(
            IndexName='StatusIndex',
            KeyConditionExpression='GSI2PK = :status',
            ExpressionAttributeValues={':status': status},
            ScanIndexForward=False
        )
        return response.get('Items', [])

    def list_products_by_performer(self, performer_id: str) -> List[Dict]:
        response = self.products_table.query(
            IndexName='PerformerIndex',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={':pk': f'PERFORMER#{performer_id}'},
            ScanIndexForward=False
        )
        return response.get('Items', [])

    def increment_sold_slots(self, product_id: str) -> Dict:
        from datetime import datetime
        response = self.products_table.update_item(
            Key={'PK': f'PRODUCT#{product_id}', 'SK': 'METADATA'},
            UpdateExpression='SET sold_slots = sold_slots + :inc, updated_at = :now',
            ExpressionAttributeValues={':inc': 1, ':now': datetime.utcnow().isoformat()},
            ReturnValues='ALL_NEW'
        )
        return response.get('Attributes', {})

    def delete_product(self, product_id: str):
        return self.products_table.delete_item(
            Key={'PK': f'PRODUCT#{product_id}', 'SK': 'METADATA'}
        )

    # ===== Merchandise Orders =====
    def put_merchandise_order(self, order_item: Dict):
        return self.merchandise_orders_table.put_item(Item=order_item)

    def get_merchandise_order(self, order_id: str) -> Optional[Dict]:
        response = self.merchandise_orders_table.get_item(
            Key={'PK': f'MERCH_ORDER#{order_id}', 'SK': 'METADATA'}
        )
        return response.get('Item')

    def update_merchandise_order_status(self, order_id: str, status: str, payment_id: str = None):
        from datetime import datetime
        update_expr = 'SET #status = :status'
        expr_names = {'#status': 'status'}
        expr_values = {':status': status}
        if payment_id:
            update_expr += ', payment_id = :pid'
            expr_values[':pid'] = payment_id
        return self.merchandise_orders_table.update_item(
            Key={'PK': f'MERCH_ORDER#{order_id}', 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

    # ===== Seat Reservations =====
    def get_seat_reservations(self, event_id: str) -> List[Dict]:
        """Получает все активные резервации для события"""
        import time
        current_time = int(time.time())

        response = self.seat_reservations_table.query(
            KeyConditionExpression='event_id = :event_id',
            FilterExpression='expires_at > :now',
            ExpressionAttributeValues={
                ':event_id': event_id,
                ':now': current_time
            }
        )
        return response.get('Items', [])

    def reserve_seat(self, event_id: str, seat_id: str, session_id: str, expires_at: int) -> bool:
        """
        Резервирует место с optimistic locking.
        Возвращает True если резервация успешна, False если место уже зарезервировано.
        """
        import time
        from botocore.exceptions import ClientError

        current_time = int(time.time())

        try:
            self.seat_reservations_table.put_item(
                Item={
                    'event_id': event_id,
                    'seat_id': seat_id,
                    'session_id': session_id,
                    'reserved_at': current_time,
                    'expires_at': expires_at
                },
                ConditionExpression='attribute_not_exists(seat_id) OR expires_at < :now',
                ExpressionAttributeValues={
                    ':now': current_time
                }
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise

    def release_seat(self, event_id: str, seat_id: str, session_id: str = None) -> bool:
        """
        Освобождает резервацию места.
        Если указан session_id, освобождает только если резервация принадлежит этой сессии.
        """
        from botocore.exceptions import ClientError

        try:
            if session_id:
                # Освобождаем только если принадлежит этой сессии
                self.seat_reservations_table.delete_item(
                    Key={
                        'event_id': event_id,
                        'seat_id': seat_id
                    },
                    ConditionExpression='session_id = :sid',
                    ExpressionAttributeValues={
                        ':sid': session_id
                    }
                )
            else:
                # Освобождаем без проверки
                self.seat_reservations_table.delete_item(
                    Key={
                        'event_id': event_id,
                        'seat_id': seat_id
                    }
                )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise

    def release_seats(self, event_id: str, seat_ids: List[str], session_id: str = None) -> int:
        """
        Освобождает несколько резерваций.
        Возвращает количество успешно освобождённых мест.
        """
        released_count = 0
        for seat_id in seat_ids:
            if self.release_seat(event_id, seat_id, session_id):
                released_count += 1
        return released_count
