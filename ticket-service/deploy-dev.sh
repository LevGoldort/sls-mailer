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
echo "✅ Deployment complete!"
echo ""
echo "Get stack outputs:"
echo "aws cloudformation describe-stacks --stack-name yallabalagan-ticket-service-dev --query 'Stacks[0].Outputs' --region eu-north-1"
