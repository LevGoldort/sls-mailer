# Quick Start Guide - Newsletter System

Быстрый старт для разработчиков. Полная документация: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 1. Проверка предварительных требований

Убедитесь что уже созданы:
- ✅ DynamoDB таблицы (contacts, campaigns, events)
- ✅ AWS SES настроен и verified
- ✅ AWS CLI настроен (`aws configure`)

---

## 2. Создать Lambda Functions (5 минут)

### 2.1. Сгенерировать SECRET_KEY
```bash
openssl rand -hex 32
# Сохраните результат!
```

### 2.2. Создать IAM роль

AWS Console → IAM → Roles → Create Role:
- Type: Lambda
- Name: `newsletter-lambda-role`
- Permissions:
  - `AWSLambdaBasicExecutionRole`
  - Custom policy (см. DEPLOYMENT.md раздел 2.1)

### 2.3. Создать 4 Lambda функции

AWS Console → Lambda → Create Function (повторить 4 раза):

| Function Name | Runtime | Timeout | Memory | Role |
|---------------|---------|---------|--------|------|
| newsletter-api | Python 3.12 | 30s | 256MB | newsletter-lambda-role |
| newsletter-sender | Python 3.12 | 300s | 512MB | newsletter-lambda-role |
| newsletter-tracker | Python 3.12 | 10s | 128MB | newsletter-lambda-role |
| newsletter-unsubscribe-handler | Python 3.12 | 10s | 128MB | newsletter-lambda-role |

### 2.4. Добавить Environment Variables

Для каждой функции добавьте переменные (см. NEWSLETTER_README.md раздел "Environment Variables")

**ВАЖНО:** Используйте одинаковый SECRET_KEY во всех функциях!

### 2.5. Загрузить код

```bash
cd /Users/levgoldort/Documents/yallabalagan
./upload-lambdas.sh
```

---

## 3. Создать API Gateways (10 минут)

### 3.1. Admin API

AWS Console → API Gateway → Create API → HTTP API:
1. Name: `newsletter-admin-api`
2. Add integration: `newsletter-api` Lambda
3. Routes:
   ```
   POST   /campaigns
   GET    /campaigns
   GET    /campaigns/{campaign_id}
   POST   /campaigns/{campaign_id}/send
   GET    /contacts/preview
   POST   /unsubscribe
   OPTIONS /*
   ```
4. Enable CORS (all origins)
5. Deploy to stage: `prod`
6. **Скопировать Invoke URL:** `https://XXXXXXXXXX.execute-api.eu-north-1.amazonaws.com`

### 3.2. Tracker API

AWS Console → API Gateway → Create API → HTTP API:
1. Name: `newsletter-tracker-api`
2. Add integration: `newsletter-tracker` Lambda
3. Routes:
   ```
   GET /track/open/{campaign_id}/{email_hash}
   GET /track/click/{campaign_id}/{email_hash}
   ```
4. Deploy to stage: `prod`
5. **Скопировать Invoke URL:** `https://YYYYYYYYYY.execute-api.eu-north-1.amazonaws.com`

### 3.3. Обновить TRACKING_BASE_URL

```bash
aws lambda update-function-configuration \
  --function-name newsletter-sender \
  --environment "Variables={...TRACKING_BASE_URL=https://YYYYYYYYYY.execute-api.eu-north-1.amazonaws.com,...}"
```

---

## 4. Настроить веб-админку (5 минут)

### 4.1. Обновить API URLs в HTML файлах

Отредактируйте следующие файлы:
- `index.html`
- `create-campaign.html`
- `campaign-details.html`
- `unsubscribe.html`

Замените:
```javascript
const API_BASE_URL = 'https://YOUR-API-GATEWAY-URL...';
```

На:
```javascript
const API_BASE_URL = 'https://XXXXXXXXXX.execute-api.eu-north-1.amazonaws.com';
```

### 4.2. Создать S3 bucket

```bash
aws s3 mb s3://yallabalagan-newsletter-admin --region eu-north-1

# Enable static website hosting
aws s3 website s3://yallabalagan-newsletter-admin \
  --index-document index.html
```

