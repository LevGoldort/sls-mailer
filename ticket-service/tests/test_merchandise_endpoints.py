"""Integration tests for /api/merchandise endpoints (Task 24)."""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _call(handler, method, path, body=None, headers=None):
    event = {
        'httpMethod': method,
        'path': path,
        'headers': headers or {},
        'queryStringParameters': None,
        'body': json.dumps(body) if isinstance(body, dict) else body,
        'requestContext': {'http': {'method': method, 'sourceIp': '127.0.0.1'}},
    }
    resp = handler.lambda_handler(event, None)
    resp['_body'] = json.loads(resp['body'])
    return resp


def _seed_performer(db, performer_id='perf-1'):
    from models.performer import Performer
    p = Performer(
        performer_id=performer_id,
        tenant_id='yallabalagan',
        name='Test DJ',
        slug=f'test-dj-{performer_id}',
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
        product_id='prod-1',
        tenant_id='yallabalagan',
        performer_id='perf-1',
        name='Cool Shirt',
        slug='cool-shirt',
        short_description='Nice shirt',
        price_ils=99.0,
        photo_url='https://cdn.example.com/shirt.jpg',
        status='active',
        total_slots=None,
        sold_slots=0,
    )
    defaults.update(kwargs)
    p = Product(**defaults)
    db.put_product(p.to_dynamodb_item())
    return p


class TestPurchaseMerchandise:
    def _buyer(self):
        return {'name': 'Alice', 'email': 'alice@example.com', 'phone': '+972501234'}

    def test_purchase_creates_order(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 201
        body = resp['_body']
        assert body['order_id'].startswith('merch-')
        assert 'payment_url' in body
        assert body['amount_ils'] == 99.0

    def test_purchase_order_persisted(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': self._buyer(),
        })
        order_id = resp['_body']['order_id']
        item = phase4_db_client.get_merchandise_order(order_id)
        assert item is not None
        assert item['status'] == 'pending'
        assert item['buyer']['email'] == 'alice@example.com'

    def test_purchase_product_not_found(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'no-such-product',
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 404

    def test_purchase_inactive_product(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, status='inactive')
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 409

    def test_purchase_sold_out(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, total_slots=5, sold_slots=5)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 409

    def test_purchase_unlimited_slots_always_available(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, total_slots=None, sold_slots=999)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 201

    def test_purchase_missing_product_id(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'buyer': self._buyer(),
        })
        assert resp['statusCode'] == 400

    def test_purchase_missing_buyer_email(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': {'name': 'Alice'},  # missing email
        })
        assert resp['statusCode'] == 400


class TestMerchandiseWebhook:
    def _webhook_body(self, order_id, status='completed'):
        return json.dumps({
            'order_id': order_id,
            'status': status,
            'transaction_id': 'txn-mock-001',
        })

    def _create_pending_order(self, handler, db):
        _seed_product(db)
        resp = _call(handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': {'name': 'Bob', 'email': 'bob@example.com'},
        })
        return resp['_body']['order_id']

    def test_webhook_completed_updates_order(self, phase4_handler, phase4_db_client):
        order_id = self._create_pending_order(phase4_handler, phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/webhook',
                     body=self._webhook_body(order_id),
                     headers={'x-webhook-signature': 'mock-sig'})
        assert resp['statusCode'] == 200
        item = phase4_db_client.get_merchandise_order(order_id)
        assert item['status'] == 'completed'

    def test_webhook_completed_increments_sold_slots(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, total_slots=10, sold_slots=0)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': {'name': 'Bob', 'email': 'bob@example.com'},
        })
        order_id = resp['_body']['order_id']
        _call(phase4_handler, 'POST', '/api/merchandise/webhook',
              body=self._webhook_body(order_id),
              headers={'x-webhook-signature': 'mock-sig'})
        product = phase4_db_client.get_product('prod-1')
        assert int(product['sold_slots']) == 1

    def test_webhook_marks_sold_out_when_full(self, phase4_handler, phase4_db_client):
        _seed_product(phase4_db_client, total_slots=1, sold_slots=0)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/purchase', {
            'product_id': 'prod-1',
            'buyer': {'name': 'Bob', 'email': 'bob@example.com'},
        })
        order_id = resp['_body']['order_id']
        _call(phase4_handler, 'POST', '/api/merchandise/webhook',
              body=self._webhook_body(order_id),
              headers={'x-webhook-signature': 'mock-sig'})
        product = phase4_db_client.get_product('prod-1')
        assert product['status'] == 'sold_out'

    def test_webhook_failed_status(self, phase4_handler, phase4_db_client):
        order_id = self._create_pending_order(phase4_handler, phase4_db_client)
        resp = _call(phase4_handler, 'POST', '/api/merchandise/webhook',
                     body=self._webhook_body(order_id, 'failed'),
                     headers={'x-webhook-signature': 'mock-sig'})
        assert resp['statusCode'] == 200
        item = phase4_db_client.get_merchandise_order(order_id)
        assert item['status'] == 'failed'

    def test_webhook_invalid_signature(self, phase4_handler):
        resp = _call(phase4_handler, 'POST', '/api/merchandise/webhook',
                     body=self._webhook_body('merch-fake'),
                     headers={'x-webhook-signature': ''})  # empty = invalid in mock mode
        assert resp['statusCode'] == 401

    def test_webhook_unknown_order_returns_200(self, phase4_handler):
        # Should return 200 to prevent All-Pay retries
        resp = _call(phase4_handler, 'POST', '/api/merchandise/webhook',
                     body=self._webhook_body('merch-nonexistent'),
                     headers={'x-webhook-signature': 'mock-sig'})
        assert resp['statusCode'] == 200
        assert resp['_body']['status'] == 'ignored'
