#!/bin/bash
set -e

echo "🚀 Deploying site-regenerator Lambda function..."

cd "$(dirname "$0")/.."

# Create deployment package
echo "📦 Creating deployment package..."
mkdir -p lambda-site-regenerator
cp lambdas/site-regenerator.py lambda-site-regenerator/lambda_function.py

# Install dependencies
cd lambda-site-regenerator
pip install requests jinja2 -t . --platform manylinux2014_x86_64 --only-binary=:all:
zip -r ../site-regenerator.zip .
cd ..

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name yallabalagan-site-regenerator --region eu-north-1 2>&1 || echo "not found")

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
      --environment Variables="{API_URL=https://ovajavet67.execute-api.eu-north-1.amazonaws.com,S3_BUCKET=yallabalagan-tickets-frontend}" \
      --region eu-north-1

    # Get layer ARN
    LAYER_ARN=$(aws lambda list-layer-versions --layer-name yallabalagan-site-templates --region eu-north-1 --query 'LayerVersions[0].LayerVersionArn' --output text)

    # Attach layer
    aws lambda update-function-configuration \
      --function-name yallabalagan-site-regenerator \
      --layers "$LAYER_ARN" \
      --region eu-north-1
else
    echo "🔄 Updating existing Lambda function..."

    # Update function code
    aws lambda update-function-code \
      --function-name yallabalagan-site-regenerator \
      --zip-file fileb://site-regenerator.zip \
      --region eu-north-1
fi

# Cleanup
rm -rf lambda-site-regenerator site-regenerator.zip

echo "✅ Lambda function deployed successfully!"
echo "🧪 Testing function..."

# Test invoke
aws lambda invoke \
  --function-name yallabalagan-site-regenerator \
  --region eu-north-1 \
  response.json

cat response.json | jq
rm response.json

echo "✅ Deployment complete!"
