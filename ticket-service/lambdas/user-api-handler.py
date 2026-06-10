"""User API Lambda — auth, user management, and tenant management endpoints.

Routes:
  POST /api/auth/login
  POST /api/auth/refresh
  POST /api/auth/logout
  POST /api/auth/change-password
  POST /api/auth/switch-tenant
  GET    /api/users
  POST   /api/users
  GET    /api/users/{id}
  PUT    /api/users/{id}
  DELETE /api/users/{id}
  POST   /api/users/{id}/reset-password
  GET    /api/tenants
  POST   /api/tenants
  GET    /api/tenants/{id}
  PUT    /api/tenants/{id}
"""
import json
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.auth_jwt import (
    generate_access_token,
    generate_refresh_token,
    TokenExpiredError,
    TokenInvalidError,
)
from utils.auth_middleware import authenticate, AuthError, stamp_deprecation_header
from utils.auth_password import hash_password, verify_password
from utils.permissions import can_manage_users, can_manage_tenants, is_platform_admin
from utils.refresh_token_service import (
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
)
from repositories import user_repository
import repositories.tenant_repository as tenant_repository
from models.user import User
from models.tenant import Tenant
from utils.rate_limiter import is_rate_limited, reset_rate_limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-API-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=63072000",
}


def ok(body: dict, status: int = 200) -> dict:
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def err(status: int, message: str) -> dict:
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps({"error": message})}


def parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Auth handlers
# ---------------------------------------------------------------------------

def _client_ip(event: dict) -> str:
    return (
        (event.get("requestContext") or {}).get("identity", {}).get("sourceIp")
        or (event.get("requestContext") or {}).get("http", {}).get("sourceIp")
        or "unknown"
    )


def handle_login(event: dict) -> dict:
    body = parse_body(event)
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return err(400, "email and password are required")

    ip = _client_ip(event)
    if is_rate_limited(ip):
        return err(429, "Too many login attempts. Please try again later.")

    tenant_raw = (body.get("tenant_id") or "").strip() or os.environ.get("TENANT_ID", "yallabalagan")
    # Resolve slug → UUID (login form sends slugs, users are stored under UUIDs)
    resolved = tenant_repository.get_tenant_by_slug(tenant_raw)
    tenant_id = resolved.tenant_id if resolved else tenant_raw
    user = user_repository.get_user_by_email(email, tenant_id)

    if not user or not user.is_active():
        return err(401, "Invalid email or password")

    if not verify_password(password, user.password_hash):
        return err(401, "Invalid email or password")

    reset_rate_limit(ip)

    access_token = generate_access_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
    )
    refresh_token = generate_refresh_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )
    store_refresh_token(refresh_token, user.user_id, user.tenant_id)

    return ok({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_api_dict(),
    })


def handle_refresh(event: dict) -> dict:
    body = parse_body(event)
    token = body.get("refresh_token") or ""

    if not token:
        return err(400, "refresh_token is required")

    try:
        payload = validate_refresh_token(token)
    except TokenExpiredError:
        return err(401, "Refresh token has expired")
    except TokenInvalidError:
        return err(401, "Invalid or revoked refresh token")

    user = user_repository.get_user_by_id(payload["sub"], payload["tenant_id"])
    if not user or not user.is_active():
        return err(401, "User not found or inactive")

    access_token = generate_access_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
    )
    return ok({"access_token": access_token})


def handle_logout(event: dict) -> dict:
    body = parse_body(event)
    token = body.get("refresh_token") or ""

    if not token:
        return err(400, "refresh_token is required")

    revoke_refresh_token(token)
    return ok({"message": "Logged out successfully"})


