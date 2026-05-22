#!/bin/bash
# Deploy ticket-service to dev or prod
# Usage: ./deploy.sh [dev|prod] [admin]
#   admin — fast mode: only sync admin panel to S3, skip Lambda rebuilds

set -e

ENV=${1:?Usage: ./deploy.sh [dev|prod] [admin]}
MODE=${2:-full}  # 'admin' for S3-only, anything else = full deploy

if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "Error: environment must be 'dev' or 'prod'"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load env file
ENV_FILE="$SCRIPT_DIR/../.env.$ENV"
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found"
  exit 1
fi
export $(cat "$ENV_FILE" | grep -v '^#' | grep -v '^$' | xargs)

PROFILE=$ENV
REGION=eu-north-1

# S3 bucket names include -dev suffix because S3 names are globally unique
if [[ "$ENV" == "prod" ]]; then
  MEDIA_BUCKET="yallabalagan-ticket-media"
  FRONTEND_BUCKET="yallabalagan-tickets-frontend"
  ADMIN_BUCKET="yallabalagan-ticket-admin"
else
  MEDIA_BUCKET="yallabalagan-ticket-media-dev"
  FRONTEND_BUCKET="yallabalagan-tickets-frontend-dev"
  ADMIN_BUCKET="yallabalagan-ticket-admin-dev"
fi

# Guard: verify AWS account matches expected
EXPECTED_ACCOUNT=$([[ "$ENV" == "prod" ]] && echo "982534389905" || echo "521760247620")
ACTUAL_ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text 2>&1)
if [ "$ACTUAL_ACCOUNT" != "$EXPECTED_ACCOUNT" ]; then
  echo "ERROR: profile '$PROFILE' points to account $ACTUAL_ACCOUNT, expected $EXPECTED_ACCOUNT"
  echo "Check your AWS credentials."
  exit 1
fi

echo "=== Deploying Ticket Service to $ENV ==="
echo "Account: $ACTUAL_ACCOUNT"
echo "Region:  $REGION"
echo ""

# Fast admin-only mode: just sync admin panel to S3 and exit
if [[ "$MODE" == "admin" ]]; then
  echo "--- Admin-only mode: syncing admin panel to S3 ---"
  aws s3 sync "$SCRIPT_DIR/admin/" "s3://$ADMIN_BUCKET/" \
    --profile "$PROFILE" --region "$REGION" \
    --exclude "*.md" --exclude ".DS_Store" \
    --delete --no-cli-pager
  echo "Done: http://$ADMIN_BUCKET.s3-website.$REGION.amazonaws.com"
  exit 0
fi

if [[ "$ENV" == "prod" ]]; then
  echo "WARNING: This will update Lambda functions in PRODUCTION!"
  echo "Press Ctrl+C to cancel, or Enter to continue..."
  read
fi

# Build
echo "Building SAM application..."
sam build
echo "Build complete"

# Helper: update a single Lambda function
update_lambda() {
  local function_name=$1
  local build_dir=$2
  local handler=$3

  echo ""
  echo "Updating Lambda: $function_name..."

  if [ ! -d "$SCRIPT_DIR/$build_dir" ]; then
    echo "  Skipping — build dir not found: $build_dir"
    return 0
  fi

  cd "$SCRIPT_DIR/$build_dir"
  zip -r -q "$SCRIPT_DIR/${function_name}.zip" .
  cd "$SCRIPT_DIR"

  local zip_size
  zip_size=$(wc -c < "$SCRIPT_DIR/${function_name}.zip")

  if [ "$zip_size" -gt 50000000 ]; then
    echo "  Package is large ($(( zip_size / 1024 / 1024 ))MB), uploading via S3..."
    aws s3 cp "$SCRIPT_DIR/${function_name}.zip" \
      "s3://$MEDIA_BUCKET/lambda-deploys/${function_name}.zip" \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
    aws lambda update-function-code \
      --function-name "$function_name" \
      --s3-bucket "$MEDIA_BUCKET" \
      --s3-key "lambda-deploys/${function_name}.zip" \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
    aws s3 rm "s3://$MEDIA_BUCKET/lambda-deploys/${function_name}.zip" \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
  else
    aws lambda update-function-code \
      --function-name "$function_name" \
      --zip-file "fileb://$SCRIPT_DIR/${function_name}.zip" \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
  fi

  aws lambda wait function-updated \
    --function-name "$function_name" \
    --region "$REGION" --profile "$PROFILE"

  aws lambda update-function-configuration \
    --function-name "$function_name" \
    --handler "$handler" \
    --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null

  aws lambda wait function-updated \
    --function-name "$function_name" \
    --region "$REGION" --profile "$PROFILE"

  rm -f "$SCRIPT_DIR/${function_name}.zip"
  echo "  Done"
}

