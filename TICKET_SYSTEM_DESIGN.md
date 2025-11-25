# Билетный Сервис - System Design

## Обзор системы

Билетный сервис для продажи билетов на мероприятия с интеграцией платежей через All-Pay, управлением локаций и событий.

---

## 1. Архитектура высокого уровня

```
┌─────────────────┐
│  Пользователи   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼────┐ ┌─▼──────────┐
│ Сайт   │ │ Админ      │
│ events │ │ (Telegram  │
└───┬────┘ │ Bot)       │
    │      └─┬──────────┘
    │        │
┌───▼────────▼─────────┐
│   API Gateway        │
│   (API Lambda)       │
└──┬─────────┬─────┬───┘
   │         │     │
   │    ┌────▼──┐  │
   │    │ Media │  │
   │    │ S3    │  │
┌──▼────▼───────▼──────┐
│   DynamoDB           │
│  ┌─────────────────┐ │
│  │ Events          │ │
│  │ Locations       │ │
│  │ Tickets/Orders  │ │
│  └─────────────────┘ │
└──────────┬───────────┘
           │
     ┌─────▼──────┐
     │  All-Pay   │
     │  Payment   │
     └─────┬──────┘
           │
     ┌─────▼──────────┐
     │  Бухгалтерия   │
     │  (чеки)        │
     └────────────────┘
```

---

## 2. Структура данных

### Events Table (DynamoDB)
```javascript
{
  PK: "EVENT#<event_id>",
  SK: "METADATA",

  event_id: "uuid",
  title: "Название события",
  description: "Описание",
  date: "2025-01-15T19:00:00Z",

  location_id: "uuid",  // Связь с локацией

  // Типы билетов (может быть несколько)
  ticket_types: [
    {
      id: "regular",
      name: "Обычный",
      price: 120,
      total: 80,
      available: 60
    },
    {
      id: "vip",
      name: "VIP",
      price: 200,
      total: 20,
      available: 15
    }
  ],
  currency: "ILS",

  // Для повторяющихся событий
  recurrence: {
    enabled: false,
    pattern: "weekly|monthly",  // еженедельно, ежемесячно
    interval: 1,                // каждую 1 неделю
    day_of_week: 5,            // пятница (0=пн, 6=вс)
    end_date: "2025-12-31"     // до какой даты повторять
  },

  images: ["s3://path/to/image1.jpg"],
  status: "active|sold_out|cancelled",

  // Политика возврата
  refund_policy: {
    enabled: true,
    hours_before: 48  // автоматический возврат за 48 часов
  },

  created_at: "timestamp",
  updated_at: "timestamp"
}
```

### Locations Table (DynamoDB)
```javascript
{
  PK: "LOCATION#<location_id>",
  SK: "METADATA",

  location_id: "uuid",
  name: "Название локации",
  address: {
    street: "Dizengoff 100",
    city: "Tel Aviv",
    coordinates: {
      lat: 32.0853,
      lng: 34.7818
    }
  },

  description: "Описание локации (полное, для страницы локации)",
  short_description: "Уютный бар в центре Тель-Авива",  // Для страницы события
  capacity: 150,

  featured_image: "s3://bucket/locations/loc123/main.jpg",  // Главное фото

  media: {
    photos: [
      "s3://bucket/locations/loc123/photo1.jpg",
      "s3://bucket/locations/loc123/photo2.jpg"
    ],
    videos: [
      "https://youtube.com/watch?v=xxxxx"
    ]
  },

  // Паркинги - важная инфа, люди всегда спрашивают
  // Упрощенная версия - только координаты и описание
  parkings: [
    {
      description: "Подземная парковка в 100 метрах от заведения, вход с улицы Дизенгоф",
      coordinates: {
        lat: 32.0854,
        lng: 34.7820
      },
      google_maps_url: "https://maps.google.com/?q=32.0854,34.7820"  // опционально
    }
  ],

  amenities: ["bar", "wifi", "accessible"],
  contact: {
    phone: "+972-xxx-xxxx",
    email: "info@location.com"
  },

  slug: "dizengoff-center",  // для URL

  created_at: "timestamp"
}
```

