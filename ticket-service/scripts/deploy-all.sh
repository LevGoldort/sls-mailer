#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REGION="eu-north-1"
ADMIN_BUCKET="yallabalagan-ticket-admin"
FRONTEND_BUCKET="yallabalagan-tickets-frontend"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Usage
usage() {
    echo -e "${BLUE}Usage:${NC} $0 [admin|frontend|all] [--skip-layers]"
    echo ""
    echo "Options:"
    echo "  admin     - Deploy admin panel only (sync S3 + deploy admin lambdas)"
    echo "  frontend  - Deploy frontend only (regenerate site + deploy all lambdas + layers)"
    echo "  all       - Deploy everything (admin + frontend)"
    echo ""
    echo "Flags:"
    echo "  --skip-layers  - Skip Lambda Layer update and dependency reinstall (faster)"
    echo ""
    echo "Examples:"
    echo "  $0 frontend              # Full deploy with layers (slow)"
    echo "  $0 frontend --skip-layers  # Quick deploy, code only (fast)"
    echo ""
    exit 1
}

# Deploy admin
deploy_admin() {
    echo -e "${GREEN}🚀 Deploying Admin Panel...${NC}"

    # Sync admin files to S3
    echo -e "${BLUE}📤 Syncing admin files to S3...${NC}"
    aws s3 sync "$PROJECT_DIR/admin-v2/" "s3://$ADMIN_BUCKET/" \
        --region "$REGION" \
        --exclude ".DS_Store" \
        --delete

    echo -e "${GREEN}✅ Admin panel deployed successfully!${NC}"
    echo -e "${BLUE}🌐 Admin URL: http://$ADMIN_BUCKET.s3-website-$REGION.amazonaws.com/${NC}"
}

# Deploy event status updater (inline function)
deploy_event_status_updater() {
    local skip_deps=$1
    local FUNCTION_NAME="yallabalagan-event-status-updater"

    echo -e "${BLUE}📦 Deploying event status updater...${NC}"

    # Create deployment package
    local TEMP_DIR=$(mktemp -d)
    cp lambdas/event-status-updater.py "$TEMP_DIR/lambda_function.py"

    # Install dependencies if not skipping
    if [ "$skip_deps" != "true" ]; then
        cd "$TEMP_DIR"
        pip install -q pytz -t . > /dev/null 2>&1
        cd - > /dev/null
    fi

    # Create zip
    cd "$TEMP_DIR"
    local ZIP_FILE="$TEMP_DIR/deployment.zip"
    zip -rq "$ZIP_FILE" .
    cd - > /dev/null

    # Update function
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$ZIP_FILE" \
        --region "$REGION" \
        --no-cli-pager > /dev/null

    # Cleanup
    rm -rf "$TEMP_DIR"
}

# Deploy lambdas
deploy_lambdas() {
    local skip_deps=$1
    echo -e "${GREEN}🚀 Deploying Lambda Functions...${NC}"

    if [ "$skip_deps" = "true" ]; then
        echo -e "${YELLOW}⚡ Quick mode: skipping dependency reinstall${NC}"
    fi

    # Deploy main API handler
    echo -e "${BLUE}📦 Deploying ticket API handler...${NC}"
    "$SCRIPT_DIR/deploy-lambda.sh" "$skip_deps"

    # Deploy site regenerator
    echo -e "${BLUE}📦 Deploying site regenerator...${NC}"
    "$SCRIPT_DIR/deploy-site-regenerator.sh" "$skip_deps"

    # Deploy email sender
    echo -e "${BLUE}📦 Deploying email sender...${NC}"
    "$SCRIPT_DIR/deploy-email-sender.sh" "$skip_deps"

    # Deploy SMS sender
    echo -e "${BLUE}📦 Deploying SMS sender...${NC}"
    "$SCRIPT_DIR/deploy-sms-sender.sh" "$skip_deps"

    # Deploy event status updater (inline)
    deploy_event_status_updater "$skip_deps"

    echo -e "${GREEN}✅ All Lambda functions deployed successfully!${NC}"
}

