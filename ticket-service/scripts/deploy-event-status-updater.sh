#!/bin/bash
set -e

SKIP_DEPS=${1:-false}

echo "🚀 Deploying event-status-updater Lambda function..."

cd "$(dirname "$0")/.."

# Create deployment package
echo "📦 Creating deployment package..."
mkdir -p lambda-event-status-updater
cp lambdas/event-status-updater.py lambda-event-status-updater/lambda_function.py

# Install dependencies
if [ "$SKIP_DEPS" != "true" ]; then
    echo "📥 Installing dependencies (pytz for timezone handling)..."
    cd lambda-event-status-updater
    pip install -q pytz -t .
    cd ..
else
    echo "⚡ Skipping dependency installation"
fi

cd lambda-event-status-updater
zip -r ../event-status-updater.zip .
cd ..

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name yallabalagan-event-status-updater --region eu-north-1 --no-cli-pager 2>&1 || echo "not found")

if [[ "$FUNCTION_EXISTS" == *"not found"* ]]; then
    echo "📤 Creating new Lambda function..."

    # Create function
    aws lambda create-function \
      --function-name yallabalagan-event-status-updater \
      --runtime python3.11 \
      --role arn:aws:iam::982534389905:role/YallaBalagan-TicketService-Lambda-Role \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://event-status-updater.zip \
      --timeout 60 \
      --memory-size 256 \
      --environment Variables="{DYNAMODB_TABLE=yallabalagan-tickets}" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

    echo "⏰ Setting up EventBridge schedule (runs every hour)..."

    # Create EventBridge rule to run every hour
    aws events put-rule \
      --name yallabalagan-event-status-updater-schedule \
      --schedule-expression "rate(1 hour)" \
      --state ENABLED \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

    # Add Lambda permission for EventBridge
    aws lambda add-permission \
      --function-name yallabalagan-event-status-updater \
      --statement-id EventBridgeInvoke \
      --action lambda:InvokeFunction \
      --principal events.amazonaws.com \
      --source-arn "arn:aws:events:eu-north-1:982534389905:rule/yallabalagan-event-status-updater-schedule" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

    # Add Lambda as target to EventBridge rule
    aws events put-targets \
      --rule yallabalagan-event-status-updater-schedule \
      --targets "Id"="1","Arn"="arn:aws:lambda:eu-north-1:982534389905:function:yallabalagan-event-status-updater" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

else
    echo "🔄 Updating existing Lambda function..."

    # Update function code
    aws lambda update-function-code \
      --function-name yallabalagan-event-status-updater \
      --zip-file fileb://event-status-updater.zip \
      --region eu-north-1 \
      --no-cli-pager > /dev/null
fi

# Cleanup
rm -rf lambda-event-status-updater event-status-updater.zip

echo "✅ Lambda function deployed successfully!"

# Cleanup
rm -f response.json

echo "✅ Deployment complete!"
echo "⏰ Function will run automatically every hour"
