#!/bin/bash
#
# Deploy Email Sender Lambda function для Ticket Service
# Usage: ./scripts/deploy-email-sender.sh
#

set -e

FUNCTION_NAME="yallabalagan-email-sender"
REGION="eu-north-1"

echo "🚀 Deploying Lambda function: $FUNCTION_NAME"
echo ""

# Создаем временную директорию для пакета
TEMP_DIR=$(mktemp -d)
echo "📦 Creating deployment package in $TEMP_DIR"

# Копируем код
cp -r models "$TEMP_DIR/"
cp -r utils "$TEMP_DIR/"
cp lambdas/email-sender.py "$TEMP_DIR/lambda_function.py"

# Устанавливаем зависимости
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt -t "$TEMP_DIR/"

# Создаем zip
cd "$TEMP_DIR"
ZIP_FILE="$TEMP_DIR/deployment.zip"
zip -rq "$ZIP_FILE" .
cd - > /dev/null

echo "✅ Package created: $(du -h "$ZIP_FILE" | cut -f1)"

# Проверяем, существует ли функция
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "⬆️  Updating existing Lambda function..."
    aws lambda update-function-code \
      --function-name "$FUNCTION_NAME" \
      --zip-file "fileb://$ZIP_FILE" \
      --region "$REGION" \
      --no-cli-pager > /dev/null
else
    echo "🆕 Creating new Lambda function..."
    # Создаем функцию (нужны базовые настройки)
    aws lambda create-function \
      --function-name "$FUNCTION_NAME" \
      --runtime python3.11 \
      --role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/lambda-execution-role \
      --handler lambda_function.lambda_handler \
      --zip-file "fileb://$ZIP_FILE" \
      --timeout 30 \
      --memory-size 256 \
      --region "$REGION" \
      --no-cli-pager > /dev/null || echo "⚠️  Note: You may need to create the function manually with proper IAM role"
fi

echo "✅ Lambda updated successfully!"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Set environment variables:"
echo "      - SENDER_EMAIL (verified SES email)"
echo "      - EVENTS_TABLE, ORDERS_TABLE, LOCATIONS_TABLE"
echo "   2. Configure IAM permissions for SES"
echo "   3. Check logs:"
echo "      aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"

