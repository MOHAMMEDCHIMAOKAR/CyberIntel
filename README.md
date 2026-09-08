# CyberIntel

> A lightweight cybersecurity news intelligence dashboard that aggregates security news from trusted RSS sources and presents it through a clean, centralized web interface.

CyberIntel is built with a deliberately simple architecture using **Vanilla HTML/CSS/JavaScript**, **Python Flask**, **RSS feeds**, and **Supabase PostgreSQL**.

---

## Overview

Cybersecurity news is distributed across many publications and security research websites. CyberIntel provides a single dashboard for collecting and viewing the latest security-related articles from configured sources.

The application:

- Aggregates cybersecurity news through RSS(Really Simple Syndication) feeds.
- Stores processed articles in Supabase PostgreSQL.
- Displays current articles through a responsive web dashboard.
- Extracts article images when RSS feeds do not provide them.
- Provides source and health APIs.
- Automatically removes articles beyond the configured retention period.
- Includes security hardening for outbound requests and API access.
- Keeps Supabase credentials strictly server-side.

---

## Features

### News Aggregation

- RSS-based news ingestion.
- Multiple configurable cybersecurity sources.
- Duplicate-safe article storage.
- Category and tag support.
- Published-date ordering.
- Configurable article limits.

### Dashboard

- Latest cybersecurity news.
- Threat and vulnerability views.
- Source listing.
- Search across loaded articles.
- Local bookmark functionality.
- Settings interface.
- Responsive frontend built without a frontend framework.

### Image Handling

CyberIntel uses a layered image discovery process:

1. Image supplied by the RSS feed.
2. Open Graph metadata.
3. Twitter metadata.
4. Generic HTML image tags.

Discovered image URLs are validated before use and stored with the associated article.

### Security

The application includes:

- SSRF-resistant outbound URL validation.
- Redirect target validation.
- Explicit HTTP request timeouts.
- RSS feed size limits.
- Refresh locking.
- Refresh rate limiting.
- Generic API error responses.
- Server-side error logging.
- Content Security Policy.
- Clickjacking protection.
- MIME-sniffing protection.
- Referrer Policy.
- Permissions Policy.
- Server-side Supabase credentials.

---

## Architecture

```text
                         +----------------------+
                         |      CyberIntel      |
                         |      Web Browser     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |      Flask API       |
                         |      server.py       |
                         +----------+-----------+
                                    |
                      +-------------+-------------+
                      |                           |
                      v                           v
             +----------------+          +-------------------+
             |   RSS Feeds    |          | Supabase PostgreSQL|
             | News Sources   |          | Articles / Sources |
             +----------------+          +-------------------+
```

### Data Flow

```text
RSS Sources
     |
     v
Feed Fetching
     |
     v
Validation & Parsing
     |
     v
Image Discovery
     |
     v
Supabase PostgreSQL
     |
     v
Flask API
     |
     v
CyberIntel Dashboard
```

---

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Backend | Python / Flask |
| Database | Supabase PostgreSQL |
| News ingestion | RSS feeds |
| Image metadata | Open Graph / Twitter / HTML |
| Local storage | Browser `localStorage` |
| Production server | Gunicorn |
| Deployment | Production WSGI hosting / Vercel adaptation |

---

## Project Structure

```text
CyberIntel/
├── index.html
├── style.css
├── script.js
├── server.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── DEPLOYMENT_CHECKLIST.md
└── supabase/
    └── schema.sql
```

### Core Files

| File | Purpose |
|---|---|
| `index.html` | Main dashboard interface |
| `style.css` | Application styling and responsive layout |
| `script.js` | Frontend application logic |
| `server.py` | Flask backend, RSS ingestion, API routes, and security controls |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `supabase/schema.sql` | Database schema and permissions |
| `DEPLOYMENT_CHECKLIST.md` | Production deployment checklist |

---

# Getting Started

## Prerequisites

Before running CyberIntel locally, install:

- Python 3
- Git
- A Supabase project
- Internet access for RSS ingestion

---

## 1. Configure Supabase

Create a Supabase project and run:

```text
supabase/schema.sql
```

using the **Supabase SQL Editor**.

The schema creates the required:

- `sources` table
- `articles` table
- Database indexes
- Row Level Security configuration
- Server-side access permissions

---

## 2. Configure Environment Variables

Create a local `.env` file from the provided template.

### PowerShell

```powershell
Copy-Item .env.example .env
```

Then configure the required Supabase credentials.

Example:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your-server-side-secret
```

Additional optional configuration can be found in:

```text
.env.example
```

### Important

**Never commit `.env` to GitHub.**

The `.gitignore` file should exclude it from version control.

---

## 3. Create a Virtual Environment

```powershell
py -m venv .venv
```

Activate it:

```powershell
.venv\Scriptsctivate
```

---

## 4. Install Dependencies

```powershell
py -m pip install -r requirements.txt
```

---

## 5. Start CyberIntel

```powershell
py server.py
```

Open:

```text
http://127.0.0.1:5000
```

---

# API

CyberIntel exposes a small HTTP API.

## Health Check

```http
GET /api/health
```

Checks:

- Application availability.
- Supabase configuration.
- Supabase reachability.

Example:

```json
{
  "ok": true,
  "supabase_configured": true,
  "supabase_reachable": true
}
```

---

## Get News

```http
GET /api/news
```

Returns the latest stored cybersecurity articles.

### Limit Results

```http
GET /api/news?limit=60
```

The backend supports up to 100 returned articles.

### Force Refresh

```http
GET /api/news?refresh=1
```

Forces an RSS refresh before returning the latest articles.

Forced refresh requests are rate-limited per client IP.

---

## Get Sources

```http
GET /api/sources
```

Returns the configured news sources.

---

# Article Retention

CyberIntel automatically removes articles older than the configured retention period.

The default value is:

```text
30 days
```

Configure it with:

```env
ARTICLE_RETENTION_DAYS=30
```

This helps prevent the database from growing indefinitely.

---

# Security

Security is treated as a core part of the application rather than an optional feature.

## Server-Side Secrets

Supabase credentials are never required by the frontend.

The browser communicates with Flask, while Flask communicates with Supabase using the server-side secret.

```text
Browser
   |
   | No Supabase secret
   v