def handle_change_password(event: dict) -> dict:
    try:
        ctx = authenticate(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    if ctx["user_id"] is None:
        return err(403, "Password change requires JWT authentication")

    body = parse_body(event)
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""

    if not current_password or not new_password:
        return err(400, "current_password and new_password are required")

    if len(new_password) < 8:
        return err(400, "new_password must be at least 8 characters")

    user = user_repository.get_user_by_id(ctx["user_id"], ctx["tenant_id"])
    if not user or not user.is_active():
        return err(404, "User not found")

    if not verify_password(current_password, user.password_hash):
        return err(401, "Current password is incorrect")

    from datetime import datetime
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow().isoformat()
    user_repository.update_user(user)

    return ok({"message": "Password changed successfully"})


# ---------------------------------------------------------------------------
# User management helpers
# ---------------------------------------------------------------------------

VALID_ROLES = {"admin", "organizer", "content_manager", "platform_admin"}


def _require_admin(event: dict):
    """Authenticate and assert admin role. Returns ctx or raises AuthError."""
    ctx = authenticate(event)
    if not can_manage_users(ctx, ctx.get("tenant_id", "")):
        raise AuthError("Admin access required", status_code=403)
    return ctx


def _tenant(ctx: dict) -> str:
    return ctx.get("tenant_id") or os.environ.get("TENANT_ID", "yallabalagan")


# ---------------------------------------------------------------------------
# User management handlers
# ---------------------------------------------------------------------------

def handle_list_users(event: dict) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    users = user_repository.list_users_by_tenant(_tenant(ctx))
    return ok({"users": [u.to_api_dict() for u in users]})


def handle_get_user(event: dict, user_id: str) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    user = user_repository.get_user_by_id(user_id, _tenant(ctx))
    if not user:
        return err(404, "User not found")
    return ok({"user": user.to_api_dict()})


def handle_create_user(event: dict) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    body = parse_body(event)
    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()
    role = body.get("role") or ""
    password = body.get("password") or ""

    if not email or not name or not role or not password:
        return err(400, "email, name, role, and password are required")
    if role not in VALID_ROLES:
        return err(400, f"role must be one of: {', '.join(sorted(VALID_ROLES))}")
    if len(password) < 8:
        return err(400, "password must be at least 8 characters")

    # platform_admin not mimicking can specify a target tenant_id in the body
    if is_platform_admin(ctx) and not ctx.get("is_mimicking") and body.get("tenant_id"):
        tenant_id = body["tenant_id"]
        if not tenant_repository.get_tenant_by_id(tenant_id):
            return err(404, f"Tenant '{tenant_id}' not found")
    else:
        tenant_id = _tenant(ctx)
    if user_repository.get_user_by_email(email, tenant_id):
        return err(409, "A user with this email already exists")

    user = User.create(
        email=email,
        password_hash=hash_password(password),
        name=name,
        role=role,
        tenant_id=tenant_id,
    )
    user_repository.create_user(user)
    return ok({"user": user.to_api_dict()}, status=201)


def handle_update_user(event: dict, user_id: str) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    user = user_repository.get_user_by_id(user_id, _tenant(ctx))
    if not user:
        return err(404, "User not found")

    body = parse_body(event)
    from datetime import datetime

    if "name" in body:
        user.name = (body["name"] or "").strip()
        if not user.name:
            return err(400, "name cannot be empty")
    if "role" in body:
        if body["role"] not in VALID_ROLES:
            return err(400, f"role must be one of: {', '.join(sorted(VALID_ROLES))}")
        user.role = body["role"]
    if "status" in body:
        if body["status"] not in {"active", "inactive"}:
            return err(400, "status must be 'active' or 'inactive'")
        user.status = body["status"]

    user.updated_at = datetime.utcnow().isoformat()
    user_repository.update_user(user)
    return ok({"user": user.to_api_dict()})


def handle_deactivate_user(event: dict, user_id: str) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    from botocore.exceptions import ClientError
    try:
        user = user_repository.deactivate_user(user_id, _tenant(ctx))
    except ClientError:
        return err(404, "User not found")

    if not user:
        return err(404, "User not found")
    return ok({"user": user.to_api_dict()})


def handle_reset_password(event: dict, user_id: str) -> dict:
    try:
        ctx = _require_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    body = parse_body(event)
    new_password = body.get("new_password") or ""
    if not new_password:
        return err(400, "new_password is required")
    if len(new_password) < 8:
        return err(400, "new_password must be at least 8 characters")

    user = user_repository.get_user_by_id(user_id, _tenant(ctx))
    if not user:
        return err(404, "User not found")

    from datetime import datetime
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow().isoformat()
    user_repository.update_user(user)
    return ok({"message": "Password reset successfully"})


# ---------------------------------------------------------------------------
# Tenant switch (platform_admin only)
# ---------------------------------------------------------------------------

def handle_switch_tenant(event: dict) -> dict:
    try:
        ctx = authenticate(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    if not is_platform_admin(ctx):
        return err(403, "Only platform_admin can switch tenants")
    if ctx.get("is_mimicking"):
        return err(403, "Already mimicking a tenant — exit first")

    body = parse_body(event)
    target_tenant_id = (body.get("tenant_id") or "").strip()
    if not target_tenant_id:
        return err(400, "tenant_id is required")

    tenant = tenant_repository.get_tenant_by_id(target_tenant_id)
    if not tenant:
        return err(404, "Tenant not found")
    if tenant.status != "active":
        return err(409, "Tenant is inactive")

    mimic_token = generate_access_token(
        user_id=ctx["user_id"],
        tenant_id=target_tenant_id,
        email=ctx["email"],
        role="admin",
        is_mimicking=True,
        original_tenant_id=ctx["tenant_id"],
    )
    return ok({
        "access_token": mimic_token,
        "tenant": tenant.to_api_dict(),
    })


# ---------------------------------------------------------------------------
# Tenant management (platform_admin only)
# ---------------------------------------------------------------------------

import re as _re

_SLUG_RE = _re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def _require_platform_admin(event: dict) -> dict:
    ctx = authenticate(event)
    if not can_manage_tenants(ctx):
        raise AuthError("platform_admin access required", status_code=403)
    return ctx


def handle_list_tenants(event: dict) -> dict:
    try:
        _require_platform_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    tenants = tenant_repository.list_tenants()
    return ok({"tenants": [t.to_api_dict() for t in tenants]})


def handle_create_tenant(event: dict) -> dict:
    try:
        _require_platform_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    body = parse_body(event)
    name = (body.get("name") or "").strip()
    slug = (body.get("slug") or "").strip().lower()

    if not name or not slug:
        return err(400, "name and slug are required")
    if not _SLUG_RE.match(slug):
        return err(400, "slug must be lowercase alphanumeric with hyphens only")

    if tenant_repository.get_tenant_by_slug(slug):
        return err(409, "A tenant with this slug already exists")

    tenant = Tenant.create(name=name, slug=slug)
    tenant_repository.create_tenant(tenant)
    return ok({"tenant": tenant.to_api_dict()}, status=201)


def handle_get_tenant(event: dict, tenant_id: str) -> dict:
    try:
        _require_platform_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    tenant = tenant_repository.get_tenant_by_id(tenant_id)
    if not tenant:
        return err(404, "Tenant not found")
    return ok({"tenant": tenant.to_api_dict()})


def handle_update_tenant(event: dict, tenant_id: str) -> dict:
    try:
        _require_platform_admin(event)
    except AuthError as e:
        return err(e.status_code, str(e))

    tenant = tenant_repository.get_tenant_by_id(tenant_id)
    if not tenant:
        return err(404, "Tenant not found")

    body = parse_body(event)
    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            return err(400, "name cannot be empty")
        tenant.name = name
    if "status" in body:
        if body["status"] not in {"active", "inactive"}:
            return err(400, "status must be 'active' or 'inactive'")
        tenant.status = body["status"]

    tenant_repository.update_tenant(tenant)
    return ok({"tenant": tenant.to_api_dict()})


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: Dict[str, Any], context: Any) -> dict:
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "")
    )
    path = event.get("path") or event.get("rawPath", "")

    stage = event.get("requestContext", {}).get("stage")
    if stage and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1:]

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # Pre-authenticate to detect API key usage for deprecation header stamping.
    # AuthError is expected for unauthenticated endpoints (login, refresh, etc.).
    _pre_ctx: Optional[dict] = None
    try:
        _pre_ctx = authenticate(event)
    except AuthError:
        pass

    try:
        if path == "/api/auth/login" and method == "POST":
            response = handle_login(event)
        elif path == "/api/auth/refresh" and method == "POST":
            response = handle_refresh(event)
        elif path == "/api/auth/logout" and method == "POST":
            response = handle_logout(event)
        elif path == "/api/auth/change-password" and method == "POST":
            response = handle_change_password(event)
        elif path == "/api/auth/switch-tenant" and method == "POST":
            response = handle_switch_tenant(event)

        # /api/tenants routing
        elif path == "/api/tenants":
            if method == "GET":
                response = handle_list_tenants(event)
            elif method == "POST":
                response = handle_create_tenant(event)
            else:
                response = err(405, "Method not allowed")
        elif path.startswith("/api/tenants/"):
            parts = path.split("/")
            if len(parts) == 4:
                tid = parts[3]
                if method == "GET":
                    response = handle_get_tenant(event, tid)
                elif method == "PUT":
                    response = handle_update_tenant(event, tid)
                else:
                    response = err(405, "Method not allowed")
            else:
                response = err(404, "Endpoint not found")

        # /api/users routing
        elif path == "/api/users":
            if method == "GET":
                response = handle_list_users(event)
            elif method == "POST":
                response = handle_create_user(event)
            else:
                response = err(405, "Method not allowed")
        elif path.startswith("/api/users/"):
            parts = path.split("/")  # ["", "api", "users", "<id>", ...]
            if len(parts) >= 4:
                uid = parts[3]
                if len(parts) == 4:
                    if method == "GET":
                        response = handle_get_user(event, uid)
                    elif method == "PUT":
                        response = handle_update_user(event, uid)
                    elif method == "DELETE":
                        response = handle_deactivate_user(event, uid)
                    else:
                        response = err(405, "Method not allowed")
                elif len(parts) == 5 and parts[4] == "reset-password" and method == "POST":
                    response = handle_reset_password(event, uid)
                else:
                    response = err(404, "Endpoint not found")
            else:
                response = err(404, "Endpoint not found")
        else:
            response = err(404, "Endpoint not found")

        if _pre_ctx:
            response = stamp_deprecation_header(response, _pre_ctx)
        return response
    except Exception as exc:
        print(f"[ERROR] {exc}")
        import traceback
        traceback.print_exc()
        return err(500, "Internal server error")
