"""JWT token generation and validation using PyJWT"""
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

ALGORITHM = "HS256"


def _get_secret() -> str:
    """Читает JWT_SECRET из env. Падает громко если не задан — лучше упасть при старте, чем подписывать токены пустым ключом."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TokenExpiredError(Exception):
    """Access или refresh token истёк"""


class TokenInvalidError(Exception):
    """Token невалидный, подделан или неверная структура"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_access_token(
    user_id: str,
    tenant_id: str,
    email: str,
    role: str,
) -> str:
    """
    Генерирует JWT access token (15 минут).

    Payload: sub, tenant_id, email, role, exp, iat, type.

    Args:
        user_id:   ID пользователя (sub).
        tenant_id: ID тенанта ('yallabalagan' сейчас).
        email:     Email пользователя.
        role:      Роль ('admin' | 'organizer').

    Returns:
        Подписанный JWT в виде строки.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def generate_refresh_token(
    user_id: str,
    tenant_id: str,
) -> str:
    """
    Генерирует JWT refresh token (7 дней).

    Refresh token содержит минимум данных — только sub и tenant_id.
    Полные данные пользователя берутся из БД при обновлении access token.

    Returns:
        Подписанный JWT + случайный jti (JWT ID) для возможности отзыва.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "refresh",
        "jti": secrets.token_hex(32),  # уникальный ID для отзыва через DynamoDB
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def validate_token(token: str, expected_type: Optional[str] = None) -> dict:
    """
    Валидирует JWT и возвращает payload.

    Args:
        token:         JWT строка.
        expected_type: 'access' или 'refresh' — проверяет поле type.
                       None — тип не проверяется.

    Returns:
        Decoded payload как dict.

    Raises:
        TokenExpiredError:  Токен истёк.
        TokenInvalidError:  Токен невалидный или неверный тип.
    """
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except InvalidTokenError as e:
        raise TokenInvalidError(f"Invalid token: {e}")

    if expected_type and payload.get("type") != expected_type:
        raise TokenInvalidError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )

    return payload


def decode_access_token(token: str) -> dict:
    """Shortcut: валидирует и возвращает payload access token."""
    return validate_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict:
    """Shortcut: валидирует и возвращает payload refresh token."""
    return validate_token(token, expected_type="refresh")
