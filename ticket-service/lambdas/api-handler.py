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
import uuid
import hmac
from difflib import SequenceMatcher

# Add parent directory to path для импорта models и utils
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Event, Location, Order, Customer, OrderTicket, TicketType, Coupon, Address, Coordinates, Parking, Media, Contact, SeatingMapConfig, VenueConfig
from models.performer import Performer, SocialLinks
from models.product import Product
from models.show import Show, Episode, ShowLink
from models.merchandise_order import MerchandiseOrder, BuyerInfo
from models.influencer import Influencer
from utils.dynamodb import DynamoDBClient
from utils.payment import get_payment_provider, parse_webhook_payload
from utils.auth import get_admin_authenticator, is_scanner_or_admin, verify_scanner_token
from utils.auth_middleware import authenticate, AuthError
from utils.permissions import can_access_event, has_permission, is_admin, is_platform_admin
from datetime import datetime, timezone


def _owns_record(ctx: dict, record_item: dict) -> bool:
    """True if ctx's tenant owns this record, or if platform_admin (can edit anything)."""
    return record_item.get('tenant_id') == ctx.get('tenant_id') or is_platform_admin(ctx)


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
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature,X-Scanner-Token,X-Scanner-Event',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
            },
            'body': ''
        }

    # Routing
    try:
        if path == '/api/events/quick' and http_method == 'POST':
            return handle_quick_post(event)
        elif path == '/api/locations/quick' and http_method == 'POST':
            return handle_quick_location(event)
        elif path == '/api/url-preview' and http_method == 'POST':
            return handle_url_preview(event)
        elif path.startswith('/api/events'):
            return handle_events(event, http_method, path)
        elif path.startswith('/api/locations'):
            return handle_locations(event, http_method, path)
        elif path.startswith('/api/orders'):
            return handle_orders(event, http_method, path)
        elif path.startswith('/api/coupons'):
            return handle_coupons(event, http_method, path)
        elif path.startswith('/api/performers'):
            return handle_performers(event, http_method, path)
        elif path.startswith('/api/products'):
            return handle_products(event, http_method, path)
        elif path.startswith('/api/merchandise'):
            return handle_merchandise(event, http_method, path)
        elif path.startswith('/api/shows'):
            return handle_shows(event, http_method, path)
        elif path.startswith('/api/episodes'):
            return handle_episodes(event, http_method, path)
        elif path.startswith('/api/influencers'):
            return handle_influencers(event, http_method, path)
        elif path.startswith('/api/instagram'):
            return handle_instagram(event, http_method, path)
        elif path.startswith('/api/tiktok'):
            return handle_tiktok(event, http_method, path)
        elif path.startswith('/api/youtube'):
            return handle_youtube(event, http_method, path)
        elif path.startswith('/api/social'):
            return handle_social(event, http_method, path)
        elif path.startswith('/api/studio'):
            return handle_studio(event, http_method, path)
        elif path.startswith('/api/facebook'):
            return handle_facebook_ads(event, http_method, path)
        elif path == '/api/upload-image' and http_method == 'POST':
            return handle_image_upload(event)
        elif path == '/api/upload-image/quick' and http_method == 'POST':
            return handle_quick_image_upload(event)
        elif path == '/api/sharing/bulk' and http_method == 'POST':
            return handle_bulk_sharing(event)
        elif path == '/api/admin/regenerate-site' and http_method == 'POST':
            return handle_regenerate_site(event)
        elif path == '/api/webhooks/allpay' and http_method == 'POST':
            return handle_allpay_webhook(event)
        # ===== SCANNER ENDPOINTS =====
        elif http_method == 'GET' and path == '/api/scanner/search':
            return handle_scanner_search(event)
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
        return list_events(event)

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


