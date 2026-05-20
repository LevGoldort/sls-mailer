"""Role-based access control helpers.

All functions accept a user context dict (as returned by auth_middleware) and
take tenant_id even though it is not enforced yet — ensures call-sites are
SaaS-ready without future refactoring.
"""
from typing import Union

# User context dict shape (from auth_middleware.authenticate):
#   {"user_id": str|None, "tenant_id": str, "role": str, ...}
# Also accepts a User model instance or any object with a .role attribute.


def _role(user: Union[dict, object]) -> str:
    if isinstance(user, dict):
        return user.get("role", "")
    return getattr(user, "role", "")


def _user_id(user: Union[dict, object]) -> Union[str, None]:
    if isinstance(user, dict):
        return user.get("user_id")
    return getattr(user, "user_id", None)


def is_admin(user: Union[dict, object], tenant_id: str) -> bool:
    """Return True if user has the admin role."""
    return _role(user) == "admin"


def can_manage_users(user: Union[dict, object], tenant_id: str) -> bool:
    """Only admins may create, update, or deactivate users."""
    return is_admin(user, tenant_id)


def can_access_event(
    user: Union[dict, object],
    event: Union[dict, object],
    tenant_id: str,
) -> bool:
    """Return True if the user may read or modify this event.

    Admins: full access.
    Organizers: only events they own (owner_id == user_id).
    Events without an owner_id are admin-only (pre-migration state).
    """
    if is_admin(user, tenant_id):
        return True

    if _role(user) == "organizer":
        if isinstance(event, dict):
            event_owner = event.get("owner_id")
        else:
            event_owner = getattr(event, "owner_id", None)
        return event_owner is not None and event_owner == _user_id(user)

    return False
