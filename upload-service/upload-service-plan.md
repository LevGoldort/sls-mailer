# File Transfer Service - Project Plan

## Project Overview

Build a serverless file transfer service where users can upload large video files (up to 600GB/month) with password protection, generate download links, and share them securely.

**Tech Stack:**
- Frontend: Static HTML/JS hosted on AWS S3
- Backend API: Cloudflare Workers
- Storage: Cloudflare R2
- Metadata: Cloudflare KV (optional)
- CDN: Cloudflare (built-in)

**Key Features:**
- Password-protected uploads
- Token-based or password-protected downloads
- Admin panel for file management
- Support for large video files
- Fast global delivery via CDN

---

## Architecture

```
AWS S3 Static Site → Cloudflare Workers API → R2 Storage
                         ↓
                    Generate URLs
                         ↓
                  Users Download Files
```

**Endpoints:**
- `POST /api/upload` - Upload file with password
- `GET /api/download/:fileId` - Download file with token/password
- `GET /api/admin/list` - List all files (admin only)
- `DELETE /api/admin/:fileId` - Delete file (admin only)

---

## Environment Variables Needed

```
UPLOAD_PASSWORD=your_upload_password
DOWNLOAD_PASSWORD=your_download_password  
ADMIN_KEY=your_admin_secret_key
TOKEN_SECRET=random_secret_for_hmac
R2_BUCKET_NAME=your-bucket-name
DOMAIN=yourdomain.com
```

---

## Tasks

### Phase 1: Setup & Configuration

#### Task 1.1: Initialize Cloudflare Workers Project
**Description:** Set up Cloudflare Workers project with Wrangler CLI
**Acceptance Criteria:**
- [ ] Wrangler installed locally
- [ ] New Workers project created with `wrangler init`
- [ ] `wrangler.toml` configured with correct account_id and project name
- [ ] Test deployment works with `wrangler deploy`

**Commands:**
```bash
npm install -g wrangler
wrangler init file-transfer-api
cd file-transfer-api
wrangler deploy
```

---

#### Task 1.2: Create R2 Bucket
**Description:** Create R2 bucket for file storage via Wrangler
**Acceptance Criteria:**
- [ ] R2 bucket created with name `file-transfer-storage`
- [ ] Bucket binding added to `wrangler.toml`
- [ ] Verify bucket accessible from Worker

**Commands:**
```bash
wrangler r2 bucket create file-transfer-storage
```

**wrangler.toml addition:**
```toml
[[r2_buckets]]
binding = "FILE_STORAGE"
bucket_name = "file-transfer-storage"
```

---

#### Task 1.3: Configure Environment Variables
**Description:** Set up all required secrets in Cloudflare Workers
**Acceptance Criteria:**
- [ ] All secrets added via `wrangler secret put`
- [ ] Secrets accessible in Worker via `env.VARIABLE_NAME`
- [ ] Test secret retrieval in Worker

**Commands:**
```bash
wrangler secret put UPLOAD_PASSWORD
wrangler secret put DOWNLOAD_PASSWORD
wrangler secret put ADMIN_KEY
wrangler secret put TOKEN_SECRET
```

---

### Phase 2: Backend - Cloudflare Workers API

#### Task 2.1: Implement Upload Endpoint
**Description:** Create POST /upload endpoint with password auth and R2 upload
**Acceptance Criteria:**
- [ ] Accept FormData with `password` and `file` fields
- [ ] Validate upload password
- [ ] Generate unique fileId (UUID)
- [ ] Stream file to R2 bucket with fileId as key
- [ ] Store metadata (filename, size, uploadedAt) in R2 custom metadata
- [ ] Generate HMAC token for download: `HMAC(fileId + TOKEN_SECRET)`
- [ ] Return JSON with `downloadUrl` and `fileId`
- [ ] Handle CORS headers for cross-origin requests
- [ ] Handle errors (wrong password, upload failure, file too large)

**Response Format:**
```json
{
  "success": true,
  "fileId": "abc-123-def",
  "downloadUrl": "https://api.yourdomain.com/download/abc-123-def?token=xyz",
  "filename": "video.mp4",
  "size": 524288000
}
```

---

