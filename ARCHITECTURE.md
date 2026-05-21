# YallaBalagan — Architecture

Serverless event ticketing platform on AWS. Two active services sharing one AWS account per environment (prod/dev).

---

## Services Overview

| Service | Directory | Purpose |
|---------|-----------|---------|
| **Ticket Service** | `ticket-service/` | Core product — events, tickets, payments, scanner, public site |
| **Newsletter** | `newsletter/` | Email campaign management (Mailchimp alternative) |

Each service has its own `template.yaml`, `samconfig.toml`, and is deployed independently.

> **Archived:** `events-site/` (Notion-driven event listings) and `donate-site/` (crowdfunding) have been consolidated into Ticket Service. Their data was migrated via `scripts/migrate_from_events_site.py` and `scripts/migrate_from_donate_site.py`. The legacy SAM stacks can be deleted once the migration is verified on production.

---

## Ticket Service (Primary Product)

### Lambda Functions

| Function | Handler | Trigger | Purpose |
|----------|---------|---------|---------|
| `yallabalagan-ticket-api` | `api-handler.py` | API Gateway `ANY /api/{proxy+}` | All public + admin API endpoints |
| `yallabalagan-user-api` | `user-api-handler.py` | API Gateway `/api/auth/*`, `/api/users/*` | JWT auth (login/refresh/logout) + user management |
| `yallabalagan-site-regenerator` | `site-regenerator.py` | EventBridge / manual | Generates static HTML from DynamoDB |
| `yallabalagan-email-sender` | `email-sender.py` | SQS / direct invoke | Sends ticket confirmation emails via SES |
| `yallabalagan-sms-sender` | `sms-sender.py` | SQS / direct invoke | Sends SMS via Active Trail |
| `yallabalagan-event-status-updater` | `event-status-updater.py` | EventBridge cron | Marks events as past, triggers reminders |
| `yallabalagan-pending-orders-cleaner` | `pending-orders-cleaner.py` | EventBridge cron | Cancels unpaid orders, restores ticket counts |

### DynamoDB Tables

| Table | Key Schema | GSIs | Purpose |
|-------|-----------|------|---------|
| `yallabalagan-events` | PK, SK | GSI1, DateIndex, SlugIndex, OwnerIndex | Events with ticket types, seat allocation |
| `yallabalagan-locations` | PK, SK | — | Venue data with coordinates, media |
| `yallabalagan-orders` | PK, SK | EventIndex (event_id+created_at), EmailIndex (email+created_at) | Customer orders and QR codes |
| `yallabalagan-coupons` | PK, SK | — | Discount/promo codes |
| `yallabalagan-seat-reservations` | event_id (HASH), seat_id (RANGE) | ExpirationIndex | Temporary seat holds during checkout (TTL-based) |
| `yallabalagan-users` | PK (`USER#<id>`), SK (`PROFILE`) | EmailIndex (email), TenantIndex (tenant_id+status) | Admin and organizer users; RATELIMIT# prefix for rate limiting |
| `yallabalagan-refresh-tokens` | PK (`TOKEN#<token>`), SK (`META`) | UserIndex (user_id+created_at) | JWT refresh tokens with TTL-based expiry |
| `yallabalagan-performers` | PK (`PERFORMER#<id>`), SK (`METADATA`) | TenantIndex, SlugIndex | Performer profiles (artists, hosts) |
| `yallabalagan-products` | PK (`PRODUCT#<id>`), SK (`METADATA`) | PerformerIndex, StatusIndex, SlugIndex | Merchandise and group products |
| `yallabalagan-merchandise-orders` | PK, SK | — | Product purchase orders |

> Table names have no environment suffix — dev and prod are isolated via separate AWS accounts, not naming conventions.

### S3 Buckets

- **Media bucket** — event/location images uploaded by admin
- **Frontend bucket** — generated static HTML site (public)
- **Admin bucket** — admin panel HTML/JS files

### Auth

Three credential types in order of precedence:

| Credential | Header | Scope |
|-----------|--------|-------|
| JWT Bearer | `Authorization: Bearer <token>` | All admin + user endpoints (primary) |
| Admin API key | `X-API-Key` | All admin endpoints (legacy, deprecated) |
| Scanner token | `X-Scanner-Token` + `X-Scanner-Event` | `/api/orders/verify/*` and `/api/scanner/search` only |

**JWT flow** (`user-api-handler.py`):
1. `POST /api/auth/login` → returns `access_token` (15 min) + `refresh_token` (30 days, stored in DynamoDB)
2. `POST /api/auth/refresh` → validates refresh token, issues new access token
3. `POST /api/auth/logout` → deletes refresh token from DynamoDB
4. Admin panel auto-refreshes access token every 60 s when nearing expiry

**Roles:** `admin` (full access) · `organizer` (own events only, future RBAC)

**Migration bridge:** `utils/auth.py` `verify_admin_key()` also accepts valid JWT admin tokens, so legacy handlers that check `X-API-Key` work transparently with Bearer tokens until migrated.

**Rate limiting:** login endpoint enforces 10 attempts / 5 min per IP via DynamoDB atomic counter (`RATELIMIT#<ip>` key in `yallabalagan-users`, TTL-based reset).

