"""Authentication middleware: JWT Bearer first, legacy API key fallback."""
import logging

from utils.auth_jwt import decode_access_token, TokenExpiredError, TokenInvalidError
from utils.auth import get_admin_authenticator  # DEPRECATED — removed in Task 17

logger = logging.getLogger(__name__)

_TENANT_ID = "yallabalagan"  # hardcoded until multi-tenancy


class AuthError(Exception):
    """Request could not be authenticated."""
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def authenticate(event: dict) -> dict:
    """Authenticate a Lambda event and return user context.

    Checks Authorization: Bearer <token> first; falls back to X-API-Key.

    Returns:
        dict with keys: user_id, tenant_id, email, role, auth_method

    Raises:
        AuthError: if no valid credentials are present.
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    auth_header = headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return _jwt_auth(auth_header[7:])

    api_key = headers.get("x-api-key") or headers.get("x-admin-key")
    if api_key:
        return _api_key_auth(api_key)

    raise AuthError("Authentication required")


def _jwt_auth(token: str) -> dict:
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise AuthError("Access token has expired")
    except TokenInvalidError as exc:
        raise AuthError(f"Invalid access token: {exc}")

    ctx = {
        "user_id": payload["sub"],
        "tenant_id": payload["tenant_id"],
        "email": payload["email"],
        "role": payload["role"],
        "auth_method": "jwt",
    }
    if payload.get("is_mimicking"):
        ctx["is_mimicking"] = True
        ctx["original_tenant_id"] = payload.get("original_tenant_id")
    return ctx


def _api_key_auth(api_key: str) -> dict:
    if not get_admin_authenticator().verify_admin_key(api_key):  # DEPRECATED
        raise AuthError("Invalid API key")

    logger.warning(
        "API key authentication is deprecated — migrate to JWT. "
        "Support will be removed in a future release."
    )
    return {
        "user_id": None,
        "tenant_id": _TENANT_ID,
        "email": None,
        "role": "admin",
        "auth_method": "api_key",
    }


def stamp_deprecation_header(response: dict, ctx: dict) -> dict:
    """Add X-Deprecated-Auth header to a Lambda response if API key auth was used."""
    if ctx.get("auth_method") == "api_key":
        headers = dict(response.get("headers") or {})
        headers["X-Deprecated-Auth"] = (
            "API key authentication is deprecated; migrate to JWT Bearer tokens"
        )
        response = {**response, "headers": headers}
    return response
