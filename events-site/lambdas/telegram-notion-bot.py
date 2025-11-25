import json
import os
import requests
from datetime import datetime
import boto3

NOTION_TOKEN = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID = os.environ['NOTION_DATABASE_ID']
ALLOWED_USERS = os.environ.get('ALLOWED_USERS', '').split(',')
SITE_GENERATOR_LAMBDA = os.environ['SITE_GENERATOR_LAMBDA']

# Ticket-service environment variables
TICKET_API_URL = os.environ.get('TICKET_API_URL', '')
TELEGRAM_SESSIONS_TABLE = os.environ.get('TELEGRAM_SESSIONS_TABLE', 'telegram-sessions')
TICKETS_MEDIA_BUCKET = os.environ.get('TICKETS_MEDIA_BUCKET', 'yallabalagan-ticket-media')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def get_og_image(url):
    """Извлекает Open Graph картинку из URL"""
    try:
        from urllib.parse import urljoin
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)

        html = response.text

        og_start = html.find('property="og:image"')
        if og_start == -1:
            og_start = html.find("property='og:image'")

        if og_start != -1:
            content_start = html.find('content=', og_start)
            if content_start != -1:
                quote = html[content_start + 8]
                content_end = html.find(quote, content_start + 9)
                if content_end != -1:
                    image_url = html[content_start + 9:content_end]
                    return urljoin(url, image_url)

        return None
    except Exception as e:
        print(f"Error getting OG image: {e}")
        return None


def check_event_exists(url):
    """Проверяет, существует ли событие с такой ссылкой"""
    query = {
        "filter": {
            "property": "URL",
            "url": {
                "equals": url
            }
        }
    }

    response = requests.post(
        f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
        headers=notion_headers(),
        json=query
    )

    if response.status_code == 200:
        results = response.json().get('results', [])
        return len(results) > 0

    return False


def add_event_to_notion(title, date, url):
    """Добавляет событие в Notion Database"""

    image_url = get_og_image(url)

    data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Date": {
                "date": {"start": date}
            },
            "URL": {
                "url": url
            }
        }
    }

    if image_url:
        data["cover"] = {
            "type": "external",
            "external": {"url": image_url}
        }
        print(f"Found cover image: {image_url}")

    print(f"Sending to Notion: {json.dumps(data, ensure_ascii=False)}")

    response = requests.post(
        f"{NOTION_API_URL}/pages",
        headers=notion_headers(),
        json=data
    )

    print(f"Notion response status: {response.status_code}")

    return response.status_code == 200


def delete_old_events():
    """Удаляет события с датой в прошлом"""
    today = datetime.now().date().isoformat()

    response = requests.post(
        f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
        headers=notion_headers(),
        json={}
    )

    if response.status_code != 200:
        return 0

    pages = response.json().get('results', [])
    deleted_count = 0

    for page in pages:
        date_prop = page['properties'].get('Date', {}).get('date')
        if date_prop and date_prop.get('start'):
            event_date = date_prop['start']
            if event_date < today:
                requests.patch(
                    f"{NOTION_API_URL}/pages/{page['id']}",
                    headers=notion_headers(),
                    json={"archived": True}
                )
                deleted_count += 1

    return deleted_count


def trigger_site_regeneration():
    """Асинхронно вызывает Lambda для регенерации сайта"""
    try:
        lambda_client.invoke(
            FunctionName=SITE_GENERATOR_LAMBDA,
            InvocationType='Event',  # Асинхронный вызов
            Payload=json.dumps({})
        )
        print(f"Triggered site regeneration via {SITE_GENERATOR_LAMBDA}")
        return True
    except Exception as e:
        print(f"Error triggering site regeneration: {e}")
        return False


def send_telegram_message(chat_id, text):
    """Отправляет сообщение в Telegram"""
    return {
        'statusCode': 200,
        'body': json.dumps({
            'method': 'sendMessage',
            'chat_id': chat_id,
            'text': text
        })
    }


def delete_event_by_url(url):
    """Удаляет событие по URL из Notion"""
    # Ищем событие с таким URL
    query = {
        "filter": {
            "property": "URL",
            "url": {
                "equals": url
            }
        }
    }

    response = requests.post(
        f"{NOTION_API_URL}/databases/{NOTION_DATABASE_ID}/query",
        headers=notion_headers(),
        json=query
    )

    if response.status_code != 200:
        return False, "Ошибка при поиске события"

    results = response.json().get('results', [])

    if not results:
        return False, "Событие с такой ссылкой не найдено"

    # Удаляем (архивируем) найденное событие
    page_id = results[0]['id']

    delete_response = requests.patch(
        f"{NOTION_API_URL}/pages/{page_id}",
        headers=notion_headers(),
        json={"archived": True}
    )

    if delete_response.status_code == 200:
        # Получаем название для сообщения
        title_prop = results[0]['properties'].get('Name', {}).get('title', [])
        title = title_prop[0]['text']['content'] if title_prop else 'Событие'
        return True, title
    else:
        return False, "Ошибка при удалении"


