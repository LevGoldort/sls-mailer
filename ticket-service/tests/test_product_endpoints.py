"""Integration tests for /api/products endpoints (Task 23)."""
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


def _seed_performer(db, performer_id='perf-1', slug='perf-one'):
    from models.performer import Performer
    p = Performer(
        performer_id=performer_id,
        tenant_id='yallabalagan',
        name='Test Performer',
        slug=slug,
        bio='Bio',
        role='DJ',
        photo_url='https://cdn.example.com/p.jpg',
        status='active',
    )
    db.put_performer(p.to_dynamodb_item())
    return p


def _seed_product(db, **kwargs):
    from models.product import Product
    defaults = dict(
        product_id='prod-seed-1',
        tenant_id='yallabalagan',
        performer_id='perf-1',
        name='Test Shirt',
        slug='test-shirt',
        short_description='A shirt',
        price_ils=100.0,
        photo_url='https://cdn.example.com/shirt.jpg',
        status='active',
    )
    defaults.update(kwargs)
    p = Product(**defaults)
    db.put_product(p.to_dynamodb_item())
    return p


class TestListProducts:
    def test_returns_active_products(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/products')
        assert resp['statusCode'] == 200
        assert resp['_body']['count'] == 1

    def test_filter_by_performer_id(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, product_id='prod-p1', slug='prod-p1', performer_id='perf-1')
        _seed_product(phase4_db_client, product_id='prod-p2', slug='prod-p2', performer_id='perf-2')
        resp = _call(phase4_handler, 'GET', '/api/products', query={'performer_id': 'perf-1'})
        assert resp['statusCode'] == 200
        products = resp['_body']['products']
        assert len(products) == 1
        assert products[0]['performer_id'] == 'perf-1'

    def test_filter_by_performer_excludes_inactive(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, product_id='prod-a', slug='prod-a', status='active')
        _seed_product(phase4_db_client, product_id='prod-i', slug='prod-i', status='inactive')
        resp = _call(phase4_handler, 'GET', '/api/products', query={'performer_id': 'perf-1'})
        products = resp['_body']['products']
        assert all(p['status'] == 'active' for p in products)

    def test_empty_list(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/products')
        assert resp['statusCode'] == 200
        assert resp['_body']['products'] == []


class TestGetProduct:
    def test_get_by_id(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/products/prod-seed-1')
        assert resp['statusCode'] == 200
        assert resp['_body']['product']['product_id'] == 'prod-seed-1'

    def test_get_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/products/no-such')
        assert resp['statusCode'] == 404

    def test_get_by_slug(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'GET', '/api/products/slug/test-shirt')
        assert resp['statusCode'] == 200
        assert resp['_body']['product']['slug'] == 'test-shirt'

    def test_get_by_slug_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'GET', '/api/products/slug/no-slug')
        assert resp['statusCode'] == 404


class TestCreateProduct:
    def _body(self, **kwargs):
        defaults = {
            'performer_id': 'perf-1',
            'name': 'New Shirt',
            'slug': 'new-shirt',
            'short_description': 'A new shirt',
            'price_ils': 150,
            'photo_url': 'https://cdn.example.com/new.jpg',
        }
        defaults.update(kwargs)
        return defaults

    def test_create_success(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/products', self._body(), _admin_headers())
        assert resp['statusCode'] == 201
        product = resp['_body']['product']
        assert product['name'] == 'New Shirt'
        assert product['performer_id'] == 'perf-1'
        assert 'product_id' in product

    def test_create_requires_auth(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/products', self._body())
        assert resp['statusCode'] == 401

    def test_create_missing_required_field(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        body = self._body()
        del body['price_ils']
        resp = _call(phase4_handler, 'POST', '/api/products', body, _admin_headers())
        assert resp['statusCode'] == 400

    def test_create_performer_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/products', self._body(), _admin_headers())
        assert resp['statusCode'] == 404

    def test_create_duplicate_slug(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/products',
                     self._body(slug='test-shirt'), _admin_headers())
        assert resp['statusCode'] == 409

    def test_create_with_total_slots(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/products',
                     self._body(total_slots=25), _admin_headers())
        assert resp['statusCode'] == 201
        assert resp['_body']['product']['total_slots'] == 25

    def test_create_unlimited_slots(self, phase4_handler, phase4_db_client):
        _seed_performer(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/products', self._body(), _admin_headers())
        assert resp['statusCode'] == 201
        assert resp['_body']['product'].get('total_slots') is None


class TestUpdateProduct:
    def test_update_price(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/products/prod-seed-1',
                     {'price_ils': 200}, _admin_headers())
        assert resp['statusCode'] == 200
        assert resp['_body']['product']['price_ils'] == 200.0

    def test_update_status(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/products/prod-seed-1',
                     {'status': 'sold_out'}, _admin_headers())
        assert resp['statusCode'] == 200
        assert resp['_body']['product']['status'] == 'sold_out'

    def test_update_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'PUT', '/api/products/no-such',
                     {'name': 'X'}, _admin_headers())
        assert resp['statusCode'] == 404

    def test_update_requires_auth(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'PUT', '/api/products/prod-seed-1', {'name': 'X'})
        assert resp['statusCode'] == 401


class TestDeleteProduct:
    def test_delete_success(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'DELETE', '/api/products/prod-seed-1',
                     headers=_admin_headers())
        assert resp['statusCode'] == 200
        assert resp['_body']['product_id'] == 'prod-seed-1'
        assert phase4_db_client.get_product('prod-seed-1') is None

    def test_delete_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'DELETE', '/api/products/no-such',
                     headers=_admin_headers())
        assert resp['statusCode'] == 404

    def test_delete_requires_auth(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'DELETE', '/api/products/prod-seed-1')
        assert resp['statusCode'] == 401