def list_events(request_event: Dict = None) -> Dict:
    """GET /api/events"""
    ctx = None
    if request_event:
        try:
            ctx = authenticate(request_event)
        except AuthError:
            pass  # unauthenticated requests see all events (public endpoint)

    # Organizer sees only their own events; admins see their tenant's events
    if ctx and not has_permission(ctx, "events:write") and has_permission(ctx, "events:write_own"):
        items = db.list_events_by_owner(ctx['user_id'])
    elif ctx:
        items = db.list_events(tenant_id=ctx.get('tenant_id'))
    else:
        items = db.list_events()  # public endpoint — no tenant filter

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
                'seat_allocation': evt.seat_allocation,
                'event_type': item.get('event_type', 'internal'),
                'performer_ids': item.get('performer_ids', []),
                'external_url': item.get('external_url', ''),
                'tags': item.get('tags', []),
                'allow_auto_discounts': evt.allow_auto_discounts,
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

    event_dict = evt.to_dynamodb_item()
    event_dict['event_type'] = item.get('event_type', 'internal')
    event_dict['performer_ids'] = item.get('performer_ids', [])
    event_dict['external_url'] = item.get('external_url', '')

    return success_response({
        'event': event_dict
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
    """POST /api/events/{event_id}/seat-allocation — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_seat_allocation_save', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "events:write"):
        log_security_event('unauthorized_seat_allocation_save', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

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
    """POST /api/events — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_event_create', {'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "events:write") and not has_permission(ctx, "events:write_own"):
        log_security_event('unauthorized_event_create', {'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

    try:
        body = json.loads(request_event.get('body', '{}'))

        # Валидация обязательных полей
        required = ['title', 'description', 'date', 'location_id']
        for field in required:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        event_type = body.get('event_type', 'internal')
        if event_type == 'internal' and 'ticket_types' not in body:
            return error_response(400, "Missing required field: ticket_types")

        # Создаем типы билетов
        ticket_types = []
        for tt in body.get('ticket_types', []):
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
            seat_allocation=seat_allocation,
            owner_id=ctx.get('user_id'),
            allow_auto_discounts=bool(body.get('allow_auto_discounts', False)),
        )

        # Сохраняем в DynamoDB
        dynamo_item = evt.to_dynamodb_item()
        dynamo_item['event_type'] = event_type
        dynamo_item['performer_ids'] = body.get('performer_ids', [])
        if body.get('scanner_password'):
            dynamo_item['scanner_password'] = body['scanner_password']
        if event_type == 'external':
            dynamo_item['external_url'] = body.get('external_url', '')
        db.put_event(dynamo_item)

        return success_response({
            'message': 'Event created successfully',
            'event_id': event_id,
            'event': dynamo_item
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
    """PUT /api/events/{id} — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_event_update', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    item = db.get_event(event_id)
    if not item:
        return error_response(404, "Event not found")

    if not can_access_event(ctx, item, ctx.get('tenant_id', 'yallabalagan')):
        log_security_event('unauthorized_event_update', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

    try:

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

        # scanner_password не является полем модели Event — хранится как raw DynamoDB attribute

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

        if 'allow_auto_discounts' in body:
            evt.allow_auto_discounts = bool(body['allow_auto_discounts'])

        evt.updated_at = datetime.utcnow().isoformat()

        # Сохраняем — сохраняем extra-поля, которых нет в Event модели
        dynamo_item = evt.to_dynamodb_item()
        dynamo_item['event_type'] = body.get('event_type', item.get('event_type', 'internal'))
        dynamo_item['performer_ids'] = body.get('performer_ids', item.get('performer_ids', []))
        if dynamo_item['event_type'] == 'external':
            dynamo_item['external_url'] = body.get('external_url', item.get('external_url', ''))
        # scanner_password: use new value if provided, otherwise preserve existing
        scanner_pw = body.get('scanner_password') if 'scanner_password' in body else item.get('scanner_password')
        if scanner_pw:
            dynamo_item['scanner_password'] = scanner_pw
        db.put_event(dynamo_item)

        return success_response({
            'message': 'Event updated successfully',
            'event_id': event_id,
            'event': dynamo_item
        })

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    except Exception as e:
        return error_response(500, f"Failed to update event: {str(e)}")


def delete_event(event_id: str, request_event: Dict) -> Dict:
    """DELETE /api/events/{id} — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_event_delete', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    item = db.get_event(event_id)
    if not item:
        return error_response(404, "Event not found")

    if not can_access_event(ctx, item, ctx.get('tenant_id', 'yallabalagan')):
        log_security_event('unauthorized_event_delete', {'event_id': event_id, 'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

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
        return list_locations(event)

    # GET /api/locations/{id} - детали локации
    if method == 'GET' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return get_location(location_id)

    # POST /api/locations/quick - создать локацию без JWT (по секрету)
    if method == 'POST' and path == '/api/locations/quick':
        return handle_quick_location_create(event)

    # POST /api/locations - создать локацию (admin)
    if method == 'POST' and path == '/api/locations':
        return create_location(event)

    # PATCH /api/locations/{id}/sharing - управление шарингом (platform_admin)
    if method == 'PATCH' and path.endswith('/sharing'):
        location_id = path.split('/')[-2]
        return patch_location_sharing(location_id, event)

    # DELETE /api/locations/{id}/sharing - убрать себя из шаринга (любой тенант)
    if method == 'DELETE' and path.endswith('/sharing'):
        location_id = path.split('/')[-2]
        return delete_location_sharing(location_id, event)

    # PUT /api/locations/{id} - обновить локацию (admin)
    if method == 'PUT' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return update_location(location_id, event)

    # DELETE /api/locations/{id} - удалить локацию (admin)
    if method == 'DELETE' and path.startswith('/api/locations/'):
        location_id = path.split('/')[-1]
        return delete_location(location_id, event)

    return error_response(404, "Locations endpoint not found")


def list_locations(request_event: Dict) -> Dict:
    """GET /api/locations"""
    tenant_id = None
    try:
        ctx = authenticate(request_event)
        tenant_id = ctx.get("tenant_id")
    except AuthError:
        pass

    items = db.list_locations(tenant_id=tenant_id)

    locations = []
    for item in items:
        try:
            loc = Location.from_dynamodb_item(item)
            d = loc.to_dynamodb_item()
            if tenant_id and item.get('tenant_id') != tenant_id:
                d['_readonly'] = True
            locations.append(d)
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
    """POST /api/locations — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_location_create', {'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "locations:write"):
        log_security_event('unauthorized_location_create', {'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

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
            venue_config=venue_config,
            tenant_id=ctx.get('tenant_id', 'yallabalagan'),
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
    """PUT /api/locations/{id} — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_location_update', {'location_id': location_id, 'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "locations:write"):
        log_security_event('unauthorized_location_update', {'location_id': location_id, 'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

    try:
        item = db.get_location(location_id)
        if not item:
            return error_response(404, "Location not found")
        if not _owns_record(ctx, item):
            return error_response(403, "This record belongs to another tenant")

        body = json.loads(request_event.get('body', '{}'))

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
    """DELETE /api/locations/{id} — admin or content_manager"""

    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_location_delete', {'location_id': location_id, 'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "locations:write"):
        log_security_event('unauthorized_location_delete', {'location_id': location_id, 'ip': get_client_identifier(request_event)})
        return error_response(403, "Access denied")

    item = db.get_location(location_id)
    if not item:
        return error_response(404, "Location not found")
    if not _owns_record(ctx, item):
        return error_response(403, "This record belongs to another tenant")

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


def _token_tenant_id(token: str) -> str | None:
    """Extract tenant_id from a JWT access token; returns None for API keys."""
    if token and token.startswith('eyJ'):
        try:
            from utils.auth_jwt import decode_access_token
            return decode_access_token(token).get('tenant_id')
        except Exception:
            pass
    return None


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

    # Tenant isolation: verify this event belongs to the requester's tenant
    tenant_id = _token_tenant_id(api_key)
    if tenant_id:
        event_item = db.get_event(event_id)
        if not event_item or event_item.get('tenant_id') != tenant_id:
            return error_response(403, "Access denied")

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
        tenant_id = _token_tenant_id(api_key)
        if tenant_id:
            tenant_event_ids = {e.get('event_id') for e in db.list_events(tenant_id=tenant_id)}
            all_orders = db.list_orders()
            items = [o for o in all_orders if o.get('event_id') in tenant_event_ids]
        else:
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

        # Auto discount — only when no coupon applied
        if not coupon_code and evt.allow_auto_discounts:
            total_tickets = sum(t.quantity for t in order_tickets)
            if total_tickets >= 5:
                discount_amount = round(subtotal * 0.15, 2)
            elif total_tickets >= 3:
                discount_amount = round(subtotal * 0.10, 2)

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
                for qr in order.qr_codes:
                    db.put_ticket_lookup(qr.code, order.order_id)
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
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_refund_check', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
        })
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "orders:read"):
        log_security_event('unauthorized_refund_check', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
        })
        return error_response(403, "Access denied")

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

        # Reverse influencer commission if all tickets in the order are now cancelled
        all_cancelled = all(qr.cancelled for qr in order.qr_codes)
        if all_cancelled and order.coupon_code:
            try:
                coupon_data = db.get_coupon(order.coupon_code)
                if coupon_data:
                    coupon = Coupon.from_dynamodb_item(coupon_data)
                    if coupon.influencer_id:
                        commission_record = db.get_influencer_commission(coupon.influencer_id, order.order_id)
                        if commission_record:
                            sales = float(commission_record.get('subtotal', 0))
                            commission = float(commission_record.get('commission', 0))
                            db.delete_influencer_commission(coupon.influencer_id, order.order_id)
                            db.subtract_influencer_totals(coupon.influencer_id, sales, commission)
                            print(f"Reversed commission {commission} for influencer {coupon.influencer_id} on order {order_id}")
            except Exception as e:
                print(f"Warning: Failed to reverse influencer commission for order {order_id}: {e}")

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
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_refund_attempt', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "orders:write"):
        log_security_event('unauthorized_refund_attempt', {
            'order_id': order_id,
            'ip': get_client_identifier(request_event)
        })
        return error_response(403, "Access denied")

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
    """POST /api/orders/verify/{ticket_code} - проверяет билет (admin or scanner)"""

    if not is_scanner_or_admin(request_event):
        log_security_event('unauthorized_ticket_verify', {
            'ticket_code': ticket_code,
            'ip': get_client_identifier(request_event) if request_event else 'unknown'
        })
        return error_response(401, "Unauthorized")

    headers = {k.lower(): v for k, v in (request_event.get('headers') or {}).items()} if request_event else {}
    scanner_token = headers.get('x-scanner-token', '')
    scanner_event_id = headers.get('x-scanner-event', '')
    scanned_by_event = scanner_event_id if scanner_token else 'admin'

    try:
        # Find order by ticket code
        order_data = db.get_order_by_ticket_code(ticket_code)
        if not order_data:
            return error_response(404, "Ticket not found")

        order = Order.from_dynamodb_item(order_data)

        # Wrong-event check for scanner auth
        if scanner_token and scanner_event_id and order.event_id != scanner_event_id:
            return success_response({'valid': False, 'reason': 'wrong_event'})

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
            return success_response({'valid': False, 'reason': 'already_scanned', 'scanned_at': qr_code.scanned_at})

        # Load event for details
        event_data = db.get_event(order.event_id)
        event = None
        if event_data:
            event = Event.from_dynamodb_item(event_data)

        # Atomic conditional write — returns 'already_scanned' if concurrent device won
        scan_result = db.update_ticket_scanned_status(order.order_id, ticket_code, scanned=True, scanned_by_event=scanned_by_event)
        if scan_result == 'already_scanned':
            order_data = db.get_order(order.order_id)
            order = Order.from_dynamodb_item(order_data)
            for qr in order.qr_codes:
                if qr.code == ticket_code:
                    return success_response({'valid': False, 'reason': 'already_scanned', 'scanned_at': qr.scanned_at})
            return success_response({'valid': False, 'reason': 'already_scanned'})

        # Reload to get written values (scanned_at)
        order_data = db.get_order(order.order_id)
        order = Order.from_dynamodb_item(order_data)

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
                'customer_name': (order.customer.name if order.customer else None),
                'scanned_at': qr_code.scanned_at,
                'seat_id': getattr(qr_code, 'seat_id', None),
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
        # ?check=CODE — quick availability check for influencer registration
        check_code = query_params.get('check')
        if check_code:
            existing = db.get_coupon(check_code.strip().upper())
            return success_response({'available': existing is None})
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
    tenant_id = None
    try:
        ctx = authenticate(request_event)
        tenant_id = ctx.get("tenant_id")
    except AuthError:
        # Fall back to legacy API key check
        auth = get_admin_authenticator()
        api_key = auth.extract_api_key(request_event)
        if not auth.verify_admin_key(api_key):
            log_security_event('unauthorized_coupons_list', {
                'ip': get_client_identifier(request_event)
            })
            return error_response(401, "Unauthorized: Admin access required")

    items = db.list_coupons(status=status, tenant_id=tenant_id)

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
    tenant_id = 'yallabalagan'
    try:
        ctx = authenticate(request_event)
        tenant_id = ctx.get("tenant_id", "yallabalagan")
    except AuthError:
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

        # Нормализуем discount_type: 'percent' → 'percentage', 'fixed' → 'fixed_amount'
        _dtype = body['discount_type']
        if _dtype == 'percent':
            _dtype = 'percentage'
        elif _dtype == 'fixed':
            _dtype = 'fixed_amount'

        # Создаем купон
        coupon = Coupon(
            coupon_code=coupon_code,
            discount_type=_dtype,
            discount_value=float(body['discount_value']),
            event_ids=body['event_ids'],
            valid_from=body.get('valid_from'),
            valid_until=body.get('valid_until'),
            status=body.get('status', 'active'),
            max_uses=body.get('max_uses'),
            description=body.get('description', ''),
            tenant_id=tenant_id,
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
            _dtype = body['discount_type']
            if _dtype == 'percent':
                _dtype = 'percentage'
            elif _dtype == 'fixed':
                _dtype = 'fixed_amount'
            coupon.discount_type = _dtype
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

    try:
        ctx = authenticate(event)
    except AuthError as e:
        log_security_event('unauthorized_image_upload', {'ip': get_client_identifier(event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "media:upload"):
        log_security_event('unauthorized_image_upload', {'ip': get_client_identifier(event)})
        return error_response(403, "Access denied")

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


def handle_quick_image_upload(event: Dict) -> Dict:
    """Quick-post image upload — authenticated by shared secret, no admin JWT required"""
    try:
        body = json.loads(event.get('body', '{}'))
        if body.get('secret') != 'yallafriend':
            return error_response(401, 'Invalid secret')

        base64_data = body.get('data')
        content_type = body.get('contentType', 'image/jpeg')

        if not base64_data:
            return error_response(400, 'Missing data')
        if content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
            return error_response(400, 'Invalid content type')

        image_data = base64.b64decode(base64_data)
        if len(image_data) > 5 * 1024 * 1024:
            return error_response(400, 'Image too large (max 5MB)')

        import uuid
        s3_client = boto3.client('s3', region_name='eu-north-1')
        bucket_name = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')
        key = f"events/{uuid.uuid4().hex[:8]}_quick.jpg"

        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=image_data,
            ContentType='image/jpeg',
            CacheControl='max-age=31536000',
        )

        url = f"https://{bucket_name}.s3.eu-north-1.amazonaws.com/{key}"
        return success_response({'url': url})

    except Exception as e:
        print(f"Error in quick image upload: {str(e)}")
        return error_response(500, f"Failed to upload image: {str(e)}")


def _extract_maps_coords(url: str):
    """Extract lat/lng from a Google Maps URL. Follows short links. Returns dict or None."""
    def _parse(u):
        m = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', u)
        if m:
            return {'lat': float(m.group(1)), 'lng': float(m.group(2))}
        m = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', u)
        if m:
            return {'lat': float(m.group(1)), 'lng': float(m.group(2))}
        m = re.search(r'[?&]ll=(-?\d+\.\d+),(-?\d+\.\d+)', u)
        if m:
            return {'lat': float(m.group(1)), 'lng': float(m.group(2))}
        return None

    coords = _parse(url)
    if coords:
        return coords

    if 'goo.gl' in url or 'maps.app' in url:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                coords = _parse(resp.url)
                if coords:
                    return coords
        except Exception as e:
            print(f"Maps short link resolve failed: {e}")

    return None


# ===== Quick-Post Handler =====
def handle_quick_post(request_event: Dict) -> Dict:
    """POST /api/events/quick — no JWT; validates QUICK_POST_SECRET from env"""
    quick_secret = os.environ.get('QUICK_POST_SECRET', '')
    if not quick_secret:
        return error_response(503, "Quick-post not configured")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    provided_secret = body.get('secret', '')
    if not provided_secret or not hmac.compare_digest(provided_secret, quick_secret):
        log_security_event('unauthorized_quick_post', {'ip': get_client_identifier(request_event)})
        return error_response(401, "Invalid secret")

    required = ['title', 'date', 'external_url']
    for f in required:
        if not body.get(f):
            return error_response(400, f"Missing required field: {f}")

    slug_value = None
    if body.get('slug'):
        try:
            slug_value = validate_event_slug(body['slug'])
        except ValueError as exc:
            return error_response(400, str(exc))

    evt = Event(
        event_id=Event.generate_id(),
        title=body['title'],
        description=body.get('description', ''),
        date=body['date'],
        location_id=body.get('location_id') or 'unknown',
        ticket_types=[],
        images=body.get('images', []),
        slug=slug_value,
        event_type='external',
        external_url=body['external_url'],
        performer_ids=body.get('performer_ids', []),
        tenant_id='yallabalagan',
    )
    item = evt.to_dynamodb_item()
    maps_url = body.get('maps_url', '').strip() if body.get('maps_url') else ''
    if maps_url:
        item['maps_url'] = maps_url
        coords = _extract_maps_coords(maps_url)
        if coords:
            item['coordinates'] = coords
            print(f"Extracted coordinates {coords} from {maps_url}")
    db.put_event(item)

    try:
        lambda_client = boto3.client('lambda')
        lambda_client.invoke(
            FunctionName=os.environ.get('SITE_REGENERATOR_LAMBDA', 'yallabalagan-site-regenerator'),
            InvocationType='Event',
            Payload=json.dumps({'source': 'quick-post', 'event_id': evt.event_id}),
        )
    except Exception as e:
        print(f"Site regeneration trigger failed: {e}")

    return success_response({'event_id': evt.event_id, 'message': 'Event created'}, 201)


def handle_url_preview(request_event: Dict) -> Dict:
    """POST /api/url-preview — public, fetches OG tags and uploads image to S3"""
    import urllib.request
    import uuid
    from html.parser import HTMLParser

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    url = body.get('url', '').strip()
    if not url or not url.startswith(('http://', 'https://')):
        return error_response(400, "Valid URL required")

    class OGParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.og = {}

        def handle_starttag(self, tag, attrs):
            if tag == 'meta':
                d = dict(attrs)
                prop = d.get('property', '') or d.get('name', '')
                if prop in ('og:title', 'og:description', 'og:image') and 'content' in d:
                    self.og[prop] = d['content']

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(100_000).decode('utf-8', errors='ignore')
    except Exception as e:
        return error_response(502, f"Could not fetch URL: {e}")

    parser = OGParser()
    parser.feed(html)
    og = parser.og

    s3_image_url = ''
    og_image = og.get('og:image', '')
    if og_image and og_image.startswith(('http://', 'https://')):
        try:
            img_req = urllib.request.Request(og_image, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(img_req, timeout=5) as img_resp:
                ct = img_resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
                allowed_ct = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
                if ct not in allowed_ct:
                    ct = 'image/jpeg'
                image_data = img_resp.read(3 * 1024 * 1024)
            ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}.get(ct, 'jpg')
            key = f"og_{uuid.uuid4().hex[:8]}.{ext}"
            bucket = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')
            boto3.client('s3', region_name='eu-north-1').put_object(
                Bucket=bucket, Key=key, Body=image_data,
                ContentType=ct, CacheControl='max-age=31536000',
            )
            s3_image_url = f"https://{bucket}.s3.eu-north-1.amazonaws.com/{key}"
        except Exception as img_err:
            print(f"OG image upload failed: {img_err}")

    return success_response({
        'title':       og.get('og:title', ''),
        'description': og.get('og:description', ''),
        'image':       s3_image_url,
    })


def handle_quick_location(request_event: Dict) -> Dict:
    """POST /api/locations/quick — creates a minimal location, auth via QUICK_POST_SECRET"""
    quick_secret = os.environ.get('QUICK_POST_SECRET', '')
    if not quick_secret:
        return error_response(503, "Quick-post not configured")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    provided_secret = body.get('secret', '')
    if not provided_secret or not hmac.compare_digest(provided_secret, quick_secret):
        log_security_event('unauthorized_quick_location', {'ip': get_client_identifier(request_event)})
        return error_response(401, "Invalid secret")

    name = body.get('name', '').strip()
    city = body.get('city', '').strip()
    address_text = body.get('address', '').strip()
    maps_url = body.get('maps_url', '').strip() if body.get('maps_url') else ''
    if not name or not city or not address_text:
        return error_response(400, "name, city and address are required")

    coords = Coordinates(lat=0, lng=0)
    if maps_url:
        extracted = _extract_maps_coords(maps_url)
        if extracted:
            coords = Coordinates(lat=extracted['lat'], lng=extracted['lng'])

    slug = re.sub(r'[^\w-]', '', re.sub(r'[\s]+', '-', name.lower()))[:80]

    loc = Location(
        location_id=Location.generate_id(),
        name=name,
        slug=slug,
        address=Address(
            street=address_text,
            city=city,
            coordinates=coords,
        ),
        description='',
        short_description='',
        capacity=0,
    )
    db.put_location(loc.to_dynamodb_item())
    return success_response({'location': {'location_id': loc.location_id, 'name': loc.name}}, 201)


def handle_quick_location_create(event: Dict) -> Dict:
    """POST /api/locations/quick — authenticated by shared secret, no JWT required"""
    try:
        body = json.loads(event.get('body', '{}'))
        if body.get('secret') != 'yallafriend':
            return error_response(401, 'Invalid secret')

        name = body.get('name', '').strip()
        city = body.get('city', '').strip()
        address_str = body.get('address', '').strip()

        if not name or not city or not address_str:
            return error_response(400, 'Missing required fields: name, city, address')

        lat = float(body.get('lat', 0) or 0)
        lng = float(body.get('lng', 0) or 0)

        location_id = Location.generate_id()
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + '-' + location_id[:6]

        loc = Location(
            location_id=location_id,
            name=name,
            slug=slug,
            address=Address(
                street=address_str,
                city=city,
                coordinates=Coordinates(lat=lat, lng=lng),
            ),
            description='',
            short_description='',
            capacity=0,
        )

        db.put_location(loc.to_dynamodb_item())
        return success_response({'location': {'location_id': location_id, 'name': name}}, status_code=201)

    except Exception as e:
        print(f"Error in quick location create: {str(e)}")
        return error_response(500, f"Failed to create location: {str(e)}")


def _patch_sharing(get_fn, update_fn, id_field: str, entity_id: str, request_event: Dict) -> Dict:
    """Shared implementation for PATCH /api/{entity}/{id}/sharing."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_platform_admin(ctx):
        return error_response(403, "Only platform_admin can manage sharing")
    if not get_fn(entity_id):
        return error_response(404, "Not found")
    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")
    allowed_tenants = body.get('allowed_tenants', [])
    if not isinstance(allowed_tenants, list):
        return error_response(400, "allowed_tenants must be a list of tenant IDs")
    update_fn(entity_id, allowed_tenants)
    return success_response({id_field: entity_id, 'allowed_tenants': allowed_tenants})


def patch_location_sharing(location_id: str, request_event: Dict) -> Dict:
    return _patch_sharing(db.get_location, db.update_location_sharing, 'location_id', location_id, request_event)


def patch_performer_sharing(performer_id: str, request_event: Dict) -> Dict:
    return _patch_sharing(db.get_performer, db.update_performer_sharing, 'performer_id', performer_id, request_event)


def patch_show_sharing(show_id: str, request_event: Dict) -> Dict:
    return _patch_sharing(db.get_show, db.update_show_sharing, 'show_id', show_id, request_event)


def _delete_sharing(get_fn, update_fn, id_field: str, entity_id: str, request_event: Dict) -> Dict:
    """DELETE /api/{entity}/{id}/sharing — self-service: removes calling tenant from allowed_tenants."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    item = get_fn(entity_id)
    if not item:
        return error_response(404, "Not found")
    tenant_id = ctx.get('tenant_id')
    current = item.get('allowed_tenants', [])
    updated = [t for t in current if t != tenant_id]
    update_fn(entity_id, updated)
    return success_response({id_field: entity_id, 'allowed_tenants': updated})


def delete_location_sharing(location_id: str, request_event: Dict) -> Dict:
    return _delete_sharing(db.get_location, db.update_location_sharing, 'location_id', location_id, request_event)


def delete_performer_sharing(performer_id: str, request_event: Dict) -> Dict:
    return _delete_sharing(db.get_performer, db.update_performer_sharing, 'performer_id', performer_id, request_event)


def delete_show_sharing(show_id: str, request_event: Dict) -> Dict:
    return _delete_sharing(db.get_show, db.update_show_sharing, 'show_id', show_id, request_event)


def handle_bulk_sharing(request_event: Dict) -> Dict:
    """POST /api/sharing/bulk — platform_admin sets allowed_tenants on many records at once."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_platform_admin(ctx):
        return error_response(403, "Only platform_admin can manage sharing")
    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")

    entity_type = body.get('entity_type')
    entity_ids = body.get('entity_ids')   # list or null (= all owned by ctx tenant)
    allowed_tenants = body.get('allowed_tenants', [])

    if entity_type not in ('location', 'performer', 'show'):
        return error_response(400, "entity_type must be location, performer, or show")
    if not isinstance(allowed_tenants, list):
        return error_response(400, "allowed_tenants must be a list")

    tenant_id = ctx.get('tenant_id')
    if entity_ids is None:
        if entity_type == 'location':
            items = db.list_locations(tenant_id=tenant_id)
            entity_ids = [i.get('location_id') for i in items if i.get('location_id')]
        elif entity_type == 'performer':
            items = db.list_performers(tenant_id=tenant_id)
            entity_ids = [i.get('performer_id') for i in items if i.get('performer_id')]
        else:
            items = db.list_shows(tenant_id=tenant_id)
            entity_ids = [i.get('show_id') for i in items if i.get('show_id')]

    update_fn = {
        'location': db.update_location_sharing,
        'performer': db.update_performer_sharing,
        'show': db.update_show_sharing,
    }[entity_type]

    for eid in entity_ids:
        update_fn(eid, allowed_tenants)

    return success_response({'updated': len(entity_ids), 'allowed_tenants': allowed_tenants})


def handle_regenerate_site(event: Dict) -> Dict:
    """ADMIN ONLY - Регенерация публичного сайта через Lambda site-regenerator"""

    try:
        ctx = authenticate(event)
    except AuthError as e:
        log_security_event('unauthorized_site_regenerate', {'ip': get_client_identifier(event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "site:regenerate"):
        log_security_event('unauthorized_site_regenerate', {'ip': get_client_identifier(event)})
        return error_response(403, "Access denied")

    try:
        print("Invoking site-regenerator Lambda...")

        lambda_client = boto3.client('lambda')

        function_name = 'yallabalagan-site-regenerator'

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


# ===== Performers Handlers =====
def handle_performers(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/performers"""

    if method == 'GET' and path == '/api/performers':
        return list_performers(event)

    if method == 'GET' and path.startswith('/api/performers/slug/'):
        slug = path.split('/')[-1]
        return get_performer_by_slug(slug)

    if method == 'POST' and path == '/api/performers':
        return create_performer(event)

    if method == 'GET' and path.startswith('/api/performers/'):
        performer_id = path.split('/')[-1]
        return get_performer(performer_id)

    if method == 'PUT' and path.startswith('/api/performers/'):
        performer_id = path.split('/')[-1]
        return update_performer(performer_id, event)

    if method == 'PATCH' and path.endswith('/sharing'):
        performer_id = path.split('/')[-2]
        return patch_performer_sharing(performer_id, event)

    if method == 'DELETE' and path.endswith('/sharing'):
        performer_id = path.split('/')[-2]
        return delete_performer_sharing(performer_id, event)

    if method == 'DELETE' and path.startswith('/api/performers/'):
        performer_id = path.split('/')[-1]
        return delete_performer(performer_id, event)

    return error_response(404, "Performers endpoint not found")


def list_performers(request_event: Dict = None) -> Dict:
    """GET /api/performers — public"""
    tenant_id = 'yallabalagan'
    if request_event:
        try:
            ctx = authenticate(request_event)
            tenant_id = ctx.get('tenant_id', 'yallabalagan')
        except AuthError:
            pass
    items = db.list_performers(tenant_id=tenant_id, status='active')
    performers = []
    for item in items:
        try:
            p = Performer.from_dynamodb_item(item)
            d = p.to_dynamodb_item()
            if item.get('tenant_id') != tenant_id:
                d['_readonly'] = True
            performers.append(d)
        except Exception as e:
            print(f"Error parsing performer: {e}")
    return success_response({'performers': performers, 'count': len(performers)})


def get_performer(performer_id: str) -> Dict:
    """GET /api/performers/{id} — public"""
    item = db.get_performer(performer_id)
    if not item:
        return error_response(404, "Performer not found")
    return success_response({'performer': Performer.from_dynamodb_item(item).to_dynamodb_item()})


def get_performer_by_slug(slug: str) -> Dict:
    """GET /api/performers/slug/{slug} — public"""
    item = db.get_performer_by_slug(slug)
    if not item:
        return error_response(404, "Performer not found")
    return success_response({'performer': Performer.from_dynamodb_item(item).to_dynamodb_item()})


def create_performer(request_event: Dict) -> Dict:
    """POST /api/performers — admin or content_manager"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_performer_create', {'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "performers:write"):
        return error_response(403, "Access denied")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    required = ['name', 'slug', 'bio', 'role']
    for f in required:
        if not body.get(f):
            return error_response(400, f"Missing required field: {f}")

    slug = normalize_slug(body['slug'])
    if not slug:
        return error_response(400, "Invalid slug")
    if db.get_performer_by_slug(slug):
        return error_response(409, "Slug already in use")

    social_data = body.get('social', {})
    performer = Performer(
        performer_id=Performer.generate_id(),
        tenant_id=ctx.get('tenant_id', 'yallabalagan'),
        name=body['name'],
        slug=slug,
        bio=body['bio'],
        role=body['role'],
        tagline=body.get('tagline'),
        photo_url=body.get('photo_url'),
        photos=body.get('photos', []),
        youtube_embed=body.get('youtube_embed'),
        social=SocialLinks.from_dict(social_data),
        contact_email=body.get('contact_email'),
        contact_phone=body.get('contact_phone'),
        status=body.get('status', 'active'),
    )
    db.put_performer(performer.to_dynamodb_item())
    return success_response({'performer': performer.to_dynamodb_item()}, 201)


def update_performer(performer_id: str, request_event: Dict) -> Dict:
    """PUT /api/performers/{id} — admin or content_manager"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "performers:write"):
        return error_response(403, "Access denied")

    item = db.get_performer(performer_id)
    if not item:
        return error_response(404, "Performer not found")
    if not _owns_record(ctx, item):
        return error_response(403, "This record belongs to another tenant")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    performer = Performer.from_dynamodb_item(item)

    if 'name' in body:
        performer.name = body['name']
    if 'slug' in body:
        new_slug = normalize_slug(body['slug'])
        if not new_slug:
            return error_response(400, "Invalid slug")
        existing = db.get_performer_by_slug(new_slug)
        if existing and existing.get('performer_id') != performer_id:
            return error_response(409, "Slug already in use")
        performer.slug = new_slug
    if 'bio' in body:
        performer.bio = body['bio']
    if 'role' in body:
        performer.role = body['role']
    if 'tagline' in body:
        performer.tagline = body['tagline']
    if 'photo_url' in body:
        performer.photo_url = body['photo_url']
    if 'photos' in body:
        performer.photos = body['photos']
    if 'youtube_embed' in body:
        performer.youtube_embed = body['youtube_embed']
    if 'social' in body:
        performer.social = SocialLinks.from_dict(body['social'])
    if 'contact_email' in body:
        performer.contact_email = body['contact_email']
    if 'contact_phone' in body:
        performer.contact_phone = body['contact_phone']
    if 'status' in body:
        performer.status = body['status']

    performer.updated_at = datetime.utcnow().isoformat()
    db.put_performer(performer.to_dynamodb_item())
    return success_response({'performer': performer.to_dynamodb_item()})


def delete_performer(performer_id: str, request_event: Dict) -> Dict:
    """DELETE /api/performers/{id} — admin or content_manager (soft delete: set status=inactive)"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "performers:write"):
        return error_response(403, "Access denied")

    item = db.get_performer(performer_id)
    if not item:
        return error_response(404, "Performer not found")
    if not _owns_record(ctx, item):
        return error_response(403, "This record belongs to another tenant")

    performer = Performer.from_dynamodb_item(item)
    performer.status = 'inactive'
    performer.updated_at = datetime.utcnow().isoformat()
    db.put_performer(performer.to_dynamodb_item())
    return success_response({'message': 'Performer deactivated', 'performer_id': performer_id})


# ===== Products Handlers =====
def handle_products(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/products"""

    if method == 'GET' and path.startswith('/api/products/slug/'):
        slug = path.split('/')[-1]
        return get_product_by_slug(slug)

    if method == 'GET' and path == '/api/products':
        return list_products(event)

    if method == 'POST' and path == '/api/products':
        return create_product(event)

    if method == 'GET' and path.startswith('/api/products/'):
        product_id = path.split('/')[-1]
        return get_product(product_id)

    if method == 'PUT' and path.startswith('/api/products/'):
        product_id = path.split('/')[-1]
        return update_product(product_id, event)

    if method == 'DELETE' and path.startswith('/api/products/'):
        product_id = path.split('/')[-1]
        return delete_product(product_id, event)

    return error_response(404, "Products endpoint not found")


def list_products(request_event: Dict) -> Dict:
    """GET /api/products — public (active). Supports ?performer_id={id}"""
    tenant_id = None
    try:
        ctx = authenticate(request_event)
        tenant_id = ctx.get('tenant_id')
    except AuthError:
        pass

    params = request_event.get('queryStringParameters') or {}
    performer_id = params.get('performer_id')

    if performer_id:
        items = db.list_products_by_performer(performer_id)
        items = [i for i in items if i.get('status') == 'active']
        if tenant_id:
            items = [i for i in items if i.get('tenant_id') == tenant_id]
    else:
        items = db.list_products(tenant_id=tenant_id)

    products = []
    for item in items:
        try:
            products.append(Product.from_dynamodb_item(item).to_dynamodb_item())
        except Exception as e:
            print(f"Error parsing product: {e}")
    return success_response({'products': products, 'count': len(products)})


def get_product(product_id: str) -> Dict:
    """GET /api/products/{id} — public"""
    item = db.get_product(product_id)
    if not item:
        return error_response(404, "Product not found")
    return success_response({'product': Product.from_dynamodb_item(item).to_dynamodb_item()})


def get_product_by_slug(slug: str) -> Dict:
    """GET /api/products/slug/{slug} — public"""
    item = db.get_product_by_slug(slug)
    if not item:
        return error_response(404, "Product not found")
    return success_response({'product': Product.from_dynamodb_item(item).to_dynamodb_item()})


def create_product(request_event: Dict) -> Dict:
    """POST /api/products — admin or content_manager"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        log_security_event('unauthorized_product_create', {'ip': get_client_identifier(request_event)})
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "products:write"):
        return error_response(403, "Access denied")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    required = ['performer_id', 'name', 'slug', 'short_description', 'price_ils']
    for f in required:
        if not body.get(f) and body.get(f) != 0:
            return error_response(400, f"Missing required field: {f}")

    slug = normalize_slug(body['slug'])
    if not slug:
        return error_response(400, "Invalid slug")
    if db.get_product_by_slug(slug):
        return error_response(409, "Slug already in use")

    if not db.get_performer(body['performer_id']):
        return error_response(404, "Performer not found")

    product = Product(
        product_id=Product.generate_id(),
        tenant_id=ctx.get('tenant_id', 'yallabalagan'),
        performer_id=body['performer_id'],
        name=body['name'],
        slug=slug,
        short_description=body['short_description'],
        full_description=body.get('full_description', ''),
        what_you_get=body.get('what_you_get', ''),
        price_ils=float(body['price_ils']),
        photo_url=body.get('photo_url'),
        gallery_urls=body.get('gallery_urls', []),
        total_slots=body.get('total_slots'),
        status=body.get('status', 'active'),
        product_type=body.get('product_type', 'personal'),
        group_size=body.get('group_size'),
    )
    db.put_product(product.to_dynamodb_item())
    return success_response({'product': product.to_dynamodb_item()}, 201)


def update_product(product_id: str, request_event: Dict) -> Dict:
    """PUT /api/products/{id} — admin or content_manager"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "products:write"):
        return error_response(403, "Access denied")

    item = db.get_product(product_id)
    if not item:
        return error_response(404, "Product not found")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    product = Product.from_dynamodb_item(item)

    if 'name' in body:
        product.name = body['name']
    if 'slug' in body:
        new_slug = normalize_slug(body['slug'])
        if not new_slug:
            return error_response(400, "Invalid slug")
        existing = db.get_product_by_slug(new_slug)
        if existing and existing.get('product_id') != product_id:
            return error_response(409, "Slug already in use")
        product.slug = new_slug
    if 'short_description' in body:
        product.short_description = body['short_description']
    if 'full_description' in body:
        product.full_description = body['full_description']
    if 'what_you_get' in body:
        product.what_you_get = body['what_you_get']
    if 'price_ils' in body:
        product.price_ils = float(body['price_ils'])
    if 'photo_url' in body:
        product.photo_url = body['photo_url']
    if 'gallery_urls' in body:
        product.gallery_urls = body['gallery_urls']
    if 'total_slots' in body:
        product.total_slots = body['total_slots']
    if 'status' in body:
        product.status = body['status']
    if 'product_type' in body:
        product.product_type = body['product_type']
    if 'group_size' in body:
        product.group_size = body['group_size']

    product.updated_at = datetime.utcnow().isoformat()
    db.put_product(product.to_dynamodb_item())
    return success_response({'product': product.to_dynamodb_item()})


def delete_product(product_id: str, request_event: Dict) -> Dict:
    """DELETE /api/products/{id} — admin or content_manager"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))

    if not has_permission(ctx, "products:write"):
        return error_response(403, "Access denied")

    item = db.get_product(product_id)
    if not item:
        return error_response(404, "Product not found")

    db.delete_product(product_id)
    return success_response({'message': 'Product deleted', 'product_id': product_id})


# ===== Merchandise Handlers =====
def handle_merchandise(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/merchandise"""

    if method == 'POST' and path == '/api/merchandise/purchase':
        return purchase_merchandise(event)

    if method == 'GET' and path == '/api/merchandise/orders':
        return list_merch_orders(event)

    if method == 'PATCH' and re.match(r'^/api/merchandise/orders/[^/]+$', path):
        order_id = path.split('/')[-1]
        return patch_merch_order(event, order_id)

    return error_response(404, "Merchandise endpoint not found")


def purchase_merchandise(request_event: Dict) -> Dict:
    """POST /api/merchandise/purchase — public, creates pending merch order"""
    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    required = ['product_id', 'buyer']
    for f in required:
        if not body.get(f):
            return error_response(400, f"Missing required field: {f}")

    buyer_data = body['buyer']
    for f in ['name', 'email']:
        if not buyer_data.get(f):
            return error_response(400, f"Missing buyer.{f}")

    product_item = db.get_product(body['product_id'])
    if not product_item:
        return error_response(404, "Product not found")

    product = Product.from_dynamodb_item(product_item)

    if product.status != 'active':
        return error_response(409, "Product is not available")

    if product.total_slots is not None and product.sold_slots >= product.total_slots:
        return error_response(409, "Product is sold out")

    order = MerchandiseOrder(
        order_id=MerchandiseOrder.generate_id(),
        product_id=product.product_id,
        product_slug=product.slug,
        performer_id=product.performer_id,
        buyer=BuyerInfo(
            name=buyer_data['name'],
            email=buyer_data['email'],
            phone=buyer_data.get('phone'),
            telegram=buyer_data.get('telegram'),
        ),
        amount_ils=product.price_ils,
        payment_method='mock' if os.environ.get('PAYMENT_MODE', 'mock') != 'production' else 'allpay',
    )
    db.put_merchandise_order(order.to_dynamodb_item())

    payment_provider = get_payment_provider()
    try:
        # AllPay API requires a tickets list — pass the product as a single line item
        merch_ticket = [type('T', (), {
            'type_name': product.name,
            'quantity': 1,
            'price_per_ticket': product.price_ils,
            'purchased_seats': None,
        })()]
        payment_url = payment_provider.create_payment_url(
            order_id=order.order_id,
            amount=order.amount_ils,
            currency='ILS',
            email=order.buyer.email,
            customer_name=order.buyer.name,
            tickets=merch_ticket,
            order_created_at=order.created_at,
        )
    except Exception as e:
        print(f"Failed to create payment URL: {e}")
        return error_response(500, "Failed to initialize payment")

    return success_response({
        'order_id': order.order_id,
        'payment_url': payment_url,
        'amount_ils': order.amount_ils,
    }, 201)


def list_merch_orders(request_event: Dict) -> Dict:
    """GET /api/merchandise/orders — admin only"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(401, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, "Access denied")

    tenant_id = ctx.get('tenant_id')
    params = request_event.get('queryStringParameters') or {}
    product_id = params.get('product_id', '').strip()

    if product_id:
        product_item = db.get_product(product_id)
        if tenant_id and (not product_item or product_item.get('tenant_id') != tenant_id):
            return error_response(403, "Access denied")
        items = db.list_merchandise_orders_by_product(product_id)
    else:
        result = db.list_merchandise_orders(limit=100)
        if tenant_id:
            tenant_product_ids = {p.get('product_id') for p in db.list_products(tenant_id=tenant_id, status=None)}
            items = [o for o in result['items'] if o.get('product_id') in tenant_product_ids]
        else:
            items = result['items']

    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return success_response({'orders': items})


def patch_merch_order(request_event: Dict, order_id: str) -> Dict:
    """PATCH /api/merchandise/orders/{id} — admin only"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(401, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, "Access denied")

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON body")

    allowed = {'fulfillment_status', 'fulfillment_note'}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return error_response(400, "No valid fields to update")

    if 'fulfillment_status' in updates and updates['fulfillment_status'] not in ('new', 'fulfilled'):
        return error_response(400, "fulfillment_status must be 'new' or 'fulfilled'")

    order_item = db.get_merchandise_order(order_id)
    if not order_item:
        return error_response(404, "Order not found")

    db.update_merchandise_order(order_id, updates)
    return success_response({'order_id': order_id, **updates})


def _send_merchandise_email(order: 'MerchandiseOrder', product_item: Dict):
    """Send purchase confirmation email to buyer via SES"""
    try:
        ses = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'eu-north-1'))
        sender = os.environ.get('EMAIL_SENDER', 'noreply@yallabalagan.com')
        product_name = product_item.get('name', 'Product') if product_item else 'Product'

        ses.send_email(
            Source=sender,
            Destination={'ToAddresses': [order.buyer.email]},
            Message={
                'Subject': {'Data': f'Purchase confirmed: {product_name}', 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {
                        'Data': (
                            f'<p>Hi {order.buyer.name},</p>'
                            f'<p>Your purchase of <strong>{product_name}</strong> '
                            f'for {order.amount_ils:.0f} ILS has been confirmed.</p>'
                            f'<p>Order ID: {order.order_id}</p>'
                            f'<p>Thank you!</p>'
                        ),
                        'Charset': 'UTF-8',
                    }
                },
            }
        )
        print(f"Confirmation email sent to {order.buyer.email} for order {order.order_id}")
    except Exception as e:
        print(f"Failed to send buyer email for {order.order_id}: {e}")


def _send_merchandise_notification_email(order: 'MerchandiseOrder', product_item: Dict, performer_item: Dict):
    """Notify performer of a new purchase"""
    try:
        ses = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'eu-north-1'))
        sender = os.environ.get('EMAIL_SENDER', 'noreply@yallabalagan.com')
        contact_email = performer_item['contact_email']
        product_name = product_item.get('name', 'Product') if product_item else 'Product'
        performer_name = performer_item.get('name', '')

        ses.send_email(
            Source=sender,
            Destination={'ToAddresses': [contact_email]},
            Message={
                'Subject': {'Data': f'New purchase: {product_name}', 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {
                        'Data': (
                            f'<p>Hi {performer_name},</p>'
                            f'<p>New purchase of <strong>{product_name}</strong>:</p>'
                            f'<ul>'
                            f'<li>Buyer: {order.buyer.name} ({order.buyer.email})</li>'
                            f'<li>Amount: {order.amount_ils:.0f} ILS</li>'
                            f'<li>Order ID: {order.order_id}</li>'
                            f'</ul>'
                        ),
                        'Charset': 'UTF-8',
                    }
                },
            }
        )
        print(f"Performer notification sent to {contact_email}")
    except Exception as e:
        print(f"Failed to send performer email: {e}")