### 4.3. Bucket policy

AWS Console → S3 → yallabalagan-newsletter-admin → Permissions → Bucket Policy:
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

### 4.4. Загрузить файлы

```bash
cd newsletter-admin
aws s3 sync . s3://yallabalagan-newsletter-admin --region eu-north-1 --exclude "*.py" --exclude "*.md" --exclude ".gitignore"
```

### 4.5. Получить URL

```bash
echo "http://yallabalagan-newsletter-admin.s3-website.eu-north-1.amazonaws.com"
```

Откройте этот URL в браузере!

---

## 5. Добавить тестовые данные (2 минуты)

```bash
cd newsletter-admin
pip3 install boto3
python3 add-test-contacts.py
```

Будет добавлено 5 тестовых контактов с разными тегами.

---

## 6. Тестирование (5 минут)

### 6.1. Открыть админку

```
http://yallabalagan-newsletter-admin.s3-website.eu-north-1.amazonaws.com
```

Вы должны увидеть:
- Statistics: 4 active contacts, 1 unsubscribed
- Empty campaigns list

### 6.2. Создать тестовую кампанию

1. Click "Create New Campaign"
2. Subject: `Test Campaign - $(date)`
3. HTML Body: Скопируйте из `email-template.html` и замените `{{CONTENT}}` на:
   ```html
   <h2>Hello!</h2>
   <p>This is a test campaign.</p>
   ```
4. Tags: Выберите `tel-aviv` (должно показать 3 recipients)
5. Click "Create Campaign"
6. Click "Send Now" или "Send Later"

### 6.3. Проверить отправку

1. Откройте Campaign Details
2. Обновите страницу через 10-20 секунд
3. Вы должны увидеть:
   - Status: `sent`
   - Sent count: 3
   - Events log с отправленными письмами

### 6.4. Проверить tracking (опционально)

Если у вас есть доступ к тестовым email адресам:
1. Откройте письмо
2. Кликните на ссылку
3. Вернитесь в Campaign Details
4. Должны появиться события `opened` и `clicked`

---

## 7. Production готовность (опционально)

### 7.1. CloudFront для HTTPS

AWS Console → CloudFront → Create Distribution:
- Origin: `yallabalagan-newsletter-admin.s3.eu-north-1.amazonaws.com`
- Custom domain: `admin-newsletter.yallabalagan.org`
- SSL: Request ACM certificate

### 7.2. SES Production Access

AWS Console → SES → Account Dashboard → Request Production Access

Заполните форму:
- Use case: Newsletter for comedy events
- Daily volume: 5,000 emails
- Compliance: Yes, we have unsubscribe links

Approval обычно 24-48 часов.

### 7.3. Monitoring

AWS Console → CloudWatch → Create Dashboard:
- Lambda invocations/errors
- SES sends/bounces
- DynamoDB read/write capacity

---

## Итого: ~30 минут от нуля до работающей системы!

✅ Lambda functions deployed
✅ API Gateways configured
✅ Web admin live
✅ Test data loaded
✅ First campaign sent

---

## Troubleshooting

### "Failed to load campaigns"
- Проверьте API Gateway URL в HTML
- Проверьте CORS настройки в API Gateway
- Откройте Browser DevTools → Network → проверьте запрос

### "Failed to send campaign"
- Проверьте CloudWatch Logs для `newsletter-sender`
- Убедитесь что SES email verified
- Проверьте IAM permissions для SES

### Tracking не работает
- Проверьте `TRACKING_BASE_URL` в `newsletter-sender`
- Убедитесь что Tracker API публичный (без авторизации)

---

## Следующие шаги

1. Подключите форму подписки на сайте → добавление в contacts table
2. Настройте bounce handling (SNS → Lambda → обновление contacts)
3. Создайте Telegram bot для управления
4. Добавьте scheduled campaigns

---

Вопросы? См. [DEPLOYMENT.md](DEPLOYMENT.md) для полной документации.
