# Newsletter System - Yallabalagan

Serverless email newsletter system на базе AWS Lambda, DynamoDB и SES.

**Экономия:** $100/мес (Mailchimp) → $2.50/мес (AWS)

---

## Быстрый старт

### Структура проекта

```
yallabalagan/
├── Lambdas/
│   ├── newsletter-api.py                  # HTTP API для админки
│   ├── newsletter-sender.py               # Отправка писем через SES
│   ├── newsletter-tracker.py              # Tracking открытий и кликов
│   └── newsletter-unsubscribe-handler.py  # Обработка отписок
│
└── newsletter-admin/
    ├── index.html                         # Главная страница админки
    ├── create-campaign.html               # Создание кампании
    ├── campaign-details.html              # Детали и аналитика
    ├── unsubscribe.html                   # Публичная страница отписки
    ├── email-template.html                # Базовый шаблон письма
    └── DEPLOYMENT.md                      # Полная инструкция по деплою
```

---

## Компоненты системы

### Lambda Functions (4)
1. **newsletter-api** - REST API для веб-админки (создание кампаний, просмотр статистики)
2. **newsletter-sender** - Отправка писем батчами (50/сек) с персонализацией и tracking
3. **newsletter-tracker** - Отслеживание открытий и кликов по ссылкам
4. **newsletter-unsubscribe-handler** - Обработка отписок с валидацией токена

### DynamoDB Tables (3)
- `yallabalagan-newsletter-contacts` - База подписчиков (email, tags, status)
- `yallabalagan-newsletter-campaigns` - Кампании (subject, body, stats)
- `yallabalagan-newsletter-events` - События (sent, opened, clicked)

### Web Admin
- Single Page Application на чистом HTML/CSS/JS
- Управление кампаниями и аналитика
- Хостинг на S3 + CloudFront

---

## Возможности

- ✅ Создание и отправка email кампаний
- ✅ Сегментация по тегам (stand-up, vip, tel-aviv, etc.)
- ✅ Tracking открытий (1x1 pixel)
- ✅ Tracking кликов (redirect через API)
- ✅ Unsubscribe с HMAC токеном
- ✅ Аналитика: sent/opened/clicked rates
- ✅ Батчинг (50 писем/сек для SES compliance)
- ✅ Responsive email templates
- ✅ Дедупликация events

---

## Деплой

См. полную инструкцию: [newsletter-admin/DEPLOYMENT.md](newsletter-admin/DEPLOYMENT.md)

### Краткая версия:

1. **Создать Lambda функции** (4 шт)
   ```bash
   ./upload-lambdas.sh
   ```

2. **Настроить API Gateway** (2 шт: admin + tracker)

3. **Обновить API URLs** в HTML файлах

4. **Загрузить админку в S3**
   ```bash
   cd newsletter-admin
   aws s3 sync . s3://yallabalagan-newsletter-admin
   ```

5. **Добавить тестовые контакты** в DynamoDB

6. **Протестировать** через веб-админку

---

## Environment Variables

Все Lambda функции требуют одинаковый `SECRET_KEY` (для HMAC токенов).

Сгенерируйте:
```bash
openssl rand -hex 32
```

### newsletter-api
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
NEWSLETTER_SENDER_LAMBDA=newsletter-sender
SECRET_KEY=<your-secret>
```

### newsletter-sender
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
SES_FROM_EMAIL=newsletter@yallabalagan.org
TRACKING_BASE_URL=https://tracker-api-gateway-url
SECRET_KEY=<same-as-above>
```

### newsletter-tracker
```
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
SECRET_KEY=<same-as-above>
```

### newsletter-unsubscribe-handler
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
SECRET_KEY=<same-as-above>
```

---

## Использование

### 1. Создать кампанию через админку

1. Открыть `https://your-admin-url/index.html`
2. Нажать "Create New Campaign"
3. Ввести Subject и HTML Body
4. Выбрать теги (или оставить пустым для всех)
5. Preview recipients
6. Create → Send

### 2. Использовать email template

Скопируйте содержимое `email-template.html` и замените `{{CONTENT}}` на ваш контент.

Обязательно включите `{{UNSUBSCRIBE_LINK}}` в footer.

### 3. Отслеживать результаты

1. Открыть кампанию в админке
2. Посмотреть статистику: Sent / Opened / Clicked
3. Просмотреть Events Log для деталей

---

## API Endpoints

### Admin API (newsletter-api)

```
POST   /campaigns                      - Создать кампанию
GET    /campaigns                      - Список кампаний
GET    /campaigns/{id}                 - Детали кампании
POST   /campaigns/{id}/send            - Отправить кампанию
GET    /contacts/preview?tags=X,Y      - Превью получателей
POST   /unsubscribe                    - Отписать контакт
```

### Tracking API (newsletter-tracker)

```
GET    /track/open/{campaign_id}/{email_hash}      - Track open
GET    /track/click/{campaign_id}/{email_hash}?url - Track click
```

---

## Безопасность

- **HMAC Tokens**: Все unsubscribe ссылки используют HMAC-SHA256
- **Email Hash**: Tracking использует хеши email (не plain text в URL)
- **CORS**: Настроен для admin домена
- **Rate Limiting**: API Gateway throttling (100 req/sec)
- **SES**: Проверенный домен + DKIM/SPF

---

## Мониторинг

### CloudWatch Logs
- `/aws/lambda/newsletter-api`
- `/aws/lambda/newsletter-sender`
- `/aws/lambda/newsletter-tracker`

### Метрики
- Lambda invocations / errors / duration
- SES sends / bounces / complaints
- DynamoDB read/write capacity

### Важно: настройте SES Notifications
- SNS topics для bounces/complaints
- Автоматическое удаление проблемных email из contacts

---

## Стоимость (примерная)

| Сервис | Использование | Стоимость |
|--------|--------------|-----------|
| Lambda | 10K invocations/мес | $0.20 |
| DynamoDB | 25GB storage + queries | $1.25 |
| SES | 1000 emails/мес | $1.00 |
| S3 + CloudFront | Static hosting | $0.50 |
| **Итого** | | **$2.50/мес** |

---

## FAQ

### Как добавить новые контакты?
Через DynamoDB Console или создайте отдельный Lambda для интеграции с формой подписки на сайте.

### Как удалить bounced emails?
Настройте SNS topic для SES bounces, подключите Lambda для автоматического обновления status в contacts table.

### Можно ли A/B тестировать subject lines?
Сейчас нет. Можно добавить: создавать 2 кампании с разными subject, отправлять на 50/50 split.

### Как увеличить лимит отправки?
Request production access в SES (по умолчанию sandbox = 200 emails/day, после approval = 50,000/day).

### Можно ли использовать для transactional emails?
Да, но лучше создать отдельную Lambda для транзакционных писем (подтверждение заказа, reset password, etc).

---

## Roadmap

- [ ] Автоматическая обработка bounces/complaints
- [ ] A/B testing для subject lines
- [ ] Telegram bot для управления
- [ ] Drag-and-drop email builder
- [ ] Scheduled campaigns (отложенная отправка)
- [ ] Webhook интеграция с формой подписки
- [ ] Export аналитики в CSV
- [ ] Email preview перед отправкой

---

## Лицензия

MIT

---

## Контакты

**Проект:** Yallabalagan Newsletter System
**Автор:** Claude Code
**Дата:** 2024-11-22

Для вопросов и предложений создавайте issue в репозитории.