# ──────────────────────────────────────────────
# Shows & Episodes handlers
# ──────────────────────────────────────────────

def handle_shows(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET' and path == '/api/shows':
        return list_shows(event)
    if method == 'GET' and path.startswith('/api/shows/'):
        show_id = path.split('/')[-1]
        return get_show(show_id)
    if method == 'POST' and path == '/api/shows':
        return create_show(event)
    if method == 'PATCH' and path.endswith('/sharing'):
        show_id = path.split('/')[-2]
        return patch_show_sharing(show_id, event)

    if method == 'DELETE' and path.endswith('/sharing'):
        show_id = path.split('/')[-2]
        return delete_show_sharing(show_id, event)

    if method == 'PUT' and path.startswith('/api/shows/'):
        show_id = path.split('/')[-1]
        return update_show(show_id, event)
    if method == 'DELETE' and path.startswith('/api/shows/'):
        show_id = path.split('/')[-1]
        return delete_show(show_id, event)
    return error_response(404, 'Not found')


def list_shows(request_event: Dict) -> Dict:
    tenant_id = None
    try:
        ctx = authenticate(request_event)
        tenant_id = ctx.get("tenant_id")
    except AuthError:
        pass
    items = db.list_shows(tenant_id=tenant_id)
    shows = []
    for item in items:
        try:
            d = Show.from_dynamodb_item(item).to_dynamodb_item()
            if tenant_id and item.get('tenant_id') != tenant_id:
                d['_readonly'] = True
            shows.append(d)
        except Exception as e:
            print(f"Error parsing show: {e}")
    shows.sort(key=lambda s: s.get('name', ''))
    return success_response({'shows': shows, 'count': len(shows)})


def get_show(show_id: str) -> Dict:
    item = db.get_show(show_id) or db.get_show_by_slug(show_id)
    if not item:
        return error_response(404, 'Show not found')
    show = Show.from_dynamodb_item(item)
    episodes = db.list_episodes_by_show(show.show_id)
    return success_response({
        'show': show.to_dynamodb_item(),
        'episodes': sorted(episodes, key=lambda e: int(e.get('number', 0)), reverse=True),
    })


def create_show(request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "shows:write"):
        return error_response(403, "Access denied")
    try:
        body = json.loads(request_event.get('body', '{}'))
        required = ['name', 'description', 'short_description']
        for f in required:
            if not body.get(f):
                return error_response(400, f'Missing required field: {f}')
        show_id = Show.generate_id()
        slug = body.get('slug') or Show.generate_slug(body['name'])
        if db.get_show_by_slug(slug):
            return error_response(400, f'Slug already taken: {slug}')
        show = Show(
            show_id=show_id,
            name=body['name'],
            slug=slug,
            description=body['description'],
            short_description=body['short_description'],
            photo_url=body.get('photo_url'),
            links=[ShowLink.from_dict(l) for l in body.get('links', [])],
            tenant_id=ctx.get('tenant_id', 'yallabalagan'),
        )
        db.put_show(show.to_dynamodb_item())
        return success_response({'show': show.to_dynamodb_item()}, 201)
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')
    except Exception as e:
        return error_response(500, f'Failed to create show: {e}')


def update_show(show_id: str, request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "shows:write"):
        return error_response(403, "Access denied")
    item = db.get_show(show_id)
    if not item:
        return error_response(404, 'Show not found')
    if not _owns_record(ctx, item):
        return error_response(403, "This record belongs to another tenant")
    try:
        body = json.loads(request_event.get('body', '{}'))
        show = Show.from_dynamodb_item(item)
        show.name = body.get('name', show.name)
        show.description = body.get('description', show.description)
        show.short_description = body.get('short_description', show.short_description)
        show.photo_url = body.get('photo_url', show.photo_url)
        if 'links' in body:
            show.links = [ShowLink.from_dict(l) for l in body['links']]
        if 'slug' in body and body['slug'] != show.slug:
            if db.get_show_by_slug(body['slug']):
                return error_response(400, f'Slug already taken: {body["slug"]}')
            show.slug = body['slug']
        show.updated_at = datetime.utcnow().isoformat()
        db.put_show(show.to_dynamodb_item())
        return success_response({'show': show.to_dynamodb_item()})
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')
    except Exception as e:
        return error_response(500, f'Failed to update show: {e}')


def delete_show(show_id: str, request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "shows:write"):
        return error_response(403, "Access denied")
    show_item = db.get_show(show_id)
    if not show_item:
        return error_response(404, 'Show not found')
    if not _owns_record(ctx, show_item):
        return error_response(403, "This record belongs to another tenant")
    db.delete_show(show_id)
    return success_response({'deleted': show_id})


def handle_episodes(event: Dict, method: str, path: str) -> Dict:
    parts = path.split('/')
    # /api/episodes or /api/episodes/{id}
    if method == 'GET' and path == '/api/episodes':
        show_id = event.get('queryStringParameters', {}) or {}
        show_id = show_id.get('show_id')
        if show_id:
            items = db.list_episodes_by_show(show_id)
            items.sort(key=lambda e: int(e.get('number', 0)), reverse=True)
            return success_response({'episodes': items, 'count': len(items)})
        items = db.list_all_episodes()
        return success_response({'episodes': items, 'count': len(items)})
    if method == 'GET' and len(parts) == 4:
        episode_id = parts[-1]
        return get_episode(episode_id)
    if method == 'POST' and path == '/api/episodes/suggest-performers':
        return suggest_performers_for_episode(event)
    if method == 'POST' and path == '/api/episodes':
        return create_episode(event)
    if method == 'PUT' and len(parts) == 4:
        return update_episode(parts[-1], event)
    if method == 'DELETE' and len(parts) == 4:
        return delete_episode_handler(parts[-1], event)
    return error_response(404, 'Not found')


def get_episode(episode_id: str) -> Dict:
    item = db.get_episode(episode_id) or db.get_episode_by_slug(episode_id)
    if not item:
        return error_response(404, 'Episode not found')
    return success_response({'episode': item})


def create_episode(request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "episodes:write"):
        return error_response(403, "Access denied")
    try:
        body = json.loads(request_event.get('body', '{}'))
        required = ['show_id', 'title', 'description', 'url']
        for f in required:
            if f not in body or body[f] == '':
                return error_response(400, f'Missing required field: {f}')
        show_item = db.get_show(body['show_id'])
        if not show_item:
            return error_response(404, f'Show not found: {body["show_id"]}')
        show = Show.from_dynamodb_item(show_item)
        if 'number' in body and body['number'] != '':
            number = int(body['number'])
        else:
            existing = db.list_episodes_by_show(body['show_id'])
            number = max((int(e.get('number', 0)) for e in existing), default=0) + 1
        episode_id = Episode.generate_id()
        slug = body.get('slug') or Episode.generate_slug(show.slug, number, body['title'])
        if db.get_episode_by_slug(slug):
            slug = f'{slug}-{episode_id[:6]}'
        episode = Episode(
            episode_id=episode_id,
            show_id=body['show_id'],
            number=number,
            title=body['title'],
            slug=slug,
            description=body['description'],
            url=body['url'],
            thumbnail_url=body.get('thumbnail_url'),
            performer_ids=body.get('performer_ids', []),
            published_at=body.get('published_at', datetime.utcnow().isoformat()),
        )
        db.put_episode(episode.to_dynamodb_item())
        return success_response({'episode': episode.to_dynamodb_item()}, 201)
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')
    except Exception as e:
        return error_response(500, f'Failed to create episode: {e}')


def update_episode(episode_id: str, request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "episodes:write"):
        return error_response(403, "Access denied")
    item = db.get_episode(episode_id)
    if not item:
        return error_response(404, 'Episode not found')
    show_item = db.get_show(item.get('show_id', ''))
    if show_item and not _owns_record(ctx, show_item):
        return error_response(403, "This record belongs to another tenant")
    try:
        body = json.loads(request_event.get('body', '{}'))
        ep = Episode.from_dynamodb_item(item)
        ep.title = body.get('title', ep.title)
        ep.description = body.get('description', ep.description)
        ep.url = body.get('url', ep.url)
        ep.thumbnail_url = body.get('thumbnail_url', ep.thumbnail_url)
        ep.performer_ids = body.get('performer_ids', ep.performer_ids)
        ep.published_at = body.get('published_at', ep.published_at)
        if 'number' in body:
            ep.number = int(body['number'])
        ep.updated_at = datetime.utcnow().isoformat()
        db.put_episode(ep.to_dynamodb_item())
        return success_response({'episode': ep.to_dynamodb_item()})
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')
    except Exception as e:
        return error_response(500, f'Failed to update episode: {e}')


def delete_episode_handler(episode_id: str, request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "episodes:write"):
        return error_response(403, "Access denied")
    ep_item = db.get_episode(episode_id)
    if not ep_item:
        return error_response(404, 'Episode not found')
    show_item = db.get_show(ep_item.get('show_id', ''))
    if show_item and not _owns_record(ctx, show_item):
        return error_response(403, "This record belongs to another tenant")
    db.delete_episode(episode_id)
    return success_response({'deleted': episode_id})


def _performer_name_score(name: str, text: str) -> float:
    name_lower = name.lower().strip()
    if name_lower in text:
        return 1.0
    tokens = name_lower.split()
    text_words = text.split()
    scores = [
        max((SequenceMatcher(None, token, w).ratio() for w in text_words), default=0.0)
        for token in tokens
    ]
    return sum(scores) / len(scores) if scores else 0.0


def suggest_performers_for_episode(request_event: Dict) -> Dict:
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not has_permission(ctx, "episodes:write"):
        return error_response(403, "Access denied")
    try:
        body = json.loads(request_event.get('body', '{}'))
        title = body.get('title', '')
        if not title:
            return error_response(400, 'Missing required field: title')
        text = f"{title} {body.get('description', '')}".lower().strip()
        performers = db.list_performers(status='active')
        suggestions = [
            {'performer_id': p['performer_id'], 'name': p['name'], 'score': round(score, 2)}
            for p in performers
            if (score := _performer_name_score(p['name'], text)) >= 0.70
        ]
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return success_response({'suggestions': suggestions})
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')
    except Exception as e:
        return error_response(500, f'Failed to suggest performers: {e}')


# ===== Helper Functions =====
def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Формирует успешный ответ"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # CORS
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature,X-Scanner-Token,X-Scanner-Event',
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
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Webhook-Signature,X-Scanner-Token,X-Scanner-Event',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
        },
        'body': json.dumps(body_data, ensure_ascii=False, cls=DecimalEncoder)
    }


