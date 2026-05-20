#!/bin/bash
#
# Deploy SMS Sender Lambda function для Ticket Service
# Usage: ./scripts/deploy-sms-sender.sh [skip_deps]
#

set -e

FUNCTION_NAME="yallabalagan-sms-sender"
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
cp lambdas/sms-sender.py "$TEMP_DIR/lambda_function.py"

# Устанавливаем зависимости (если не пропускаем)
if [ "$SKIP_DEPS" = "true" ]; then
    echo "⚡ Skipping dependency installation (quick mode)"
    if [ -d "/tmp/sms-sender-deps-cache" ]; then
        echo "📋 Using cached dependencies..."
        cp -r /tmp/sms-sender-deps-cache/* "$TEMP_DIR/" 2>/dev/null || true
    fi
else
    echo "📥 Installing dependencies..."
    pip install -q -r requirements.txt -t "$TEMP_DIR/"
    # Cache dependencies
    mkdir -p /tmp/sms-sender-deps-cache
    rsync -a --exclude='models' --exclude='utils' --exclude='lambda_function.py' "$TEMP_DIR/" /tmp/sms-sender-deps-cache/ 2>/dev/null || true
fi

# Создаем zip
cd "$TEMP_DIR"
ZIP_FILE="$TEMP_DIR/deployment.zip"
zip -rq "$ZIP_FILE" .
cd - > /dev/null

echo "✅ Package created: $(du -h "$ZIP_FILE" | cut -f1)"

# Обновляем функцию
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
