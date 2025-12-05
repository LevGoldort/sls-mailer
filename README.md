# YallaBalagan - AWS Serverless Infrastructure

Serverless инфраструктура для четырёх систем YallaBalagan на базе AWS (Lambda, DynamoDB, S3, API Gateway).

---

## 🏗️ Архитектура

Проект состоит из 4 независимых сервисов:

### 1. **Ticket Service** (`ticket-service/`)
Билетная система с админкой и интеграцией All-Pay
- 5 Lambda функций
- 3 DynamoDB таблицы (events, locations, orders)
- API Gateway + S3 для frontend
- Email уведомления через SES

### 2. **Events Site** (`events-site/`)
Главный сайт с событиями (интеграция с Notion)
- 2 Lambda функции
- Telegram bot для управления
- Автогенерация статического сайта

### 3. **Donate Site** (`donate-site/`)
Сайт для пожертвований и краудфандинга
- 4 Lambda функции
- Интеграция с 3 Notion базами данных
- All-Pay payment processing
- Telegram bot для админки

### 4. **Newsletter** (`newsletter/`)
Email рассылки (альтернатива Mailchimp)
- 5 Lambda функций
- Email tracking (открытия, клики)
- Веб-админка для управления кампаниями
- SES для отправки писем

---

## 🚀 Быстрый старт

### Предварительные требования

1. **AWS CLI** (настроен для prod и dev аккаунтов)
2. **AWS SAM CLI** (для деплоя)
3. **Python 3.11+**

### Установка SAM CLI

```bash
# macOS
brew install aws-sam-cli

# Linux
# См. https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
```

### Настройка AWS профилей

```bash
# Production account
aws configure --profile yallabalagan-prod
# Введите Access Key, Secret Key, region=eu-north-1

# Development account
aws configure --profile yallabalagan-dev
# Введите Access Key, Secret Key, region=eu-north-1
```

### Подготовка переменных окружения

```bash
# 1. Скопируйте example файл
cp .env.example .env.prod
cp .env.example .env.dev

# 2. Заполните все необходимые токены и секреты
nano .env.prod  # или используйте ваш любимый редактор
```

### Деплой всех сервисов

```bash
# Deploy на DEV окружение
./deploy-all.sh dev

# Deploy на PROD окружение
./deploy-all.sh prod
```

### Деплой отдельного сервиса

```bash
# Например, только ticket-service
cd ticket-service
sam build
sam deploy --config-env dev --profile yallabalagan-dev

# С параметрами
sam deploy --config-env dev --profile yallabalagan-dev \
  --parameter-overrides \
    TelegramBotToken=bot123:ABC \
    AllPayWebhookSecret=secret123
```

---

## 📁 Структура проекта

```
yallabalagan/
├── ticket-service/          # Билетная система
│   ├── template.yaml        # SAM CloudFormation template
│   ├── samconfig.toml       # SAM конфигурация (prod/dev)
│   ├── lambdas/             # Lambda функции
│   ├── models/              # Data models
│   ├── utils/               # Утилиты
│   ├── admin/               # HTML админка
│   ├── frontend/            # Frontend templates
│   └── scripts/             # Деплой скрипты (legacy)
│
├── events-site/             # Главный сайт
│   ├── template.yaml
│   ├── samconfig.toml
│   └── lambdas/
│
├── donate-site/             # Сайт для пожертвований
│   ├── template.yaml
│   ├── samconfig.toml
│   └── lambdas/
│
├── newsletter/              # Email рассылки
│   ├── template.yaml
│   ├── samconfig.toml
│   ├── lambdas/
│   └── admin/               # Web админка
│
├── deploy-all.sh            # Деплой всех сервисов
├── .env.example             # Пример переменных окружения
├── .env.prod                # Production secrets (НЕ в git!)
├── .env.dev                 # Development secrets (НЕ в git!)
├── DEPLOYMENT_GUIDE.md      # Подробная документация
└── README.md                # Этот файл
```

---

## 📚 Документация

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Полное руководство по деплою
- **[ticket-service/AWS_SETUP.md](ticket-service/AWS_SETUP.md)** - Настройка Ticket Service
- **[newsletter/README.md](newsletter/README.md)** - Документация Newsletter системы

---

## 🔑 Переменные окружения

См. [.env.example](.env.example) для полного списка.

Основные секреты:

