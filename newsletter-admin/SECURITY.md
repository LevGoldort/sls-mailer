# Security Setup - Newsletter Admin

Защита веб-админки от несанкционированного доступа.

---

## 🚨 Текущее состояние: НЕЗАЩИЩЕНО

**Проблема:** Любой, кто знает URL `http://yallabalagan-newsletter-admin.s3-website.eu-north-1.amazonaws.com/`, может:
- Просматривать все кампании
- Создавать кампании
- Отправлять письма всем подписчикам

**Решение:** Добавить аутентификацию.

---

## ✅ Решение 1: CloudFront + Basic Auth (Рекомендуется)

### Плюсы
- ✅ Быстрая настройка (15-20 минут)
- ✅ Не требует изменений в коде админки
- ✅ Работает во всех браузерах
- ✅ HTTPS из коробки

### Шаги

#### 1. Создать Lambda@Edge функцию

**ВАЖНО:** Lambda@Edge работает только в регионе **us-east-1**!

```bash
# Создать функцию
aws lambda create-function \
  --region us-east-1 \
  --function-name newsletter-admin-auth \
  --runtime nodejs18.x \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-edge-role \
  --handler index.handler \
  --zip-file fileb://lambda-auth.zip \
  --timeout 5 \
  --memory-size 128
```

Код функции: `cloudfront-basic-auth-lambda.js`

**⚠️ ВАЖНО:** Измените пароль в файле!

```javascript
const authUser = 'admin';
const authPass = 'YOUR_STRONG_PASSWORD_HERE'; // Замените это!
```

#### 2. Создать IAM роль для Lambda@Edge

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "lambda.amazonaws.com",
          "edgelambda.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Прикрепить managed policy: `AWSLambdaBasicExecutionRole`

#### 3. Опубликовать версию Lambda

Lambda@Edge требует конкретную версию (не $LATEST):

```bash
aws lambda publish-version \
  --region us-east-1 \
  --function-name newsletter-admin-auth
```

Запомните ARN версии (например, `...newsletter-admin-auth:1`)

#### 4. Создать CloudFront Distribution

AWS Console → CloudFront → Create Distribution:

**Origin:**
- Origin Domain: `yallabalagan-newsletter-admin.s3-website.eu-north-1.amazonaws.com`
- Protocol: HTTP only (S3 website endpoint)

**Default Cache Behavior:**
- Viewer Protocol Policy: Redirect HTTP to HTTPS
- Allowed HTTP Methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
- Cache Policy: CachingDisabled (для динамического контента)

**Lambda Function Associations:**
- Event Type: **Viewer Request**
- Lambda Function ARN: `arn:aws:lambda:us-east-1:ACCOUNT:function:newsletter-admin-auth:1`

**Settings:**
- Default Root Object: `index.html`
- Custom SSL Certificate: (опционально, для custom domain)

#### 5. Дождаться деплоя

CloudFront деплой занимает ~15-20 минут.

#### 6. Тестирование

Откройте CloudFront URL (например, `https://d111111abcdef8.cloudfront.net`):

1. Должен появиться браузерный popup с запросом логина/пароля
2. Введите credentials из Lambda функции
3. После успешного логина откроется админка

---

## ✅ Решение 2: API Gateway Authorizer (Защита API)

Вместо защиты админки, защитите сам API.

### Плюсы
- ✅ Админка остается простой
- ✅ API защищен от прямых запросов

### Минусы
- ❌ Token виден в JavaScript коде
- ❌ Любой может скопировать token из DevTools

### Шаги

#### 1. Включить API Key в API Gateway

AWS Console → API Gateway → newsletter-admin-api:

1. **API Keys** → Create API Key
   - Name: `newsletter-admin-key`
   - Auto-generate key
   - Save the key!

2. **Usage Plans** → Create
   - Name: `newsletter-admin-plan`
   - Throttling: 100 requests/sec
   - Quota: 10,000 requests/month
   - Add API Stage: newsletter-admin-api / prod

3. **Associate API Key to Usage Plan**

4. **Update Routes** → Require API Key
   - Для каждого route: Settings → API Key Required: ✓

5. **Deploy API**

