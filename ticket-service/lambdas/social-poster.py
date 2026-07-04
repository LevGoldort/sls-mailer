import json
import os
import sys
import datetime

sys.path.insert(0, '/var/task')

from utils.dynamodb import DynamoDBClient
from utils.instagram import post_reel, post_feed_image, decrypt_token as ig_decrypt_token
from utils.tiktok import post_video_bytes as tiktok_post_video_bytes
from utils.youtube import upload_video as youtube_upload_video, set_thumbnail as youtube_set_thumbnail

db = DynamoDBClient()

MEDIA_BUCKET = os.environ.get('MEDIA_BUCKET', 'yallabalagan-ticket-media')
INSTAGRAM_TOKEN_KEY = os.environ.get('INSTAGRAM_TOKEN_KEY', '')
TIKTOK_TOKEN_KEY = os.environ.get('TIKTOK_TOKEN_KEY', '')
YOUTUBE_TOKEN_KEY = os.environ.get('YOUTUBE_TOKEN_KEY', '')


def lambda_handler(event, context):
    if event.get('source') == 'scheduler':
        process_scheduled_posts()
    else:
        post_id = event.get('post_id')
        if post_id:
            process_post(post_id)


def process_scheduled_posts():
    now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    stale_before = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Mark posts stuck in 'publishing' for > 2 hours as failed
    stale = db.list_stale_publishing_posts(stale_before)
    print(f"Scheduler: found {len(stale)} stale publishing posts")
    for post in stale:
        post_id = post['SK']
        print(f"Marking stale post {post_id} as failed")
        db.update_social_post(post_id, {'status': 'failed', 'error': 'Timed out in publishing state'})

    posts = db.list_due_scheduled_posts()
    print(f"Scheduler: found {len(posts)} due scheduled posts")
    for post in posts:
        post_id = post['SK']
        db.update_social_post(post_id, {'status': 'publishing', 'publishing_since': now})
        process_post(post_id)


def process_post(post_id: str):
    post = db.get_social_post(post_id)
    if not post:
        print(f"Post {post_id} not found")
        return

    media = post.get('media', [])
    # Support both old (caption) and new (title+description) schema
    title = post.get('title') or post.get('caption', '')
    description = post.get('description') or post.get('caption', '')
    tags = post.get('tags', [])
    cover = post.get('cover')  # { type, timestamp_ms?, s3_key }
    collaborators = post.get('collaborators', [])
    targets = post.get('targets', [])
    tenant_id = post.get('tenant_id', '')

    all_ok = True
    any_ok = False

    updated_targets = []
    for target in targets:
        if target.get('status') != 'pending':
            updated_targets.append(target)
            continue
        try:
            platform_post_id = _post_to_platform(target, media, title, description, tags, cover, collaborators, tenant_id)
            updated_targets.append({**target, 'status': 'published', 'platform_post_id': platform_post_id})
            any_ok = True
        except Exception as e:
            print(f"Failed to post to {target.get('platform')} account {target.get('account_id')}: {e}")
            updated_targets.append({**target, 'status': 'failed', 'error': str(e)})
            all_ok = False

    if all_ok and any_ok:
        final_status = 'published'
    elif any_ok:
        final_status = 'partial_fail'
    else:
        final_status = 'failed'

    db.update_social_post(post_id, {
        'status': final_status,
        'targets': updated_targets,
        'published_at': _now_iso(),
    })
    print(f"Post {post_id} finished with status={final_status}")


def _post_to_platform(target: dict, media: list, title: str, description: str,
                      tags: list, cover: dict, collaborators: list, tenant_id: str = '') -> str:
    platform = target.get('platform')
    account_id = target.get('account_id')

    if platform == 'instagram':
        conn = db.get_instagram_connection(account_id, tenant_id=tenant_id)
        if not conn:
            raise ValueError(f"Instagram account {account_id} not found")
        token = ig_decrypt_token(conn['access_token'], INSTAGRAM_TOKEN_KEY)
        first = media[0] if media else None
        if not first:
            raise ValueError("No media to post")
        public_url = f"https://{MEDIA_BUCKET}.s3.eu-north-1.amazonaws.com/{first['s3_key']}"
        cover_url = None
        if cover and cover.get('s3_key'):
            cover_url = f"https://{MEDIA_BUCKET}.s3.eu-north-1.amazonaws.com/{cover['s3_key']}"
        if first.get('type') == 'video':
            return post_reel(account_id, public_url, description, token,
                             cover_url=cover_url, collaborators=collaborators or None)
        else:
            return post_feed_image(account_id, public_url, description, token,
                                   collaborators=collaborators or None)

    elif platform == 'tiktok':
        conn = db.get_tiktok_connection(account_id, tenant_id=tenant_id)
        if not conn:
            raise ValueError(f"TikTok account {account_id} not found")
        first = media[0] if media else None
        if not first:
            raise ValueError("No media to post")
        if first.get('type') != 'video':
            raise ValueError("TikTok only supports video posts in this version")
        access_token = _get_fresh_tiktok_token(conn)
        video_bytes = _download_from_s3(first['s3_key'])
        tiktok_title = (title[:150] if title else first.get('filename', 'Video'))
        cover_ts = cover.get('timestamp_ms') if cover and cover.get('type') == 'frame' else None
        publish_id = tiktok_post_video_bytes(access_token, video_bytes, tiktok_title,
                                             privacy_level='SELF_ONLY', cover_timestamp_ms=cover_ts)
        return _wait_for_tiktok_publish(access_token, publish_id)

    elif platform == 'youtube':
        conn = db.get_youtube_connection(account_id, tenant_id=tenant_id)
        if not conn:
            raise ValueError(f"YouTube account {account_id} not found")
        first = media[0] if media else None
        if not first:
            raise ValueError("No media to post")
        if first.get('type') != 'video':
            raise ValueError("YouTube only supports video posts in this version")
        access_token = _get_fresh_youtube_token(conn)
        video_bytes = _download_from_s3(first['s3_key'])
        yt_title = (title[:100] if title else first.get('filename', 'Video')).strip() or 'Video'
        video_id = youtube_upload_video(access_token, video_bytes, yt_title,
                                        description=description, tags=tags or None)
        if cover and cover.get('s3_key'):
            try:
                thumb_bytes = _download_from_s3(cover['s3_key'])
                youtube_set_thumbnail(access_token, video_id, thumb_bytes)
                print(f"YouTube thumbnail set for video {video_id}")
            except Exception as e:
                print(f"YouTube thumbnail upload failed (non-fatal): {e}")
        return video_id

    raise ValueError(f"Unknown platform: {platform}")


