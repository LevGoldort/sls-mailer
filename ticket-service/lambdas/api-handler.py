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

from models import Event, Location, Order, Customer, OrderTicket, TicketType, Coupon, Address, Coordinates, Parking, Media, Contact, SeatingMapConfig, VenueConfig
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
    # Safe logging: only method, path, and source IP (no headers/body)
    http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method'))
    path = event.get('path', event.get('rawPath', ''))
    source_ip = get_client_identifier(event)
    print(f"Request: {http_method} {path} from {source_ip}")

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
                'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
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

    # GET /api/events/{id}/purchased-seats - получить проданные места (admin)
    if method == 'GET' and path.endswith('/purchased-seats'):
        event_id = path.split('/')[-2]
        return get_purchased_seats(event_id, event)

    # GET /api/events/{id}/seating-map - получить карту мест
    if method == 'GET' and path.endswith('/seating-map'):
        event_id = path.split('/')[-2]
        return get_seating_map(event_id)

    # GET /api/events/{id}/seat-availability - получить доступность мест
    if method == 'GET' and path.endswith('/seat-availability'):
        event_id = path.split('/')[-2]
        return get_seat_availability(event_id)

    # POST /api/events/{id}/seat-allocation - сохранить распределение мест (admin)
    if method == 'POST' and path.endswith('/seat-allocation'):
        event_id = path.split('/')[-2]
        return save_seat_allocation(event_id, event)

    # POST /api/events/{id}/send-sms-blast - blast SMS to all buyers of event
    if method == 'POST' and path.endswith('/send-sms-blast'):
        event_id = path.split('/')[-2]
        return send_event_sms_blast(event_id, event)

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
                'currency': evt.currency,
                'seat_allocation': evt.seat_allocation  # Include for frontend seat picker
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


def get_purchased_seats(event_id: str, request_event: Dict = None) -> Dict:
    """
    ADMIN ONLY - GET /api/events/{event_id}/purchased-seats
    Returns all purchased seats for an event with their ticket types
    Used by admin editor to lock sold seats
    """
    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event) if request_event else None

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_purchased_seats_access', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Get all orders for this event
        orders = db.get_orders_by_event(event_id)

        purchased_seats = {}
        counts_by_type = {}

        for order in orders:
            payment_status = order.get('payment', {}).get('status', '')

            # Only include completed orders (pending orders use seat reservations with TTL)
            if payment_status != 'completed':
                continue

            for qr in order.get('qr_codes', []):
                if not qr.get('seat_id') or qr.get('cancelled', False):
                    continue

                seat_id = qr['seat_id']
                ticket_type_id = qr.get('ticket_type')

                purchased_seats[seat_id] = {
                    'ticket_type_id': ticket_type_id,
                    'order_id': order.get('order_id'),
                    'status': payment_status
                }

                counts_by_type[ticket_type_id] = counts_by_type.get(ticket_type_id, 0) + 1

        return success_response({
            'event_id': event_id,
            'purchased_seats': purchased_seats,
            'counts_by_type': counts_by_type
        })

    except Exception as e:
        print(f"Error getting purchased seats for event {event_id}")
        return error_response(500, str(e))


def get_seating_map(event_id: str) -> Dict:
    """
    GET /api/events/{event_id}/seating-map
    Returns the seating map configuration for the event's location
    """
    try:
        # Get event
        event_item = db.get_event(event_id)
        if not event_item:
            return error_response(404, "Event not found")

        evt = Event.from_dynamodb_item(event_item)

        # Get location
        location_item = db.get_location(evt.location_id)
        if not location_item:
            return error_response(404, "Location not found")

        location = Location.from_dynamodb_item(location_item)

        # Return seating map
        if location.venue_config.venue_type != 'seated':
            return success_response({
                'event_id': event_id,
                'venue_type': 'standing',
                'seating_map': None
            })

        seating_map = location.venue_config.seating_map.to_dict() if location.venue_config.seating_map else None

        return success_response({
            'event_id': event_id,
            'venue_type': 'seated',
            'seating_map': seating_map
        })

    except Exception as e:
        print(f"Error getting seating map for event {event_id}: {str(e)}")
        return error_response(500, str(e))


def get_seat_availability(event_id: str) -> Dict:
    """
    GET /api/events/{event_id}/seat-availability
    Returns seat allocation, purchased seats, and reserved seats for an event
    """
    try:
        # Get event
        event_item = db.get_event(event_id)
        if not event_item:
            return error_response(404, "Event not found")

        evt = Event.from_dynamodb_item(event_item)

        # Get purchased seats
        purchased_seats_data = get_purchased_seats_dict(event_id)
        purchased_seat_ids = list(purchased_seats_data.keys())

        # Get reserved seats (filter out expired reservations)
        import time
        current_time = int(time.time())

        reservations = db.get_seat_reservations(event_id)
        # Filter: only return reservations that haven't expired yet
        active_reservations = [r for r in reservations if r.get('expires_at', 0) > current_time]

        reserved_seats = [{'seat_id': r['seat_id'], 'session_id': r['session_id'], 'expires_at': r['expires_at']} for r in active_reservations]
        reserved_seat_ids = [r['seat_id'] for r in active_reservations]

        return success_response({
            'event_id': event_id,
            'seat_allocation': evt.seat_allocation or {},
            'purchased_seats': purchased_seat_ids,
            'reserved_seats': reserved_seat_ids,
            'reserved_seats_details': reserved_seats
        })

    except Exception as e:
        print(f"Error getting seat availability for event {event_id}: {str(e)}")
        return error_response(500, str(e))


