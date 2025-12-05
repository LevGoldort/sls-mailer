import json
import os
import requests
from datetime import datetime
import boto3

NOTION_TOKEN = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID = os.environ['NOTION_DATABASE_ID']
ALLOWED_USERS = os.environ.get('ALLOWED_USERS', '').split(',')
SITE_GENERATOR_LAMBDA = os.environ['SITE_GENERATOR_LAMBDA']

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

lambda_client = boto3.client('lambda')


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
            InvocationType='Event',
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

    page_id = results[0]['id']

    delete_response = requests.patch(
        f"{NOTION_API_URL}/pages/{page_id}",
        headers=notion_headers(),
        json={"archived": True}
    )

    if delete_response.status_code == 200:
        title_prop = results[0]['properties'].get('Name', {}).get('title', [])
        title = title_prop[0]['text']['content'] if title_prop else 'Событие'
        return True, title
    else:
        return False, "Ошибка при удалении"


def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])

        if 'message' not in body:
            return {'statusCode': 200}

        message = body['message']
        chat_id = message['chat']['id']

        username = message.get('from', {}).get('username', '')
        if username not in ALLOWED_USERS:
            return send_telegram_message(chat_id, '🚫 У вас нет доступа к этому боту')

        text = message.get('text', '')

        if text.startswith('/add'):
            parts = text.split(' ', 2)

            if len(parts) < 3:
                return send_telegram_message(
                    chat_id,
                    '❌ Неверный формат!\n\nИспользуй:\n/add YYYY-MM-DD Описание https://ссылка'
                )

            _, date, rest = parts
            print(f"DEBUG: Received date from Telegram: '{date}'")

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
                trigger_site_regeneration()

                msg = f'✅ Событие добавлено!\n\n📅 {date}\n📝 {description}\n🔗 {url}'
                if deleted:
                    msg += f'\n\n🗑 Удалено устаревших событий: {deleted}'
                msg += f'\n\n🌐 Сайт обновляется...'
                return send_telegram_message(chat_id, msg)
            else:
                return send_telegram_message(chat_id, '❌ Ошибка при добавлении события')

        elif text.startswith('/delete'):
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

<b>Команды:</b>
/add YYYY-MM-DD Описание https://ссылка - добавить событие
/delete https://ссылка - удалить событие
/refresh - обновить сайт вручную
/help - показать эту справку
            """
            return send_telegram_message(chat_id, help_text)

        elif text == '/refresh':
            deleted = delete_old_events()
            success = trigger_site_regeneration()
            if success:
                msg = '✅ Сайт обновляется...'
                if deleted:
                    msg = f'✅ Удалено устаревших событий: {deleted}\n\n🌐 Сайт обновляется...'
                return send_telegram_message(chat_id, msg)
            else:
                return send_telegram_message(chat_id, '❌ Ошибка при обновлении сайта')

        else:
            return send_telegram_message(chat_id, 'Используй /help для списка команд')

    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 200}
