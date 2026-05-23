"""Unit tests for utils/permissions.py"""
import pytest
from utils.permissions import is_admin, can_manage_users, can_access_event

TENANT = "yallabalagan"


def _ctx(role: str, user_id: str = "u1") -> dict:
    return {"user_id": user_id, "tenant_id": TENANT, "role": role}


def _event(owner_id=None) -> dict:
    return {"event_id": "ev1", "owner_id": owner_id}


# ===== is_admin =====

class TestIsAdmin:
    def test_admin_returns_true(self):
        assert is_admin(_ctx("admin"), TENANT) is True

    def test_organizer_returns_false(self):
        assert is_admin(_ctx("organizer"), TENANT) is False

    def test_empty_role_returns_false(self):
        assert is_admin(_ctx(""), TENANT) is False

    def test_accepts_user_model_object(self):
        class FakeUser:
            role = "admin"
        assert is_admin(FakeUser(), TENANT) is True


# ===== can_manage_users =====

class TestCanManageUsers:
    def test_admin_can_manage_users(self):
        assert can_manage_users(_ctx("admin"), TENANT) is True

    def test_organizer_cannot_manage_users(self):
        assert can_manage_users(_ctx("organizer"), TENANT) is False


# ===== can_access_event =====

class TestCanAccessEvent:
    def test_admin_accesses_any_event(self):
        assert can_access_event(_ctx("admin"), _event(owner_id="someone-else"), TENANT) is True

    def test_admin_accesses_event_without_owner(self):
        assert can_access_event(_ctx("admin"), _event(owner_id=None), TENANT) is True

    def test_organizer_accesses_own_event(self):
        ctx = _ctx("organizer", user_id="u1")
        assert can_access_event(ctx, _event(owner_id="u1"), TENANT) is True

    def test_organizer_denied_other_event(self):
        ctx = _ctx("organizer", user_id="u1")
        assert can_access_event(ctx, _event(owner_id="u2"), TENANT) is False

    def test_organizer_denied_unowned_event(self):
        ctx = _ctx("organizer", user_id="u1")
        assert can_access_event(ctx, _event(owner_id=None), TENANT) is False

    def test_unknown_role_denied(self):
        assert can_access_event(_ctx("viewer"), _event(owner_id="u1"), TENANT) is False

    def test_accepts_event_model_object(self):
        class FakeEvent:
            owner_id = "u1"
        ctx = _ctx("organizer", user_id="u1")
        assert can_access_event(ctx, FakeEvent(), TENANT) is True

    def test_tenant_id_param_accepted(self):
        # Ensure signature matches future SaaS call-sites
        assert can_access_event(_ctx("admin"), _event(), "other-tenant") is True
