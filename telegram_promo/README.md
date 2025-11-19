# Telegram Product Cards Promo

Автоматизация создания скриншотов карточек товаров и постинга в Telegram для промо.

## 📋 Описание

Этот инструмент:
1. Открывает каждую страницу таланта на donate.yallabalagan.org
2. Делает скриншоты всех карточек товаров (каждую отдельно)
3. Постит скриншоты в Telegram чат с описанием и ссылкой на таланта

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
cd telegram_promo

# Создать виртуальное окружение (опционально, но рекомендуется)
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установить пакеты
pip install -r requirements.txt

# Установить браузер для Playwright
playwright install chromium
```

### 2. Настройка конфигурации

#### Вариант A: Переменные окружения (рекомендуется)

```bash
# Notion API (должны быть уже настроены для основного проекта)
export NOTION_TOKEN="your_notion_token"
export TALENTS_DB_ID="your_talents_database_id"
export PRODUCTS_DB_ID="your_products_database_id"

# Telegram Bot
export TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
export TELEGRAM_CHAT_ID="your_chat_id"
```

#### Вариант B: Редактирование config.py

Откройте `config.py` и замените:
- `YOUR_BOT_TOKEN_HERE` на токен вашего бота
- `YOUR_CHAT_ID_HERE` на ID чата куда постить

### 3. Получение Telegram Bot Token

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot` (или используйте существующего бота)
3. Следуйте инструкциям и получите токен
4. Сохраните токен в переменную окружения или config.py

### 4. Получение Chat ID

**Способ 1: Через bot**
1. Добавьте вашего бота в нужный чат
2. Отправьте любое сообщение в чат (например, "test")
3. Откройте в браузере:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. Найдите в ответе `"chat":{"id":-XXXXXXXXX}`
5. Скопируйте ID (со знаком минус если есть)

