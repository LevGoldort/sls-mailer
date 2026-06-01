#!/usr/bin/env python3
"""
Lambda: Instagram token auto-refresh.
Runs every 48h via EventBridge schedule.
Finds connections whose token expires within 10 days, refreshes via Graph API.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.dynamodb import DynamoDBClient
from utils.instagram import refresh_long_lived_token, encrypt_token, decrypt_token, token_expires_at

REFRESH_WINDOW_DAYS = 10

db = DynamoDBClient()


def lambda_handler(event, context):
    app_id = os.environ.get('META_APP_ID', '')
    app_secret = os.environ.get('META_APP_SECRET', '')
    token_key = os.environ.get('INSTAGRAM_TOKEN_KEY', '')

    if not all([app_id, app_secret, token_key]):
        print("ERROR: Instagram env vars not set, skipping refresh")
        return {'refreshed': 0, 'errors': 0}

    connections = db.list_instagram_connections()
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(days=REFRESH_WINDOW_DAYS)

    refreshed = 0
    errors = 0

    for conn in connections:
        ig_user_id = conn.get('SK')
        expires_at_str = conn.get('token_expires_at', '')

        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            print(f"WARN: could not parse token_expires_at for {ig_user_id}: {expires_at_str}")
            continue

        if expires_at > threshold:
            continue

        print(f"Refreshing token for IG user {ig_user_id} (expires {expires_at_str})")
        try:
            access_token = decrypt_token(conn['access_token'], token_key)
            new_token_data = refresh_long_lived_token(app_id, app_secret, access_token)
            new_token = new_token_data['access_token']
            new_expires_in = new_token_data.get('expires_in', 5183944)

            db.update_instagram_token(
                ig_user_id,
                encrypt_token(new_token, token_key),
                token_expires_at(new_expires_in),
            )
            print(f"Refreshed token for {ig_user_id}")
            refreshed += 1
        except Exception as e:
            print(f"ERROR refreshing token for {ig_user_id}: {e}")
            errors += 1

    result = {'refreshed': refreshed, 'errors': errors, 'total_checked': len(connections)}
    print(f"Token refresh complete: {json.dumps(result)}")
    return result
