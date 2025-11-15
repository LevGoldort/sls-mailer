#!/bin/bash

# Script to upload Lambda functions to AWS
# Usage: ./upload-lambdas.sh [function-name]
#   - No arguments: deploy all Lambda functions
#   - With argument: deploy only the specified function

set -e  # Exit on error

LAMBDAS_DIR="./Lambdas"
TEMP_DIR=$(mktemp -d)

# Color output for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to deploy a single Lambda
deploy_lambda() {
    local lambda_file=$1
    local filename=$(basename "$lambda_file")
    local function_name="${filename%.py}"

    echo -e "${YELLOW}Processing: $function_name${NC}"

    # Create a temporary working directory for this Lambda
    local work_dir="$TEMP_DIR/$function_name"
    mkdir -p "$work_dir"

    # Copy the Lambda file as lambda_function.py
    cp "$lambda_file" "$work_dir/lambda_function.py"

    # Create zip archive
    local zip_file="$TEMP_DIR/${function_name}.zip"
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
}

# Main script
echo "Starting Lambda deployment..."
echo "Temporary directory: $TEMP_DIR"
echo ""

# Check if a specific function name was provided
if [ $# -eq 1 ]; then
    # Deploy single function
    FUNCTION_NAME=$1
    LAMBDA_FILE="$LAMBDAS_DIR/${FUNCTION_NAME}.py"

    if [ ! -f "$LAMBDA_FILE" ]; then
        echo -e "${RED}Error: Lambda function '$FUNCTION_NAME' not found at $LAMBDA_FILE${NC}"
        echo -e "${BLUE}Available functions:${NC}"
        for file in "$LAMBDAS_DIR"/*.py; do
            echo "  - $(basename "${file%.py}")"
        done
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    echo -e "${BLUE}Deploying single function: $FUNCTION_NAME${NC}"
    echo ""
    deploy_lambda "$LAMBDA_FILE"
else
    # Deploy all functions
    echo -e "${BLUE}Deploying all Lambda functions${NC}"
    echo ""

    for lambda_file in "$LAMBDAS_DIR"/*.py; do
        deploy_lambda "$lambda_file"
    done
fi

# Cleanup
echo "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo -e "${GREEN}Deployment complete!${NC}"
