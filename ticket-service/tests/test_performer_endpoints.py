"""Integration tests for /api/performers endpoints (Task 22)."""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_KEY = 'test-admin-key'


def _call(handler, method, path, body=None, headers=None, query=None):
    event = {
        'httpMethod': method,
        'path': path,
        'headers': headers or {},
        'queryStringParameters': query,
        'body': json.dumps(body) if body else None,
        'requestContext': {'http': {'method': method, 'sourceIp': '127.0.0.1'}},
    }
    resp = handler.lambda_handler(event, None)
    resp['_body'] = json.loads(resp['body'])
    return resp


def _admin_headers():
    return {'X-API-Key': ADMIN_KEY}


def _seed_performer(db, **kwargs):
    from models.performer import Performer, SocialLinks
    defaults = dict(
        performer_id='perf-seed-1',
        tenant_id='yallabalagan',
        name='DJ Seed',
        slug='dj-seed',
        bio='Bio',
        role='DJ',
        photo_url='https://cdn.example.com/photo.jpg',
        status='active',
    )
    defaults.update(kwargs)
    p = Performer(**defaults)
    db.put_performer(p.to_dynamodb_item())
    return p


class TestListPerformers:
    def test_returns_active_performers(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/performers')
        assert resp['statusCode'] == 200
        body = resp['_body']
        assert body['count'] == 1
        assert body['performers'][0]['name'] == 'DJ Seed'

    def test_inactive_excluded(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client, performer_id='perf-inactive', slug='inactive-dj', status='inactive')
        resp = _call(phase4_handler, 'GET', '/api/performers')
        assert resp['statusCode'] == 200
        assert resp['_body']['count'] == 0

    def test_empty_list(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/performers')
        assert resp['statusCode'] == 200
        assert resp['_body']['performers'] == []


class TestGetPerformer:
    def test_get_by_id(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/performers/perf-seed-1')
        assert resp['statusCode'] == 200
        assert resp['_body']['performer']['performer_id'] == 'perf-seed-1'

    def test_get_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/performers/no-such-id')
        assert resp['statusCode'] == 404

    def test_get_by_slug(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/performers/slug/dj-seed')
        assert resp['statusCode'] == 200
        assert resp['_body']['performer']['slug'] == 'dj-seed'

    def test_get_by_slug_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/performers/slug/no-such-slug')
        assert resp['statusCode'] == 404


class TestCreatePerformer:
    def _body(self, **kwargs):
        defaults = {
            'name': 'DJ New',
            'slug': 'dj-new',
            'bio': 'Fresh bio',
            'role': 'DJ',
            'photo_url': 'https://cdn.example.com/new.jpg',
        }
        defaults.update(kwargs)
        return defaults

    def test_create_success(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/performers', self._body(), _admin_headers())
        assert resp['statusCode'] == 201
        body = resp['_body']
        assert body['performer']['name'] == 'DJ New'
        assert body['performer']['slug'] == 'dj-new'
        assert 'performer_id' in body['performer']

    def test_create_requires_auth(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/performers', self._body())
        assert resp['statusCode'] == 401

    def test_create_missing_required_field(self, phase4_handler):
        body = self._body()
        del body['slug']
        resp = _call(phase4_handler, 'POST', '/api/performers', body, _admin_headers())
        assert resp['statusCode'] == 400

    def test_create_duplicate_slug(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/performers',
                     self._body(slug='dj-seed'), _admin_headers())
        assert resp['statusCode'] == 409

    def test_create_with_social_links(self, phase4_handler):
        body = self._body(social={'instagram': '@new_dj', 'telegram': '@newdj'})
        resp = _call(phase4_handler, 'POST', '/api/performers', body, _admin_headers())
        assert resp['statusCode'] == 201
        performer = resp['_body']['performer']
        assert performer['social']['instagram'] == '@new_dj'


class TestUpdatePerformer:
    def test_update_name(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/performers/perf-seed-1',
                     {'name': 'DJ Updated'}, _admin_headers())
        assert resp['statusCode'] == 200
        assert resp['_body']['performer']['name'] == 'DJ Updated'

    def test_update_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'PUT', '/api/performers/no-such',
                     {'name': 'X'}, _admin_headers())
        assert resp['statusCode'] == 404

    def test_update_requires_auth(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/performers/perf-seed-1', {'name': 'X'})
        assert resp['statusCode'] == 401

    def test_update_slug_conflict(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        _seed_performer(phase4_db_client, performer_id='perf-seed-2', slug='dj-other')
        resp = _call(phase4_handler, 'PUT', '/api/performers/perf-seed-2',
                     {'slug': 'dj-seed'}, _admin_headers())
        assert resp['statusCode'] == 409

    def test_update_same_slug_ok(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/performers/perf-seed-1',
                     {'slug': 'dj-seed'}, _admin_headers())
        assert resp['statusCode'] == 200


class TestDeletePerformer:
    def test_soft_delete_sets_inactive(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'DELETE', '/api/performers/perf-seed-1',
                     headers=_admin_headers())
        assert resp['statusCode'] == 200
        assert resp['_body']['message'] == 'Performer deactivated'

        # Verify performer is now inactive and excluded from list
        item = phase4_db_client.get_performer('perf-seed-1')
        assert item['status'] == 'inactive'
        list_resp = _call(phase4_handler, 'GET', '/api/performers')
        assert list_resp['_body']['count'] == 0

    def test_delete_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'DELETE', '/api/performers/no-such',
                     headers=_admin_headers())
        assert resp['statusCode'] == 404

    def test_delete_requires_auth(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'DELETE', '/api/performers/perf-seed-1')
        assert resp['statusCode'] == 401