# ============================================================
# TICKET-SERVICE BOT FUNCTIONS
# ============================================================

# Session Management
def get_session(chat_id):
    """Get session from DynamoDB"""
    try:
        table = dynamodb.Table(TELEGRAM_SESSIONS_TABLE)
        response = table.get_item(Key={'chat_id': str(chat_id)})
        return response.get('Item')
    except Exception as e:
        print(f"Error getting session: {e}")
        return None


def save_session(chat_id, session_data):
    """Save session to DynamoDB with 24h TTL"""
    try:
        table = dynamodb.Table(TELEGRAM_SESSIONS_TABLE)
        import time
        session_data['chat_id'] = str(chat_id)
        session_data['updated_at'] = int(time.time())
        session_data['ttl'] = int(time.time()) + 86400  # 24 hours
        table.put_item(Item=session_data)
        return True
    except Exception as e:
        print(f"Error saving session: {e}")
        return False


def clear_session(chat_id):
    """Delete session from DynamoDB"""
    try:
        table = dynamodb.Table(TELEGRAM_SESSIONS_TABLE)
        table.delete_item(Key={'chat_id': str(chat_id)})
        return True
    except Exception as e:
        print(f"Error clearing session: {e}")
        return False


# Telegram Bot API Helpers
def send_message_with_keyboard(chat_id, text, buttons=None, parse_mode='HTML'):
    """Send message with optional inline keyboard via webhook response"""
    payload = {
        'method': 'sendMessage',
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }

    if buttons:
        # buttons format: [[{'text': 'Button 1', 'callback_data': 'data1'}], ...]
        payload['reply_markup'] = {'inline_keyboard': buttons}

    return {
        'statusCode': 200,
        'body': json.dumps(payload)
    }


