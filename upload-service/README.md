# 🚀 Upload Service - Yallabalagan

Сервис для загрузки и обмена большими файлами (до 500GB).

## Архитектура

- **Backend:** Cloudflare Worker + R2 Storage
- **Frontend:** Static website на AWS S3
- **Upload:** Multipart upload с presigned URLs

## URLs

### Production
- **Frontend:** http://yallabalagan-upload-service-prod.s3-website.eu-north-1.amazonaws.com/upload.html
- **Admin:** http://yallabalagan-upload-service-prod.s3-website.eu-north-1.amazonaws.com/admin.html

### Development
- **Frontend:** http://yallabalagan-upload-service.s3-website.eu-north-1.amazonaws.com/upload.html
- **Admin:** http://yallabalagan-upload-service.s3-website.eu-north-1.amazonaws.com/admin.html

### Backend (общий для dev и prod)
- **API:** https://file-upload-api.yalla.workers.dev

## Деплой

### Быстрый деплой всего

```bash
./deploy.sh --all
```

### Деплой только Worker

```bash
./deploy.sh --worker
```

### Деплой только Frontend

```bash
# В Dev и Prod
./deploy.sh --frontend

# Только Dev
./deploy.sh --frontend-dev

# Только Prod
./deploy.sh --frontend-prod
```

### Комбинации

```bash
# Worker + Frontend в Prod
./deploy.sh --worker --frontend-prod

# Worker + Frontend в Dev
./deploy.sh --worker --frontend-dev
```

## Как это работает

1. **Инициация загрузки:**
   - Пользователь вводит пароль и выбирает файл
   - Frontend → Worker: создать multipart upload
   - Worker → R2: начать multipart upload
   - Worker → Frontend: uploadId и параметры

2. **Загрузка частей:**
   - Frontend → Worker: дай presigned URL для части N
   - Worker → Frontend: presigned URL (действует 15 минут)
   - Frontend → R2 напрямую: загрузка 100MB chunk
   - Повторить для всех частей (параллельно 3 части)

3. **Завершение:**
   - Frontend → Worker: все части загружены, вот ETags
   - Worker → R2: завершить multipart upload
   - Worker → Frontend: ссылка для скачивания

## Технические детали

### Лимиты
- Максимальный размер файла: **500GB**
- Размер части: **100MB**
- Одновременных частей: **3**
- Retry попыток: **3**

### API Endpoints

- `POST /api/initiate-upload` - Начать загрузку
- `POST /api/get-presigned-url` - Получить presigned URL для части
- `POST /api/complete-upload` - Завершить загрузку
- `POST /api/abort-upload` - Отменить загрузку
- `GET /api/download/:fileId` - Скачать файл
- `GET /api/admin/list` - Список файлов (admin)
- `DELETE /api/admin/:fileId` - Удалить файл (admin)

## Фишки

- 🌈 Упячка-стиль шапка с безумными анимациями
- 🤖 "СЛАВА РОБОТАМ!"
- 💾 "В ЖОПУ ДРАЙВ ЯНДЕКС ДИСК ВИТРАНСФЕР И ДИСКЕТЫ!"
- 🚀 Параллельная загрузка частей
- ⚡ Retry при ошибках
- 📊 Real-time прогресс с скоростью
- 🎨 Адаптивный дизайн

---

**Сделано с любовью для обмена любыми большими файлами** 🎬
