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

# Add parent directory to path для импорта models и utils
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Event, Location, Order, Customer, OrderTicket, TicketType, Coupon, Address, Coordinates, Parking, Media, Contact
from utils.dynamodb import DynamoDBClient
from datetime import datetime


# Helper для конвертации Decimal в int/float
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


# Инициализация DynamoDB клиента
db = DynamoDBClient()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler для API Gateway requests
    """
    print(f"Received event: {json.dumps(event)}")

    # Извлекаем метод и путь
    http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method'))
    path = event.get('path', event.get('rawPath', ''))

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
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

    # GET /api/events/{id} - детали события
    if method == 'GET' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return get_event(event_id)

    # POST /api/events - создать событие (admin)
    if method == 'POST' and path == '/api/events':
        return create_event(event)

    # PUT /api/events/{id} - обновить событие (admin)
    if method == 'PUT' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return update_event(event_id, event)

    # DELETE /api/events/{id} - удалить событие (admin)
    if method == 'DELETE' and path.startswith('/api/events/'):
        event_id = path.split('/')[-1]
        return delete_event(event_id)

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
                'images': evt.images
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


def create_event(request_event: Dict) -> Dict:
    """POST /api/events"""
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
            images=body.get('images', [])
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
    """PUT /api/events/{id}"""
    try:
        # Проверяем что событие существует
        item = db.get_event(event_id)
        if not item:
            return error_response(404, "Event not found")

        body = json.loads(request_event.get('body', '{}'))

        # Получаем текущее событие
        evt = Event.from_dynamodb_item(item)

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


def delete_event(event_id: str) -> Dict:
    """DELETE /api/events/{id}"""
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
        return delete_location(location_id)

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
    """POST /api/locations"""
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
    """PUT /api/locations/{id}"""
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


def delete_location(location_id: str) -> Dict:
    """DELETE /api/locations/{id}"""
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
            return list_orders_by_event(event_id)
        else:
            return list_all_orders()

    # POST /api/orders - создать заказ
    if method == 'POST' and path == '/api/orders':
        return create_order(event)

    # GET /api/orders/{id} - детали заказа
    if method == 'GET' and path.startswith('/api/orders/'):
        order_id = path.split('/')[-1]
        return get_order(order_id)

    return error_response(404, "Orders endpoint not found")


def list_orders_by_event(event_id: str) -> Dict:
    """GET /api/orders?event_id=xxx - список заказов для события"""
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


def list_all_orders() -> Dict:
    """GET /api/orders - список всех заказов"""
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

        # Создаем заказ
        customer = Customer(**body['customer'])
        order = Order(
            order_id=Order.generate_id(),
            event_id=event_id,
            customer=customer,
            tickets=order_tickets,
            total_amount=sum(t.get_total() for t in order_tickets)
        )

        # Генерируем QR коды
        order.generate_qr_codes()

        # Уменьшаем количество доступных билетов
        for ticket in order_tickets:
            evt.decrease_available(ticket.type_id, ticket.quantity)

        # Сохраняем
        db.put_order(order.to_dynamodb_item())
        db.put_event(evt.to_dynamodb_item())

        return success_response({
            'message': 'Order created successfully',
            'order_id': order.order_id,
            'order': order.to_dynamodb_item(),
            'payment_url': f"https://allpay.example.com/pay/{order.order_id}"  # TODO: Real All-Pay URL
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


# ===== Coupons Handlers =====
def handle_coupons(event: Dict, method: str, path: str) -> Dict:
    """Обрабатывает запросы к /api/coupons"""

    # GET /api/coupons - список купонов
    if method == 'GET' and path == '/api/coupons':
        query_params = event.get('queryStringParameters', {}) or {}
        status = query_params.get('status')
        return list_coupons(status)

    # GET /api/coupons/{code} - детали купона
    if method == 'GET' and path.startswith('/api/coupons/'):
        coupon_code = path.split('/')[-1]
        return get_coupon_details(coupon_code)

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
        return delete_coupon_handler(coupon_code)

    return error_response(404, "Coupons endpoint not found")


def list_coupons(status: str = None) -> Dict:
    """GET /api/coupons"""
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


def get_coupon_details(coupon_code: str) -> Dict:
    """GET /api/coupons/{code}"""
    item = db.get_coupon(coupon_code)

    if not item:
        return error_response(404, "Coupon not found")

    coupon = Coupon.from_dynamodb_item(item)

    return success_response({
        'coupon': coupon.to_dict()
    })


def create_coupon(request_event: Dict) -> Dict:
    """POST /api/coupons"""
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

        # Получаем купон
        item = db.get_coupon(coupon_code)
        if not item:
            return error_response(404, "Coupon not found")

        coupon = Coupon.from_dynamodb_item(item)

        # Валидируем
        is_valid, error_msg = coupon.is_valid(event_id)
        if not is_valid:
            return error_response(400, error_msg)

        # Рассчитываем скидку
        discount_amount = coupon.calculate_discount(amount)
        final_amount = coupon.apply_discount(amount)

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
    """PUT /api/coupons/{code}"""
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


def delete_coupon_handler(coupon_code: str) -> Dict:
    """DELETE /api/coupons/{code}"""
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
    """Handles image upload to S3 bucket"""
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


def error_response(status_code: int, message: str) -> Dict:
    """Формирует ответ об ошибке"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': message
        }, ensure_ascii=False, cls=DecimalEncoder)
    }


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
