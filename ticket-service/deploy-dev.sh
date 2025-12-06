#!/bin/bash
# Deploy ticket-service to Development environment

set -e  # Exit on error

# Load .env.dev
if [ ! -f ../.env.dev ]; then
    echo "Error: .env.dev not found in project root!"
    exit 1
fi

export $(cat ../.env.dev | grep -v '^#' | grep -v '^$' | xargs)

echo "=== Deploying Ticket Service to DEV ==="
echo "Stack: yallabalagan-ticket-service-dev"
echo "Region: eu-north-1"
echo ""

# Build
echo "Building SAM application..."
sam build

# Deploy
echo "Deploying to AWS..."
sam deploy \
  --config-env dev \
  --parameter-overrides \
    "Environment=dev" \
    "AllPayWebhookSecret=${ALLPAY_WEBHOOK_SECRET}" \
    "SenderEmail=${SENDER_EMAIL}"

echo ""
echo "Syncing admin files to S3..."
aws s3 sync admin/ s3://yallabalagan-ticket-admin-dev/ \
  --exclude "*.md" \
  --exclude ".DS_Store" \
  --delete

echo ""
echo "Syncing frontend files to S3..."
aws s3 sync frontend/ s3://yallabalagan-tickets-frontend-dev/ \
  --exclude "*.md" \
  --exclude ".DS_Store" \
  --delete

echo ""
echo "✅ Deployment complete!"
echo ""
echo "URLs:"
echo "  Admin:    http://yallabalagan-ticket-admin-dev.s3-website.eu-north-1.amazonaws.com"
echo "  Frontend: http://yallabalagan-tickets-frontend-dev.s3-website.eu-north-1.amazonaws.com"
echo "  API:      https://wcyt1odrnc.execute-api.eu-north-1.amazonaws.com/dev"
echo ""
echo "Get stack outputs:"
echo "aws cloudformation describe-stacks --stack-name yallabalagan-ticket-service-dev --query 'Stacks[0].Outputs' --region eu-north-1"