def get_telegram_file(file_id):
    """Get file info from Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    try:
        response = requests.get(url, params={'file_id': file_id})
        if response.status_code == 200:
            file_path = response.json()['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            return file_url
        return None
    except Exception as e:
        print(f"Error getting file: {e}")
        return None


def download_telegram_photo(file_url):
    """Download photo from Telegram"""
    try:
        response = requests.get(file_url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"Error downloading photo: {e}")
        return None


# S3 Media Upload
def upload_photo_to_s3(photo_content, s3_key):
    """Upload photo to S3 and return URL"""
    try:
        s3_client.put_object(
            Bucket=TICKETS_MEDIA_BUCKET,
            Key=s3_key,
            Body=photo_content,
            ContentType='image/jpeg',
            ACL='public-read'  # Try public-read, fallback to generating signed URL if blocked
        )

        # Return public URL
        url = f"https://{TICKETS_MEDIA_BUCKET}.s3.eu-north-1.amazonaws.com/{s3_key}"
        return url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        # Try without ACL if public-read is blocked
        try:
            s3_client.put_object(
                Bucket=TICKETS_MEDIA_BUCKET,
                Key=s3_key,
                Body=photo_content,
                ContentType='image/jpeg'
            )
            # Generate presigned URL (7 days expiry)
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': TICKETS_MEDIA_BUCKET, 'Key': s3_key},
                ExpiresIn=604800  # 7 days
            )
            return url
        except Exception as e2:
            print(f"Error with fallback upload: {e2}")
            return None


# API Integration
def call_ticket_api(method, endpoint, data=None):
    """Call ticket-service API with retry logic"""
    url = f"{TICKET_API_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    for attempt in range(3):
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                return None

            if response.status_code in [200, 201]:
                return response.json()
            else:
                print(f"API error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"API call error (attempt {attempt + 1}): {e}")
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
    return None


def get_locations_list():
    """Get all locations from API"""
    result = call_ticket_api('GET', '/api/locations')
    if result and 'locations' in result:
        return result['locations']
    return []


def get_events_list():
    """Get all events from API"""
    result = call_ticket_api('GET', '/api/events')
    if result and 'events' in result:
        return result['events']
    return []


# Parsers
from datetime import datetime as dt
import re


def parse_date(text):
    """Parse date from text (YYYY-MM-DD)"""
    try:
        date_obj = dt.strptime(text.strip(), '%Y-%m-%d')
        if date_obj.date() < dt.now().date():
            return None, "Дата не может быть в прошлом"
        return text.strip(), None
    except:
        return None, "Неверный формат. Используй YYYY-MM-DD, например: 2025-12-31"


def parse_time(text):
    """Parse time from text (HH:MM)"""
    try:
        time_obj = dt.strptime(text.strip(), '%H:%M')
        return text.strip(), None
    except:
        return None, "Неверный формат. Используй HH:MM, например: 20:00"


def parse_ticket_type(text):
    """Parse ticket type: Name | Price | Quantity"""
    parts = [p.strip() for p in text.split('|')]
    if len(parts) != 3:
        return None, "Неверный формат. Используй: Название | Цена | Количество"

    name, price_str, qty_str = parts

    try:
        price = int(price_str)
        qty = int(qty_str)

        if price <= 0 or qty <= 0:
            return None, "Цена и количество должны быть больше нуля"

        return {
            'name': name,
            'price': price,
            'total': qty,
            'available': qty
        }, None
    except:
        return None, "Цена и количество должны быть числами"


def parse_coordinates(text):
    """Parse coordinates from text or Google Maps URL"""
    # Try Google Maps URL
    if 'google.com/maps' in text or 'maps.google.com' in text:
        match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', text)
        if match:
            return float(match.group(1)), float(match.group(2)), None

        match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', text)
        if match:
            return float(match.group(1)), float(match.group(2)), None

    # Try lat,lng format
    parts = text.split(',')
    if len(parts) == 2:
        try:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng, None
        except:
            pass

    return None, None, "Неверный формат. Используй: lat,lng или Google Maps URL"


# Dialog Handlers
def handle_event_creation_step(chat_id, text, session):
    """Handle event creation dialog (9 steps)"""
    import uuid

    step = session.get('step', 1)
    data = session.get('data', {})

    if step == 1:  # Title
        data['title'] = text.strip()
        session['step'] = 2
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "✅ Название принято!\n\n<b>Шаг 2/9:</b> Введи описание события")

    elif step == 2:  # Description
        data['description'] = text.strip()
        session['step'] = 3
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "✅ Описание принято!\n\n<b>Шаг 3/9:</b> Введи дату (YYYY-MM-DD)\n\nНапример: 2025-12-31")

    elif step == 3:  # Date
        date_str, error = parse_date(text)
        if error:
            return send_message_with_keyboard(chat_id, f"❌ {error}\n\nПопробуй еще раз:")
        data['date'] = date_str
        session['step'] = 4
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, f"✅ Дата принята: {date_str}\n\n<b>Шаг 4/9:</b> Введи время (HH:MM)\n\nНапример: 20:00")

    elif step == 4:  # Time
        time_str, error = parse_time(text)
        if error:
            return send_message_with_keyboard(chat_id, f"❌ {error}\n\nПопробуй еще раз:")
        data['time'] = time_str
        data['datetime'] = f"{data['date']}T{time_str}:00Z"
        session['step'] = 5
        session['data'] = data
        save_session(chat_id, session)

        # Show location selection
        locations = get_locations_list()
        buttons = []
        for loc in locations[:7]:  # Max 7 locations
            buttons.append([{'text': loc['name'], 'callback_data': f"loc_{loc['location_id']}"}])
        buttons.append([{'text': '➕ Создать новую локацию', 'callback_data': 'loc_new'}])

        return send_message_with_keyboard(chat_id, f"✅ Время принято: {time_str}\n\n<b>Шаг 5/9:</b> Выбери локацию:", buttons)

    elif step == 6:  # Number of ticket types
        # This is handled by callback, shouldn't reach here
        return True

    elif step == 7:  # Ticket types input
        if 'ticket_types' not in data:
            data['ticket_types'] = []
            data['ticket_count'] = data.get('ticket_count', 1)
            data['current_ticket'] = 1

        ticket, error = parse_ticket_type(text)
        if error:
            return send_message_with_keyboard(chat_id, f"❌ {error}\n\nПопробуй еще раз (билет #{data['current_ticket']}):")

        # Add ticket type
        data['ticket_types'].append(ticket)
        current = data['current_ticket']
        total = data['ticket_count']

        if current < total:
            # Ask for next ticket type
            data['current_ticket'] += 1
            session['data'] = data
            save_session(chat_id, session)
            return send_message_with_keyboard(chat_id, f"✅ Билет #{current} добавлен: {ticket['name']} - {ticket['price']}₪ ({ticket['total']} шт)\n\n<b>Билет #{data['current_ticket']}/{total}:</b>\nФормат: Название | Цена | Количество")
        else:
            # All tickets added, move to photo upload
            total_tickets = sum(t['total'] for t in data['ticket_types'])
            session['step'] = 8
            session['data'] = data
            session['temp_event_id'] = f"tmp-{uuid.uuid4().hex[:8]}"
            data['images'] = []
            save_session(chat_id, session)
            return send_message_with_keyboard(chat_id, f"✅ Все билеты добавлены! Всего мест: {total_tickets}\n\n<b>Шаг 8/9:</b> Загрузи фото события (или отправь /skip для пропуска)")

    elif step == 8:  # Photos - handled separately, skip command
        if text.strip().lower() == '/skip' or text.strip().lower() == '/next':
            session['step'] = 9
            save_session(chat_id, session)
            buttons = [
                [{'text': '✅ Да, за 48 часов', 'callback_data': 'refund_48'}],
                [{'text': '✅ Да, за 24 часа', 'callback_data': 'refund_24'}],
                [{'text': '❌ Нет возврата', 'callback_data': 'refund_no'}]
            ]
            return send_message_with_keyboard(chat_id, "Понял, фото не загружено.\n\n<b>Шаг 9/9:</b> Политика возврата билетов?", buttons)
        else:
            return send_message_with_keyboard(chat_id, "Отправь фото или /skip для пропуска, или /next когда закончишь загрузку")

    return False


def handle_location_creation_step(chat_id, text, session):
    """Handle location creation dialog (7 steps)"""
    import uuid
    import re

    step = session.get('step', 1)
    data = session.get('data', {})
    print(f"[LOCATION] Chat {chat_id}, current step: {step}, text: {text[:50]}")

    if step == 1:  # Name
        name = text.strip()
        data['name'] = name
        # Generate slug
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
        data['slug'] = slug[:50]
        session['step'] = 2
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, f"✅ Название: {name}\n(Slug: {slug})\n\n<b>Шаг 2/7:</b> Введи адрес\n\nФормат: Улица, Город\nНапример: Dizengoff 50, Tel Aviv")

    elif step == 2:  # Address
        parts = [p.strip() for p in text.split(',')]
        if len(parts) < 2:
            return send_message_with_keyboard(chat_id, "❌ Неверный формат адреса.\n\nИспользуй: Улица, Город")
        data['address'] = {'street': parts[0], 'city': parts[1]}
        session['step'] = 3
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, f"✅ Адрес принят!\n\n<b>Шаг 3/7:</b> Введи координаты\n\nФормат: lat,lng или Google Maps URL\nНапример: 32.0853,34.7818")

    elif step == 3:  # Coordinates
        lat, lng, error = parse_coordinates(text)
        if error:
            return send_message_with_keyboard(chat_id, f"❌ {error}\n\nПопробуй еще раз:")
        # Convert float to Decimal for DynamoDB
        from decimal import Decimal
        data['address']['coordinates'] = {'lat': Decimal(str(lat)), 'lng': Decimal(str(lng))}
        session['step'] = 4
        session['data'] = data
        print(f"[LOCATION] Saving session with step 4 for chat {chat_id}")
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, f"✅ Координаты приняты: {lat},{lng}\n\n<b>Шаг 4/7:</b> Введи вместимость (количество мест)")

    elif step == 4:  # Capacity
        try:
            capacity = int(text.strip())
            if capacity <= 0:
                raise ValueError()
            data['capacity'] = capacity
            session['step'] = 5
            session['data'] = data
            save_session(chat_id, session)
            return send_message_with_keyboard(chat_id, f"✅ Вместимость: {capacity} человек\n\n<b>Шаг 5/7:</b> Введи краткое описание локации")
        except:
            return send_message_with_keyboard(chat_id, "❌ Введи число больше нуля")

    elif step == 5:  # Short description
        data['short_description'] = text.strip()
        session['step'] = 6
        session['data'] = data
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "✅ Краткое описание принято!\n\n<b>Шаг 6/7:</b> Введи полное описание")

    elif step == 6:  # Full description
        data['description'] = text.strip()
        session['step'] = 7
        session['data'] = data
        session['temp_location_id'] = f"tmp-{uuid.uuid4().hex[:8]}"
        data['images'] = []
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "✅ Описание принято!\n\n<b>Шаг 7/7:</b> Загрузи фото локации (или /skip для пропуска)")

    elif step == 7:  # Photos - handled separately
        if text.strip().lower() == '/skip' or text.strip().lower() == '/next':
            # Create location via API
            location_data = {
                'name': data['name'],
                'slug': data['slug'],
                'address': data['address'],
                'capacity': data['capacity'],
                'description': data.get('description', ''),
                'media': {'photos': data.get('images', [])}
            }

            result = call_ticket_api('POST', '/api/locations', location_data)
            if result and 'location_id' in result:
                clear_session(chat_id)
                return send_message_with_keyboard(chat_id, f"✅ Локация создана!\n\nID: {result['location_id']}\nНазвание: {data['name']}")
            else:
                return send_message_with_keyboard(chat_id, "❌ Ошибка при создании локации. Попробуй позже или /ticket_cancel для отмены")
        else:
            return send_message_with_keyboard(chat_id, "Отправь фото или /skip для завершения без фото, или /next когда закончишь загрузку")

    return False


# Photo Handler
def handle_photo_message(chat_id, message, session):
    """Handle photo uploads during dialogs"""
    if not session:
        # This returns a dict but we're in lambda handler, need to handle it
        send_message_with_keyboard(chat_id, "Нет активного диалога. Используй /ticket_new_event или /ticket_new_location")
        return True

    if 'photo' not in message:
        return False

    photo = message['photo'][-1]  # Get largest photo
    file_id = photo['file_id']

    # Download photo
    file_url = get_telegram_file(file_id)
    if not file_url:
        send_message_with_keyboard(chat_id, "❌ Ошибка при получении фото. Попробуй еще раз.")
        return True

    photo_content = download_telegram_photo(file_url)
    if not photo_content:
        send_message_with_keyboard(chat_id, "❌ Ошибка при загрузке фото. Попробуй еще раз.")
        return True

    # Upload to S3
    import uuid
    session_type = session.get('type', '')
    temp_id = session.get('temp_event_id' if session_type == 'event_creation' else 'temp_location_id', uuid.uuid4().hex[:8])
    photo_name = f"{uuid.uuid4().hex[:12]}.jpg"

    if session_type == 'event_creation':
        s3_key = f"events/{temp_id}/{photo_name}"
    elif session_type == 'location_creation':
        s3_key = f"locations/{temp_id}/{photo_name}"
    else:
        return False

    s3_url = upload_photo_to_s3(photo_content, s3_key)
    if not s3_url:
        send_message_with_keyboard(chat_id, "❌ Ошибка при загрузке в S3. Попробуй еще раз.")
        return True

    # Add to session data
    data = session.get('data', {})
    if 'images' not in data:
        data['images'] = []
    data['images'].append(s3_url)
    session['data'] = data
    save_session(chat_id, session)

    count = len(data['images'])
    send_message_with_keyboard(chat_id, f"✅ Фото #{count} загружено!\n\nЗагрузи еще фото или отправь /next для продолжения")
    return True


# Command Handlers
def handle_ticket_command(chat_id, text, session):
    """Route ticket-service commands"""
    if text == '/ticket_help':
        help_text = """
