"""Unit tests for User model"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import User, TENANT_ID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user():
    return User(
        user_id="user-123",
        tenant_id="yallabalagan",
        email="admin@yallabalagan.org",
        password_hash="hashed_password",
        name="Admin User",
        role="admin",
        status="active",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


@pytest.fixture
def organizer_user():
    return User(
        user_id="user-456",
        tenant_id="yallabalagan",
        email="organizer@yallabalagan.org",
        password_hash="hashed_password",
        name="Organizer User",
        role="organizer",
        status="active",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


# ---------------------------------------------------------------------------
# Model fields
# ---------------------------------------------------------------------------

class TestUserFields:
    def test_all_required_fields_present(self, sample_user):
        assert sample_user.user_id == "user-123"
        assert sample_user.tenant_id == "yallabalagan"
        assert sample_user.email == "admin@yallabalagan.org"
        assert sample_user.password_hash == "hashed_password"
        assert sample_user.name == "Admin User"
        assert sample_user.role == "admin"
        assert sample_user.status == "active"
        assert sample_user.created_at == "2026-01-01T00:00:00"
        assert sample_user.updated_at == "2026-01-01T00:00:00"

    def test_tenant_id_default_constant(self):
        assert TENANT_ID == "yallabalagan"


# ---------------------------------------------------------------------------
# generate_id
# ---------------------------------------------------------------------------

class TestGenerateId:
    def test_generates_unique_ids(self):
        id1 = User.generate_id()
        id2 = User.generate_id()
        assert id1 != id2

    def test_id_is_string(self):
        assert isinstance(User.generate_id(), str)

    def test_id_is_uuid_format(self):
        import re
        uid = User.generate_id()
        assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", uid)


# ---------------------------------------------------------------------------
# create factory
# ---------------------------------------------------------------------------

class TestCreateFactory:
    def test_create_sets_all_fields(self):
        user = User.create(
            email="test@example.com",
            password_hash="hash123",
            name="Test User",
            role="organizer",
        )
        assert user.email == "test@example.com"
        assert user.password_hash == "hash123"
        assert user.name == "Test User"
        assert user.role == "organizer"
        assert user.tenant_id == TENANT_ID
        assert user.status == "active"
        assert user.user_id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_create_uses_provided_user_id(self):
        user = User.create(
            email="test@example.com",
            password_hash="hash",
            name="Test",
            role="admin",
            user_id="explicit-id-123",
        )
        assert user.user_id == "explicit-id-123"

    def test_create_uses_provided_tenant_id(self):
        user = User.create(
            email="test@example.com",
            password_hash="hash",
            name="Test",
            role="admin",
            tenant_id="other-tenant",
        )
        assert user.tenant_id == "other-tenant"

    def test_create_timestamps_are_equal(self):
        user = User.create(
            email="test@example.com",
            password_hash="hash",
            name="Test",
            role="admin",
        )
        assert user.created_at == user.updated_at


# ---------------------------------------------------------------------------
# DynamoDB serialization
# ---------------------------------------------------------------------------

class TestDynamoDBSerialization:
    def test_to_dynamodb_item_pk_format(self, sample_user):
        item = sample_user.to_dynamodb_item()
        assert item["PK"] == "TENANT#yallabalagan#USER#user-123"

    def test_to_dynamodb_item_sk(self, sample_user):
        item = sample_user.to_dynamodb_item()
        assert item["SK"] == "METADATA"

    def test_to_dynamodb_item_contains_all_fields(self, sample_user):
        item = sample_user.to_dynamodb_item()
        for field in ["user_id", "tenant_id", "email", "password_hash",
                      "name", "role", "status", "created_at", "updated_at"]:
            assert field in item, f"Field '{field}' missing from DynamoDB item"

    def test_to_dynamodb_item_email_for_gsi(self, sample_user):
        """email должен быть в item для EmailIndex GSI"""
        item = sample_user.to_dynamodb_item()
        assert item["email"] == "admin@yallabalagan.org"

    def test_to_dynamodb_item_tenant_id_for_gsi(self, sample_user):
        """tenant_id должен быть в item для TenantIndex GSI"""
        item = sample_user.to_dynamodb_item()
        assert item["tenant_id"] == "yallabalagan"

    def test_from_dynamodb_item_roundtrip(self, sample_user):
        item = sample_user.to_dynamodb_item()
        restored = User.from_dynamodb_item(item)
        assert restored.user_id == sample_user.user_id
        assert restored.tenant_id == sample_user.tenant_id
        assert restored.email == sample_user.email
        assert restored.password_hash == sample_user.password_hash
        assert restored.name == sample_user.name
        assert restored.role == sample_user.role
        assert restored.status == sample_user.status

    def test_from_dynamodb_item_status_default(self):
        """from_dynamodb_item должен использовать 'active' если status отсутствует"""
        item = {
            "user_id": "u1",
            "tenant_id": "yallabalagan",
            "email": "test@example.com",
            "password_hash": "h",
            "name": "Test",
            "role": "admin",
        }
        user = User.from_dynamodb_item(item)
        assert user.status == "active"


# ---------------------------------------------------------------------------
# API serialization
# ---------------------------------------------------------------------------

class TestApiSerialization:
    def test_to_api_dict_excludes_password_hash(self, sample_user):
        api_dict = sample_user.to_api_dict()
        assert "password_hash" in sample_user.to_dict()
        assert "password_hash" not in api_dict

    def test_to_api_dict_contains_expected_fields(self, sample_user):
        api_dict = sample_user.to_api_dict()
        for field in ["user_id", "tenant_id", "email", "name",
                      "role", "status", "created_at", "updated_at"]:
            assert field in api_dict, f"Field '{field}' missing from API dict"

    def test_to_dict_contains_all_fields_including_password(self, sample_user):
        full_dict = sample_user.to_dict()
        assert "password_hash" in full_dict


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------

class TestHelperMethods:
    def test_is_active_true(self, sample_user):
        assert sample_user.is_active() is True

    def test_is_active_false_when_inactive(self, sample_user):
        sample_user.status = "inactive"
        assert sample_user.is_active() is False

    def test_is_admin_true_for_admin(self, sample_user):
        assert sample_user.is_admin() is True

    def test_is_admin_false_for_organizer(self, organizer_user):
        assert organizer_user.is_admin() is False

    def test_role_values(self, sample_user, organizer_user):
        assert sample_user.role == "admin"
        assert organizer_user.role == "organizer"
