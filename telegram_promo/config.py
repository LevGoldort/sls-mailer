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

# Mobile viewport settings (iPhone 13/14 Pro)
# Используем мобильную версию для более крупных заголовков и текста
VIEWPORT_WIDTH = 393   # iPhone 13/14 Pro ширина
VIEWPORT_HEIGHT = 852  # iPhone 13/14 Pro высота

# Mobile User Agent (iOS 17 Safari)
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# Template для сообщений в Telegram
MESSAGE_TEMPLATE = """Привет, {talent_name}! 
Наконец-то запускаем донатный сайт для Яллы! Буду писать тебе когда что-то купят из твоих. 
Я анонсирую запуск в районе 14-00, буду благодарен если можешь поддержать у себя в соц.сетях или каналах или вообще где угодно :)
Вот ссылка на тебя на сайте: на {site_url}/talent/{talent_slug}/
И прилагаю фотки карточек как они на сайте, можно юзать в сторис или еще где-то.

P.S. Сорри что я пересылаю сообщение от бота, просто сгенерил текст, ссылки и картинки для каждого таланта на сайте, чтобы не помереть руками скринить! Спасибо за участие!!!"""


# Задержка между скриншотами (секунды)
SCREENSHOT_DELAY = 1

# Задержка между постами в Telegram (секунды)
# Увеличено до 10 секунд чтобы избежать flood control
POST_DELAY = 10
