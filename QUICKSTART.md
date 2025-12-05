# YallaBalagan - Quick Start Guide

Быстрый старт для деплоя всей инфраструктуры на новый AWS аккаунт.

---

## ⚡ Быстрый деплой (5 минут)

```bash
# 1. Установите SAM CLI (если еще нет)
brew install aws-sam-cli

# 2. Настройте AWS профили
aws configure --profile yallabalagan-prod
aws configure --profile yallabalagan-dev

# 3. Создайте файл с секретами
cp .env.example .env.dev
nano .env.dev  # Заполните все токены

# 4. Проверьте готовность
./check-deployment-readiness.sh dev

# 5. Деплой!
./deploy-all.sh dev
```

**Готово!** Все 4 сервиса развернуты на AWS.

---

## 📝 Основные команды

### Деплой

```bash
# Все сервисы на DEV
./deploy-all.sh dev

# Все сервисы на PROD
./deploy-all.sh prod

# Отдельный сервис
cd ticket-service
sam build
sam deploy --config-env dev --profile yallabalagan-dev
```

### Обновление кода

```bash
# Быстрое обновление (только код)
cd ticket-service
sam build
sam deploy --no-confirm-changeset --profile yallabalagan-prod
```

### Мониторинг

```bash
# Логи в реальном времени
aws logs tail /aws/lambda/yallabalagan-ticket-api-dev --follow --profile yallabalagan-dev

# Список стеков
aws cloudformation list-stacks --profile yallabalagan-dev
```

### Локальное тестирование

```bash
cd ticket-service

# Локальный API
sam local start-api

# Тест Lambda
sam local invoke TicketApiFunction --event events/test.json
```

---

## 🔑 Получение секретов

### Telegram Bot Token
```bash
# 1. Напишите @BotFather в Telegram
# 2. /newbot
# 3. Скопируйте токен
```

### Notion Token
```bash
# 1. Перейдите на https://www.notion.so/my-integrations
# 2. New integration
# 3. Скопируйте Internal Integration Token
```

### Notion Database ID
```bash
# 1. Откройте базу в браузере
# 2. URL: https://www.notion.so/workspace/DATABASE_ID?v=...
# 3. Скопируйте DATABASE_ID
```

### Newsletter Secret Key
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Telegram User ID
```bash
# Напишите @userinfobot в Telegram
```

---

## 📊 После деплоя

### 1. Настройте Telegram webhooks

```bash
# Events Site
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN_EVENTS/setWebhook?url=WEBHOOK_URL"

# Donate Site
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN_DONATE/setWebhook?url=WEBHOOK_URL"
```

### 2. Загрузите админки на S3

```bash
# Ticket Service Admin
cd ticket-service
aws s3 sync admin/ s3://yallabalagan-ticket-admin-dev/ --profile yallabalagan-dev

# Newsletter Admin
cd newsletter
aws s3 sync admin/ s3://yallabalagan-newsletter-admin-dev/ --profile yallabalagan-dev
```

### 3. Verify SES emails

```bash
aws ses verify-email-identity \
  --email-address tickets@yallabalagan.org \
  --profile yallabalagan-dev

aws ses verify-email-identity \
  --email-address newsletter@yallabalagan.org \
  --profile yallabalagan-dev
```

### 4. Настройте All-Pay webhook

В All-Pay dashboard укажите Payment Webhook URL из outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name yallabalagan-donate-site-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`PaymentWebhookUrl`].OutputValue' \
  --output text \
  --profile yallabalagan-dev
```

---

## 🎯 Получить URLs после деплоя

```bash
# Ticket Service API
aws cloudformation describe-stacks \
  --stack-name yallabalagan-ticket-service-dev \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-dev

# Events Site
aws cloudformation describe-stacks \
  --stack-name yallabalagan-events-site-dev \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-dev

# Donate Site
aws cloudformation describe-stacks \
  --stack-name yallabalagan-donate-site-dev \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-dev

# Newsletter
aws cloudformation describe-stacks \
  --stack-name yallabalagan-newsletter-dev \
  --query 'Stacks[0].Outputs' \
  --profile yallabalagan-dev
```

Или используйте скрипт:

```bash
./deploy-all.sh dev  # В конце покажет все URLs
```

---

## ❌ Troubleshooting

### Ошибка: "Unable to upload artifact"

```bash
# Создайте S3 bucket для SAM
aws s3 mb s3://aws-sam-cli-managed-default-samclisourcebucket-dev \
  --region eu-north-1 \
  --profile yallabalagan-dev
```

### Ошибка: "Invalid credentials"

```bash
# Проверьте профиль
aws sts get-caller-identity --profile yallabalagan-dev

# Перенастройте если нужно
aws configure --profile yallabalagan-dev
```

### Lambda не может подключиться к DynamoDB

```bash
# Проверьте IAM роли
aws cloudformation describe-stack-resources \
  --stack-name yallabalagan-ticket-service-dev \
  --profile yallabalagan-dev
```

### Проверить что всё работает

```bash
# Вызовите API
API_URL=$(aws cloudformation describe-stacks \
  --stack-name yallabalagan-ticket-service-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text \
  --profile yallabalagan-dev)

curl $API_URL/api/events
```

---

## 🗑️ Удаление всего (cleanup)

**ВНИМАНИЕ:** Это удалит ВСЕ данные!

```bash
# Development окружение
sam delete --stack-name yallabalagan-ticket-service-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-events-site-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-donate-site-dev --profile yallabalagan-dev
sam delete --stack-name yallabalagan-newsletter-dev --profile yallabalagan-dev

# Production (ТОЛЬКО ЕСЛИ ТОЧНО УВЕРЕНЫ!)
# Сделайте бэкапы DynamoDB перед этим!
```

---

## 💡 Полезные алиасы

Добавьте в `~/.zshrc` или `~/.bashrc`:

```bash
# YallaBalagan shortcuts
alias yb-deploy-dev='cd ~/Documents/yallabalagan && ./deploy-all.sh dev'
alias yb-deploy-prod='cd ~/Documents/yallabalagan && ./deploy-all.sh prod'
alias yb-check='cd ~/Documents/yallabalagan && ./check-deployment-readiness.sh dev'
alias yb-logs='aws logs tail /aws/lambda/yallabalagan-ticket-api-dev --follow --profile yallabalagan-dev'
```

---

## 📚 Дальше

- Полная документация: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- Ticket Service: [ticket-service/README.md](ticket-service/README.md)
- Newsletter: [newsletter/README.md](newsletter/README.md)

---

**Готово!** 🎉
