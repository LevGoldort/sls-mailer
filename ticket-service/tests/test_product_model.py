"""Unit tests for Product model (Task 23)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.product import Product


class TestProduct:
    def _make(self, **kwargs):
        defaults = dict(
            product_id='prod-123',
            tenant_id='yallabalagan',
            performer_id='perf-456',
            name='Cool T-Shirt',
            slug='cool-t-shirt',
            short_description='A cool shirt',
            price_ils=120.0,
            photo_url='https://cdn.example.com/shirt.jpg',
        )
        defaults.update(kwargs)
        return Product(**defaults)

    def test_generate_id_returns_string(self):
        pid = Product.generate_id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_to_dynamodb_item_pk_sk(self):
        p = self._make()
        item = p.to_dynamodb_item()
        assert item['PK'] == 'PRODUCT#prod-123'
        assert item['SK'] == 'METADATA'

    def test_gsi1_performer_index(self):
        p = self._make()
        item = p.to_dynamodb_item()
        assert item['GSI1PK'] == 'PERFORMER#perf-456'
        assert item['GSI1SK'] == p.updated_at

    def test_gsi2_status_index(self):
        p = self._make(status='active')
        item = p.to_dynamodb_item()
        assert item['GSI2PK'] == 'active'
        assert item['GSI2SK'] == p.updated_at

    def test_total_slots_absent_when_none(self):
        p = self._make(total_slots=None)
        item = p.to_dynamodb_item()
        assert 'total_slots' not in item

    def test_total_slots_present_when_set(self):
        p = self._make(total_slots=50)
        item = p.to_dynamodb_item()
        assert item['total_slots'] == 50

    def test_sold_slots_defaults_to_zero(self):
        p = self._make()
        assert p.sold_slots == 0
        assert p.to_dynamodb_item()['sold_slots'] == 0

    def test_from_dynamodb_item_roundtrip(self):
        p = self._make(
            full_description='Full description here',
            what_you_get='One shirt',
            total_slots=100,
            sold_slots=5,
            status='active',
        )
        restored = Product.from_dynamodb_item(p.to_dynamodb_item())
        assert restored.product_id == p.product_id
        assert restored.performer_id == p.performer_id
        assert restored.name == p.name
        assert restored.price_ils == p.price_ils
        assert restored.total_slots == 100
        assert restored.sold_slots == 5
        assert restored.status == 'active'

    def test_from_dynamodb_item_unlimited_slots(self):
        p = self._make(total_slots=None)
        restored = Product.from_dynamodb_item(p.to_dynamodb_item())
        assert restored.total_slots is None

    def test_from_dynamodb_item_defaults(self):
        item = {'product_id': 'p-1', 'performer_id': 'perf-1', 'name': 'X', 'slug': 'x'}
        p = Product.from_dynamodb_item(item)
        assert p.tenant_id == 'yallabalagan'
        assert p.price_ils == 0.0
        assert p.sold_slots == 0
        assert p.gallery_urls == []

    def test_gallery_urls_stored(self):
        p = self._make(gallery_urls=['https://cdn.example.com/1.jpg', 'https://cdn.example.com/2.jpg'])
        item = p.to_dynamodb_item()
        assert item['gallery_urls'] == ['https://cdn.example.com/1.jpg', 'https://cdn.example.com/2.jpg']
