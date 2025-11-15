#!/bin/bash

# Script to upload Lambda functions to AWS
# Each .py file in Lambdas/ directory will be uploaded as a separate Lambda function

set -e  # Exit on error

LAMBDAS_DIR="./Lambdas"
TEMP_DIR=$(mktemp -d)

# Color output for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Starting Lambda deployment..."
echo "Temporary directory: $TEMP_DIR"
echo ""

# Iterate through each Python file in Lambdas directory
for lambda_file in "$LAMBDAS_DIR"/*.py; do
    # Get the base filename without path and extension
    filename=$(basename "$lambda_file")
    function_name="${filename%.py}"

    echo -e "${YELLOW}Processing: $function_name${NC}"

    # Create a temporary working directory for this Lambda
    work_dir="$TEMP_DIR/$function_name"
    mkdir -p "$work_dir"

    # Copy the Lambda file as lambda_function.py
    cp "$lambda_file" "$work_dir/lambda_function.py"

    # Create zip archive
    zip_file="$TEMP_DIR/${function_name}.zip"
    (cd "$work_dir" && zip -q "$zip_file" lambda_function.py)

    # Upload to AWS Lambda
    echo "Uploading to AWS Lambda function: $function_name"
    if aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://$zip_file" \
        --no-cli-pager > /dev/null; then
        echo -e "${GREEN}✓ Successfully uploaded $function_name${NC}"
    else
        echo -e "${RED}✗ Failed to upload $function_name${NC}"
    fi

    echo ""
done

# Cleanup
echo "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo -e "${GREEN}Deployment complete!${NC}"
