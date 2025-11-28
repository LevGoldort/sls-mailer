"""Simple API key authentication for admin endpoints"""
import os
import hmac
from typing import Optional


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
        """Verify admin API key with constant-time comparison"""
        if not api_key or not self.admin_keys:
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
