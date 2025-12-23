# 🚀 Пошаговая инструкция по деплою

Эта инструкция поможет вам развернуть сервис загрузки файлов с нуля.

---

## Предварительные требования

- ✅ Node.js 18+ установлен
- ✅ Wrangler CLI установлен: `npm install -g wrangler`
- ✅ AWS CLI установлен (для деплоя frontend на S3)
- ✅ Cloudflare account с подключенной картой
- ✅ AWS account (для S3)

---

## Часть 1: Backend (Cloudflare Worker)

### Шаг 1: Установка зависимостей

```bash
cd upload-service/worker
npm install
```

Ожидаемый результат: `node_modules/` создан, зависимости установлены

### Шаг 2: Логин в Cloudflare

```bash
wrangler login
```

Откроется браузер для авторизации. После успешного логина вернитесь в терминал.

### Шаг 3: Создание R2 bucket

```bash
wrangler r2 bucket create video-uploads
```

Ожидаемый вывод:
```
Created bucket 'video-uploads'
```

### Шаг 4: Создание KV namespace

```bash
wrangler kv:namespace create FILE_METADATA
```

Ожидаемый вывод:
```
🌀 Creating namespace with title "file-upload-api-FILE_METADATA"
✨ Success!
Add the following to your wrangler.toml:
[[kv_namespaces]]
binding = "FILE_METADATA"
id = "abc123def456..."
```

**ВАЖНО:** Скопируйте ID из вывода!

### Шаг 5: Настройка wrangler.toml

Отредактируйте `worker/wrangler.toml`:

1. Раскомментируйте секцию R2:
```toml
[[r2_buckets]]
binding = "FILE_STORAGE"
bucket_name = "video-uploads"
```

2. Раскомментируйте и вставьте ID из Шага 4:
```toml
[[kv_namespaces]]
binding = "FILE_METADATA"
id = "abc123def456..."  # Ваш ID здесь
```

### Шаг 6: Получение R2 API credentials