def save_seat_allocation(event_id: str, request_event: Dict) -> Dict:
    """
    ADMIN ONLY - POST /api/events/{event_id}/seat-allocation
    Saves seat allocation for an event with validation against sold seats
    """
    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_seat_allocation_save', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        # Get event
        event_item = db.get_event(event_id)
        if not event_item:
            return error_response(404, "Event not found")

        evt = Event.from_dynamodb_item(event_item)

        # Parse body
        body_str = request_event.get('body') or '{}'
        body = json.loads(body_str)
        seat_allocation = body.get('seat_allocation', {})

        if not seat_allocation:
            return error_response(400, "seat_allocation is required")

        # Get locked (purchased) seats
        purchased_seats_data = get_purchased_seats_dict(event_id)

        # Validate that purchased seats haven't changed allocation
        if evt.seat_allocation:
            for seat_id, details in purchased_seats_data.items():
                old_type = evt.seat_allocation.get(seat_id)
                new_type = seat_allocation.get(seat_id)

                if old_type != new_type:
                    return error_response(400,
                        f"Cannot modify seat {seat_id} - already sold to ticket type {old_type}")

        # Count seats per ticket type
        allocation_counts = {}
        for seat_id, ticket_type_id in seat_allocation.items():
            allocation_counts[ticket_type_id] = allocation_counts.get(ticket_type_id, 0) + 1

        # Validate against ticket type totals
        for tt in evt.ticket_types:
            allocated = allocation_counts.get(tt.id, 0)
            if allocated > tt.total:
                return error_response(400,
                    f"Seat allocation exceeds total for ticket type '{tt.name}': allocated {allocated}, total {tt.total}")

        # Count already sold tickets per type (to preserve sold count)
        sold_counts = {}
        for tt in evt.ticket_types:
            sold_counts[tt.id] = tt.total - tt.available

        # Update ticket type availability based on seat allocation
        for tt in evt.ticket_types:
            allocated_seats = allocation_counts.get(tt.id, 0)
            already_sold = sold_counts.get(tt.id, 0)

            # Available = allocated seats - already sold
            tt.available = max(0, allocated_seats - already_sold)
            print(f"Updated ticket type '{tt.name}': allocated={allocated_seats}, sold={already_sold}, available={tt.available}")

        # Update event
        evt.seat_allocation = seat_allocation
        evt.updated_at = datetime.utcnow().isoformat()
        db.put_event(evt.to_dynamodb_item())

        return success_response({
            'message': 'Seat allocation saved successfully',
            'event_id': event_id,
            'seat_allocation': seat_allocation
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        print(f"Error saving seat allocation for event {event_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, str(e))


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

        # Валидация seat_allocation (опционально)
        seat_allocation = None
        if body.get('seat_allocation'):
            seat_allocation = body['seat_allocation']

            # Подсчитываем места для каждого типа билета
            allocation_counts = {}
            for seat_id, ticket_type_id in seat_allocation.items():
                allocation_counts[ticket_type_id] = allocation_counts.get(ticket_type_id, 0) + 1

            # Проверяем что количество не превышает total для каждого типа
            # И обновляем available на основе выделенных мест
            for tt in ticket_types:
                allocated = allocation_counts.get(tt.id, 0)
                if allocated > tt.total:
                    return error_response(400,
                        f"Seat allocation exceeds total for ticket type '{tt.name}': allocated {allocated}, total {tt.total}")

                # For seated events, available = allocated seats (not total)
                tt.available = allocated
                print(f"Set ticket type '{tt.name}' available={allocated} based on seat allocation")

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
            slug=slug_value,
            seat_allocation=seat_allocation
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


def get_purchased_seats_dict(event_id: str) -> Dict[str, Dict]:
    """
    Helper function: Returns {seat_id: {ticket_type_id, order_id, status}}
    for all purchased seats in an event.

    Использует ту же логику что и get_purchased_seats_set() - см. её docstring
    для объяснения почему qr_codes является источником правды.

    NOTE: Only returns COMPLETED purchases. Pending orders are handled via seat reservations.
    Cancelled tickets are excluded so their seats can be re-purchased.
    """
    orders = db.get_orders_by_event(event_id)
    purchased = {}

    for order in orders:
        # Only count seats as purchased if payment is completed
        if order.get('payment', {}).get('status') == 'completed':
            for qr in order.get('qr_codes', []):
                if qr.get('seat_id') and not qr.get('cancelled', False):
                    purchased[qr['seat_id']] = {
                        'ticket_type_id': qr.get('ticket_type'),
                        'order_id': order.get('order_id'),
                        'status': order.get('payment', {}).get('status')
                    }

    return purchased


def get_purchased_seats_set(event_id: str) -> set:
    """
    ЕДИНСТВЕННЫЙ ИСТОЧНИК ПРАВДЫ для проданных мест!

    Returns set of all purchased seat IDs for an event.

    ВАЖНО: Эта функция используется во ВСЕХ местах системы:
      - seat-availability (фронт видит какие места заняты)
      - reserve-seats (проверка при резервации)
      - create_order (проверка при создании заказа)
      - webhook (проверка при подтверждении оплаты)

    Источник данных: qr_codes[].seat_id (НЕ tickets[].purchased_seats!)

    Причина: При отмене билета (cancel ticket):
      - qr_codes[].cancelled = True (обновляется)
      - tickets[].purchased_seats (НЕ очищается)

    Поэтому qr_codes - единственный надёжный источник информации о том,
    какие билеты реально действительны.

    Условия для "занятого" места:
      1. payment.status == 'completed'
      2. qr_codes[].seat_id существует
      3. qr_codes[].cancelled == False
    """
    orders = db.get_orders_by_event(event_id)
    purchased = set()

    for order in orders:
        # Only count seats as purchased if payment is completed
        if order.get('payment', {}).get('status') == 'completed':
            for qr in order.get('qr_codes', []):
                if qr.get('seat_id') and not qr.get('cancelled', False):
                    purchased.add(qr['seat_id'])

    return purchased


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
            # NEW: Validate ticket type deletions - prevent deletion of types with sales
            new_type_ids = {tt['id'] for tt in body['ticket_types']}
            old_type_ids = {tt.id for tt in evt.ticket_types}
            deleted_type_ids = old_type_ids - new_type_ids

            if deleted_type_ids:
                # Check if deleted types have sales (only completed payments count)
                orders = db.get_orders_by_event(event_id)
                for order in orders:
                    if order.get('payment', {}).get('status') == 'completed':
                        for ticket in order.get('tickets', []):
                            if ticket['type_id'] in deleted_type_ids:
                                # Find ticket type name
                                tt = next((t for t in evt.ticket_types if t.id == ticket['type_id']), None)
                                type_name = tt.name if tt else ticket['type_id']
                                return error_response(400,
                                    f"Cannot delete ticket type '{type_name}' - it has sold tickets")

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

        # Валидация seat_allocation при обновлении
        if 'seat_allocation' in body:
            seat_allocation = body['seat_allocation']

            if seat_allocation:
                # NEW: Validate that purchased seats haven't changed allocation
                if evt.seat_allocation:  # Only validate if event already had seat allocation
                    purchased_seats_data = get_purchased_seats_dict(event_id)

                    for seat_id, details in purchased_seats_data.items():
                        old_type = evt.seat_allocation.get(seat_id)
                        new_type = seat_allocation.get(seat_id)

                        if old_type != new_type:
                            return error_response(400,
                                f"Cannot change allocation for seat {seat_id} - "
                                f"already sold to ticket type {old_type}")

                # Подсчитываем места для каждого типа билета
                allocation_counts = {}
                for seat_id, ticket_type_id in seat_allocation.items():
                    allocation_counts[ticket_type_id] = allocation_counts.get(ticket_type_id, 0) + 1

                # Проверяем против обновлённых типов билетов
                types_to_validate = evt.ticket_types

                for tt in types_to_validate:
                    allocated = allocation_counts.get(tt.id, 0)
                    if allocated > tt.total:
                        return error_response(400,
                            f"Seat allocation exceeds total for ticket type '{tt.name}': allocated {allocated}, total {tt.total}")

            evt.seat_allocation = seat_allocation

            # Recalculate available for each ticket type based on seat allocation
            # (same logic as save_seat_allocation)
            purchased_seats = get_purchased_seats_dict(event_id)
            sold_by_type = {}
            for seat_id, details in purchased_seats.items():
                tt_id = details.get('ticket_type_id')
                if tt_id:
                    sold_by_type[tt_id] = sold_by_type.get(tt_id, 0) + 1

            for tt in evt.ticket_types:
                allocated = allocation_counts.get(tt.id, 0)
                sold = sold_by_type.get(tt.id, 0)
                tt.available = max(0, allocated - sold)
                print(f"Recalculated '{tt.name}': allocated={allocated}, sold={sold}, available={tt.available}")

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

        # Парсим и валидируем venue_config
        venue_config_data = body.get('venue_config', {'venue_type': 'standing'})
        venue_type = venue_config_data.get('venue_type', 'standing')

        # Валидация venue_type
        if venue_type not in ['seated', 'standing']:
            return error_response(400, "venue_type must be 'seated' or 'standing'")

        seating_map = None
        if venue_type == 'seated':
            seating_map_data = venue_config_data.get('seating_map')
            if seating_map_data:
                # Валидация seating_map
                rows = seating_map_data.get('rows', 0)
                seats_per_row = seating_map_data.get('seats_per_row', 0)

                if rows < 1 or rows > 30:
                    return error_response(400, "seating_map.rows must be between 1 and 30")
                if seats_per_row < 1 or seats_per_row > 50:
                    return error_response(400, "seating_map.seats_per_row must be between 1 and 50")

                numbering_direction = seating_map_data.get('numbering_direction', 'left-to-right')
                if numbering_direction not in ['left-to-right', 'right-to-left']:
                    return error_response(400, "numbering_direction must be 'left-to-right' or 'right-to-left'")

                seating_map = SeatingMapConfig(
                    rows=rows,
                    seats_per_row=seats_per_row,
                    disabled_seats=seating_map_data.get('disabled_seats', []),
                    custom_numbers=seating_map_data.get('custom_numbers', {}),
                    numbering_direction=numbering_direction
                )

        venue_config = VenueConfig(
            venue_type=venue_type,
            seating_map=seating_map
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
            media=media,
            venue_config=venue_config
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

        # Обработка venue_config с проверкой immutability
        if 'venue_config' in body:
            venue_config_data = body['venue_config']
            new_venue_type = venue_config_data.get('venue_type')

            # IMMUTABILITY: Проверяем что venue_type не изменяется
            if new_venue_type and new_venue_type != loc.venue_config.venue_type:
                return error_response(400,
                    f"Cannot change venue_type from '{loc.venue_config.venue_type}' to '{new_venue_type}'. "
                    "Venue type is immutable after creation.")

            # Разрешаем обновление seating_map для seated venues
            if loc.venue_config.venue_type == 'seated' and 'seating_map' in venue_config_data:
                seating_map_data = venue_config_data['seating_map']

                # Валидация seating_map
                rows = seating_map_data.get('rows', 0)
                seats_per_row = seating_map_data.get('seats_per_row', 0)

                if rows < 1 or rows > 30:
                    return error_response(400, "seating_map.rows must be between 1 and 30")
                if seats_per_row < 1 or seats_per_row > 50:
                    return error_response(400, "seating_map.seats_per_row must be between 1 and 50")

                numbering_direction = seating_map_data.get('numbering_direction', 'left-to-right')
                if numbering_direction not in ['left-to-right', 'right-to-left']:
                    return error_response(400, "numbering_direction must be 'left-to-right' or 'right-to-left'")

                loc.venue_config.seating_map = SeatingMapConfig(
                    rows=rows,
                    seats_per_row=seats_per_row,
                    disabled_seats=seating_map_data.get('disabled_seats', []),
                    custom_numbers=seating_map_data.get('custom_numbers', {}),
                    numbering_direction=numbering_direction
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

    # POST /api/orders/reserve-seats - резервировать места
    if method == 'POST' and path == '/api/orders/reserve-seats':
        return reserve_seats(event)

    # POST /api/orders/release-seats - освободить резервации
    if method == 'POST' and path == '/api/orders/release-seats':
        return release_seats(event)

    # POST /api/orders/verify/{ticket_code} - проверить билет (admin only)
    if method == 'POST' and path.startswith('/api/orders/verify/'):
        ticket_code = path.split('/')[-1]
        return verify_ticket(ticket_code, event)

    # GET /api/orders/{id}/can-refund - проверить возможность возврата (admin)
    if method == 'GET' and path.endswith('/can-refund'):
        order_id = path.split('/')[-2]  # /api/orders/{id}/can-refund
        return check_can_refund(order_id, event)

    # POST /api/orders/{id}/cancel-tickets - partial ticket cancellation
    if method == 'POST' and path.endswith('/cancel-tickets'):
        order_id = path.split('/')[-2]
        return cancel_tickets(order_id, event)

    # POST /api/orders/{id}/resend-email - resend order confirmation email
    if method == 'POST' and path.endswith('/resend-email'):
        order_id = path.split('/')[-2]
        return resend_order_email(order_id, event)

    # POST /api/orders/{id}/resend-sms - resend SMS to individual order
    if method == 'POST' and path.endswith('/resend-sms'):
        order_id = path.split('/')[-2]
        return resend_order_sms(order_id, event)

    # POST /api/orders/{id}/refund - обработать возврат
    if method == 'POST' and path.endswith('/refund'):
        order_id = path.split('/')[-2]  # /api/orders/{id}/refund
        return process_refund(order_id, event)

    # PATCH /api/orders/{id}/customer - update customer info
    if method == 'PATCH' and path.endswith('/customer'):
        order_id = path.split('/')[-2]
        return update_order_customer(order_id, event)

    # GET /api/orders/{id}/ticket - public ticket view (no auth required)
    if method == 'GET' and path.endswith('/ticket'):
        order_id = path.split('/')[-2]
        return get_order_public_ticket(order_id)

    # GET /api/orders/{id} - детали заказа
    if method == 'GET' and path.startswith('/api/orders/'):
        order_id = path.split('/')[-1]
        return get_order(order_id, event)

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
        print(f"[DEBUG] get_orders_by_event({event_id}): {len(items)} items from DB")

        orders = []
        parse_errors = 0
        for item in items:
            try:
                order = Order.from_dynamodb_item(item)
                orders.append(order.to_dynamodb_item())
            except Exception as e:
                parse_errors += 1
                print(f"Error parsing order {item.get('order_id', 'unknown')}: {e}")
                continue

        print(f"[DEBUG] Parsed {len(orders)} orders, {parse_errors} errors")

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
        print(f"[DEBUG] list_orders: {len(items)} items from DB")

        orders = []
        parse_errors = 0
        for item in items:
            try:
                order = Order.from_dynamodb_item(item)
                orders.append(order.to_dynamodb_item())
            except Exception as e:
                parse_errors += 1
                print(f"Error parsing order {item.get('order_id', 'unknown')}: {e}")
                continue

        print(f"[DEBUG] Parsed {len(orders)} orders, {parse_errors} errors")

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

        # Проверяем что событие не прошло (event_date + 30 minutes >= now)
        from datetime import datetime, timedelta
        import pytz

        # Parse as naive datetime, then localize to Israel timezone
        naive_dt = datetime.fromisoformat(evt.date.replace('Z', ''))
        israel_tz = pytz.timezone('Asia/Jerusalem')
        event_dt = israel_tz.localize(naive_dt)
        event_end_time = event_dt + timedelta(minutes=30)  # Fixed: 30 minutes
        now = datetime.now(israel_tz)

        if event_end_time <= now:
            return error_response(400, "This event has already ended. Ticket sales are closed.")

        # Проверяем лимит билетов в одном заказе
        total_quantity = sum(t.get('quantity', 0) for t in body['tickets'])
        if total_quantity > 10:
            return error_response(400, "Maximum 10 tickets per order")

        # Проверяем доступность билетов
        order_tickets = []
        for ticket_req in body['tickets']:
            type_id = ticket_req['type_id']
            quantity = ticket_req['quantity']
            purchased_seats = ticket_req.get('purchased_seats')

            ticket_type = evt.get_ticket_type(type_id)
            if not ticket_type:
                return error_response(400, f"Invalid ticket type: {type_id}")

            if ticket_type.available < quantity:
                return error_response(400, f"Not enough tickets available for {ticket_type.name}")

            order_tickets.append(OrderTicket(
                type_id=type_id,
                type_name=ticket_type.name,
                quantity=quantity,
                price_per_ticket=ticket_type.price,
                purchased_seats=purchased_seats
            ))

        # NEW: Validate seat allocation for seated events
        if evt.seat_allocation:
            # This is a seated event - validate purchased_seats
            for ticket in order_tickets:
                if not ticket.purchased_seats:
                    return error_response(400,
                        "Seated events require 'purchased_seats' for all tickets")

                if len(ticket.purchased_seats) != ticket.quantity:
                    return error_response(400,
                        f"purchased_seats length ({len(ticket.purchased_seats)}) "
                        f"must match quantity ({ticket.quantity})")

                # Validate seats match ticket type in event allocation
                for seat_id in ticket.purchased_seats:
                    if seat_id not in evt.seat_allocation:
                        return error_response(400,
                            f"Seat {seat_id} does not exist in venue")

                    expected_type = evt.seat_allocation[seat_id]
                    if expected_type != ticket.type_id:
                        return error_response(400,
                            f"Seat {seat_id} is allocated to ticket type {expected_type}, "
                            f"not {ticket.type_id}")

            # Check for seat conflicts with existing orders AND active reservations
            existing_purchased = get_purchased_seats_set(event_id)
            import time as _time
            _current_time = int(_time.time())
            _reservations = db.get_seat_reservations(event_id)

            # Get session_id from request body - exclude this user's own reservations
            order_session_id = body.get('session_id')

            # Only consider reservations from OTHER sessions as conflicts
            _active_reserved = {
                r['seat_id'] for r in _reservations
                if r.get('expires_at', 0) > _current_time
                and r.get('session_id') != order_session_id
            }

            all_requested_seats = []
            for ticket in order_tickets:
                all_requested_seats.extend(ticket.purchased_seats or [])

            print(f"[ORDER] Seat check for event {event_id}: "
                  f"requested={all_requested_seats}, "
                  f"purchased={existing_purchased}, "
                  f"reserved_by_others={_active_reserved}, "
                  f"session_id={order_session_id}")

            for ticket in order_tickets:
                for seat_id in ticket.purchased_seats:
                    if seat_id in existing_purchased:
                        print(f"[ORDER] ❌ Seat {seat_id} already PURCHASED")
                        return error_response(400,
                            f"Seat {seat_id} is already purchased")
                    if seat_id in _active_reserved:
                        print(f"[ORDER] ❌ Seat {seat_id} already RESERVED by another session")
                        return error_response(400,
                            f"Seat {seat_id} is already reserved")

        # Calculate subtotal
        subtotal = sum(t.get_total() for t in order_tickets)

        # Process coupon if provided
        coupon_code = body.get('coupon_code')
        discount_amount = 0
        coupon = None

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
        total_amount = round(subtotal - discount_amount, 2)

        # Определяем является ли заказ бесплатным (100% скидка)
        is_free_order = (total_amount == 0)

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

        if is_free_order:
            # БЕСПЛАТНЫЙ ЗАКАЗ - финализируем сразу без платежного сервиса
            # Обновляем статус оплаты на 'completed'
            order.payment.status = 'completed'
            order.payment.paid_at = datetime.utcnow().isoformat()
            # allpay_transaction_id остается None для бесплатных заказов

            print(f"Processing free order {order.order_id} with 100% discount")

            try:
                # 1. Генерируем QR коды
                print(f"Generating QR codes for free order {order.order_id}")
                order.generate_qr_codes()

                # 2. Уменьшаем доступные билеты
                event_data = db.get_event(order.event_id)
                if event_data:
                    evt = Event.from_dynamodb_item(event_data)

                    for ticket in order.tickets:
                        success = evt.decrease_available(ticket.type_id, ticket.quantity)
                        if not success:
                            raise Exception(f"Not enough tickets available for {ticket.type_name}")
                        print(f"Decreased {ticket.quantity} tickets of type {ticket.type_id}")

                    # Сохраняем обновленное событие
                    db.put_event(evt.to_dynamodb_item())

                # 3. Инкрементируем использование промокода
                if order.coupon_code:
                    coupon_data = db.get_coupon(order.coupon_code)
                    if coupon_data:
                        coupon = Coupon.from_dynamodb_item(coupon_data)
                        coupon.increment_uses()
                        db.put_coupon(coupon.to_dynamodb_item())
                        print(f"Incremented coupon usage for {order.coupon_code}")

                # 4. Сохраняем завершенный заказ с QR кодами
                db.put_order(order.to_dynamodb_item())
                print(f"Free order {order.order_id} completed successfully")

                # 5. Триггерим email Lambda асинхронно
                lambda_client = boto3.client('lambda')
                lambda_client.invoke(
                    FunctionName=os.environ.get('EMAIL_SENDER_LAMBDA', 'yallabalagan-email-sender'),
                    InvocationType='Event',
                    Payload=json.dumps({'order_id': order.order_id})
                )
                print(f"Email Lambda triggered for free order {order.order_id}")

                # Trigger SMS Lambda asynchronously
                lambda_client.invoke(
                    FunctionName=os.environ.get('SMS_SENDER_LAMBDA', 'yallabalagan-sms-sender'),
                    InvocationType='Event',
                    Payload=json.dumps({'order_id': order.order_id})
                )
                print(f"SMS Lambda triggered for free order {order.order_id}")

                # Возвращаем успешный ответ БЕЗ payment_url
                return success_response({
                    'message': 'Free order completed successfully',
                    'order_id': order.order_id,
                    'order': order.to_dynamodb_item(),
                    'free_order': True  # Флаг для фронтенда
                }, status_code=201)

            except Exception as e:
                # При ошибке логируем и возвращаем ошибку
                print(f"Failed to process free order {order.order_id}: {str(e)}")
                import traceback
                traceback.print_exc()

                # Пытаемся удалить частично созданный заказ
                try:
                    db.delete_order(order.order_id)
                except:
                    pass

                return error_response(500, f"Failed to process free order: {str(e)}")

        else:
            # ПЛАТНЫЙ ЗАКАЗ - существующая логика
            # НЕ генерируем QR коды и НЕ уменьшаем билеты до успешной оплаты!
            # Это будет сделано в webhook handler при получении статуса 'completed'
            pass

        # Сохраняем заказ со статусом pending
        print(f"[DEBUG] About to save order {order.order_id} to DynamoDB")
        order_dynamodb_item = order.to_dynamodb_item()
        print(f"[DEBUG] Order DynamoDB item: PK={order_dynamodb_item.get('PK')}, SK={order_dynamodb_item.get('SK')}")
        db.put_order(order_dynamodb_item)
        print(f"[DEBUG] Order {order.order_id} saved successfully")

        # Verify the order was saved by reading it back
        print(f"[DEBUG] Verifying order {order.order_id} was saved...")
        saved_order = db.get_order(order.order_id)
        if saved_order:
            print(f"[DEBUG] ✓ Order {order.order_id} verified in DynamoDB")
        else:
            print(f"[ERROR] ✗ Order {order.order_id} NOT FOUND after save!")

        # Build human-readable seat labels for payment description
        seat_display_map = {}
        if evt.seat_allocation:
            seating_map = None
            try:
                loc_data = db.get_location(evt.location_id)
                if loc_data:
                    from models import Location
                    loc = Location.from_dynamodb_item(loc_data)
                    if loc.venue_config and loc.venue_config.seating_map:
                        seating_map = loc.venue_config.seating_map
            except Exception as e:
                print(f"[ORDER] Warning: Failed to load location {evt.location_id} for seat labels: {e}")

            if seating_map:
                for ticket in order_tickets:
                    for sid in (ticket.purchased_seats or []):
                        parts = sid.split('-')
                        if len(parts) == 2:
                            row_idx, seat_idx = int(parts[0]), int(parts[1])
                            row_d = row_idx + 1
                            seat_d = seat_idx + 1
                            custom = (seating_map.custom_numbers or {}).get(sid)
                            if custom:
                                seat_d = int(custom.get('seat', seat_d))
                                if custom.get('row') is not None:
                                    row_d = int(custom['row'])
                            elif getattr(seating_map, 'numbering_direction', None) == 'right-to-left':
                                seat_d = int(getattr(seating_map, 'seats_per_row', 20)) - seat_idx
                            seat_display_map[sid] = f"Ряд {row_d}, Место {seat_d}"
            else:
                print(f"[ORDER] No seating_map for location {evt.location_id}, skipping seat labels in payment")

        # Generate payment URL via payment provider
        payment_provider = get_payment_provider()
        try:
            payment_url = payment_provider.create_payment_url(
                order_id=order.order_id,
                amount=order.total_amount,
                currency=order.currency,
                email=order.customer.email,
                event_id=event_id,
                customer_name=order.customer.name,
                tickets=order_tickets,  # NEW: for API mode items array
                order_created_at=order.created_at,  # NEW: for expire calculation
                discount_type=coupon.discount_type if coupon and discount_amount > 0 else None,
                discount_value=coupon.discount_value if coupon and discount_amount > 0 else 0,
                event_title=evt.title,
                seat_display_map=seat_display_map
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


def reserve_seats(request_event: Dict) -> Dict:
    """
    POST /api/orders/reserve-seats
    Temporarily reserves seats for a customer session (10 minutes TTL)
    Uses optimistic locking to prevent race conditions
    """
    try:
        body = json.loads(request_event.get('body', '{}'))

        # Validate required fields
        required = ['event_id', 'seat_ids', 'session_id']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        event_id = body['event_id']
        seat_ids = body['seat_ids']
        session_id = body['session_id']

        if not isinstance(seat_ids, list) or len(seat_ids) == 0:
            return error_response(400, "seat_ids must be a non-empty array")

        if len(seat_ids) > 10:
            return error_response(400, "Maximum 10 tickets per order")

        # Get event
        event_item = db.get_event(event_id)
        if not event_item:
            return error_response(404, "Event not found")

        evt = Event.from_dynamodb_item(event_item)

        # Check that seats exist in allocation
        if evt.seat_allocation:
            for seat_id in seat_ids:
                if seat_id not in evt.seat_allocation:
                    return error_response(400, f"Seat {seat_id} does not exist in venue")

        # Check that seats are not already purchased
        purchased_seats = get_purchased_seats_set(event_id)
        for seat_id in seat_ids:
            if seat_id in purchased_seats:
                return error_response(400, f"Seat {seat_id} is already purchased")

        # Try to reserve seats with optimistic locking
        import time
        timestamp = int(time.time())
        ttl = timestamp + 600  # 10 minutes

        reserved_seats = []
        failed_seat = None

        for seat_id in seat_ids:
            success = db.reserve_seat(event_id, seat_id, session_id, ttl)
            if success:
                reserved_seats.append(seat_id)
            else:
                failed_seat = seat_id
                break

        # If any reservation failed, rollback all reservations
        if failed_seat:
            db.release_seats(event_id, reserved_seats, session_id)
            return error_response(409, f"Seat {failed_seat} is already reserved")

        return success_response({
            'message': 'Seats reserved successfully',
            'event_id': event_id,
            'seat_ids': seat_ids,
            'session_id': session_id,
            'reserved_until': ttl,
            'expires_in_seconds': 600
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to reserve seats: {str(e)}")


def release_seats(request_event: Dict) -> Dict:
    """
    POST /api/orders/release-seats
    Releases temporary seat reservations for a session
    """
    try:
        body = json.loads(request_event.get('body', '{}'))

        # Validate required fields
        required = ['event_id', 'seat_ids', 'session_id']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        event_id = body['event_id']
        seat_ids = body['seat_ids']
        session_id = body['session_id']

        if not isinstance(seat_ids, list):
            return error_response(400, "seat_ids must be an array")

        # Release seats
        released_count = db.release_seats(event_id, seat_ids, session_id)

        return success_response({
            'message': 'Seats released successfully',
            'event_id': event_id,
            'released_count': released_count,
            'total_requested': len(seat_ids)
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to release seats: {str(e)}")


def get_order(order_id: str, request_event: Dict = None) -> Dict:
    """GET /api/orders/{id}
    Two-tier access:
    - Admin API key: full access
    - Public: requires matching email query param
    """
    item = db.get_order(order_id)

    if not item:
        return error_response(404, "Order not found")

    order = Order.from_dynamodb_item(item)

    # Check admin auth first
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event) if request_event else None

    if not auth.verify_admin_key(api_key):
        # Public access: require email query param matching customer email
        query_params = (request_event or {}).get('queryStringParameters', {}) or {}
        email = query_params.get('email', '').strip().lower()

        if not email:
            return error_response(401, "Unauthorized: Admin key or email parameter required")

        customer_email = (order.customer.email or '').strip().lower()
        if email != customer_email:
            return error_response(403, "Forbidden: Email does not match order")

    return success_response({
        'order': order.to_dynamodb_item()
    })


def get_order_public_ticket(order_id: str) -> Dict:
    """GET /api/orders/{id}/ticket - public ticket view, no auth required"""
    item = db.get_order(order_id)
    if not item:
        return error_response(404, "Order not found")

    order = Order.from_dynamodb_item(item)

    if order.payment.status != 'completed':
        return error_response(403, "Tickets not available: payment not completed")

    # Load event
    event_data = db.get_event(order.event_id)
    if not event_data:
        return error_response(404, "Event not found")
    event = Event.from_dynamodb_item(event_data)

    # Load location
    location_name = ""
    seating_map_config = None
    try:
        location_data = db.get_location(event.location_id)
        if location_data:
            location = Location.from_dynamodb_item(location_data)
            location_name = location.name
            if location.venue_config and location.venue_config.seating_map:
                sm = location.venue_config.seating_map
                seating_map_config = {
                    'seats_per_row': int(sm.seats_per_row),
                    'disabled_seats': list(sm.disabled_seats or []),
                    'numbering_direction': sm.numbering_direction,
                    'custom_numbers': dict(sm.custom_numbers or {})
                }
    except Exception as e:
        print(f"Warning: Failed to load location: {e}")

    # Build ticket list (strip sensitive fields)
    tickets = [
        {
            'type_name': t.type_name,
            'quantity': int(t.quantity),
            'purchased_seats': list(t.purchased_seats or [])
        }
        for t in order.tickets
    ]

    qr_codes = [
        {
            'code': qr.code,
            's3_url': qr.s3_url,
            'seat_id': qr.seat_id,
            'cancelled': bool(getattr(qr, 'cancelled', False))
        }
        for qr in order.qr_codes
    ]

    customer_first_name = (order.customer.name or '').split()[0] if order.customer and order.customer.name else ''

    ticket_data = {
        'order_id': order.order_id,
        'event_title': event.title,
        'event_date': event.date,
        'location_name': location_name,
        'customer_first_name': customer_first_name,
        'tickets': tickets,
        'qr_codes': qr_codes
    }
    if seating_map_config:
        ticket_data['seating_map_config'] = seating_map_config

    return success_response({'ticket': ticket_data})


def check_can_refund(order_id: str, request_event: Dict = None) -> Dict:
    """ADMIN ONLY - GET /api/orders/{id}/can-refund - проверяет возможность возврата"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event) if request_event else None

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_refund_check', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
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


def cancel_tickets(order_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/orders/{id}/cancel-tickets - partial ticket cancellation"""

    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_cancel_tickets', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))
        qr_codes_to_cancel = body.get('qr_codes', [])
        reason = body.get('reason', '')

        if not qr_codes_to_cancel:
            return error_response(400, "qr_codes list is required")

        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")

        order = Order.from_dynamodb_item(order_data)

        if order.payment.status != 'completed':
            return error_response(400, "Can only cancel tickets on completed orders")

        # Load event for restoring availability
        event_data = db.get_event(order.event_id)
        if not event_data:
            return error_response(404, "Event not found")

        event_obj = Event.from_dynamodb_item(event_data)

        # Build lookup of QR codes in order
        qr_map = {qr.code: qr for qr in order.qr_codes}

        # Validate all requested codes
        cancelled_count = 0
        tickets_to_restore = {}  # type_id -> count

        for code in qr_codes_to_cancel:
            if code not in qr_map:
                return error_response(400, f"QR code {code} not found in this order")
            qr = qr_map[code]
            if qr.cancelled:
                return error_response(400, f"QR code {code} is already cancelled")
            if qr.scanned:
                return error_response(400, f"QR code {code} has already been scanned")

        # Cancel the tickets
        now = datetime.now(timezone.utc).isoformat()
        for code in qr_codes_to_cancel:
            qr = qr_map[code]
            qr.cancelled = True
            qr.cancelled_at = now
            cancelled_count += 1
            tickets_to_restore[qr.ticket_type] = tickets_to_restore.get(qr.ticket_type, 0) + 1

        # Restore availability on event
        for type_id, count in tickets_to_restore.items():
            event_obj.increase_available(type_id, count)

        # Save both
        db.put_order(order.to_dynamodb_item())
        db.put_event(event_obj.to_dynamodb_item())

        print(f"Cancelled {cancelled_count} tickets for order {order_id}: {qr_codes_to_cancel}. Reason: {reason}")

        # Send cancellation email
        try:
            lambda_client = boto3.client('lambda')
            lambda_client.invoke(
                FunctionName=os.environ.get('EMAIL_SENDER_LAMBDA', 'yallabalagan-email-sender'),
                InvocationType='Event',
                Payload=json.dumps({
                    'order_id': order_id,
                    'email_type': 'cancellation',
                    'cancelled_codes': qr_codes_to_cancel
                })
            )
            print(f"Cancellation email triggered for order {order_id}")
        except Exception as e:
            print(f"Warning: Failed to trigger cancellation email: {e}")

        return success_response({
            'status': 'success',
            'message': f'{cancelled_count} ticket(s) cancelled',
            'cancelled_codes': qr_codes_to_cancel,
            'order_id': order_id
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")
    except Exception as e:
        print(f"Error cancelling tickets: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to cancel tickets: {str(e)}")


def update_order_customer(order_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - PATCH /api/orders/{id}/customer - update customer info"""

    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_update_customer', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))

        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")

        order = Order.from_dynamodb_item(order_data)

        # Update customer fields if provided
        updated_fields = []
        if 'name' in body:
            order.customer.name = body['name'].strip()
            updated_fields.append('name')
        if 'email' in body:
            order.customer.email = body['email'].strip().lower()
            updated_fields.append('email')
        if 'phone' in body:
            order.customer.phone = body['phone'].strip()
            updated_fields.append('phone')

        if not updated_fields:
            return error_response(400, "No fields to update. Provide name, email, or phone.")

        order.updated_at = datetime.utcnow().isoformat()
        db.put_order(order.to_dynamodb_item())

        print(f"Updated customer info for order {order_id}: {updated_fields}")

        return success_response({
            'status': 'success',
            'message': f"Updated: {', '.join(updated_fields)}",
            'customer': {
                'name': order.customer.name,
                'email': order.customer.email,
                'phone': order.customer.phone
            }
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON in request body")
    except Exception as e:
        print(f"Error updating customer info: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to update customer: {str(e)}")


def resend_order_email(order_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/orders/{id}/resend-email - resend confirmation email"""

    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_resend_email', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))
        custom_message = body.get('custom_message', '')

        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")

        order = Order.from_dynamodb_item(order_data)

        if order.payment.status != 'completed':
            return error_response(400, "Can only resend email for completed orders")

        # Invoke email Lambda asynchronously
        lambda_client = boto3.client('lambda')
        payload = {
            'order_id': order_id,
            'force_resend': True,
            'custom_message': custom_message
        }
        lambda_client.invoke(
            FunctionName=os.environ.get('EMAIL_SENDER_LAMBDA', 'yallabalagan-email-sender'),
            InvocationType='Event',
            Payload=json.dumps(payload)
        )

        print(f"Email resend triggered for order {order_id}")

        return success_response({
            'status': 'success',
            'message': 'Email resend triggered',
            'order_id': order_id
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")
    except Exception as e:
        print(f"Error resending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to resend email: {str(e)}")


def resend_order_sms(order_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/orders/{id}/resend-sms - resend SMS to individual order"""

    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_resend_sms', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))
        custom_message = body.get('custom_message', '')

        order_data = db.get_order(order_id)
        if not order_data:
            return error_response(404, "Order not found")

        order = Order.from_dynamodb_item(order_data)

        if order.payment.status != 'completed':
            return error_response(400, "Can only resend SMS for completed orders")

        lambda_client = boto3.client('lambda')
        payload = {
            'order_id': order_id,
            'force_resend': True,
            'custom_message': custom_message
        }
        lambda_client.invoke(
            FunctionName=os.environ.get('SMS_SENDER_LAMBDA', 'yallabalagan-sms-sender'),
            InvocationType='Event',
            Payload=json.dumps(payload)
        )

        print(f"SMS resend triggered for order {order_id}")

        return success_response({
            'status': 'success',
            'message': 'SMS resend triggered',
            'order_id': order_id
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")
    except Exception as e:
        print(f"Error resending SMS: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to resend SMS: {str(e)}")


def send_event_sms_blast(event_id: str, request_event: Dict) -> Dict:
    """ADMIN ONLY - POST /api/events/{id}/send-sms-blast - blast SMS to all buyers of event"""

    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event)

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_sms_blast', {
            'event_id': event_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(401, "Unauthorized: Admin access required")

    try:
        body = json.loads(request_event.get('body', '{}'))
        custom_message = body.get('custom_message', '')
        include_ticket_info = body.get('include_ticket_info', True)

        # Load all completed orders for event
        order_items = db.get_orders_by_event(event_id)
        if not order_items:
            return success_response({'triggered': 0, 'event_id': event_id, 'message': 'No orders found'})

        lambda_client = boto3.client('lambda')
        triggered = 0

        for item in order_items:
            order = Order.from_dynamodb_item(item)
            if order.payment.status != 'completed':
                continue
            if not (order.customer and order.customer.phone):
                continue
            if order.qr_codes and all(getattr(qr, 'cancelled', False) for qr in order.qr_codes):
                continue

            payload = {
                'order_id': order.order_id,
                'force_resend': True,
                'custom_message': custom_message,
                'include_ticket_info': include_ticket_info
            }
            lambda_client.invoke(
                FunctionName=os.environ.get('SMS_SENDER_LAMBDA', 'yallabalagan-sms-sender'),
                InvocationType='Event',
                Payload=json.dumps(payload)
            )
            triggered += 1

        print(f"SMS blast triggered for event {event_id}: {triggered} SMS queued")

        return success_response({
            'triggered': triggered,
            'event_id': event_id,
            'message': f'SMS blast triggered for {triggered} orders'
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")
    except Exception as e:
        print(f"Error in SMS blast: {str(e)}")
        import traceback
        traceback.print_exc()
        return error_response(500, f"Failed to send SMS blast: {str(e)}")


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


def verify_ticket(ticket_code: str, request_event: Dict = None) -> Dict:
    """POST /api/orders/verify/{ticket_code} - проверяет билет (admin only)"""

    # SECURITY: Require admin authentication
    auth = get_admin_authenticator()
    api_key = auth.extract_api_key(request_event) if request_event else None

    if not auth.verify_admin_key(api_key):
        log_security_event('unauthorized_ticket_verify', {
            'ticket_code': ticket_code,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
        })
        return error_response(401, "Unauthorized: Admin access required")

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

        if qr_code.cancelled:
            return error_response(400, "Ticket has been cancelled")

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

        # SECURITY: Content-type whitelist
        allowed_content_types = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        if content_type not in allowed_content_types:
            return error_response(400, f'Invalid content type. Allowed: {", ".join(allowed_content_types)}')

        # Decode base64 data
        image_data = base64.b64decode(base64_data)

        # SECURITY: Size limit (5MB)
        max_size = 5 * 1024 * 1024  # 5MB
        if len(image_data) > max_size:
            return error_response(400, f'Image too large. Maximum size: 5MB')

        # SECURITY: Filename sanitization - strip path components, allow only safe chars, prefix with UUID
        import uuid
        # Extract just the filename (strip any path components)
        safe_name = os.path.basename(filename)
        # Remove any non-safe characters
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', safe_name)
        # Prefix with UUID to prevent collisions and path traversal
        safe_filename = f"{uuid.uuid4().hex[:8]}_{safe_name}"

        # Initialize S3 client
        s3_client = boto3.client('s3', region_name='eu-north-1')
        bucket_name = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')

        # Upload to S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=safe_filename,
            Body=image_data,
            ContentType=content_type,
            CacheControl='max-age=31536000',  # 1 year cache
        )

        # Generate public URL
        url = f"https://{bucket_name}.s3.eu-north-1.amazonaws.com/{safe_filename}"

        print(f"Image uploaded successfully: {url}")

        return success_response({
            'message': 'Image uploaded successfully',
            'url': url,
            'filename': safe_filename
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

        # Get environment to construct correct function name
        environment = os.environ.get('ENVIRONMENT', 'prod')
        if environment == 'prod':
            # Prod function has no suffix
            function_name = 'yallabalagan-site-regenerator'
        else:
            # Dev and other envs have suffix
            function_name = f'yallabalagan-site-regenerator-{environment}'

        # Invoke site regenerator Lambda synchronously
        response = lambda_client.invoke(
            FunctionName=function_name,
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
                'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
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
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
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
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
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

                # Получаем событие
                event_data = db.get_event(order.event_id)
                if not event_data:
                    raise Exception(f"Event {order.event_id} not found")

                evt = Event.from_dynamodb_item(event_data)

                # ✅ КРИТИЧЕСКАЯ ВАЛИДАЦИЯ для seated events
                # Проверяем доступность мест перед финализацией
                if evt.seat_allocation:
                    # Собираем все места из заказа
                    order_seats = set()
                    for ticket in order.tickets:
                        if ticket.purchased_seats:
                            order_seats.update(ticket.purchased_seats)

                    if order_seats:  # Если есть места в заказе
                        print(f"Validating seat availability for order {order_id}: seats {order_seats}")

                        # CRITICAL: Release seat reservations for this order's seats BEFORE conflict check
                        # Payment confirmed, so reservations are no longer needed
                        print(f"Releasing seat reservations for order {order_id}")
                        for seat_id in order_seats:
                            try:
                                db.release_seat(order.event_id, seat_id)
                                print(f"Released reservation for seat {seat_id}")
                            except Exception as e:
                                # Continue even if reservation doesn't exist or delete fails
                                print(f"Warning: Could not release reservation for seat {seat_id}: {str(e)}")

                        # ============================================================
                        # CRITICAL FIX: Используем qr_codes вместо tickets.purchased_seats
                        # ============================================================
                        #
                        # ПРОБЛЕМА (BUG-779f0330):
                        # Раньше тут использовался tickets[].purchased_seats для проверки
                        # проданных мест. Но когда билет отменяется (cancelled):
                        #   - qr_codes[].cancelled = True  (правильно обновляется)
                        #   - tickets[].purchased_seats    (НЕ очищается!)
                        #
                        # Это приводило к рассинхрону:
                        #   - seat-availability (использует qr_codes) → место свободно
                        #   - webhook (использовал tickets) → место занято → REFUND
                        #
                        # РЕШЕНИЕ:
                        # Используем get_purchased_seats_set() которая проверяет qr_codes
                        # с учётом cancelled флага. Это тот же источник данных что и
                        # seat-availability, поэтому не будет рассинхрона.
                        # ============================================================

                        # Получаем уже проданные места через единый источник правды (qr_codes)
                        # NOTE: get_purchased_seats_set проверяет:
                        #   1. payment.status == 'completed'
                        #   2. qr_codes[].seat_id exists
                        #   3. qr_codes[].cancelled == False (отменённые билеты не блокируют место)
                        existing_purchased = get_purchased_seats_set(order.event_id)

                        # Исключаем места текущего заказа (на случай если они уже есть в qr_codes)
                        # В норме на этом этапе qr_codes ещё не сгенерированы, но для defensive coding
                        existing_purchased = existing_purchased - order_seats

                        # ✅ ТАКЖЕ проверяем активные резервации (TTL не истек)
                        import time
                        current_time = int(time.time())
                        all_reservations = db.get_seat_reservations(order.event_id)
                        # Filter: only check reservations that haven't expired
                        active_reservations = [r for r in all_reservations if r.get('expires_at', 0) > current_time]
                        reserved_seats = {r['seat_id'] for r in active_reservations}

                        # Объединяем проданные и зарезервированные места
                        unavailable_seats = existing_purchased | reserved_seats

                        print(f"[WEBHOOK] Seat check for order {order_id}: "
                              f"order_seats={order_seats}, "
                              f"purchased_by_others={existing_purchased}, "
                              f"active_reservations={reserved_seats}, "
                              f"total_unavailable={unavailable_seats}")

                        # Проверяем конфликты
                        conflicts = order_seats & unavailable_seats
                        purchased_conflicts = order_seats & existing_purchased
                        reservation_conflicts = order_seats & reserved_seats
                        if conflicts:
                            print(f"❌ SEAT CONFLICT DETECTED: Order {order_id} "
                                  f"conflicts={conflicts}, "
                                  f"purchased_conflicts={purchased_conflicts}, "
                                  f"reservation_conflicts={reservation_conflicts}")

                            # Обновляем статус заказа на failed
                            db.update_order_payment_status(
                                order_id=order_id,
                                status='failed',
                                transaction_id=transaction_id
                            )

                            # Инициируем возврат средств
                            try:
                                refund_result = payment_provider.refund(
                                    order_id=order_id,
                                    amount=order.total_amount,
                                    transaction_id=transaction_id
                                )
                                print(f"Refund initiated: {refund_result}")
                            except Exception as refund_error:
                                print(f"ERROR: Failed to initiate refund: {str(refund_error)}")
                                # Продолжаем, чтобы отправить email пользователю

                            # TODO: Отправить email пользователю о проблеме и возврате средств
                            # send_seat_conflict_email(order, conflicts)

                            # Возвращаем успех в webhook (чтобы AllPay не повторял)
                            # но логируем критическую ошибку
                            print(f"⚠️ CRITICAL: Seats no longer available for order {order_id}. Refund processed.")

                            return success_response({
                                'status': 'failed_seat_conflict',
                                'message': f'Seats {list(conflicts)} are no longer available',
                                'refund_initiated': True,
                                'order_id': order_id
                            })

                        print(f"✅ Seat validation passed: all {len(order_seats)} seats are available")

                # Генерируем QR коды для билетов
                print(f"Generating QR codes for order {order_id}")
                order.generate_qr_codes()

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

                # Trigger SMS Lambda asynchronously
                lambda_client.invoke(
                    FunctionName=os.environ.get('SMS_SENDER_LAMBDA', 'yallabalagan-sms-sender'),
                    InvocationType='Event',
                    Payload=json.dumps({'order_id': order_id})
                )
                print(f"SMS Lambda triggered for order {order_id}")
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