### Tickets/Orders Table (DynamoDB)
```javascript
{
  PK: "ORDER#<order_id>",
  SK: "METADATA",

  order_id: "uuid",
  event_id: "uuid",

  customer: {
    name: "Имя",
    email: "email@example.com",
    phone: "+972-xxx-xxxx"
  },

  // Билеты разных типов в одном заказе
  tickets: [
    {
      type_id: "regular",
      type_name: "Обычный",
      quantity: 2,
      price_per_ticket: 120
    },
    {
      type_id: "vip",
      type_name: "VIP",
      quantity: 1,
      price_per_ticket: 200
    }
  ],

  total_amount: 440,
  currency: "ILS",

  payment: {
    status: "pending|completed|failed|refunded",
    allpay_transaction_id: "xxxxx",
    paid_at: "timestamp",
    refund: {
      requested_at: "timestamp",
      processed_at: "timestamp",
      amount: 440,
      reason: "customer_request|event_cancelled"
    }
  },

  qr_codes: [
    {
      code: "YBEV-2025-XXXX-1",
      ticket_type: "regular",
      s3_url: "s3://path/to/qrcode1.png",
      scanned: false,
      scanned_at: null
    },
    {
      code: "YBEV-2025-XXXX-2",
      ticket_type: "regular",
      s3_url: "s3://path/to/qrcode2.png",
      scanned: false,
      scanned_at: null
    },
    {
      code: "YBEV-2025-XXXX-3",
      ticket_type: "vip",
      s3_url: "s3://path/to/qrcode3.png",
      scanned: false,
      scanned_at: null
    }
  ],

  // Уведомления
  notifications: {
    email_sent: true,
    sms_sent: true,
    reminder_sent: false
  },

  created_at: "timestamp"
}

// Secondary index для поиска по событию
{
  GSI_PK: "EVENT#<event_id>",
  GSI_SK: "ORDER#<order_id>"
}

// Secondary index для поиска по email
{
  GSI_PK: "EMAIL#<email>",
  GSI_SK: "ORDER#<order_id>"
}
```

---

## 3. API Endpoints

### Events API
```
GET    /api/events                    - Список всех событий
GET    /api/events/:id                - Детали события
POST   /api/events                    - Создать событие (admin)
PUT    /api/events/:id                - Обновить событие (admin)
DELETE /api/events/:id                - Удалить событие (admin)
GET    /api/events/:id/availability   - Проверить доступность билетов
```

### Locations API
```
GET    /api/locations                 - Список всех локаций
GET    /api/locations/:id             - Детали локации
GET    /api/locations/:slug           - Детали по slug
POST   /api/locations                 - Создать локацию (admin)
PUT    /api/locations/:id             - Обновить локацию (admin)
DELETE /api/locations/:id             - Удалить локацию (admin)
POST   /api/locations/:id/media       - Загрузить фото/видео (admin)
```

### Tickets/Orders API
```
POST   /api/orders                    - Создать заказ (купить билет)
GET    /api/orders/:id                - Детали заказа
GET    /api/orders/verify/:ticket_code - Проверить билет (для входа)
POST   /api/orders/:id/refund         - Запросить возврат (авто или admin)
GET    /api/orders/:id/can-refund     - Проверить возможность возврата
GET    /api/orders/customer/:email    - Все билеты клиента
POST   /api/orders/:id/resend         - Переслать билеты на email/SMS
```

### Media API
```
POST   /api/media/upload              - Загрузить изображение
GET    /api/media/:id                 - Получить изображение
```

---

## 4. User Flow: Покупка билета

```
┌─────────┐
│ User    │
│ выбирает│
│ событие │
└────┬────┘
     │
┌────▼─────────────────┐
│ Страница события     │
│ - Описание           │
│ - Дата/время         │
│ - Локация (ссылка)   │
│ - Цена               │
│ - Кнопка "Купить"    │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ Форма заказа         │
│ - Имя                │
│ - Email              │
│ - Телефон            │
│ - Количество билетов │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ POST /api/orders     │
│ Создается заказ      │
│ Status: pending      │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ Redirect → All-Pay   │
│ Платежная форма      │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ Webhook от All-Pay   │
│ Payment completed    │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ Lambda:              │
│ - Обновить статус    │
│ - Сгенерировать QR   │
│ - Уменьшить tickets  │
│ - Отправить email    │
└────┬─────────────────┘
     │
┌────▼─────────────────┐
│ Email клиенту:       │
│ - Билет с QR кодом   │
│ - Детали события     │
│ - Инструкции         │
└──────────────────────┘
```

---

## 5. Admin Flow: Создание события (через Telegram Bot)

```
┌───────────────┐
│ Admin         │
│ /create_event │
└───────┬───────┘
        │
┌───────▼──────────────┐
│ Bot: Название?       │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Admin: "Stand-up"    │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Описание?       │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Admin: текст         │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Дата? (YYYY-MM-DD)│
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Время? (HH:MM)  │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Выбери локацию  │
│ [Кнопки с локациями] │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Цена билета?    │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Всего билетов?  │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Загрузи фото    │
│ (optional)           │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: Подтверждение   │
│ [Preview события]    │
│ Создать? Да/Нет      │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ POST /api/events     │
│ Создание в БД        │
└───────┬──────────────┘
        │
┌───────▼──────────────┐
│ Bot: ✅ Создано!     │
│ URL: yallabalagan... │
└──────────────────────┘
```

