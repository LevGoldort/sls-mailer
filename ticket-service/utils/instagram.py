"""
Meta Graph API client and Instagram token utilities.
Handles OAuth flow, token encryption (AES-256-GCM), and Graph API calls.
"""
import os
import base64
import secrets
import requests
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

GRAPH_URL = "https://graph.facebook.com/v22.0"


# ─── Token encryption ─────────────────────────────────────────────────────────

def encrypt_token(token: str, key_hex: str) -> str:
    """Encrypt access token with AES-256-GCM. Returns base64(nonce + ciphertext)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(key_hex)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, token.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_token(encrypted: str, key_hex: str) -> str:
    """Decrypt token encrypted by encrypt_token."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(key_hex)
    data = base64.b64decode(encrypted)
    nonce, ct = data[:12], data[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode()


# ─── OAuth helpers ─────────────────────────────────────────────────────────────

def get_oauth_url(app_id: str, redirect_uri: str, state: str) -> str:
    params = {
        'client_id': app_id,
        'redirect_uri': redirect_uri,
        'scope': 'instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,business_management',
        'state': state,
        'response_type': 'code',
    }
    return f"https://www.facebook.com/dialog/oauth?{urlencode(params)}"


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> dict:
    """Exchange authorization code for short-lived user token."""
    resp = requests.get(f"{GRAPH_URL}/oauth/access_token", params={
        'client_id': app_id,
        'client_secret': app_secret,
        'redirect_uri': redirect_uri,
        'code': code,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_long_lived_token(app_id: str, app_secret: str, short_lived_token: str) -> dict:
    """Exchange short-lived token for long-lived (~60 days) token."""
    resp = requests.get(f"{GRAPH_URL}/oauth/access_token", params={
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': app_secret,
        'fb_exchange_token': short_lived_token,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()  # {access_token, token_type, expires_in}


def refresh_long_lived_token(app_id: str, app_secret: str, access_token: str) -> dict:
    """Refresh an existing long-lived token. Returns new token data."""
    resp = requests.get(f"{GRAPH_URL}/oauth/access_token", params={
        'grant_type': 'fb_exchange_token',
        'client_id': app_id,
        'client_secret': app_secret,
        'fb_exchange_token': access_token,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ─── Graph API helpers ─────────────────────────────────────────────────────────

def get_me(access_token: str) -> dict:
    """GET /me — who is the token authenticated as."""
    resp = requests.get(f"{GRAPH_URL}/me", params={
        'access_token': access_token,
        'fields': 'id,name',
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_user_pages(access_token: str) -> list:
    """GET /me/accounts — Facebook Pages the user manages directly."""
    resp = requests.get(f"{GRAPH_URL}/me/accounts", params={
        'access_token': access_token,
        'fields': 'id,name,instagram_business_account',
        'limit': 100,
    }, timeout=10)
    resp.raise_for_status()
    full = resp.json()
    print(f"get_user_pages raw response: {full}")
    return full.get('data', [])


def get_business_pages(access_token: str) -> list:
    """GET /me/businesses → owned_pages — for Business Suite managed pages."""
    pages = []
    try:
        resp = requests.get(f"{GRAPH_URL}/me/businesses", params={
            'access_token': access_token,
            'fields': 'id,name',
            'limit': 50,
        }, timeout=10)
        resp.raise_for_status()
        businesses = resp.json().get('data', [])
        print(f"get_business_pages: {len(businesses)} businesses: {[b.get('name') for b in businesses]}")
        for biz in businesses:
            biz_id = biz['id']
            pr = requests.get(f"{GRAPH_URL}/{biz_id}/owned_pages", params={
                'access_token': access_token,
                'fields': 'id,name,instagram_business_account',
                'limit': 100,
            }, timeout=10)
            pr.raise_for_status()
            biz_pages = pr.json().get('data', [])
            print(f"  Business {biz_id} pages: {biz_pages}")
            pages.extend(biz_pages)
    except Exception as e:
        print(f"get_business_pages error: {e}")
    return pages


def get_ig_user_info(ig_user_id: str, access_token: str) -> dict:
    """GET /{ig_user_id}?fields=id,name,username — IG Business account info."""
    resp = requests.get(f"{GRAPH_URL}/{ig_user_id}", params={
        'access_token': access_token,
        'fields': 'id,name,username',
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def post_story(ig_user_id: str, image_url: str, access_token: str, link: str = '') -> str:
    """Post an image as Instagram Story. Returns media_id."""
    import time

    # Step 1: create media container (caption not supported for Stories)
    container_data = {
        'image_url': image_url,
        'media_type': 'STORIES',
        'access_token': access_token,
    }
    if link:
        container_data['link_url'] = link
        print(f"Instagram post_story: link_url will be sent: {link}")

    container_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data=container_data,
        timeout=15,
    )
    print(f"Instagram container response {container_resp.status_code}: {container_resp.text}")
    if not container_resp.ok:
        container_resp.raise_for_status()
    creation_id = container_resp.json()['id']

    # Step 2: poll until container status is FINISHED
    # API Gateway hard-limits to 29s, Lambda to 30s — stay under 20s total poll time
    for attempt in range(8):
        time.sleep(2)
        status_resp = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={'fields': 'status_code', 'access_token': access_token},
            timeout=10,
        )
        if status_resp.ok:
            status_code = status_resp.json().get('status_code', '')
            print(f"Container {creation_id} status: {status_code} (attempt {attempt + 1})")
            if status_code == 'FINISHED':
                break
            if status_code == 'ERROR':
                raise RuntimeError(f"Meta container processing failed: {status_resp.json()}")
        if attempt == 7:
            raise RuntimeError("Container not ready after 16s — retry later")

    # Step 3: publish
    publish_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={
            'creation_id': creation_id,
            'access_token': access_token,
        },
        timeout=15,
    )
    if not publish_resp.ok:
        print(f"Meta publish error {publish_resp.status_code}: {publish_resp.text}")
        publish_resp.raise_for_status()
    return publish_resp.json()['id']


def token_expires_at(expires_in_seconds: int) -> str:
    """Return ISO-8601 UTC datetime string for token expiry."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expiry.isoformat()
