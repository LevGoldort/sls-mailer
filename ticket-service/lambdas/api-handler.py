"""
Main API Handler Lambda для билетного сервиса
Обрабатывает все API запросы через API Gateway
"""
import json
import os
import sys
from typing import Dict, Any
from decimal import Decimal
import boto3
import base64
import re

# Add parent directory to path для импорта models и utils
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Event, Location, Order, Customer, OrderTicket, TicketType, Coupon, Address, Coordinates, Parking, Media, Contact
from utils.dynamodb import DynamoDBClient
from utils.payment import get_payment_provider, parse_webhook_payload
from utils.auth import get_admin_authenticator
from datetime import datetime, timezone


# Helper для конвертации Decimal в int/float
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


# Инициализация DynamoDB клиента
db = DynamoDBClient()
SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$')  # 2-50 chars, lowercase, digits, hyphen


def normalize_slug(slug: str) -> str:
    """Приводит slug к безопасному формату"""
    if not slug:
        return ''
    cleaned = slug.strip().lower()
    cleaned = cleaned.replace(' ', '-')
    cleaned = re.sub(r'[^a-z0-9-]', '-', cleaned)
    cleaned = re.sub(r'-{2,}', '-', cleaned)
    return cleaned.strip('-')


def validate_event_slug(slug: str, current_event_id: str = None) -> str:
    """Проверяет slug на валидность и уникальность"""
    normalized = normalize_slug(slug)

    if not normalized:
        raise ValueError("Slug не может быть пустым")

    if not SLUG_PATTERN.match(normalized):
        raise ValueError("Slug может содержать только латинские буквы, цифры и дефисы (2-50 символов)")

    if db.is_event_slug_taken(normalized, exclude_event_id=current_event_id):
        raise ValueError("Такой slug уже используется другим событием")

    return normalized


def log_security_event(event_type: str, details: dict):
    """Log security events for monitoring"""
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event_type': event_type,
        'details': details
    }
    print(f"SECURITY_EVENT: {json.dumps(log_entry)}")