---

## 6. Технический стек

### Frontend
- **Генератор сайта**: Lambda (Python) - генерирует статические HTML
- **Хостинг**: S3 + CloudFront
- **CSS Framework**: Tailwind или Bootstrap
- **JS**: Vanilla JS или Alpine.js (легковесно)

### Backend
- **API**: AWS Lambda + API Gateway
- **Database**: DynamoDB
  - Events table
  - Locations table
  - Orders table
- **Storage**: S3
  - Event images
  - Location photos
  - QR codes
  - Generated tickets (PDF)
- **Auth**: Lambda Authorizer для admin endpoints

### Admin
- **Telegram Bot**: AWS Lambda (Python)
  - python-telegram-bot library
  - Webhook от Telegram → Lambda
  - Вся логика создания/редактирования событий

### Integrations
- **All-Pay**:
  - Payment page redirect
  - Webhook для подтверждения оплаты
  - API для проверки статуса платежа
  - Refund API для возвратов
- **Email**: AWS SES
  - Отправка билетов
  - Напоминания о событиях
  - Подтверждения заказов
- **SMS**: (сервис TBD - найдешь)
  - Подтверждение покупки
  - QR код и ссылка на билет
  - Напоминание за день до события

---

## 7. Страницы сайта

### Главная страница (`/`)
- Список предстоящих событий
- Фильтры: дата, локация, тип
- Search

### Страница события (`/events/<event_id>`)
- Фото события
- Название, описание
- Дата, время
- Локация (ссылка на страницу локации)
- Карта
- Цена билета
- Кнопка "Купить билет"
- Счетчик доступных билетов

### Страница локации (`/locations/<slug>`)
- Название
- Описание
- Адрес + карта
- Фотогалерея (карусель)
- Видео с YouTube (embed)
- Вместимость
- Удобства (parking, bar, wifi, etc)
- Контакты
- Список предстоящих событий в этой локации

### Страница заказа (`/checkout/<event_id>`)
- Форма данных клиента
- Выбор количества билетов
- Итоговая сумма
- Кнопка "Оплатить" → redirect на All-Pay

### Страница билета (`/tickets/<ticket_code>`)
- QR код
- Детали события
- Инструкции для входа
- Кнопка "Добавить в календарь"
- Кнопка "Скачать PDF"

---

## 8. Безопасность

### Admin endpoints
- JWT токены или API ключи
- Telegram Bot: whitelist admin user IDs
- Rate limiting на API

### Payment
- HTTPS only
- All-Pay обрабатывает платежные данные (PCI compliance)
- Webhook signature verification

### Tickets
- QR код с подписью (JWT или HMAC)
- Одноразовое сканирование
- Проверка в момент входа

---

## 9. Масштабирование

### Phase 1: MVP
- Одна Lambda для всего API
- DynamoDB с on-demand pricing
- S3 для статики
- Telegram Bot для админки

### Phase 2: Growth
- Разделить Lambda по функциям
- DynamoDB: provisioned capacity с auto-scaling
- CloudFront для кеширования
- Email напоминания за день до события

### Phase 3: Advanced
- Analytics (сколько билетов продано, популярные события)
- Recurring events (еженедельные)
- Discount codes / promo codes
- Seats selection (для некоторых локаций)
- Multi-language support
- Mobile app

---

## 10. Deployment structure

```
yallabalagan/
├── ticket-service/
│   ├── lambdas/
│   │   ├── api-handler.py           # Main API
│   │   ├── site-generator.py        # Generate static site
│   │   ├── telegram-bot.py          # Admin bot
│   │   ├── payment-webhook.py       # All-Pay webhooks
│   │   ├── ticket-generator.py      # Generate QR, PDF
│   │   └── email-sender.py          # Send tickets via email
│   ├── frontend/
│   │   ├── templates/
│   │   │   ├── index.html
│   │   │   ├── event.html
│   │   │   ├── location.html
│   │   │   └── checkout.html
│   │   ├── static/
│   │   │   ├── css/
│   │   │   └── js/
│   ├── scripts/
│   │   ├── deploy-api.sh
│   │   └── deploy-site.sh
│   └── docs/
│       ├── API.md
│       └── TELEGRAM_BOT.md
```

---

## 11. Refund Flow (Возврат билетов)

