import requests

GRAPH_URL = "https://graph.facebook.com/v22.0"
RUSSIAN_LOCALE_ID = 1071  # ru_RU — verify via /search?type=adlocale&q=Russian before first deploy
CAMPAIGN_PREFIX = "YB | "


def _post(path, token, data):
    resp = requests.post(
        f"{GRAPH_URL}/{path}",
        params={"access_token": token},
        json=data,
        timeout=30,
    )
    body = resp.json()
    if "error" in body:
        err = body["error"]
        import sys
        print(f"FB API error on POST /{path}: code={err.get('code')} subcode={err.get('error_subcode')} "
              f"type={err.get('type')} msg={err.get('message')} user_msg={err.get('error_user_msg')} "
              f"data={err.get('error_data')}", file=sys.stderr)
        raise RuntimeError(err.get("message", "Facebook API error"))
    resp.raise_for_status()
    return body


def create_campaign(name, token, ad_account_id, pixel_id):
    body = _post(f"{ad_account_id}/campaigns", token, {
        "name": name,
        "objective": "OUTCOME_SALES",
        "status": "PAUSED",
        "special_ad_categories": [],
        "is_adset_budget_sharing_enabled": False,  # adset-level budget, not CBO
    })
    return body["id"]


def create_ad_set(campaign_id, name, daily_budget_cents, start_unix, end_unix,
                  targeting, pixel_id, page_id, token, ad_account_id):
    body = _post(f"{ad_account_id}/adsets", token, {
        "name": name,
        "campaign_id": campaign_id,
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "promoted_object": {
            "pixel_id": pixel_id,
            "custom_event_type": "PURCHASE",
        },
        "daily_budget": daily_budget_cents,
        "start_time": start_unix,
        "end_time": end_unix,
        "targeting": targeting,
        "status": "PAUSED",
    })
    return body["id"]


def upload_image(image_url, token, ad_account_id):
    resp = requests.post(
        f"{GRAPH_URL}/{ad_account_id}/adimages",
        params={"access_token": token},
        data={"url": image_url},
        timeout=30,
    )
    body = resp.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", "Facebook API error"))
    resp.raise_for_status()
    images = body.get("images", {})
    first = next(iter(images.values()))
    return first["hash"]


def upload_video_from_url(s3_url, name, token, ad_account_id):
    body = _post(f"{ad_account_id}/advideos", token, {
        "file_url": s3_url,
        "name": name,
    })
    return body["id"]


def create_image_ad_creative(page_id, message, image_hash, link_url, token, ad_account_id):
    body = _post(f"{ad_account_id}/adcreatives", token, {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "message": message,
                "image_hash": image_hash,
                "link": link_url,
                "call_to_action": {"type": "BUY_TICKETS"},
            },
        },
    })
    return body["id"]


def create_video_ad_creative(page_id, message, video_id, link_url, token, ad_account_id):
    body = _post(f"{ad_account_id}/adcreatives", token, {
        "object_story_spec": {
            "page_id": page_id,
            "video_data": {
                "video_id": video_id,
                "message": message,
                "call_to_action": {
                    "type": "BUY_TICKETS",
                    "value": {"link": link_url},
                },
            },
        },
    })
    return body["id"]


def create_ad(ad_set_id, creative_id, name, token, ad_account_id):
    body = _post(f"{ad_account_id}/ads", token, {
        "name": name,
        "adset_id": ad_set_id,
        "creative": {"creative_id": creative_id},
        "status": "PAUSED",
    })
    return body["id"]


def get_campaigns_with_insights(token, ad_account_id):
    resp = requests.get(
        f"{GRAPH_URL}/{ad_account_id}/campaigns",
        params={
            "access_token": token,
            "fields": (
                "id,name,status,daily_budget,lifetime_budget,start_time,end_time,"
                "insights.date_preset(maximum){impressions,clicks,spend,actions}"
            ),
            "effective_status": '["ACTIVE","PAUSED"]',
            "limit": 25,
        },
        timeout=30,
    )
    body = resp.json()
    if "error" in body:
        err = body["error"]
        raise RuntimeError(err.get("message", "Facebook API error"))
    return [c for c in body.get("data", []) if c.get("name", "").startswith(CAMPAIGN_PREFIX)]


def build_targeting(city_lat, city_lng, radius_km=10):
    return {
        "geo_locations": {
            "custom_locations": [{
                "latitude": city_lat,
                "longitude": city_lng,
                "radius": radius_km,
                "distance_unit": "kilometer",
            }]
        },
        "locales": [RUSSIAN_LOCALE_ID],
        "age_min": 18,
    }
