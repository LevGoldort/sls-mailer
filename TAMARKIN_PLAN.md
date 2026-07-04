# Plan: tamarkin-site — Fundraising Sub-Project

## Context

A standalone fundraising site for comedian Tamarkin, hosted at `tamarkin.yallabalagan.org`. Collects donations via AllPay API (Tamarkin's own merchant account). Tracks progress toward 20,000 NIS goal. Fully isolated infrastructure — no shared tables, buckets, or stacks with the main yallabalagan ticket-service.

---

## Directory Structure

New top-level service directory: `tamarkin-site/`

```
tamarkin-site/
  template.yaml          # SAM stack
  samconfig.toml
  deploy.sh
  lambdas/
    donation-initiator.py   # POST /api/donate
    webhook-handler.py      # POST /webhook/allpay
    progress-handler.py     # GET /api/progress
  frontend/
    index.html
    success.html
    error.html
    tamarkin.jpg           # uploaded manually later
    js/
      accessibility-toolbar.js   # copied from ticket-service/frontend/static/js/
    css/
      accessibility-toolbar.css  # copied from ticket-service/frontend/static/css/
```

---

## AWS Resources (all isolated, prefixed `tamarkin-`)

| Resource | Name | Purpose |
|---|---|---|
| S3 Bucket | `tamarkin-donations-site` | Static site hosting |
| DynamoDB Table | `tamarkin-donations` | All donation records |
| Lambda | `DonationInitiatorFunction` | Creates AllPay payment session |
| Lambda | `WebhookHandlerFunction` | Confirms payment from AllPay webhook |
| Lambda | `ProgressHandlerFunction` | Returns collected total for progress bar |
| HttpApi | `TamarkinApi` | API Gateway routing |
| CloudFront | `TamarkinDistribution` | HTTPS + subdomain fronting S3 + API |
| ACM Certificate | (us-east-1) | `tamarkin.yallabalagan.org` TLS cert |

---

## DynamoDB Schema

Table: `tamarkin-donations`, PK: `donation_id` (HASH)

```
donation_id   str   "DON-{timestamp}-{uuid8}"
created_at    int   unix timestamp
name          str   donor's name
email         str   donor's email
amount        str   amount in NIS (e.g. "100")
needs_receipt bool  "Нужна кабала" checkbox value
status        str   "pending" | "completed"
payment_data  map   full AllPay webhook payload (for debugging)
```

No GSIs needed — progress query is a scan with filter `status = "completed"`.

---

## Lambda: DonationInitiatorFunction — `POST /api/donate`

1. Parse JSON body: `{name, email, amount, needs_receipt}`
2. Validate: amount is integer 10–50000, name/email non-empty
3. Generate `donation_id = "DON-{int(time.time())}-{uuid4()[:8]}"`
4. Write pending record to DynamoDB (`status: "pending"`)
5. Call AllPay API (`https://allpay.to/app/?show=getpayment&mode=api10`):
   - `login`: ALLPAY_LOGIN env var
   - `order_id`: donation_id
   - `items`: `[{name: "Пожертвование в поддержку Тамаркина", qty: 1, price: "100.00", vat: "Y"}]`
   - `currency`: "ILS"
   - `notifications_url`: `{API_URL}/webhook/allpay`
   - `return_url`: `https://tamarkin.yallabalagan.org/success.html`
   - `client_email`: email, `client_name`: name
   - `expire`: now + 30 minutes
   - `lang`: "RU"
   - `sign`: SHA256 signature using ALLPAY_API_KEY (same algorithm as `ticket-service/utils/payment.py` lines 208–260)
6. Return `{payment_url: "..."}` → frontend redirects browser

**Signature algorithm** (copy from ticket-service, don't import):
`SHA256(sorted_non_empty_values joined by ":" + ":" + api_key)`
Handles nested `items` array by flattening sub-keys in sorted order.

---

## Lambda: WebhookHandlerFunction — `POST /webhook/allpay`

1. Parse JSON body
2. Verify signature using ALLPAY_WEBHOOK_SECRET (same SHA256 algorithm, without items nesting)
3. Check `status == 1` (AllPay success code)
4. Extract `order_id` from payload
5. Update DynamoDB: `status → "completed"`, `payment_data → full payload`
6. Return HTTP 200

---

## Lambda: ProgressHandlerFunction — `GET /api/progress`

1. Scan `tamarkin-donations` with filter `status = "completed"`
2. Sum `amount` values
3. Return `{collected: 12500, goal: 20000, count: 47}`
4. CORS header: `Access-Control-Allow-Origin: *`

---

## Frontend

### `index.html` — Russian, LTR
- Comedian photo (`tamarkin.jpg`)
- Story text block (placeholder text, to be filled by user)
- **Progress bar**: JS fetches `GET /api/progress` on load, renders `collected / 20,000 ₪`
- **Donation form**:
  - Preset buttons: 50 / 100 / 200 / 500 ₪ (clicking sets amount)
  - Free-form input for custom amount (min 10 ₪)
  - Name field (required)
  - Email field (required)
  - Checkbox: "Мне нужна кабала на моё имя"
  - Submit → `POST /api/donate` → redirect to `payment_url`
- Vanilla JS, no framework, inline CSS (matches existing project patterns)
- **Footer** links (all pointing to main site):
  - `https://yallabalagan.org/terms.html`
  - `https://yallabalagan.org/privacy.html`
  - `https://yallabalagan.org/accessibility.html`
- **Accessibility toolbar**: include `css/accessibility-toolbar.css` + `js/accessibility-toolbar.js` (copied as-is from ticket-service); toolbar button injected by JS

### `success.html`
- "Спасибо за вашу поддержку!" message
- Link back to main page

### `error.html`
- "Что-то пошло не так" with link back

---

## SAM Template Parameters

```yaml
Parameters:
  AllPayLogin: {Type: String, NoEcho: true}
  AllPayApiKey: {Type: String, NoEcho: true}
  AllPayWebhookSecret: {Type: String, NoEcho: true}
  DomainName: {Type: String, Default: "tamarkin.yallabalagan.org"}
  CertificateArn: {Type: String}   # pre-created ACM cert in us-east-1
```

---

## deploy.sh

```bash
#!/bin/bash
set -e
PROFILE=${1:-yallabalagan-prod}
aws s3 sync frontend/ s3://tamarkin-donations-site/ --profile $PROFILE
sam build && sam deploy --profile $PROFILE
```

---

## Manual Steps (outside SAM)

1. **ACM Certificate**: Request `tamarkin.yallabalagan.org` in `us-east-1` (required for CloudFront), validate via DNS
2. **Route 53**: Add CNAME/Alias record `tamarkin.yallabalagan.org → CloudFront domain`
3. **AllPay credentials**: Tamarkin's merchant login/api_key/webhook_secret to be added to SAM params
4. **Photo**: Upload `tamarkin.jpg` to `frontend/` before deploy
5. **Story text**: Fill in placeholder text in `index.html`

---

## Verification

1. Deploy to prod: `./deploy.sh yallabalagan-prod`
2. Sync frontend to S3
3. Open `https://tamarkin.yallabalagan.org` → page loads, progress bar shows 0 / 20,000
4. Submit form with 100 ₪ → redirected to AllPay page
5. Complete test payment → redirected to success.html
6. Check DynamoDB `tamarkin-donations` → record with `status: completed`
7. Reload main page → progress bar shows 100 ₪ collected
8. Test `needs_receipt=true` → flag saved in DB