**Способ 2: Через специальных ботов**
1. Добавьте [@getidsbot](https://t.me/getidsbot) в ваш чат
2. Бот покажет Chat ID

### 5. Запуск

```bash
# Шаг 1: Создать скриншоты всех карточек товаров
python screenshot_products.py

# Шаг 2: Запостить скриншоты в Telegram
python telegram_poster.py
```

## 📁 Структура проекта

```
telegram_promo/
├── config.py                   # Конфигурация
├── screenshot_products.py      # Скрипт для создания скриншотов
├── telegram_poster.py          # Скрипт для постинга в Telegram
├── requirements.txt            # Python зависимости
├── README.md                   # Эта инструкция
└── screenshots/                # Папка со скриншотами (создается автоматически)
    ├── lev_product1.png
    ├── lev_product2.png
    └── ...
```

## 🔧 Настройка

### Параметры в config.py

```python
# Размер viewport для скриншотов
VIEWPORT_WIDTH = 1080   # Стандарт для соцсетей
VIEWPORT_HEIGHT = 1920

# Шаблон сообщения в Telegram
MESSAGE_TEMPLATE = "{talent_name} - поддержи на {site_url}/talent/{talent_slug}/"

# Задержки
SCREENSHOT_DELAY = 1  # секунд между скриншотами
POST_DELAY = 2        # секунд между постами в Telegram
```

## 📸 Как работает screenshot_products.py

1. Получает список всех активных талантов из Notion
2. Получает список всех активных продуктов из Notion
3. Для каждого таланта:
   - Открывает страницу `/talent/{slug}/`
   - Ждет полной загрузки
   - Находит все `.product-card` элементы
   - Делает скриншот каждой карточки отдельно
   - Сохраняет как `{talent_slug}_{product_slug}.png`

**Особенности:**
- Headless режим (браузер не открывается)
- Разрешение 1080px (оптимально для соцсетей)
- Автоматическое определение slug продукта из ссылки
- Прогресс-индикатор в консоли

## 📱 Как работает telegram_poster.py

1. Сканирует папку `screenshots/` и группирует файлы по талантам
2. Получает информацию о талантах из Notion (имя, slug)
3. Для каждого таланта:
   - Формирует текст сообщения по шаблону
   - Если 1 скриншот - отправляет как фото с caption
   - Если несколько - отправляет как media group (альбом)
   - Задержка между постами для избежания лимитов

**Формат сообщения:**
```
{Имя Таланта} - поддержи на donate.yallabalagan.org/talent/{slug}/
[прикрепленные скриншоты карточек товаров]
```

## ⚠️ Troubleshooting

### Ошибка: "Notion credentials not configured"
- Убедитесь что установлены переменные окружения `NOTION_TOKEN`, `TALENTS_DB_ID`, `PRODUCTS_DB_ID`
- Или отредактируйте config.py напрямую

### Ошибка: "Telegram bot token not configured"
- Получите токен от @BotFather
- Установите переменную окружения `TELEGRAM_BOT_TOKEN` или отредактируйте config.py

### Ошибка: "No product cards found on page"
- Проверьте что сайт доступен
- Убедитесь что у таланта есть активные продукты
- Проверьте CSS селектор `.product-card` на сайте

### Telegram Rate Limits
- Telegram имеет лимиты на отправку сообщений
- Увеличьте `POST_DELAY` в config.py если получаете ошибки

### Screenshots слишком большие/маленькие
- Измените `VIEWPORT_WIDTH` и `VIEWPORT_HEIGHT` в config.py
- Стандартные размеры для соцсетей: 1080x1920 (mobile), 1200x630 (desktop)

## 🎨 Кастомизация

### Изменить текст сообщения

Отредактируйте `MESSAGE_TEMPLATE` в config.py:
```python
MESSAGE_TEMPLATE = "🎭 {talent_name}\n\n💰 Поддержи на {site_url}/talent/{talent_slug}/\n\n#yallabalagan #donate"
```

### Изменить размер скриншотов

```python
VIEWPORT_WIDTH = 1200   # для desktop preview
VIEWPORT_HEIGHT = 800
```

### Постить в несколько чатов

Создайте копию telegram_poster.py и измените `CHAT_ID`, либо модифицируйте скрипт для работы с несколькими чатами.

## 📊 Вывод скриптов

### screenshot_products.py
```
============================================================
🚀 Starting product screenshots generation
============================================================
📁 Screenshots directory: /path/to/screenshots
📥 Fetching data from Notion...
✅ Found 10 active talents
✅ Found 25 active products

📸 Starting screenshots for 10 talents...

[1/10] Processing: Лев Гольдорт
  🌐 Opening https://donate.yallabalagan.org/talent/lev/
  ✓ Found 3 product cards on page
    ✓ Screenshot saved: screenshots/lev_tour.png
    ✓ Screenshot saved: screenshots/lev_consultation.png
    ✓ Screenshot saved: screenshots/lev_merch.png

...

============================================================
✅ COMPLETED!
============================================================
📊 Statistics:
  - Talents processed: 10
  - Total screenshots: 25
  - Location: /path/to/screenshots

💡 Next step: Run telegram_poster.py to post to Telegram
============================================================
```

### telegram_poster.py
```
============================================================
📱 Starting Telegram posting
============================================================
✅ Found screenshots for 10 talents
📥 Fetching talent information from Notion...

📤 Starting posting to chat -1001234567890...

[1/10] Лев Гольдорт
  📤 Posting 3 screenshots for Лев Гольдорт
  ✅ Posted successfully!
  ⏳ Waiting 2s before next post...

...

============================================================
✅ COMPLETED!
============================================================
📊 Statistics:
  - Successfully posted: 10
  - Failed: 0
  - Total: 10
============================================================
```

## 🔐 Безопасность

- **НЕ** коммитьте токены и credentials в git
- Используйте переменные окружения
- Добавьте `config.py` в `.gitignore` если храните там секреты
- Храните токены в безопасном месте (1Password, Bitwarden, etc.)

## 📝 Примечания

- Это одноразовый скрипт для промо-кампании
- Скриншоты сохраняются локально в папке `screenshots/`
- Можно запускать скрипты многократно (скриншоты перезапишутся)
- Telegram posts не дублируются автоматически - контролируйте вручную

## 🆘 Поддержка

Вопросы и проблемы:
- Email: yalla@yallabalagan.org
- Telegram: @yallabalagan

---

Сделано с ❤️ для Ялла, Балаган