<b>📋 Билетная система - Команды:</b>

<b>Создание:</b>
/ticket_new_event - Создать событие
/ticket_new_location - Создать локацию

<b>Просмотр:</b>
/ticket_list_events - Список событий
/ticket_list_locations - Список локаций
/ticket_orders &lt;event_id&gt; - Заказы по событию
/ticket_stats &lt;event_id&gt; - Статистика продаж

<b>Другое:</b>
/ticket_cancel - Отменить текущий диалог
/ticket_help - Эта справка
        """
        return send_message_with_keyboard(chat_id, help_text)

    elif text == '/ticket_new_event':
        # Start event creation dialog
        clear_session(chat_id)
        session = {'type': 'event_creation', 'step': 1, 'data': {}}
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "<b>🎭 Создание события</b>\n\n<b>Шаг 1/9:</b> Введи название события")

    elif text == '/ticket_new_location':
        # Start location creation dialog
        clear_session(chat_id)
        session = {'type': 'location_creation', 'step': 1, 'data': {}}
        save_session(chat_id, session)
        return send_message_with_keyboard(chat_id, "<b>📍 Создание локации</b>\n\n<b>Шаг 1/7:</b> Введи название локации")

    elif text == '/ticket_cancel':
        clear_session(chat_id)
        if session:
            return send_message_with_keyboard(chat_id, "❌ Диалог отменен")
        else:
            return send_message_with_keyboard(chat_id, "Нет активного диалога")

    elif text == '/ticket_list_events':
        return show_events_list(chat_id)

    elif text == '/ticket_list_locations':
        return show_locations_list(chat_id)

    elif text.startswith('/ticket_orders'):
        parts = text.split()
        if len(parts) < 2:
            return send_message_with_keyboard(chat_id, "❌ Используй: /ticket_orders &lt;event_id&gt;")
        else:
            return show_event_orders(chat_id, parts[1])

    elif text.startswith('/ticket_stats'):
        parts = text.split()
        if len(parts) < 2:
            return send_message_with_keyboard(chat_id, "❌ Используй: /ticket_stats &lt;event_id&gt;")
        else:
            return show_event_stats(chat_id, parts[1])

    return None


def handle_callback_query(callback_query):
    """Handle inline keyboard button clicks"""
    chat_id = callback_query['message']['chat']['id']
    data = callback_query['data']
    callback_id = callback_query['id']

    # Get session
    session = get_session(chat_id)

    # Answer callback to remove loading state
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, json={'callback_query_id': callback_id})

    if data.startswith('loc_'):
        # Location selection
        if data == 'loc_new':
            # Start location creation
            old_session_data = session.get('data', {}) if session else {}
            clear_session(chat_id)
            new_session = {'type': 'location_creation', 'step': 1, 'data': {}, 'return_to_event': old_session_data}
            save_session(chat_id, new_session)
            send_message_with_keyboard(chat_id, "<b>📍 Создание локации</b>\n\n<b>Шаг 1/7:</b> Введи название локации")
        else:
            # Location selected
            location_id = data[4:]  # Remove 'loc_' prefix
            if session and session.get('type') == 'event_creation':
                session['data']['location_id'] = location_id
                session['step'] = 6
                save_session(chat_id, session)

                # Ask for number of ticket types
                buttons = [
                    [{'text': '1', 'callback_data': 'tickets_1'}],
                    [{'text': '2', 'callback_data': 'tickets_2'}],
                    [{'text': '3', 'callback_data': 'tickets_3'}]
                ]
                send_message_with_keyboard(chat_id, "✅ Локация выбрана!\n\n<b>Шаг 6/9:</b> Сколько типов билетов?", buttons)

    elif data.startswith('tickets_'):
        # Number of ticket types selected
        count = int(data.split('_')[1])
        if session and session.get('type') == 'event_creation':
            session['data']['ticket_count'] = count
            session['data']['ticket_types'] = []
            session['data']['current_ticket'] = 1
            session['step'] = 7
            save_session(chat_id, session)
            send_message_with_keyboard(chat_id, f"<b>Шаг 7/9:</b> Создаем {count} тип(а/ов) билетов\n\n<b>Билет #1/{count}:</b>\nФормат: Название | Цена | Количество\n\nПример: Обычный | 120 | 50")

    elif data.startswith('refund_'):
        # Refund policy selected
        if session and session.get('type') == 'event_creation':
            refund_type = data.split('_')[1]
            refund_policy = {}

            if refund_type == '48':
                refund_policy = {'enabled': True, 'hours_before': 48}
            elif refund_type == '24':
                refund_policy = {'enabled': True, 'hours_before': 24}
            else:
                refund_policy = {'enabled': False}

            session['data']['refund_policy'] = refund_policy

            # Show confirmation
            data_obj = session['data']
            summary = f"""
