"""
Unit tests for seat reservation API endpoints
"""
import pytest
import json
import time
from decimal import Decimal


def test_reserve_seats_success(db_client, sample_event, api_gateway_event, api_handler):
    """Test POST /api/orders/reserve-seats with valid data"""
    # Setup
    db_client.put_event(sample_event)

    

    # Reserve seats
    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0', '0-1'],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['message'] == 'Seats reserved successfully'
    assert body['event_id'] == 'test-event-1'
    assert body['seat_ids'] == ['0-0', '0-1']
    assert body['session_id'] == 'session-123'
    assert 'reserved_until' in body
    assert body['expires_in_seconds'] == 600

    # Verify reservations in DB
    reservations = db_client.get_seat_reservations('test-event-1')
    assert len(reservations) == 2
    seat_ids = [r['seat_id'] for r in reservations]
    assert '0-0' in seat_ids
    assert '0-1' in seat_ids


def test_reserve_seats_already_reserved(db_client, sample_event, api_gateway_event, api_handler):
    """Test reserving seats that are already reserved"""
    # Setup
    db_client.put_event(sample_event)

    # Reserve seat first
    ttl = int(time.time()) + 600
    db_client.reserve_seat('test-event-1', '0-0', 'session-456', ttl)

    

    # Try to reserve same seat
    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0', '0-1'],
            'session_id': 'session-789'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'already reserved' in body['error']
    assert '0-0' in body['error']

    # Verify rollback - 0-1 should not be reserved
    reservations = db_client.get_seat_reservations('test-event-1')
    seat_ids = [r['seat_id'] for r in reservations]
    assert '0-1' not in seat_ids  # Should be rolled back


def test_reserve_seats_already_purchased(db_client, sample_event, api_gateway_event, api_handler):
    """Test reserving seats that are already purchased"""
    # Setup event
    db_client.put_event(sample_event)

    # Create order with purchased seat
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

    

    # Try to reserve purchased seat
    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0'],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'already purchased' in body['error']


def test_reserve_seats_invalid_seat(db_client, sample_event, api_gateway_event, api_handler):
    """Test reserving seat that doesn't exist in venue"""
    # Setup
    db_client.put_event(sample_event)

    

    # Try to reserve non-existent seat
    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['99-99'],  # Non-existent seat
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'does not exist' in body['error']


def test_reserve_seats_missing_fields(db_client, sample_event, api_gateway_event, api_handler):
    """Test reserve seats with missing required fields"""
    db_client.put_event(sample_event)

    

    # Missing seat_ids
    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Missing required field' in body['error']


def test_reserve_seats_empty_list(db_client, sample_event, api_gateway_event, api_handler):
    """Test reserve seats with empty seat_ids list"""
    db_client.put_event(sample_event)

    

    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': [],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'non-empty array' in body['error']


def test_reserve_seats_event_not_found(db_client, api_gateway_event, api_handler):
    """Test reserving seats for non-existent event"""
    

    event = api_gateway_event(
        'POST',
        '/api/orders/reserve-seats',
        body={
            'event_id': 'non-existent',
            'seat_ids': ['0-0'],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'Event not found' in body['error']


def test_release_seats_success(db_client, sample_event, api_gateway_event, api_handler):
    """Test POST /api/orders/release-seats with valid data"""
    # Setup
    db_client.put_event(sample_event)

    # Reserve seats first
    ttl = int(time.time()) + 600
    db_client.reserve_seat('test-event-1', '0-0', 'session-123', ttl)
    db_client.reserve_seat('test-event-1', '0-1', 'session-123', ttl)

    

    # Release seats
    event = api_gateway_event(
        'POST',
        '/api/orders/release-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0', '0-1'],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['message'] == 'Seats released successfully'
    assert body['released_count'] == 2
    assert body['total_requested'] == 2

    # Verify seats are released
    reservations = db_client.get_seat_reservations('test-event-1')
    assert len(reservations) == 0


def test_release_seats_wrong_session(db_client, sample_event, api_gateway_event, api_handler):
    """Test releasing seats with wrong session_id"""
    # Setup
    db_client.put_event(sample_event)

    # Reserve seat with one session
    ttl = int(time.time()) + 600
    db_client.reserve_seat('test-event-1', '0-0', 'session-123', ttl)

    

    # Try to release with different session
    event = api_gateway_event(
        'POST',
        '/api/orders/release-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0'],
            'session_id': 'session-456'  # Wrong session
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['released_count'] == 0  # Should not release

    # Verify seat is still reserved
    reservations = db_client.get_seat_reservations('test-event-1')
    assert len(reservations) == 1


def test_release_seats_partial_release(db_client, sample_event, api_gateway_event, api_handler):
    """Test releasing some seats that belong to session and some that don't"""
    # Setup
    db_client.put_event(sample_event)

    ttl = int(time.time()) + 600
    db_client.reserve_seat('test-event-1', '0-0', 'session-123', ttl)
    db_client.reserve_seat('test-event-1', '0-1', 'session-456', ttl)  # Different session

    

    # Try to release both
    event = api_gateway_event(
        'POST',
        '/api/orders/release-seats',
        body={
            'event_id': 'test-event-1',
            'seat_ids': ['0-0', '0-1'],
            'session_id': 'session-123'
        }
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['released_count'] == 1  # Only 0-0 released
    assert body['total_requested'] == 2

    # Verify 0-1 still reserved
    reservations = db_client.get_seat_reservations('test-event-1')
    assert len(reservations) == 1
    assert reservations[0]['seat_id'] == '0-1'


def test_release_seats_missing_fields(db_client, api_gateway_event, api_handler):
    """Test release seats with missing required fields"""
    

    event = api_gateway_event(
        'POST',
        '/api/orders/release-seats',
        body={
            'event_id': 'test-event-1',
            # Missing seat_ids and session_id
        }
    )
    response = api_handler.lambda_handler(event, None)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Missing required field' in body['error']


def test_concurrent_reservation_race_condition(db_client, sample_event, api_handler):
    """Test race condition handling when two requests try to reserve same seat"""
    import threading

    # Setup
    db_client.put_event(sample_event)

    results = []

    def reserve_seat_thread(session_id):
        
        event = {
            'body': json.dumps({
                'event_id': 'test-event-1',
                'seat_ids': ['0-0'],
                'session_id': session_id
            })
        }
        result = api_handler.reserve_seats(event)
        results.append((session_id, result['statusCode']))

    # Create two threads trying to reserve same seat
    thread1 = threading.Thread(target=reserve_seat_thread, args=('session-1',))
    thread2 = threading.Thread(target=reserve_seat_thread, args=('session-2',))

    # Start threads simultaneously
    thread1.start()
    thread2.start()

    # Wait for completion
    thread1.join()
    thread2.join()

    # Assert: one should succeed (200), one should fail (409)
    status_codes = [r[1] for r in results]
    assert 200 in status_codes
    assert 409 in status_codes

    # Verify only one reservation exists
    reservations = db_client.get_seat_reservations('test-event-1')
    assert len(reservations) == 1
