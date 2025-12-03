#!/bin/bash
#
# Deploy All YallaBalagan Services to AWS
# Usage: ./deploy-all.sh [prod|dev]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Environment
ENV=${1:-dev}

if [[ "$ENV" != "prod" && "$ENV" != "dev" ]]; then
    echo -e "${RED}Error: Environment must be 'prod' or 'dev'${NC}"
    echo "Usage: ./deploy-all.sh [prod|dev]"
    exit 1
fi

# AWS Profile
if [ "$ENV" = "prod" ]; then
    AWS_PROFILE="yallabalagan-prod"
    CONFIG_ENV="default"
else
    AWS_PROFILE="yallabalagan-dev"
    CONFIG_ENV="dev"
fi

echo -e "${YELLOW}╔════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   YallaBalagan Deployment to ${ENV^^}        ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}AWS Profile: ${AWS_PROFILE}${NC}"
echo -e "${BLUE}Region: eu-north-1${NC}"
echo ""

# Check AWS credentials
echo -e "${BLUE}🔐 Checking AWS credentials...${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile $AWS_PROFILE 2>/dev/null || echo "")
if [ -z "$ACCOUNT_ID" ]; then
    echo -e "${RED}❌ AWS credentials not configured for profile: $AWS_PROFILE${NC}"
    echo "Run: aws configure --profile $AWS_PROFILE"
    exit 1
fi
echo -e "${GREEN}✅ AWS Account ID: $ACCOUNT_ID${NC}"
echo ""

# Check SAM CLI
echo -e "${BLUE}🔧 Checking SAM CLI...${NC}"
if ! command -v sam &> /dev/null; then
    echo -e "${RED}❌ AWS SAM CLI not installed${NC}"
    echo "Install: brew install aws-sam-cli"
    exit 1
fi
SAM_VERSION=$(sam --version)
echo -e "${GREEN}✅ $SAM_VERSION${NC}"
echo ""

# Load environment variables
if [ -f ".env.$ENV" ]; then
    echo -e "${BLUE}📥 Loading environment variables from .env.$ENV${NC}"
    set -a
    source .env.$ENV
    set +a
    echo -e "${GREEN}✅ Environment variables loaded${NC}"
else
    echo -e "${YELLOW}⚠️  No .env.$ENV file found. You'll need to provide parameters manually.${NC}"
fi
echo ""

# Confirmation
if [ "$ENV" = "prod" ]; then
    echo -e "${YELLOW}⚠️  WARNING: You are deploying to PRODUCTION!${NC}"
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Deployment cancelled."
        exit 0
    fi
    echo ""
fi

# Function to deploy a service
deploy_service() {
    local service_name=$1
    local service_dir=$2

    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  Deploying: $service_name${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    cd "$service_dir" || exit 1

    echo -e "${BLUE}📦 Building...${NC}"
    sam build

    echo -e "${BLUE}🚀 Deploying...${NC}"
    sam deploy \
        --config-env "$CONFIG_ENV" \
        --profile "$AWS_PROFILE" \
        --no-confirm-changeset

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $service_name deployed successfully${NC}"
    else
        echo -e "${RED}❌ Failed to deploy $service_name${NC}"
        cd - > /dev/null
        return 1
    fi

    cd - > /dev/null
    echo ""
}

# Deploy all services
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${GREEN}Starting deployment of all services...${NC}"
echo ""

# 1. Ticket Service
deploy_service "Ticket Service" "$SCRIPT_DIR/ticket-service"

# 2. Events Site
deploy_service "Events Site" "$SCRIPT_DIR/events-site"

# 3. Donate Site
deploy_service "Donate Site" "$SCRIPT_DIR/donate-site"

# 4. Newsletter
deploy_service "Newsletter" "$SCRIPT_DIR/newsletter"

# Summary
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ All services deployed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Get all stack outputs
echo -e "${BLUE}📊 Stack Outputs:${NC}"
echo ""

get_stack_output() {
    local stack_name=$1
    local output_key=$2
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --profile "$AWS_PROFILE" 2>/dev/null || echo "N/A"
}

# Ticket Service
TICKET_STACK="yallabalagan-ticket-service-$ENV"
echo -e "${YELLOW}Ticket Service:${NC}"
echo "  API URL: $(get_stack_output $TICKET_STACK ApiUrl)"
echo "  Frontend: $(get_stack_output $TICKET_STACK FrontendUrl)"
echo "  Admin: $(get_stack_output $TICKET_STACK AdminUrl)"
echo ""

# Events Site
EVENTS_STACK="yallabalagan-events-site-$ENV"
echo -e "${YELLOW}Events Site:${NC}"
echo "  Website: $(get_stack_output $EVENTS_STACK WebsiteUrl)"
echo "  Telegram Webhook: $(get_stack_output $EVENTS_STACK TelegramWebhookUrl)"
echo ""

# Donate Site
DONATE_STACK="yallabalagan-donate-site-$ENV"
echo -e "${YELLOW}Donate Site:${NC}"
echo "  Website: $(get_stack_output $DONATE_STACK WebsiteUrl)"
echo "  Payment Webhook: $(get_stack_output $DONATE_STACK PaymentWebhookUrl)"
echo "  Telegram Webhook: $(get_stack_output $DONATE_STACK TelegramWebhookUrl)"
echo ""

# Newsletter
NEWSLETTER_STACK="yallabalagan-newsletter-$ENV"
echo -e "${YELLOW}Newsletter:${NC}"
echo "  Admin Panel: $(get_stack_output $NEWSLETTER_STACK AdminUrl)"
echo "  API URL: $(get_stack_output $NEWSLETTER_STACK ApiUrl)"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  📝 Next Steps:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "1. Configure Telegram webhooks:"
echo "   Use the Telegram Webhook URLs above"
echo ""
echo "2. Upload static files (admin panels):"
echo "   cd ticket-service && aws s3 sync admin/ s3://yallabalagan-ticket-admin-$ENV/"
echo "   cd newsletter && aws s3 sync admin/ s3://yallabalagan-newsletter-admin-$ENV/"
echo ""
echo "3. Configure All-Pay webhook:"
echo "   Use the Payment Webhook URL above in All-Pay dashboard"
echo ""
echo "4. Verify SES email addresses:"
echo "   aws ses verify-email-identity --email-address your@email.com --profile $AWS_PROFILE"
echo ""
echo "5. Monitor logs:"
echo "   aws logs tail /aws/lambda/yallabalagan-ticket-api-$ENV --follow --profile $AWS_PROFILE"
echo ""
echo -e "${GREEN}🎉 Deployment complete!${NC}"