| Сервис | Переменная | Где взять |
|--------|------------|-----------|
| All | AWS Profile | `aws configure --profile yallabalagan-prod` |
| Ticket | `TELEGRAM_BOT_TOKEN_TICKET` | @BotFather |
| Ticket | `ALLPAY_WEBHOOK_SECRET` | All-Pay dashboard |
| Events | `NOTION_TOKEN` | notion.so/my-integrations |
| Events | `NOTION_DATABASE_ID_EVENTS` | URL Notion базы |
| Newsletter | `NEWSLETTER_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |

---

## 💰 Стоимость

### Production (~$15-30/месяц)
- Lambda: $5-10
- DynamoDB: $2-5 (PAY_PER_REQUEST)
- S3: $1-3
- API Gateway: $3-5
- SES: $0.10/1000 писем

### Development
Практически бесплатно (AWS Free Tier)

**Экономия vs SaaS:**
- Mailchimp: $100/мес → $0.10/1000 писем
- Heroku/Railway: $25-50/мес → $5-10/мес Lambda
- **Итого: ~$400+/мес → ~$20/мес** 🎉

---

## 🛠️ Команды

### Деплой

```bash
# Все сервисы
./deploy-all.sh prod

# Отдельный сервис
cd ticket-service
sam build && sam deploy --config-env default --profile yallabalagan-prod
```

### Обновление кода (без изменения инфраструктуры)

```bash
# Быстрое обновление Lambda
cd ticket-service
sam build
sam deploy --no-confirm-changeset --profile yallabalagan-prod
```

### Мониторинг

```bash
# Логи в реальном времени
aws logs tail /aws/lambda/yallabalagan-ticket-api-prod --follow --profile yallabalagan-prod

# Или через SAM
sam logs --stack-name yallabalagan-ticket-service-prod --tail --profile yallabalagan-prod
```

### Локальное тестирование

```bash
# Локальный API Gateway
cd ticket-service
sam local start-api

# Тест конкретной Lambda
sam local invoke TicketApiFunction --event events/test.json
```

### Удаление стека

```bash
# ВНИМАНИЕ: Это удалит ВСЕ данные!
sam delete --stack-name yallabalagan-ticket-service-dev --profile yallabalagan-dev
```

---

## 🔒 Безопасность

### Перед деплоем на PROD:

1. ✅ Используйте **AWS Secrets Manager** для секретов (вместо .env файлов)
2. ✅ Включите **CloudTrail** для аудита
3. ✅ Настройте **Budget Alerts**
4. ✅ Включите **MFA** на AWS аккаунте
5. ✅ Настройте **DynamoDB Point-in-Time Recovery** (бэкапы)
6. ✅ Verify **SES email addresses**

### Важно:

```bash
# Добавьте в .gitignore
echo ".env.prod" >> .gitignore
echo ".env.dev" >> .gitignore
```

---

## 🐛 Troubleshooting

### Ошибка: "Unable to upload artifact"

```bash
# Создайте S3 bucket для SAM
aws s3 mb s3://aws-sam-cli-managed-default-samclisourcebucket-prod \
  --region eu-north-1 \
  --profile yallabalagan-prod
```

### Ошибка: "Invalid template"

```bash
sam validate --profile yallabalagan-prod
```

### Lambda не имеет доступа к DynamoDB

Проверьте IAM политики в CloudFormation Console или:

```bash
aws cloudformation describe-stack-resources \
  --stack-name yallabalagan-ticket-service-prod \
  --profile yallabalagan-prod
```

---

## 📊 Мониторинг и алерты

### CloudWatch Dashboard

```bash
# Создайте dashboard для мониторинга
aws cloudwatch put-dashboard \
  --dashboard-name YallaBalagan-Prod \
  --dashboard-body file://monitoring/dashboard.json \
  --profile yallabalagan-prod
```

### Budget Alert

```bash
# Создайте бюджет с алертами
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget file://budget.json \
  --profile yallabalagan-prod
```

---

## 🚧 Миграция с существующей инфраструктуры

Если у вас уже есть развернутая инфраструктура:

1. **Импорт существующих ресурсов** в CloudFormation
2. **Постепенная миграция** сервис за сервисом
3. **Тестирование на dev** перед миграцией prod

См. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) раздел "Migration"

---

## 📝 TODO

- [ ] CI/CD с GitHub Actions
- [ ] CloudFront для CDN
- [ ] Custom domain names
- [ ] WAF для защиты API
- [ ] Automated testing

---

## 🤝 Contributing

Для внесения изменений:

1. Тестируйте на `dev` окружении
2. Используйте `sam validate` перед commit
3. Обновляйте документацию

---

## 📄 Лицензия

Private project - YallaBalagan

---

## 🆘 Поддержка

Вопросы? Проблемы?

1. Проверьте [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
2. Посмотрите CloudWatch Logs
3. Проверьте IAM permissions

---

**Готово!** 🎉

Теперь вся ваша инфраструктура описана как код и может быть развернута на любом AWS аккаунте одной командой.