# Update Lambda Layer
update_layer() {
    echo -e "${GREEN}🚀 Updating Lambda Layer...${NC}"

    # Create layer zip
    echo -e "${BLUE}📦 Creating layer package...${NC}"
    cd "$PROJECT_DIR"
    mkdir -p lambda-layer/templates
    mkdir -p lambda-layer/static
    cp -r frontend/templates/* lambda-layer/templates/
    cp -r frontend/static/* lambda-layer/static/
    cd lambda-layer
    zip -r ../site-templates-layer.zip . > /dev/null
    cd ..
    rm -rf lambda-layer

    # Publish new layer version and capture ARN
    echo -e "${BLUE}📤 Publishing new layer version...${NC}"
    LAYER_ARN=$(aws lambda publish-layer-version \
        --layer-name yallabalagan-site-templates \
        --description "Jinja2 templates and static files for site generation" \
        --zip-file fileb://site-templates-layer.zip \
        --compatible-runtimes python3.11 python3.12 \
        --region "$REGION" \
        --query 'LayerVersionArn' \
        --output text \
        --no-cli-pager)

    # Cleanup
    rm -f site-templates-layer.zip

    if [ -z "$LAYER_ARN" ] || [ "$LAYER_ARN" = "None" ]; then
        echo -e "${RED}❌ Failed to create layer!${NC}"
        return 1
    fi

    echo -e "${GREEN}✅ Layer published: $LAYER_ARN${NC}"

    # Update site-regenerator to use new layer
    echo -e "${BLUE}🔄 Updating site-regenerator to use latest layer...${NC}"
    aws lambda update-function-configuration \
        --function-name yallabalagan-site-regenerator \
        --layers "$LAYER_ARN" \
        --region "$REGION" \
        --no-cli-pager > /dev/null

    echo -e "${GREEN}✅ Lambda Layer updated successfully!${NC}"
}

# Regenerate frontend site
regenerate_site() {
    echo -e "${GREEN}🚀 Regenerating Frontend Site...${NC}"

    # Wait a bit for layer update to complete
    echo -e "${BLUE}⏳ Waiting for Lambda update to complete...${NC}"
    sleep 3

    # Invoke site regenerator
    echo -e "${BLUE}🏗️  Generating static site from DynamoDB data...${NC}"
    aws lambda invoke \
        --function-name yallabalagan-site-regenerator \
        --region "$REGION" \
        --payload '{}' \
        --no-cli-pager \
        /tmp/regenerate-response.json > /dev/null

    # Parse response
    RESPONSE=$(cat /tmp/regenerate-response.json)
    STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['body'])" 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")

    if [ "$STATUS" = "success" ]; then
        echo -e "${GREEN}✅ Frontend site regenerated successfully!${NC}"
        echo -e "${BLUE}🌐 Frontend URL: http://$FRONTEND_BUCKET.s3-website-$REGION.amazonaws.com/${NC}"
    else
        echo -e "${RED}❌ Site regeneration failed. Check logs with:${NC}"
        echo -e "   aws logs tail /aws/lambda/yallabalagan-site-regenerator --follow --region $REGION"
    fi

    rm -f /tmp/regenerate-response.json
}

# Sync static files
sync_static_files() {
    echo -e "${BLUE}📤 Syncing static files (CSS, JS, fonts, images)...${NC}"
    aws s3 sync "$PROJECT_DIR/frontend/static/" "s3://$FRONTEND_BUCKET/static/" \
        --region "$REGION" \
        --exclude ".DS_Store" \
        --delete
    echo -e "${GREEN}✅ Static files synced successfully!${NC}"
}

# Deploy frontend
deploy_frontend() {
    local skip_layers=$1
    echo -e "${GREEN}🚀 Deploying Frontend...${NC}"

    # Sync static files first
    sync_static_files

    # Update Lambda Layer first (unless skipping)
    if [ "$skip_layers" != "true" ]; then
        update_layer
        # Wait for layer update to complete before deploying functions
        echo -e "${BLUE}⏳ Waiting for layer update to complete...${NC}"
        sleep 5
    else
        echo -e "${YELLOW}⚡ Skipping Lambda Layer update${NC}"
    fi

    # Deploy all Lambda functions
    deploy_lambdas "$skip_layers"

    # Regenerate site
    regenerate_site
}

# Main script
main() {
    if [ $# -eq 0 ]; then
        usage
    fi

    cd "$PROJECT_DIR"

    # Parse flags
    SKIP_LAYERS="false"
    if [[ "$2" == "--skip-layers" ]] || [[ "$3" == "--skip-layers" ]]; then
        SKIP_LAYERS="true"
    fi

    case "$1" in
        admin)
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}  Deploying ADMIN PANEL${NC}"
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            deploy_admin
            ;;
        frontend)
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}  Deploying FRONTEND${NC}"
            if [ "$SKIP_LAYERS" = "true" ]; then
                echo -e "${YELLOW}  (Quick mode - skipping layers)${NC}"
            fi
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            deploy_frontend "$SKIP_LAYERS"
            ;;
        all)
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}  Deploying EVERYTHING${NC}"
            if [ "$SKIP_LAYERS" = "true" ]; then
                echo -e "${YELLOW}  (Quick mode - skipping layers)${NC}"
            fi
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            deploy_admin
            echo ""
            deploy_frontend "$SKIP_LAYERS"
            ;;
        *)
            echo -e "${RED}❌ Invalid argument: $1${NC}"
            echo ""
            usage
            ;;
    esac

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✅ Deployment Complete!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Run main
main "$@"