def _process_merch_webhook(order_id: str, payment_status: str, transaction_id: str) -> Dict:
    """Handle AllPay webhook for a merchandise order (order_id starts with 'merch-')."""
    order_item = db.get_merchandise_order(order_id)
    if not order_item:
        return success_response({'status': 'ignored', 'message': f'Merch order {order_id} not found'})

    db.update_merchandise_order_status(order_id, payment_status, transaction_id or None)

    if payment_status == 'completed':
        try:
            order = MerchandiseOrder.from_dynamodb_item(order_item)
            db.increment_sold_slots(order.product_id)

            product_item = db.get_product(order.product_id)
            if product_item:
                product = Product.from_dynamodb_item(product_item)
                if product.total_slots is not None and product.sold_slots >= product.total_slots:
                    product.status = 'sold_out'
                    product.updated_at = datetime.utcnow().isoformat()
                    db.put_product(product.to_dynamodb_item())

            _send_merchandise_email(order, product_item)

            performer_item = db.get_performer(order.performer_id)
            if performer_item and performer_item.get('contact_email'):
                _send_merchandise_notification_email(order, product_item, performer_item)

        except Exception as e:
            print(f"Failed to finalize merch order {order_id}: {e}")
            import traceback
            traceback.print_exc()

    return success_response({'status': 'success', 'message': 'Webhook processed'})


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

        # Route merch orders to separate handler
        if order_id.startswith('merch-'):
            return _process_merch_webhook(order_id, payment_status, transaction_id)

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

                        # Record influencer commission if this is an influencer coupon
                        if coupon.influencer_id:
                            try:
                                subtotal = float(order.total_amount) + float(order.discount_amount or 0)
                                commission = round(subtotal * coupon.commission_rate, 2)
                                event_item = db.get_event(order.event_id)
                                event_title = event_item.get('title', order.event_id) if event_item else order.event_id
                                total_tickets = sum(t.quantity for t in order.tickets)
                                commission_record = {
                                    'PK': f'INFLUENCER#{coupon.influencer_id}',
                                    'SK': f'COMMISSION#{order.order_id}',
                                    'influencer_id': coupon.influencer_id,
                                    'order_id': order.order_id,
                                    'event_id': order.event_id,
                                    'event_title': event_title,
                                    'tenant_id': event_item.get('tenant_id', '') if event_item else '',
                                    'tickets': total_tickets,
                                    'subtotal': Decimal(str(round(subtotal, 2))),
                                    'commission': Decimal(str(commission)),
                                    'created_at': datetime.now(timezone.utc).isoformat(),
                                }
                                db.add_influencer_commission(commission_record)
                                db.update_influencer_totals(coupon.influencer_id, subtotal, commission)
                                print(f"Recorded commission {commission} for influencer {coupon.influencer_id}")
                            except Exception as e:
                                print(f"Error recording influencer commission: {e}")

                # Сохраняем обновленный заказ с QR кодами
                db.put_order(order.to_dynamodb_item())
                for qr in order.qr_codes:
                    db.put_ticket_lookup(qr.code, order.order_id)
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


