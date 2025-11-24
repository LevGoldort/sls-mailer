import json
import os
import requests
import boto3
import random
import string
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# Environment variables
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
NOTION_TOKEN = os.environ['NOTION_TOKEN']
ORDERS_DB_ID = os.environ['ORDERS_DB_ID']
PRODUCTS_DB_ID = os.environ['PRODUCTS_DB_ID']
TALENTS_DB_ID = os.environ['TALENTS_DB_ID']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
TELEGRAM_PRODUCTS_CHANNEL = os.environ['TELEGRAM_PRODUCTS_CHANNEL']
ADMIN_USERNAMES = os.environ.get('ADMIN_USERNAMES', '').split(',')
DONATE_SITE_LAMBDA = os.environ.get('DONATE_SITE_LAMBDA', 'donate-site-generator')
TELEGRAM_PRODUCTS_CHANNEL_USERNAME = os.environ['TELEGRAM_PRODUCTS_CHANNEL_USERNAME']

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')


def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def send_telegram_message(chat_id, text, parse_mode='HTML'):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None


def is_admin(username):
    """Проверяет является ли пользователь администратором"""
    if not username:
        return False

    admin_list = [name.strip() for name in ADMIN_USERNAMES if name.strip()]
    return username.lower() in [name.lower() for name in admin_list]


def get_text_from_rich_text(rich_text_array):
    """Извлекает текст из Notion rich_text"""
    if not rich_text_array:
        return ""
    return "".join([t.get('plain_text', '') for t in rich_text_array])


def get_url_from_files(files_array):
    """Извлекает URL из Notion files property"""
    if not files_array:
        return ""
    if len(files_array) == 0:
        return ""

    file_obj = files_array[0]
    if 'file' in file_obj:
        return file_obj['file'].get('url', '')
    elif 'external' in file_obj:
        return file_obj['external'].get('url', '')

    return ""


def invoke_donate_site_generator():
    """Вызывает лямбду генерации сайта"""
    try:
        response = lambda_client.invoke(
            FunctionName=DONATE_SITE_LAMBDA,
            InvocationType='Event'
        )
        print(f"Invoked {DONATE_SITE_LAMBDA}: {response['StatusCode']}")
        return response['StatusCode'] == 202
    except Exception as e:
        print(f"Error invoking {DONATE_SITE_LAMBDA}: {e}")
        return False


def file_exists_on_s3(s3_key):
    """Проверяет существует ли файл на S3"""
    try:
        s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return True
    except:
        return False


def download_image(url):
    """Скачивает изображение по URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        return None


def upload_to_s3(file_content, s3_key):
    """Загружает файл на S3"""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType='image/jpeg'
        )

        s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        print(f"Uploaded to S3: {s3_url}")
        return s3_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None


def update_notion_photo_url(page_id, new_url):
    """Обновляет Photo_URL в Notion"""
    try:
        response = requests.patch(
            f"{NOTION_API_URL}/pages/{page_id}",
            headers=notion_headers(),
            json={
                "properties": {
                    "Photo_URL": {
                        "url": new_url
                    }
                }
            },
            timeout=10
        )

        if response.status_code != 200:
            print(f"Notion update error: {response.text}")

        return response.status_code == 200
    except Exception as e:
        print(f"Error updating Notion: {e}")
        return False


def query_notion_database(database_id):
    """Получает все записи из базы Notion"""
    try:
        all_results = []
        has_more = True
        start_cursor = None

        while has_more:
            payload = {"page_size": 100}
            if start_cursor:
                payload["start_cursor"] = start_cursor

            response = requests.post(
                f"{NOTION_API_URL}/databases/{database_id}/query",
                headers=notion_headers(),
                json=payload,
                timeout=15
            )

            if response.status_code != 200:
                print(f"Error querying database: {response.text}")
                break

            data = response.json()
            all_results.extend(data.get('results', []))
            has_more = data.get('has_more', False)
            start_cursor = data.get('next_cursor')

        return all_results
    except Exception as e:
        print(f"Error in query_notion_database: {e}")
        return []


def process_photos_migration(database_id, folder_name):
    """Мигрирует фото из Notion в S3"""
    print(f"Processing {folder_name}...")

    pages = query_notion_database(database_id)
    print(f"Found {len(pages)} pages in {folder_name}")

    updated_count = 0

    for page in pages:
        page_id = page['id']
        props = page['properties']

        # Получаем Slug
        slug = get_text_from_rich_text(props.get('Slug', {}).get('rich_text', []))
        if not slug:
            print(f"Skipping page {page_id} - no slug")
            continue

        # Получаем Photo_URL
        photo_url = props.get('Photo_URL', {}).get('url', '')
        if not photo_url:
            print(f"Skipping {slug} - no photo URL")
            continue

        # Проверяем что это не наш S3
        if S3_BUCKET_NAME in photo_url:
            print(f"Skipping {slug} - already on S3")
            continue

        print(f"Processing {slug}: {photo_url}")

        s3_key = f"images/{folder_name}/{slug}.jpg"

        # Проверяем есть ли уже файл на S3
        if file_exists_on_s3(s3_key):
            s3_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
            print(f"{slug} already exists on S3, updating Notion only")
        else:
            # Скачиваем фото
            image_content = download_image(photo_url)
            if not image_content:
                print(f"Failed to download {slug}")
                continue

            # Загружаем на S3
            s3_url = upload_to_s3(image_content, s3_key)
            if not s3_url:
                print(f"Failed to upload {slug} to S3")
                continue

        # Обновляем в Notion
        if update_notion_photo_url(page_id, s3_url):
            updated_count += 1
            print(f"Updated {slug} successfully")
        else:
            print(f"Failed to update {slug} in Notion")

    return updated_count


def generate_activation_code():
    """Генерирует случайный код из 8 символов"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(8))