#### Task 2.2: Implement Download Endpoint
**Description:** Create GET /download/:fileId endpoint with token/password verification
**Acceptance Criteria:**
- [ ] Accept fileId from URL path
- [ ] Accept token from query param OR password from header/query
- [ ] Verify token: `HMAC(fileId + TOKEN_SECRET) === token`
- [ ] OR verify download password matches
- [ ] Fetch file from R2 by fileId
- [ ] Return 404 if file not found
- [ ] Stream file to response with correct headers:
  - `Content-Type` from R2 metadata
  - `Content-Disposition: attachment; filename="original_name"`
  - `Content-Length` from R2 object size
  - `Cache-Control: public, max-age=3600` for CDN caching
- [ ] Handle Range requests for resumable downloads
- [ ] Return 401 for invalid token/password

---

#### Task 2.3: Implement Admin List Endpoint
**Description:** Create GET /admin/list endpoint to list all files
**Acceptance Criteria:**
- [ ] Verify admin key in query param: `?key=ADMIN_KEY`
- [ ] List all objects in R2 bucket using `R2.list()`
- [ ] For each object, extract metadata (filename, size, uploadedAt)
- [ ] Return JSON array with file info
- [ ] Include generated download URLs for each file
- [ ] Return 401 if admin key invalid

**Response Format:**
```json
[
  {
    "fileId": "abc-123",
    "filename": "video.mp4",
    "size": 524288000,
    "uploadedAt": "2025-12-22T10:00:00Z",
    "downloadUrl": "https://api.yourdomain.com/download/abc-123?token=xyz"
  }
]
```

---

#### Task 2.4: Implement Admin Delete Endpoint
**Description:** Create DELETE /admin/:fileId endpoint to delete files
**Acceptance Criteria:**
- [ ] Verify admin key in query param or header
- [ ] Delete object from R2: `R2.delete(fileId)`
- [ ] Return success response
- [ ] Return 404 if file not found
- [ ] Return 401 if admin key invalid

---

#### Task 2.5: Add CORS Support
**Description:** Handle OPTIONS preflight requests and add CORS headers
**Acceptance Criteria:**
- [ ] Handle OPTIONS method for all endpoints
- [ ] Return CORS headers on all responses:
  - `Access-Control-Allow-Origin: *` (or specific domain)
  - `Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS`
  - `Access-Control-Allow-Headers: Content-Type, Authorization`
- [ ] Test cross-origin requests from S3 static site

---

#### Task 2.6: Add Rate Limiting (Optional)
**Description:** Implement basic rate limiting to prevent abuse
**Acceptance Criteria:**
- [ ] Use Cloudflare KV to track request counts per IP
- [ ] Limit upload requests to 10 per hour per IP
- [ ] Limit download requests to 100 per hour per IP
- [ ] Return 429 Too Many Requests when limit exceeded
- [ ] Reset counters after time window

---

### Phase 3: Frontend - S3 Static Site

#### Task 3.1: Create Upload Page HTML
**Description:** Build upload.html with password input and file selector
**Acceptance Criteria:**
- [ ] Clean, responsive design
- [ ] Password input field (type="password")
- [ ] File input field (accept video formats)
- [ ] Upload button
- [ ] Progress indicator (spinner or progress bar)
- [ ] Result display area for download link
- [ ] Copy-to-clipboard button for download URL
- [ ] Error message display area
- [ ] Mobile-friendly responsive layout

---

#### Task 3.2: Create Upload JavaScript Logic
**Description:** Implement upload.js for handling file uploads
**Acceptance Criteria:**
- [ ] Read password and file from form inputs
- [ ] Validate inputs (password not empty, file selected)
- [ ] Create FormData with password and file
- [ ] POST to `https://api.yourdomain.com/upload` using fetch API
- [ ] Show upload progress (if possible with fetch)
- [ ] Handle successful response:
  - Display download URL
  - Enable copy-to-clipboard
  - Show success message
- [ ] Handle errors:
  - Wrong password (401)
  - File too large (413)
  - Network errors
  - Display user-friendly error messages
- [ ] Reset form after successful upload

**Key Functions:**
- `validateForm()` - Check inputs before upload
- `uploadFile(password, file)` - Execute upload via fetch
- `displaySuccess(data)` - Show download link
- `displayError(message)` - Show error message
- `copyToClipboard(url)` - Copy download URL

