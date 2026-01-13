#!/bin/bash
# Deploy ticket-service to Production environment

set -e  # Exit on error

# Load .env.prod
if [ ! -f ../.env.prod ]; then
    echo "Error: .env.prod not found in project root!"
    exit 1
fi

export $(cat ../.env.prod | grep -v '^#' | grep -v '^$' | xargs)

echo "=== Deploying Ticket Service to PRODUCTION ==="
echo "Stack: yallabalagan-ticket-service-prod"
echo "Region: eu-north-1"
echo ""
echo "⚠️  WARNING: This will deploy to PRODUCTION!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

# Build
echo "Building SAM application..."
sam build

# Deploy
echo "Deploying to AWS..."
sam deploy \
  --config-env default \
  --parameter-overrides \
    "Environment=prod" \
    "PaymentMode=${PAYMENT_MODE}" \
    "SenderEmail=${SENDER_EMAIL}" \
    "AllPayLogin=${ALLPAY_LOGIN}" \
    "AllPayWebhookSecret=${ALLPAY_WEBHOOK_SECRET}" \
    "AllPayApiKey=${ALLPAY_API_KEY}" \
    "AllPayUseApi=${ALLPAY_USE_API}" \
    "PaymentExpireMinutes=${PAYMENT_EXPIRE_MINUTES}" \
    "AdminApiKeys=${ADMIN_API_KEYS}"

echo ""
echo "Syncing admin files to S3..."
aws s3 sync admin/ s3://yallabalagan-ticket-admin/ \
  --exclude "*.md" \
  --exclude ".DS_Store" \
  --delete

echo ""
echo "Syncing frontend files to S3..."
aws s3 sync frontend/ s3://yallabalagan-tickets-frontend/ \
  --exclude "*.md" \
  --exclude ".DS_Store" \
  --delete

echo ""
echo "✅ Deployment complete!"
echo ""
echo "URLs:"
echo "  Admin:    http://yallabalagan-ticket-admin.s3-website.eu-north-1.amazonaws.com"
echo "  Frontend: http://yallabalagan-tickets-frontend.s3-website.eu-north-1.amazonaws.com"
echo ""
echo "Get stack outputs:"
echo "aws cloudformation describe-stacks --stack-name yallabalagan-ticket-service-prod --query 'Stacks[0].Outputs' --region eu-north-1"