def handle_scanner_search(request_event: Dict) -> Dict:
    """GET /api/scanner/search?event_id=&q= — minimal payload, no payment data."""
    if not is_scanner_or_admin(request_event):
        log_security_event('unauthorized_scanner_search', {'ip': get_client_identifier(request_event)})
        return error_response(401, "Unauthorized")

    params = request_event.get('queryStringParameters') or {}
    event_id = (params.get('event_id') or '').strip()
    q = (params.get('q') or '').strip()

    if not event_id:
        return error_response(400, "event_id is required")
    if len(q) < 2:
        return error_response(400, "q must be at least 2 characters")

    # Scanner tokens are event-scoped: enforce event_id == X-Scanner-Event
    headers = {k.lower(): v for k, v in (request_event.get('headers') or {}).items()}
    scanner_token = headers.get('x-scanner-token', '')
    if scanner_token:
        scanner_event = headers.get('x-scanner-event', '')
        if event_id != scanner_event:
            return error_response(403, "event_id mismatch")

    try:
        raw_orders = db.get_orders_by_event(event_id)
        q_lower = q.lower()
        results = []
        for raw in raw_orders:
            order = Order.from_dynamodb_item(raw)
            if not (order.payment and order.payment.status == 'completed'):
                continue
            customer = order.customer or Customer()
            name = (customer.name or '').lower()
            email = (customer.email or '').lower()
            phone = (customer.phone or '').lower()
            if q_lower not in name and q_lower not in email and q_lower not in phone:
                continue
            tickets = [
                {
                    'code': qr.code,
                    'ticket_type': qr.ticket_type,
                    'seat_id': getattr(qr, 'seat_id', None),
                    'scanned': qr.scanned,
                    'scanned_at': qr.scanned_at,
                    'cancelled': qr.cancelled,
                }
                for qr in (order.qr_codes or [])
            ]
            results.append({
                'order_id': order.order_id,
                'customer': {'name': customer.name, 'phone': customer.phone},
                'tickets': tickets,
            })
        return success_response({'results': results})
    except Exception as e:
        return error_response(500, str(e))


##############################################################################
# Influencer / Loyalty Program
##############################################################################

def handle_influencers(event: Dict, method: str, path: str) -> Dict:
    segments = [s for s in path.split('/') if s]
    # /api/influencers
    if len(segments) == 2:
        if method == 'POST':
            return register_influencer(event)
        elif method == 'GET':
            return list_influencers_admin(event)
    # /api/influencers/{id}
    elif len(segments) == 3:
        influencer_id = segments[2]
        if method == 'GET':
            return get_influencer_dashboard(influencer_id)
    return error_response(404, "Endpoint not found")


