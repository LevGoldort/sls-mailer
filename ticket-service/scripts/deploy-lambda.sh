#!/bin/bash
#
# Deploy Lambda function для Ticket Service API
# Usage: ./scripts/deploy-lambda.sh
#

set -e

FUNCTION_NAME="yallabalagan-ticket-api"
REGION="eu-north-1"

echo "🚀 Deploying Lambda function: $FUNCTION_NAME"
echo ""

# Создаем временную директорию для пакета
TEMP_DIR=$(mktemp -d)
echo "📦 Creating deployment package in $TEMP_DIR"

# Копируем код
cp -r models "$TEMP_DIR/"
cp -r utils "$TEMP_DIR/"
cp lambdas/api-handler.py "$TEMP_DIR/lambda_function.py"

# Устанавливаем зависимости
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt -t "$TEMP_DIR/"

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
