# DEPRECATED — will be removed in Task 17 after full JWT migration
"""Simple API key authentication for admin endpoints"""
import os
import hmac
import boto3
from datetime import datetime, timezone, timedelta
from typing import Optional

_dynamodb = None
_events_table = None


def _get_events_table():
    global _dynamodb, _events_table
    if _events_table is None:
        region = os.environ.get('AWS_REGION', 'eu-north-1')
        _dynamodb = boto3.resource('dynamodb', region_name=region)
        _events_table = _dynamodb.Table(os.environ.get('EVENTS_TABLE', 'yallabalagan-events'))
    return _events_table


class AdminAuthenticator:
    """Admin API key verification using environment variable"""

    def __init__(self):
        # Admin API keys from environment (comma-separated)
        self.admin_keys = set(
            os.environ.get('ADMIN_API_KEYS', '').split(',')
        )
        self.admin_keys = {k.strip() for k in self.admin_keys if k.strip()}

        if not self.admin_keys:
            print("WARNING: No admin API keys configured!")

    def verify_admin_key(self, api_key: str) -> bool:
        """Verify admin API key or JWT Bearer token with admin role."""
        if not api_key:
            return False

        # Accept JWT tokens (eyJ…) that carry an admin role
        if api_key.startswith('eyJ'):
            try:
                from utils.auth_jwt import decode_access_token
                payload = decode_access_token(api_key)
                return payload.get('role') == 'admin'
            except Exception:
                return False

        if not self.admin_keys:
            return False

        # Use constant-time comparison to prevent timing attacks
        for valid_key in self.admin_keys:
            if hmac.compare_digest(api_key, valid_key):
                return True
        return False

    def extract_api_key(self, event: dict) -> Optional[str]:
        """Extract API key from Lambda event headers"""
        headers = event.get('headers', {})
        # Try multiple header names for flexibility
        return (
            headers.get('x-api-key') or
            headers.get('x-admin-key') or
            headers.get('authorization', '').replace('Bearer ', '').replace('bearer ', '')
        )


# Singleton instance
_admin_auth = None


def get_admin_authenticator() -> AdminAuthenticator:
    """Get singleton admin authenticator instance"""
    global _admin_auth
    if _admin_auth is None:
        _admin_auth = AdminAuthenticator()
    return _admin_auth


def verify_scanner_token(token: str, event_id: str) -> bool:
    """Verify scanner token against the event's scanner_password in DynamoDB.

    Returns False on any error, missing field, or expired event — fails closed.
    Event is considered expired when event.date + 8h <= now(UTC).
    """
    try:
        if not token or not event_id:
            return False

        response = _get_events_table().get_item(Key={'PK': f'EVENT#{event_id}', 'SK': 'METADATA'})
        item = response.get('Item')
        if not item:
            return False

        scanner_password = item.get('scanner_password', '')
        if not scanner_password:
            return False

        if not hmac.compare_digest(token, scanner_password):
            return False

        event_date_str = item.get('date', '')
        if not event_date_str:
            return False

        event_dt = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)

        if event_dt + timedelta(hours=8) <= datetime.now(timezone.utc):
            return False

        return True

    except Exception:
        return False


def is_scanner_or_admin(request_event: dict) -> bool:
    """Returns True if request authenticates as admin (X-API-Key) or scanner
    (X-Scanner-Token + X-Scanner-Event). Never raises.
    """
    try:
        headers = {k.lower(): v for k, v in (request_event.get('headers') or {}).items()}

        api_key = (
            headers.get('x-api-key') or
            headers.get('x-admin-key') or
            headers.get('authorization', '').replace('Bearer ', '').replace('bearer ', '')
        )
        if api_key and get_admin_authenticator().verify_admin_key(api_key):
            return True

        scanner_token = headers.get('x-scanner-token', '')
        scanner_event = headers.get('x-scanner-event', '')
        if scanner_token and scanner_event and verify_scanner_token(scanner_token, scanner_event):
            return True

        return False

    except Exception:
        return False