#### 2. Обновить HTML файлы

Добавьте header во все fetch запросы:

```javascript
const API_KEY = 'your-api-key-here';

fetch(`${API_BASE_URL}/campaigns`, {
    headers: {
        'x-api-key': API_KEY
    }
})
```

**⚠️ ПРОБЛЕМА:** API Key виден в коде! Любой может его украсть из источника страницы.

---

## ✅ Решение 3: AWS Cognito (Профессиональная аутентификация)

Полноценная система управления пользователями.

### Плюсы
- ✅ Профессиональная аутентификация
- ✅ Управление пользователями (add/remove)
- ✅ MFA, password reset, email verification
- ✅ JWT tokens

### Минусы
- ❌ Сложная настройка
- ❌ Требует изменений в HTML (добавить login page)

### Шаги (кратко)

1. **Создать Cognito User Pool**
2. **Создать App Client**
3. **Добавить пользователей**
4. **Обновить HTML:**
   - Добавить login.html страницу
   - Использовать AWS Amplify для аутентификации
   - Передавать JWT token в API запросы
5. **Добавить Cognito Authorizer в API Gateway**

Полная инструкция: https://docs.aws.amazon.com/cognito/

---

## 🎯 Рекомендация

**Для быстрого старта:** Используйте **CloudFront + Basic Auth**

**Для production с несколькими админами:** Используйте **Cognito**

---

## 🔐 Дополнительные меры безопасности

### 1. IP Whitelist (опционально)

Ограничьте доступ только с ваших IP:

CloudFront → Security → AWS WAF:
- Create IP Set: Ваши IP адреса
- Create Rule: Allow only from IP Set

### 2. Custom Domain с SSL

Используйте custom domain вместо CloudFront URL:
- `admin.yallabalagan.org`
- SSL certificate через ACM (в us-east-1!)
- Скрыть прямой S3 URL

### 3. Monitoring

CloudWatch Alarms:
- Alert при >100 неудачных auth попыток
- Alert при создании >10 кампаний в час

### 4. Audit Logging

Включите CloudTrail для логирования:
- Кто и когда логинился
- Какие действия выполнялись

---

## 📝 Quick Start: CloudFront + Basic Auth

```bash
# 1. Изменить пароль в cloudfront-basic-auth-lambda.js
vim cloudfront-basic-auth-lambda.js

# 2. Создать zip
zip lambda-auth.zip cloudfront-basic-auth-lambda.js

# 3. Создать Lambda в us-east-1
aws lambda create-function \
  --region us-east-1 \
  --function-name newsletter-admin-auth \
  --runtime nodejs18.x \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-edge-role \
  --handler cloudfront-basic-auth-lambda.handler \
  --zip-file fileb://lambda-auth.zip

# 4. Publish version
aws lambda publish-version \
  --region us-east-1 \
  --function-name newsletter-admin-auth

# 5. Создать CloudFront (через Console - проще)
# 6. Подождать 15 минут
# 7. Тестировать!
```

---

## 🧪 Тестирование

После настройки:

1. Откройте CloudFront URL
2. Должен появиться popup с запросом логина
3. Введите credentials
4. Админка должна открыться
5. Попробуйте в инкогнито - должен снова запросить пароль

---

## ❓ FAQ

**Q: Можно ли использовать секретный URL вместо аутентификации?**
A: Нет! Security through obscurity - плохая практика. URL можно случайно передать кому-то или он попадет в логи.

**Q: Где хранить пароль для Basic Auth?**
A: Для production используйте AWS Secrets Manager вместо hardcoded пароля в Lambda.

**Q: Можно ли добавить несколько пользователей в Basic Auth?**
A: Да, но лучше перейти на Cognito для управления пользователями.

**Q: CloudFront стоит дорого?**
A: Для админки с малым трафиком: ~$0.50-1.00/месяц. Lambda@Edge: практически бесплатно.

---

## 🆘 Support

Проблемы с настройкой? Проверьте:
- Lambda@Edge создан в us-east-1 (обязательно!)
- Lambda version опубликована (не $LATEST)
- CloudFront деплой завершен (15-20 мин)
- Browser cache очищен (Ctrl+Shift+R)