# Update Lambda functions
update_lambda "yallabalagan-ticket-api" \
  ".aws-sam/build/TicketApiFunction" \
  "lambdas/api-handler.lambda_handler"

# Update ticket-api env vars
echo "  Updating environment variables..."
cat > /tmp/ticket-api-env.json <<EOF
{
  "Variables": {
    "ALLPAY_LOGIN": "${ALLPAY_LOGIN}",
    "ALLPAY_WEBHOOK_SECRET": "${ALLPAY_WEBHOOK_SECRET}",
    "ALLPAY_API_KEY": "${ALLPAY_API_KEY}",
    "ALLPAY_USE_API": "${ALLPAY_USE_API}",
    "PAYMENT_EXPIRE_MINUTES": "${PAYMENT_EXPIRE_MINUTES}",
    "JWT_SECRET": "${JWT_SECRET}",
    "ADMIN_API_KEYS": "${ADMIN_API_KEYS}",
    "API_URL": "${API_URL}",
    "FRONTEND_URL": "${FRONTEND_URL}",
    "ENVIRONMENT": "${ENV}",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "SMS_SENDER_LAMBDA": "yallabalagan-sms-sender",
    "QUICK_POST_SECRET": "${QUICK_POST_SECRET}",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "PERFORMERS_TABLE": "yallabalagan-performers",
    "PRODUCTS_TABLE": "yallabalagan-products",
    "MERCHANDISE_ORDERS_TABLE": "yallabalagan-merchandise-orders",
    "SHOWS_TABLE": "yallabalagan-shows",
    "EPISODES_TABLE": "yallabalagan-episodes",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}"
  }
}
EOF
aws lambda update-function-configuration \
  --function-name yallabalagan-ticket-api \
  --environment file:///tmp/ticket-api-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/ticket-api-env.json
echo "  Environment variables updated"

# Update User API (auth + user management)
echo ""
update_lambda "yallabalagan-user-api" \
  ".aws-sam/build/UserApiFunction" \
  "lambdas/user-api-handler.lambda_handler"

echo "  Updating environment variables..."
cat > /tmp/user-api-env.json <<EOF
{
  "Variables": {
    "ADMIN_API_KEYS": "${ADMIN_API_KEYS}",
    "JWT_SECRET": "${JWT_SECRET}",
    "USERS_TABLE": "yallabalagan-users",
    "REFRESH_TOKENS_TABLE": "yallabalagan-refresh-tokens",
    "TENANT_ID": "yallabalagan",
    "ENVIRONMENT": "${ENV}"
  }
}
EOF
aws lambda update-function-configuration \
  --function-name yallabalagan-user-api \
  --environment file:///tmp/user-api-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws lambda wait function-updated \
  --function-name yallabalagan-user-api \
  --region "$REGION" --profile "$PROFILE"
rm -f /tmp/user-api-env.json
echo "  Environment variables updated"

# Wire user-api routes into the existing HTTP API (idempotent)
echo "  Wiring API Gateway routes for user-api..."
# Extract API ID from API_URL (e.g. https://d4xhvmdzbg.execute-api.eu-north-1... → d4xhvmdzbg)
API_ID=$(echo "$API_URL" | sed 's|https://\([^.]*\)\..*|\1|')

if [ -z "$API_ID" ] || [ "$API_ID" = "None" ]; then
  echo "  WARNING: Could not determine API ID from API_URL — skipping route wiring"
