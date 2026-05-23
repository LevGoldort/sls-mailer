# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Task Master AI Instructions
**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md

---

## Project Overview

**YallaBalagan** — serverless event ticketing platform on AWS (Israel market). Four independent services, each deployed separately via AWS SAM to isolated dev/prod AWS accounts.

| Service | Directory | Purpose |
|---------|-----------|---------|
| **Ticket Service** | `ticket-service/` | Core product — events, tickets, payments, scanner |
| **Events Site** | `events-site/` | Public static site (Notion-driven) |
| **Donate Site** | `donate-site/` | Crowdfunding with All-Pay |
| **Newsletter** | `newsletter/` | Email campaigns |

Primary work happens in `ticket-service/`.

---

## Commands

### Deploy

```bash
# Single service (from service directory)
cd ticket-service
sam build && sam deploy --config-env dev --profile yallabalagan-dev
sam build && sam deploy --profile yallabalagan-prod  # prod uses default config-env

# All services at once
./deploy-all.sh dev   # or prod
```

### Tests (ticket-service)

```bash
cd ticket-service
pip install -r requirements-test.txt

pytest                          # all tests
pytest tests/test_auth_jwt.py   # single file
pytest -m unit                  # unit tests only
pytest -m "not integration"     # skip integration tests
```

Tests use **moto** to mock AWS — no real AWS credentials needed for unit/integration tests.

---

## Ticket Service Architecture

### Lambda Functions

All lambdas live in `ticket-service/lambdas/`. The single `api-handler.py` handles all API Gateway requests — routing is done inside the handler via `path` + `httpMethod` matching.

Supporting lambdas triggered by EventBridge or SQS:
- `site-regenerator.py` — regenerates static HTML from DynamoDB on demand
- `email-sender.py` / `sms-sender.py` — triggered by SQS after payment
- `event-status-updater.py` — cron: marks events past, sends reminders
- `pending-orders-cleaner.py` — cron: cancels unpaid orders, restores seat counts

### Code Layout

```
ticket-service/
  lambdas/        # Lambda handlers
  models/         # Pydantic-style dataclasses: Event, Order, Location, User, Coupon
  utils/
    dynamodb.py   # DynamoDBClient — all DB operations
    auth.py       # AdminAuthenticator (API key, scanner token)
    auth_jwt.py   # JWT access/refresh token logic (PyJWT + HS256)
    auth_password.py  # Argon2 password hashing
    payment.py    # All-Pay integration + webhook parsing
    qr_generator.py
  repositories/   # (emerging layer, not fully used yet)
  admin/          # Static HTML admin panel, served from S3
  tests/
  template.yaml   # SAM infrastructure definition
```

### DynamoDB

Five tables (same names in dev and prod — isolation is per AWS account, not per name):

- `yallabalagan-events` — events with embedded ticket types and seating config
- `yallabalagan-orders` — orders with QR codes; GSIs: `EventIndex`, `EmailIndex`
- `yallabalagan-locations` — venue data
- `yallabalagan-coupons` — promo codes
- `yallabalagan-seat-reservations` — short-lived seat holds (TTL-based)

See `ticket-service/DYNAMODB_SCHEMA.md` for full key schema and GSI details.

### Auth

Currently two parallel auth systems coexist during migration:

| Method | Header | Scope |
|--------|--------|-------|
| Admin API key | `X-API-Key` | All admin endpoints |
| Scanner token | `X-Scanner-Token` + `X-Scanner-Event` | QR scan + search only; event-scoped, 8h TTL |
| JWT (in progress) | `Authorization: Bearer <token>` | Will replace API keys (see Phase 2) |

JWT secret read from `JWT_SECRET` env var — raises `RuntimeError` at Lambda init if missing.

### Payment Flow

`POST /api/orders` → order created (`status: pending`) → All-Pay URL returned → customer redirected → All-Pay POSTs to `/api/orders/webhook` → status updated, QR generated, email+SMS queued.

### Seated Venue Flow

Seat reservation uses DynamoDB conditional writes on `yallabalagan-seat-reservations`. `ConditionalCheckFailedException` means seat is taken. Reservations expire via TTL (10–15 min).

---

## Environments

| | Dev | Prod |
|-|-----|------|
| AWS Profile | `yallabalagan-dev` | `yallabalagan-prod` |
| SAM config-env | `dev` | `default` |
| Region | `eu-north-1` | `eu-north-1` |

---

## Active Work (Phase 2: User Management + RBAC)

Replacing API key auth with JWT + role-based access. See `.taskmaster/docs/user-management-prd.md` and tasks in `.taskmaster/tasks/tasks.json`.

- Roles: `admin` (full access) and `organizer` (own events only)
- Admin-only user creation; no self-registration
- Refresh tokens stored in DynamoDB with TTL
- Migration: existing events get assigned to first admin user

Infrastructure partially done: `models/user.py`, `utils/auth_jwt.py`, `utils/auth_password.py`, test files exist.

---

## Roadmap Phases

- **Phase 3**: Frontend redesign — fix mobile UX, evaluate React vs vanilla
- **Phase 4**: Consolidate events-site + donate-site into ticket-service; retire Notion/Telegram-bot admin
- **Phase 5**: Marketing — bonuses, loyalty program, promo codes
- **Phase 6**: Facebook Ads — partial branch exists, see `.taskmaster/docs/archive/facebook-ads-prd.md`
- **Future**: SaaS/multi-tenancy (`tenant_id` prefix in DynamoDB), CI/CD, multi-language
