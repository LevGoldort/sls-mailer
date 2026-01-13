# File Upload Worker - Backend API

Cloudflare Worker для загрузки больших файлов (>50GB) в R2 storage.

## Архитектура

Использует multipart upload с presigned URLs для обхода лимитов Worker на размер запроса:
- Браузер загружает файлы **напрямую в R2** через presigned URLs
- Worker контролирует доступ через пароли и генерирует presigned URLs
- Метаданные хранятся в Cloudflare KV

## API Endpoints

### Upload Flow
- `POST /api/initiate-upload` - Начать multipart upload
- `POST /api/get-presigned-url` - Получить presigned URL для части
- `POST /api/complete-upload` - Финализировать загрузку
- `POST /api/abort-upload` - Отменить загрузку

### Download Flow
- `GET /api/download/:fileId?token=xxx` - Скачать файл по токену
- `GET /api/download/:fileId` с header `X-Download-Password` - Скачать по паролю

### Admin
- `GET /api/admin/list?key=xxx` - Список всех файлов
- `DELETE /api/admin/:fileId?key=xxx` - Удалить файл

## Setup & Deployment

### 1. Установка зависимостей

```bash
cd upload-service/worker
npm install
```

### 2. Создание R2 bucket

```bash
# Логин в Cloudflare
wrangler login

# Создать R2 bucket
wrangler r2 bucket create video-uploads
```

### 3. Создание KV namespace

```bash
# Создать production KV namespace
wrangler kv:namespace create FILE_METADATA

# Скопировать ID из вывода и добавить в wrangler.toml:
# [[kv_namespaces]]
# binding = "FILE_METADATA"
# id = "ваш-kv-namespace-id"
```

### 4. Получение R2 API токенов

1. Открыть Cloudflare Dashboard → R2 → Settings
2. Создать API token с правами:
   - Object Read & Write
   - Bucket Read & Write
3. Сохранить:
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
4. Endpoint: `https://<account-id>.r2.cloudflarestorage.com`

### 5. Настройка secrets

```bash
# Генерация безопасных паролей
openssl rand -base64 32  # для каждого secret

# Установка secrets
wrangler secret put UPLOAD_PASSWORD
wrangler secret put DOWNLOAD_PASSWORD
wrangler secret put ADMIN_KEY
wrangler secret put TOKEN_SECRET
wrangler secret put R2_ACCESS_KEY_ID
wrangler secret put R2_SECRET_ACCESS_KEY
wrangler secret put R2_ENDPOINT
```

### 6. Обновление wrangler.toml

Раскомментировать и заполнить секции R2 и KV в `wrangler.toml`:

```toml
[[r2_buckets]]
binding = "FILE_STORAGE"
bucket_name = "video-uploads"

[[kv_namespaces]]
binding = "FILE_METADATA"
id = "ваш-kv-namespace-id-здесь"
```

### 7. Деплой

```bash
# Development
npm run dev

# Production
npm run deploy
```

## Тестирование

### Test Upload Initiation

```bash
curl -X POST https://your-worker.workers.dev/api/initiate-upload \
  -H "Content-Type: application/json" \
  -d '{
    "password": "your_upload_password",
    "filename": "test.mp4",
    "fileSize": 104857600,
    "contentType": "video/mp4"
  }'
```

### Test Health Check

```bash
curl https://your-worker.workers.dev/health
```

### Test Admin List

```bash
curl "https://your-worker.workers.dev/api/admin/list?key=your_admin_key"
```

## Структура проекта

```
worker/
├── src/
│   ├── index.js                 # Main entry + router
│   ├── handlers/                # API endpoints
│   │   ├── initiate-upload.js
│   │   ├── get-presigned-url.js
│   │   ├── complete-upload.js
│   │   ├── download.js
│   │   ├── abort-upload.js
│   │   └── admin.js
│   └── lib/                     # Utilities
│       ├── r2-client.js         # R2 SDK wrapper
│       ├── auth.js              # Authentication
│       ├── crypto.js            # Token generation
│       └── cors.js              # CORS helpers
├── wrangler.toml                # Cloudflare config
├── package.json
└── README.md                    # This file
```

## Environment Variables

### В wrangler.toml (публичные)
- `PART_SIZE` - Размер части (100MB по умолчанию)
- `MAX_FILE_SIZE` - Максимальный размер файла (100GB)
- `PRESIGNED_URL_EXPIRY` - Срок действия presigned URL (15 мин)
- `DOWNLOAD_URL_EXPIRY` - Срок действия download URL (1 час)

### Secrets (через wrangler secret put)
- `UPLOAD_PASSWORD` - Пароль для загрузки
- `DOWNLOAD_PASSWORD` - Пароль для скачивания
- `ADMIN_KEY` - Ключ для админки
- `TOKEN_SECRET` - Секрет для генерации токенов
- `R2_ACCESS_KEY_ID` - R2 access key
- `R2_SECRET_ACCESS_KEY` - R2 secret key
- `R2_ENDPOINT` - R2 endpoint URL

## Troubleshooting

### Error: FILE_STORAGE не настроен
- Проверить что R2 bucket создан
- Проверить wrangler.toml - секция `[[r2_buckets]]` раскомментирована

### Error: FILE_METADATA не настроен
- Создать KV namespace: `wrangler kv:namespace create FILE_METADATA`
- Добавить ID в wrangler.toml

### CORS ошибки
- Проверить что frontend домен соответствует настройкам в `src/lib/cors.js`
- Для production обновить `Access-Control-Allow-Origin` на конкретный домен

### Upload fails после 200+ частей
- Presigned URLs истекают через 15 минут
- Решение: увеличить `PRESIGNED_URL_EXPIRY` или использовать параллельную загрузку

## Мониторинг

### Cloudflare Dashboard
- Workers → file-upload-api → Metrics
- R2 → video-uploads → Usage
- Billing → Usage

### Логи
```bash
wrangler tail
```

## Стоимость

### Estimated для 600GB/месяц, файлы по 50GB:
- R2 Storage (140GB avg): **$2.10/мес**
- R2 Operations: **$0** (в рамках free tier)
- Workers: **$0** (в рамках free tier)
- **Итого: ~$2.10/мес**

## Следующие шаги

1. ✅ Backend Worker создан
2. ⏳ Создать frontend (upload.html, admin.html)
3. ⏳ Деплой Worker на production
4. ⏳ Деплой frontend на S3
5. ⏳ Тестирование E2E
