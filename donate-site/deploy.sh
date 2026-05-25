#!/bin/bash
# Deploy donate-site to dev or prod
# Usage: ./deploy.sh [dev|prod]

set -e

ENV=${1:?Usage: ./deploy.sh [dev|prod]}

if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "Error: environment must be 'dev' or 'prod'"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROFILE=$ENV
REGION=eu-north-1
BUCKET="yallabalagan-donate-site-${ENV}"

echo "=== Deploying Donate Site to $ENV ==="

# Copy shared accessibility files
echo "Copying shared accessibility files..."
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.css" "$SCRIPT_DIR/static/css/"
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.js" "$SCRIPT_DIR/static/js/"
mkdir -p "$SCRIPT_DIR/static/fonts/OpenDyslexic"
cp "$SCRIPT_DIR/../accessibility/fonts/"* "$SCRIPT_DIR/static/fonts/OpenDyslexic/"

# Build and deploy Lambda functions
echo "Building SAM application..."
if [[ "$ENV" == "dev" ]]; then
  sam build --config-env dev
  sam deploy --config-env dev --profile "$PROFILE"
else
  sam build
  sam deploy --profile "$PROFILE"
fi

# Sync static files to S3
echo "Syncing static files to S3..."
aws s3 sync "$SCRIPT_DIR/static/" "s3://$BUCKET/static/" \
  --profile "$PROFILE" --region "$REGION" \
  --exclude "*.md" --exclude ".DS_Store"

echo ""
echo "=== Deployment complete: $ENV ==="
echo "  Site: http://$BUCKET.s3-website.$REGION.amazonaws.com"
