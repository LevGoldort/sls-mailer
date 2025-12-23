#!/bin/bash

# 🚀 Deploy Script для Upload Service
# Деплой Worker и Frontend (Dev + Prod)

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
WORKER_DIR="worker"
FRONTEND_DIR="frontend"
S3_BUCKET_DEV="yallabalagan-upload-service"
S3_BUCKET_PROD="yallabalagan-upload-service-prod"

# Функции для вывода
print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Деплой Worker
deploy_worker() {
    print_header "Deploying Cloudflare Worker"

    cd "$WORKER_DIR"

    print_info "Running npm run deploy..."
    npm run deploy

    print_success "Worker deployed successfully!"
    echo ""

    cd ..
}

# Деплой Frontend в Dev
deploy_frontend_dev() {
    print_header "Deploying Frontend to DEV (S3)"

    cd "$FRONTEND_DIR"

    print_info "Syncing to s3://$S3_BUCKET_DEV..."
    aws s3 sync . s3://$S3_BUCKET_DEV

    print_success "Frontend deployed to DEV!"
    print_info "URL: http://$S3_BUCKET_DEV.s3-website.eu-north-1.amazonaws.com/upload.html"
    echo ""

    cd ..
}

# Деплой Frontend в Prod
deploy_frontend_prod() {
    print_header "Deploying Frontend to PROD (S3)"

    cd "$FRONTEND_DIR"

    print_info "Syncing to s3://$S3_BUCKET_PROD..."
    aws s3 sync . s3://$S3_BUCKET_PROD

    print_success "Frontend deployed to PROD!"
    print_info "URL: http://$S3_BUCKET_PROD.s3-website.eu-north-1.amazonaws.com/upload.html"
    echo ""

    cd ..
}

# Показать помощь
show_help() {
    echo "🚀 Upload Service Deploy Script"
    echo ""
    echo "Использование:"
    echo "  ./deploy.sh [options]"
    echo ""
    echo "Опции:"
    echo "  --worker         Деплой только Worker"
    echo "  --frontend-dev   Деплой только Frontend в Dev"
    echo "  --frontend-prod  Деплой только Frontend в Prod"
    echo "  --frontend       Деплой Frontend в Dev и Prod"
    echo "  --all            Деплой всего (Worker + Frontend Dev + Prod)"
    echo "  --help           Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  ./deploy.sh --all                    # Полный деплой"
    echo "  ./deploy.sh --worker                 # Только Worker"
    echo "  ./deploy.sh --frontend               # Frontend в Dev и Prod"
    echo "  ./deploy.sh --worker --frontend-prod # Worker + Frontend в Prod"
    echo ""
}

# Главная логика
main() {
    # Если нет аргументов, показать помощь
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi

    # Проверка что мы в правильной директории
    if [ ! -d "$WORKER_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
        print_error "Запускайте скрипт из корня upload-service!"
        exit 1
    fi

    # Флаги
    DEPLOY_WORKER=false
    DEPLOY_FRONTEND_DEV=false
    DEPLOY_FRONTEND_PROD=false

    # Парсинг аргументов
    while [[ $# -gt 0 ]]; do
        case $1 in
            --worker)
                DEPLOY_WORKER=true
                shift
                ;;
            --frontend-dev)
                DEPLOY_FRONTEND_DEV=true
                shift
                ;;
            --frontend-prod)
                DEPLOY_FRONTEND_PROD=true
                shift
                ;;
            --frontend)
                DEPLOY_FRONTEND_DEV=true
                DEPLOY_FRONTEND_PROD=true
                shift
                ;;
            --all)
                DEPLOY_WORKER=true
                DEPLOY_FRONTEND_DEV=true
                DEPLOY_FRONTEND_PROD=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                print_error "Неизвестная опция: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Деплой
    print_header "🚀 Starting Deployment"
    echo ""

    if [ "$DEPLOY_WORKER" = true ]; then
        deploy_worker
    fi

    if [ "$DEPLOY_FRONTEND_DEV" = true ]; then
        deploy_frontend_dev
    fi

    if [ "$DEPLOY_FRONTEND_PROD" = true ]; then
        deploy_frontend_prod
    fi

    print_header "🎉 Deployment Complete!"

    # Итоговая информация
    if [ "$DEPLOY_WORKER" = true ]; then
        echo -e "${GREEN}Worker:${NC} https://file-upload-api.yalla.workers.dev"
    fi

    if [ "$DEPLOY_FRONTEND_DEV" = true ]; then
        echo -e "${GREEN}Frontend DEV:${NC} http://$S3_BUCKET_DEV.s3-website.eu-north-1.amazonaws.com/upload.html"
    fi

    if [ "$DEPLOY_FRONTEND_PROD" = true ]; then
        echo -e "${GREEN}Frontend PROD:${NC} http://$S3_BUCKET_PROD.s3-website.eu-north-1.amazonaws.com/upload.html"
    fi

    echo ""
}

# Запуск
main "$@"
