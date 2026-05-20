"""User API Lambda — auth and user management endpoints.

Routes:
  POST /api/auth/login
  POST /api/auth/refresh
  POST /api/auth/logout
  POST /api/auth/change-password
  /api/users/* — added in Task 9
"""
import json
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.auth_jwt import (
    generate_access_token,
    generate_refresh_token,
    TokenExpiredError,
    TokenInvalidError,
)
from utils.auth_middleware import authenticate, AuthError
from utils.auth_password import hash_password, verify_password
from utils.refresh_token_service import (
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
)
from repositories import user_repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-API-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Content-Type": "application/json",
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

def handle_login(event: dict) -> dict:
    body = parse_body(event)
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return err(400, "email and password are required")

    tenant_id = os.environ.get("TENANT_ID", "yallabalagan")
    user = user_repository.get_user_by_email(email, tenant_id)

    if not user or not user.is_active():
        return err(401, "Invalid email or password")

    if not verify_password(password, user.password_hash):
        return err(401, "Invalid email or password")

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

    try:
        if path == "/api/auth/login" and method == "POST":
            return handle_login(event)
        if path == "/api/auth/refresh" and method == "POST":
            return handle_refresh(event)
        if path == "/api/auth/logout" and method == "POST":
            return handle_logout(event)
        if path == "/api/auth/change-password" and method == "POST":
            return handle_change_password(event)
        return err(404, "Endpoint not found")
    except Exception as exc:
        print(f"[ERROR] {exc}")
        import traceback
        traceback.print_exc()
        return err(500, "Internal server error")
