#!/bin/bash

# Script to upload Lambda functions to AWS
# Usage: ./upload-lambdas.sh [project/function-name]
#   - No arguments: deploy all Lambda functions from all projects
#   - With argument: deploy only the specified function (e.g., newsletter/newsletter-api)

set -e  # Exit on error

# Base directory for all projects (one level up from scripts/)
BASE_DIR=".."
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
    # Deploy single function (format: project/function-name or just function-name.py)
    FUNCTION_PATH=$1

    # Check if it's a full path with project
    if [[ "$FUNCTION_PATH" == *"/"* ]]; then
        LAMBDA_FILE="$BASE_DIR/${FUNCTION_PATH}.py"
    else
        # Search for the function in all project directories
        FOUND=""
        for project in events-site donate-site newsletter; do
            TEST_PATH="$BASE_DIR/$project/lambdas/${FUNCTION_PATH}.py"
            if [ -f "$TEST_PATH" ]; then
                LAMBDA_FILE="$TEST_PATH"
                FOUND="yes"
                break
            fi
        done

        if [ -z "$FOUND" ]; then
            echo -e "${RED}Error: Lambda function '$FUNCTION_PATH' not found${NC}"
            echo -e "${BLUE}Available functions:${NC}"
            for project in events-site donate-site newsletter; do
                echo -e "${YELLOW}$project:${NC}"
                for file in "$BASE_DIR/$project/lambdas"/*.py 2>/dev/null; do
                    [ -f "$file" ] && echo "  - $(basename "${file%.py}")"
                done
            done
            rm -rf "$TEMP_DIR"
            exit 1
        fi
    fi

    if [ ! -f "$LAMBDA_FILE" ]; then
        echo -e "${RED}Error: Lambda function not found at $LAMBDA_FILE${NC}"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    echo -e "${BLUE}Deploying single function: $FUNCTION_PATH${NC}"
    echo ""
    deploy_lambda "$LAMBDA_FILE"
else
    # Deploy all functions from all projects
    echo -e "${BLUE}Deploying all Lambda functions from all projects${NC}"
    echo ""

    for project in events-site donate-site newsletter; do
        PROJECT_DIR="$BASE_DIR/$project/lambdas"
        if [ -d "$PROJECT_DIR" ]; then
            echo -e "${YELLOW}=== Project: $project ===${NC}"
            for lambda_file in "$PROJECT_DIR"/*.py; do
                [ -f "$lambda_file" ] && deploy_lambda "$lambda_file"
            done
        fi
    done
fi

# Cleanup
echo "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo -e "${GREEN}Deployment complete!${NC}"
