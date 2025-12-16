"""
Unit tests for seated venue order processing
Tests order creation, availability calculation, and refunds for seated events
"""
import pytest
import json
from decimal import Decimal


def test_create_order_with_seats(db_client, sample_event, sample_location, api_gateway_event, api_handler):
    """Test creating an order with purchased_seats for seated venue"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Create order with seats
    order_data = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+972501234567'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 2,
                'purchased_seats': ['0-0', '0-1']
            }
        ]
    }

    event = api_gateway_event('POST', '/api/orders', body=order_data)
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] in [200, 201]  # Either OK or Created
    body = json.loads(response['body'])
    assert 'order_id' in body
    assert body['message'] == 'Order created successfully'


def test_create_order_seat_count_mismatch(db_client, sample_event, sample_location, api_gateway_event, api_handler):
    """Test that order creation fails if seat count doesn't match quantity"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Create order with mismatched seat count
    order_data = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+972501234567'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 2,
                'purchased_seats': ['0-0']  # Only 1 seat but quantity is 2
            }
        ]
    }

    event = api_gateway_event('POST', '/api/orders', body=order_data)
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'must match quantity' in body['error']


def test_create_order_invalid_seat_type(db_client, sample_event, sample_location, api_gateway_event, api_handler):
    """Test that order creation fails if seat is allocated to wrong ticket type"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Try to buy VIP ticket with regular seat
    order_data = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+972501234567'
        },
        'tickets': [
            {
                'type_id': 'tt-vip',
                'quantity': 1,
                'purchased_seats': ['0-0']  # This seat is allocated to tt-regular
            }
        ]
    }

    event = api_gateway_event('POST', '/api/orders', body=order_data)
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'is allocated to ticket type' in body['error']


def test_create_order_seat_already_sold(db_client, sample_event, sample_location, api_gateway_event, api_handler):
    """Test that order creation fails if seat is already sold"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Create first order
    order_data_1 = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'First User',
            'email': 'first@example.com',
            'phone': '+972501111111'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 1,
                'purchased_seats': ['0-0']
            }
        ]
    }

    event1 = api_gateway_event('POST', '/api/orders', body=order_data_1)
    response1 = api_handler.lambda_handler(event1, None)
    assert response1['statusCode'] in [200, 201]  # Either OK or Created

    # Try to create second order with same seat
    order_data_2 = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Second User',
            'email': 'second@example.com',
            'phone': '+972502222222'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 1,
                'purchased_seats': ['0-0']  # Same seat as first order
            }
        ]
    }

    event2 = api_gateway_event('POST', '/api/orders', body=order_data_2)
    response2 = api_handler.lambda_handler(event2, None)

    # Assert
    assert response2['statusCode'] == 400
    body = json.loads(response2['body'])
    assert 'already reserved' in body['error']


