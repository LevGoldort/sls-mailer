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
  aws s3 sync "$SCRIPT_DIR/admin-v2/" "s3://$ADMIN_BUCKET/" \
    --profile "$PROFILE" --region "$REGION" \
    --exclude "*.md" --exclude ".DS_Store" \
    --delete --no-cli-pager
  if [[ "$ENV" == "prod" ]]; then
    aws cloudfront create-invalidation --distribution-id E1QVQ0JRE575WR --paths "/*" \
      --profile "$PROFILE" --no-cli-pager > /dev/null
    echo "CloudFront invalidated"
  fi
  echo "Done: https://admin.yallabalagan.org"
  exit 0
fi

# if [[ "$ENV" == "prod" ]]; then
#   echo "WARNING: This will update Lambda functions in PRODUCTION!"
#   echo "Press Ctrl+C to cancel, or Enter to continue..."
#   read
# fi

# Build
echo "Building SAM application..."
sam build
echo "Build complete"

# Helper: create Lambda function if it doesn't exist yet
ensure_lambda() {
  local function_name=$1
  local handler=$2
  local timeout=${3:-30}
  local memory=${4:-512}

  local exists
  exists=$(aws lambda get-function --function-name "$function_name" \
    --region "$REGION" --profile "$PROFILE" --query 'Configuration.FunctionName' \
    --output text 2>/dev/null || echo "")

  if [ -z "$exists" ]; then
    echo "  Creating Lambda: $function_name..."
    # Use a minimal placeholder zip so the function can be created before code upload
    echo 'def lambda_handler(e,c): pass' > /tmp/_placeholder.py
    zip -j -q /tmp/_placeholder.zip /tmp/_placeholder.py
    LAMBDA_ROLE=$(aws lambda get-function-configuration \
      --function-name yallabalagan-ticket-api \
      --region "$REGION" --profile "$PROFILE" \
      --query 'Role' --output text)
    aws lambda create-function \
      --function-name "$function_name" \
      --runtime python3.12 \
      --role "$LAMBDA_ROLE" \
      --handler "$handler" \
      --timeout "$timeout" \
      --memory-size "$memory" \
      --zip-file fileb:///tmp/_placeholder.zip \
      --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
    aws lambda wait function-active \
      --function-name "$function_name" \
      --region "$REGION" --profile "$PROFILE"
    rm -f /tmp/_placeholder.py /tmp/_placeholder.zip
    echo "  Created"
  fi
}

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
    "INFLUENCERS_TABLE": "yallabalagan-influencers",
    "INSTAGRAM_CONNECTIONS_TABLE": "yallabalagan-instagram",
    "TIKTOK_CONNECTIONS_TABLE": "yallabalagan-tiktok",
    "TIKTOK_CLIENT_KEY": "${TIKTOK_CLIENT_KEY}",
    "TIKTOK_CLIENT_SECRET": "${TIKTOK_CLIENT_SECRET}",
    "TIKTOK_TOKEN_KEY": "${TIKTOK_TOKEN_KEY}",
    "YOUTUBE_CONNECTIONS_TABLE": "yallabalagan-youtube",
    "YOUTUBE_CLIENT_ID": "${YOUTUBE_CLIENT_ID}",
    "YOUTUBE_CLIENT_SECRET": "${YOUTUBE_CLIENT_SECRET}",
    "YOUTUBE_TOKEN_KEY": "${YOUTUBE_TOKEN_KEY}",
    "SOCIAL_POSTS_TABLE": "yallabalagan-social-posts",
    "SOCIAL_POSTER_LAMBDA": "yallabalagan-social-poster",
    "META_APP_ID": "${META_APP_ID}",
    "META_APP_SECRET": "${META_APP_SECRET}",
    "INSTAGRAM_TOKEN_KEY": "${INSTAGRAM_TOKEN_KEY}",
    "API_BASE_URL": "${API_URL}",
    "ADMIN_BASE_URL": "${ADMIN_BASE_URL}",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "FRONTEND_BUCKET": "${FRONTEND_BUCKET}",
    "FB_AD_ACCOUNT_ID": "${FbAdAccountId}",
    "FB_PAGE_ID": "${FbPageId}",
    "FB_SYSTEM_USER_TOKEN": "${FbSystemUserToken}",
    "FB_PIXEL_ID": "${FB_PIXEL_ID}",
    "TENANTS_TABLE": "yallabalagan-tenants"
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
    "TENANTS_TABLE": "yallabalagan-tenants",
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
  for ROUTE_KEY in "ANY /api/auth/{proxy+}" "ANY /api/users" "ANY /api/users/{proxy+}" "ANY /api/tenants" "ANY /api/tenants/{proxy+}"; do
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
    "CLOUDFRONT_DISTRIBUTION_ID": "E1QVQ0JRE575WR",
    "GA4_ID": "${GA4_ID}",
    "FB_PIXEL_ID": "${FB_PIXEL_ID}",
    "YOUTUBE_API_KEY": "${YOUTUBE_API_KEY}",
    "YOUTUBE_PLAYLIST_ID": "${YOUTUBE_PLAYLIST_ID}",
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
    "INFLUENCERS_TABLE": "yallabalagan-influencers",
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
ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-config"