---

#### Task 3.3: Create Download Page (Optional)
**Description:** Build download.html for password-protected downloads
**Acceptance Criteria:**
- [ ] Extract fileId from URL path
- [ ] If no token in URL, show password form
- [ ] Submit password to Worker
- [ ] On success, trigger file download
- [ ] Show download progress if possible
- [ ] Handle errors (wrong password, file not found)

---

#### Task 3.4: Create Admin Panel HTML
**Description:** Build admin.html for managing files
**Acceptance Criteria:**
- [ ] Admin key input (or store in localStorage after first entry)
- [ ] "Load Files" button
- [ ] Table displaying all files:
  - FileId
  - Filename
  - Size (formatted)
  - Upload date
  - Download URL (with copy button)
  - Delete button
- [ ] Confirm before delete
- [ ] Refresh list after delete
- [ ] Error handling for unauthorized access

---

#### Task 3.5: Create Admin JavaScript Logic
**Description:** Implement admin.js for file management
**Acceptance Criteria:**
- [ ] Fetch file list from `/admin/list?key=ADMIN_KEY`
- [ ] Parse and display files in table
- [ ] Format file sizes (bytes → MB/GB)
- [ ] Format dates nicely
- [ ] Implement copy-to-clipboard for download URLs
- [ ] Implement delete file functionality:
  - Confirm dialog
  - DELETE request to `/admin/:fileId?key=ADMIN_KEY`
  - Remove from table on success
- [ ] Handle errors (unauthorized, network issues)

---

#### Task 3.6: Style with CSS
**Description:** Create styles.css for all pages
**Acceptance Criteria:**
- [ ] Consistent design across all pages
- [ ] Responsive layout (mobile-first)
- [ ] Clean, modern UI
- [ ] Button hover states
- [ ] Loading states/spinners
- [ ] Error/success message styling
- [ ] Table styling for admin panel
- [ ] Copy button styling

---

#### Task 3.7: Deploy Static Site to S3
**Description:** Upload HTML/CSS/JS files to S3 bucket
**Acceptance Criteria:**
- [ ] S3 bucket created (or use existing)
- [ ] Static website hosting enabled
- [ ] Upload all files: upload.html, admin.html, download.html, app.js, admin.js, styles.css
- [ ] Set correct permissions (public read)
- [ ] Configure bucket policy for public access
- [ ] Test access via S3 website endpoint
- [ ] (Optional) Configure custom domain with Route53

**Commands:**
```bash
aws s3 sync ./frontend s3://your-bucket-name --acl public-read
aws s3 website s3://your-bucket-name --index-document upload.html
```

---

### Phase 4: Testing & Deployment

#### Task 4.1: End-to-End Upload Test
**Description:** Test complete upload flow from frontend to R2
**Test Cases:**
- [ ] Upload small file (< 10MB) with correct password → Success
- [ ] Upload large file (> 100MB) with correct password → Success
- [ ] Upload with wrong password → 401 error
- [ ] Upload without password → 401 error
- [ ] Upload without file → Error message
- [ ] Verify file appears in R2 bucket
- [ ] Verify download URL generated correctly

---

#### Task 4.2: End-to-End Download Test
**Description:** Test complete download flow
**Test Cases:**
- [ ] Download with valid token → File downloads
- [ ] Download with valid password → File downloads
- [ ] Download with invalid token → 401 error
- [ ] Download with wrong password → 401 error
- [ ] Download non-existent fileId → 404 error
- [ ] Test resume download (Range requests)
- [ ] Verify correct filename on download
- [ ] Test download speed from different locations

---

#### Task 4.3: Admin Panel Test
**Description:** Test admin functionality
**Test Cases:**
- [ ] List files with correct admin key → Shows all files
- [ ] List files with wrong admin key → 401 error
- [ ] Delete file → File removed from R2 and list
- [ ] Copy download URL → Copies correctly
- [ ] Verify file metadata displayed correctly

---

#### Task 4.4: Performance Testing
**Description:** Test system under load
**Test Cases:**
- [ ] Upload 10 files concurrently → All succeed
- [ ] Download same file 100 times → Fast delivery via CDN
- [ ] Monitor R2 operation costs
- [ ] Monitor Worker execution time
- [ ] Test with files at max size limit
- [ ] Verify CDN caching works (check cache HIT/MISS headers)

