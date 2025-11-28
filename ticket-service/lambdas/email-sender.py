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
        <h2 style="color: #667eea; margin-top: 0;">{{ event.title }}</h2>
        
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <p><strong>📅 Дата и время:</strong> {{ event_date_formatted }}</p>
            <p><strong>📍 Локация:</strong> {{ location_name }}</p>
            <p><strong>🎫 Количество билетов:</strong> {{ total_tickets }}</p>
            <p><strong>💰 Сумма:</strong> {{ order.total_amount }} {{ order.currency }}</p>
            <p><strong>📧 Номер заказа:</strong> {{ order.order_id }}</p>
        </div>
        
        {% if order.qr_codes %}
        <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="color: #667eea; margin-top: 0;">Ваши QR-коды:</h3>
            <p style="color: #666; font-size: 14px;">Покажите эти QR-коды на входе</p>
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px; margin-top: 20px;">
                {% for qr in order.qr_codes %}
                <div style="text-align: center; padding: 15px; border: 2px solid #e0e0e0; border-radius: 8px;">
                    {% if qr.s3_url %}
                    <img src="{{ qr.s3_url }}" alt="QR Code {{ qr.code }}" style="width: 150px; height: 150px; display: block; margin: 0 auto;">
                    {% else %}
                    <div style="width: 150px; height: 150px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; margin: 0 auto; border-radius: 8px;">
                        <span style="font-size: 48px;">📱</span>
                    </div>
                    {% endif %}
                    <p style="margin: 10px 0 5px 0; font-size: 12px; font-family: monospace; color: #666;">{{ qr.code }}</p>
                    <p style="margin: 0; font-size: 11px; color: #999;">{{ qr.ticket_type }}</p>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
        
        <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
            <p style="margin: 0; font-size: 14px;"><strong>⚠️ Важно:</strong></p>
            <ul style="margin: 10px 0 0 0; padding-left: 20px; font-size: 14px;">
                <li>Приходите за 15-30 минут до начала события</li>
                <li>Покажите QR-код на входе (можно с телефона)</li>
                <li>Сохраните это письмо до посещения события</li>
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
            <p style="color: #666; font-size: 12px; margin: 0;">
                Если у вас есть вопросы, свяжитесь с нами по email или телефону.
            </p>
        </div>
    </div>
</body>
</html>
"""


def format_event_date(event_date: str) -> str:
    """Форматирует дату события для отображения"""
    try:
        dt = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
        # Format: "15 января 2025, 19:00"
        months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        return f"{dt.day} {months[dt.month - 1]} {dt.year}, {dt.strftime('%H:%M')}"
    except:
        return event_date


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
        if not order_id:
            print("Error: order_id not provided")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'order_id is required'})
            }
        
        print(f"Processing email for order {order_id}")
        
        # Load order from DynamoDB
        order_data = db.get_order(order_id)
        if not order_data:
            print(f"Error: Order {order_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Order {order_id} not found'})
            }
        
        order = Order.from_dynamodb_item(order_data)
        
        # Check if email already sent
        if order.notifications.email_sent:
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
        try:
            location_data = db.get_location(event_obj.location_id)
            if location_data:
                from models import Location
                location = Location.from_dynamodb_item(location_data)
                location_name = location.name
        except:
            pass  # Location not critical for email
        
        # Load email template
        template_str = load_email_template()
        template = Template(template_str)
        
        # Calculate total tickets
        total_tickets = sum(t.quantity for t in order.tickets)
        
        # Render email HTML
        email_html = template.render(
            order=order,
            event=event_obj,
            event_date_formatted=format_event_date(event_obj.date),
            location_name=location_name,
            total_tickets=total_tickets
        )
        
        # Get sender email from env
        sender_email = os.environ.get('SENDER_EMAIL', 'noreply@yallabalagan.com')
        recipient_email = order.customer.email
        
        # Send email via SES
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

