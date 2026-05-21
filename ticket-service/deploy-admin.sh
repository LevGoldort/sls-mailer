#!/bin/bash
# Fast deploy: upload admin panel to S3 only (no Lambda rebuild)
# Usage: ./deploy-admin.sh [dev|prod]

set -e

ENV=${1:?Usage: ./deploy-admin.sh [dev|prod]}

if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "Error: environment must be 'dev' or 'prod'"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROFILE=$ENV
REGION=eu-north-1

if [[ "$ENV" == "prod" ]]; then
  ADMIN_BUCKET="yallabalagan-ticket-admin"
else
  ADMIN_BUCKET="yallabalagan-ticket-admin-dev"
fi

echo "=== Uploading admin panel → s3://$ADMIN_BUCKET/ ==="

aws s3 sync "$SCRIPT_DIR/admin/" "s3://$ADMIN_BUCKET/" \
  --delete \
  --profile "$PROFILE" \
  --region "$REGION" \
  --no-cli-pager

echo "Done: http://$ADMIN_BUCKET.s3-website.$REGION.amazonaws.com"