def create_code_image(code):
    """Создает изображение с кодом активации"""
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)

    # Качаем шрифт с S3 в /tmp
    font_path = '/tmp/font.ttf'
    if not os.path.exists(font_path):
        s3_client.download_file(S3_BUCKET_NAME, 'fonts/Roboto-Bold.ttf', font_path)
        print("Downloaded font from S3")

    font = ImageFont.truetype(font_path, 120)

    bbox = draw.textbbox((0, 0), code, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (800 - text_width) / 2
    y = (400 - text_height) / 2

    draw.text((x, y), code, fill='black', font=font)

    img_buffer = BytesIO()
    img.save(img_buffer, format='JPEG', quality=95)
    img_buffer.seek(0)

    return img_buffer


def send_photo_to_channel(image_buffer, price_stars, product_name, product_url):
    """Отправляет платное фото в канал с ценой в Stars"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPaidMedia"

    caption = (
        f'Товар: "{product_name}"\n\n'
        f'После покупки звездами введите код с картинки на сайте: {product_url}'
    )

    files = {
        'media': ('code.jpg', image_buffer, 'image/jpeg')
    }

    data = {
        'chat_id': TELEGRAM_PRODUCTS_CHANNEL,
        'star_count': price_stars,
        'caption': caption,
        'media': json.dumps([{
            'type': 'photo',
            'media': 'attach://media'
        }])
    }

    try:
        response = requests.post(url, data=data, files=files, timeout=15)

        if response.status_code != 200:
            print(f"Error sending paid photo: {response.text}")
            return None

        result = response.json()

        if not result.get('ok'):
            print(f"Telegram API error: {result}")
            return None

        message_id = result.get('result', {}).get('message_id')
        return message_id

    except Exception as e:
        print(f"Error sending paid photo: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_product_fields(page_id, price_stars, tg_code, tg_post_link):
    """Обновляет поля продукта в Notion"""
    try:
        properties = {
            "Price_Stars": {
                "number": price_stars
            },
            "Tg_Code": {
                "rich_text": [
                    {
                        "text": {
                            "content": tg_code
                        }
                    }
                ]
            }
        }

        if tg_post_link:
            properties["Tg_Post_link"] = {
                "url": tg_post_link
            }

        print(f"Updating page {page_id} with properties: {json.dumps(properties)}")

        response = requests.patch(
            f"{NOTION_API_URL}/pages/{page_id}",
            headers=notion_headers(),
            json={"properties": properties},
            timeout=10
        )

        print(f"Notion response status: {response.status_code}")
        print(f"Notion response: {response.text}")

        return response.status_code == 200
    except Exception as e:
        print(f"Error updating product fields: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_save_photos(chat_id, username):
    """Обрабатывает команду /save_photos"""
    if not is_admin(username):
        send_telegram_message(chat_id, "❌ У вас нет прав для использования этой команды")
        return

    send_telegram_message(chat_id, "🔄 Начинаю миграцию фотографий на S3...")

    # Обрабатываем Talents
    talents_updated = process_photos_migration(TALENTS_DB_ID, "talents")

    # Обрабатываем Products
    products_updated = process_photos_migration(PRODUCTS_DB_ID, "products")

    message = (
        f"✅ <b>Миграция завершена!</b>\n\n"
        f"Обновлено фотографий:\n"
        f"├ Таланты: {talents_updated}\n"
        f"└ Продукты: {products_updated}"
    )

    send_telegram_message(chat_id, message)


def handle_generate_codes(chat_id, username):
    """Обрабатывает команду /generate_codes"""
    if not is_admin(username):
        send_telegram_message(chat_id, "❌ У вас нет прав для использования этой команды")
        return

    send_telegram_message(chat_id, "🔄 Генерирую коды и публикую в канал...")

    # Получаем все продукты
    products = query_notion_database(PRODUCTS_DB_ID)
    print(f"Found {len(products)} products")

    added_count = 0

    for product in products:
        page_id = product['id']
        props = product['properties']

        # Проверяем есть ли уже Price_Stars
        price_stars = props.get('Price_Stars', {}).get('number')
        if price_stars:
            print(f"Skipping product {page_id} - already has Price_Stars")
            continue

        # Получаем цену в шекелях
        price_ils = props.get('Price_ILS', {}).get('number')
        if not price_ils:
            print(f"Skipping product {page_id} - no Price_ILS")
            continue

        # Получаем название для логов
        product_name = get_text_from_rich_text(props.get('Name', {}).get('title', []))
        slug = get_text_from_rich_text(props.get('Slug', {}).get('rich_text', []))
        product_url = f"https://donate.yallabalagan.org/product/{slug}"

        print(f"Processing product: {product_name}")

        # Считаем цену в Stars
        price_stars = int(price_ils * 18)

        # Генерируем код
        code = generate_activation_code()
        print(f"Generated code: {code}")

        # Создаем картинку
        image_buffer = create_code_image(code)

        # Отправляем в канал
        message_id = send_photo_to_channel(image_buffer, price_stars, product_name, product_url)

        # Формируем ссылку на пост
        tg_post_link = None
        if message_id:
            # Получаем username канала для формирования ссылки
            channel_username = TELEGRAM_PRODUCTS_CHANNEL.replace('@', '')
            tg_post_link = f"https://t.me/{TELEGRAM_PRODUCTS_CHANNEL_USERNAME}/{message_id}"
            print(f"Post link: {tg_post_link}")

        # Обновляем продукт в Notion
        if update_product_fields(page_id, price_stars, code, tg_post_link):
            added_count += 1
            print(f"Updated product {product_name} successfully")
        else:
            print(f"Failed to update product {product_name}")

    message = f"✅ <b>Готово!</b>\n\nДобавлено {added_count} товаров в канал"
    send_telegram_message(chat_id, message)


def get_orders():
    """Получает заказы из Notion со статусом New или In Progress"""
    try:
        # Сначала загружаем все продукты и таланты один раз
        print("Loading all products and talents...")
        all_products = query_notion_database(PRODUCTS_DB_ID)
        all_talents = query_notion_database(TALENTS_DB_ID)

        # Создаем словари для быстрого поиска
        products_map = {}
        for product in all_products:
            product_id = product['id']
            product_name = get_text_from_rich_text(product['properties'].get('Name', {}).get('title', []))
            talent_relation = product['properties'].get('Talent', {}).get('relation', [])
            talent_id = talent_relation[0]['id'] if talent_relation else None
            products_map[product_id] = {
                'name': product_name,
                'talent_id': talent_id
            }

        talents_map = {}
        for talent in all_talents:
            talent_id = talent['id']
            talent_name = get_text_from_rich_text(talent['properties'].get('Name', {}).get('title', []))
            talents_map[talent_id] = talent_name

        print(f"Loaded {len(products_map)} products and {len(talents_map)} talents")

        # Теперь загружаем заказы
        response = requests.post(
            f"{NOTION_API_URL}/databases/{ORDERS_DB_ID}/query",
            headers=notion_headers(),
            json={
                "filter": {
                    "or": [
                        {
                            "property": "Status",
                            "select": {
                                "equals": "New"
                            }
                        },
                        {
                            "property": "Status",
                            "select": {
                                "equals": "In Progress"
                            }
                        }
                    ]
                },
                "sorts": [
                    {
                        "property": "Created_Date",
                        "direction": "descending"
                    }
                ]
            },
            timeout=15
        )

        if response.status_code != 200:
            print(f"Error fetching orders: {response.text}")
            return []

        pages = response.json().get('results', [])
        orders = []

        for page in pages:
            props = page['properties']

            order_id = get_text_from_rich_text(props.get('ID', {}).get('title', []))

            product_relation = props.get('Product', {}).get('relation', [])
            product_id = product_relation[0]['id'] if product_relation else None

            # Быстрый поиск в словарях вместо API запросов
            product_name = ''
            talent_name = ''
            if product_id and product_id in products_map:
                product_name = products_map[product_id]['name']
                talent_id = products_map[product_id]['talent_id']
                if talent_id and talent_id in talents_map:
                    talent_name = talents_map[talent_id]

            created_time = page.get('created_time', '')
            created_date = ''
            if created_time:
                try:
                    dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                    created_date = dt.strftime('%d.%m.%Y %H:%M')
                except:
                    created_date = created_time

            status = props.get('Status', {}).get('select', {}).get('name', 'Unknown')

            # Получаем информацию о покупателях из Buyers_Info (JSON)
            buyers_info_text = get_text_from_rich_text(props.get('Buyers_Info', {}).get('rich_text', []))
            buyers_count = props.get('Buyers_Count', {}).get('number', 0)

            customer_name = ''
            customer_email = ''
            customer_telegram = ''
            customer_phone = ''

            # Парсим JSON из Buyers_Info
            if buyers_info_text:
                try:
                    buyers_list = json.loads(buyers_info_text)
                    if buyers_list and len(buyers_list) > 0:
                        # Берем данные первого покупателя для отображения
                        first_buyer = buyers_list[0]
                        customer_name = first_buyer.get('name', '')
                        customer_email = first_buyer.get('email', '')
                        customer_telegram = first_buyer.get('telegram', '')
                        customer_phone = first_buyer.get('phone', '')

                        # Если покупателей больше одного, добавляем инфо
                        if len(buyers_list) > 1:
                            customer_name = f"{customer_name} (+{len(buyers_list)-1} еще)"
                except json.JSONDecodeError:
                    print(f"Failed to parse Buyers_Info JSON for order {order_id}")

            print(f"Order {order_id}: {buyers_count} buyers, first: name='{customer_name}', email='{customer_email}', telegram='{customer_telegram}'")

            order = {
                'order_id': order_id,
                'product_name': product_name,
                'talent_name': talent_name,
                'created': created_date,
                'status': status,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'customer_telegram': customer_telegram,
                'customer_phone': customer_phone,
                'buyers_count': buyers_count
            }

            orders.append(order)

        return orders

    except Exception as e:
        print(f"Error getting orders: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_product_name(product_id):
    """Получает название продукта по ID"""
    try:
        response = requests.get(
            f"{NOTION_API_URL}/pages/{product_id}",
            headers=notion_headers(),
            timeout=10
        )

        if response.status_code == 200:
            page = response.json()
            props = page['properties']
            return get_text_from_rich_text(props.get('Name', {}).get('title', []))

        return 'Unknown Product'
    except:
        return 'Unknown Product'


def get_talent_from_product(product_id):
    """Получает имя таланта через связь Product -> Talent"""
    try:
        response = requests.get(
            f"{NOTION_API_URL}/pages/{product_id}",
            headers=notion_headers(),
            timeout=10
        )

        if response.status_code != 200:
            return 'Unknown Talent'

        page = response.json()
        props = page['properties']

        talent_relation = props.get('Talent', {}).get('relation', [])
        if not talent_relation:
            return 'Unknown Talent'

        talent_id = talent_relation[0]['id']

        response = requests.get(
            f"{NOTION_API_URL}/pages/{talent_id}",
            headers=notion_headers(),
            timeout=10
        )

        if response.status_code == 200:
            talent_page = response.json()
            talent_props = talent_page['properties']
            return get_text_from_rich_text(talent_props.get('Name', {}).get('title', []))

        return 'Unknown Talent'

    except Exception as e:
        print(f"Error getting talent: {e}")
        return 'Unknown Talent'


def format_orders_message(orders):
    """Форматирует список заказов для Telegram"""
    if not orders:
        return "📦 <b>Активных заказов нет</b>\n\nВсе заказы обработаны!"

    message = f"📦 <b>Активные заказы ({len(orders)})</b>\n\n"

    for order in orders:
        status_emoji = "🆕" if order['status'] == "New" else "⏳"

        message += f"{status_emoji} <b>{order['order_id']}</b>\n"
        message += f"├ Продукт: {order['product_name']}\n"
        message += f"├ Талант: {order['talent_name']}\n"
        message += f"├ Создан: {order['created']}\n"

        # Информация о покупателе
        customer_lines = []

        # Если это групповой заказ (больше 1 покупателя), показываем количество
        if order.get('buyers_count', 1) > 1:
            customer_lines.append(f"👥 Покупателей: {order['buyers_count']}")

        if order['customer_name']:
            customer_lines.append(f"Покупатель: {order['customer_name']}")
        if order['customer_email']:
            customer_lines.append(f"Email: {order['customer_email']}")
        if order['customer_phone']:
            customer_lines.append(f"Телефон: {order['customer_phone']}")
        if order['customer_telegram']:
            customer_lines.append(f"Telegram: {order['customer_telegram']}")

        # Если есть информация о покупателе, статус не последний
        if customer_lines:
            message += f"├ Статус: <i>{order['status']}</i>\n"
            # Добавляем строки с правильными символами
            for i, line in enumerate(customer_lines):
                if i == len(customer_lines) - 1:
                    # Последняя строка
                    message += f"└ {line}\n"
                else:
                    message += f"├ {line}\n"
        else:
            # Если нет информации о покупателе, статус последний
            message += f"└ Статус: <i>{order['status']}</i>\n"

        message += f"\n"

    return message


def handle_refresh_command(chat_id, username):
    """Обрабатывает команду /refresh"""
    if not is_admin(username):
        send_telegram_message(chat_id, "❌ У вас нет прав для использования этой команды")
        return

    send_telegram_message(chat_id, "🔄 Запускаю обновление сайта...")

    success = invoke_donate_site_generator()

    if success:
        send_telegram_message(
            chat_id,
            "✅ <b>Сайт обновляется!</b>\n\n"
            "Генерация займёт ~30-60 секунд.\n"
            "Сайт: https://donate.yallabalagan.org"
        )
    else:
        send_telegram_message(
            chat_id,
            "❌ <b>Ошибка при запуске обновления</b>\n\n"
            "Проверьте логи Lambda функции."
        )


def handle_orders_command(chat_id, username):
    """Обрабатывает команду /orders"""
    if not is_admin(username):
        send_telegram_message(chat_id, "❌ У вас нет прав для использования этой команды")
        return

    send_telegram_message(chat_id, "⏳ Загружаю заказы...")

    orders = get_orders()
    message = format_orders_message(orders)
    send_telegram_message(chat_id, message)


def handle_start_command(chat_id, username):
    """Обрабатывает команду /start"""
    is_authorized = is_admin(username)

    if is_authorized:
        message = (
            "👋 <b>Привет, админ!</b>\n\n"
            "Доступные команды:\n\n"
            "🔄 /refresh - Обновить сайт donate.yallabalagan.org\n"
            "📦 /orders - Показать активные заказы\n"
            "📸 /save_photos - Мигрировать фото на S3\n"
            "🎫 /generate_codes - Сгенерировать коды и опубликовать\n"
            "❓ /help - Показать это сообщение"
        )
    else:
        message = (
            "👋 Привет!\n\n"
            "❌ У вас нет доступа к этому боту.\n"
            f"Ваш username: @{username if username else 'неизвестно'}"
        )

    send_telegram_message(chat_id, message)


def handle_help_command(chat_id, username):
    """Обрабатывает команду /help"""
    handle_start_command(chat_id, username)


def lambda_handler(event, context):
    """Main handler для Telegram webhook"""
    print(f"Received event: {json.dumps(event)}")

    try:
        body = json.loads(event.get('body', '{}'))

        if 'message' not in body:
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Not a message, ignored'})
            }

        message = body['message']
        chat_id = message['chat']['id']
        username = message.get('from', {}).get('username', '')
        text = message.get('text', '')

        print(f"Message from @{username}: {text}")

        if text.startswith('/start'):
            handle_start_command(chat_id, username)

        elif text.startswith('/help'):
            handle_help_command(chat_id, username)

        elif text.startswith('/refresh'):
            handle_refresh_command(chat_id, username)

        elif text.startswith('/orders'):
            handle_orders_command(chat_id, username)

        elif text.startswith('/save_photos'):
            handle_save_photos(chat_id, username)

        elif text.startswith('/generate_codes'):
            handle_generate_codes(chat_id, username)

        else:
            if is_admin(username):
                send_telegram_message(
                    chat_id,
                    "❓ Неизвестная команда. Используй /help для списка команд."
                )

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'OK'})
        }

    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }