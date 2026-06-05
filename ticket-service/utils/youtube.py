"""
YouTube Data API v3 client and OAuth utilities.
Handles Google OAuth 2.0 flow, token encryption (AES-256-GCM), and video upload.

Access tokens expire in 1 hour; refresh tokens are indefinite (until revoked).
Always call refresh_access_token() before uploading if token_expires_at is near.

Unlike TikTok, YouTube does NOT support pull-from-URL. The caller must provide
video bytes directly (download from S3 before calling upload_video).
"""
import base64
import json
import secrets
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_API_BASE = "https://www.googleapis.com/youtube/v3"
YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


# ─── Token encryption (AES-256-GCM, same as instagram.py / tiktok.py) ─────────

def encrypt_token(token: str, key_hex: str) -> str:
    """Encrypt a token string with AES-256-GCM. Returns base64(nonce + ciphertext)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(key_hex)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, token.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_token(encrypted: str, key_hex: str) -> str:
    """Decrypt a token encrypted by encrypt_token."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(key_hex)
    data = base64.b64decode(encrypted)
    nonce, ct = data[:12], data[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode()


# ─── OAuth helpers ─────────────────────────────────────────────────────────────

def get_oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build Google OAuth authorization URL for YouTube upload scope."""
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': OAUTH_SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    """Exchange authorization code for access + refresh tokens.
    Returns: {access_token, refresh_token, expires_in, token_type, ...}
    """
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'code': code,
        'grant_type': 'authorization_code',
    }, timeout=15)
    if not resp.ok:
        print(f"YouTube exchange_code error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f"YouTube token exchange error: {data}")
    return data


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token.
    Returns: {access_token, expires_in, token_type, ...}
    """
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f"YouTube token refresh error: {data}")
    return data


# ─── Channel info ──────────────────────────────────────────────────────────────

def get_channel_info(access_token: str) -> dict:
    """GET /youtube/v3/channels?mine=true — returns channel info for the authenticated user.
    Returns: {channel_id, channel_title, channel_thumbnail_url}
    """
    resp = requests.get(
        f"{YT_API_BASE}/channels",
        params={'part': 'snippet', 'mine': 'true'},
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    if not resp.ok:
        print(f"YouTube get_channel_info error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    data = resp.json()
    items = data.get('items', [])
    if not items:
        raise RuntimeError("No YouTube channel found for this account")
    channel = items[0]
    snippet = channel.get('snippet', {})
    thumbnails = snippet.get('thumbnails', {})
    thumbnail_url = (
        thumbnails.get('default', {}).get('url', '') or
        thumbnails.get('medium', {}).get('url', '') or
        ''
    )
    return {
        'channel_id': channel['id'],
        'channel_title': snippet.get('title', ''),
        'channel_thumbnail_url': thumbnail_url,
    }


# ─── Video upload ──────────────────────────────────────────────────────────────

def set_thumbnail(access_token: str, video_id: str, image_bytes: bytes) -> None:
    """Upload a custom thumbnail for a YouTube video. Requires channel verification."""
    resp = requests.post(
        'https://www.googleapis.com/upload/youtube/v3/thumbnails/set',
        params={'videoId': video_id, 'uploadType': 'media'},
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'image/jpeg',
        },
        data=image_bytes,
        timeout=30,
    )
    if not resp.ok:
        print(f"YouTube set_thumbnail failed {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()


def upload_video(access_token: str, video_bytes: bytes, title: str,
                 description: str = '', category_id: str = '22',
                 privacy_status: str = 'public', tags: list = None) -> str:
    """Upload a video to YouTube using resumable upload. Returns the YouTube video ID.

    Two-step process:
      1. POST initiation request → get resumable upload URL from Location header
      2. PUT video bytes to that URL → YouTube returns the video resource with 'id'

    category_id 22 = People & Blogs (safe default for event/entertainment content).
    """
    snippet = {
        'title': title[:100],
        'description': description[:5000],
        'categoryId': category_id,
    }
    if tags:
        snippet['tags'] = [t[:500] for t in tags[:500]]

    metadata = {
        'snippet': snippet,
        'status': {
            'privacyStatus': privacy_status,
        },
    }

    # Step 1: initiate resumable upload
    init_resp = requests.post(
        YT_UPLOAD_URL,
        params={'uploadType': 'resumable', 'part': 'snippet,status'},
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Upload-Content-Type': 'video/mp4',
            'X-Upload-Content-Length': str(len(video_bytes)),
        },
        data=json.dumps(metadata),
        timeout=30,
    )
    print(f"YouTube upload init {init_resp.status_code}")
    init_resp.raise_for_status()
    resumable_url = init_resp.headers.get('Location')
    if not resumable_url:
        raise RuntimeError("YouTube did not return a resumable upload URL")

    # Step 2: upload video bytes
    upload_resp = requests.put(
        resumable_url,
        headers={
            'Content-Type': 'video/mp4',
            'Content-Length': str(len(video_bytes)),
        },
        data=video_bytes,
        timeout=270,
    )
    print(f"YouTube upload complete {upload_resp.status_code}: {upload_resp.text[:200]}")
    upload_resp.raise_for_status()
    video_data = upload_resp.json()
    video_id = video_data.get('id')
    if not video_id:
        raise RuntimeError(f"YouTube upload succeeded but no video ID returned: {video_data}")
    return video_id


# ─── Helpers ───────────────────────────────────────────────────────────────────

def token_expires_at(expires_in_seconds: int) -> str:
    """Return ISO-8601 UTC string for when a token expires."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expiry.strftime('%Y-%m-%dT%H:%M:%SZ')