Flask
   |
   | Server-side secret
   v
Supabase
```

## SSRF Protection

Outbound URLs are validated before requests are made.

The validation includes protections against:

- Localhost addresses.
- Loopback addresses.
- Private network addresses.
- Link-local addresses.
- Reserved addresses.
- Unsupported protocols.
- Unexpected ports.
- Unsafe redirect destinations.

## HTTP Protection

External requests use explicit timeouts and feed-size limits to reduce the impact of slow or unexpectedly large responses.

## Security Headers

CyberIntel configures security-related HTTP response headers including:

- `Content-Security-Policy`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `Permissions-Policy`

---

# Image Processing

CyberIntel attempts to provide useful article thumbnails without blindly trusting arbitrary image URLs.

The image discovery order is:

```text
RSS image
   ↓
Open Graph image
   ↓
Twitter image
   ↓
Generic HTML image
```

Before an external image URL is requested, it is checked against the application's outbound URL validation rules.

Images discovered during ingestion are stored with the corresponding article in Supabase.

---

# Error Handling

CyberIntel uses generic responses for client-facing API failures while retaining useful diagnostic information in server logs.

This avoids exposing internal implementation details or sensitive exception information to users.

External feed failures are handled independently so that a problem with one source does not necessarily prevent other sources from being processed.

---

# Production Deployment

Do not use Flask's development server for a production deployment.

For a traditional Linux-based deployment, use a production WSGI server such as Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 server:app
```

Configure production environment variables through the deployment platform.

Do not upload `.env` to the deployment environment through Git.

---

# Vercel Deployment

CyberIntel can be adapted for deployment on Vercel using its Python/Flask support.

A Vercel-oriented architecture should separate:

```text
/api/news
```

from the RSS ingestion process.

Recommended architecture:

```text
Browser
   |
   v
Vercel / Flask
   |
   v
Supabase
```

and separately:

```text
Vercel Cron
   |
   v
Refresh Endpoint
   |
   +--> RSS Feeds
   |
   +--> Image Processing
   |
   +--> Supabase
```

For Vercel deployment, use Vercel environment variables for:

```text
SUPABASE_URL
SUPABASE_SECRET_KEY
CRON_SECRET
```

Never place these secrets in frontend JavaScript or source control.

> Cron frequency depends on the Vercel plan and its current scheduling limits. Verify the current Vercel documentation before selecting a production refresh interval.

---

# Supabase Security

The database is configured with Row Level Security and server-side permissions.

The intended access model is:

```text
Public Browser
      |
      X
      | No direct database credentials
      |
      v
Flask Backend
      |
      v
Supabase PostgreSQL
```

The Supabase secret key must remain confidential.

### If a Secret Is Exposed

If a Supabase secret has ever been exposed through:

- Git history
- GitHub
- ZIP archives
- Logs
- Screenshots
- Chat messages
- Public deployments

immediately revoke or rotate the exposed key in Supabase and configure the application with the replacement secret.

---

# GitHub Publishing

Before pushing CyberIntel to GitHub, verify that sensitive files are excluded.

Run:

```powershell
git status
```

The repository should **not** contain:

```text
.env
.venv/
__pycache__/
*.pyc
```

A clean repository should contain only the source code, configuration templates, documentation, and database schema required by the project.

### Initial Git Setup

```powershell
git init
git add .
git status
git commit -m "Initial CyberIntel release"
git branch -M main
```

Then connect the repository to GitHub and push:

```powershell
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Do not replace `YOUR_GITHUB_REPOSITORY_URL` with a repository URL containing credentials or tokens.

---

# Configuration

Environment variables are documented in:

```text
.env.example
```

Typical configuration includes:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SECRET_KEY` | Server-side Supabase credential |
| `ARTICLE_RETENTION_DAYS` | Number of days articles are retained |
| RSS/image settings | Optional ingestion configuration |

The exact available configuration should always be taken from the current `.env.example`.

---

# Reliability Considerations

CyberIntel is intentionally designed to remain simple.

The backend includes:

- Feed request timeouts.
- Feed-size limits.
- Refresh locking.
- Refresh rate limiting.
- Database indexes.
- Image caching.
- Article retention cleanup.
- Independent feed failure handling.
- Server-side logging.

Some controls, such as in-memory locks and caches, are process-local. Serverless deployments may use multiple independent instances, so production deployments should not rely on in-memory state for global coordination or rate limiting.

---

# Development Principles

CyberIntel follows a few simple principles:

1. **Keep the architecture simple.**
2. **Keep secrets server-side.**
3. **Treat external RSS and article content as untrusted input.**
4. **Validate outbound URLs.**
5. **Fail gracefully when individual news sources are unavailable.**
6. **Keep the database limited to useful, recent content.**
7. **Avoid unnecessary frameworks and dependencies.**
8. **Prefer maintainable code over unnecessary complexity.**

---

# License

Choose and add a license appropriate for the project.

For a typical open-source or portfolio project, the MIT License is a common option.

If using MIT, add a `LICENSE` file containing the official MIT License text.

---

## CyberIntel

**A simple, secure, and centralized way to keep up with cybersecurity news.**
