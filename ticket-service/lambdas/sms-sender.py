"""
SMS Sender Lambda
Sends SMS notifications via Active Trail after successful payment
"""
import json
import os
import re
import sys
import boto3
import urllib.request
import urllib.error
from typing import Dict, Any
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Order, Event
from utils.dynamodb import DynamoDBClient


db = DynamoDBClient()


def format_event_date(event_date: str) -> str:
    """Format event date for SMS display"""
    try:
        clean_str = event_date.replace('Z', '')
        dt = datetime.fromisoformat(clean_str)
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{dt.day} {months[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M')}"
    except:
        return event_date


def build_sms_message(order: Order, event: Event, custom_message: str = None, include_ticket_info: bool = True) -> str:
    """Build SMS message text"""
    parts = []

    if custom_message:
        parts.append(custom_message)

    if include_ticket_info:
        total_tickets = sum(t.quantity for t in order.tickets)
        parts.append(f"Ваши билеты на {event.title}")
        parts.append(f"Дата: {format_event_date(event.date)}")
        parts.append(f"Билетов: {total_tickets}")
        parts.append("Билеты отправлены на email.")
        frontend_url = os.environ.get('FRONTEND_URL', 'https://events.yallabalagan.org')
        parts.append(f"Билеты онлайн: {frontend_url}/ticket.html?order_id={order.order_id}")

    return "\n".join(parts)


def send_active_trail_sms(phone: str, message: str) -> Dict:
    """Send SMS via Active Trail Operational Message API"""
    api_key = os.environ.get('ACTIVETRAIL_API_KEY')
    sender_id = os.environ.get('ACTIVETRAIL_SENDER_ID', 'Yalla')

    if not api_key:
        raise ValueError("ACTIVETRAIL_API_KEY environment variable not set")

    # Normalize phone: keep leading + if present, strip everything except digits
    normalized = phone.strip()
    prefix = '+' if normalized.startswith('+') else ''
    normalized = prefix + re.sub(r'\D', '', normalized)

    url = 'https://webapi.mymarketing.co.il/api/smscampaign/OperationalMessage'

    payload = {
        "details": {
            "name": "ticket_notification",
            "from_name": sender_id,
            "content": message,
            "can_unsubscribe": False,
            "unsubscribe_text": ""
        },
        "scheduling": {
            "send_now": True
        },
        "mobiles": [
            {"phone_number": normalized}
        ]
    }

    data = json.dumps(payload).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response_body = response.read().decode('utf-8')
            print(f"Active Trail response ({response.status}): {response_body}")
            return {
                'status_code': response.status,
                'body': response_body
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        print(f"Active Trail HTTP error {e.code}: {error_body}")
        raise RuntimeError(f"Active Trail API error {e.code}: {error_body}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for sending SMS via Active Trail

    Expected event payload:
    {
        "order_id": "uuid",
        "custom_message": "Optional prepended text",
        "force_resend": false
    }
    """
    try:
        # Parse payload
        if isinstance(event, str):
            payload = json.loads(event)
        elif 'order_id' in event:
            payload = event
        else:
            body = event.get('body', '{}')
            if isinstance(body, str):
                payload = json.loads(body)
            else:
                payload = body

        order_id = payload.get('order_id')
        force_resend = payload.get('force_resend', False)
        custom_message = payload.get('custom_message', '')
        include_ticket_info = payload.get('include_ticket_info', True)

        if not order_id:
            print("Error: order_id not provided")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'order_id is required'})
            }

        print(f"Processing SMS for order {order_id} (force_resend={force_resend})")

        # Load order
        order_data = db.get_order(order_id)
        if not order_data:
            print(f"Error: Order {order_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Order {order_id} not found'})
            }

        order = Order.from_dynamodb_item(order_data)

        # Skip if already sent (unless force_resend)
        if order.notifications.sms_sent and not force_resend:
            print(f"SMS already sent for order {order_id}")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'SMS already sent', 'order_id': order_id})
            }

        # Check phone number
        phone = order.customer.phone if order.customer else None
        if not phone:
            print(f"No phone number for order {order_id}, skipping SMS")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No phone number, SMS skipped', 'order_id': order_id})
            }

        # Load event
        event_data = db.get_event(order.event_id)
        if not event_data:
            print(f"Error: Event {order.event_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Event {order.event_id} not found'})
            }

        event_obj = Event.from_dynamodb_item(event_data)

        # Build and send SMS
        message_text = build_sms_message(order, event_obj, custom_message or None, include_ticket_info)
        print(f"Sending SMS to {phone}: {message_text[:50]}...")

        result = send_active_trail_sms(phone, message_text)

        # Mark SMS as sent
        db.update_order_notification_status(order_id, sms_sent=True)
        print(f"SMS sent and marked for order {order_id}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'SMS sent successfully',
                'order_id': order_id,
                'active_trail_response': result
            })
        }

    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
