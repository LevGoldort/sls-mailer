"""Role-based access control helpers.

All functions accept a user context dict (as returned by auth_middleware) and
take tenant_id even though it is not enforced yet — ensures call-sites are
SaaS-ready without future refactoring.

To add a new role in the future: add one entry to ROLE_PERMISSIONS only.
"""
from typing import Union

# User context dict shape (from auth_middleware.authenticate):
#   {"user_id": str|None, "tenant_id": str, "role": str, ...}
# Also accepts a User model instance or any object with a .role attribute.

# Permission strings used across the codebase:
#   "events:write"       — create / update / delete events, seat-allocation
#   "locations:write"    — create / update / delete locations
#   "performers:write"   — create / update / delete performers
#   "products:write"     — create / update / delete merch products
#   "shows:write"        — create / update / delete shows
#   "episodes:write"     — create / update / delete episodes
#   "media:upload"       — upload images to S3
#   "site:regenerate"    — trigger site regeneration
#   "*"                  — wildcard: all permissions (admin only)

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"*", "tenants:manage"},
    "admin": {"*"},
    "content_manager": {
        "events:write",
        "locations:write",
        "performers:write",
        "products:write",
        "shows:write",
        "episodes:write",
        "media:upload",
        "site:regenerate",
    },
    "organizer": {
        "events:write_own",
    },
}


def _role(user: Union[dict, object]) -> str:
    if isinstance(user, dict):
        return user.get("role", "")
    return getattr(user, "role", "")


def _user_id(user: Union[dict, object]) -> Union[str, None]:
    if isinstance(user, dict):
        return user.get("user_id")
    return getattr(user, "user_id", None)


def has_permission(user: Union[dict, object], permission: str) -> bool:
    """Return True if user's role grants the given permission."""
    perms = ROLE_PERMISSIONS.get(_role(user), set())
    return "*" in perms or permission in perms


def is_admin(user: Union[dict, object], tenant_id: str) -> bool:
    """Return True if user has the admin role (wildcard permissions)."""
    return has_permission(user, "*")


def can_manage_users(user: Union[dict, object], tenant_id: str) -> bool:
    """Only admins may create, update, or deactivate users."""
    return is_admin(user, tenant_id)


def is_platform_admin(user: Union[dict, object]) -> bool:
    """Return True if user has the platform_admin role (cross-tenant powers)."""
    return _role(user) == "platform_admin"


def can_manage_tenants(user: Union[dict, object]) -> bool:
    """Only platform_admin may create, update, or list tenants."""
    return is_platform_admin(user)


def can_access_event(
    user: Union[dict, object],
    event: Union[dict, object],
    tenant_id: str,
) -> bool:
    """Return True if the user may read or modify this event.

    Admins and content_managers: full access to all events.
    Organizers: only events they own (owner_id == user_id).
    Events without an owner_id are admin-only (pre-migration state).
    """
    if is_admin(user, tenant_id):
        return True

    if has_permission(user, "events:write"):
        return True

    if _role(user) == "organizer":
        if isinstance(event, dict):
            event_owner = event.get("owner_id")
        else:
            event_owner = getattr(event, "owner_id", None)
        return event_owner is not None and event_owner == _user_id(user)

    return False
