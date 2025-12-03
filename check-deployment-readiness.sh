#!/bin/bash
#
# Check if YallaBalagan is ready for deployment
# Usage: ./check-deployment-readiness.sh [prod|dev]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ENV=${1:-dev}
AWS_PROFILE="yallabalagan-$ENV"
CHECKS_PASSED=0
CHECKS_FAILED=0

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   YallaBalagan Deployment Readiness Check ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Environment: $ENV${NC}"
echo -e "${YELLOW}AWS Profile: $AWS_PROFILE${NC}"
echo ""

# Function to check and report
check() {
    local check_name=$1
    local check_command=$2

    printf "%-50s" "$check_name"

    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((CHECKS_FAILED++))
        return 1
    fi
}

# Check CLI tools
echo -e "${BLUE}━━━ CLI Tools ━━━${NC}"
check "AWS CLI installed" "command -v aws"
check "SAM CLI installed" "command -v sam"
check "Python 3.11+ installed" "python3 --version | grep -E '3\.(11|12|13)'"
check "Git installed" "command -v git"
echo ""

# Check AWS credentials
echo -e "${BLUE}━━━ AWS Configuration ━━━${NC}"
check "AWS profile configured ($AWS_PROFILE)" "aws configure get aws_access_key_id --profile $AWS_PROFILE"
check "AWS credentials valid" "aws sts get-caller-identity --profile $AWS_PROFILE"
check "Correct region (eu-north-1)" "aws configure get region --profile $AWS_PROFILE | grep eu-north-1"
echo ""

# Check environment variables file
echo -e "${BLUE}━━━ Environment Variables ━━━${NC}"
check ".env.$ENV file exists" "test -f .env.$ENV"

if [ -f ".env.$ENV" ]; then
    source .env.$ENV

    # Ticket Service
    check "TELEGRAM_BOT_TOKEN_TICKET set" "test -n '$TELEGRAM_BOT_TOKEN_TICKET'"
    check "ALLPAY_WEBHOOK_SECRET set" "test -n '$ALLPAY_WEBHOOK_SECRET'"

    # Events Site
    check "NOTION_TOKEN set" "test -n '$NOTION_TOKEN'"
    check "NOTION_DATABASE_ID_EVENTS set" "test -n '$NOTION_DATABASE_ID_EVENTS'"

    # Newsletter
    check "NEWSLETTER_SECRET_KEY set" "test -n '$NEWSLETTER_SECRET_KEY'"
fi
echo ""

# Check SAM templates
echo -e "${BLUE}━━━ SAM Templates ━━━${NC}"
check "ticket-service/template.yaml exists" "test -f ticket-service/template.yaml"
check "events-site/template.yaml exists" "test -f events-site/template.yaml"
check "donate-site/template.yaml exists" "test -f donate-site/template.yaml"
check "newsletter/template.yaml exists" "test -f newsletter/template.yaml"
echo ""

# Validate SAM templates
echo -e "${BLUE}━━━ Template Validation ━━━${NC}"
check "ticket-service template valid" "(cd ticket-service && sam validate --profile $AWS_PROFILE)"
check "events-site template valid" "(cd events-site && sam validate --profile $AWS_PROFILE)"
check "donate-site template valid" "(cd donate-site && sam validate --profile $AWS_PROFILE)"
check "newsletter template valid" "(cd newsletter && sam validate --profile $AWS_PROFILE)"
echo ""

# Check samconfig files
echo -e "${BLUE}━━━ SAM Configurations ━━━${NC}"
check "ticket-service/samconfig.toml exists" "test -f ticket-service/samconfig.toml"
check "events-site/samconfig.toml exists" "test -f events-site/samconfig.toml"
check "donate-site/samconfig.toml exists" "test -f donate-site/samconfig.toml"
check "newsletter/samconfig.toml exists" "test -f newsletter/samconfig.toml"
echo ""

# Check Lambda code
echo -e "${BLUE}━━━ Lambda Functions ━━━${NC}"
check "ticket-service lambdas exist" "test -d ticket-service/lambdas && ls ticket-service/lambdas/*.py | wc -l | grep -qv '^0'"
check "events-site lambdas exist" "test -d events-site/lambdas && ls events-site/lambdas/*.py | wc -l | grep -qv '^0'"
check "donate-site lambdas exist" "test -d donate-site/lambdas && ls donate-site/lambdas/*.py | wc -l | grep -qv '^0'"
check "newsletter lambdas exist" "test -d newsletter/lambdas && ls newsletter/lambdas/*.py | wc -l | grep -qv '^0'"
echo ""

# Check dependencies
echo -e "${BLUE}━━━ Dependencies ━━━${NC}"
check "ticket-service/requirements.txt exists" "test -f ticket-service/requirements.txt"
echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Checks passed: $CHECKS_PASSED${NC}"
echo -e "${RED}Checks failed: $CHECKS_FAILED${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! Ready to deploy.${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Run: ./deploy-all.sh $ENV"
    echo "  2. Or deploy individual services:"
    echo "     cd ticket-service && sam build && sam deploy --config-env ${ENV/prod/default} --profile $AWS_PROFILE"
    echo ""
    exit 0
else
    echo -e "${RED}❌ Some checks failed. Please fix the issues above before deploying.${NC}"
    echo ""

    if ! command -v sam &> /dev/null; then
        echo -e "${YELLOW}Install SAM CLI:${NC}"
        echo "  brew install aws-sam-cli"
        echo ""
    fi

    if ! aws configure get aws_access_key_id --profile $AWS_PROFILE &> /dev/null; then
        echo -e "${YELLOW}Configure AWS profile:${NC}"
        echo "  aws configure --profile $AWS_PROFILE"
        echo ""
    fi

    if [ ! -f ".env.$ENV" ]; then
        echo -e "${YELLOW}Create environment file:${NC}"
        echo "  cp .env.example .env.$ENV"
        echo "  nano .env.$ENV  # Fill in your secrets"
        echo ""
    fi

    exit 1
fi