def test_save_seat_allocation_updates_availability(db_client, sample_event, admin_api_key, api_gateway_event, api_handler):
    """Test that saving seat allocation updates ticket availability"""
    # Setup event with initial allocation
    db_client.put_event(sample_event)

    # Create new allocation with fewer seats
    new_allocation = {
        'seat_allocation': {
            '0-0': 'tt-regular',  # Only 1 regular seat now
            '0-1': 'tt-vip',
            '0-2': 'tt-vip'  # 2 VIP seats
        }
    }

    event = api_gateway_event(
        'POST',
        '/api/events/test-event-1/seat-allocation',
        body=new_allocation,
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 200

    # Check that ticket availability was updated
    updated_event = db_client.get_event('test-event-1')
    ticket_types = {tt['id']: tt for tt in updated_event['ticket_types']}

    # Regular: was 50, now only 1 seat allocated -> available should be 1
    assert ticket_types['tt-regular']['available'] == 1

    # VIP: was 20, now only 2 seats allocated -> available should be 2
    assert ticket_types['tt-vip']['available'] == 2


def test_create_event_with_seat_allocation_sets_availability(db_client, sample_location, admin_api_key, api_gateway_event, api_handler):
    """Test that creating event with seat_allocation sets correct availability"""
    # Setup location
    db_client.put_location(sample_location)

    # Create event with seat allocation
    event_data = {
        'title': 'New Seated Event',
        'description': 'Test event',
        'date': '2025-12-31T20:00:00Z',
        'location_id': 'test-location-1',
        'ticket_types': [
            {
                'id': 'tt-regular',
                'name': 'Regular',
                'price': 100,
                'total': 50  # Total capacity
            },
            {
                'id': 'tt-vip',
                'name': 'VIP',
                'price': 200,
                'total': 20  # Total capacity
            }
        ],
        'seat_allocation': {
            '0-0': 'tt-regular',
            '0-1': 'tt-regular',
            '0-2': 'tt-regular',  # 3 regular seats allocated
            '0-3': 'tt-vip'  # 1 VIP seat allocated
        }
    }

    event = api_gateway_event(
        'POST',
        '/api/events',
        body=event_data,
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response = api_handler.lambda_handler(event, None)

    # Assert
    assert response['statusCode'] == 201
    body = json.loads(response['body'])

    # Check that availability matches allocated seats, not total
    ticket_types = {tt['id']: tt for tt in body['event']['ticket_types']}
    assert ticket_types['tt-regular']['available'] == 3  # Not 50!
    assert ticket_types['tt-vip']['available'] == 1  # Not 20!


def test_refund_releases_seats(db_client, sample_event, sample_location, admin_api_key, api_gateway_event, api_handler):
    """Test that refunding an order releases the seats"""
    # Setup
    db_client.put_event(sample_event)
    db_client.put_location(sample_location)

    # Create order
    order_data = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '+972501234567'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 2,
                'purchased_seats': ['0-0', '0-1']
            }
        ]
    }

    event1 = api_gateway_event('POST', '/api/orders', body=order_data)
    response1 = api_handler.lambda_handler(event1, None)
    assert response1['statusCode'] in [200, 201]  # Either OK or Created
    order_id = json.loads(response1['body'])['order_id']

    # Mark order as paid (simulate webhook)
    db_client.update_order_payment_status(order_id, 'completed', 'txn-123')

    # Get event and decrease available (simulate webhook finalization)
    evt_data = db_client.get_event('test-event-1')
    from models.event import Event
    evt = Event.from_dynamodb_item(evt_data)
    evt.decrease_available('tt-regular', 2)
    db_client.put_event(evt.to_dynamodb_item())

    # Get initial available count
    evt_before = db_client.get_event('test-event-1')
    available_before = next(tt['available'] for tt in evt_before['ticket_types'] if tt['id'] == 'tt-regular')

    # Process refund
    event2 = api_gateway_event(
        'POST',
        f'/api/orders/{order_id}/refund',
        headers={'Authorization': f'Bearer {admin_api_key}'}
    )
    response2 = api_handler.lambda_handler(event2, None)
    assert response2['statusCode'] == 200

    # Check that seats were released (available increased)
    evt_after = db_client.get_event('test-event-1')
    available_after = next(tt['available'] for tt in evt_after['ticket_types'] if tt['id'] == 'tt-regular')

    assert available_after == available_before + 2

    # Check that refunded order seats can now be purchased
    order_data_2 = {
        'event_id': 'test-event-1',
        'customer': {
            'name': 'Second User',
            'email': 'second@example.com',
            'phone': '+972502222222'
        },
        'tickets': [
            {
                'type_id': 'tt-regular',
                'quantity': 1,
                'purchased_seats': ['0-0']  # Same seat from refunded order
            }
        ]
    }

    event3 = api_gateway_event('POST', '/api/orders', body=order_data_2)
    response3 = api_handler.lambda_handler(event3, None)

    # Should succeed now since the seat was released
    assert response3['statusCode'] in [200, 201]  # Either OK or Created