def register_influencer(request_event: Dict) -> Dict:
    """POST /api/influencers — platform_admin only"""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_platform_admin(ctx):
        return error_response(403, "Only platform_admin can register influencers")

    try:
        body = json.loads(request_event.get('body') or '{}')
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON")

    required = ['name', 'email', 'phone', 'social_link', 'audience_size', 'coupon_code']
    for field_name in required:
        if not body.get(field_name, '').strip():
            return error_response(400, f"Missing required field: {field_name}")

    raw_code = body['coupon_code'].strip().upper()
    if not re.match(r'^[A-Z0-9][A-Z0-9\-]{1,19}$', raw_code):
        return error_response(400, "Промо-код: 2–20 символов, только буквы, цифры и дефис")

    # Check code availability
    if db.get_coupon(raw_code):
        return error_response(409, "Этот промо-код уже занят")

    import uuid as _uuid
    influencer_id = str(_uuid.uuid4())

    coupon = Coupon(
        coupon_code=raw_code,
        discount_type='percentage',
        discount_value=10.0,
        event_ids=['*'],
        status='active',
        description=f'Промо-код блогера {body["name"].strip()}',
        influencer_id=influencer_id,
        commission_rate=0.10,
    )
    db.put_coupon(coupon.to_dynamodb_item())

    influencer = Influencer(
        influencer_id=influencer_id,
        name=body['name'].strip(),
        email=body['email'].strip().lower(),
        phone=body['phone'].strip(),
        social_link=body['social_link'].strip(),
        audience_size=body['audience_size'].strip(),
        coupon_code=raw_code,
    )
    db.put_influencer(influencer.to_dynamodb_item())

    # Send welcome email asynchronously
    try:
        frontend_url = os.environ.get('FRONTEND_URL', 'https://yallabalagan.org')
        dashboard_url = f"{frontend_url}/loyalty-dashboard.html?id={influencer_id}"
        lambda_client = boto3.client('lambda')
        lambda_client.invoke(
            FunctionName=os.environ.get('EMAIL_SENDER_LAMBDA', 'yallabalagan-email-sender'),
            InvocationType='Event',
            Payload=json.dumps({
                'email_type': 'influencer_welcome',
                'influencer_id': influencer_id,
                'name': influencer.name,
                'email': influencer.email,
                'coupon_code': raw_code,
                'dashboard_url': dashboard_url,
            })
        )
    except Exception as e:
        print(f"Warning: failed to trigger welcome email: {e}")

    return success_response({
        'influencer_id': influencer_id,
        'coupon_code': raw_code,
    }, status_code=201)


def get_influencer_dashboard(influencer_id: str) -> Dict:
    """GET /api/influencers/{id} — public, UUID-gated"""
    item = db.get_influencer(influencer_id)
    if not item:
        return error_response(404, "Influencer not found")
    influencer = Influencer.from_dynamodb_item(item)
    commissions_raw = db.get_influencer_commissions(influencer_id)
    commissions = [
        {
            'order_id': c.get('order_id', ''),
            'event_id': c.get('event_id', ''),
            'event_title': c.get('event_title', ''),
            'tickets': int(c.get('tickets', 0)),
            'subtotal': float(c.get('subtotal', 0)),
            'commission': float(c.get('commission', 0)),
            'created_at': c.get('created_at', ''),
        }
        for c in commissions_raw
    ]
    return success_response({
        'influencer': influencer.to_dict(),
        'commissions': commissions,
    })


def list_influencers_admin(request_event: Dict) -> Dict:
    """GET /api/influencers — admin only; returns per-tenant stats for non-platform_admin."""
    ctx = None
    try:
        ctx = authenticate(request_event)
    except AuthError:
        auth = get_admin_authenticator()
        if not auth.verify_admin_key(auth.extract_api_key(request_event)):
            return error_response(401, "Unauthorized")

    items = db.list_influencers()
    influencers = []
    for item in items:
        try:
            influencers.append(Influencer.from_dynamodb_item(item).to_dict())
        except Exception as e:
            print(f"Error parsing influencer: {e}")

    if ctx and not is_platform_admin(ctx):
        tenant_id = ctx.get('tenant_id')
        commissions = db.list_commissions_by_tenant(tenant_id)
        agg = {}
        for c in commissions:
            iid = c.get('influencer_id', '')
            if iid not in agg:
                agg[iid] = {'total_sales': 0.0, 'total_commission': 0.0, 'orders_count': 0}
            agg[iid]['total_sales']      += float(c.get('subtotal', 0))
            agg[iid]['total_commission'] += float(c.get('commission', 0))
            agg[iid]['orders_count']     += 1
        for inf in influencers:
            iid = inf['influencer_id']
            t = agg.get(iid, {'total_sales': 0.0, 'total_commission': 0.0, 'orders_count': 0})
            inf['total_sales']      = round(t['total_sales'], 2)
            inf['total_commission'] = round(t['total_commission'], 2)
            inf['orders_count']     = t['orders_count']

    return success_response({'influencers': influencers})


##############################################################################
# Instagram OAuth + Connection handlers
##############################################################################

def _ig_env() -> tuple[str, str, str, str]:
    """Return (app_id, app_secret, token_key, api_base_url) or raise."""
    app_id = os.environ.get('META_APP_ID', '')
    app_secret = os.environ.get('META_APP_SECRET', '')
    token_key = os.environ.get('INSTAGRAM_TOKEN_KEY', '')
    api_base_url = os.environ.get('API_BASE_URL', '')
    if not all([app_id, app_secret, token_key, api_base_url]):
        raise ValueError("Instagram env vars not configured (META_APP_ID, META_APP_SECRET, INSTAGRAM_TOKEN_KEY, API_BASE_URL)")
    return app_id, app_secret, token_key, api_base_url


