"""Tests for POST /api/events/quick endpoint (Task 26)."""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUICK_SECRET = 'test-quick-secret-xyz'


def _call(handler, body=None):
    event = {
        'httpMethod': 'POST',
        'path': '/api/events/quick',
        'headers': {},
        'queryStringParameters': None,
        'body': json.dumps(body) if body else None,
        'requestContext': {'http': {'method': 'POST', 'sourceIp': '127.0.0.1'}},
    }
    resp = handler.lambda_handler(event, None)
    resp['_body'] = json.loads(resp['body'])
    return resp


def _valid_body(**kwargs):
    defaults = {
        'secret': QUICK_SECRET,
        'title': 'Quick Event',
        'date': '2026-07-01T21:00:00Z',
        'external_url': 'https://external-tickets.com/show',
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture(autouse=True)
def set_quick_secret():
    os.environ['QUICK_POST_SECRET'] = QUICK_SECRET
    yield
    os.environ.pop('QUICK_POST_SECRET', None)


class TestQuickPost:
    def test_correct_secret_creates_event(self, phase4_handler):
        resp = _call(phase4_handler, _valid_body())
        assert resp['statusCode'] == 201
        assert 'event_id' in resp['_body']

    def test_event_is_persisted(self, phase4_handler, phase4_db_client):
        resp = _call(phase4_handler, _valid_body())
        event_id = resp['_body']['event_id']
        item = phase4_db_client.get_event(event_id)
        assert item is not None
        assert item['event_type'] == 'external'
        assert item['external_url'] == 'https://external-tickets.com/show'
        assert item['title'] == 'Quick Event'

    def test_wrong_secret_returns_401(self, phase4_handler):
        resp = _call(phase4_handler, _valid_body(secret='wrong-secret'))
        assert resp['statusCode'] == 401

    def test_missing_secret_returns_401(self, phase4_handler):
        body = _valid_body()
        del body['secret']
        resp = _call(phase4_handler, body)
        assert resp['statusCode'] == 401

    def test_missing_title_returns_400(self, phase4_handler):
        body = _valid_body()
        del body['title']
        resp = _call(phase4_handler, body)
        assert resp['statusCode'] == 400

    def test_missing_date_returns_400(self, phase4_handler):
        body = _valid_body()
        del body['date']
        resp = _call(phase4_handler, body)
        assert resp['statusCode'] == 400

    def test_missing_external_url_returns_400(self, phase4_handler):
        body = _valid_body()
        del body['external_url']
        resp = _call(phase4_handler, body)
        assert resp['statusCode'] == 400

    def test_unconfigured_secret_returns_503(self, phase4_handler):
        os.environ.pop('QUICK_POST_SECRET', None)
        resp = _call(phase4_handler, _valid_body())
        assert resp['statusCode'] == 503

    def test_with_optional_fields(self, phase4_handler, phase4_db_client):
        body = _valid_body(
            description='A great show',
            location_id='loc-special',
            performer_ids=['perf-1', 'perf-2'],
        )
        resp = _call(phase4_handler, body)
        assert resp['statusCode'] == 201
        item = phase4_db_client.get_event(resp['_body']['event_id'])
        assert item['performer_ids'] == ['perf-1', 'perf-2']
        assert item['location_id'] == 'loc-special'

    def test_does_not_require_auth_header(self, phase4_handler):
        # No X-API-Key, no Bearer token — secret in body is the only auth
        resp = _call(phase4_handler, _valid_body())
        assert resp['statusCode'] == 201
