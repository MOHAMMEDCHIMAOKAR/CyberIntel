# CyberIntel

A simple cybersecurity news dashboard using vanilla HTML/CSS/JS, Flask, RSS feeds, and Supabase PostgreSQL.

## Architecture

Browser → Flask (`server.py`) → RSS feeds + Supabase

The Supabase secret key is server-side only. Never put it in frontend code, commit `.env`, or include `.env` in a ZIP/deployment artifact.

## Local setup

1. Create/configure the Supabase project.
2. Run `supabase/schema.sql` in the Supabase SQL Editor.
3. Copy `.env.example` to `.env`.
4. Add the server-only Supabase secret key to `.env`.
5. Create a virtual environment:

```powershell
py -m venv .venv
.venv\Scripts\activate
```

6. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

7. Start locally:

```powershell
py server.py
```

Open `http://127.0.0.1:5000`.

## API

- `GET /api/health` — application and Supabase reachability check.
- `GET /api/news` — current articles.
- `GET /api/news?refresh=1` — force a refresh; rate-limited per client IP.
- `GET /api/news?limit=60` — return up to 100 articles.
- `GET /api/sources` — configured sources.

## Hardening included

- Explicit RSS and article-page request timeouts.
- Safe outbound URL validation to reduce SSRF risk, including redirect validation.
- In-memory refresh lock to prevent concurrent refreshes in one process.
- Rate limiting for forced refresh requests.
- Generic client-facing errors with server-side logging.
- Real Supabase reachability health check.
- Daily rolling article retention cleanup.
- Persistent article images stored in Supabase.
- Open Graph/Twitter metadata preferred over generic page images.
- Frontend bookmark storage handles malformed local storage safely.
- Frontend uses the backend as its sole live intelligence source; demo/RSS2JSON fallback code is removed.
- Security response headers including CSP, frame protection, and MIME sniffing protection.

## Image handling

CyberIntel first uses images supplied by RSS. If an item has no image, the backend checks the article page for Open Graph/Twitter metadata and then generic image tags. Discovered URLs are stored with the article in Supabase.

Optional settings are available in `.env.example`.

## Retention

Articles older than `ARTICLE_RETENTION_DAYS` are removed by the backend cleanup routine. The default is 30 days.

## Production deployment

Do not deploy the Flask development server. Use a production WSGI server such as Gunicorn on a Linux deployment target:

```bash
gunicorn --bind 0.0.0.0:5000 server:app
```

Set all secrets and configuration through the deployment platform's environment-variable settings. Do not upload `.env`.

### Supabase secret rotation

If a Supabase secret was ever exposed in a ZIP, repository, log, or chat, revoke/rotate it in Supabase and create a new server-side secret before deployment.
