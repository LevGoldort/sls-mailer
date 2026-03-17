#!/bin/bash
# Deploy ticket-service to Production - Lambda Updates Only
#
# This script updates ONLY Lambda functions on prod without using CloudFormation.
# Existing infrastructure (DynamoDB tables, S3 buckets, API Gateway) remains unchanged.
#
# What this script does:
#   1. Build Lambda packages with SAM
#   2. Update Lambda function code directly via AWS API
#   3. Update Lambda environment variables
#   4. Update SiteTemplatesLayer (Jinja2 templates for site-regenerator)
#   5. Sync admin and frontend static files to S3
#   6. Invoke site-regenerator to regenerate HTML pages
#
# What this script does NOT do:
#   - Does NOT create or modify CloudFormation stack
#   - Does NOT touch DynamoDB tables
#   - Does NOT modify S3 buckets
#   - Does NOT change API Gateway configuration

set -e  # Exit on error

# Get script directory and change to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env.prod
if [ ! -f ../.env.prod ]; then
    echo "Error: .env.prod not found in project root!"
    exit 1
fi

export $(cat ../.env.prod | grep -v '^#' | grep -v '^$' | xargs)

echo "=== Deploying Ticket Service to PRODUCTION (Lambda Updates Only) ==="
echo "Stack: NO CloudFormation stack (direct Lambda updates)"
echo "Region: eu-north-1"
echo ""
echo "⚠️  WARNING: This will update Lambda functions in PRODUCTION!"
echo ""
echo "Lambda functions to be updated:"
echo "  - yallabalagan-ticket-api"
echo "  - yallabalagan-site-regenerator (+ SiteTemplatesLayer with Jinja2 templates)"
echo "  - yallabalagan-email-sender"
echo "  - yallabalagan-event-status-updater"
echo ""
echo "Existing infrastructure (DynamoDB, S3 buckets, API Gateway) will NOT be touched."
echo ""
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

# Build
echo ""
echo "📦 Building SAM application..."
sam build

if [ ! -d "$SCRIPT_DIR/.aws-sam/build" ]; then
    echo "❌ Build failed - .aws-sam/build directory not found"
    exit 1
fi

echo "✅ Build complete"

# Helper function to update Lambda
update_lambda() {
    local function_name=$1
    local build_dir=$2
    local handler=$3

    echo ""
    echo "🚀 Updating Lambda: $function_name..."

    # Create zip package
    cd "$SCRIPT_DIR/$build_dir"
    zip -r -q "$SCRIPT_DIR/${function_name}.zip" .
    cd "$SCRIPT_DIR"

    if [ ! -f "$SCRIPT_DIR/${function_name}.zip" ]; then
        echo "❌ Package not found: ${function_name}.zip"
        return 1
    fi

    # Update function code
    aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://$SCRIPT_DIR/${function_name}.zip" \
        --region eu-north-1 \
        --profile prod \
        --no-cli-pager > /dev/null

    echo "   ✓ Code updated"

    # Wait for update to complete
    aws lambda wait function-updated \
        --function-name "$function_name" \
        --region eu-north-1 \
        --profile prod

    echo "   ✓ Update complete"

    # Cleanup
    rm -f "$SCRIPT_DIR/${function_name}.zip"
}

# Update TicketApiFunction
update_lambda "yallabalagan-ticket-api" ".aws-sam/build/TicketApiFunction" "lambdas/api-handler.lambda_handler"

# Update environment variables for ticket-api
echo "   ⚙️  Updating environment variables..."
cat > /tmp/ticket-api-env.json <<EOF
{
  "Variables": {
    "ALLPAY_LOGIN": "${ALLPAY_LOGIN}",
    "ALLPAY_WEBHOOK_SECRET": "${ALLPAY_WEBHOOK_SECRET}",
    "ALLPAY_API_KEY": "${ALLPAY_API_KEY}",
    "ALLPAY_USE_API": "${ALLPAY_USE_API}",
    "PAYMENT_EXPIRE_MINUTES": "${PAYMENT_EXPIRE_MINUTES}",
    "ADMIN_API_KEYS": "${ADMIN_API_KEYS}",
    "API_URL": "${API_URL}",
    "FRONTEND_URL": "${FRONTEND_URL}",
    "ENVIRONMENT": "prod",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "yallabalagan-ticket-media",
    "FRONTEND_BUCKET": "yallabalagan-tickets-frontend"
  }
}
EOF