def handle_studio(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET' and path == '/api/studio/templates':
        return studio_list_templates(event)
    if method == 'POST' and path == '/api/studio/templates':
        return studio_create_template(event)
    if method == 'DELETE' and path.startswith('/api/studio/templates/'):
        tpl_id = path.split('/')[-1]
        return studio_delete_template(event, tpl_id)
    return error_response(404, 'Not found')


def studio_list_templates(request_event: Dict) -> Dict:
    """GET /api/studio/templates — list all HTML template presets."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    templates = db.list_templates()
    serialized = [
        {'id': t.get('SK'), 'name': t.get('name'), 'html': t.get('html', ''), 'created_at': t.get('created_at')}
        for t in templates
    ]
    return success_response({'templates': serialized})


def studio_create_template(request_event: Dict) -> Dict:
    """POST /api/studio/templates — save a new HTML template."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    body = json.loads(request_event.get('body') or '{}')
    name = (body.get('name') or '').strip()
    html = (body.get('html') or '').strip()

    if not name:
        return error_response(400, 'name is required')
    if not html:
        return error_response(400, 'html is required')
    if len(html.encode('utf-8')) > 380_000:
        return error_response(400, 'HTML too large (max 380KB)')

    import uuid
    tpl_id = str(uuid.uuid4())[:8]
    tpl = {
        'id': tpl_id,
        'name': name,
        'html': html,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    db.put_template(tpl)
    return success_response({'template': tpl}, 201)


def studio_delete_template(request_event: Dict, tpl_id: str) -> Dict:
    """DELETE /api/studio/templates/{id}."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    existing = db.get_template(tpl_id)
    if not existing:
        return error_response(404, 'Template not found')

    db.delete_template(tpl_id)
    return success_response({'deleted': tpl_id})


def handle_facebook_ads(event: Dict, method: str, path: str) -> Dict:
    if method == 'POST' and path == '/api/facebook/create-ad':
        return fb_create_ad_campaign(event)
    if method == 'GET' and path == '/api/facebook/upload-url':
        return fb_get_video_upload_url(event)
    if method == 'GET' and path == '/api/facebook/campaigns':
        return fb_get_campaigns(event)
    return error_response(404, 'Not found')


def fb_create_ad_campaign(request_event: Dict) -> Dict:
    """POST /api/facebook/create-ad — create FB campaign + ad set + ads."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        body = json.loads(request_event.get('body') or '{}')
        event_id       = (body.get('event_id') or '').strip()
        campaign_name  = (body.get('campaign_name') or '').strip()
        ad_text        = (body.get('ad_text') or '').strip()
        daily_budget_ils = body.get('daily_budget_ils')
        start_date     = (body.get('start_date') or '').strip()
        end_date       = (body.get('end_date') or '').strip()
        city_lat       = body.get('city_lat')
        city_lng       = body.get('city_lng')
        creatives      = body.get('creatives') or {}

        if not all([event_id, campaign_name, ad_text, daily_budget_ils, start_date, end_date]):
            return error_response(400, 'Missing required fields')
        if not creatives:
            return error_response(400, 'At least one creative is required')

        ev = db.get_event(event_id)
        if not ev:
            return error_response(404, 'Event not found')

        slug = ev.get('slug') or event_id
        link_url = f"https://yallabalagan.org/events/{slug}.html"

        from datetime import datetime, timezone
        start_unix = int(datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
        end_unix   = int(datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
        daily_budget_cents = int(float(daily_budget_ils)) * 100

        token          = os.environ['FB_SYSTEM_USER_TOKEN']
        ad_account_id  = os.environ['FB_AD_ACCOUNT_ID']
        page_id        = os.environ['FB_PAGE_ID']
        pixel_id       = os.environ.get('FB_PIXEL_ID', '')

        from utils.facebook_ads import (
            CAMPAIGN_PREFIX,
            build_targeting, create_campaign, create_ad_set,
            upload_image, upload_video_from_url,
            create_image_ad_creative, create_video_ad_creative, create_ad,
        )

        prefixed_name = f"{CAMPAIGN_PREFIX}{campaign_name}"
        targeting = build_targeting(city_lat or 32.0853, city_lng or 34.7818)

        campaign_id = create_campaign(prefixed_name, token, ad_account_id, pixel_id)
        ad_set_id   = create_ad_set(
            campaign_id, prefixed_name, daily_budget_cents,
            start_unix, end_unix, targeting, pixel_id, page_id, token, ad_account_id,
        )

        IMAGE_SLOTS = ('story_image', 'square_image', 'horizontal_image')
        ads_created = []
        ads_failed  = []

        for slot_key, url in creatives.items():
            if not url:
                continue
            try:
                if slot_key in IMAGE_SLOTS:
                    image_hash  = upload_image(url, token, ad_account_id)
                    creative_id = create_image_ad_creative(page_id, ad_text, image_hash, link_url, token, ad_account_id)
                elif slot_key == 'story_video':
                    video_id    = upload_video_from_url(url, campaign_name, token, ad_account_id)
                    creative_id = create_video_ad_creative(page_id, ad_text, video_id, link_url, token, ad_account_id)
                else:
                    continue
                ad_id = create_ad(ad_set_id, creative_id, slot_key, token, ad_account_id)
                ads_created.append({'slot': slot_key, 'ad_id': ad_id})
            except (RuntimeError, Exception) as e:
                ads_failed.append({'slot': slot_key, 'error': str(e)})

        manager_url = f"https://www.facebook.com/adsmanager/manage/campaigns?act={ad_account_id.replace('act_', '')}"
        return success_response({
            'campaign_id': campaign_id,
            'ad_set_id': ad_set_id,
            'ads_created': ads_created,
            'ads_failed': ads_failed,
            'partial': len(ads_failed) > 0,
            'manager_url': manager_url,
        })

    except (KeyError, EnvironmentError) as e:
        return error_response(500, f'Server configuration error: {str(e)}')
    except RuntimeError as e:
        print(f"fb_create_ad_campaign FB error: {e}")
        return error_response(502, str(e))
    except Exception as e:
        print(f"fb_create_ad_campaign error: {e}")
        return error_response(500, 'Internal server error')


def fb_get_video_upload_url(request_event: Dict) -> Dict:
    """GET /api/facebook/upload-url — presigned S3 PUT URL for video upload."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        params       = request_event.get('queryStringParameters') or {}
        filename     = (params.get('filename') or '').strip()
        content_type = (params.get('contentType') or '').strip()

        if not filename or not content_type:
            return error_response(400, 'Missing filename or contentType')
        if content_type != 'video/mp4':
            return error_response(400, 'Only video/mp4 is supported')

        import uuid
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', os.path.basename(filename))
        object_key = f"videos/{uuid.uuid4().hex[:8]}_{safe_name}"

        bucket_name = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')
        s3_client   = boto3.client('s3', region_name='eu-north-1')

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket_name, 'Key': object_key, 'ContentType': content_type},
            ExpiresIn=300,
        )
        s3_url = f"https://{bucket_name}.s3.eu-north-1.amazonaws.com/{object_key}"
        return success_response({'upload_url': upload_url, 's3_url': s3_url})

    except Exception as e:
        print(f"fb_get_video_upload_url error: {e}")
        return error_response(500, 'Internal server error')


def fb_get_campaigns(request_event: Dict) -> Dict:
    """GET /api/facebook/campaigns — list active/paused campaigns with lifetime insights."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        token         = os.environ['FB_SYSTEM_USER_TOKEN']
        ad_account_id = os.environ['FB_AD_ACCOUNT_ID']
        from utils.facebook_ads import get_campaigns_with_insights
        raw = get_campaigns_with_insights(token, ad_account_id)

        campaigns = []
        for c in raw:
            ins_list = c.get('insights', {}).get('data', [])
            ins = ins_list[0] if ins_list else {}
            actions = ins.get('actions', [])
            conversions = sum(
                int(a.get('value', 0))
                for a in actions
                if a.get('action_type') == 'purchase'
            )
            daily_ils = round(int(c.get('daily_budget') or 0) / 100)
            campaigns.append({
                'id':               c['id'],
                'name':             c.get('name', ''),
                'status':           c.get('status', ''),
                'daily_budget_ils': daily_ils,
                'start_time':       c.get('start_time', ''),
                'end_time':         c.get('end_time', ''),
                'impressions':      int(ins.get('impressions') or 0),
                'clicks':           int(ins.get('clicks') or 0),
                'spend_ils':        round(float(ins.get('spend') or 0), 2),
                'conversions':      conversions,
                'manager_url':      (
                    f"https://www.facebook.com/adsmanager/manage/campaigns"
                    f"?act={ad_account_id.replace('act_', '')}&campaign_ids={c['id']}"
                ),
            })
        return success_response({'campaigns': campaigns})

    except RuntimeError as e:
        print(f"fb_get_campaigns FB error: {e}")
        return error_response(502, str(e))
    except Exception as e:
        print(f"fb_get_campaigns error: {e}")
        return error_response(500, 'Internal server error')


def handle_instagram(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET' and path == '/api/instagram/accounts':
        return ig_list_accounts(event)
    if method == 'GET' and path == '/api/instagram/oauth/start':
        return ig_oauth_start(event)
    if method == 'GET' and path == '/api/instagram/oauth/callback':
        return ig_oauth_callback(event)
    if method == 'DELETE' and path.startswith('/api/instagram/accounts/'):
        ig_user_id = path.split('/')[-1]
        return ig_disconnect(event, ig_user_id)
    if method == 'POST' and path == '/api/instagram/post':
        return ig_post_story(event)
    if method == 'GET' and path == '/api/instagram/history':
        return ig_list_history(event)
    return error_response(404, 'Not found')


def ig_list_accounts(request_event: Dict) -> Dict:
    """GET /api/instagram/accounts — list connected IG accounts."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    items = db.list_instagram_connections(tenant_id=ctx.get('tenant_id'))
    accounts = []
    for item in items:
        accounts.append({
            'ig_user_id': item.get('SK'),
            'ig_username': item.get('ig_username'),
            'ig_name': item.get('ig_name'),
            'token_expires_at': item.get('token_expires_at'),
            'connected_at': item.get('connected_at'),
            'connected_by': item.get('connected_by'),
            'status': item.get('status', 'active'),
        })
    return success_response({'accounts': accounts})


def ig_oauth_start(request_event: Dict) -> Dict:
    """GET /api/instagram/oauth/start — redirect to Meta OAuth page."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        app_id, _, _, api_base_url = _ig_env()
    except ValueError as e:
        return error_response(500, str(e))

    import secrets as _secrets
    from utils.instagram import get_oauth_url
    tenant_id = ctx.get('tenant_id', 'yallabalagan')
    state = f"{tenant_id}:{_secrets.token_urlsafe(16)}"
    redirect_uri = f"{api_base_url}/api/instagram/oauth/callback"
    oauth_url = get_oauth_url(app_id, redirect_uri, state)
    return success_response({'url': oauth_url})


def ig_oauth_callback(request_event: Dict) -> Dict:
    """GET /api/instagram/oauth/callback — exchange code, store token, redirect."""
    qs = request_event.get('queryStringParameters') or {}
    code = qs.get('code')
    error = qs.get('error')
    state = qs.get('state', '')
    # state format: "tenant_id:random" — extract tenant_id
    _ig_tenant_id = state.split(':')[0] if ':' in state else 'yallabalagan'
    admin_url = os.environ.get('ADMIN_BASE_URL', '')

    if error or not code:
        return _ig_redirect(admin_url, 'social-settings.html', error='oauth_denied')

    try:
        app_id, app_secret, token_key, api_base_url = _ig_env()
    except ValueError:
        return _ig_redirect(admin_url, 'social-settings.html', error='config_error')

    try:
        from utils.instagram import (
            exchange_code, get_long_lived_token, get_user_pages,
            get_business_pages, get_ig_user_info, encrypt_token, token_expires_at,
        )
        redirect_uri = f"{api_base_url}/api/instagram/oauth/callback"

        # Exchange code → short-lived token
        short = exchange_code(app_id, app_secret, redirect_uri, code)
        short_token = short['access_token']

        # Short → long-lived (~60 days)
        long = get_long_lived_token(app_id, app_secret, short_token)
        long_token = long['access_token']
        expires_in = long.get('expires_in', 5183944)  # ~60 days default

        # Find Instagram Business account via FB Pages
        from utils.instagram import get_me
        me = get_me(long_token)
        print(f"Instagram OAuth: token belongs to: {me}")
        pages = get_user_pages(long_token)
        print(f"Instagram OAuth: {len(pages)} direct pages found")
        # Fallback: Business Suite managed pages
        if not pages:
            print("Instagram OAuth: trying Business API fallback")
            pages = get_business_pages(long_token)
            print(f"Instagram OAuth: {len(pages)} business pages found")
        for p in pages:
            print(f"  Page {p.get('id')} '{p.get('name')}': ig_business={p.get('instagram_business_account')}")
        ig_account = None
        page_id = None
        for page in pages:
            ib = page.get('instagram_business_account')
            if ib:
                ig_account = ib
                page_id = page['id']
                break

        if not ig_account:
            print("Instagram OAuth: no IG Business account linked to any FB page")
            return _ig_redirect(admin_url, 'social-settings.html', error='no_ig_business')

        ig_user_id = ig_account['id']
        ig_info = get_ig_user_info(ig_user_id, long_token)

        now = datetime.now(timezone.utc).isoformat()
        connection = {
            'PK': 'CONNECTION',
            'SK': ig_user_id,
            'ig_user_id': ig_user_id,
            'ig_username': ig_info.get('username', ''),
            'ig_name': ig_info.get('name', ''),
            'ig_picture_url': ig_info.get('profile_picture_url', ''),
            'access_token': encrypt_token(long_token, token_key),
            'token_expires_at': token_expires_at(expires_in),
            'page_id': page_id,
            'connected_at': now,
            'status': 'active',
            'tenant_id': _ig_tenant_id,
        }
        db.put_instagram_connection(connection)
        return _ig_redirect(admin_url, 'social-settings.html', success='connected')

    except Exception as e:
        print(f"Instagram OAuth callback error: {e}")
        import traceback; traceback.print_exc()
        return _ig_redirect(admin_url, 'social-settings.html', error='callback_failed')


def _ig_redirect(admin_url: str, page: str, **params) -> Dict:
    from urllib.parse import urlencode
    qs = urlencode(params)
    location = f"{admin_url}/{page}?{qs}" if admin_url else f"/{page}?{qs}"
    return {
        'statusCode': 302,
        'headers': {'Location': location, 'Access-Control-Allow-Origin': '*'},
        'body': '',
    }


def ig_disconnect(request_event: Dict, ig_user_id: str) -> Dict:
    """DELETE /api/instagram/accounts/{ig_user_id} — remove connection."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    if not db.get_instagram_connection(ig_user_id):
        return error_response(404, 'Account not found')

    db.delete_instagram_connection(ig_user_id)
    return success_response({'message': 'Disconnected'})


def ig_post_story(request_event: Dict) -> Dict:
    """POST /api/instagram/post — publish image URL to IG as a Story."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        body = json.loads(request_event.get('body', '{}'))
        ig_user_id = body.get('ig_user_id')
        image_url = body.get('image_url')
        caption = body.get('caption', '')
        link = body.get('link', '')
        if not ig_user_id or not image_url:
            return error_response(400, 'ig_user_id and image_url are required')
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')

    try:
        _, _, token_key, _ = _ig_env()
    except ValueError as e:
        return error_response(500, str(e))

    connection = db.get_instagram_connection(ig_user_id)
    if not connection:
        return error_response(404, 'Instagram account not connected')

    try:
        from utils.instagram import decrypt_token, post_story
        access_token = decrypt_token(connection['access_token'], token_key)
        media_id = post_story(ig_user_id, image_url, access_token, link=link)
    except Exception as e:
        print(f"Instagram post error: {e}")
        import traceback; traceback.print_exc()
        return error_response(500, f"Failed to post: {e}")

    # Write history log separately — don't let a log failure mask a successful post
    try:
        now = datetime.now(timezone.utc)
        month = now.strftime('%Y-%m')
        log = {
            'PK': f'LOG#{month}',
            'SK': f"{now.isoformat()}#{ig_user_id}",
            'ig_user_id': ig_user_id,
            'ig_username': connection.get('ig_username', ''),
            'image_url': image_url,
            'thumbnail_url': image_url,
            'media_id': media_id,
            'posted_at': now.isoformat(),
            'posted_by': ctx.get('user_id', '') if isinstance(ctx, dict) else getattr(ctx, 'user_id', ''),
        }
        db.put_instagram_log(log)
    except Exception as log_err:
        print(f"Warning: failed to write Instagram history log: {log_err}")

    return success_response({'media_id': media_id})


def ig_list_history(request_event: Dict) -> Dict:
    """GET /api/instagram/history?month=YYYY-MM — post history log."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    qs = request_event.get('queryStringParameters') or {}
    month = qs.get('month', datetime.now(timezone.utc).strftime('%Y-%m'))
    items = db.list_instagram_logs(month)
    return success_response({'history': items, 'month': month})


# ─── TikTok API ───────────────────────────────────────────────────────────────

def handle_tiktok(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET'    and path == '/api/tiktok/accounts':           return tiktok_list_accounts(event)
    if method == 'GET'    and path == '/api/tiktok/oauth/start':        return tiktok_oauth_start(event)
    if method == 'GET'    and path == '/api/tiktok/oauth/callback':     return tiktok_oauth_callback(event)
    if method == 'DELETE' and path.startswith('/api/tiktok/accounts/'): return tiktok_disconnect(event, path.split('/')[-1])
    return error_response(404, 'Not found')


def tiktok_list_accounts(request_event: Dict) -> Dict:
    """GET /api/tiktok/accounts — list connected TikTok accounts."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    accounts = db.list_tiktok_connections(tenant_id=ctx.get('tenant_id'))
    safe = [{k: v for k, v in a.items() if k not in ('access_token', 'refresh_token', 'PK')} for a in accounts]
    return success_response({'accounts': safe})


def tiktok_oauth_start(request_event: Dict) -> Dict:
    """GET /api/tiktok/oauth/start — redirect URL to TikTok OAuth."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    client_key = os.environ.get('TIKTOK_CLIENT_KEY', '')
    api_base_url = os.environ.get('API_BASE_URL', '')
    if not client_key:
        return error_response(503, 'TikTok not configured')

    import secrets as _secrets
    tenant_id = ctx.get('tenant_id', 'yallabalagan')
    state = f"{tenant_id}:{_secrets.token_urlsafe(16)}"
    redirect_uri = f"{api_base_url}/api/social/tt/callback"

    from utils.tiktok import get_oauth_url
    url = get_oauth_url(client_key, redirect_uri, state)
    return success_response({'url': url})


def tiktok_oauth_callback(request_event: Dict) -> Dict:
    """GET /api/tiktok/oauth/callback — exchange code, store tokens, redirect."""
    qs = request_event.get('queryStringParameters') or {}
    admin_url = os.environ.get('ADMIN_BASE_URL', '')
    api_base_url = os.environ.get('API_BASE_URL', '')
    _tt_state = qs.get('state', '')
    _tt_tenant_id = _tt_state.split(':')[0] if ':' in _tt_state else 'yallabalagan'

    code = qs.get('code', '')
    error = qs.get('error', '')
    if error or not code:
        return _tt_redirect(admin_url, error='oauth_denied')

    client_key = os.environ.get('TIKTOK_CLIENT_KEY', '')
    client_secret = os.environ.get('TIKTOK_CLIENT_SECRET', '')
    token_key = os.environ.get('TIKTOK_TOKEN_KEY', '')
    if not client_key or not client_secret or not token_key:
        return _tt_redirect(admin_url, error='config_error')

    try:
        from utils.tiktok import exchange_code, get_user_info, encrypt_token, token_expires_at
        redirect_uri = f"{api_base_url}/api/social/tt/callback"
        tokens = exchange_code(client_key, client_secret, redirect_uri, code)

        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token', '')
        open_id = tokens.get('open_id', '')
        expires_in = tokens.get('expires_in', 86400)
        refresh_expires_in = tokens.get('refresh_expires_in', 31536000)

        user_info = get_user_info(access_token, open_id)
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        connection = {
            'PK': 'CONNECTION',
            'SK': open_id,
            'tiktok_user_id': open_id,
            'display_name': user_info.get('display_name', ''),
            'avatar_url': user_info.get('avatar_url', ''),
            'access_token': encrypt_token(access_token, token_key),
            'refresh_token': encrypt_token(refresh_token, token_key) if refresh_token else '',
            'token_expires_at': token_expires_at(expires_in),
            'refresh_token_expires_at': token_expires_at(refresh_expires_in),
            'connected_at': now,
            'status': 'active',
            'tenant_id': _tt_tenant_id,
        }
        db.put_tiktok_connection(connection)
        return _tt_redirect(admin_url, success='tiktok_connected')

    except Exception as e:
        print(f"TikTok OAuth callback error: {e}")
        import traceback; traceback.print_exc()
        return _tt_redirect(admin_url, error='callback_failed')


def _tt_redirect(admin_url: str, **params) -> Dict:
    from urllib.parse import urlencode
    qs = urlencode(params)
    location = f"{admin_url}/social-settings.html?{qs}" if admin_url else f"/social-settings.html?{qs}"
    return {
        'statusCode': 302,
        'headers': {'Location': location, 'Access-Control-Allow-Origin': '*'},
        'body': '',
    }


def tiktok_disconnect(request_event: Dict, tiktok_user_id: str) -> Dict:
    """DELETE /api/tiktok/accounts/{user_id} — remove TikTok connection."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    if not db.get_tiktok_connection(tiktok_user_id):
        return error_response(404, 'Account not found')

    db.delete_tiktok_connection(tiktok_user_id)
    return success_response({'message': 'Disconnected'})


# ─── YouTube API ───────────────────────────────────────────────────────────────

def handle_youtube(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET'    and path == '/api/youtube/accounts':            return youtube_list_accounts(event)
    if method == 'GET'    and path == '/api/youtube/oauth/start':         return youtube_oauth_start(event)
    if method == 'GET'    and path == '/api/youtube/oauth/callback':      return youtube_oauth_callback(event)
    if method == 'DELETE' and path.startswith('/api/youtube/accounts/'):  return youtube_disconnect(event, path.split('/')[-1])
    return error_response(404, 'Not found')


def youtube_list_accounts(request_event: Dict) -> Dict:
    """GET /api/youtube/accounts — list connected YouTube channels."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    accounts = db.list_youtube_connections(tenant_id=ctx.get('tenant_id'))
    safe = [{k: v for k, v in a.items() if k not in ('access_token', 'refresh_token', 'PK')} for a in accounts]
    return success_response({'accounts': safe})


def youtube_oauth_start(request_event: Dict) -> Dict:
    """GET /api/youtube/oauth/start — redirect URL to Google OAuth."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    client_id = os.environ.get('YOUTUBE_CLIENT_ID', '')
    api_base_url = os.environ.get('API_BASE_URL', '')
    if not client_id:
        return error_response(503, 'YouTube not configured')

    import secrets as _secrets
    tenant_id = ctx.get('tenant_id', 'yallabalagan')
    state = f"{tenant_id}:{_secrets.token_urlsafe(16)}"
    redirect_uri = f"{api_base_url}/api/youtube/oauth/callback"

    from utils.youtube import get_oauth_url
    url = get_oauth_url(client_id, redirect_uri, state)
    return success_response({'url': url})


def youtube_oauth_callback(request_event: Dict) -> Dict:
    """GET /api/youtube/oauth/callback — exchange code, store tokens, redirect."""
    qs = request_event.get('queryStringParameters') or {}
    admin_url = os.environ.get('ADMIN_BASE_URL', '')
    api_base_url = os.environ.get('API_BASE_URL', '')

    _yt_state = qs.get('state', '')
    _yt_tenant_id = _yt_state.split(':')[0] if ':' in _yt_state else 'yallabalagan'

    code = qs.get('code', '')
    error = qs.get('error', '')
    if error or not code:
        return _yt_redirect(admin_url, error='oauth_denied')

    client_id = os.environ.get('YOUTUBE_CLIENT_ID', '')
    client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET', '')
    token_key = os.environ.get('YOUTUBE_TOKEN_KEY', '')
    if not client_id or not client_secret or not token_key:
        return _yt_redirect(admin_url, error='config_error')

    try:
        from utils.youtube import exchange_code, get_channel_info, encrypt_token, token_expires_at
        redirect_uri = f"{api_base_url}/api/youtube/oauth/callback"
        print(f"YouTube OAuth callback: redirect_uri={redirect_uri} code_len={len(code)}")
        tokens = exchange_code(client_id, client_secret, redirect_uri, code)

        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token', '')
        expires_in = tokens.get('expires_in', 3600)

        channel = get_channel_info(access_token)
        channel_id = channel['channel_id']
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        connection = {
            'PK': 'CONNECTION',
            'SK': channel_id,
            'youtube_channel_id': channel_id,
            'channel_title': channel.get('channel_title', ''),
            'channel_thumbnail_url': channel.get('channel_thumbnail_url', ''),
            'access_token': encrypt_token(access_token, token_key),
            'refresh_token': encrypt_token(refresh_token, token_key) if refresh_token else '',
            'token_expires_at': token_expires_at(expires_in),
            'connected_at': now,
            'status': 'active',
            'tenant_id': _yt_tenant_id,
        }
        db.put_youtube_connection(connection)
        return _yt_redirect(admin_url, success='youtube_connected')

    except Exception as e:
        print(f"YouTube OAuth callback error: {e}")
        import traceback; traceback.print_exc()
        return _yt_redirect(admin_url, error='callback_failed')


def _yt_redirect(admin_url: str, **params) -> Dict:
    from urllib.parse import urlencode
    qs = urlencode(params)
    location = f"{admin_url}/social-settings.html?{qs}" if admin_url else f"/social-settings.html?{qs}"
    return {
        'statusCode': 302,
        'headers': {'Location': location, 'Access-Control-Allow-Origin': '*'},
        'body': '',
    }


def youtube_disconnect(request_event: Dict, channel_id: str) -> Dict:
    """DELETE /api/youtube/accounts/{channel_id} — remove YouTube connection."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    if not db.get_youtube_connection(channel_id):
        return error_response(404, 'Account not found')

    db.delete_youtube_connection(channel_id)
    return success_response({'message': 'Disconnected'})


# ─── Social Cross-Post API ─────────────────────────────────────────────────────

def handle_social(event: Dict, method: str, path: str) -> Dict:
    if method == 'GET' and path == '/api/social/posts':
        return social_list_posts(event)
    if method == 'POST' and path == '/api/social/posts':
        return social_create_post(event)
    if method == 'GET' and path == '/api/social/upload-url':
        return social_upload_url(event)
    if method == 'POST' and path.startswith('/api/social/posts/') and path.endswith('/publish'):
        post_id = path.split('/')[-2]
        return social_publish_post(event, post_id)
    if method == 'DELETE' and path.startswith('/api/social/posts/'):
        post_id = path.split('/')[-1]
        return social_delete_post(event, post_id)
    if method == 'GET' and path == '/api/social/tt/callback':
        return tiktok_oauth_callback(event)
    return error_response(404, 'Not found')


def social_list_posts(request_event: Dict) -> Dict:
    """GET /api/social/posts — list cross-posts (newest first)."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    _tenant_id = ctx.get('tenant_id')
    posts = db.list_social_posts(tenant_id=_tenant_id)
    ig_conns = {c['SK']: c.get('ig_username', '') or c.get('ig_name', '') for c in db.list_instagram_connections(tenant_id=_tenant_id)}
    tt_conns = {c['SK']: c.get('display_name', '') for c in db.list_tiktok_connections(tenant_id=_tenant_id)}
    yt_conns = {c['SK']: c.get('channel_title', '') for c in db.list_youtube_connections(tenant_id=_tenant_id)}
    account_labels = {'instagram': ig_conns, 'tiktok': tt_conns, 'youtube': yt_conns}

    for post in posts:
        for target in post.get('targets', []):
            platform = target.get('platform', '')
            account_id = target.get('account_id', '')
            target['account_label'] = account_labels.get(platform, {}).get(account_id, '')

    return success_response({'posts': posts})


def social_create_post(request_event: Dict) -> Dict:
    """POST /api/social/posts — create a cross-post (draft, schedule, or publish immediately)."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    try:
        body = json.loads(request_event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response(400, 'Invalid JSON')

    title = body.get('title', '')
    description = body.get('description', body.get('caption', ''))
    tags = body.get('tags', [])
    cover = body.get('cover')  # { type, timestamp_ms?, s3_key, public_url }
    collaborators = body.get('collaborators', [])
    media = body.get('media', [])
    targets = body.get('targets', [])
    scheduled_at = body.get('scheduled_at')

    if not targets:
        return error_response(400, 'At least one target account is required')
    if not media:
        return error_response(400, 'At least one media item is required')

    # Validate targets
    for t in targets:
        if t.get('platform') == 'instagram':
            if not db.get_instagram_connection(t.get('account_id', '')):
                return error_response(400, f"Instagram account {t.get('account_id')} not connected")
        elif t.get('platform') == 'tiktok':
            if not db.get_tiktok_connection(t.get('account_id', '')):
                return error_response(400, f"TikTok account {t.get('account_id')} not connected")
        elif t.get('platform') == 'youtube':
            if not db.get_youtube_connection(t.get('account_id', '')):
                return error_response(400, f"YouTube account {t.get('account_id')} not connected")

    import uuid
    post_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    targets_with_status = [{**t, 'status': 'pending'} for t in targets]

    if scheduled_at:
        status = 'scheduled'
    else:
        status = 'publishing'

    item = {
        'PK': 'POST',
        'SK': post_id,
        'tenant_id': ctx.get('tenant_id', 'yallabalagan'),
        'status': status,
        'title': title,
        'description': description,
        'media': media,
        'targets': targets_with_status,
        'created_at': now,
        'created_by': ctx.get('user_id', '') if isinstance(ctx, dict) else getattr(ctx, 'user_id', ''),
    }
    if tags:
        item['tags'] = tags
    if cover:
        item['cover'] = cover
    if collaborators:
        item['collaborators'] = collaborators[:3]
    if scheduled_at:
        item['scheduled_at'] = scheduled_at

    db.put_social_post(item)

    if not scheduled_at:
        _invoke_social_poster(post_id)

    return success_response({'post_id': post_id, 'status': status}, status_code=201)


def social_upload_url(request_event: Dict) -> Dict:
    """GET /api/social/upload-url?filename=video.mp4&content_type=video/mp4 — pre-signed S3 PUT URL for video."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    qs = request_event.get('queryStringParameters') or {}
    filename = qs.get('filename', 'upload')
    content_type = qs.get('content_type', 'video/mp4')

    allowed_types = {
        'video/mp4', 'video/quicktime', 'video/webm',
        'image/jpeg', 'image/png', 'image/webp',
    }
    if content_type not in allowed_types:
        return error_response(400, f"Unsupported content type: {content_type}")

    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', os.path.basename(filename))
    s3_key = f"social-posts/{uuid.uuid4().hex[:8]}_{safe_name}"
    bucket_name = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')

    s3_client = boto3.client('s3', region_name='eu-north-1')
    upload_url = s3_client.generate_presigned_url(
        'put_object',
        Params={'Bucket': bucket_name, 'Key': s3_key, 'ContentType': content_type},
        ExpiresIn=600,
    )
    public_url = f"https://{bucket_name}.s3.eu-north-1.amazonaws.com/{s3_key}"

    return success_response({'upload_url': upload_url, 's3_key': s3_key, 'public_url': public_url})


def social_publish_post(request_event: Dict, post_id: str) -> Dict:
    """POST /api/social/posts/{id}/publish — trigger immediate publish of a draft."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    post = db.get_social_post(post_id)
    if not post:
        return error_response(404, 'Post not found')
    if post.get('status') not in ('draft', 'scheduled', 'failed'):
        return error_response(400, f"Cannot publish post with status={post.get('status')}")

    # Reset only failed targets to pending so poster retries them (published ones stay as-is)
    targets = [{**t, 'status': 'pending'} if t.get('status') == 'failed' else t for t in post.get('targets', [])]
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    db.update_social_post(post_id, {'status': 'publishing', 'publishing_since': now, 'targets': targets})
    _invoke_social_poster(post_id)

    return success_response({'post_id': post_id, 'status': 'publishing'})


def social_delete_post(request_event: Dict, post_id: str) -> Dict:
    """DELETE /api/social/posts/{id} — delete a draft or failed post."""
    try:
        ctx = authenticate(request_event)
    except AuthError as e:
        return error_response(e.status_code, str(e))
    if not is_admin(ctx, ctx.get('tenant_id', '')):
        return error_response(403, 'Access denied')

    post = db.get_social_post(post_id)
    if not post:
        return error_response(404, 'Post not found')
    if post.get('status') not in ('draft', 'failed', 'scheduled'):
        return error_response(400, f"Cannot delete post with status={post.get('status')}")

    db.delete_social_post(post_id)
    return success_response({'message': 'Deleted'})


def _invoke_social_poster(post_id: str):
    """Async-invoke the social-poster Lambda with the given post_id."""
    lambda_name = os.environ.get('SOCIAL_POSTER_LAMBDA', 'yallabalagan-social-poster')
    try:
        lambda_client = boto3.client('lambda', region_name='eu-north-1')
        lambda_client.invoke(
            FunctionName=lambda_name,
            InvocationType='Event',
            Payload=json.dumps({'post_id': post_id}),
        )
    except Exception as e:
        print(f"Warning: failed to invoke social-poster for post {post_id}: {e}")


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
