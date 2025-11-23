#!/bin/bash
#
# Deploy Newsletter System
# Updates Lambda functions and S3 static files
#
# Usage: ./deploy-newsletter.sh [options]
#   --lambdas-only    Only deploy Lambda functions
#   --s3-only         Only deploy S3 files
#   --help            Show this help

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
LAMBDAS_DIR="./Lambdas"
S3_BUCKET="yallabalagan-newsletter-admin"
REGION="eu-north-1"
ADMIN_DIR="./newsletter-admin"

# Newsletter Lambda functions
NEWSLETTER_LAMBDAS=(
    "newsletter-api"
    "newsletter-sender"
    "newsletter-tracker"
    "newsletter-unsubscribe-handler"
)

# Parse arguments
DEPLOY_LAMBDAS=true
DEPLOY_S3=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --lambdas-only)
            DEPLOY_S3=false
            shift
            ;;
        --s3-only)
            DEPLOY_LAMBDAS=false
            shift
            ;;
        --help)
            echo "Usage: ./deploy-newsletter.sh [options]"
            echo "  --lambdas-only    Only deploy Lambda functions"
            echo "  --s3-only         Only deploy S3 files"
            echo "  --help            Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Newsletter System Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to deploy a single Lambda
deploy_lambda() {
    local lambda_file=$1
    local filename=$(basename "$lambda_file")
    local function_name="${filename%.py}"

    echo -e "${YELLOW}Deploying: ${function_name}${NC}"

    # Create temporary directory
    local temp_dir=$(mktemp -d)
    local work_dir="$temp_dir/$function_name"
    mkdir -p "$work_dir"

    # Copy the Lambda file as lambda_function.py
    cp "$lambda_file" "$work_dir/lambda_function.py"

    # Create zip archive
    local zip_file="$temp_dir/${function_name}.zip"
    (cd "$work_dir" && zip -q "$zip_file" lambda_function.py)

    # Upload to AWS Lambda
    if aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://$zip_file" \
        --region "$REGION" \
        --no-cli-pager > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Successfully deployed $function_name${NC}"
    else
        echo -e "${RED}✗ Failed to deploy $function_name${NC}"
        rm -rf "$temp_dir"
        return 1
    fi

    # Cleanup
    rm -rf "$temp_dir"
}

# Deploy Lambda functions
if [ "$DEPLOY_LAMBDAS" = true ]; then
    echo -e "${BLUE}📦 Deploying Lambda Functions...${NC}"
    echo ""

    for lambda_name in "${NEWSLETTER_LAMBDAS[@]}"; do
        lambda_file="$LAMBDAS_DIR/${lambda_name}.py"

        if [ ! -f "$lambda_file" ]; then
            echo -e "${RED}✗ Lambda file not found: $lambda_file${NC}"
            continue
        fi

        deploy_lambda "$lambda_file"
    done

    echo ""
fi

# Deploy S3 static files
if [ "$DEPLOY_S3" = true ]; then
    echo -e "${BLUE}🌐 Deploying Web Admin to S3...${NC}"
    echo ""

    # Check if directory exists
    if [ ! -d "$ADMIN_DIR" ]; then
        echo -e "${RED}✗ Admin directory not found: $ADMIN_DIR${NC}"
        exit 1
    fi

    # Sync files to S3
    echo -e "${YELLOW}Syncing files to s3://$S3_BUCKET...${NC}"

    if aws s3 sync "$ADMIN_DIR" "s3://$S3_BUCKET" \
        --region "$REGION" \
        --exclude "*.py" \
        --exclude "*.md" \
        --exclude "*.backup" \
        --exclude ".gitignore" \
        --exclude ".DS_Store" \
        --cache-control "no-cache, no-store, must-revalidate" \
        --delete; then
        echo -e "${GREEN}✓ Successfully deployed web admin${NC}"
    else
        echo -e "${RED}✗ Failed to deploy web admin${NC}"
        exit 1
    fi

    echo ""

    # Show S3 URL
    echo -e "${GREEN}🌍 Web Admin URL:${NC}"
    echo -e "   http://$S3_BUCKET.s3-website.$REGION.amazonaws.com"
    echo ""
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Show what was deployed
if [ "$DEPLOY_LAMBDAS" = true ]; then
    echo -e "${BLUE}Deployed Lambda functions:${NC}"
    for lambda_name in "${NEWSLETTER_LAMBDAS[@]}"; do
        echo "  • $lambda_name"
    done
    echo ""
fi

if [ "$DEPLOY_S3" = true ]; then
    echo -e "${BLUE}Deployed S3 files:${NC}"
    aws s3 ls "s3://$S3_BUCKET" --region "$REGION" | grep -E "\\.html$" | awk '{print "  • " $4}'
    echo ""
fi

echo -e "${YELLOW}💡 Tips:${NC}"
echo "  • Test the admin: http://$S3_BUCKET.s3-website.$REGION.amazonaws.com"
echo "  • Check Lambda logs: aws logs tail /aws/lambda/newsletter-api --follow"
echo "  • Deploy only Lambdas: ./deploy-newsletter.sh --lambdas-only"
echo "  • Deploy only S3: ./deploy-newsletter.sh --s3-only"
echo ""