**Security headers** on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=63072000`.

Scanner tokens are event-scoped and expire 8 hours after event start time.

### API Gateway Routing

One HTTP API (`yallabalagan-ticket-service-{env}`), two Lambda integrations:

```
ANY /api/auth/{proxy+}   → yallabalagan-user-api
ANY /api/auth            → yallabalagan-user-api
ANY /api/users/{proxy+}  → yallabalagan-user-api
ANY /api/users           → yallabalagan-user-api
ANY /api/{proxy+}        → yallabalagan-ticket-api  (catch-all)
```

Routes for `user-api` are wired by `deploy.sh` via AWS CLI (not SAM), idempotently on every deploy.

### Key API Endpoints

```
# Public
GET  /api/events
GET  /api/events/{id}
GET  /api/events/{slug}
GET  /api/locations
GET  /api/locations/{id}
POST /api/orders                    — create order, returns All-Pay redirect URL
GET  /api/orders/{id}
POST /api/orders/webhook            — All-Pay payment webhook

# Scanner (X-Scanner-Token or X-API-Key)
POST /api/orders/verify/{code}      — scan QR code, mark as checked in
GET  /api/scanner/search            — search orders by name/email/phone

# Auth (user-api-handler.py)
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
POST /api/auth/change-password

# User management — admin only (user-api-handler.py)
GET  /api/users
POST /api/users
GET  /api/users/{id}
PUT  /api/users/{id}
DELETE /api/users/{id}              — deactivates (sets status=inactive)
POST /api/users/{id}/reset-password

# Admin (JWT Bearer or X-API-Key)
POST/PUT/DELETE /api/events/{id}
POST/PUT/DELETE /api/locations/{id}
GET  /api/orders                    — list all orders
GET  /api/admin/facebook-ads/*      — Facebook Ads integration (feature branch)
```

### Admin Panel Pages

Located in `ticket-service/admin/`, served from S3. Auth state is managed by `auth.js` (access/refresh tokens in `localStorage`). Shared utilities in `shared.js`.

| File | Purpose |
|------|---------|
| `login.html` | JWT login form |
| `index.html` | Dashboard with stats + site regeneration |
| `events.html` | Events list |
| `event-edit.html` | Create/edit event, seating map, scanner password, FB ads |
| `orders.html` | Orders list and management |
| `locations.html` | Locations list |
| `location-edit.html` | Create/edit location |
| `coupons.html` | Coupon management |
| `users.html` | User management (admin only, hidden from organizers) |
| `scanner.html` | **Ralphy** — door scanner for volunteers (mobile) |
| `analytics.html` | Sales analytics |
| `sms-blast.html` | Bulk SMS to event attendees |

### Payment Flow

1. Customer submits order form → `POST /api/orders` → order created with `status: pending`
2. Response contains All-Pay payment URL → customer redirected
3. All-Pay posts to `/api/orders/webhook` on completion
4. Lambda: updates order status, generates QR codes, triggers email + SMS

### Seat Reservation Flow (seated venues)

1. Customer selects seats → `POST /api/seats/reserve` → DynamoDB conditional write
2. Reservation held for 10-15 min via TTL
3. On payment completion → seats permanently assigned to order
4. `ConditionalCheckFailedException` = seat taken → return conflict error

---

## Environments

| | Dev | Prod |
|-|-----|------|
| AWS Profile | `yallabalagan-dev` | `yallabalagan-prod` |
| SAM config env | `dev` | `default` |
| Resource naming | same names, isolated by account | same names, isolated by account |
| Region | `eu-north-1` | `eu-north-1` |

Deploy single service (full — rebuilds all Lambdas):
```bash
cd ticket-service
sam build && sam deploy --config-env dev --profile yallabalagan-dev
./deploy.sh dev
```

Deploy admin panel only (fast — S3 sync, no Lambda rebuild):
```bash
cd ticket-service
./deploy.sh dev admin
```

Deploy all services:
```bash
./deploy-all.sh dev  # or prod
```

`deploy.sh` also wires the `user-api` API Gateway routes on every run (idempotent). The API ID is derived from `API_URL` in `.env.dev` / `.env.prod`.

---

## Integrations

| Integration | Used by | Purpose |
|------------|---------|---------|
| **All-Pay** | Ticket, Donate | Payment processing and refunds |
| **AWS SES** | Ticket, Newsletter | Transactional emails |
| **Active Trail** | Ticket | SMS (ticket confirmation, reminders) |
| **Notion** | Events Site | Content source for public event listings |
| **Facebook Ads API** | Ticket (feature branch) | Launch ad campaigns from admin panel |

---

## Planned / In Progress

- **Organizer RBAC** — `organizer` role is issued and stored, but row-level filtering (own events only) is not enforced yet in `api-handler.py` route handlers.
- **Full JWT migration** — 21 route handlers in `api-handler.py` still use the legacy `get_admin_authenticator()` pattern. A bridge in `utils/auth.py` makes them accept JWT tokens transparently in the meantime.
- **Frontend redesign** — fix mobile UX; evaluate React vs vanilla (Phase 3).
- **Service consolidation** — merge events-site + donate-site into ticket-service; retire Notion/Telegram-bot admin (Phase 4).
- **SaaS / multi-tenancy** — `tenant_id` prefix in DynamoDB, payment provider abstraction, per-tenant sub-users (Phase 5+).
