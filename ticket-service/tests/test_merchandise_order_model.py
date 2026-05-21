"""Unit tests for BuyerInfo and MerchandiseOrder models (Task 24)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.merchandise_order import BuyerInfo, MerchandiseOrder


class TestBuyerInfo:
    def test_to_dict_required_fields_only(self):
        b = BuyerInfo(name='Alice', email='alice@example.com')
        d = b.to_dict()
        assert d == {'name': 'Alice', 'email': 'alice@example.com'}
        assert 'phone' not in d
        assert 'telegram' not in d

    def test_to_dict_with_optional_fields(self):
        b = BuyerInfo(name='Bob', email='bob@example.com', phone='+972501234', telegram='@bob')
        d = b.to_dict()
        assert d['phone'] == '+972501234'
        assert d['telegram'] == '@bob'

    def test_from_dict_roundtrip(self):
        b = BuyerInfo(name='Carol', email='carol@example.com', phone='+972509999')
        restored = BuyerInfo.from_dict(b.to_dict())
        assert restored.name == 'Carol'
        assert restored.email == 'carol@example.com'
        assert restored.phone == '+972509999'
        assert restored.telegram is None


class TestMerchandiseOrder:
    def _make(self, **kwargs):
        defaults = dict(
            order_id='merch-abc-123',
            product_id='prod-456',
            product_slug='cool-shirt',
            performer_id='perf-789',
            buyer=BuyerInfo(name='Alice', email='alice@example.com'),
            amount_ils=120.0,
        )
        defaults.update(kwargs)
        return MerchandiseOrder(**defaults)

    def test_generate_id_has_merch_prefix(self):
        oid = MerchandiseOrder.generate_id()
        assert oid.startswith('merch-')

    def test_to_dynamodb_item_pk_sk(self):
        o = self._make()
        item = o.to_dynamodb_item()
        assert item['PK'] == 'MERCH_ORDER#merch-abc-123'
        assert item['SK'] == 'METADATA'

    def test_gsi1_email_index(self):
        o = self._make()
        item = o.to_dynamodb_item()
        assert item['GSI1PK'] == 'alice@example.com'
        assert item['GSI1SK'] == o.created_at

    def test_gsi2_product_index(self):
        o = self._make()
        item = o.to_dynamodb_item()
        assert item['GSI2PK'] == 'PRODUCT#prod-456'
        assert item['GSI2SK'] == o.created_at

    def test_buyer_email_denormalized(self):
        o = self._make()
        item = o.to_dynamodb_item()
        assert item['buyer_email'] == 'alice@example.com'

    def test_payment_id_absent_when_none(self):
        o = self._make(payment_id=None)
        item = o.to_dynamodb_item()
        assert 'payment_id' not in item

    def test_payment_id_present_when_set(self):
        o = self._make(payment_id='txn-xyz')
        item = o.to_dynamodb_item()
        assert item['payment_id'] == 'txn-xyz'

    def test_status_defaults_to_pending(self):
        o = self._make()
        assert o.status == 'pending'
        assert o.to_dynamodb_item()['status'] == 'pending'

    def test_from_dynamodb_item_roundtrip(self):
        o = self._make(payment_id='txn-001', status='completed')
        restored = MerchandiseOrder.from_dynamodb_item(o.to_dynamodb_item())
        assert restored.order_id == 'merch-abc-123'
        assert restored.product_id == 'prod-456'
        assert restored.performer_id == 'perf-789'
        assert restored.buyer.name == 'Alice'
        assert restored.buyer.email == 'alice@example.com'
        assert restored.amount_ils == 120.0
        assert restored.payment_id == 'txn-001'
        assert restored.status == 'completed'
