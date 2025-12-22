# Plan: Update Production Deployment to Support Seated Venues

## Current Situation

- **DEV environment**: Works fully with seated venues (deployed via `deploy-dev.sh` using SAM)
- **PROD environment**: Does NOT exist yet
- **deploy-prod.sh**: Already exists and uses SAM, but never been run
- **Problem**: `template.yaml` uses `-${Environment}` suffix for all resources, but prod needs names WITHOUT suffix

## User Requirements

1. **Naming Strategy**: Prod resources should be named WITHOUT suffix (e.g., `yallabalagan-ticket-admin` NOT `yallabalagan-ticket-admin-prod`)
2. **Deployment Method**: Use SAM for prod (via existing `deploy-prod.sh`)
3. **Goal**: Deploy seated venues feature to production

## Solution

Update `template.yaml` to conditionally use suffix only for dev environment, and no suffix for prod.

## Implementation Steps

### Step 1: Update template.yaml Resource Names

**File**: `/Users/levgoldort/Documents/yallabalagan/ticket-service/template.yaml`

For EACH resource that has a name/TableName/BucketName/FunctionName, change from:
```yaml
TableName: !Sub yallabalagan-events-${Environment}
```

To use conditional logic:
```yaml
TableName: !If [IsProd, yallabalagan-events, !Sub yallabalagan-events-${Environment}]
```

**Resources to update:**

#### DynamoDB Tables (lines 115, 167, 196, 240, 275):
- EventsTable: `yallabalagan-events` (prod) vs `yallabalagan-events-dev`
- LocationsTable: `yallabalagan-locations` vs `yallabalagan-locations-dev`
- OrdersTable: `yallabalagan-orders` vs `yallabalagan-orders-dev`
- CouponsTable: `yallabalagan-coupons` vs `yallabalagan-coupons-dev`
- **SeatReservationsTable**: `yallabalagan-seat-reservations` vs `yallabalagan-seat-reservations-dev`
  - ⚠️ IMPORTANT: This matches existing prod table name from DYNAMODB_SCHEMA.md

#### S3 Buckets (lines 314, 352, 382):
- MediaBucket: `yallabalagan-ticket-media` vs `yallabalagan-ticket-media-dev`
- FrontendBucket: `yallabalagan-tickets-frontend` vs `yallabalagan-tickets-frontend-dev`
- AdminBucket: `yallabalagan-ticket-admin` vs `yallabalagan-ticket-admin-dev`

#### Lambda Functions (lines 416, 461, 493, 515, 532):
- TicketApiFunction: `yallabalagan-ticket-api` vs `yallabalagan-ticket-api-dev`
- SiteRegeneratorFunction: `yallabalagan-site-regenerator` vs `yallabalagan-site-regenerator-dev`
- EmailSenderFunction: `yallabalagan-email-sender` vs `yallabalagan-email-sender-dev`
- EventStatusUpdaterFunction: `yallabalagan-event-status-updater` vs `yallabalagan-event-status-updater-dev`
- **PendingOrdersCleanerFunction**: `yallabalagan-pending-orders-cleaner` vs `yallabalagan-pending-orders-cleaner-dev`

#### Lambda Layer (line 554):
- SiteTemplatesLayer: `yallabalagan-site-templates` vs `yallabalagan-site-templates-dev`

#### Environment Variables (lines 98, 455)
- EMAIL_SENDER_LAMBDA: Update to use conditional naming
- Lambda invoke ARNs: Update to use conditional naming

### Step 2: Update Outputs Section

**File**: `/Users/levgoldort/Documents/yallabalagan/ticket-service/template.yaml`

Update Export Names (lines 612, 618, 624, 630, 635, 640, 648, 654):
```yaml
Export:
  Name: !If [IsProd, TicketApiUrl, !Sub ${Environment}-TicketApiUrl]
```

### Step 3: Verify deploy-prod.sh Configuration ✅

**File**: `/Users/levgoldort/Documents/yallabalagan/ticket-service/deploy-prod.sh`

**Current config** (lines 32-42):
- ✅ Uses `--config-env default` (CORRECT - prod config is in `[default]` section of samconfig.toml)
- ✅ Has all required parameters loaded from .env.prod

**Status**: No changes needed - already correctly configured

### Step 4: Verify samconfig.toml Configuration ✅

**File**: `/Users/levgoldort/Documents/yallabalagan/ticket-service/samconfig.toml`

**Current config**:
- ✅ `[default.deploy.parameters]` for prod (lines 6-20)
- ✅ `[dev.deploy.parameters]` for dev (lines 32-46)
- ✅ stack_name: `yallabalagan-ticket-service-prod`
- ✅ Environment=prod parameter

**Status**: Already correctly configured - no changes needed

### Step 5: Verify .env.prod Exists ✅

**File**: `/Users/levgoldort/Documents/yallabalagan/.env.prod`

**Status**: ✅ File exists and should contain:
- PAYMENT_MODE
- SENDER_EMAIL
- ALLPAY_LOGIN
- ALLPAY_WEBHOOK_SECRET
- ALLPAY_API_KEY
- ALLPAY_USE_API
- PAYMENT_EXPIRE_MINUTES

### Step 6: Test Deployment

Run the deployment:
```bash
cd ticket-service
./deploy-prod.sh
```

This will:
1. Build SAM application
2. Create all missing prod resources:
   - DynamoDB tables (including SeatReservationsTable with TTL)
   - S3 buckets
   - Lambda functions (all 5, including pending-orders-cleaner)
   - API Gateway
   - EventBridge schedules
   - IAM policies
3. Sync admin and frontend files to S3

## Critical Files

1. `/Users/levgoldort/Documents/yallabalagan/ticket-service/template.yaml` - Main changes
2. `/Users/levgoldort/Documents/yallabalagan/ticket-service/deploy-prod.sh` - Minor fix
3. `/Users/levgoldort/Documents/yallabalagan/ticket-service/samconfig.toml` - Add prod config
4. `/Users/levgoldort/Documents/yallabalagan/.env.prod` - Verify exists

## What This Enables

After deployment, prod will have:
- ✅ SeatReservationsTable with TTL for temporary seat holds
- ✅ All 5 Lambda functions (including pending-orders-cleaner)
- ✅ API Gateway with seating endpoints
- ✅ EventBridge schedules (10 min for event-status-updater, 5 min for pending-orders-cleaner)
- ✅ Proper IAM permissions for seated venue operations

## Deployment Verification

After running `deploy-prod.sh`, verify:
```bash
# Check tables exist
aws dynamodb describe-table --table-name yallabalagan-seat-reservations --region eu-north-1

# Check Lambda functions
aws lambda list-functions --region eu-north-1 | grep yallabalagan

# Check API Gateway
aws apigatewayv2 get-apis --region eu-north-1

# Test seating endpoint
curl https://<api-id>.execute-api.eu-north-1.amazonaws.com/prod/api/events/<event-id>/seating-map
```

## Alternative: deploy-all.sh (NOT RECOMMENDED)

If user insists on using deploy-all.sh instead of SAM:
1. Create SeatReservationsTable manually via AWS CLI
2. Create deploy-pending-orders-cleaner.sh script
3. Create API Gateway manually
4. Set up EventBridge schedules manually
5. Update all Lambda environment variables
6. Update deploy-all.sh to call pending-orders-cleaner deploy

**Why SAM is better**: Automates all of the above + ensures consistency + easier rollback.