ensure_table "yallabalagan-tenants" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S AttributeName=slug,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes '[{"IndexName":"SlugIndex","KeySchema":[{"AttributeName":"slug","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}]'

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-tenants"

USER_API_ROLE=$(aws lambda get-function-configuration --function-name yallabalagan-user-api \
  --region "$REGION" --profile "$PROFILE" --query 'Role' --output text 2>/dev/null | sed 's|.*/||' || echo "")
if [ -n "$USER_API_ROLE" ]; then
  ensure_dynamodb_policy "$USER_API_ROLE" "yallabalagan-tenants"
fi
ensure_dynamodb_policy "$REGEN_ROLE" "yallabalagan-shows"
ensure_dynamodb_policy "$REGEN_ROLE" "yallabalagan-episodes"

ensure_table "yallabalagan-influencers" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-influencers"

ensure_table "yallabalagan-instagram" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-instagram"

ensure_table "yallabalagan-tiktok" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-tiktok"

ensure_table "yallabalagan-youtube" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-youtube"

ensure_table "yallabalagan-social-posts" \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S AttributeName=status,AttributeType=S AttributeName=scheduled_at,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes '[{"IndexName":"StatusScheduledIndex","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"scheduled_at","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'

ensure_dynamodb_policy "$TICKET_API_ROLE" "yallabalagan-social-posts"

# Allow ticket-api to invoke social-poster
aws iam put-role-policy \
  --role-name "$TICKET_API_ROLE" \
  --policy-name "InvokeSocialPoster" \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"arn:aws:lambda:${REGION}:${ACTUAL_ACCOUNT}:function:yallabalagan-social-poster\"}]}" \
  --profile "$PROFILE" 2>/dev/null && echo "  Policy attached: $TICKET_API_ROLE → InvokeSocialPoster" || true

# Deploy instagram-token-refresher Lambda
echo ""
echo "Deploying instagram-token-refresher..."
ensure_lambda "yallabalagan-instagram-token-refresher" "lambdas/instagram-token-refresher.lambda_handler"
update_lambda "yallabalagan-instagram-token-refresher" \
  ".aws-sam/build/InstagramTokenRefresherFunction" \
  "lambdas/instagram-token-refresher.lambda_handler"

cat > /tmp/ig-refresher-env.json <<EOF
{
  "Variables": {
    "INSTAGRAM_CONNECTIONS_TABLE": "yallabalagan-instagram",
    "META_APP_ID": "${META_APP_ID}",
    "META_APP_SECRET": "${META_APP_SECRET}",
    "INSTAGRAM_TOKEN_KEY": "${INSTAGRAM_TOKEN_KEY}"
  }
}
EOF
aws lambda wait function-updated \
  --function-name yallabalagan-instagram-token-refresher \
  --region "$REGION" --profile "$PROFILE"
