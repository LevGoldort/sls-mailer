"""High-level refresh token management: JWT validation + DynamoDB storage."""
import hashlib
from datetime import datetime, timezone, timedelta

from utils.auth_jwt import (
    decode_refresh_token,
    TokenInvalidError,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from repositories import token_repository


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def store_refresh_token(token: str, user_id: str, tenant_id: str) -> None:
    """Hash the raw JWT and persist it with a 7-day TTL."""
    expires_at = int(
        (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()
    )
    token_repository.store_refresh_token(
        token_hash=_hash(token),
        user_id=user_id,
        tenant_id=tenant_id,
        expires_at=expires_at,
    )


def validate_refresh_token(token: str) -> dict:
    """Validate JWT signature/expiry and confirm the token is not revoked.

    Returns the decoded payload.
    Raises TokenExpiredError if the JWT is expired.
    Raises TokenInvalidError if the JWT is invalid or the token was revoked.
    """
    payload = decode_refresh_token(token)
    if token_repository.get_refresh_token(_hash(token)) is None:
        raise TokenInvalidError("Refresh token has been revoked")
    return payload


def revoke_refresh_token(token: str) -> None:
    """Remove the token from DynamoDB so it can no longer be used."""
    token_repository.revoke_refresh_token(_hash(token))
