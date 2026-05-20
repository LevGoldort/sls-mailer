"""Tests for owner_id and tenant_id fields on Event model"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.event import Event, TicketType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(**kwargs) -> Event:
    defaults = dict(
        event_id="evt-001",
        title="Test Event",
        description="Description",
        date="2026-06-01T20:00:00Z",
        location_id="loc-001",
        ticket_types=[TicketType(id="tt-1", name="Regular", price=100.0, total=50, available=50)],
    )
    defaults.update(kwargs)
    return Event(**defaults)


def make_dynamodb_item(**kwargs):
    base = {
        "PK": "EVENT#evt-001",
        "SK": "METADATA",
        "event_id": "evt-001",
        "title": "Test Event",
        "description": "Description",
        "date": "2026-06-01T20:00:00Z",
        "location_id": "loc-001",
        "ticket_types": [{"id": "tt-1", "name": "Regular", "price": 100.0, "total": 50, "available": 50}],
        "currency": "ILS",
        "images": [],
        "status": "active",
        "recurrence": None,
        "refund_policy": {"enabled": True, "hours_before": 48},
        "GSI1PK": "EVENT",
        "GSI1SK": "2026-06-01T20:00:00Z",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Backward compatibility — новые поля Optional
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_event_without_owner_id_is_valid(self):
        event = make_event()
        assert event.owner_id is None

    def test_event_without_tenant_id_is_valid(self):
        event = make_event()
        assert event.tenant_id is None

    def test_existing_fields_unaffected(self):
        event = make_event()
        assert event.event_id == "evt-001"
        assert event.title == "Test Event"
        assert event.status == "active"

    def test_from_dynamodb_item_without_new_fields(self):
        """Legacy DynamoDB item без owner_id и tenant_id читается без ошибок"""
        item = make_dynamodb_item()
        event = Event.from_dynamodb_item(item)
        assert event.owner_id is None
        assert event.tenant_id is None


# ---------------------------------------------------------------------------
# Создание событий с новыми полями
# ---------------------------------------------------------------------------

class TestNewFields:
    def test_event_with_owner_id(self):
        event = make_event(owner_id="user-123")
        assert event.owner_id == "user-123"

    def test_event_with_tenant_id(self):
        event = make_event(tenant_id="yallabalagan")
        assert event.tenant_id == "yallabalagan"

    def test_event_with_both_fields(self):
        event = make_event(owner_id="user-123", tenant_id="yallabalagan")
        assert event.owner_id == "user-123"
        assert event.tenant_id == "yallabalagan"


# ---------------------------------------------------------------------------
# to_dynamodb_item — сериализация
# ---------------------------------------------------------------------------

class TestToDynamodbItem:
    def test_owner_id_included_when_set(self):
        event = make_event(owner_id="user-123")
        item = event.to_dynamodb_item()
        assert item["owner_id"] == "user-123"

    def test_tenant_id_included_when_set(self):
        event = make_event(tenant_id="yallabalagan")
        item = event.to_dynamodb_item()
        assert item["tenant_id"] == "yallabalagan"

    def test_owner_id_absent_when_none(self):
        """None не должен попасть в DynamoDB item — иначе сломается OwnerIndex GSI"""
        event = make_event()
        item = event.to_dynamodb_item()
        assert "owner_id" not in item

    def test_tenant_id_absent_when_none(self):
        event = make_event()
        item = event.to_dynamodb_item()
        assert "tenant_id" not in item

    def test_existing_fields_still_present(self):
        event = make_event(owner_id="user-123")
        item = event.to_dynamodb_item()
        assert item["PK"] == "EVENT#evt-001"
        assert item["GSI1PK"] == "EVENT"
        assert item["title"] == "Test Event"


# ---------------------------------------------------------------------------
# from_dynamodb_item — десериализация
# ---------------------------------------------------------------------------

class TestFromDynamodbItem:
    def test_reads_owner_id(self):
        item = make_dynamodb_item(owner_id="user-123")
        event = Event.from_dynamodb_item(item)
        assert event.owner_id == "user-123"

    def test_reads_tenant_id(self):
        item = make_dynamodb_item(tenant_id="yallabalagan")
        event = Event.from_dynamodb_item(item)
        assert event.tenant_id == "yallabalagan"

    def test_roundtrip_with_new_fields(self):
        original = make_event(owner_id="user-123", tenant_id="yallabalagan")
        item = original.to_dynamodb_item()
        restored = Event.from_dynamodb_item(item)
        assert restored.owner_id == original.owner_id
        assert restored.tenant_id == original.tenant_id

    def test_roundtrip_without_new_fields(self):
        """Legacy событие без новых полей — roundtrip не ломается"""
        original = make_event()
        item = original.to_dynamodb_item()
        restored = Event.from_dynamodb_item(item)
        assert restored.owner_id is None
        assert restored.tenant_id is None
        assert restored.event_id == original.event_id