aws lambda update-function-configuration \
  --function-name yallabalagan-instagram-token-refresher \
  --environment file:///tmp/ig-refresher-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/ig-refresher-env.json

IG_REFRESHER_ROLE=$(aws lambda get-function-configuration --function-name yallabalagan-instagram-token-refresher --region "$REGION" --profile "$PROFILE" --query 'Role' --output text 2>/dev/null | sed 's|.*/||' || echo "")
if [ -n "$IG_REFRESHER_ROLE" ]; then
  ensure_dynamodb_policy "$IG_REFRESHER_ROLE" "yallabalagan-instagram"
fi
echo "  instagram-token-refresher deployed"

# Deploy social-poster Lambda
echo ""
echo "Deploying social-poster..."
ensure_lambda "yallabalagan-social-poster" "lambdas/social-poster.lambda_handler" 300 1024
update_lambda "yallabalagan-social-poster" \
  ".aws-sam/build/SocialPosterFunction" \
  "lambdas/social-poster.lambda_handler"

cat > /tmp/social-poster-env.json <<EOF
{
  "Variables": {
    "SOCIAL_POSTS_TABLE": "yallabalagan-social-posts",
    "INSTAGRAM_CONNECTIONS_TABLE": "yallabalagan-instagram",
    "INSTAGRAM_TOKEN_KEY": "${INSTAGRAM_TOKEN_KEY}",
    "TIKTOK_CONNECTIONS_TABLE": "yallabalagan-tiktok",
    "TIKTOK_CLIENT_KEY": "${TIKTOK_CLIENT_KEY}",
    "TIKTOK_CLIENT_SECRET": "${TIKTOK_CLIENT_SECRET}",
    "TIKTOK_TOKEN_KEY": "${TIKTOK_TOKEN_KEY}",
    "YOUTUBE_CONNECTIONS_TABLE": "yallabalagan-youtube",
    "YOUTUBE_CLIENT_ID": "${YOUTUBE_CLIENT_ID}",
    "YOUTUBE_CLIENT_SECRET": "${YOUTUBE_CLIENT_SECRET}",
    "YOUTUBE_TOKEN_KEY": "${YOUTUBE_TOKEN_KEY}",
    "MEDIA_BUCKET": "${MEDIA_BUCKET}",
    "ENVIRONMENT": "${ENV}"
  }
}
EOF
aws lambda wait function-updated \
  --function-name yallabalagan-social-poster \
  --region "$REGION" --profile "$PROFILE"
aws lambda update-function-configuration \
  --function-name yallabalagan-social-poster \
  --environment file:///tmp/social-poster-env.json \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
rm -f /tmp/social-poster-env.json

SOCIAL_POSTER_ROLE=$(aws lambda get-function-configuration --function-name yallabalagan-social-poster --region "$REGION" --profile "$PROFILE" --query 'Role' --output text 2>/dev/null | sed 's|.*/||' || echo "")
if [ -n "$SOCIAL_POSTER_ROLE" ]; then
  ensure_dynamodb_policy "$SOCIAL_POSTER_ROLE" "yallabalagan-social-posts"
  ensure_dynamodb_policy "$SOCIAL_POSTER_ROLE" "yallabalagan-instagram"
  ensure_dynamodb_policy "$SOCIAL_POSTER_ROLE" "yallabalagan-tiktok"
  ensure_dynamodb_policy "$SOCIAL_POSTER_ROLE" "yallabalagan-youtube"
  aws iam put-role-policy \
    --role-name "$SOCIAL_POSTER_ROLE" \
    --policy-name "S3-ReadMedia" \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\"],\"Resource\":\"arn:aws:s3:::${MEDIA_BUCKET}/*\"}]}" \
    --profile "$PROFILE" 2>/dev/null && echo "  Policy attached: $SOCIAL_POSTER_ROLE → S3 read" || true
fi
echo "  social-poster deployed"