<b>📋 Проверь данные события:</b>

<b>Название:</b> {data_obj.get('title', '')}
<b>Описание:</b> {data_obj.get('description', '')}
<b>Дата и время:</b> {data_obj.get('date', '')} {data_obj.get('time', '')}
<b>Локация ID:</b> {data_obj.get('location_id', '')}
<b>Билеты:</b>
"""
            for i, ticket in enumerate(data_obj.get('ticket_types', []), 1):
                summary += f"  {i}. {ticket['name']}: {ticket['price']}₪ ({ticket['total']} шт)\n"

            total_seats = sum(t['total'] for t in data_obj.get('ticket_types', []))
            summary += f"\n<b>Всего мест:</b> {total_seats}"
            summary += f"\n<b>Фото:</b> {len(data_obj.get('images', []))} загружено"

            if refund_policy.get('enabled'):
                summary += f"\n<b>Возврат:</b> За {refund_policy['hours_before']} часов"
            else:
                summary += "\n<b>Возврат:</b> Нет"

            buttons = [
                [{'text': '✅ Создать', 'callback_data': 'event_create'}],
                [{'text': '❌ Отменить', 'callback_data': 'event_cancel'}]
            ]
            session['step'] = 9
            save_session(chat_id, session)
            send_message_with_keyboard(chat_id, summary, buttons)

    elif data == 'event_create':
        # Create event via API
        if session and session.get('type') == 'event_creation':
            event_data = {
                'title': session['data'].get('title', ''),
                'description': session['data'].get('description', ''),
                'date': session['data'].get('datetime', ''),
                'location_id': session['data'].get('location_id', ''),
                'ticket_types': session['data'].get('ticket_types', []),
                'images': session['data'].get('images', []),
                'refund_policy': session['data'].get('refund_policy', {'enabled': False}),
                'status': 'active'
            }

            result = call_ticket_api('POST', '/api/events', event_data)
            if result and 'event_id' in result:
                clear_session(chat_id)
                event_id = result['event_id']
                send_message_with_keyboard(chat_id, f"✅ <b>Событие создано!</b>\n\nID: {event_id}\nНазвание: {event_data['title']}")
            else:
                send_message_with_keyboard(chat_id, "❌ Ошибка при создании события. Попробуй позже.")

    elif data == 'event_cancel':
        clear_session(chat_id)
        send_message_with_keyboard(chat_id, "❌ Создание события отменено")

    return {'statusCode': 200}


# Display Functions
def show_events_list(chat_id):
    """Show list of all events"""
    events = get_events_list()
    if not events:
        return send_message_with_keyboard(chat_id, "📋 Событий пока нет")

    text = "<b>📋 Список событий:</b>\n\n"
    for event in events[:10]:  # Show first 10
        text += f"<b>{event.get('title', 'Без названия')}</b>\n"
        text += f"ID: <code>{event.get('event_id', '')}</code>\n"
        text += f"Дата: {event.get('date', 'Не указана')}\n"
        text += f"Статус: {event.get('status', '')}\n\n"

    return send_message_with_keyboard(chat_id, text)


def show_locations_list(chat_id):
    """Show list of all locations"""
    locations = get_locations_list()
    if not locations:
        return send_message_with_keyboard(chat_id, "📍 Локаций пока нет")

    text = "<b>📍 Список локаций:</b>\n\n"
    for loc in locations[:10]:
        text += f"<b>{loc.get('name', 'Без названия')}</b>\n"
        text += f"ID: <code>{loc.get('location_id', '')}</code>\n"
        text += f"Вместимость: {loc.get('capacity', 0)} чел\n\n"

    return send_message_with_keyboard(chat_id, text)


def show_event_orders(chat_id, event_id):
    """Show orders for specific event"""
    result = call_ticket_api('GET', f'/api/orders?event_id={event_id}')
    if not result or 'orders' not in result:
        return send_message_with_keyboard(chat_id, "❌ Не удалось получить заказы")

    orders = result['orders']
    if not orders:
        return send_message_with_keyboard(chat_id, f"📦 Заказов для события {event_id} пока нет")

    total_revenue = sum(o.get('total_amount', 0) for o in orders)
    total_tickets = sum(sum(t.get('quantity', 0) for t in o.get('tickets', [])) for o in orders)

    text = f"<b>📦 Заказы для {event_id}:</b>\n\n"
    text += f"<b>Всего заказов:</b> {len(orders)}\n"
    text += f"<b>Всего билетов:</b> {total_tickets}\n"
    text += f"<b>Выручка:</b> {total_revenue}₪\n\n"

    text += "<b>Последние 5 заказов:</b>\n"
    for order in orders[:5]:
        text += f"\nID: <code>{order.get('order_id', '')}</code>\n"
        text += f"Сумма: {order.get('total_amount', 0)}₪\n"
        text += f"Статус: {order.get('status', '')}\n"

    return send_message_with_keyboard(chat_id, text)


def show_event_stats(chat_id, event_id):
    """Show statistics for specific event"""
    result = call_ticket_api('GET', f'/api/events/{event_id}')
    if not result or 'event_id' not in result:
        return send_message_with_keyboard(chat_id, "❌ Событие не найдено")

    event = result
    text = f"<b>📊 Статистика: {event.get('title', '')}</b>\n\n"

    ticket_types = event.get('ticket_types', [])
    for ticket in ticket_types:
        total = ticket.get('total', 0)
        available = ticket.get('available', 0)
        sold = total - available
        percentage = (sold / total * 100) if total > 0 else 0

        text += f"<b>{ticket.get('name', '')}:</b>\n"
        text += f"  Продано: {sold}/{total} ({percentage:.1f}%)\n"
        text += f"  Цена: {ticket.get('price', 0)}₪\n"
        text += f"  Выручка: {sold * ticket.get('price', 0)}₪\n\n"

    total_capacity = sum(t.get('total', 0) for t in ticket_types)
    total_available = sum(t.get('available', 0) for t in ticket_types)
    total_sold = total_capacity - total_available
    total_revenue = sum((t.get('total', 0) - t.get('available', 0)) * t.get('price', 0) for t in ticket_types)
    potential_revenue = sum(t.get('total', 0) * t.get('price', 0) for t in ticket_types)

    text += f"<b>Итого:</b>\n"
    text += f"Продано билетов: {total_sold}/{total_capacity}\n"
    text += f"Текущая выручка: {total_revenue}₪\n"
    text += f"Потенциальная выручка: {potential_revenue}₪\n"

    return send_message_with_keyboard(chat_id, text)


def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])

        # Handle callback query (inline keyboard buttons)
        if 'callback_query' in body:
            return handle_callback_query(body['callback_query'])

        if 'message' not in body:
            return {'statusCode': 200}

        message = body['message']
        chat_id = message['chat']['id']

        username = message.get('from', {}).get('username', '')
        if username not in ALLOWED_USERS:
            return send_telegram_message(chat_id, '🚫 У вас нет доступа к этому боту')

        # Check for active session
        session = get_session(chat_id)

        # Handle photo uploads
        if 'photo' in message:
            if handle_photo_message(chat_id, message, session):
                return {'statusCode': 200}

        text = message.get('text', '')

        # Handle ticket-service commands
        if text.startswith('/ticket'):
            result = handle_ticket_command(chat_id, text, session)
            if result:
                return result
            return {'statusCode': 200}

        # Continue active dialog session
        if session:
            if session.get('type') == 'event_creation':
                result = handle_event_creation_step(chat_id, text, session)
                return result if result else {'statusCode': 200}
            elif session.get('type') == 'location_creation':
                result = handle_location_creation_step(chat_id, text, session)
                return result if result else {'statusCode': 200}

        # Existing Notion commands below...

        if text.startswith('/add'):
            parts = text.split(' ', 2)

            if len(parts) < 3:
                return send_telegram_message(
                    chat_id,
                    '❌ Неверный формат!\n\nИспользуй:\n/add YYYY-MM-DD Описание https://ссылка'
                )

            _, date, rest = parts

            words = rest.split()
            if not words:
                return send_telegram_message(
                    chat_id,
                    '❌ Неверный формат!\n\nИспользуй:\n/add YYYY-MM-DD Описание https://ссылка'
                )

            url = words[-1]
            description = ' '.join(words[:-1])

            try:
                datetime.fromisoformat(date)
            except:
                return send_telegram_message(chat_id, '❌ Неверный формат даты! Используй YYYY-MM-DD')

            if not url.startswith('http'):
                return send_telegram_message(chat_id, '❌ Ссылка должна начинаться с http:// или https://')

            if not description:
                return send_telegram_message(chat_id, '❌ Добавь описание события!')

            if check_event_exists(url):
                return send_telegram_message(chat_id, '⚠️ Событие с такой ссылкой уже существует!')

            success = add_event_to_notion(description, date, url)

            if success:
                deleted = delete_old_events()
                trigger_site_regeneration()  # Асинхронно обновляем сайт

                msg = f'✅ Событие добавлено!\n\n📅 {date}\n📝 {description}\n🔗 {url}'
                if deleted:
                    msg += f'\n\n🗑 Удалено устаревших событий: {deleted}'
                msg += f'\n\n🌐 Сайт обновляется...'
                return send_telegram_message(chat_id, msg)
            else:
                return send_telegram_message(chat_id, '❌ Ошибка при добавлении события')

        elif text.startswith('/delete'):
            # Парсим: /delete https://example.com
            parts = text.split(' ', 1)

            if len(parts) < 2:
                return send_telegram_message(
                    chat_id,
                    '❌ Неверный формат!\n\nИспользуй:\n/delete https://ссылка'
                )

            url = parts[1].strip()

            if not url.startswith('http'):
                return send_telegram_message(chat_id, '❌ Ссылка должна начинаться с http:// или https://')

            success, result = delete_event_by_url(url)

            if success:
                trigger_site_regeneration()
                return send_telegram_message(
                    chat_id,
                    f'✅ Событие удалено!\n\n📝 {result}\n\n🌐 Сайт обновляется...'
                )
            else:
                return send_telegram_message(chat_id, f'❌ {result}')

        elif text == '/start' or text == '/help':
            help_text = """
👋 Привет! Я бот для управления событиями.

<b>Notion события:</b>
/add YYYY-MM-DD Описание https://ссылка - добавить событие
/delete https://ссылка - удалить событие
/refresh - обновить сайт вручную

<b>Билетная система:</b>
/ticket_help - Справка по билетам
/ticket_new_event - Создать событие с билетами
/ticket_new_location - Создать локацию

/help - показать эту справку
            """
            send_message_with_keyboard(chat_id, help_text)
            return {'statusCode': 200}

        elif text == '/refresh':
            success = trigger_site_regeneration()
            if success:
                return send_telegram_message(chat_id, '✅ Сайт обновляется...')
            else:
                return send_telegram_message(chat_id, '❌ Ошибка при обновлении сайта')

        else:
            return send_telegram_message(chat_id, 'Используй /help для списка команд')

    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 200}