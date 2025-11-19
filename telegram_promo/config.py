"""
Конфигурация для скриншотов и постинга в Telegram
"""

import os

# Telegram Bot Configuration
# Получите токен от @BotFather в Telegram
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# ID чата куда постить
# Чтобы получить CHAT_ID:
# 1. Добавьте бота в чат
# 2. Отправьте любое сообщение в чат
# 3. Откройте https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
# 4. Найдите "chat":{"id": -XXXXXXXXX}
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID_HERE')

# Notion API Configuration
# Используются те же переменные окружения что и для основного сайта
NOTION_TOKEN = os.environ.get('NOTION_TOKEN', '')
TALENTS_DB_ID = os.environ.get('TALENTS_DB_ID', '')
PRODUCTS_DB_ID = os.environ.get('PRODUCTS_DB_ID', '')

# URLs
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DONATE_SITE_URL = "https://donate.yallabalagan.org"

# Screenshot Configuration
SCREENSHOTS_DIR = "screenshots"
VIEWPORT_WIDTH = 1080  # Ширина для соцсетей
VIEWPORT_HEIGHT = 1920  # Высота viewport

# Template для сообщений в Telegram
MESSAGE_TEMPLATE = "{talent_name} - поддержи на {site_url}/talent/{talent_slug}/"

# Задержка между скриншотами (секунды)
SCREENSHOT_DELAY = 1

# Задержка между постами в Telegram (секунды)
POST_DELAY = 2