else
  USER_API_ARN="arn:aws:lambda:${REGION}:${ACTUAL_ACCOUNT}:function:yallabalagan-user-api"
  INTEGRATION_URI="arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${USER_API_ARN}/invocations"

  # Create integration (or reuse existing)
  INTEGRATION_ID=$(aws apigatewayv2 get-integrations \
    --api-id "$API_ID" \
    --query "Items[?IntegrationUri=='${INTEGRATION_URI}'].IntegrationId | [0]" \
    --output text --profile "$PROFILE" --region "$REGION" --no-cli-pager 2>/dev/null)

  if [ -z "$INTEGRATION_ID" ] || [ "$INTEGRATION_ID" = "None" ]; then
    INTEGRATION_ID=$(aws apigatewayv2 create-integration \
      --api-id "$API_ID" \
      --integration-type AWS_PROXY \
      --integration-uri "$INTEGRATION_URI" \
      --payload-format-version "2.0" \
      --query 'IntegrationId' --output text \
      --profile "$PROFILE" --region "$REGION" --no-cli-pager)
    echo "  Created integration: $INTEGRATION_ID"
  else
    echo "  Reusing integration: $INTEGRATION_ID"
  fi

  # Create routes (idempotent)
  for ROUTE_KEY in "ANY /api/auth/{proxy+}" "ANY /api/users" "ANY /api/users/{proxy+}"; do
    EXISTING_ROUTE=$(aws apigatewayv2 get-routes \
      --api-id "$API_ID" \
      --query "Items[?RouteKey=='${ROUTE_KEY}'].RouteId | [0]" \
      --output text --profile "$PROFILE" --region "$REGION" --no-cli-pager 2>/dev/null)
    if [ -z "$EXISTING_ROUTE" ] || [ "$EXISTING_ROUTE" = "None" ]; then
      aws apigatewayv2 create-route \
        --api-id "$API_ID" \
        --route-key "$ROUTE_KEY" \
        --target "integrations/${INTEGRATION_ID}" \
        --profile "$PROFILE" --region "$REGION" --no-cli-pager > /dev/null
      echo "  Created route: $ROUTE_KEY"
    else
      echo "  Route exists: $ROUTE_KEY"
    fi
  done

  # Allow API Gateway to invoke user-api (idempotent via 2>/dev/null)
  aws lambda add-permission \
    --function-name yallabalagan-user-api \
    --statement-id allow-apigateway-user-api \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACTUAL_ACCOUNT}:${API_ID}/*/*" \
    --profile "$PROFILE" --region "$REGION" --no-cli-pager > /dev/null 2>&1 || true
  echo "  Routes wired"
fi

# Update SiteTemplatesLayer
echo ""
echo "Updating SiteTemplatesLayer..."
cd "$SCRIPT_DIR/frontend"
zip -r -q "$SCRIPT_DIR/site-templates-layer.zip" templates static
cd "$SCRIPT_DIR"

LAYER_VERSION_ARN=$(aws lambda publish-layer-version \
  --layer-name yallabalagan-site-templates \
  --description "Jinja2 templates for site generation" \
  --zip-file "fileb://$SCRIPT_DIR/site-templates-layer.zip" \
  --compatible-runtimes python3.12 \
  --region "$REGION" --profile "$PROFILE" \
  --query 'LayerVersionArn' --output text)
rm -f "$SCRIPT_DIR/site-templates-layer.zip"
echo "  Published: $LAYER_VERSION_ARN"

update_lambda "yallabalagan-site-regenerator" \
  ".aws-sam/build/SiteRegeneratorFunction" \
  "lambdas/site-regenerator.lambda_handler"

echo "  Attaching new layer version..."
aws lambda update-function-configuration \
  --function-name yallabalagan-site-regenerator \
  --layers "$LAYER_VERSION_ARN" \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws lambda wait function-updated \
  --function-name yallabalagan-site-regenerator \
  --region "$REGION" --profile "$PROFILE"

echo "  Updating environment variables..."
cat > /tmp/site-regen-env.json <<EOF
{
  "Variables": {
    "API_URL": "${API_URL}",
    "S3_BUCKET": "${S3_BUCKET}",
    "GA4_ID": "${GA4_ID}",
    "FB_PIXEL_ID": "${FB_PIXEL_ID}",
    "ENVIRONMENT": "${ENV}",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "SHOWS_TABLE": "yallabalagan-shows",
    "EPISODES_TABLE": "yallabalagan-episodes",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}"
  }
}
EOF
aws lambda update-function-configuration \
  --function-name yallabalagan-site-regenerator \
  --environment file:///tmp/site-regen-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/site-regen-env.json

update_lambda "yallabalagan-email-sender" \
  ".aws-sam/build/EmailSenderFunction" \
  "lambdas/email-sender.lambda_handler"

echo "  Updating environment variables..."
cat > /tmp/email-sender-env.json <<EOF
{
  "Variables": {
    "SENDER_EMAIL": "${SENDER_EMAIL}",
    "FRONTEND_URL": "${FRONTEND_URL}",
    "ENVIRONMENT": "${ENV}",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}"
  }
}
EOF
aws lambda update-function-configuration \
  --function-name yallabalagan-email-sender \
  --environment file:///tmp/email-sender-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/email-sender-env.json

if aws lambda get-function --function-name yallabalagan-sms-sender \
    --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null 2>&1; then
  update_lambda "yallabalagan-sms-sender" \
    ".aws-sam/build/SmsSenderFunction" \
    "lambdas/sms-sender.lambda_handler"

  echo "  Updating environment variables..."
  cat > /tmp/sms-sender-env.json <<EOF
{
  "Variables": {
    "ACTIVETRAIL_API_KEY": "${ACTIVETRAIL_API_KEY}",
    "ACTIVETRAIL_SENDER_ID": "${ACTIVETRAIL_SENDER_ID}",
    "FRONTEND_URL": "${FRONTEND_URL}",
    "ENVIRONMENT": "${ENV}",
    "EVENTS_TABLE": "yallabalagan-events",
    "ORDERS_TABLE": "yallabalagan-orders"
  }
}
EOF
  aws lambda update-function-configuration \
    --function-name yallabalagan-sms-sender \
    --environment file:///tmp/sms-sender-env.json \
    --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
  rm -f /tmp/sms-sender-env.json
else
  echo ""
  echo "  Skipping yallabalagan-sms-sender — function not found in this account"
fi

update_lambda "yallabalagan-pending-orders-cleaner" \
  ".aws-sam/build/PendingOrdersCleanerFunction" \
  "lambdas/pending-orders-cleaner.lambda_handler"

echo "  Updating environment variables..."
cat > /tmp/pending-cleaner-env.json <<EOF
{
  "Variables": {
    "ENVIRONMENT": "${ENV}",
    "EVENTS_TABLE": "yallabalagan-events",
    "ORDERS_TABLE": "yallabalagan-orders",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}"
  }
}
EOF
aws lambda update-function-configuration \
  --function-name yallabalagan-pending-orders-cleaner \
  --environment file:///tmp/pending-cleaner-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws lambda wait function-updated \
  --function-name yallabalagan-pending-orders-cleaner \
  --region "$REGION" --profile "$PROFILE"
rm -f /tmp/pending-cleaner-env.json

update_lambda "yallabalagan-event-status-updater" \
  ".aws-sam/build/EventStatusUpdaterFunction" \
  "lambdas/event-status-updater.lambda_handler"

echo "  Updating environment variables..."
cat > /tmp/event-updater-env.json <<EOF
{
  "Variables": {
    "ENVIRONMENT": "${ENV}",
    "PAYMENT_MODE": "${PAYMENT_MODE}",
    "EMAIL_SENDER_LAMBDA": "yallabalagan-email-sender",
    "EVENTS_TABLE": "yallabalagan-events",
    "LOCATIONS_TABLE": "yallabalagan-locations",
    "ORDERS_TABLE": "yallabalagan-orders",
    "COUPONS_TABLE": "yallabalagan-coupons",
    "SEAT_RESERVATIONS_TABLE": "yallabalagan-seat-reservations",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}"
  }
}
EOF
aws lambda wait function-updated \
  --function-name yallabalagan-event-status-updater \
  --region "$REGION" --profile "$PROFILE"
aws lambda update-function-configuration \
  --function-name yallabalagan-event-status-updater \
  --environment file:///tmp/event-updater-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/event-updater-env.json

# Ensure Shows and Episodes DynamoDB tables exist + Lambda policies are attached
echo ""
echo "Ensuring Shows/Episodes tables and policies..."

# Helper: create DynamoDB table if it doesn't exist
ensure_table() {
  local table_name=$1
  local exists
  exists=$(aws dynamodb describe-table --table-name "$table_name" --region "$REGION" --profile "$PROFILE" --query 'Table.TableName' --output text 2>/dev/null || echo "")
  if [ -z "$exists" ]; then
    echo "  Creating table: $table_name"
    aws dynamodb create-table \
      --table-name "$table_name" \
      --billing-mode PAY_PER_REQUEST \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager "${@:2}" > /dev/null
    aws dynamodb wait table-exists --table-name "$table_name" --region "$REGION" --profile "$PROFILE"
    echo "  Table created"
  else
    echo "  Table exists: $table_name"
  fi
}

ensure_table "yallabalagan-shows" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S AttributeName=slug,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes '[{"IndexName":"SlugIndex","KeySchema":[{"AttributeName":"slug","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}]'

ensure_table "yallabalagan-episodes" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S AttributeName=slug,AttributeType=S AttributeName=show_id,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes '[{"IndexName":"SlugIndex","KeySchema":[{"AttributeName":"slug","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}},{"IndexName":"ShowIndex","KeySchema":[{"AttributeName":"show_id","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}]'

# Helper: attach inline policy granting DynamoDB CRUD on a table to a Lambda role
ensure_dynamodb_policy() {
  local role_name=$1
  local table_name=$2
  local policy_name="DynamoDB-${table_name}"
  local account_id
  account_id=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)
  local table_arn="arn:aws:dynamodb:${REGION}:${account_id}:table/${table_name}"
  aws iam put-role-policy \
    --role-name "$role_name" \
    --policy-name "$policy_name" \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\",\"dynamodb:UpdateItem\",\"dynamodb:DeleteItem\",\"dynamodb:Scan\",\"dynamodb:Query\",\"dynamodb:BatchGetItem\",\"dynamodb:BatchWriteItem\"],\"Resource\":[\"${table_arn}\",\"${table_arn}/index/*\"]}]}" \
    --profile "$PROFILE" 2>/dev/null && echo "  Policy attached: $role_name → $table_name" || true
}

TICKET_API_ROLE=$(aws lambda get-function-configuration --function-name yallabalagan-ticket-api --region "$REGION" --profile "$PROFILE" --query 'Role' --output text | sed 's|.*/||')
REGEN_ROLE=$(aws lambda get-function-configuration --function-name yallabalagan-site-regenerator --region "$REGION" --profile "$PROFILE" --query 'Role' --output text | sed 's|.*/||')

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-shows"
ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-episodes"
ensure_dynamodb_policy "$REGEN_ROLE" "yallabalagan-shows"
ensure_dynamodb_policy "$REGEN_ROLE" "yallabalagan-episodes"

