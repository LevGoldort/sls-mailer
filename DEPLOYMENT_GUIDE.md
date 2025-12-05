# YallaBalagan - AWS SAM Deployment Guide

Полная инструкция по развертыванию всех четырёх систем в AWS с помощью SAM (Serverless Application Model).

---

## 📋 Содержание

1. [Предварительные требования](#предварительные-требования)
2. [Установка AWS SAM CLI](#установка-aws-sam-cli)
3. [Подготовка секретов](#подготовка-секретов)
4. [Деплой на Production](#деплой-на-production)
5. [Деплой на Development](#деплой-на-development)
6. [Переменные окружения](#переменные-окружения)
7. [Обновление кода](#обновление-кода)
8. [Troubleshooting](#troubleshooting)

---

## Предварительные требования

### 1. AWS CLI установлен и настроен

```bash
# Проверка
aws --version

# Настройка для PRODUCTION аккаунта
aws configure --profile yallabalagan-prod
# AWS Access Key ID: [ваш prod ключ]
# AWS Secret Access Key: [ваш prod секрет]
# Default region: eu-north-1
# Default output format: json

# Настройка для DEVELOPMENT аккаунта
aws configure --profile yallabalagan-dev
# AWS Access Key ID: [ваш dev ключ]
# AWS Secret Access Key: [ваш dev секрет]
# Default region: eu-north-1
# Default output format: json
```

### 2. Python 3.11+ установлен

```bash
python3 --version
# Должно быть >= 3.11
```

### 3. Проверка AWS аккаунтов

```bash
# Production account
aws sts get-caller-identity --profile yallabalagan-prod

# Development account
aws sts get-caller-identity --profile yallabalagan-dev
```

---

## Установка AWS SAM CLI

### macOS (Homebrew)

```bash
brew tap aws/tap
brew install aws-sam-cli

# Проверка
sam --version
```

### Linux

```bash
# Download installer
wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip
unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
sudo ./sam-installation/install

# Проверка
sam --version
```

### Windows

```powershell
# Using MSI installer from:
# https://github.com/aws/aws-sam-cli/releases/latest
```

---

## Подготовка секретов

Перед деплоем нужно подготовить все секреты и токены. Рекомендую использовать AWS Systems Manager Parameter Store или AWS Secrets Manager.

### Способ 1: Переменные окружения (простой)

Создайте файл `.env.prod` и `.env.dev` в корне проекта:

```bash
# .env.prod
TELEGRAM_BOT_TOKEN_TICKET=bot123456:ABC-DEF...
TELEGRAM_BOT_TOKEN_EVENTS=bot234567:XYZ-ABC...
TELEGRAM_BOT_TOKEN_DONATE=bot345678:QWE-RTY...
ALLPAY_WEBHOOK_SECRET=your-allpay-secret
NOTION_TOKEN=secret_...
NOTION_DATABASE_ID_EVENTS=abc123...
NOTION_DATABASE_ID_TALENTS=def456...
NOTION_DATABASE_ID_PRODUCTS=ghi789...
NOTION_DATABASE_ID_PROJECTS=jkl012...
NEWSLETTER_SECRET_KEY=your-generated-secret-key
```

### Способ 2: AWS Secrets Manager (рекомендуется для prod)

```bash
# Создание секретов в AWS Secrets Manager
aws secretsmanager create-secret \
  --name /yallabalagan/prod/telegram-bot-token-ticket \
  --secret-string "bot123456:ABC-DEF..." \
  --profile yallabalagan-prod

# Повторите для всех секретов
```

Затем обновите `template.yaml` для использования Secrets Manager:

```yaml
Parameters:
  TelegramBotToken:
    Type: String
    Default: '{{resolve:secretsmanager:/yallabalagan/prod/telegram-bot-token-ticket:SecretString}}'
```

---

## Деплой на Production

### 1. Ticket Service

```bash
cd ticket-service

# Build
sam build

# Deploy (первый раз с guided setup)
sam deploy \
  --profile yallabalagan-prod \
  --parameter-overrides \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN_TICKET \
    AllPayWebhookSecret=$ALLPAY_WEBHOOK_SECRET

# Или используя config
sam deploy --config-env default --profile yallabalagan-prod
```

**Outputs после деплоя:**
- `ApiUrl` - используйте для обновления frontend
- `FrontendUrl` - URL публичного сайта
- `AdminUrl` - URL админки

### 2. Events Site

```bash
cd ../events-site

sam build

sam deploy \
  --profile yallabalagan-prod \
  --parameter-overrides \
    NotionToken=$NOTION_TOKEN \
    NotionDatabaseId=$NOTION_DATABASE_ID_EVENTS \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN_EVENTS

# После деплоя настройте Telegram webhook
WEBHOOK_URL=$(aws cloudformation describe-stacks \
  --stack-name yallabalagan-events-site-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`TelegramWebhookUrl`].OutputValue' \
  --output text \
  --profile yallabalagan-prod)

curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN_EVENTS/setWebhook?url=$WEBHOOK_URL"
```

### 3. Donate Site

```bash
cd ../donate-site

sam build

sam deploy \
  --profile yallabalagan-prod \
  --parameter-overrides \
    NotionToken=$NOTION_TOKEN \
    TalentsDbId=$NOTION_DATABASE_ID_TALENTS \
    ProductsDbId=$NOTION_DATABASE_ID_PRODUCTS \
    ProjectsDbId=$NOTION_DATABASE_ID_PROJECTS \
    AllPayWebhookSecret=$ALLPAY_WEBHOOK_SECRET \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN_DONATE

# Настройка Telegram webhook
WEBHOOK_URL=$(aws cloudformation describe-stacks \
  --stack-name yallabalagan-donate-site-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`TelegramWebhookUrl`].OutputValue' \
  --output text \
  --profile yallabalagan-prod)

curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN_DONATE/setWebhook?url=$WEBHOOK_URL"

# Настройка All-Pay webhook
PAYMENT_WEBHOOK=$(aws cloudformation describe-stacks \
  --stack-name yallabalagan-donate-site-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`PaymentWebhookUrl`].OutputValue' \
  --output text \
  --profile yallabalagan-prod)

echo "Configure this URL in All-Pay dashboard: $PAYMENT_WEBHOOK"
```

### 4. Newsletter

```bash
cd ../newsletter

sam build

# Сначала сгенерируйте SECRET_KEY для HMAC
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

sam deploy \
  --profile yallabalagan-prod \
  --parameter-overrides \
    SecretKey=$SECRET_KEY

# После деплоя загрузите admin файлы в S3
ADMIN_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name yallabalagan-newsletter-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`AdminBucketName`].OutputValue' \
  --output text \
  --profile yallabalagan-prod)

aws s3 sync admin/ s3://$ADMIN_BUCKET/ \
  --exclude "*.md" \
  --profile yallabalagan-prod
```

### 5. Загрузка статических файлов (админки, frontend)

```bash
# Ticket Service - Admin
cd ticket-service
aws s3 sync admin/ s3://yallabalagan-ticket-admin-prod/ \
  --profile yallabalagan-prod

# Events Site (генерируется автоматически Lambda)
# Donate Site (генерируется автоматически Lambda)
```

---

## Деплой на Development

Процесс идентичный, но используйте `--config-env dev` и профиль `yallabalagan-dev`:

```bash
# Ticket Service
cd ticket-service
sam build
sam deploy --config-env dev --profile yallabalagan-dev \
  --parameter-overrides \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN_TICKET_DEV \
    AllPayWebhookSecret=$ALLPAY_WEBHOOK_SECRET_DEV

# Events Site
cd ../events-site
sam build
sam deploy --config-env dev --profile yallabalagan-dev \
  --parameter-overrides \
    NotionToken=$NOTION_TOKEN_DEV \
    NotionDatabaseId=$NOTION_DATABASE_ID_EVENTS_DEV \
    TelegramBotToken=$TELEGRAM_BOT_TOKEN_EVENTS_DEV

# И так далее для всех сервисов...
```

---

## Переменные окружения

### Ticket Service

| Параметр | Описание | Где взять |
|----------|----------|-----------|
| `TelegramBotToken` | Telegram bot token | @BotFather |
| `AllPayWebhookSecret` | All-Pay webhook secret | All-Pay dashboard |
| `SenderEmail` | Verified SES email | AWS SES Console |

### Events Site

| Параметр | Описание | Где взять |
|----------|----------|-----------|
| `NotionToken` | Notion integration token | notion.so/my-integrations |
| `NotionDatabaseId` | Notion database ID | URL базы данных |
| `TelegramBotToken` | Telegram bot token | @BotFather |
| `YouTubeApiKey` | YouTube API key (опционально) | Google Cloud Console |

### Donate Site

| Параметр | Описание | Где взять |
|----------|----------|-----------|
| `NotionToken` | Notion integration token | notion.so/my-integrations |
| `TalentsDbId` | Notion Talents database ID | URL базы |
| `ProductsDbId` | Notion Products database ID | URL базы |
| `ProjectsDbId` | Notion Projects database ID | URL базы |
| `AllPayWebhookSecret` | All-Pay webhook secret | All-Pay dashboard |
| `TelegramBotToken` | Telegram bot token | @BotFather |

### Newsletter

| Параметр | Описание | Где взять |
|----------|----------|-----------|
| `SecretKey` | HMAC secret для токенов | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SenderEmail` | Verified SES email | AWS SES Console |

---

## Обновление кода

### Быстрое обновление Lambda (без изменения инфраструктуры)

```bash
# Ticket Service - обновить только API Lambda
cd ticket-service
sam build
sam deploy --config-env default --profile yallabalagan-prod --no-confirm-changeset

# Или обновить конкретную функцию напрямую (быстрее)
cd ticket-service
zip -r api-handler.zip models/ utils/ lambdas/api-handler.py
aws lambda update-function-code \
  --function-name yallabalagan-ticket-api-prod \
  --zip-file fileb://api-handler.zip \
  --profile yallabalagan-prod
```

### Полное обновление стека (с изменениями инфраструктуры)

```bash
cd ticket-service
sam build
sam deploy --config-env default --profile yallabalagan-prod
```

---

## Мониторинг

### Логи Lambda функций

```bash
# Real-time logs
sam logs \
  --stack-name yallabalagan-ticket-service-prod \
  --name TicketApiFunction \
  --tail \
  --profile yallabalagan-prod

# Или напрямую через AWS CLI
aws logs tail /aws/lambda/yallabalagan-ticket-api-prod \
  --follow \
  --profile yallabalagan-prod
```

### CloudWatch Dashboard

```bash
# Создайте dashboard для мониторинга
aws cloudwatch put-dashboard \
  --dashboard-name YallaBalagan-Prod \
  --dashboard-body file://monitoring/dashboard.json \
  --profile yallabalagan-prod
```

---

## Удаление стека (cleanup)

```bash
# ВНИМАНИЕ: Это удалит ВСЕ ресурсы включая данные в DynamoDB!

# Удаление dev окружения
sam delete --stack-name yallabalagan-ticket-service-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-events-site-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-donate-site-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-newsletter-dev --profile yallabalagan-dev

# Перед удалением prod - обязательно сделайте бэкап DynamoDB!
```

---

## Troubleshooting

### Ошибка: "Unable to upload artifact ... AccessDenied"

Создайте S3 bucket для SAM deployment:

```bash
aws s3 mb s3://aws-sam-cli-managed-default-samclisourcebucket-prod \
  --region eu-north-1 \
  --profile yallabalagan-prod
```

### Ошибка: "Invalid template property or properties"

Проверьте синтаксис YAML:

```bash
sam validate --profile yallabalagan-prod
```

### Lambda функция не имеет доступа к DynamoDB

Проверьте IAM политики в CloudFormation:

```bash
aws cloudformation describe-stack-resources \
  --stack-name yallabalagan-ticket-service-prod \
  --profile yallabalagan-prod
```

### API Gateway возвращает 403

Проверьте CORS настройки в `template.yaml`:

```yaml
CorsConfiguration:
  AllowOrigins:
    - '*'
```

---

## Полезные команды

```bash
# Список всех стеков
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --profile yallabalagan-prod

# Информация о конкретном стеке
aws cloudformation describe-stacks \
  --stack-name yallabalagan-ticket-service-prod \
  --profile yallabalagan-prod

# Получить все outputs
aws cloudformation describe-stacks \
  --stack-name yallabalagan-ticket-service-prod \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-prod

# Локальное тестирование Lambda
sam local invoke TicketApiFunction \
  --event events/test-event.json

# Локальный API Gateway
sam local start-api
```

---

## Стоимость

### Production (примерная оценка)

- **Lambda**: ~$5-10/мес (зависит от трафика)
- **DynamoDB**: ~$2-5/мес (PAY_PER_REQUEST)
- **S3**: ~$1-3/мес (статика + media)
- **API Gateway**: ~$3-5/мес (HTTP API)
- **SES**: $0.10 за 1000 писем
- **CloudWatch Logs**: ~$2/мес

**Итого: ~$15-30/мес** (вместо $400+ на Mailchimp + Heroku + др)

### Development

- Практически бесплатно благодаря AWS Free Tier
- Рекомендую включить `TTL` на DynamoDB таблицах для автоочистки тестовых данных

---

## Безопасность

### Рекомендации:

1. **Используйте AWS Secrets Manager** для всех токенов и секретов
2. **Включите CloudTrail** для аудита всех API вызовов
3. **Настройте Budget Alerts** для контроля расходов
4. **Используйте IAM roles** с минимальными необходимыми правами
5. **Включите MFA** на production AWS аккаунте
6. **Настройте WAF** для API Gateway (опционально, для защиты от DDoS)

```bash
# Создание бюджета
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget file://budget.json \
  --profile yallabalagan-prod
```

---

## Следующие шаги

После успешного деплоя:

1. ✅ Настройте Telegram webhooks
2. ✅ Настройте All-Pay webhooks
3. ✅ Verify email addresses в SES
4. ✅ Настройте CloudWatch Alarms
5. ✅ Создайте бэкапы DynamoDB (Point-in-Time Recovery)
6. ✅ Настройте CI/CD (GitHub Actions)

---

Готово! 🚀

Теперь у вас есть полностью автоматизированная инфраструктура, которую можно развернуть на новом AWS аккаунте одной командой.