---

#### Task 4.5: Production Deployment
**Description:** Deploy to production with custom domain
**Acceptance Criteria:**
- [ ] Custom domain configured for Workers: `api.yourdomain.com`
- [ ] SSL certificate active
- [ ] Update frontend API URLs to production domain
- [ ] Re-deploy static site to S3 with production URLs
- [ ] Verify CORS headers work with production domains
- [ ] Set all production secrets in Workers
- [ ] Enable Cloudflare firewall rules (optional)
- [ ] Set up monitoring/alerts

---

### Phase 5: Enhancements (Optional)

#### Task 5.1: Add File Expiration
**Description:** Automatically delete files after N days
**Acceptance Criteria:**
- [ ] Store uploadedAt timestamp in R2 metadata
- [ ] Create Cloudflare Worker Cron job (scheduled task)
- [ ] Cron runs daily, lists all files
- [ ] Delete files older than 30 days
- [ ] Log deletions

---

#### Task 5.2: Add Download Counter
**Description:** Track how many times each file has been downloaded
**Acceptance Criteria:**
- [ ] Use Cloudflare KV to store download counts
- [ ] Increment counter on each successful download
- [ ] Display download count in admin panel
- [ ] Optional: limit downloads per file (e.g., max 10 downloads)

---

#### Task 5.3: Add Email Notifications
**Description:** Send email when file is uploaded
**Acceptance Criteria:**
- [ ] Integrate with email service (SendGrid, Mailgun, etc.)
- [ ] Send email to admin on successful upload
- [ ] Include filename, size, download URL in email
- [ ] Handle email sending errors gracefully

---

#### Task 5.4: Add Multi-file Upload
**Description:** Allow uploading multiple files at once
**Acceptance Criteria:**
- [ ] Update frontend to accept multiple files
- [ ] Upload files sequentially or in parallel
- [ ] Show progress for each file
- [ ] Return multiple download URLs
- [ ] Handle partial failures (some files succeed, some fail)

---

#### Task 5.5: Migration to Cloudflare Pages
**Description:** Move static site from S3 to Cloudflare Pages
**Acceptance Criteria:**
- [ ] Create Cloudflare Pages project
- [ ] Configure Git integration (GitHub/GitLab)
- [ ] Deploy frontend to Pages
- [ ] Configure `_routes.json` to route API calls to Workers
- [ ] Update domain DNS to point to Pages
- [ ] Remove S3 hosting
- [ ] Test everything works on Pages

---

## Project Completion Checklist

- [ ] All Phase 1 tasks complete (Setup)
- [ ] All Phase 2 tasks complete (Backend API)
- [ ] All Phase 3 tasks complete (Frontend)
- [ ] All Phase 4 tasks complete (Testing & Deployment)
- [ ] System deployed to production
- [ ] Documentation written
- [ ] Admin trained on using admin panel
- [ ] Costs monitored and within budget ($5-7/month)

---

## Quick Start Commands

```bash
# Initialize project
wrangler init file-transfer-api
cd file-transfer-api

# Create R2 bucket
wrangler r2 bucket create file-transfer-storage

# Add secrets
wrangler secret put UPLOAD_PASSWORD
wrangler secret put DOWNLOAD_PASSWORD
wrangler secret put ADMIN_KEY
wrangler secret put TOKEN_SECRET

# Deploy Worker
wrangler deploy

# Deploy frontend to S3
aws s3 sync ./frontend s3://your-bucket-name --acl public-read
```

---

## Useful Resources

- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Cloudflare R2 Docs](https://developers.cloudflare.com/r2/)
- [Wrangler CLI Docs](https://developers.cloudflare.com/workers/wrangler/)
- [R2 Bindings](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Workers CORS](https://developers.cloudflare.com/workers/examples/cors-header-proxy/)

---

## Cost Tracking

Track monthly costs:
- R2 Storage: ___ GB × $0.015 = $___
- R2 Operations: Class A ___ , Class B ___  = $___
- Workers Requests: ___ (free tier: 100k/day)
- S3 Hosting: $___ (if staying on S3)

**Expected Total: $5-7/month**  