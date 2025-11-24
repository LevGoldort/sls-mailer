# Newsletter System Deployment Guide

Serverless email newsletter system для Yallabalagan. Замена Mailchimp ($100/мес → $2.50/мес).

## Архитектура

- **4 Lambda Functions**: API, Sender, Tracker, Unsubscribe Handler
- **3 DynamoDB Tables**: Contacts, Campaigns, Events
- **2 API Gateways**: Private (admin) + Public (tracking)
- **1 S3 Bucket**: Static web admin
- **AWS SES**: Email sending

---

## 1. Предварительные требования

### 1.1. DynamoDB Tables (уже созданы)
```
✅ yallabalagan-newsletter-contacts
✅ yallabalagan-newsletter-campaigns
✅ yallabalagan-newsletter-events
```

### 1.2. AWS SES
```
✅ Domain verified: yallabalagan.org
✅ Region: eu-north-1
✅ Email verified: newsletter@yallabalagan.org
```

### 1.3. Secret Key
Сгенерируйте секретный ключ (32+ символа):
```bash
openssl rand -hex 32
```
Сохраните этот ключ - он нужен для всех Lambda функций!

---

## 2. Создание Lambda Functions

### 2.1. IAM Role для Lambda

Создайте IAM роль `newsletter-lambda-role` с политиками:

**Trust policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Permissions:**
- `AWSLambdaBasicExecutionRole` (managed policy)
- Custom policy `newsletter-lambda-policy`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:eu-north-1:*:table/yallabalagan-newsletter-contacts",
        "arn:aws:dynamodb:eu-north-1:*:table/yallabalagan-newsletter-campaigns",
        "arn:aws:dynamodb:eu-north-1:*:table/yallabalagan-newsletter-events",
        "arn:aws:dynamodb:eu-north-1:*:table/yallabalagan-newsletter-events/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:eu-north-1:*:function:newsletter-sender"
    }
  ]
}
```

### 2.2. Создать Lambda Functions

Создайте 4 функции в AWS Console или через CLI:

#### Function 1: newsletter-api
```bash
aws lambda create-function \
  --function-name newsletter-api \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/newsletter-lambda-role \
  --handler lambda_function.lambda_handler \
  --timeout 30 \
  --memory-size 256 \
  --region eu-north-1 \
  --zip-file fileb://dummy.zip
```

Environment Variables:
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
NEWSLETTER_SENDER_LAMBDA=newsletter-sender
SECRET_KEY=<your-secret-key-from-step-1.3>
```

#### Function 2: newsletter-sender
```bash
aws lambda create-function \
  --function-name newsletter-sender \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/newsletter-lambda-role \
  --handler lambda_function.lambda_handler \
  --timeout 300 \
  --memory-size 512 \
  --region eu-north-1 \
  --zip-file fileb://dummy.zip
```

Environment Variables:
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
SES_FROM_EMAIL=newsletter@yallabalagan.org
TRACKING_BASE_URL=https://TRACKER_API_GATEWAY_URL
SECRET_KEY=<same-as-newsletter-api>
```

**ВАЖНО:** TRACKING_BASE_URL будет заполнен после создания API Gateway для tracker (шаг 3.2)

#### Function 3: newsletter-tracker
```bash
aws lambda create-function \
  --function-name newsletter-tracker \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/newsletter-lambda-role \
  --handler lambda_function.lambda_handler \
  --timeout 10 \
  --memory-size 128 \
  --region eu-north-1 \
  --zip-file fileb://dummy.zip
```

Environment Variables:
```
CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns
EVENTS_TABLE=yallabalagan-newsletter-events
SECRET_KEY=<same-as-above>
```

#### Function 4: newsletter-unsubscribe-handler
```bash
aws lambda create-function \
  --function-name newsletter-unsubscribe-handler \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/newsletter-lambda-role \
  --handler lambda_function.lambda_handler \
  --timeout 10 \
  --memory-size 128 \
  --region eu-north-1 \
  --zip-file fileb://dummy.zip
