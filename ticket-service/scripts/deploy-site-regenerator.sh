#!/bin/bash
set -e

SKIP_DEPS=${1:-false}

echo "🚀 Deploying site-regenerator Lambda function..."

cd "$(dirname "$0")/.."

# Create deployment package
echo "📦 Creating deployment package..."
mkdir -p lambda-site-regenerator
cp lambdas/site-regenerator.py lambda-site-regenerator/lambda_function.py

# Install dependencies (if not skipping)
cd lambda-site-regenerator
if [ "$SKIP_DEPS" = "true" ]; then
    echo "⚡ Skipping dependency installation (quick mode)"
    if [ -d "/tmp/site-regenerator-deps-cache" ]; then
        echo "📋 Using cached dependencies..."
        cp -r /tmp/site-regenerator-deps-cache/* . 2>/dev/null || true
    fi
else
    echo "📥 Installing dependencies..."
    pip install requests jinja2 pytz -t . --platform manylinux2014_x86_64 --only-binary=:all:
    # Cache dependencies
    mkdir -p /tmp/site-regenerator-deps-cache
    rsync -a --exclude='lambda_function.py' . /tmp/site-regenerator-deps-cache/ 2>/dev/null || true
fi
zip -r ../site-regenerator.zip .
cd ..

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name yallabalagan-site-regenerator --region eu-north-1 --no-cli-pager 2>&1 || echo "not found")

if [[ "$FUNCTION_EXISTS" == *"not found"* ]]; then
    echo "📤 Creating new Lambda function..."

    # Create function
    aws lambda create-function \
      --function-name yallabalagan-site-regenerator \
      --runtime python3.11 \
      --role arn:aws:iam::982534389905:role/YallaBalagan-TicketService-Lambda-Role \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://site-regenerator.zip \
      --timeout 60 \
      --memory-size 512 \
      --environment Variables="{API_URL=https://ovajavet67.execute-api.eu-north-1.amazonaws.com,S3_BUCKET=yallabalagan-tickets-frontend,GA4_ID=G-RP1612BFV9,FB_PIXEL_ID=738718761834602}" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

    # Get layer ARN
    LAYER_ARN=$(aws lambda list-layer-versions --layer-name yallabalagan-site-templates --region eu-north-1 --query 'LayerVersions[0].LayerVersionArn' --output text --no-cli-pager)

    # Attach layer
    aws lambda update-function-configuration \
      --function-name yallabalagan-site-regenerator \
      --layers "$LAYER_ARN" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null
else
    echo "🔄 Updating existing Lambda function..."

    # Update function code
    aws lambda update-function-code \
      --function-name yallabalagan-site-regenerator \
      --zip-file fileb://site-regenerator.zip \
      --region eu-north-1 \
      --no-cli-pager > /dev/null

    # Wait for code update to complete before updating configuration
    echo "⏳ Waiting for code update to complete..."
    sleep 3

    # Update environment variables
    echo "🔄 Updating environment variables..."
    aws lambda update-function-configuration \
      --function-name yallabalagan-site-regenerator \
      --environment Variables="{API_URL=https://ovajavet67.execute-api.eu-north-1.amazonaws.com,S3_BUCKET=yallabalagan-tickets-frontend,GA4_ID=G-RP1612BFV9,FB_PIXEL_ID=738718761834602}" \
      --region eu-north-1 \
      --no-cli-pager > /dev/null
fi

# Cleanup
rm -rf lambda-site-regenerator site-regenerator.zip

echo "✅ Lambda function deployed successfully!"

# Cleanup
rm -f response.json

echo "✅ Deployment complete!"
