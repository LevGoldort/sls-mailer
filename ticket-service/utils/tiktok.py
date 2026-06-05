"""
TikTok Content Posting API client and OAuth utilities.
Handles OAuth 2.0 flow, token encryption (AES-256-GCM), and video posting via PULL_FROM_URL.

Access tokens expire in 24h; refresh tokens expire in 365 days.
Always call refresh_access_token() before posting if token_expires_at is near.
"""
import base64
import secrets
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
OAUTH_SCOPE = "user.info.basic,video.publish,video.upload"


# ─── Token encryption (AES-256-GCM, same as utils/instagram.py) ───────────────

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

def get_oauth_url(client_key: str, redirect_uri: str, state: str) -> str:
    """Build TikTok OAuth authorization URL."""
    params = {
        'client_key': client_key,
        'scope': OAUTH_SCOPE,
        'redirect_uri': redirect_uri,
        'state': state,
        'response_type': 'code',
    }
    return f"{TIKTOK_AUTH_URL}?{urlencode(params)}"


def exchange_code(client_key: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    """Exchange authorization code for access + refresh tokens.
    Returns: {access_token, refresh_token, open_id, expires_in, refresh_expires_in, ...}
    """
    resp = requests.post(f"{TIKTOK_API_BASE}/oauth/token/", data={
        'client_key': client_key,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # TikTok wraps response in {data: {...}, error: {...}}
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok token exchange error: {data['error']}")
    return data.get('data', data)


def refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token using the refresh token.
    Returns: {access_token, refresh_token, expires_in, refresh_expires_in, ...}
    """
    resp = requests.post(f"{TIKTOK_API_BASE}/oauth/token/", data={
        'client_key': client_key,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok token refresh error: {data['error']}")
    return data.get('data', data)


# ─── User info ─────────────────────────────────────────────────────────────────

def get_user_info(access_token: str, open_id: str) -> dict:
    """GET /v2/user/info/ — returns {open_id, display_name, avatar_url}."""
    resp = requests.get(
        f"{TIKTOK_API_BASE}/user/info/",
        params={'fields': 'open_id,display_name,avatar_url'},
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok user info error: {data['error']}")
    return data.get('data', {}).get('user', data.get('data', {}))


# ─── Video posting ─────────────────────────────────────────────────────────────

def post_video(access_token: str, video_url: str, title: str,
               privacy_level: str = 'SELF_ONLY') -> str:
    """Initiate a TikTok video post via PULL_FROM_URL. Returns publish_id.

    TikTok pulls the video from video_url asynchronously.
    Use get_post_status(publish_id) to poll until PUBLISH_COMPLETE.
    """
    payload = {
        'post_info': {
            'title': title[:150],
            'privacy_level': privacy_level,
            'disable_duet': False,
            'disable_comment': False,
            'disable_stitch': False,
        },
        'source_info': {
            'source': 'PULL_FROM_URL',
            'video_url': video_url,
        },
    }
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/video/init/",
        json=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
        },
        timeout=30,
    )
    print(f"TikTok post init {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    data = resp.json()
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok post init error: {data['error']}")
    return data['data']['publish_id']


def get_post_status(access_token: str, publish_id: str) -> dict:
    """Check TikTok publish status.
    Returns dict with 'status': PROCESSING_DOWNLOAD | PROCESSING_UPLOAD | PUBLISH_COMPLETE | FAILED
    On PUBLISH_COMPLETE: includes publicaly_available.post_id
    """
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/status/fetch/",
        json={'publish_id': publish_id},
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok status fetch error: {data['error']}")
    return data.get('data', {})


def post_video_bytes(access_token: str, video_bytes: bytes, title: str,
                     privacy_level: str = 'SELF_ONLY', cover_timestamp_ms: int = None) -> str:
    """Post video via FILE_UPLOAD (no domain verification needed). Returns publish_id."""
    video_size = len(video_bytes)
    MAX_CHUNK = 64 * 1024 * 1024  # 64 MB
    MIN_CHUNK = 5 * 1024 * 1024   # 5 MB

    if video_size <= MAX_CHUNK:
        chunk_size = video_size
        total_chunk_count = 1
    else:
        # TikTok requires chunk_size * total_chunk_count == video_size exactly.
        # Find smallest count where the resulting chunk_size fits in [5MB, 64MB].
        chunk_size = None
        total_chunk_count = None
        for count in range(2, 1001):
            cs, remainder = divmod(video_size, count)
            if remainder == 0 and MIN_CHUNK <= cs <= MAX_CHUNK:
                chunk_size = cs
                total_chunk_count = count
                break
        if chunk_size is None:
            total_chunk_count = 2
            chunk_size = video_size // 2
    print(f"TikTok FILE_UPLOAD: video_size={video_size} chunk_size={chunk_size} total_chunks={total_chunk_count}")

    post_info = {
        'title': title[:150],
        'privacy_level': privacy_level,
        'disable_duet': True,
        'disable_comment': True,
        'disable_stitch': True,
    }
    if cover_timestamp_ms is not None:
        post_info['video_cover_timestamp_ms'] = int(cover_timestamp_ms)

    payload = {
        'post_info': post_info,
        'source_info': {
            'source': 'FILE_UPLOAD',
            'video_size': video_size,
            'chunk_size': chunk_size,
            'total_chunk_count': total_chunk_count,
        },
    }
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/video/init/",
        json=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=UTF-8',
        },
        timeout=30,
    )
    print(f"TikTok FILE_UPLOAD init {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    data = resp.json()
    if data.get('error', {}).get('code', 'ok') != 'ok':
        raise RuntimeError(f"TikTok upload init error: {data['error']}")

    publish_id = data['data']['publish_id']
    upload_url = data['data']['upload_url']

    for i in range(total_chunk_count):
        start = i * chunk_size
        end = min(start + chunk_size, video_size)
        chunk = video_bytes[start:end]
        upload_resp = requests.put(
            upload_url,
            headers={
                'Content-Range': f'bytes {start}-{end - 1}/{video_size}',
                'Content-Type': 'video/mp4',
            },
            data=chunk,
            timeout=120,
        )
        print(f"TikTok chunk {i + 1}/{total_chunk_count}: {upload_resp.status_code}")
        if not upload_resp.ok:
            raise RuntimeError(f"TikTok chunk upload failed: {upload_resp.status_code} {upload_resp.text[:200]}")

    return publish_id


# ─── Helpers ───────────────────────────────────────────────────────────────────

def token_expires_at(expires_in_seconds: int) -> str:
    """Return ISO-8601 UTC string for when a token expires."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expiry.strftime('%Y-%m-%dT%H:%M:%SZ')