# Sync S3
echo ""
echo "Syncing admin files to S3..."
aws s3 sync "$SCRIPT_DIR/admin/" "s3://$ADMIN_BUCKET/" \
  --profile "$PROFILE" \
  --exclude "*.md" --exclude ".DS_Store" \
  --delete

echo "Syncing frontend static files to S3..."
aws s3 sync "$SCRIPT_DIR/frontend/static/" "s3://$FRONTEND_BUCKET/static/" \
  --profile "$PROFILE" \
  --exclude "*.md" --exclude ".DS_Store"

# Regenerate site
echo ""
echo "Regenerating site..."
aws lambda invoke \
  --function-name yallabalagan-site-regenerator \
  --invocation-type RequestResponse \
  --region "$REGION" --profile "$PROFILE" \
  --cli-read-timeout 120 \
  /tmp/site-regenerator-output.json > /dev/null 2>&1

if [ -f /tmp/site-regenerator-output.json ]; then
  REGEN_STATUS=$(cat /tmp/site-regenerator-output.json | grep -o '"statusCode": [0-9]*' | grep -o '[0-9]*')
  if [ "$REGEN_STATUS" = "200" ]; then
    echo "  Site regenerated"
  else
    echo "  Site regeneration returned status: $REGEN_STATUS"
    cat /tmp/site-regenerator-output.json
  fi
  rm -f /tmp/site-regenerator-output.json
fi

# CloudFront invalidation (prod only)
if [[ "$ENV" == "prod" ]]; then
  echo ""
  echo "Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --distribution-id E1QVQ0JRE575WR \
    --paths "/*" \
    --profile "$PROFILE" --no-cli-pager > /dev/null
  echo "  Invalidation created"
fi

echo ""
echo "=== Deployment complete: $ENV ==="
echo ""
if [[ "$ENV" == "prod" ]]; then
  echo "  Admin:    https://admin.yallabalagan.org"
  echo "  Frontend: https://events.yallabalagan.org"
  echo "  API:      https://ovajavet67.execute-api.eu-north-1.amazonaws.com"
else
  echo "  Admin:    http://$ADMIN_BUCKET.s3-website.eu-north-1.amazonaws.com"
  echo "  Frontend: http://$FRONTEND_BUCKET.s3-website.eu-north-1.amazonaws.com"
  echo "  API:      ${API_URL}"
fi
echo ""
echo "Logs: aws logs tail /aws/lambda/yallabalagan-ticket-api --follow --profile $PROFILE"
