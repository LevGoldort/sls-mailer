# Roadmap

Updated May 2026.

---

## Phase 1: Dev/Prod Environment ✅

- Separate AWS accounts for dev and prod
- Single parameterized `deploy.sh dev|prod` script
- Dev environment working. Prod deploy via new script not yet validated.

---

## Phase 2: User Management + RBAC

Replace API key auth with proper user system.

- JWT-based auth (PyJWT + Argon2)
- Roles: Admin (full access) and Organizer (own events only)
- Admin-only user creation and password reset
- Refresh tokens in DynamoDB with TTL
- Frontend: login page, auth.js, users management page
- Migration: existing events assigned to first admin

PRD and task breakdown: `.taskmaster/docs/user-management-prd.md`, tasks in `.taskmaster/tasks/tasks.json`

---

## Phase 3: Frontend Redesign

Current vanilla HTML/JS has UX issues — poor mobile layout, images not fitting, no animations.

- Fix known mobile issues (images, layout)
- Add animations and visual polish
- Evaluate React migration vs staying on vanilla (tradeoff: complexity vs component reuse as app grows)

---

## Phase 4: Consolidate Events Site + Donate Site into Ticket Service

Both services are currently minimal — Notion as database, Telegram bot as admin, hard to maintain.

- Migrate events-site data model into ticket-service DynamoDB
- Migrate donate-site into ticket-service
- Replace Telegram bot admin with the existing HTML admin panel
- Decommission separate Notion integrations

---

## Phase 5: Marketing & Loyalty

- Automatic bonuses on ticket purchases
- Blogger/influencer loyalty program
- Promo codes (infrastructure partially exists via coupons table)

---

## Phase 6: Facebook Ads Integration

Partially implemented on a separate feature branch (`facebook-ads` or similar). Goals:

- Launch ad campaigns directly from event editor
- Geo-targeting around event location (40km radius)
- Pause/resume campaigns from admin panel
- Evaluate reusing existing branch code vs rewrite

PRD archived at `.taskmaster/docs/archive/facebook-ads-prd.md`

---

## Future / Unscheduled

- SaaS / multi-tenancy (tenant_id in DynamoDB, payment provider abstraction, per-tenant RBAC)
- CI/CD with GitHub Actions
- Analytics dashboard
- Multi-language support (Hebrew, English)
