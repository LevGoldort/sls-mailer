"""Tests for event_type/external_url/performer_ids extension of Event model (Task 25)."""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_KEY = 'test-admin-key'


def _call(handler, method, path, body=None, headers=None):
    event = {
        'httpMethod': method,
        'path': path,
        'headers': headers or {},
        'queryStringParameters': None,
        'body': json.dumps(body) if body else None,
        'requestContext': {'http': {'method': method, 'sourceIp': '127.0.0.1'}},
    }
    resp = handler.lambda_handler(event, None)
    resp['_body'] = json.loads(resp['body'])
    return resp


def _admin():
    return {'X-API-Key': ADMIN_KEY}


class TestEventModelExtension:
    def test_default_event_type_is_internal(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[],
        )
        assert e.event_type == 'internal'
        assert e.external_url is None
        assert e.performer_ids == []

    def test_to_dynamodb_item_always_writes_event_type(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[], event_type='internal',
        )
        item = e.to_dynamodb_item()
        assert item['event_type'] == 'internal'

    def test_to_dynamodb_item_external_url_present_when_set(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[], event_type='external',
            external_url='https://tickets.external.com',
        )
        item = e.to_dynamodb_item()
        assert item['external_url'] == 'https://tickets.external.com'

    def test_to_dynamodb_item_external_url_absent_when_none(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[], event_type='internal',
        )
        item = e.to_dynamodb_item()
        assert 'external_url' not in item

    def test_to_dynamodb_item_performer_ids_absent_when_empty(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[], performer_ids=[],
        )
        item = e.to_dynamodb_item()
        assert 'performer_ids' not in item

    def test_to_dynamodb_item_performer_ids_stored(self):
        from models.event import Event
        e = Event(
            event_id='e-1', title='T', description='D',
            date='2026-01-01T20:00:00Z', location_id='l-1',
            ticket_types=[], performer_ids=['p-1', 'p-2'],
        )
        item = e.to_dynamodb_item()
        assert item['performer_ids'] == ['p-1', 'p-2']

    def test_from_dynamodb_item_defaults_event_type_to_internal(self):
        from models.event import Event
        item = {
            'PK': 'EVENT#e-old', 'SK': 'METADATA',
            'event_id': 'e-old', 'title': 'Old Event', 'description': 'D',
            'date': '2025-01-01T20:00:00Z', 'location_id': 'l-1',
            'ticket_types': [], 'status': 'active',
        }
        e = Event.from_dynamodb_item(item)
        assert e.event_type == 'internal'
        assert e.external_url is None
        assert e.performer_ids == []


class TestCreateEventWithType:
    def _internal_body(self, **kwargs):
        defaults = {
            'title': 'Internal Show',
            'description': 'A show',
            'date': '2026-06-01T20:00:00Z',
            'location_id': 'loc-1',
            'ticket_types': [{'id': 'tt-1', 'name': 'General', 'price': 100, 'total': 50}],
            'event_type': 'internal',
        }
        defaults.update(kwargs)
        return defaults

    def _external_body(self, **kwargs):
        defaults = {
            'title': 'External Show',
            'description': 'A show',
            'date': '2026-06-01T20:00:00Z',
            'location_id': 'loc-1',
            'event_type': 'external',
            'external_url': 'https://tickets.elsewhere.com',
        }
        defaults.update(kwargs)
        return defaults

    def test_create_internal_event(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/events', self._internal_body(), _admin())
        assert resp['statusCode'] == 201
        assert resp['_body']['event']['event_type'] == 'internal'

    def test_create_external_event(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/events', self._external_body(), _admin())
        assert resp['statusCode'] == 201
        event = resp['_body']['event']
        assert event['event_type'] == 'external'
        assert event['external_url'] == 'https://tickets.elsewhere.com'

    def test_external_event_without_url_rejected(self, phase4_handler):
        body = self._external_body()
        del body['external_url']
        resp = _call(phase4_handler, 'POST', '/api/events', body, _admin())
        assert resp['statusCode'] == 400

    def test_internal_event_without_ticket_types_rejected(self, phase4_handler):
        body = self._internal_body()
        del body['ticket_types']
        resp = _call(phase4_handler, 'POST', '/api/events', body, _admin())
        assert resp['statusCode'] == 400

    def test_external_event_does_not_require_ticket_types(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/events', self._external_body(), _admin())
        assert resp['statusCode'] == 201

    def test_invalid_event_type_rejected(self, phase4_handler):
        body = self._internal_body(event_type='invalid')
        resp = _call(phase4_handler, 'POST', '/api/events', body, _admin())
        assert resp['statusCode'] == 400

    def test_create_event_with_performer_ids(self, phase4_handler):
        body = self._internal_body(performer_ids=['perf-1', 'perf-2'])
        resp = _call(phase4_handler, 'POST', '/api/events', body, _admin())
        assert resp['statusCode'] == 201
        assert resp['_body']['event']['performer_ids'] == ['perf-1', 'perf-2']


class TestUpdateEventType:
    def _seed_event(self, db, event_id='evt-1', event_type='internal'):
        from models.event import Event, TicketType
        e = Event(
            event_id=event_id,
            title='Test Event',
            description='Desc',
            date='2026-06-01T20:00:00Z',
            location_id='loc-1',
            ticket_types=[TicketType(id='tt-1', name='General', price=100, total=50, available=50)],
            event_type=event_type,
            external_url='https://x.com' if event_type == 'external' else None,
            status='active',
        )
        db.put_event(e.to_dynamodb_item())
        return e

    def test_update_adds_external_url(self, phase4_handler, phase4_db_client):
        self._seed_event(phase4_db_client, event_type='internal')
        resp = _call(phase4_handler, 'PUT', '/api/events/evt-1',
                     {'event_type': 'external', 'external_url': 'https://new.com'}, _admin())
        assert resp['statusCode'] == 200
        assert resp['_body']['event']['event_type'] == 'external'

    def test_update_switch_to_external_without_url_rejected(self, phase4_handler, phase4_db_client):
        self._seed_event(phase4_db_client, event_type='internal')
        resp = _call(phase4_handler, 'PUT', '/api/events/evt-1',
                     {'event_type': 'external'}, _admin())
        assert resp['statusCode'] == 400

    def test_update_performer_ids(self, phase4_handler, phase4_db_client):
        self._seed_event(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/events/evt-1',
                     {'performer_ids': ['perf-10', 'perf-20']}, _admin())
        assert resp['statusCode'] == 200
        assert resp['_body']['event']['performer_ids'] == ['perf-10', 'perf-20']