def get_client_identifier(event: Dict) -> str:
    """Extract client IP for logging"""
    headers = event.get('headers', {})
    forwarded_for = headers.get('x-forwarded-for', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()

    http_context = event.get('requestContext', {}).get('http', {})
    return http_context.get('sourceIp', 'unknown')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler для API Gateway requests
    """
    print(f"Received event: {json.dumps(event)}")

    # Извлекаем метод и путь
    http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method'))
    path = event.get('path', event.get('rawPath', ''))

    # Remove stage from path for HTTP API v2.0
    stage = event.get('requestContext', {}).get('stage')
    if stage and path.startswith(f'/{stage}/'):
        path = path[len(stage)+1:]  # Remove '/stage' prefix

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': ''
        }

    # Routing
    try:
        if path.startswith('/api/events'):
            return handle_events(event, http_method, path)
        elif path.startswith('/api/locations'):
            return handle_locations(event, http_method, path)
        elif path.startswith('/api/orders'):
            return handle_orders(event, http_method, path)
        elif path.startswith('/api/coupons'):
            return handle_coupons(event, http_method, path)
        elif path == '/api/upload-image' and http_method == 'POST':
            return handle_image_upload(event)
        elif path == '/api/admin/regenerate-site' and http_method == 'POST':
            return handle_regenerate_site(event)
        elif path == '/api/webhooks/allpay' and http_method == 'POST':
            return handle_allpay_webhook(event)
        else:
            return error_response(404, "Endpoint not found")

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Internal server error: {str(e)}")


# ===== Events Handlers =====
def handle_events(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/events"""

    # GET /api/events - список событий
    if method == 'GET' and path == '/api/events':
        return list_events()

    # GET /api/events/slug/{slug} - детали события по slug
    if method == 'GET' and path.startswith('/api/events/slug/'):
        slug = path.split('/')[-1]
        return get_event_by_slug(slug)

    # POST /api/events - создать событие (admin)
    if method == 'POST' and path == '/api/events':
        return create_event(event)

    # GET /api/events/{id} - детали события
    if method == 'GET' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return get_event(event_id)

    # PUT /api/events/{id} - обновить событие (admin)
    if method == 'PUT' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return update_event(event_id, event)

    # DELETE /api/events/{id} - удалить событие (admin)
    if method == 'DELETE' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return delete_event(event_id, event)

    return error_response(404, "Events endpoint not found")


def list_events() -> Dict:
    """GET /api/events"""
    items = db.list_events()

    events = []
    for item in items:
        try:
            evt = Event.from_dynamodb_item(item)
            events.append({
                'event_id': evt.event_id,
                'title': evt.title,
                'description': evt.description,
                'date': evt.date,
                'location_id': evt.location_id,
                'ticket_types': [tt.to_dict() for tt in evt.ticket_types],
                'status': evt.status,
                'images': evt.images,
                'slug': evt.slug,
                'currency': evt.currency
            })
        except Exception as e:
            print(f"Error parsing event: {e}")
            continue

    return success_response({
        'events': events,
        'count': len(events)
    })


def get_event(event_id: str) -> Dict:
    """GET /api/events/{id}"""
    item = db.get_event(event_id)

    if not item:
        return error_response(404, "Event not found")

    evt = Event.from_dynamodb_item(item)

    return success_response({
        'event': evt.to_dynamodb_item()
    })


def get_event_by_slug(slug: str) -> Dict:
    """GET /api/events/slug/{slug}"""
    if not slug:
        return error_response(400, "Slug is required")

    item = db.get_event_by_slug(slug)
    if not item:
        return error_response(404, "Event not found")

    evt = Event.from_dynamodb_item(item)

    return success_response({
        'event': evt.to_dynamodb_item()
    })


def create_event(request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/events"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_event_create', {
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация обязательных полей
        required = ['title', 'description', 'date', 'location_id', 'ticket_types']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        # Создаем типы билетов
        ticket_types = []
        for tt in body['ticket_types']:
            ticket_types.append(TicketType(
                id=tt['id'],
                name=tt['name'],
                price=tt['price'],
                total=tt['total'],
                available=tt['total']  # Initially all available
            ))

        # Обрабатываем slug (опционально)
        slug_value = None
        if body.get('slug'):
            try:
                slug_value = validate_event_slug(body['slug'])
            except ValueError as exc:
                return error_response(400, str(exc))

        # Создаем событие
        event_id = Event.generate_id()
        evt = Event(
            event_id=event_id,
            title=body['title'],
            description=body['description'],
            date=body['date'],
            location_id=body['location_id'],
            ticket_types=ticket_types,
            currency=body.get('currency', 'ILS'),
            images=body.get('images', []),
            slug=slug_value
        )

        # Сохраняем в DynamoDB
        db.put_event(evt.to_dynamodb_item())

        return success_response({
            'message': 'Event created successfully',
            'event_id': event_id,
            'event': evt.to_dynamodb_item()
        }, status_code=201)

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to create event: {str(e)}")


def update_event(event_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - PUT /api/events/{id}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_event_update', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Проверяем что событие существует
        item = db.get_event(event_id)
        if not item:
            return error_response(404, "Event not found")

        body = json.loads(request_event.get('body', '{}'))

        # Получаем текущее событие
        evt = Event.from_dynamodb_item(item)

        # Обновляем slug (можно очистить)
        if 'slug' in body:
            slug_value = body['slug']
            if slug_value:
                try:
                    evt.slug = validate_event_slug(slug_value, evt.event_id)
                except ValueError as exc:
                    return error_response(400, str(exc))
            else:
                evt.slug = None

        # Обновляем поля
        if 'title' in body:
            evt.title = body['title']
        if 'description' in body:
            evt.description = body['description']
        if 'date' in body:
            evt.date = body['date']
        if 'location_id' in body:
            evt.location_id = body['location_id']
        if 'currency' in body:
            evt.currency = body['currency']
        if 'images' in body:
            evt.images = body['images']
        if 'status' in body:
            evt.status = body['status']
        if 'ticket_types' in body:
            # Обновляем типы билетов
            ticket_types = []
            for tt in body['ticket_types']:
                ticket_types.append(TicketType(
                    id=tt['id'],
                    name=tt['name'],
                    price=tt['price'],
                    total=tt['total'],
                    available=tt.get('available', tt['total'])
                ))
            evt.ticket_types = ticket_types

        evt.updated_at = datetime.utcnow().isoformat()

        # Сохраняем
        db.put_event(evt.to_dynamodb_item())

        return success_response({
            'message': 'Event updated successfully',
            'event_id': event_id,
            'event': evt.to_dynamodb_item()
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to update event: {str(e)}")


def delete_event(event_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - DELETE /api/events/{id}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_event_delete', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    item = db.get_event(event_id)
    if not item:
        return error_response(404, "Event not found")

    db.delete_event(event_id)

    return success_response({
        'message': 'Event deleted successfully',
        'event_id': event_id
    })


# ===== Locations Handlers =====
def handle_locations(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/locations"""

    # GET /api/locations - список локаций
    if method == 'GET' and path == '/api/locations':
        return list_locations()

    # GET /api/locations/{id} - детали локации
    if method == 'GET' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return get_location(location_id)

    # POST /api/locations - создать локацию (admin)
    if method == 'POST' and path == '/api/locations':
        return create_location(event)

    # PUT /api/locations/{id} - обновить локацию (admin)
    if method == 'PUT' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return update_location(location_id, event)

    # DELETE /api/locations/{id} - удалить локацию (admin)
    if method == 'DELETE' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return delete_location(location_id, event)

    return error_response(404, "Locations endpoint not found")


def list_locations() -> Dict:
    """GET /api/locations"""
    items = db.list_locations()

    locations = []
    for item in items:
        try:
            loc = Location.from_dynamodb_item(item)
            locations.append(loc.to_dynamodb_item())
        except Exception as e:
            print(f"Error parsing location: {e}")
            continue

    return success_response({
        'locations': locations,
        'count': len(locations)
    })


def get_location(location_id: str) -> Dict:
    """GET /api/locations/{id} or GET /api/locations/{slug}"""
    # Попробуем найти по ID
    item = db.get_location(location_id)

    # Если не найдено, попробуем по slug
    if not item:
        item = db.get_location_by_slug(location_id)

    if not item:
        return error_response(404, "Location not found")

    loc = Location.from_dynamodb_item(item)

    return success_response({
        'location': loc.to_dynamodb_item()
    })


def create_location(request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/locations"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_location_create', {
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация обязательных полей
        required = ['name', 'slug', 'address', 'capacity']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        # Парсим address
        address_data = body['address']
        address = Address(
            street=address_data.get('street', ''),
            city=address_data.get('city', ''),
            coordinates=Coordinates(**address_data.get('coordinates', {'lat': 0, 'lng': 0}))
        )

        # Парсим parkings
        parkings = []
        for p in body.get('parkings', []):
            parkings.append(Parking(
                description=p.get('description', ''),
                coordinates=Coordinates(**p.get('coordinates', {'lat': 0, 'lng': 0})),
                google_maps_url=p.get('google_maps_url')
            ))

        # Парсим media
        media_data = body.get('media', {})
        media = Media(
            photos=media_data.get('photos', []),
            videos=media_data.get('videos', [])
        )

        # Создаем локацию
        location_id = Location.generate_id()
        loc = Location(
            location_id=location_id,
            name=body['name'],
            slug=body['slug'],
            address=address,
            capacity=body['capacity'],
            description=body.get('description', ''),
            short_description=body.get('short_description', ''),
            parkings=parkings,
            media=media
        )

        # Сохраняем в DynamoDB
        db.put_location(loc.to_dynamodb_item())

        return success_response({
            'message': 'Location created successfully',
            'location_id': location_id,
            'location': loc.to_dynamodb_item()
        }, status_code=201)

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to create location: {str(e)}")


def update_location(location_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - PUT /api/locations/{id}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_location_update', {
            'location_id': location_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Проверяем что локация существует
        item = db.get_location(location_id)
        if not item:
            return error_response(404, "Location not found")

        body = json.loads(request_event.get('body', '{}'))

        # Получаем текущую локацию
        loc = Location.from_dynamodb_item(item)

        # Обновляем поля
        if 'name' in body:
            loc.name = body['name']
        if 'slug' in body:
            loc.slug = body['slug']
        if 'address' in body:
            address_data = body['address']
            loc.address = Address(
                street=address_data.get('street', ''),
                city=address_data.get('city', ''),
                coordinates=Coordinates(**address_data.get('coordinates', {'lat': 0, 'lng': 0}))
            )
        if 'capacity' in body:
            loc.capacity = body['capacity']
        if 'description' in body:
            loc.description = body['description']
        if 'short_description' in body:
            loc.short_description = body['short_description']
        if 'parkings' in body:
            parkings = []
            for p in body['parkings']:
                parkings.append(Parking(
                    description=p.get('description', ''),
                    coordinates=Coordinates(**p.get('coordinates', {'lat': 0, 'lng': 0})),
                    google_maps_url=p.get('google_maps_url')
                ))
            loc.parkings = parkings
        if 'media' in body:
            media_data = body['media']
            loc.media = Media(
                photos=media_data.get('photos', []),
                videos=media_data.get('videos', [])
            )

        loc.updated_at = datetime.utcnow().isoformat()

        # Сохраняем
        db.put_location(loc.to_dynamodb_item())

        return success_response({
            'message': 'Location updated successfully',
            'location_id': location_id,
            'location': loc.to_dynamodb_item()
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to update location: {str(e)}")


def delete_location(location_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - DELETE /api/locations/{id}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_location_delete', {
            'location_id': location_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    item = db.get_location(location_id)
    if not item:
        return error_response(404, "Location not found")

    db.delete_location(location_id)

    return success_response({
        'message': 'Location deleted successfully',
        'location_id': location_id
    })


# ===== Orders Handlers =====
def handle_orders(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/orders"""

    # GET /api/orders?event_id=xxx - список заказов для события
    if method == 'GET' and path == '/api/orders':
        query_params = event.get('queryStringParameters', {}) or {}
        event_id = query_params.get('event_id')
        if event_id:
            return list_orders_by_event(event_id, event)
        else:
            return list_all_orders(event)

    # POST /api/orders - создать заказ
    if method == 'POST' and path == '/api/orders':
        return create_order(event)

    # GET /api/orders/verify/{ticket_code} - проверить билет
    if method == 'GET' and path.startswith('/api/orders/verify/'):
        ticket_code = path.split('/')[-1]
        return verify_ticket(ticket_code)

    # GET /api/orders/{id}/can-refund - проверить возможность возврата
    if method == 'GET' and path.endswith('/can-refund'):
        order_id = path.split('/')[-2]  # /api/orders/{id}/can-refund
        return check_can_refund(order_id)

    # POST /api/orders/{id}/refund - обработать возврат
    if method == 'POST' and path.endswith('/refund'):
        order_id = path.split('/')[-2]  # /api/orders/{id}/refund
        return process_refund(order_id, event)

    # GET /api/orders/{id} - детали заказа
    if method == 'GET' and path.startswith('/api/orders/'):
        order_id = path.split('/')[-1]
        return get_order(order_id)

    return error_response(404, "Orders endpoint not found")


def list_orders_by_event(event_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - GET /api/orders?event_id=xxx - список заказов для события"""

    # SECURITY: Require admin authentication (PII protection)
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_orders_access', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        items = db.get_orders_by_event(event_id)

        orders = []
        for item in items:
            try:
                order = Order.from_dynamodb_item(item)
                orders.append(order.to_dynamodb_item())
            except Exception as e:
                print(f"Error parsing order: {e}")
                continue

        return success_response({
            'orders': orders,
            'count': len(orders),
            'event_id': event_id
        })

    except Exception as e:
        print(f"Error listing orders for event {event_id}: {e}")
        return error_response(500, f"Failed to list orders: {str(e)}")


def list_all_orders(request_event: Dict) -> Dict:
    """ADMIN ONLY - GET /api/orders - список всех заказов"""

    # SECURITY: Require admin authentication (PII protection)
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_all_orders_access', {
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        items = db.list_orders()

        orders = []
        for item in items:
            try:
                order = Order.from_dynamodb_item(item)
                orders.append(order.to_dynamodb_item())
            except Exception as e:
                print(f"Error parsing order: {e}")
                continue

        return success_response({
            'orders': orders,
            'count': len(orders)
        })

    except Exception as e:
        print(f"Error listing all orders: {e}")
        return error_response(500, f"Failed to list orders: {str(e)}")


def create_order(request_event: Dict) -> Dict:
    """POST /api/orders - создать заказ"""
    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация
        required = ['event_id', 'customer', 'tickets']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        event_id = body['event_id']

        # Проверяем что событие существует
        event_item = db.get_event(event_id)
        if not event_item:
            return error_response(404, "Event not found")

        evt = Event.from_dynamodb_item(event_item)

        # Проверяем что событие не прошло (event_date + 1 hour >= now)
        from datetime import datetime, timedelta, timezone
        event_dt = datetime.fromisoformat(evt.date.replace('Z', '+00:00'))
        event_end_time = event_dt + timedelta(hours=1)
        now = datetime.now(timezone.utc)

        if event_end_time <= now:
            return error_response(400, "This event has already ended. Ticket sales are closed.")

        # Проверяем доступность билетов
        order_tickets = []
        for ticket_req in body['tickets']:
            type_id = ticket_req['type_id']
            quantity = ticket_req['quantity']

            ticket_type = evt.get_ticket_type(type_id)
            if not ticket_type:
                return error_response(400, f"Invalid ticket type: {type_id}")

            if ticket_type.available < quantity:
                return error_response(400, f"Not enough tickets available for {ticket_type.name}")

            order_tickets.append(OrderTicket(
                type_id=type_id,
                type_name=ticket_type.name,
                quantity=quantity,
                price_per_ticket=ticket_type.price
            ))

        # Calculate subtotal
        subtotal = sum(t.get_total() for t in order_tickets)

        # Process coupon if provided
        coupon_code = body.get('coupon_code')
        discount_amount = 0

        if coupon_code:
            # Get and validate coupon
            coupon_item = db.get_coupon(coupon_code)
            if not coupon_item:
                return error_response(400, "Coupon not found")

            coupon = Coupon.from_dynamodb_item(coupon_item)

            # Validate coupon
            is_valid, error_msg = coupon.is_valid(event_id)
            if not is_valid:
                return error_response(400, f"Invalid coupon: {error_msg}")

            # Calculate discount (total tickets for per-ticket discount)
            total_tickets = sum(t.quantity for t in order_tickets)
            discount_amount = coupon.calculate_discount(subtotal, total_tickets)

            # NOTE: Coupon usage will be incremented ONLY after successful payment
            # (in webhook handler when payment_status == 'completed')

        # Calculate total with discount
        total_amount = subtotal - discount_amount

        # Создаем заказ
        customer = Customer(**body['customer'])
        order = Order(
            order_id=Order.generate_id(),
            event_id=event_id,
            customer=customer,
            tickets=order_tickets,
            total_amount=total_amount,
            coupon_code=coupon_code,
            discount_amount=discount_amount
        )

        # НЕ генерируем QR коды и НЕ уменьшаем билеты до успешной оплаты!
        # Это будет сделано в webhook handler при получении статуса 'completed'

        # Сохраняем заказ со статусом pending
        db.put_order(order.to_dynamodb_item())

        # Generate payment URL via payment provider
        payment_provider = get_payment_provider()
        try:
            payment_url = payment_provider.create_payment_url(
                order_id=order.order_id,
                amount=order.total_amount,
                currency=order.currency,
                email=order.customer.email,
                event_id=event_id,
                customer_name=order.customer.name
            )
        except Exception as e:
            print(f"Failed to create payment URL: {str(e)}")
            payment_url = f"/processing.html?order_id={order.order_id}"  # Fallback

        return success_response({
            'message': 'Order created successfully',
            'order_id': order.order_id,
            'order': order.to_dynamodb_item(),
            'payment_url': payment_url
        }, status_code=201)

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to create order: {str(e)}")


def get_order(order_id: str) -> Dict:
    """GET /api/orders/{id}"""
    item = db.get_order(order_id)

    if not item:
        return error_response(404, "Order not found")

    order = Order.from_dynamodb_item(item)

    return success_response({
        'order': order.to_dynamodb_item()
    })


def check_can_refund(order_id: str) -> Dict:
    """GET /api/orders/{id}/can-refund - проверяет возможность возврата"""
    try:
        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")
        
        order = Order.from_dynamodb_item(order_data)
        
        # Load event
        event_data = db.get_event(order.event_id)
        if not event_data:
            return error_response(404, "Event not found")
        
        event = Event.from_dynamodb_item(event_data)
        
        # Check refund eligibility
        hours_before = event.refund_policy.hours_before if event.refund_policy else 48
        can_refund, reason = order.can_refund(event.date, hours_before)
        
        # Calculate hours until event
        event_dt = datetime.fromisoformat(event.date.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours_until = (event_dt - now).total_seconds() / 3600
        
        return success_response({
            'can_refund': can_refund,
            'reason': reason,
            'hours_until_event': round(hours_until, 2),
            'hours_before_required': hours_before
        })
        
    except Exception as e:
        print(f"Error checking refund eligibility: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to check refund eligibility: {str(e)}")


def process_refund(order_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/orders/{id}/refund - обрабатывает возврат (placeholder)"""

    # SECURITY: Require admin authentication (financial protection)
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_refund_attempt', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")
        
        order = Order.from_dynamodb_item(order_data)
        
        # Load event
        event_data = db.get_event(order.event_id)
        if not event_data:
            return error_response(404, "Event not found")
        
        event_obj = Event.from_dynamodb_item(event_data)
        
        # Check refund eligibility
        hours_before = event_obj.refund_policy.hours_before if event_obj.refund_policy else 48
        can_refund, reason = order.can_refund(event_obj.date, hours_before)
        
        if not can_refund:
            return error_response(400, f"Cannot refund: {reason}")
        
        # TODO: Call All-Pay refund API here
        # For now, this is a placeholder that always succeeds
        print(f"PLACEHOLDER: Processing refund for order {order_id}")
        print(f"TODO: Integrate with All-Pay refund API")
        
        # Update order status to refunded
        from models import Refund
        refund = Refund(
            requested_at=datetime.utcnow().isoformat(),
            processed_at=datetime.utcnow().isoformat(),
            amount=order.total_amount,
            reason="customer_request"
        )
        
        order.payment.status = "refunded"
        order.payment.refund = refund
        
        # Restore tickets to event
        for ticket in order.tickets:
            event_obj.increase_available(ticket.type_id, ticket.quantity)
            print(f"Restored {ticket.quantity} tickets of type {ticket.type_id} for event {order.event_id}")
        
        # Save updated order and event
        db.put_order(order.to_dynamodb_item())
        db.put_event(event_obj.to_dynamodb_item())
        
        print(f"Refund processed successfully for order {order_id}")
        
        return success_response({
            'status': 'success',
            'message': 'Refund processed successfully',
            'refund_amount': order.total_amount,
            'currency': order.currency,
            'order_id': order_id,
            'note': 'This is a placeholder implementation. All-Pay integration pending.'
        })
        
    except Exception as e:
        print(f"Error processing refund: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to process refund: {str(e)}")


def verify_ticket(ticket_code: str) -> Dict:
    """GET /api/orders/verify/{ticket_code} - проверяет билет"""
    try:
        # Find order by ticket code
        order_data = db.get_order_by_ticket_code(ticket_code)
        if not order_data:
            return error_response(404, "Ticket not found")
        
        order = Order.from_dynamodb_item(order_data)
        
        # Find the specific QR code
        qr_code = None
        for qr in order.qr_codes:
            if qr.code == ticket_code:
                qr_code = qr
                break
        
        if not qr_code:
            return error_response(404, "Ticket code not found in order")
        
        # Validate ticket
        if order.payment.status != "completed":
            return error_response(400, "Ticket payment not completed")
        
        if order.payment.status == "refunded":
            return error_response(400, "Ticket has been refunded")
        
        if qr_code.scanned:
            return error_response(400, "Ticket already scanned", extra_data={
                'scanned_at': qr_code.scanned_at,
                'order_id': order.order_id
            })
        
        # Load event for details
        event_data = db.get_event(order.event_id)
        event = None
        if event_data:
            event = Event.from_dynamodb_item(event_data)
        
        # Mark ticket as scanned
        db.update_ticket_scanned_status(order.order_id, ticket_code, scanned=True)
        
        # Reload order to get updated scan status
        order_data = db.get_order(order.order_id)
        order = Order.from_dynamodb_item(order_data)
        
        # Find updated QR code
        for qr in order.qr_codes:
            if qr.code == ticket_code:
                qr_code = qr
                break
        
        return success_response({
            'valid': True,
            'ticket': {
                'code': ticket_code,
                'ticket_type': qr_code.ticket_type,
                'order_id': order.order_id,
                'scanned_at': qr_code.scanned_at,
                'event': {
                    'event_id': order.event_id,
                    'title': event.title if event else None,
                    'date': event.date if event else None
                } if event else None
            }
        })
        
    except Exception as e:
        print(f"Error verifying ticket: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to verify ticket: {str(e)}")


# ===== Coupons Handlers =====
def handle_coupons(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/coupons"""

    # GET /api/coupons - список купонов
    if method == 'GET' and path == '/api/coupons':
        query_params = event.get('queryStringParameters', {}) or {}
        status = query_params.get('status')
        return list_coupons(status, event)

    # GET /api/coupons/{code} - детали купона
    if method == 'GET' and path.startswith('/api/coupons/'):
        coupon_code = path.split('/')[-1]
        return get_coupon_details(coupon_code, event)

    # POST /api/coupons - создать купон (admin)
    if method == 'POST' and path == '/api/coupons':
        return create_coupon(event)

    # POST /api/coupons/validate - валидация купона
    if method == 'POST' and path == '/api/coupons/validate':
        return validate_coupon(event)

    # PUT /api/coupons/{code} - обновить купон (admin)
    if method == 'PUT' and path.startswith('/api/coupons/'):
        coupon_code = path.split('/')[-1]
        return update_coupon(coupon_code, event)

    # DELETE /api/coupons/{code} - удалить купон (admin)
    if method == 'DELETE' and path.startswith('/api/coupons/'):
        coupon_code = path.split('/')[-1]
        return delete_coupon_handler(coupon_code, event)

    return error_response(404, "Coupons endpoint not found")


def list_coupons(status: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - GET /api/coupons"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_coupons_list', {
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    items = db.list_coupons(status=status)

    coupons = []
    for item in items:
        try:
            coupon = Coupon.from_dynamodb_item(item)
            coupons.append(coupon.to_dict())
        except Exception as e:
            print(f"Error parsing coupon: {e}")
            continue

    return success_response({
        'coupons': coupons,
        'count': len(coupons)
    })


def get_coupon_details(coupon_code: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - GET /api/coupons/{code}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_coupon_details', {
            'coupon_code': coupon_code,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    item = db.get_coupon(coupon_code)

    if not item:
        return error_response(404, "Coupon not found")

    coupon = Coupon.from_dynamodb_item(item)

    return success_response({
        'coupon': coupon.to_dict()
    })


def create_coupon(request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/coupons"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_coupon_create', {
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация обязательных полей
        required = ['discount_type', 'discount_value', 'event_ids']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        # Генерируем код или используем предоставленный
        coupon_code = body.get('coupon_code', Coupon.generate_code())

        # Проверяем что купон с таким кодом не существует
        existing = db.get_coupon(coupon_code)
        if existing:
            return error_response(400, "Coupon with this code already exists")

        # Создаем купон
        coupon = Coupon(
            coupon_code=coupon_code,
            discount_type=body['discount_type'],
            discount_value=float(body['discount_value']),
            event_ids=body['event_ids'],
            valid_from=body.get('valid_from'),
            valid_until=body.get('valid_until'),
            status=body.get('status', 'active'),
            max_uses=body.get('max_uses'),
            description=body.get('description', '')
        )

        # Сохраняем в DynamoDB
        db.put_coupon(coupon.to_dynamodb_item())

        return success_response({
            'message': 'Coupon created successfully',
            'coupon_code': coupon_code,
            'coupon': coupon.to_dict()
        }, status_code=201)

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to create coupon: {str(e)}")


def validate_coupon(request_event: Dict) -> Dict:
    """POST /api/coupons/validate - Валидация купона для заказа"""
    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация
        required = ['coupon_code', 'event_id', 'amount']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        coupon_code = body['coupon_code']
        event_id = body['event_id']
        amount = float(body['amount'])
        ticket_quantity = int(body.get('ticket_quantity', 1))  # Optional, defaults to 1

        # Получаем купон
        item = db.get_coupon(coupon_code)
        if not item:
            return error_response(404, "Coupon not found")

        coupon = Coupon.from_dynamodb_item(item)

        # Валидируем
        is_valid, error_msg = coupon.is_valid(event_id)
        if not is_valid:
            return error_response(400, error_msg)

        # Рассчитываем скидку (с учетом количества билетов)
        discount_amount = coupon.calculate_discount(amount, ticket_quantity)
        final_amount = coupon.apply_discount(amount, ticket_quantity)

        return success_response({
            'valid': True,
            'coupon': coupon.to_dict(),
            'discount_amount': discount_amount,
            'final_amount': final_amount,
            'discount_description': coupon.get_discount_description()
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to validate coupon: {str(e)}")


def update_coupon(coupon_code: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - PUT /api/coupons/{code}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_coupon_update', {
            'coupon_code': coupon_code,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Проверяем что купон существует
        item = db.get_coupon(coupon_code)
        if not item:
            return error_response(404, "Coupon not found")

        body = json.loads(request_event.get('body', '{}'))

        # Получаем текущий купон
        coupon = Coupon.from_dynamodb_item(item)

        # Обновляем поля
        if 'discount_type' in body:
            coupon.discount_type = body['discount_type']
        if 'discount_value' in body:
            coupon.discount_value = float(body['discount_value'])
        if 'event_ids' in body:
            coupon.event_ids = body['event_ids']
        if 'valid_from' in body:
            coupon.valid_from = body['valid_from']
        if 'valid_until' in body:
            coupon.valid_until = body['valid_until']
        if 'status' in body:
            coupon.status = body['status']
        if 'max_uses' in body:
            coupon.max_uses = body['max_uses']
        if 'description' in body:
            coupon.description = body['description']

        coupon.updated_at = datetime.utcnow().isoformat()

        # Сохраняем
        db.put_coupon(coupon.to_dynamodb_item())

        return success_response({
            'message': 'Coupon updated successfully',
            'coupon_code': coupon_code,
            'coupon': coupon.to_dict()
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to update coupon: {str(e)}")


def delete_coupon_handler(coupon_code: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - DELETE /api/coupons/{code}"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_coupon_delete', {
            'coupon_code': coupon_code,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    item = db.get_coupon(coupon_code)
    if not item:
        return error_response(404, "Coupon not found")

    db.delete_coupon(coupon_code)

    return success_response({
        'message': 'Coupon deleted successfully',
        'coupon_code': coupon_code
    })


# ===== Image Upload Handler =====
def handle_image_upload(event: Dict) -> Dict:
    """ADMIN ONLY - Handles image upload to S3 bucket"""

    # SECURITY: Require admin authentication (S3 abuse prevention)
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_image_upload', {
            'ip': get_client_identifier(event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))

        filename = body.get('filename')
        content_type = body.get('contentType')
        base64_data = body.get('data')

        if not filename or not content_type or not base64_data:
            return error_response(400, 'Missing required fields: filename, contentType, data')

        # Decode base64 data
        image_data = base64.b64decode(base64_data)

        # Initialize S3 client
        s3_client = boto3.client('s3', region_name='eu-north-1')
        bucket_name = 'yallabalagan-ticket-media'

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=image_data,
            ContentType=content_type,
            CacheControl='max-age=31536000',  # 1 year cache
        )

        # Generate public URL
        url = f"https://{bucket_name}.s3.eu-north-1.amazonaws.com/{filename}"

        print(f"Image uploaded successfully: {url}")

        return success_response({
            'message': 'Image uploaded successfully',
            'url': url,
            'filename': filename
        })

    except Exception as e:
        print(f"Error uploading image: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to upload image: {str(e)}")


def handle_regenerate_site(event: Dict) -> Dict:
    """ADMIN ONLY - Регенерация публичного сайта через Lambda site-regenerator"""

    # SECURITY: Require admin authentication (Lambda abuse prevention)
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_site_regenerate', {
            'ip': get_client_identifier(event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        print("Invoking site-regenerator Lambda...")

        lambda_client = boto3.client('lambda')

        # Invoke site regenerator Lambda synchronously
        response = lambda_client.invoke(
            FunctionName='yallabalagan-site-regenerator',
            InvocationType='RequestResponse',  # Synchronous for immediate response
            Payload=json.dumps({})
        )

        # Parse response
        result_payload = json.loads(response['Payload'].read())

        print(f"Site regenerator response: {result_payload}")

        # Return the response from site-regenerator
        return {
            'statusCode': result_payload.get('statusCode', 200),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': result_payload.get('body', '{}')
        }

    except Exception as e:
        print(f"Error invoking site regenerator: {str(e)}")
        import traceback
        traceback.print_exc()

        return error_response(500, f"Failed to regenerate site: {str(e)}")


# ===== Helper Functions =====
def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Формирует успешный ответ"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # CORS
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(data, ensure_ascii=False, cls=DecimalEncoder)
    }


def error_response(status_code: int, message: str, extra_data: Dict = None) -> Dict:
    """Формирует ответ об ошибке"""
    body_data = {'error': message}
    if extra_data:
        body_data.update(extra_data)
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body_data, ensure_ascii=False, cls=DecimalEncoder)
    }


def handle_allpay_webhook(event: Dict) -> Dict:
    """
    POST /api/webhooks/allpay - handle webhook from All-Pay (or mock)

    Processes payment status updates from payment provider
    """
    try:
        # Extract body
        body = event.get('body', '')
        if event.get('isBase64Encoded'):
            body = base64.b64decode(body).decode('utf-8')

        print(f"Received webhook: {body}")

        # Get payment provider (respects PAYMENT_MODE)
        payment_provider = get_payment_provider()

        # AllPay puts signature in JSON body field 'sign'
        # Mock puts signature in header 'x-webhook-signature'
        headers = event.get('headers', {})
        mock_signature = headers.get('x-webhook-signature', '')

        # Parse body to check if it has 'sign' field
        try:
            body_json = json.loads(body)
            allpay_signature = body_json.get('sign', '')
        except:
            allpay_signature = ''

        # Use appropriate signature based on provider
        signature = allpay_signature if allpay_signature else mock_signature

        # Verify signature
        if not payment_provider.verify_webhook_signature(body.encode(), signature):
            print(f"Invalid webhook signature")
            return error_response(401, "Invalid signature")

        # Parse webhook payload
        try:
            webhook_data = parse_webhook_payload(body)
        except ValueError as e:
            print(f"Invalid webhook payload: {str(e)}")
            return error_response(400, str(e))

        order_id = webhook_data['order_id']
        payment_status = webhook_data['status']  # 'completed', 'failed', 'cancelled'
        transaction_id = webhook_data.get('transaction_id')

        print(f"Webhook received: order_id={order_id}, status={payment_status}, transaction_id={transaction_id}")

        # Validate order exists BEFORE processing
        order_data = db.get_order(order_id)
        if not order_data:
            print(f"ERROR: Order {order_id} not found")
            # Return 200 to prevent AllPay retries
            return success_response({
                'status': 'ignored',
                'message': f'Order {order_id} not found'
            })

        # Update order payment status
        db.update_order_payment_status(
            order_id=order_id,
            status=payment_status,
            transaction_id=transaction_id
        )

        # If payment completed, finalize the order
        if payment_status == 'completed':
            try:
                # Получаем заказ из БД
                order_data = db.get_order(order_id)
                if not order_data:
                    raise Exception(f"Order {order_id} not found")

                # Создаем Order объект
                order = Order.from_dynamodb_item(order_data)

                # Генерируем QR коды для билетов
                print(f"Generating QR codes for order {order_id}")
                order.generate_qr_codes()

                # Получаем событие и уменьшаем доступные билеты
                event_data = db.get_event(order.event_id)
                if event_data:
                    evt = Event.from_dynamodb_item(event_data)

                    # Уменьшаем количество доступных билетов
                    for ticket in order.tickets:
                        evt.decrease_available(ticket.type_id, ticket.quantity)
                        print(f"Decreased {ticket.quantity} tickets of type {ticket.type_id} for event {order.event_id}")

                    # Сохраняем обновленное событие
                    db.put_event(evt.to_dynamodb_item())

                # Increment coupon usage if coupon was used
                if order.coupon_code:
                    coupon_data = db.get_coupon(order.coupon_code)
                    if coupon_data:
                        coupon = Coupon.from_dynamodb_item(coupon_data)
                        coupon.increment_uses()
                        db.put_coupon(coupon.to_dynamodb_item())
                        print(f"Incremented coupon usage for {order.coupon_code}, now at {coupon.current_uses} uses")

                # Сохраняем обновленный заказ с QR кодами
                db.put_order(order.to_dynamodb_item())
                print(f"Order {order_id} finalized with QR codes and tickets decremented")

                # Trigger email Lambda asynchronously
                lambda_client = boto3.client('lambda')
                lambda_client.invoke(
                    FunctionName=os.environ.get('EMAIL_SENDER_LAMBDA', 'yallabalagan-email-sender'),
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps({
                        'order_id': order_id
                    })
                )
                print(f"Email Lambda triggered for order {order_id}")
            except Exception as e:
                # Don't fail webhook if processing fails - log it
                print(f"Failed to finalize order {order_id}: {str(e)}")
                import traceback
                traceback.print_exc()

        # Return success to payment provider
        return success_response({
            'status': 'success',
            'message': 'Webhook processed'
        })

    except Exception as e:
        print(f"Webhook processing error: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Webhook processing failed: {str(e)}")


# For local testing
if __name__ == '__main__':
    # Test event
    test_event = {
        'httpMethod': 'GET',
        'path': '/api/events',
        'body': None
    }

    response = lambda_handler(test_event, None)
    print(json.dumps(response, indent=2, ensure_ascii=False))
