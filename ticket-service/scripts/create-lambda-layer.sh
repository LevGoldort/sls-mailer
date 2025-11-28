#!/bin/bash
set -e

echo "📦 Creating Lambda Layer with templates and static files..."

cd "$(dirname "$0")/.."

# Create layer directory structure
# Note: AWS Lambda extracts layers to /opt, so we create the structure without /opt prefix
mkdir -p lambda-layer/templates
mkdir -p lambda-layer/static

# Copy templates
cp -r frontend/templates/* lambda-layer/templates/

# Copy static files
cp -r frontend/static/* lambda-layer/static/

# Create zip
cd lambda-layer
zip -r ../site-templates-layer.zip .
cd ..

echo "✅ Layer created: site-templates-layer.zip"
echo "📤 Uploading to AWS..."

# Upload layer
aws lambda publish-layer-version \
  --layer-name yallabalagan-site-templates \
  --description "Jinja2 templates and static files for site generation" \
  --zip-file fileb://site-templates-layer.zip \
  --compatible-runtimes python3.11 \
  --region eu-north-1

# Cleanup
rm -rf lambda-layer site-templates-layer.zip

echo "✅ Lambda layer published!"
