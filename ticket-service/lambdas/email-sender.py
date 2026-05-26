"""
Email Sender Lambda
Отправляет email с билетами после успешной оплаты
"""
import json
import os
import sys
import boto3
from typing import Dict, Any
from datetime import datetime
from decimal import Decimal

# Add parent directory to path для импорта models и utils
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Order, Event
from utils.dynamodb import DynamoDBClient
from jinja2 import Template


# Initialize clients
db = DynamoDBClient()
ses_client = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'eu-north-1'))


def load_email_template() -> str:
    """Загружает HTML шаблон для email"""
    # Try to load from Lambda layer first, then fallback to inline template
    template_path = '/opt/templates/email/ticket_confirmation.html'
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # Fallback to inline template
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ваши билеты</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
        <h1 style="margin: 0; font-size: 28px;">🎫 Ваши билеты готовы!</h1>
    </div>
    
    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        {% if custom_message %}
        <div style="background: #e3f2fd; border: 2px solid #2196f3; padding: 20px; margin-bottom: 24px; border-radius: 8px;">
            <p style="margin: 0; font-size: 17px; line-height: 1.5; color: #1a1a1a;">📢 {{ custom_message }}</p>
        </div>
        {% endif %}

        <h2 style="color: #667eea; margin-top: 0;">{{ event.title }}</h2>

        {% if event.images and event.images|length > 0 %}
        <div style="margin-bottom: 20px; text-align: center;">
            <img src="{{ event.images[0] }}" alt="{{ event.title }}" style="max-width: 100%; height: auto; border-radius: 8px;">
        </div>
        {% endif %}

        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <p><strong>📅 Дата и время:</strong> {{ event_date_formatted }}</p>
            <p><strong>📍 Локация:</strong> <a href="{{ frontend_url }}/locations/{{ location_slug }}.html" style="color: #667eea; text-decoration: none;">{{ location_name }}</a>{% if location_address %}, {{ location_address }}{% endif %}</p>
            <p><strong>🎫 Билеты:</strong> {% for ticket in order.tickets %}{{ ticket.quantity }}x {{ ticket.type_name }}{% if ticket.purchased_seats %} ({% for seat_id in ticket.purchased_seats %}{{ get_seat_display(seat_id) }}{% if not loop.last %}; {% endif %}{% endfor %}){% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</p>
            <p><strong>💰 Сумма:</strong> {{ order.total_amount }} {{ order.currency }}</p>
            <p><strong>📧 Номер заказа:</strong> {{ order.order_id }}</p>
        </div>

        {% if enriched_qr_codes %}
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="color: #667eea; margin-top: 0;">Ваши билеты:</h3>
            <p style="color: #666; font-size: 14px;">Покажите эти QR-коды на входе</p>

            {% for qr in enriched_qr_codes %}
            <div style="border: 2px solid #e0e0e0; border-radius: 8px; padding: 15px; margin-top: 15px;">
                <!-- Top section: Info left, QR right -->
                <div style="display: table; width: 100%;">
                    <div style="display: table-cell; vertical-align: top; width: 60%;">
                        <p style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600; color: #667eea;">{{ event.title }}</p>
                        <p style="margin: 0 0 6px 0; font-size: 14px; color: #333;">🎫 {{ qr['ticket_type_name'] }}</p>
                        {% if qr['seat_id'] %}
                        <p style="margin: 0 0 6px 0; font-size: 15px; font-weight: 600; color: #667eea;">💺 {{ qr['seat_display'] }}</p>
                        {% endif %}
                        <p style="margin: 0 0 4px 0; font-size: 13px; color: #666;">📍 <a href="{{ frontend_url }}/locations/{{ location_slug }}.html" style="color: #667eea; text-decoration: none;">{{ location_name }}</a></p>
                        {% if location_address %}
                        <p style="margin: 0; font-size: 12px; color: #999;">{{ location_address }}</p>
                        {% endif %}
                    </div>
                    <div style="display: table-cell; vertical-align: top; width: 40%; text-align: right;">
                        {% if qr['s3_url'] %}
                        <img src="{{ qr['s3_url'] }}" alt="QR Code" style="width: 120px; height: 120px; border-radius: 8px;">
                        {% else %}
                        <div style="width: 120px; height: 120px; background: #f0f0f0; display: inline-flex; align-items: center; justify-content: center; border-radius: 8px;">
                            <span style="font-size: 48px;">📱</span>
                        </div>
                        {% endif %}
                    </div>
                </div>

                <!-- Bottom section: Ticket ID -->
                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0;">
                    <p style="margin: 0; font-size: 11px; color: #999;">ID билета: <span style="font-family: monospace; color: #666;">{{ qr['code'] }}</span></p>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        
        <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
            <p style="margin: 0; font-size: 14px;"><strong>⚠️ Важно:</strong></p>
            <ul style="margin: 10px 0 0 0; padding-left: 20px; font-size: 14px;">
                <li>Покажите QR-код на входе (можно с телефона)</li>
                <li>Сохраните это письмо до посещения события</li>
            </ul>
        </div>

        <div style="text-align: center; margin-bottom: 20px;">
            <a href="{{ frontend_url }}/ticket.html?order_id={{ order.order_id }}"
               style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                      color: white; padding: 14px 28px; text-decoration: none;
                      border-radius: 8px; font-size: 16px; font-weight: 600;">
                Посмотреть билеты онлайн
            </a>
        </div>

        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
            <p style="color: #666; font-size: 12px; margin: 0 0 10px 0;">
                Для отмены билетов напишите на <a href="mailto:yalla@yallabalagan.org" style="color: #667eea;">yalla@yallabalagan.org</a> и укажите айди билетов (можно переслать это сообщение просто).
            </p>
            <p style="color: #666; font-size: 12px; margin: 0;">
                По закону мы вернем 100% стоимости при отмене за 7 дней до даты. В других случаях - пишите, решим.
            </p>
        </div>
    </div>
</body>
</html>
"""


def get_seat_display(seat_id: str, seating_map) -> str:
    """
    Converts internal seat ID like "0-14" to display label like "Ряд 1, Место 21".
    Counts only enabled seats (skips disabled) - same logic as seating-map-editor.js
    """
    parts = seat_id.split('-')
    if len(parts) != 2:
        return seat_id

    row_index = int(parts[0])
    seat_index = int(parts[1])
    row_display = row_index + 1

    if seating_map:
        custom = seating_map.custom_numbers.get(seat_id)
        if custom:
            seat_display = int(custom.get('seat', seat_index + 1))
            custom_row = custom.get('row')
            if custom_row is not None:
                row_display = int(custom_row)
        else:
            # Count only enabled seats to calculate display number
            disabled_seats = set(seating_map.disabled_seats or [])
            seats_per_row = int(seating_map.seats_per_row)
            enabled_count = 0

            if seating_map.numbering_direction == 'right-to-left':
                # Count from right to left
                for s in range(seats_per_row - 1, -1, -1):
                    check_id = f"{row_index}-{s}"
                    if check_id not in disabled_seats:
                        enabled_count += 1
                        if s == seat_index:
                            break
            else:
                # Count from left to right
                for s in range(seat_index + 1):
                    check_id = f"{row_index}-{s}"
                    if check_id not in disabled_seats:
                        enabled_count += 1

            seat_display = enabled_count
    else:
        seat_display = seat_index + 1

    return f"Ряд {row_display}, Место {seat_display}"


def load_cancellation_template() -> str:
    """Загружает HTML шаблон для email отмены билетов"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отмена билетов</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #e53935 0%, #ff6f00 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
        <h1 style="margin: 0; font-size: 28px;">Отмена билетов</h1>
    </div>

    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        <h2 style="color: #e53935; margin-top: 0;">{{ event.title }}</h2>

        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <p><strong>📅 Дата и время:</strong> {{ event_date_formatted }}</p>
            <p><strong>📍 Локация:</strong> <a href="{{ frontend_url }}/locations/{{ location_slug }}.html" style="color: #e53935; text-decoration: none;">{{ location_name }}</a>{% if location_address %}, {{ location_address }}{% endif %}</p>
            <p><strong>📧 Номер заказа:</strong> {{ order.order_id }}</p>
        </div>

        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="color: #e53935; margin-top: 0;">Отменённые билеты:</h3>

            {% for qr in cancelled_qr_codes %}
            <div style="border: 2px solid #ffcdd2; border-radius: 8px; padding: 15px; margin-top: 15px;">
                <p style="margin: 0 0 6px 0; font-size: 16px; font-weight: 600; color: #e53935;">{{ qr['ticket_type_name'] }}</p>
                {% if qr['seat_id'] %}
                <p style="margin: 0 0 6px 0; font-size: 15px; font-weight: 600; color: #333;">💺 {{ qr['seat_display'] }}</p>
                {% endif %}
                <p style="margin: 0; font-size: 12px; color: #999;">ID билета: <span style="font-family: monospace; color: #666;">{{ qr['code'] }}</span></p>
            </div>
            {% endfor %}
        </div>

        <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
            <p style="margin: 0; font-size: 14px;">По всем дополнительным вопросам связанным с отменой и рефандом пишите на <a href="mailto:yalla@yallabalagan.org" style="color: #e53935;">yalla@yallabalagan.org</a></p>
        </div>
    </div>
</body>
</html>
"""



def format_event_date(event_date: str) -> str:
    """Форматирует дату события для отображения"""
    try:
        # Parse as naive datetime (already in Israel time)
        clean_str = event_date.replace('Z', '')  # Remove Z if present
        dt = datetime.fromisoformat(clean_str)
        # Format: "15 января 2025, 19:00"
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{dt.day} {months[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M')}"
    except:
        return event_date


def send_influencer_welcome_email(payload: Dict) -> Dict:
    """Send welcome email to newly registered influencer"""
    name = payload.get('name', '')
    email = payload.get('email', '')
    coupon_code = payload.get('coupon_code', '')
    dashboard_url = payload.get('dashboard_url', '')
    from_email = os.environ.get('FROM_EMAIL', 'noreply@yallabalagan.org')
    frontend_url = os.environ.get('FRONTEND_URL', 'https://yallabalagan.org')

    if not email:
        print("influencer_welcome: no email provided")
        return {'statusCode': 400, 'body': json.dumps({'error': 'email required'})}

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:3px solid #1a1410;box-shadow:8px 8px 0 #1a1410;">
  <div style="background:#ffd400;border-bottom:3px solid #1a1410;padding:24px 28px;">
    <div style="font-family:monospace;font-size:11px;letter-spacing:.12em;opacity:.6;">YALLA BALAGAN · ПРОГРАММА ЛОЯЛЬНОСТИ</div>
    <h1 style="margin:8px 0 0;font-size:28px;line-height:1.1;">★ Добро пожаловать,<br>{name}!</h1>
  </div>
  <div style="padding:28px;">
    <p style="font-size:15px;line-height:1.6;margin-top:0;">Ты успешно зарегистрирован в программе лояльности YallaBalagan.</p>

    <div style="background:#f8f8f8;border:2px solid #1a1410;padding:16px 20px;margin:20px 0;">
      <div style="font-family:monospace;font-size:11px;letter-spacing:.1em;opacity:.5;margin-bottom:6px;">ТВОЙ ПРОМО-КОД</div>
      <div style="font-family:monospace;font-size:26px;font-weight:700;letter-spacing:.08em;">{coupon_code}</div>
      <p style="font-size:13px;margin:8px 0 0;opacity:.7;">Покупатели введут этот код и получат скидку 10% на билеты.</p>
    </div>

    <p style="font-size:14px;line-height:1.6;">С каждого заказа по твоему коду тебе начисляется <strong>10% комиссии</strong> (от цены до скидки).</p>

    <div style="margin:24px 0;">
      <a href="{dashboard_url}" style="display:inline-block;background:#1a1410;color:#ffd400;padding:12px 24px;text-decoration:none;font-family:monospace;font-size:14px;font-weight:700;letter-spacing:.06em;border:2px solid #1a1410;box-shadow:4px 4px 0 #ffd400;">★ МОЙ ДАШБОРД →</a>
    </div>

    <p style="font-size:13px;color:#666;line-height:1.5;">Сохрани эту ссылку — она даёт доступ к твоей статистике:<br>
    <a href="{dashboard_url}" style="color:#1a1410;word-break:break-all;">{dashboard_url}</a></p>

    <hr style="border:0;border-top:1px dashed #ccc;margin:24px 0;">
    <p style="font-size:12px;color:#999;">Вопросы? Пиши нам — <a href="mailto:hello@yallabalagan.org" style="color:#1a1410;">hello@yallabalagan.org</a></p>
  </div>
</div>
</body></html>"""

    text_body = f"Добро пожаловать в программу лояльности YallaBalagan!\n\nТвой промо-код: {coupon_code}\nДашборд: {dashboard_url}\n\nС каждой продажи по твоему коду тебе начисляется 10% комиссии."

    try:
        ses_client.send_email(
            Source=f'YallaBalagan <{from_email}>',
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': f'★ Твой промо-код {coupon_code} — YallaBalagan', 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_body, 'Charset': 'UTF-8'},
                    'Text': {'Data': text_body, 'Charset': 'UTF-8'},
                },
            }
        )
        print(f"Influencer welcome email sent to {email}")
        return {'statusCode': 200, 'body': json.dumps({'message': 'Email sent'})}
    except Exception as e:
        print(f"Error sending influencer welcome email: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler для отправки email с билетами
    
    Expected event payload:
    {
        "order_id": "uuid"
    }
    """
    try:
        # Parse event payload
        if isinstance(event, str):
            payload = json.loads(event)
        elif 'order_id' in event:
            payload = event
        else:
            # Lambda invoke format
            body = event.get('body', '{}')
            if isinstance(body, str):
                payload = json.loads(body)
            else:
                payload = body
        
        order_id = payload.get('order_id')
        email_type = payload.get('email_type', 'confirmation')
        force_resend = payload.get('force_resend', False)
        custom_message = payload.get('custom_message')
        cancelled_codes = payload.get('cancelled_codes', [])

        # Influencer welcome email — separate flow
        if email_type == 'influencer_welcome':
            return send_influencer_welcome_email(payload)

        if not order_id:
            print("Error: order_id not provided")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'order_id is required'})
            }

        print(f"Processing email for order {order_id} (force_resend={force_resend})")

        # Load order from DynamoDB
        order_data = db.get_order(order_id)
        if not order_data:
            print(f"Error: Order {order_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Order {order_id} not found'})
            }

        order = Order.from_dynamodb_item(order_data)

        # Check if email already sent (skip guard on force_resend and cancellation)
        if email_type != 'cancellation' and order.notifications.email_sent and not force_resend:
            print(f"Email already sent for order {order_id}")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Email already sent', 'order_id': order_id})
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
        
        # Load location (optional - for display)
        location_name = "Локация"
        location_address = ""
        location_slug = event_obj.location_id  # Fallback to ID if slug not available
        seating_map = None
        try:
            location_data = db.get_location(event_obj.location_id)
            if location_data:
                from models import Location
                location = Location.from_dynamodb_item(location_data)
                location_name = location.name
                location_slug = location.slug  # Use slug for URL
                # Format address as "City, Street"
                if location.address and location.address.city and location.address.street:
                    location_address = f"{location.address.city}, {location.address.street}"
                # Extract seating map config for seat display labels
                if location.venue_config and location.venue_config.seating_map:
                    seating_map = location.venue_config.seating_map
        except Exception as e:
            print(f"Warning: Failed to load location: {e}")  # Log the error instead of silently ignoring

        # --- Cancellation email branch ---
        if email_type == 'cancellation':
            print(f"Rendering cancellation email for codes: {cancelled_codes}")

            # Enrich only the cancelled QR codes
            ticket_type_map = {t.type_id: t.type_name for t in order.tickets}
            cancelled_qr_codes = []
            for qr in order.qr_codes:
                if qr.code in cancelled_codes:
                    qr_dict = qr.to_dict()
                    qr_dict['ticket_type_name'] = ticket_type_map.get(qr.ticket_type, qr.ticket_type)
                    if qr_dict.get('seat_id'):
                        qr_dict['seat_display'] = get_seat_display(qr_dict['seat_id'], seating_map)
                    cancelled_qr_codes.append(qr_dict)

            frontend_url = os.environ.get('FRONTEND_URL', 'https://yallabalagan.org')
            cancel_template = Template(load_cancellation_template())
            email_html = cancel_template.render(
                order=order,
                event=event_obj,
                event_date_formatted=format_event_date(event_obj.date),
                location_name=location_name,
                location_address=location_address,
                location_slug=location_slug,
                cancelled_qr_codes=cancelled_qr_codes,
                frontend_url=frontend_url
            )

            sender_email = os.environ.get('SENDER_EMAIL', 'yalla@yallabalagan.org')
            recipient_email = order.customer.email

            print(f"Sending cancellation email from {sender_email} to {recipient_email}")

            response = ses_client.send_email(
                Source=sender_email,
                Destination={'ToAddresses': [recipient_email]},
                Message={
                    'Subject': {
                        'Data': f'Отмена билетов: {event_obj.title}',
                        'Charset': 'UTF-8'
                    },
                    'Body': {
                        'Html': {
                            'Data': email_html,
                            'Charset': 'UTF-8'
                        }
                    }
                }
            )

            print(f"Cancellation email sent. MessageId: {response['MessageId']}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Cancellation email sent successfully',
                    'order_id': order_id,
                    'message_id': response['MessageId']
                })
            }

        # --- Confirmation email flow (default) ---

        # Load email template
        template_str = load_email_template()
        template = Template(template_str)

        # Calculate total tickets
        total_tickets = sum(t.quantity for t in order.tickets)

        # Enrich QR codes with ticket type names and seat display labels
        try:
            ticket_type_map = {t.type_id: t.type_name for t in order.tickets}
            enriched_qr_codes = []
            for qr in order.qr_codes:
                if getattr(qr, 'cancelled', False):
                    continue
                qr_dict = qr.to_dict()
                qr_dict['ticket_type_name'] = ticket_type_map.get(qr.ticket_type, qr.ticket_type)
                if qr.seat_id:
                    qr_dict['seat_display'] = get_seat_display(qr.seat_id, seating_map)
                enriched_qr_codes.append(qr_dict)
            print(f"Enriched {len(enriched_qr_codes)} QR codes (excluded cancelled)")
        except Exception as e:
            print(f"Error enriching QR codes: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to empty list
            enriched_qr_codes = []

        # Get frontend URL from environment
        frontend_url = os.environ.get('FRONTEND_URL', 'https://yallabalagan.org')

        # Render email HTML
        try:
            # Pre-compute seat display labels for template use
            seat_display_fn = lambda seat_id: get_seat_display(seat_id, seating_map)

            email_html = template.render(
                order=order,
                event=event_obj,
                event_date_formatted=format_event_date(event_obj.date),
                location_name=location_name,
                location_address=location_address,
                location_slug=location_slug,
                total_tickets=total_tickets,
                enriched_qr_codes=enriched_qr_codes,
                frontend_url=frontend_url,
                get_seat_display=seat_display_fn,
                custom_message=custom_message
            )
            print(f"Email template rendered successfully")
        except Exception as e:
            print(f"Error rendering email template: {e}")
            import traceback
            traceback.print_exc()
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Failed to render email template: {str(e)}'})
            }
        
        # Get sender email from env
        sender_email = os.environ.get('SENDER_EMAIL', 'yalla@yallabalagan.org')
        recipient_email = order.customer.email

        print(f"Sending email from {sender_email} to {recipient_email}")

        # Send email via SES
        try:
            response = ses_client.send_email(
                Source=sender_email,
                Destination={
                    'ToAddresses': [recipient_email]
                },
                Message={
                    'Subject': {
                        'Data': f'Ваши билеты: {event_obj.title}',
                        'Charset': 'UTF-8'
                    },
                    'Body': {
                        'Html': {
                            'Data': email_html,
                            'Charset': 'UTF-8'
                        }
                    }
                }
            )

            print(f"Email sent successfully. MessageId: {response['MessageId']}")
        except Exception as e:
            print(f"ERROR sending email via SES: {e}")
            print(f"Sender: {sender_email}, Recipient: {recipient_email}")
            import traceback
            traceback.print_exc()
            # Re-raise to trigger the outer exception handler
            raise
        
        # Update order to mark email as sent
        from datetime import datetime
        db.update_order_notification_status(order_id, email_sent=True)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Email sent successfully',
                'order_id': order_id,
                'message_id': response['MessageId']
            })
        }
        
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