def _get_fresh_tiktok_token(conn: dict) -> str:
    """Return a valid TikTok access token, refreshing if it expires within 5 minutes."""
    from utils.tiktok import decrypt_token, refresh_access_token, encrypt_token, token_expires_at as tt_expires
    expires_at = conn.get('token_expires_at', '')
    if expires_at:
        expiry = datetime.datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        if expiry <= soon:
            client_key = os.environ.get('TIKTOK_CLIENT_KEY', '')
            client_secret = os.environ.get('TIKTOK_CLIENT_SECRET', '')
            refresh_tok = decrypt_token(conn['refresh_token'], TIKTOK_TOKEN_KEY)
            new_tokens = refresh_access_token(client_key, client_secret, refresh_tok)
            enc_access = encrypt_token(new_tokens['access_token'], TIKTOK_TOKEN_KEY)
            enc_refresh = encrypt_token(new_tokens.get('refresh_token', refresh_tok), TIKTOK_TOKEN_KEY)
            db.update_tiktok_tokens(
                conn['SK'],
                enc_access, tt_expires(new_tokens['expires_in']),
                enc_refresh, tt_expires(new_tokens.get('refresh_expires_in', 31536000)),
            )
            print(f"TikTok token refreshed for account {conn['SK']}")
            return new_tokens['access_token']
    from utils.tiktok import decrypt_token
    return decrypt_token(conn['access_token'], TIKTOK_TOKEN_KEY)


def _wait_for_tiktok_publish(access_token: str, publish_id: str) -> str:
    """Poll TikTok publish status until complete. Returns post_id. Polls up to 90s."""
    import time
    from utils.tiktok import get_post_status
    for attempt in range(18):  # 18 × 5s = 90s
        time.sleep(5)
        status_data = get_post_status(access_token, publish_id)
        status = status_data.get('status', '')
        print(f"TikTok publish {publish_id} status: {status} (attempt {attempt + 1})")
        if status == 'PUBLISH_COMPLETE':
            return status_data.get('publicaly_available', {}).get('post_id', publish_id)
        if status == 'FAILED':
            raise RuntimeError(f"TikTok publish failed: {status_data}")
    raise RuntimeError("TikTok publish timed out after 90s")


def _get_fresh_youtube_token(conn: dict) -> str:
    """Return a valid YouTube access token, refreshing if it expires within 5 minutes."""
    from utils.youtube import decrypt_token, refresh_access_token, encrypt_token, token_expires_at as yt_expires
    expires_at = conn.get('token_expires_at', '')
    if expires_at:
        expiry = datetime.datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        if expiry <= soon:
            client_id = os.environ.get('YOUTUBE_CLIENT_ID', '')
            client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET', '')
            refresh_tok = decrypt_token(conn['refresh_token'], YOUTUBE_TOKEN_KEY)
            new_tokens = refresh_access_token(client_id, client_secret, refresh_tok)
            enc_access = encrypt_token(new_tokens['access_token'], YOUTUBE_TOKEN_KEY)
            db.update_youtube_token(
                conn['SK'],
                enc_access,
                yt_expires(new_tokens['expires_in']),
            )
            print(f"YouTube token refreshed for channel {conn['SK']}")
            return new_tokens['access_token']
    from utils.youtube import decrypt_token
    return decrypt_token(conn['access_token'], YOUTUBE_TOKEN_KEY)


def _download_from_s3(s3_key: str) -> bytes:
    """Download a file from the media S3 bucket and return its bytes."""
    import boto3
    s3 = boto3.client('s3', region_name='eu-north-1')
    resp = s3.get_object(Bucket=MEDIA_BUCKET, Key=s3_key)
    return resp['Body'].read()


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
