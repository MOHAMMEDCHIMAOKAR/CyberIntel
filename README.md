CyberIntel

A lightweight cybersecurity news aggregation dashboard built with vanilla HTML, CSS, and JavaScript, Flask, RSS feeds, and Supabase PostgreSQL.

CyberIntel collects cybersecurity news from configured RSS sources, processes and stores articles in Supabase, and presents the latest intelligence through a simple web interface.

Architecture
Browser
   │
   ▼
Flask Application
   │
   ├── RSS Feeds
   │
   └── Supabase PostgreSQL

The Supabase secret key is used exclusively on the server side. Never expose it in frontend code, commit .env to version control, or include .env in a ZIP archive or deployment artifact.

Local Development
1. Configure Supabase

Create and configure the Supabase project, then execute:

supabase/schema.sql

in the Supabase SQL Editor.

2. Configure environment variables

Create a local .env file from the provided template:

Copy-Item .env.example .env

Add the required server-side Supabase credentials to .env.

Keep .env local. It must not be committed to Git or included in deployment artifacts.

3. Create a virtual environment
py -m venv .venv
.venv\Scripts\activate
4. Install dependencies
py -m pip install -r requirements.txt
5. Start the application
py server.py

The application will be available at:

http://127.0.0.1:5000
API Reference
Endpoint	Description
GET /api/health	Checks application status and Supabase connectivity.
GET /api/news	Returns the latest stored cybersecurity articles.
GET /api/news?refresh=1	Forces a news refresh. Requests are rate-limited per client IP.
GET /api/news?limit=60	Returns up to 100 articles.
GET /api/sources	Returns the configured news sources.
Security & Hardening

CyberIntel includes several security and reliability controls:

Explicit timeouts for RSS and article-page requests.
SSRF-resistant outbound URL validation, including redirect validation.
In-memory refresh locking to prevent concurrent refresh operations within a process.
Rate limiting for forced refresh requests.
Generic client-facing error responses with detailed server-side logging.
Supabase connectivity verification through the health endpoint.
Automatic rolling retention cleanup for older articles.
Persistent article images stored in Supabase.
Open Graph and Twitter metadata prioritized when extracting article images.
Safe handling of malformed browser localStorage bookmark data.
Backend-only live intelligence retrieval with demo data and RSS2JSON fallbacks removed.
Security response headers, including:
Content Security Policy (CSP)
Clickjacking protection
MIME-sniffing protection
Referrer Policy
Permissions Policy
Image Processing

CyberIntel uses the following image discovery strategy:

Use an image provided directly by the RSS feed when available.
If no image is provided, inspect the article page for:
Open Graph metadata
Twitter metadata
Generic image tags
Validate discovered image URLs before requesting them.
Store the resulting image URL with the article in Supabase.

Additional image-processing options can be configured through .env.example.

Article Retention

CyberIntel automatically removes articles older than the configured retention period.

The default retention period is:

30 days

This can be configured using:

ARTICLE_RETENTION_DAYS
Production Deployment

The Flask development server is intended for local development only.

For traditional Linux-based deployments, use a production WSGI server such as Gunicorn:

gunicorn --bind 0.0.0.0:5000 server:app

All secrets and environment-specific configuration should be provided through the deployment platform's environment-variable system.

Never upload .env to the production server through source control or include it in a public deployment artifact.

Supabase Secret Management

Supabase credentials must remain server-side.

If a Supabase secret has ever been exposed through:

A Git repository
A ZIP archive
Application logs
Screenshots
Chat messages
Other publicly accessible locations

immediately revoke or rotate the exposed credential in Supabase and configure the application with a new server-side secret.

Project Structure
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
Technology Stack
Frontend: HTML5, CSS3, Vanilla JavaScript
Backend: Python / Flask
Database: Supabase PostgreSQL
News ingestion: RSS feeds
Image extraction: Open Graph, Twitter metadata, and HTML image tags
Deployment: Compatible with production WSGI hosting and suitable for adaptation to serverless platforms such as Vercel
