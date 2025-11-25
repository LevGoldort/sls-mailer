# YallaBalagan Ticket Service

Билетный сервис для продажи билетов на мероприятия YallaBalagan.

## Структура проекта

```
ticket-service/
├── models/                    # Модели данных
│   ├── event.py              # Event, TicketType, Recurrence
│   ├── location.py           # Location, Address, Parking
│   └── order.py              # Order, Customer, QRCode
├── lambdas/                  # Lambda функции
│   ├── api-handler.py        # Main API handler
│   ├── telegram-bot.py       # Telegram bot (TODO)
│   └── payment-webhook.py    # All-Pay webhooks (TODO)
├── utils/                    # Утилиты
│   └── dynamodb.py           # DynamoDB wrapper
├── config/                   # Конфигурация
│   └── dynamodb_tables.json  # Схемы таблиц
├── scripts/                  # Deployment scripts
└── docs/                     # Документация
```

## Быстрый старт (локальная разработка)

### 1. Установка зависимостей

```bash
cd ticket-service
pip install -r requirements.txt
```

### 2. Настройка AWS credentials

```bash
aws configure
# Введи свои AWS credentials
```

### 3. Тестирование моделей (локально)

```python
from models import Event, TicketType, Location, Order

# Создание события
event = Event(
    event_id=Event.generate_id(),
    title="Stand-up вечер",
    description="Комедийный вечер",
    date="2025-02-15T19:00:00Z",
    location_id="loc-123",
    ticket_types=[
        TicketType(id="regular", name="Обычный", price=100, total=50, available=50)
    ]
)

# Конвертация в DynamoDB формат
item = event.to_dynamodb_item()
print(item)
```

## Deployment в AWS

### Полная инструкция по настройке AWS

См. [AWS_SETUP.md](./AWS_SETUP.md) - пошаговая инструкция с командами AWS CLI.

### Быстрый деплой Lambda (после первичной настройки)

```bash
# Создать deployment package
cd ticket-service
./scripts/deploy-lambda.sh
```

## API Endpoints

### Events
- `GET /api/events` - Список событий
- `GET /api/events/{id}` - Детали события
- `POST /api/events` - Создать событие (admin)
- `PUT /api/events/{id}` - Обновить событие (admin)
- `DELETE /api/events/{id}` - Удалить событие (admin)

### Locations
- `GET /api/locations` - Список локаций
- `GET /api/locations/{id}` - Детали локации (по ID или slug)
- `POST /api/locations` - Создать локацию (admin)

### Orders
- `POST /api/orders` - Создать заказ (купить билет)
- `GET /api/orders/{id}` - Детали заказа
- `GET /api/orders/customer/{email}` - Заказы клиента

## Модели данных

### Event
```python
{
  "event_id": "uuid",
  "title": "Название",
  "description": "Описание",
  "date": "2025-01-15T19:00:00Z",
  "location_id": "uuid",
  "ticket_types": [
    {"id": "regular", "name": "Обычный", "price": 100, "total": 50, "available": 45}
  ],
  "status": "active|sold_out|cancelled",
  "images": ["s3://..."],
  "recurrence": {...},
  "refund_policy": {"enabled": true, "hours_before": 48}
}
```

### Location
```python
{
  "location_id": "uuid",
  "name": "Название",
  "slug": "dizengoff-center",
  "address": {
    "street": "Dizengoff 100",
    "city": "Tel Aviv",
    "coordinates": {"lat": 32.0853, "lng": 34.7818}
  },
  "parkings": [
    {
      "type": "underground",
      "name": "Подземная парковка",
      "description": "100 метров от заведения",
      "location": {
        "coordinates": {"lat": 32.0854, "lng": 34.7820},
        "google_maps_url": "https://maps.google.com/..."
      },
      "price": "15₪/час"
    }
  ],
  "capacity": 150,
  "media": {"photos": [...], "videos": [...]}
}
```

### Order
```python
{
  "order_id": "uuid",
  "event_id": "uuid",
  "customer": {
    "name": "Имя",
    "email": "email@example.com",
    "phone": "+972-xxx-xxxx"
  },
  "tickets": [
    {"type_id": "regular", "type_name": "Обычный", "quantity": 2, "price_per_ticket": 100}
  ],
  "total_amount": 200,
  "payment": {"status": "completed", "allpay_transaction_id": "xxx"},
  "qr_codes": [
    {"code": "YBEV-2025-XXXX-1", "ticket_type": "regular", "scanned": false}
  ]
}
```

## Фичи

### ✅ Реализовано (базовый функционал)
- [x] Модели данных (Event, Location, Order)
- [x] DynamoDB схемы и индексы
- [x] API для Events (CRUD)
- [x] API для Locations (list, get)
- [x] API для Orders (create, get)
- [x] Генерация QR кодов для билетов
- [x] Проверка доступности билетов
- [x] Типы билетов (Regular, VIP, etc)

### 🚧 TODO (следующие фазы)
- [ ] Telegram Bot для админки
- [ ] All-Pay интеграция (payment, webhooks)
- [ ] Email уведомления (AWS SES)
- [ ] SMS уведомления
- [ ] Возвраты билетов (refund logic)
- [ ] Повторяющиеся события (recurrence)
- [ ] Site generator (статические HTML страницы)
- [ ] QR код сканирование
- [ ] Analytics и статистика

## Разработка

### Запуск тестов (локально)

```python
# Тест API handler
cd lambdas
python api-handler.py
```

### Логи Lambda в AWS

```bash
aws logs tail /aws/lambda/yallabalagan-ticket-api --follow --region eu-north-1
```

## Environment Variables

Lambda функции используют:
- `EVENTS_TABLE` - название таблицы событий (default: yallabalagan-events)
- `LOCATIONS_TABLE` - название таблицы локаций (default: yallabalagan-locations)
- `ORDERS_TABLE` - название таблицы заказов (default: yallabalagan-orders)
- `AWS_REGION` - регион AWS (default: eu-north-1)

## Документация

- [TICKET_SYSTEM_DESIGN.md](../TICKET_SYSTEM_DESIGN.md) - System design и архитектура
- [AWS_SETUP.md](./AWS_SETUP.md) - Настройка AWS инфраструктуры

## Контакты

Вопросы? Пиши!