aws lambda update-function-configuration \
    --function-name yallabalagan-ticket-api \
    --environment file:///tmp/ticket-api-env.json \
    --region eu-north-1 \
    --profile prod \
    --no-cli-pager > /dev/null

rm -f /tmp/ticket-api-env.json

echo "   ✓ Environment variables updated"

# Update SiteTemplatesLayer
echo ""
echo "📦 Updating SiteTemplatesLayer..."

# Create layer zip (templates/ and static/ at root level)
cd "$SCRIPT_DIR/frontend"
zip -r -q "$SCRIPT_DIR/site-templates-layer.zip" templates static
cd "$SCRIPT_DIR"

# Publish new layer version
LAYER_VERSION_ARN=$(aws lambda publish-layer-version \
    --layer-name yallabalagan-site-templates \
    --description "Jinja2 templates for site generation" \
    --zip-file "fileb://$SCRIPT_DIR/site-templates-layer.zip" \
    --compatible-runtimes python3.12 \
    --region eu-north-1 \
    --profile prod \
    --query 'LayerVersionArn' \
    --output text)

rm -f "$SCRIPT_DIR/site-templates-layer.zip"
echo "   ✓ Published new layer version: $LAYER_VERSION_ARN"

# Update SiteRegeneratorFunction
if [ -d "$SCRIPT_DIR/.aws-sam/build/SiteRegeneratorFunction" ]; then
    update_lambda "yallabalagan-site-regenerator" ".aws-sam/build/SiteRegeneratorFunction" "lambdas/site-regenerator.lambda_handler"

    # Update Lambda to use new Layer version
    echo "   ⚙️  Attaching new layer version..."
    aws lambda update-function-configuration \
        --function-name yallabalagan-site-regenerator \
        --layers "$LAYER_VERSION_ARN" \
        --region eu-north-1 \
        --profile prod \
        --no-cli-pager > /dev/null

    aws lambda wait function-updated \
        --function-name yallabalagan-site-regenerator \
        --region eu-north-1 \
        --profile prod

    echo "   ✓ Layer attached"

    echo "   ⚙️  Updating environment variables..."
    cat > /tmp/site-regen-env.json <<EOF
{
  "Variables": {
    "API_URL": "${API_URL}",
    "S3_BUCKET": "${S3_BUCKET}",
    "GA4_ID": "${GA4_ID}",
    "FB_PIXEL_ID": "${FB_PIXEL_ID}",
    "ENVIRONMENT": "prod",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "yallabalagan-ticket-media",
    "FRONTEND_BUCKET": "yallabalagan-tickets-frontend"
  }
}
EOF
    aws lambda update-function-configuration \
        --function-name yallabalagan-site-regenerator \
        --environment file:///tmp/site-regen-env.json \
        --region eu-north-1 \
        --profile prod \
        --no-cli-pager > /dev/null
    rm -f /tmp/site-regen-env.json

    echo "   ✓ Environment variables updated"
fi

# Update EmailSenderFunction
if [ -d "$SCRIPT_DIR/.aws-sam/build/EmailSenderFunction" ]; then
    update_lambda "yallabalagan-email-sender" ".aws-sam/build/EmailSenderFunction" "lambdas/email-sender.lambda_handler"

    echo "   ⚙️  Updating environment variables..."
    cat > /tmp/email-sender-env.json <<EOF
{
  "Variables": {
    "SENDER_EMAIL": "${SENDER_EMAIL}",
    "ENVIRONMENT": "prod",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "yallabalagan-ticket-media",
    "FRONTEND_BUCKET": "yallabalagan-tickets-frontend"
  }
}
EOF
    aws lambda update-function-configuration \
        --function-name yallabalagan-email-sender \
        --environment file:///tmp/email-sender-env.json \
        --region eu-north-1 \
        --profile prod \
        --no-cli-pager > /dev/null
    rm -f /tmp/email-sender-env.json

    echo "   ✓ Environment variables updated"
