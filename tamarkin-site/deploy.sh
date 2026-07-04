#!/bin/bash
# Deploy tamarkin-site to prod
# Usage: ./deploy.sh

set -e

PROFILE=prod
REGION=eu-north-1
STACK_NAME=tamarkin-site-prod
SITE_BUCKET=tamarkin-donations-site
SAM_BUCKET=yallabalagan-sam-artifacts-prod
EXPECTED_ACCOUNT=982534389905

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load secrets from .env.tamarkin (repo root)
ENV_FILE="$SCRIPT_DIR/../.env.tamarkin"
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found."
  echo "Create it with:"
  echo "  ALLPAY_LOGIN=..."
  echo "  ALLPAY_API_KEY=..."
  echo "  ALLPAY_WEBHOOK_SECRET=..."
  echo "  TAMARKIN_CF_DISTRIBUTION_ID=...  # optional, for CloudFront invalidation"
  exit 1
fi
export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)

# Verify AWS account
ACTUAL_ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text 2>&1)
if [ "$ACTUAL_ACCOUNT" != "$EXPECTED_ACCOUNT" ]; then
  echo "ERROR: profile '$PROFILE' points to account $ACTUAL_ACCOUNT, expected $EXPECTED_ACCOUNT"
  exit 1
fi

echo "=== Deploying Tamarkin Site ==="
echo "Account: $ACTUAL_ACCOUNT | Region: $REGION"
echo ""

# Copy shared accessibility files
echo "--- Copying accessibility files ---"
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.js" "$SCRIPT_DIR/frontend/js/"
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.css" "$SCRIPT_DIR/frontend/css/"

# Copy portrait from design handoff (only if not already present)
PORTRAIT_SRC="$SCRIPT_DIR/../design_handoff_delo_tamarkina/assets/tamarkin-portrait.jpg"
if [ -f "$PORTRAIT_SRC" ]; then
  cp "$PORTRAIT_SRC" "$SCRIPT_DIR/frontend/tamarkin-portrait.jpg"
fi

# Build
echo "--- Building SAM ---"
sam build --cached

# Deploy (idempotent — creates stack on first run, updates on subsequent)
echo "--- Deploying SAM stack ---"
sam deploy \
  --stack-name "$STACK_NAME" \
  --s3-bucket "$SAM_BUCKET" \
  --s3-prefix tamarkin-site \
  --region "$REGION" \
  --profile "$PROFILE" \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --parameter-overrides \
    AllPayLogin="$ALLPAY_LOGIN" \
    AllPayApiKey="$ALLPAY_API_KEY"

# Get API URL from stack outputs
echo ""
echo "--- Getting API URL ---"
STACK_API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" --profile "$PROFILE" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)
echo "  API URL: $STACK_API_URL"

# Inject real API URL into donation-initiator Lambda env (bypasses CF circular dependency)
echo "  Updating Lambda env..."
aws lambda update-function-configuration \
  --function-name tamarkin-donation-initiator \
  --environment "Variables={DONATIONS_TABLE=tamarkin-donations,DONATION_GOAL=20000,ALLPAY_LOGIN=$ALLPAY_LOGIN,ALLPAY_API_KEY=$ALLPAY_API_KEY,API_URL=$STACK_API_URL}" \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws lambda wait function-updated \
  --function-name tamarkin-donation-initiator \
  --region "$REGION" --profile "$PROFILE"
sed "s|__API_URL__|$STACK_API_URL|g" "$SCRIPT_DIR/frontend/index.html" > /tmp/tamarkin-index.html
sed "s|__API_URL__|$STACK_API_URL|g" "$SCRIPT_DIR/frontend/success.html" > /tmp/tamarkin-success.html

# Sync frontend to S3 (HTML files with injected URL uploaded separately)
echo ""
echo "--- Syncing frontend to S3 ---"
aws s3 sync "$SCRIPT_DIR/frontend/" "s3://$SITE_BUCKET/" \
  --profile "$PROFILE" --region "$REGION" \
  --exclude "*.md" --exclude ".DS_Store" --exclude "index.html" --exclude "success.html" \
  --delete
aws s3 cp /tmp/tamarkin-index.html "s3://$SITE_BUCKET/index.html" \
  --profile "$PROFILE" --region "$REGION" \
  --content-type "text/html; charset=utf-8"
aws s3 cp /tmp/tamarkin-success.html "s3://$SITE_BUCKET/success.html" \
  --profile "$PROFILE" --region "$REGION" \
  --content-type "text/html; charset=utf-8"
rm -f /tmp/tamarkin-index.html /tmp/tamarkin-success.html

# CloudFront invalidation (optional — only if distribution ID is set)
if [ -n "$TAMARKIN_CF_DISTRIBUTION_ID" ]; then
  echo ""
  echo "--- Invalidating CloudFront ---"
  aws cloudfront create-invalidation \
    --distribution-id "$TAMARKIN_CF_DISTRIBUTION_ID" \
    --paths "/*" \
    --profile "$PROFILE" --no-cli-pager > /dev/null
  echo "  Invalidation created"
fi

# Print API URL from stack outputs
echo ""
echo "=== Deploy complete ==="
API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" --profile "$PROFILE" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)
echo "  API URL: $API_URL"
echo "  Site:    http://$SITE_BUCKET.s3-website.$REGION.amazonaws.com"
echo ""
echo "Logs: aws logs tail /aws/lambda/tamarkin-donation-initiator --follow --profile $PROFILE"
