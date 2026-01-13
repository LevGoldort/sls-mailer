"""
Unit tests for seating-related API endpoints
"""
import pytest
import json
from decimal import Decimal


def test_get_seating_map_seated_venue(db_client, sample_event, sample_location, api_gateway_event, api_handler):
    """Test GET /api/events/{event_id}/seating-map for seated venue"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Make request
    event = api_gateway_event('GET', '/api/events/test-event-1/seating-map')
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['event_id'] == 'test-event-1'
    assert body['venue_type'] == 'seated'
    assert body['seating_map'] is not None
    assert body['seating_map']['rows'] == 2
    assert body['seating_map']['seats_per_row'] == 5


def test_get_seating_map_standing_venue(db_client, sample_event, api_gateway_event, api_handler):
    """Test GET /api/events/{event_id}/seating-map for standing venue"""
    # Setup standing venue
    standing_location = {
        'PK': 'LOCATION#test-location-2',
        'SK': 'METADATA',
        'location_id': 'test-location-2',
        'name': 'Standing Venue',
        'slug': 'standing-venue',
        'address': {
            'street': 'Street 1',
            'city': 'Tel Aviv',
            'coordinates': {'lat': Decimal('32.0'), 'lng': Decimal('34.0')}
        },
        'capacity': 200,
        'description': 'Standing venue',
        'short_description': 'Standing',
        'media': {'photos': [], 'videos': []},
        'parkings': [],
        'amenities': [],
        'contact': {},
        'venue_config': {
            'venue_type': 'standing'
        }
    }

    sample_event['location_id'] = 'test-location-2'
    db_client.put_event(sample_event)
    db_client.put_location(standing_location)

    

    # Make request
    event = api_gateway_event('GET', '/api/events/test-event-1/seating-map')
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['venue_type'] == 'standing'
    assert body['seating_map'] is None


def test_get_seating_map_event_not_found(db_client, api_gateway_event, api_handler):
    """Test GET /api/events/{event_id}/seating-map with non-existent event"""
    

    event = api_gateway_event('GET', '/api/events/non-existent/seating-map')
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'error' in body


def test_get_seat_availability(db_client, sample_event, api_gateway_event, api_handler):
    """Test GET /api/events/{event_id}/seat-availability"""
    # Setup
    db_client.put_event(sample_event)

    

    # Make request
    event = api_gateway_event('GET', '/api/events/test-event-1/seat-availability')
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['event_id'] == 'test-event-1'
    assert 'seat_allocation' in body
    assert 'purchased_seats' in body
    assert 'reserved_seats' in body
    assert body['seat_allocation'] == sample_event['seat_allocation']
    assert isinstance(body['purchased_seats'], list)
    assert isinstance(body['reserved_seats'], list)


def test_get_seat_availability_with_reservations(db_client, sample_event, api_gateway_event, api_handler):
    """Test seat availability with active reservations"""
    import time

    # Setup event
    db_client.put_event(sample_event)

    # Add reservation
    ttl = int(time.time()) + 600
    db_client.reserve_seat('test-event-1', '0-0', 'session-123', ttl)

    

    # Make request
    event = api_gateway_event('GET', '/api/events/test-event-1/seat-availability')
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert '0-0' in body['reserved_seats']
    assert len(body['reserved_seats_details']) == 1
    assert body['reserved_seats_details'][0]['seat_id'] == '0-0'
    assert body['reserved_seats_details'][0]['session_id'] == 'session-123'


def test_save_seat_allocation_success(db_client, sample_event, admin_api_key, api_gateway_event, api_handler):
    """Test POST /api/events/{event_id}/seat-allocation with valid data"""
    # Setup
    db_client.put_event(sample_event)

    

    # New seat allocation
    new_allocation = {
        '0-0': 'tt-regular',
        '0-1': 'tt-regular',
        '0-2': 'tt-regular',
        '0-3': 'tt-vip',
        '0-4': 'tt-vip'
    }

    # Make request with admin auth
    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body={'seat_allocation': new_allocation},
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['message'] == 'Seat allocation saved successfully'
    assert body['seat_allocation'] == new_allocation

    # Verify saved in DB
    saved_event = db_client.get_event('test-event-1')
    assert saved_event['seat_allocation'] == new_allocation


def test_save_seat_allocation_unauthorized(db_client, sample_event, api_gateway_event, api_handler):
    """Test POST /api/events/{event_id}/seat-allocation without admin auth"""
    db_client.put_event(sample_event)

    

    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body={'seat_allocation': {'0-0': 'tt-regular'}},
        headers={}
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']


def test_save_seat_allocation_exceeds_total(db_client, sample_event, admin_api_key, api_gateway_event, api_handler):
    """Test seat allocation that exceeds ticket type total"""
    db_client.put_event(sample_event)

    

    # Try to allocate more seats than available for regular (total: 50)
    oversized_allocation = {f'0-{i}': 'tt-regular' for i in range(60)}

    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body={'seat_allocation': oversized_allocation},
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'exceeds total' in body['error']


def test_save_seat_allocation_cannot_modify_sold_seat(db_client, sample_event, admin_api_key, api_gateway_event, api_handler):
    """Test that sold seats cannot be reallocated to different ticket type"""
    # Setup event
    db_client.put_event(sample_event)

    # Create order with purchased seats
    order = {
        'PK': 'ORDER#order-1',
        'SK': 'METADATA',
        'order_id': 'order-1',
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+1234567890'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'type_name': 'Regular',
                'quantity': 1,
                'price_per_ticket': Decimal('100'),
                'purchased_seats': ['0-0']
            }
        ],
        'total_amount': Decimal('100'),
        'currency': 'ILS',
        'payment': {'status': 'completed'},
        'qr_codes': [],
        'notifications': {},
        'customer_email': 'test@example.com'
    }
    db_client.put_order(order)

    

    # Try to change seat 0-0 from tt-regular to tt-vip
    new_allocation = dict(sample_event['seat_allocation'])
    new_allocation['0-0'] = 'tt-vip'

    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body={'seat_allocation': new_allocation},
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'already sold' in body['error']
    assert '0-0' in body['error']


def test_save_seat_allocation_missing_data(db_client, sample_event, admin_api_key, api_gateway_event, api_handler):
    """Test POST /api/events/{event_id}/seat-allocation with missing data"""
    db_client.put_event(sample_event)

    

    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body={},  # Empty body
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'seat_allocation is required' in body['error']
