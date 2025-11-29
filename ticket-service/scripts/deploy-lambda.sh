#!/bin/bash
#
# Deploy Lambda function для Ticket Service API
# Usage: ./scripts/deploy-lambda.sh [skip_deps]
#

set -e

FUNCTION_NAME="yallabalagan-ticket-api"
REGION="eu-north-1"
SKIP_DEPS=${1:-false}

echo "🚀 Deploying Lambda function: $FUNCTION_NAME"
echo ""

# Создаем временную директорию для пакета
TEMP_DIR=$(mktemp -d)
echo "📦 Creating deployment package in $TEMP_DIR"

# Копируем код
cp -r models "$TEMP_DIR/"
cp -r utils "$TEMP_DIR/"
cp lambdas/api-handler.py "$TEMP_DIR/lambda_function.py"

# Устанавливаем зависимости (если не пропускаем)
if [ "$SKIP_DEPS" = "true" ]; then
    echo "⚡ Skipping dependency installation (quick mode)"
    # Copy existing dependencies from previous deployment if available
    if [ -d "/tmp/lambda-deps-cache" ]; then
        echo "📋 Using cached dependencies..."
        cp -r /tmp/lambda-deps-cache/* "$TEMP_DIR/" 2>/dev/null || true
    fi
else
    echo "📥 Installing dependencies..."
    pip install -q -r requirements.txt -t "$TEMP_DIR/"
    # Cache dependencies for future quick deploys
    mkdir -p /tmp/lambda-deps-cache
    rsync -a --exclude='models' --exclude='utils' --exclude='lambda_function.py' "$TEMP_DIR/" /tmp/lambda-deps-cache/ 2>/dev/null || true
fi

# Создаем zip
cd "$TEMP_DIR"
ZIP_FILE="$TEMP_DIR/deployment.zip"
zip -rq "$ZIP_FILE" .
cd - > /dev/null

echo "✅ Package created: $(du -h "$ZIP_FILE" | cut -f1)"

# Обновляем Lambda
echo "⬆️  Uploading to AWS Lambda..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_FILE" \
  --region "$REGION" \
  --no-cli-pager > /dev/null

echo "✅ Lambda updated successfully!"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📝 Check logs:"
echo "   aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