fi

# Update EventStatusUpdaterFunction
if [ -d "$SCRIPT_DIR/.aws-sam/build/EventStatusUpdaterFunction" ]; then
    update_lambda "yallabalagan-event-status-updater" ".aws-sam/build/EventStatusUpdaterFunction" "lambdas/event-status-updater.lambda_handler"

    echo "   ⚙️  Updating environment variables..."
    cat > /tmp/event-updater-env.json <<EOF
{
  "Variables": {
    "ENVIRONMENT": "prod",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "yallabalagan-ticket-media",
    "FRONTEND_BUCKET": "yallabalagan-tickets-frontend"
  }
}
EOF
    aws lambda wait function-updated \
        --function-name yallabalagan-event-status-updater \
        --region eu-north-1 \
        --profile prod

    aws lambda update-function-configuration \
        --function-name yallabalagan-event-status-updater \
        --handler "lambdas/event-status-updater.lambda_handler" \
        --runtime python3.12 \
        --environment file:///tmp/event-updater-env.json \
        --region eu-north-1 \
        --profile prod \
        --no-cli-pager > /dev/null
    rm -f /tmp/event-updater-env.json

    echo "   ✓ Handler, runtime, and environment variables updated"
fi

# Sync S3 files
echo ""
if [ -d "$SCRIPT_DIR/admin" ]; then
    echo "📤 Syncing admin files to S3..."
    aws s3 sync "$SCRIPT_DIR/admin/" s3://yallabalagan-ticket-admin/ \
      --profile prod \
      --exclude "*.md" \
      --exclude ".DS_Store" \
      --delete
    echo "   ✓ Admin files synced"
else
    echo "⚠️  Skipping admin sync - directory not found"
fi

echo ""
if [ -d "$SCRIPT_DIR/frontend/static" ]; then
    echo "📤 Syncing frontend static files to S3..."
    # Only sync static/ folder - HTML pages are generated by site-regenerator
    aws s3 sync "$SCRIPT_DIR/frontend/static/" s3://yallabalagan-tickets-frontend/static/ \
      --profile prod \
      --exclude "*.md" \
      --exclude ".DS_Store"
else
    echo "⚠️  Skipping frontend sync - static directory not found"
fi

# Regenerate site (HTML pages)
echo ""
echo "🔄 Regenerating site (invoking site-regenerator Lambda)..."
aws lambda invoke \
    --function-name yallabalagan-site-regenerator \
    --invocation-type RequestResponse \
    --region eu-north-1 \
    --profile prod \
    --cli-read-timeout 120 \
    /tmp/site-regenerator-output.json > /dev/null 2>&1

if [ -f /tmp/site-regenerator-output.json ]; then
    REGEN_STATUS=$(cat /tmp/site-regenerator-output.json | grep -o '"statusCode": [0-9]*' | grep -o '[0-9]*')
    if [ "$REGEN_STATUS" = "200" ]; then
        echo "   ✓ Site regenerated successfully"
    else
        echo "   ⚠️  Site regeneration returned status: $REGEN_STATUS"
        cat /tmp/site-regenerator-output.json
    fi
    rm -f /tmp/site-regenerator-output.json
else
    echo "   ⚠️  Could not verify site regeneration"
fi

# Invalidate CloudFront cache for admin panel
echo ""
echo "🔄 Invalidating CloudFront cache for admin panel..."
aws cloudfront create-invalidation \
    --distribution-id E1QVQ0JRE575WR \
    --paths "/*" \
    --profile prod \
    --no-cli-pager > /dev/null
echo "   ✓ CloudFront invalidation created"

echo ""
echo "✅ ✅ ✅ Deployment complete! ✅ ✅ ✅"
echo ""
echo "URLs:"
echo "  Admin:    http://yallabalagan-ticket-admin.s3-website.eu-north-1.amazonaws.com"
echo "  Frontend: http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com"
echo "  API:      https://ovajavet67.execute-api.eu-north-1.amazonaws.com"
echo ""
echo "Check Lambda logs:"
echo "  aws logs tail /aws/lambda/yallabalagan-ticket-api --follow --profile prod"
echo ""
