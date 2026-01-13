"""
Pytest fixtures for ticket service tests
"""
import pytest
import os
import sys
import json
import importlib.util
from decimal import Decimal
from moto import mock_aws
import boto3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def import_api_handler():
    """Import api-handler.py module (with hyphen in name)"""
    module_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'lambdas',
        'api-handler.py'
    )
    spec = importlib.util.spec_from_file_location("api_handler", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['api_handler'] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_REGION'] = 'eu-north-1'
    # Set admin key for auth tests
    os.environ['ADMIN_API_KEYS'] = 'test-admin-key'


@pytest.fixture
def dynamodb_mock(aws_credentials):
    """Create mocked DynamoDB service"""
    with mock_aws():
        yield boto3.resource('dynamodb', region_name='eu-north-1')


@pytest.fixture
def events_table(dynamodb_mock):
    """Create mocked events table"""
    table = dynamodb_mock.create_table(
        TableName='yallabalagan-events-test',
        KeySchema=[
            {'AttributeName': 'PK', 'KeyType': 'HASH'},
            {'AttributeName': 'SK', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'PK', 'AttributeType': 'S'},
            {'AttributeName': 'SK', 'AttributeType': 'S'},
            {'AttributeName': 'GSI1PK', 'AttributeType': 'S'},
            {'AttributeName': 'GSI1SK', 'AttributeType': 'S'},
            {'AttributeName': 'slug', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST',
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'GSI1',
                'KeySchema': [
                    {'AttributeName': 'GSI1PK', 'KeyType': 'HASH'},
                    {'AttributeName': 'GSI1SK', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            },
            {
                'IndexName': 'SlugIndex',
                'KeySchema': [
                    {'AttributeName': 'slug', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ]
    )
    return table


@pytest.fixture
def locations_table(dynamodb_mock):
    """Create mocked locations table"""
    table = dynamodb_mock.create_table(
        TableName='yallabalagan-locations-test',
        KeySchema=[
            {'AttributeName': 'PK', 'KeyType': 'HASH'},
            {'AttributeName': 'SK', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'PK', 'AttributeType': 'S'},
            {'AttributeName': 'SK', 'AttributeType': 'S'},
            {'AttributeName': 'slug', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST',
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'SlugIndex',
                'KeySchema': [
                    {'AttributeName': 'slug', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ]
    )
    return table


@pytest.fixture
def orders_table(dynamodb_mock):
    """Create mocked orders table"""
    table = dynamodb_mock.create_table(
        TableName='yallabalagan-orders-test',
        KeySchema=[
            {'AttributeName': 'PK', 'KeyType': 'HASH'},
            {'AttributeName': 'SK', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'PK', 'AttributeType': 'S'},
            {'AttributeName': 'SK', 'AttributeType': 'S'},
            {'AttributeName': 'event_id', 'AttributeType': 'S'},
            {'AttributeName': 'customer_email', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST',
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'EventIndex',
                'KeySchema': [
                    {'AttributeName': 'event_id', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            },
            {
                'IndexName': 'EmailIndex',
                'KeySchema': [
                    {'AttributeName': 'customer_email', 'KeyType': 'HASH'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ]
    )
    return table


@pytest.fixture
def seat_reservations_table(dynamodb_mock):
    """Create mocked seat reservations table"""
    table = dynamodb_mock.create_table(
        TableName='yallabalagan-seat-reservations-test',
        KeySchema=[
            {'AttributeName': 'event_id', 'KeyType': 'HASH'},
            {'AttributeName': 'seat_id', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'event_id', 'AttributeType': 'S'},
            {'AttributeName': 'seat_id', 'AttributeType': 'S'},
            {'AttributeName': 'expires_at', 'AttributeType': 'N'}
        ],
        BillingMode='PAY_PER_REQUEST',
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'ExpirationIndex',
                'KeySchema': [
                    {'AttributeName': 'event_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'expires_at', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ]
    )
    return table


@pytest.fixture
def db_client(events_table, locations_table, orders_table, seat_reservations_table):
    """Create DynamoDB client with test tables"""
    os.environ['EVENTS_TABLE'] = 'yallabalagan-events-test'
    os.environ['LOCATIONS_TABLE'] = 'yallabalagan-locations-test'
    os.environ['ORDERS_TABLE'] = 'yallabalagan-orders-test'
    os.environ['SEAT_RESERVATIONS_TABLE'] = 'yallabalagan-seat-reservations-test'

    from utils.dynamodb import DynamoDBClient
    return DynamoDBClient()


@pytest.fixture
def sample_event():
    """Sample event data for testing"""
    return {
        'PK': 'EVENT#test-event-1',
        'SK': 'METADATA',
        'event_id': 'test-event-1',
        'title': 'Test Event',
        'description': 'Test Description',
        'date': '2025-12-31T20:00:00Z',
        'location_id': 'test-location-1',
        'ticket_types': [
            {
                'id': 'tt-regular',
                'name': 'Regular',
                'price': Decimal('100'),
                'total': 50,
                'available': 50
            },
            {
                'id': 'tt-vip',
                'name': 'VIP',
                'price': Decimal('200'),
                'total': 20,
                'available': 20
            }
        ],
        'currency': 'ILS',
        'status': 'active',
        'seat_allocation': {
            '0-0': 'tt-regular',
            '0-1': 'tt-regular',
            '0-2': 'tt-vip',
            '0-3': 'tt-vip'
        },
        'GSI1PK': 'EVENT',
        'GSI1SK': '2025-12-31T20:00:00Z'
    }


@pytest.fixture
def sample_location():
    """Sample location data for testing"""
    return {
        'PK': 'LOCATION#test-location-1',
        'SK': 'METADATA',
        'location_id': 'test-location-1',
        'name': 'Test Venue',
        'slug': 'test-venue',
        'address': {
            'street': 'Test Street 123',
            'city': 'Tel Aviv',
            'coordinates': {'lat': Decimal('32.0853'), 'lng': Decimal('34.7818')}
        },
        'capacity': 100,
        'description': 'Test venue description',
        'short_description': 'Test venue',
        'media': {'photos': [], 'videos': []},
        'parkings': [],
        'amenities': [],
        'contact': {},
        'venue_config': {
            'venue_type': 'seated',
            'seating_map': {
                'rows': 2,
                'seats_per_row': 5,
                'disabled_seats': [],
                'custom_numbers': {},
                'numbering_direction': 'left-to-right'
            }
        }
    }


@pytest.fixture
def admin_api_key():
    """Mock admin API key - ENV already set in aws_credentials"""
    return 'test-admin-key'


@pytest.fixture
def api_gateway_event():
    """Base API Gateway event structure"""
    def _make_event(method='GET', path='/', body=None, headers=None):
        event = {
            'httpMethod': method,
            'path': path,
            'headers': headers or {},
            'queryStringParameters': None,
            'body': json.dumps(body) if body else None,
            'requestContext': {
                'http': {
                    'method': method,
                    'sourceIp': '127.0.0.1'
                }
            }
        }
        return event
    return _make_event


@pytest.fixture
def api_handler(db_client):
    """Import and return api-handler module with mocked db and auth"""
    # Import module
    module = import_api_handler()

    # Replace the global db client with our mocked one
    module.db = db_client

    # Create a simple mock authenticator class
    class MockAuthenticator:
        def extract_api_key(self, event):
            """Extract API key from event"""
            headers = event.get('headers', {})
            auth_header = headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                return auth_header[7:]
            return headers.get('X-API-Key', '')

        def verify_admin_key(self, api_key):
            """Always accept test-admin-key"""
            return api_key == 'test-admin-key'

    # Replace get_admin_authenticator
    def mocked_get_admin_authenticator():
        return MockAuthenticator()

    module.get_admin_authenticator = mocked_get_admin_authenticator

    return module