```

Environment Variables:
```
CONTACTS_TABLE=yallabalagan-newsletter-contacts
SECRET_KEY=<same-as-above>
```

### 2.3. Загрузить код функций

Используйте существующий скрипт:
```bash
./upload-lambdas.sh
```

Или загрузите каждую функцию отдельно:
```bash
./upload-lambdas.sh newsletter-api
./upload-lambdas.sh newsletter-sender
./upload-lambdas.sh newsletter-tracker
./upload-lambdas.sh newsletter-unsubscribe-handler
```

---

## 3. API Gateway Setup

### 3.1. Admin API (newsletter-api)

1. Создайте **HTTP API** в API Gateway
2. Название: `newsletter-admin-api`
3. Добавьте интеграцию с Lambda `newsletter-api`
4. Настройте маршруты:
   - `POST /campaigns`
   - `GET /campaigns`
   - `GET /campaigns/{campaign_id}`
   - `POST /campaigns/{campaign_id}/send`
   - `GET /contacts/preview`
   - `POST /unsubscribe`
   - `OPTIONS /*` (для CORS)

5. Включите CORS:
   - Allow Origins: `*`
   - Allow Methods: `GET, POST, OPTIONS`
   - Allow Headers: `Content-Type, Authorization`

6. Deploy stage: `prod`
7. Запишите API URL: `https://XXXXXXXXXX.execute-api.eu-north-1.amazonaws.com`

### 3.2. Tracking API (newsletter-tracker)

1. Создайте **HTTP API** в API Gateway
2. Название: `newsletter-tracker-api`
3. Добавьте интеграцию с Lambda `newsletter-tracker`
4. Настройте маршруты:
   - `GET /track/open/{campaign_id}/{email_hash}`
   - `GET /track/click/{campaign_id}/{email_hash}`

5. Deploy stage: `prod`
6. Запишите API URL: `https://YYYYYYYYYY.execute-api.eu-north-1.amazonaws.com`

**ВАЖНО:** После получения Tracking API URL, обновите environment variable `TRACKING_BASE_URL` в Lambda `newsletter-sender`:
```bash
aws lambda update-function-configuration \
  --function-name newsletter-sender \
  --environment "Variables={CONTACTS_TABLE=yallabalagan-newsletter-contacts,CAMPAIGNS_TABLE=yallabalagan-newsletter-campaigns,EVENTS_TABLE=yallabalagan-newsletter-events,SES_FROM_EMAIL=newsletter@yallabalagan.org,TRACKING_BASE_URL=https://YYYYYYYYYY.execute-api.eu-north-1.amazonaws.com,SECRET_KEY=YOUR_SECRET_KEY}"
```

---

## 4. S3 + CloudFront (Web Admin)

### 4.1. Создать S3 Bucket
```bash
aws s3 mb s3://yallabalagan-newsletter-admin --region eu-north-1
```

### 4.2. Настроить Static Website Hosting
```bash
aws s3 website s3://yallabalagan-newsletter-admin \
  --index-document index.html \
  --error-document index.html
```

### 4.3. Bucket Policy (для CloudFront)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::yallabalagan-newsletter-admin/*"
    }
  ]
}
```

### 4.4. Обновить API URLs в HTML файлах

Отредактируйте файлы в `newsletter-admin/`:
- `index.html`
- `create-campaign.html`
- `campaign-details.html`
- `unsubscribe.html`

Замените:
```javascript
const API_BASE_URL = 'https://YOUR-API-GATEWAY-URL.execute-api.eu-north-1.amazonaws.com';
```

На:
```javascript
const API_BASE_URL = 'https://XXXXXXXXXX.execute-api.eu-north-1.amazonaws.com';
```

### 4.5. Загрузить файлы в S3
```bash
cd newsletter-admin
aws s3 sync . s3://yallabalagan-newsletter-admin --region eu-north-1
```

### 4.6. Настроить CloudFront (опционально, для HTTPS + custom domain)

1. Создайте CloudFront Distribution
2. Origin: `yallabalagan-newsletter-admin.s3.eu-north-1.amazonaws.com`
3. Viewer Protocol Policy: Redirect HTTP to HTTPS
4. Default Root Object: `index.html`
5. Custom Domain (опционально): `admin-newsletter.yallabalagan.org`
6. SSL Certificate: Request via ACM (в регионе us-east-1!)

---

## 5. Настройка Public Unsubscribe Page

### 5.1. Создать S3 Bucket для Public Site
```bash
aws s3 mb s3://yallabalagan-newsletter-public --region eu-north-1
```

### 5.2. Загрузить unsubscribe.html
```bash
aws s3 cp newsletter-admin/unsubscribe.html s3://yallabalagan-newsletter-public/ --region eu-north-1
```

### 5.3. CloudFront для Public Site
Настроить как в шаге 4.6, но для домена:
- `newsletter.yallabalagan.org`

---

## 6. Тестовые данные

### 6.1. Добавить тестовые контакты

AWS Console → DynamoDB → yallabalagan-newsletter-contacts → Create Item:

```json
{
  "email": "test1@example.com",
  "name": "Test User 1",
  "tags": ["stand-up", "tel-aviv"],
  "status": "active",
  "created_at": 1700000000
}
```

Повторите для test2, test3 с разными тегами.

### 6.2. Протестировать API

```bash
# Создать кампанию
curl -X POST https://ADMIN_API_URL/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Test Campaign",
    "html_body": "<h1>Hello!</h1><p>This is a test.</p><a href=\"{{UNSUBSCRIBE_LINK}}\">Unsubscribe</a>",
    "tags_filter": ["tel-aviv"]
  }'

# Получить список кампаний
curl https://ADMIN_API_URL/campaigns

# Превью контактов
curl https://ADMIN_API_URL/contacts/preview?tags=tel-aviv
```

---

## 7. Стоимость

**Текущая стоимость (примерная):**
- Lambda: $0.20 (бесплатный tier - 1M запросов/мес)
- DynamoDB: $1.25 (25GB free tier)
- SES: $1.00 (1000 emails)
- S3 + CloudFront: $0.50

**Итого: ~$2.50/мес** (vs Mailchimp $100/мес)

---

## 8. Безопасность

### 8.1. Защита Admin API

Опционально добавьте API Key или Cognito:
- API Gateway → Authorizers → Create Lambda Authorizer
- Или используйте CloudFront с Basic Auth

### 8.2. Rate Limiting

API Gateway → Throttling:
- Rate: 100 requests/sec
- Burst: 200 requests

### 8.3. SES Production Access

По умолчанию SES в sandbox mode (200 emails/day). Для production:
1. AWS Console → SES → Account dashboard
2. Request production access
3. Заполните форму (Use case: Newsletter)
4. После approval: 50,000 emails/day

---

## 9. Мониторинг

### 9.1. CloudWatch Logs
Lambda функции автоматически пишут в CloudWatch Logs:
- `/aws/lambda/newsletter-api`
- `/aws/lambda/newsletter-sender`
- `/aws/lambda/newsletter-tracker`

### 9.2. CloudWatch Metrics
Создайте Dashboard для отслеживания:
- Lambda invocations
- SES sends/bounces/complaints
- DynamoDB read/write capacity

### 9.3. SES Notifications (важно!)
Настройте SNS topics для SES:
- Bounces (жёсткие отказы)
- Complaints (жалобы на спам)

Автоматически удаляйте bounced/complained emails из contacts table.

---

## 10. Следующие шаги

- [ ] Настроить автоматическую очистку bounced emails
- [ ] Добавить A/B testing для subject lines
- [ ] Создать Telegram bot для управления рассылкой
- [ ] Добавить сегментацию по location/interests
- [ ] Интеграция с существующей формой подписки на сайте

---

## Troubleshooting

### Lambda не отправляет письма
- Проверьте SES verified emails
- Проверьте IAM permissions для SES
- Проверьте CloudWatch Logs

### CORS ошибки в админке
- Проверьте API Gateway CORS настройки
- Убедитесь что OPTIONS method настроен

### Tracking links не работают
- Проверьте TRACKING_BASE_URL в newsletter-sender
- Убедитесь что Tracking API публичный (без авторизации)

### High DynamoDB costs
- Используйте On-Demand pricing вместо Provisioned
- Оптимизируйте Scan операции (используйте Query где возможно)

---

## Поддержка

Вопросы и баги: создавайте issue в репозитории или пишите в Telegram.

**Автор:** Claude Code
**Дата:** 2024-11-22