1. Открыть [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Перейти в **R2** → **Settings**
3. Нажать **Manage R2 API Tokens**
4. Нажать **Create API Token**
5. Выбрать права:
   - ✅ Object Read & Write
   - ✅ Bucket Read & Write
6. Нажать **Create API Token**
7. Сохранить:
   - `Access Key ID` (например: `a1b2c3d4e5f6...`)
   - `Secret Access Key` (например: `xyz789abc...`)
8. Скопировать R2 endpoint (в формате `https://<account-id>.r2.cloudflarestorage.com`)

### Шаг 7: Генерация паролей

```bash
# Сгенерировать 4 случайных пароля
openssl rand -base64 32  # UPLOAD_PASSWORD
openssl rand -base64 32  # DOWNLOAD_PASSWORD
openssl rand -base64 32  # ADMIN_KEY
openssl rand -base64 32  # TOKEN_SECRET
```

Сохраните их в безопасное место (например, password manager).

### Шаг 8: Установка secrets

```bash
cd upload-service/worker

wrangler secret put UPLOAD_PASSWORD
# Ввести пароль из Шага 7

wrangler secret put DOWNLOAD_PASSWORD
# Ввести пароль из Шага 7

wrangler secret put ADMIN_KEY
# Ввести пароль из Шага 7

wrangler secret put TOKEN_SECRET
# Ввести пароль из Шага 7

wrangler secret put R2_ACCESS_KEY_ID
# Ввести Access Key ID из Шага 6

wrangler secret put R2_SECRET_ACCESS_KEY
# Ввести Secret Access Key из Шага 6

wrangler secret put R2_ENDPOINT
# Ввести endpoint из Шага 6 (https://<account-id>.r2.cloudflarestorage.com)
```

Проверить что все установлены:
```bash
wrangler secret list
```

### Шаг 9: Деплой Worker

```bash
npm run deploy
```

Ожидаемый вывод:
```
Published file-upload-api
  https://file-upload-api.abc123.workers.dev
```

**ВАЖНО:** Скопируйте URL Worker - он понадобится для frontend!

### Шаг 10: Тестирование Worker

```bash
# Health check
curl https://ваш-worker-url.workers.dev/health

# Ожидается:
# {"status":"healthy","service":"file-upload-api","timestamp":"..."}
```

Если получена ошибка - проверьте логи:
```bash
wrangler tail
```

---

## Часть 2: Frontend (S3 Static Site)

### Шаг 1: Настройка API URL в frontend

Отредактируйте **2 файла**:

1. `frontend/js/upload-page.js`:
```javascript
const API_BASE_URL = 'https://ваш-worker-url.workers.dev';
```

2. `frontend/js/admin-page.js`:
```javascript
const API_BASE_URL = 'https://ваш-worker-url.workers.dev';
```

Замените `ваш-worker-url.workers.dev` на URL из Часть 1, Шаг 9.

### Шаг 2: Создание S3 bucket

```bash
# Выберите уникальное имя bucket
export BUCKET_NAME="your-upload-service-frontend"

# Создать bucket
aws s3 mb s3://$BUCKET_NAME --region eu-north-1
```

### Шаг 3: Загрузка файлов на S3

```bash
cd upload-service/frontend

aws s3 sync . s3://$BUCKET_NAME --acl public-read
```

Ожидаемый вывод:
```
upload: ./upload.html to s3://...
upload: ./admin.html to s3://...
upload: ./css/styles.css to s3://...
upload: ./js/uploader.js to s3://...
...
```

### Шаг 4: Включение Static Website Hosting

```bash
aws s3 website s3://$BUCKET_NAME \
    --index-document upload.html \
    --error-document upload.html
```

### Шаг 5: Настройка Bucket Policy (публичный доступ)

Создайте файл `bucket-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::ВАШ-BUCKET-NAME/*"
    }
  ]
}
```

Замените `ВАШ-BUCKET-NAME` на ваше имя bucket.

Применить policy:
```bash
aws s3api put-bucket-policy \
    --bucket $BUCKET_NAME \
    --policy file://bucket-policy.json
```

### Шаг 6: Получение URL frontend

```bash
echo "http://$BUCKET_NAME.s3-website-eu-north-1.amazonaws.com"
```

Это ваш URL для доступа к сервису!

---

## Часть 3: Тестирование E2E

### Тест 1: Загрузка файла

1. Открыть `http://ваш-bucket.s3-website-eu-north-1.amazonaws.com/upload.html`
2. Ввести UPLOAD_PASSWORD из Части 1, Шага 7
3. Выбрать тестовый видеофайл (<100MB для начала)
4. Нажать "Загрузить файл"
5. Дождаться завершения (прогресс-бар)
6. **Ожидается:** Получена ссылка для скачивания

### Тест 2: Скачивание файла

1. Скопировать ссылку из Теста 1
2. Открыть в новой вкладке
3. **Ожидается:** Файл начал скачиваться с правильным именем

### Тест 3: Админ-панель

1. Открыть `http://ваш-bucket.s3-website-eu-north-1.amazonaws.com/admin.html`
2. Ввести ADMIN_KEY из Части 1, Шага 7
3. Нажать "Войти"
4. **Ожидается:**
   - Файл из Теста 1 отображается в таблице
   - Корректные размер и дата
   - Кнопка "Копировать" работает
5. Нажать "Удалить" на файле
6. Подтвердить удаление
7. **Ожидается:** Файл исчез из списка

---

## Часть 4: Production Checklist

### Перед запуском в production:

- [ ] Все тесты из Части 3 прошли успешно
- [ ] Пароли сохранены в безопасном месте
- [ ] S3 bucket policy настроен правильно (публичный доступ)
- [ ] Worker URL работает (health check проходит)
- [ ] Frontend URL работает
- [ ] Протестирована загрузка большого файла (>1GB)
- [ ] Настроен мониторинг в Cloudflare Dashboard (Billing Alerts)

### Опционально (но рекомендуется):

- [ ] Custom domain для Worker: `api.yourdomain.com`
- [ ] Custom domain для Frontend: `upload.yourdomain.com`
- [ ] CloudFront перед S3 (для HTTPS и лучшей производительности)
- [ ] Backup паролей в password manager

---

## Часть 5: Обновление после изменений

### Обновить Worker:

```bash
cd upload-service/worker
npm run deploy
```

### Обновить Frontend:

```bash
cd upload-service/frontend
aws s3 sync . s3://$BUCKET_NAME --acl public-read
```

### Обновить secrets:

```bash
cd upload-service/worker
wrangler secret put UPLOAD_PASSWORD  # и т.д.
```

---

## Troubleshooting

### Worker deployment fails: "Account ID not found"

```bash
wrangler login
# Убедиться что залогинены в правильный аккаунт
```

### R2 bucket creation fails: "Billing required"

- Открыть Cloudflare Dashboard → Billing
- Добавить платежную карту
- Retry: `wrangler r2 bucket create video-uploads`

### Frontend shows 403 Forbidden

- Проверить bucket policy: `aws s3api get-bucket-policy --bucket $BUCKET_NAME`
- Убедиться что `s3:GetObject` разрешен для всех

### CORS errors в консоли браузера

- Проверить что API_BASE_URL правильный в frontend JS файлах
- Проверить что Worker деплоился без ошибок
- Проверить CORS headers в worker/src/lib/cors.js

### "Invalid password" при загрузке

- Проверить что secret установлен: `wrangler secret list`
- Проверить что используете правильный пароль
- Re-deploy Worker: `npm run deploy`

---

## Готово! 🎉

Теперь у вас работающий сервис загрузки больших файлов!

**Следующие шаги:**
- Поделиться URL и паролями с командой
- Мониторить использование в Cloudflare Dashboard
- При необходимости - настроить custom domains