### Автоматический возврат (за 48+ часов)
```
┌──────────────────┐
│ User на странице │
│ своего билета    │
└────────┬─────────┘
         │
┌────────▼─────────────────────┐
│ GET /api/orders/:id/can-refund│
│ Check: event.date - now > 48h │
└────────┬─────────────────────┘
         │
    ┌────▼────┐
    │ Можно?  │
    └─┬────┬──┘
  Да  │    │ Нет
┌─────▼─┐  └──▼──────────────┐
│ Кнопка│    │ Сообщение:     │
│"Вернуть│    │ "Возврат только│
│деньги"│    │ за 48 часов"   │
└───┬────┘    └────────────────┘
    │
┌───▼────────────────────┐
│ POST /api/orders/:id/refund│
└───┬────────────────────┘
    │
┌───▼────────────────────┐
│ Lambda:                │
│ 1. Update status→refund│
│ 2. Call All-Pay refund │
│ 3. Restore tickets     │
│ 4. Send email+SMS      │
└───┬────────────────────┘
    │
┌───▼────────────────────┐
│ Email+SMS:             │
│ "Возврат 440₪         │
│  обработан"            │
└────────────────────────┘
```

### Логика проверки:
```python
def can_refund(order, event):
    # Проверка времени
    hours_until_event = (event.date - now()).hours
    if hours_until_event < event.refund_policy.hours_before:
        return False, "Слишком поздно для возврата"

    # Проверка статуса
    if order.payment.status != "completed":
        return False, "Оплата не завершена"

    if order.payment.status == "refunded":
        return False, "Уже возвращено"

    return True, "OK"
```

---

## 12. Recurring Events (Повторяющиеся события)

### Создание через Telegram Bot
```
Admin: /create_event
Bot: Тип события?
     [Разовое] [Еженедельное] [Ежемесячное]

Admin: [Еженедельное]
Bot: День недели?
     [Пн] [Вт] [Ср] [Чт] [Пт] [Сб] [Вс]

Admin: [Пятница]
Bot: До какой даты повторять? (YYYY-MM-DD)
Admin: 2025-12-31
Bot: ✅ Будет создано 48 событий (каждую пятницу до 31.12.2025)
     Продолжить?
```

### Lambda cron job (EventBridge)
```python
# Runs daily at 00:00
def generate_recurring_events():
    # Найти события с recurrence.enabled = true
    recurring_events = get_recurring_events()

    for template in recurring_events:
        # Проверить, нужно ли создать событие на следующую неделю/месяц
        next_date = calculate_next_occurrence(template)

        if not event_exists(template.id, next_date):
            create_event_instance(template, next_date)
```

---

## 13. Уточненные требования

### ✅ Реализовано в дизайне:
1. **Возврат билетов**: Автоматический возврат за 48+ часов до события
2. **Типы билетов**: Поддержка нескольких типов (Regular, VIP, Student, etc)
3. **Повторяющиеся события**: Еженедельные/ежемесячные через recurrence
4. **Уведомления**: Email (AWS SES) + SMS (интеграция TBD)
5. **Языки**: Русский
6. **Регистрация**: Не нужна, покупка как гость
7. **Проверка билетов**: QR коды (сканирование - в будущем)

### 🔮 Будущие версии (v2):
- **Места в залах**: Seating map, выбор конкретных мест
- **Мобильное приложение**: Для сканирования QR кодов на входе
- **Analytics**: Дашборд продаж, популярные события
- **Промокоды**: Discount codes для маркетинга
- **Multi-language**: Иврит, английский

---

## 14. Telegram Bot Commands

### Admin команды:
```
/start              - Приветствие и меню
/create_event       - Создать событие (с вопросами)
/edit_event         - Редактировать событие
/cancel_event       - Отменить событие (возврат всем)
/list_events        - Список всех событий
/event_stats <id>   - Статистика продаж

/create_location    - Добавить локацию
/edit_location      - Редактировать локацию
/list_locations     - Список локаций

/orders_today       - Заказы за сегодня
/search_order       - Найти заказ по email/phone
```

---

## 15. Next Steps (Что делать дальше)

### Phase 1: MVP (2-3 недели)
1. ✅ System design (done)
2. Setup AWS:
   - DynamoDB tables
   - Lambda functions
   - S3 buckets
   - API Gateway
3. Core API:
   - Events CRUD
   - Locations CRUD
   - Orders (create, get)
4. Site generator:
   - Template engine
   - Static pages (events list, event page, location page)
5. All-Pay integration:
   - Payment flow
   - Webhook handler
6. Telegram Bot:
   - Basic commands
   - Create event flow

### Phase 2: Enhancements (1-2 недели)
1. Refunds logic
2. Email notifications (SES)
3. SMS integration
4. QR code generation
5. Recurring events
6. Admin dashboard in bot

### Phase 3: Polish (1 неделя)
1. Error handling
2. Logging & monitoring
3. Testing
4. Documentation
5. Deploy to production

---

## Готов начинать? 🚀
