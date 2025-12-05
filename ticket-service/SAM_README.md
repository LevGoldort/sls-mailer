# Ticket Service - SAM Deployment

AWS SAM конфигурация для билетной системы YallaBalagan.

---

## 📦 Что будет создано

### DynamoDB Tables
- `yallabalagan-events-{env}` - События с билетами
- `yallabalagan-locations-{env}` - Локации
- `yallabalagan-orders-{env}` - Заказы билетов

### Lambda Functions
- `yallabalagan-ticket-api-{env}` - Main API handler
- `yallabalagan-site-regenerator-{env}` - Генерация frontend
- `yallabalagan-email-sender-{env}` - Email уведомления
- `yallabalagan-event-status-updater-{env}` - Обновление статусов
- `yallabalagan-pending-orders-cleaner-{env}` - Очистка expired заказов

### S3 Buckets
- `yallabalagan-ticket-media-{env}` - QR коды, фото
- `yallabalagan-tickets-frontend-{env}` - Статический сайт
- `yallabalagan-ticket-admin-{env}` - Админка

### API Gateway
- HTTP API для ticket API

---

## 🚀 Деплой

### Быстрый деплой

```bash
# Development
sam build
sam deploy --config-env dev --profile yallabalagan-dev

# Production
sam build
sam deploy --config-env default --profile yallabalagan-prod
```

### С параметрами

```bash
sam deploy \
  --config-env dev \
  --profile yallabalagan-dev \
  --parameter-overrides \
    TelegramBotToken=bot123:ABC \
    AllPayWebhookSecret=secret123 \
    SenderEmail=tickets@yallabalagan.org
```

---

## ⚙️ Параметры

| Параметр | Описание | Пример |
|----------|----------|--------|
| `Environment` | prod/dev | `dev` |
| `TelegramBotToken` | Telegram bot token | `bot123:ABC...` |
| `AllPayWebhookSecret` | All-Pay secret | `secret123` |
| `SenderEmail` | SES verified email | `tickets@yallabalagan.org` |
| `GA4Id` | Google Analytics ID | `G-XXXXXXXXXX` |
| `FBPixelId` | Facebook Pixel ID | `123456789` |

---

## 🔧 Локальное тестирование

```bash
# Start local API
sam local start-api

# Invoke function
sam local invoke TicketApiFunction --event events/create-order.json

# Generate event template
sam local generate-event apigateway http-api-proxy > events/test.json
```

---

## 📊 После деплоя

### 1. Получить URLs

```bash
aws cloudformation describe-stacks \
  --stack-name yallabalagan-ticket-service-dev \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-dev
```

Outputs:
- `ApiUrl` - API Gateway URL
- `FrontendUrl` - S3 website URL
- `AdminUrl` - Admin panel URL

### 2. Загрузить админку

```bash
aws s3 sync admin/ s3://yallabalagan-ticket-admin-dev/ \
  --profile yallabalagan-dev
```

### 3. Verify SES email

```bash
aws ses verify-email-identity \
  --email-address tickets@yallabalagan.org \
  --profile yallabalagan-dev
```

---

## 🔄 Обновление

### Только код (быстро)

```bash
sam build
sam deploy --no-confirm-changeset --profile yallabalagan-dev
```

### Или напрямую update Lambda

```bash
# Создать zip
zip -r deployment.zip models/ utils/ lambdas/api-handler.py

# Update
aws lambda update-function-code \
  --function-name yallabalagan-ticket-api-dev \
  --zip-file fileb://deployment.zip \
  --profile yallabalagan-dev
```

---

## 📝 Логи

```bash
# Real-time
aws logs tail /aws/lambda/yallabalagan-ticket-api-dev --follow --profile yallabalagan-dev

# Или через SAM
sam logs --stack-name yallabalagan-ticket-service-dev --tail --profile yallabalagan-dev
```

---

## 🗑️ Удаление

```bash
sam delete --stack-name yallabalagan-ticket-service-dev --profile yallabalagan-dev
```

**ВНИМАНИЕ:** Это удалит все данные в DynamoDB! Сделайте бэкап перед удалением.