# Wire EventBridge schedule → social-poster (idempotent)
echo ""
echo "Wiring EventBridge schedule for social-poster..."
aws events put-rule \
  --name "yallabalagan-social-poster-schedule" \
  --schedule-expression "rate(5 minutes)" \
  --state ENABLED \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws events put-targets \
  --rule "yallabalagan-social-poster-schedule" \
  --targets "[{\"Id\":\"SocialPoster\",\"Arn\":\"arn:aws:lambda:${REGION}:${ACTUAL_ACCOUNT}:function:yallabalagan-social-poster\",\"Input\":\"{\\\"source\\\":\\\"scheduler\\\"}\"}]" \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null
aws lambda add-permission \
  --function-name yallabalagan-social-poster \
  --statement-id allow-eventbridge-schedule \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACTUAL_ACCOUNT}:rule/yallabalagan-social-poster-schedule" \
  --region "$REGION" --profile "$PROFILE" --no-cli-pager > /dev/null 2>&1 || true
echo "  EventBridge schedule wired (rate 5 min)"

# Allow site-regenerator to invalidate CloudFront
echo "  Ensuring CloudFront invalidation policy for site-regenerator..."
aws iam put-role-policy \
  --role-name "$REGEN_ROLE" \
  --policy-name "CloudFront-Invalidation" \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"cloudfront:CreateInvalidation","Resource":"*"}]}' \
  --profile "$PROFILE" 2>/dev/null && echo "  Policy attached: $REGEN_ROLE → cloudfront:CreateInvalidation" || true

# Sync S3
echo ""
echo "Syncing admin files to S3..."
aws s3 sync "$SCRIPT_DIR/admin-v2/" "s3://$ADMIN_BUCKET/" \
  --profile "$PROFILE" \
  --exclude "*.md" --exclude ".DS_Store" \
  --delete

echo "Copying shared accessibility files..."
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.css" "$SCRIPT_DIR/frontend/static/css/"
cp "$SCRIPT_DIR/../accessibility/accessibility-toolbar.js" "$SCRIPT_DIR/frontend/static/js/"
mkdir -p "$SCRIPT_DIR/frontend/static/fonts/OpenDyslexic"
cp "$SCRIPT_DIR/../accessibility/fonts/"* "$SCRIPT_DIR/frontend/static/fonts/OpenDyslexic/"

echo "Syncing frontend static files to S3..."
aws s3 sync "$SCRIPT_DIR/frontend/static/" "s3://$FRONTEND_BUCKET/static/" \
  --profile "$PROFILE" \
  --exclude "*.md" --exclude ".DS_Store"

# Ensure S3 website ErrorDocument points to 404.html
echo ""
echo "Updating S3 website configuration..."
aws s3api put-bucket-website \
  --bucket "$FRONTEND_BUCKET" \
  --website-configuration '{"IndexDocument":{"Suffix":"index.html"},"ErrorDocument":{"Key":"404.html"}}' \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager
echo "  ErrorDocument set to 404.html"

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
  aws cloudfront create-invalidation \
    --distribution-id E395U4QHM2AOIF \
    --paths "/*" \
    --profile "$PROFILE" --no-cli-pager > /dev/null
  echo "  Invalidation created"
fi

echo ""
echo "=== Deployment complete: $ENV ==="
echo ""
if [[ "$ENV" == "prod" ]]; then
  echo "  Admin:    https://admin.yallabalagan.org"
  echo "  Frontend: https://yallabalagan.org"
  echo "  API:      https://ovajavet67.execute-api.eu-north-1.amazonaws.com"
else
  echo "  Admin:    http://$ADMIN_BUCKET.s3-website.eu-north-1.amazonaws.com"
  echo "  Frontend: http://$FRONTEND_BUCKET.s3-website.eu-north-1.amazonaws.com"
  echo "  API:      ${API_URL}"
fi
echo ""
echo "Logs: aws logs tail /aws/lambda/yallabalagan-ticket-api --follow --profile $PROFILE"
