import hashlib
import os
import ipaddress
import logging
import socket
import time
import threading
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from supabase import create_client

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
PORT = int(os.getenv("PORT", "5000"))
REFRESH_SECONDS = int(os.getenv("NEWS_REFRESH_SECONDS", "300"))
MAX_ARTICLES_PER_SOURCE = int(os.getenv("MAX_ARTICLES_PER_SOURCE", "20"))
ARTICLE_RETENTION_DAYS = int(os.getenv("ARTICLE_RETENTION_DAYS", "30"))
CLEANUP_SECONDS = 86400
FEED_REQUEST_TIMEOUT = float(os.getenv("FEED_REQUEST_TIMEOUT", "10"))
REFRESH_RATE_LIMIT_SECONDS = int(os.getenv("REFRESH_RATE_LIMIT_SECONDS", "60"))
IMAGE_LOOKUP_TIMEOUT = float(os.getenv("IMAGE_LOOKUP_TIMEOUT", "4"))
IMAGE_CACHE_SECONDS = int(os.getenv("IMAGE_CACHE_SECONDS", "86400"))

SOURCES = [
    {"id": "thehackernews", "name": "The Hacker News", "feed": "https://feeds.feedburner.com/TheHackersNews", "homepage": "https://thehackernews.com/", "description": "Cybersecurity news, vulnerabilities, threat research and enterprise security."},
    {"id": "bleepingcomputer", "name": "BleepingComputer", "feed": "https://www.bleepingcomputer.com/feed/", "homepage": "https://www.bleepingcomputer.com/", "description": "Security news covering malware, ransomware, Windows and cybercrime."},
    {"id": "krebsonsecurity", "name": "Krebs on Security", "feed": "https://krebsonsecurity.com/feed/", "homepage": "https://krebsonsecurity.com/", "description": "Investigative reporting and analysis on cybercrime and security."},
    {"id": "securityweek", "name": "SecurityWeek", "feed": "https://feeds.feedburner.com/securityweek", "homepage": "https://www.securityweek.com/", "description": "Enterprise security news, vulnerability research and threat intelligence."},
]

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

_last_refresh = 0.0
_last_cleanup = 0.0
_refresh_lock = threading.Lock()
_rate_lock = threading.Lock()
_refresh_attempts = {}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("cyberintel")


class _HTMLTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value):
    parser = _HTMLTextParser()
    try:
        parser.feed(unescape(str(value or "")))
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = unescape(str(value or ""))
    return " ".join(text.replace("\n", " ").split()).strip()


_image_cache = {}


def _valid_image_url(value, base_url=""):
    if not value:
        return ""
    value = str(value).strip().strip('\"\'')
    if not value or value.startswith("data:"):
        return ""
    value = urljoin(base_url, value) if base_url else value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return ""


class _ImageParser(HTMLParser):
    """Collect preferred social metadata before generic <img> tags."""
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.meta_image = ""
        self.img_image = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "meta":
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and not self.meta_image:
                image = _valid_image_url(attrs.get("content"), self.base_url)
                if image:
                    self.meta_image = image
        elif tag == "img" and not self.img_image:
            for key in ("src", "data-src", "data-original", "data-lazy-src"):
                image = _valid_image_url(attrs.get(key), self.base_url)
                if image:
                    self.img_image = image
                    break

    @property
    def image(self):
        return self.meta_image or self.img_image

def first_image(entry):
    candidates = []
    media = entry.get("media_content") or []
    thumbnails = entry.get("media_thumbnail") or []
    enclosures = entry.get("enclosures") or []

    candidates.extend(item.get("url") or item.get("href") for item in media if isinstance(item, dict))
    candidates.extend(item.get("url") or item.get("href") for item in thumbnails if isinstance(item, dict))
    candidates.extend(item.get("href") or item.get("url") for item in enclosures if isinstance(item, dict))

    image = entry.get("image")
    if isinstance(image, dict):
        candidates.append(image.get("href") or image.get("url"))

    # Some feeds put the image only inside their HTML summary/content.
    html_values = [entry.get("summary"), entry.get("description")]
    content = entry.get("content") or []
    if isinstance(content, list):
        html_values.extend(item.get("value") for item in content if isinstance(item, dict))

    for html in html_values:
        if html:
            parser = _ImageParser(entry.get("link") or "")
            try:
                parser.feed(str(html))
                if parser.image:
                    candidates.append(parser.image)
            except Exception:
                pass

    for value in candidates:
        image_url = _valid_image_url(value, entry.get("link") or "")
        if image_url:
            return image_url
    return ""


def _is_public_hostname(hostname):
    """Reject localhost, private, loopback, link-local and reserved targets."""
    if not hostname:
        return False
    hostname = hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        return False
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _safe_outbound_url(url, allowed_schemes=("http", "https")):
    parsed = urlparse(url)
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 80, 443):
        return False
    return _is_public_hostname(parsed.hostname)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_outbound_url(newurl):
            raise ValueError("Blocked redirect target")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_safe_opener = build_opener(_SafeRedirectHandler())

def _fetch_url(url, timeout, accept):
    if not _safe_outbound_url(url):
        raise ValueError("Blocked outbound URL")
    req = Request(url, headers={"User-Agent": "CyberIntel/1.0", "Accept": accept})
    return _safe_opener.open(req, timeout=timeout)

def page_image(url):
    """Find an article's Open Graph/Twitter image when the RSS item has none."""
    if not url:
        return ""
    now = time.time()
    cached = _image_cache.get(url)
    if cached and now - cached[0] < cached[1]:
        return cached[2]

    try:
        with _fetch_url(url, IMAGE_LOOKUP_TIMEOUT, "text/html,application/xhtml+xml") as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                image = ""
            else:
                html = response.read(512 * 1024).decode("utf-8", errors="ignore")
                parser = _ImageParser(url)
                parser.feed(html)
                image = parser.image
    except Exception as exc:
        logger.debug("Image lookup failed for %s: %s", url, exc)
        image = ""

    ttl = IMAGE_CACHE_SECONDS if image else 3600
    _image_cache[url] = (now, ttl, image)
    return image


def fill_missing_images(rows):
    missing = [row for row in rows if not row.get("image") and row.get("url")]
    if not missing:
        return rows

    # Keep startup/refresh responsive while allowing sources with no RSS image
    # to get their real article thumbnail from Open Graph metadata.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(page_image, row["url"]): row for row in missing}
        for future in as_completed(futures):
            row = futures[future]
            try:
                row["image"] = future.result() or ""
            except Exception:
                row["image"] = ""
    return rows


def severity_for(title, summary, category, tags):
    text = f"{title} {summary} {category} {' '.join(tags)}".lower()
    if any(term in text for term in ("actively exploited", "exploited in the wild", "zero-day", "rce", "remote code execution", "critical", "maximum severity")):
        return "Critical"
    if any(term in text for term in ("ransomware", "malware", "vulnerability", "exploit", "breach", "phishing", "attack", "backdoor")):
        return "High"
    if any(term in text for term in ("threat actor", "credential", "identity", "campaign", "intrusion")):
        return "Medium"
    return "Low"


def classify(title, summary):
    text = f"{title} {summary}".lower()
    # Specific/high-signal topics come first so broad words such as "attack"
    # do not hide ransomware, malware, vulnerability, or AI stories.
    rules = [
        ("Ransomware", ("ransomware", "ransom demand", "data extortion")),
        ("Malware", ("malware", "trojan", "stealer", "botnet", "spyware", "backdoor", "infostealer")),
        ("Vulnerabilities", ("cve-", "vulnerability", "vulnerable", "zero-day", "zero day", "rce", "remote code execution", "security flaw")),
        ("Data Breaches", ("data breach", "breach", "data leak", "leaked data", "exposed data", "stolen data")),
        ("AI Security", ("artificial intelligence", "large language model", "llm", "prompt injection", "ai agent", "ai agents", "machine learning")),
        ("Cloud Security", ("cloud security", "cloud", "aws", "azure", "gcp", "kubernetes", "container")),
        ("Threat Intelligence", ("threat actor", "apt", "threat intel", "ioc", "indicator of compromise")),
        ("Cyber Attacks", ("cyber attack", "attack campaign", "intrusion", "phishing", "ddos", "compromise")),
    ]
    for category, words in rules:
        if any(word in text for word in words):
            return category
    return "General Cybersecurity"


def tags_for(title, summary):
    text = f"{title} {summary}".lower()
    rules = [
        ("CVE", "cve-"), ("Ransomware", "ransomware"), ("Malware", "malware"),
        ("Phishing", "phishing"), ("Cloud", "cloud"), ("AI Security", "artificial intelligence"),
        ("Data Breach", "breach"), ("Zero-Day", "zero-day"),
        ("Supply Chain", "supply chain"), ("Vulnerability", "vulnerability"),
        ("Identity", "identity"), ("Credentials", "credential"),
    ]
    tags = [name for name, word in rules if word in text]
    return tags[:4] or ["Cybersecurity"]


def article_id(source_id, url, title):
    raw = f"{source_id}|{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def normalize_published(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass

    raw = entry.get("published") or entry.get("updated")
    if raw:
        return clean_text(raw)

    return datetime.now(timezone.utc).isoformat()


def normalize_entry(entry, source):
    title = clean_text(entry.get("title") or "Untitled security story")
    summary = clean_text(entry.get("summary") or entry.get("description") or "No summary available.")
    url = clean_text(entry.get("link") or source["homepage"])

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        url = source["homepage"]

    return {
        "id": article_id(source["id"], url, title),
        "source_id": source["id"],
        "source": source["name"],
        "title": title,
        "summary": summary[:2000],
        "url": url,
        "published_at": normalize_published(entry),
        "category": classify(title, summary),
        "tags": tags_for(title, summary),
        "image": first_image(entry),
    }


def upsert_source(source):
    """Ensure the parent source exists before inserting articles referencing it."""
    return supabase.table("sources").upsert(
        {
            "id": source["id"],
            "name": source["name"],
            "feed_url": source["feed"],
            "homepage_url": source["homepage"],
            "description": source["description"],
            "enabled": True,
        },
        on_conflict="id",
    ).execute()


def fetch_feed(url):
    """Fetch an RSS/Atom document with an explicit timeout and size limit."""
    with _fetch_url(url, FEED_REQUEST_TIMEOUT, "application/rss+xml, application/atom+xml, application/xml, text/xml") as response:
        data = response.read(2 * 1024 * 1024)
    parsed = feedparser.parse(data)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise ValueError("Feed could not be parsed")
    return parsed

def ingest():
    if supabase is None:
        raise RuntimeError(
            "Supabase is not configured. Copy .env.example to .env and add SUPABASE_URL and SUPABASE_SECRET_KEY."
        )

    successful_sources = 0
    failed_sources = []

    for source in SOURCES:
        try:
            # IMPORTANT: sources must exist before articles because articles.source_id
            # has a foreign-key constraint referencing sources.id.
            upsert_source(source)

            parsed = fetch_feed(source["feed"])
            rows = [
                normalize_entry(entry, source)
                for entry in parsed.entries[:MAX_ARTICLES_PER_SOURCE]
            ]
            rows = fill_missing_images(rows)

            if rows:
                supabase.table("articles").upsert(rows, on_conflict="id").execute()

            supabase.table("sources").update({
                "last_fetched_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", source["id"]).execute()
            successful_sources += 1
        except Exception as exc:
            failed_sources.append({"source": source["id"], "error": type(exc).__name__})
            logger.warning("Feed ingestion failed for %s: %s", source["id"], exc)

    if successful_sources == 0:
        raise RuntimeError(f"All news sources failed: {failed_sources}")

    return {
        "successful_sources": successful_sources,
        "failed_sources": failed_sources,
    }



def cleanup_old_articles():
    """Delete articles older than the configured retention period."""
    if supabase is None:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=ARTICLE_RETENTION_DAYS)
    result = supabase.table("articles").delete().lt(
        "published_at", cutoff.isoformat()
    ).execute()
    logger.info("Article retention cleanup completed (cutoff=%s)", cutoff.isoformat())


def cleanup_if_needed():
    global _last_cleanup
    now = time.time()

    if now - _last_cleanup >= CLEANUP_SECONDS:
        try:
            cleanup_old_articles()
            _last_cleanup = now
        except Exception as exc:
            logger.exception("Article retention cleanup failed: %s", exc)


def refresh_if_needed(force=False):
    global _last_refresh
    now = time.time()
    if not force and now - _last_refresh < REFRESH_SECONDS:
        return {"skipped": True}

    with _refresh_lock:
        now = time.time()
        if not force and now - _last_refresh < REFRESH_SECONDS:
            return {"skipped": True}
        result = ingest()
        _last_refresh = now
        return result


def refresh_rate_limited(client_ip):
    now = time.time()
    with _rate_lock:
        last = _refresh_attempts.get(client_ip, 0.0)
        if now - last < REFRESH_RATE_LIMIT_SECONDS:
            return False
        _refresh_attempts[client_ip] = now
        if len(_refresh_attempts) > 2048:
            cutoff = now - REFRESH_RATE_LIMIT_SECONDS
            for key, value in list(_refresh_attempts.items()):
                if value < cutoff:
                    _refresh_attempts.pop(key, None)
    return True


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )
    return response


@app.get("/api/health")
def health():
    supabase_ok = False
    if supabase is not None:
        try:
            supabase.table("sources").select("id").limit(1).execute()
            supabase_ok = True
        except Exception as exc:
            logger.warning("Supabase health check failed: %s", exc)
    ok = supabase is not None and supabase_ok
    return jsonify({
        "ok": ok,
        "supabase_configured": supabase is not None,
        "supabase_reachable": supabase_ok,
    }), (200 if ok else 503)


@app.get("/api/news")
def news():
    try:
        force_refresh = request.args.get("refresh") == "1"
        if force_refresh and not refresh_rate_limited(request.remote_addr or "unknown"):
            return jsonify({"error": "Refresh temporarily rate limited", "articles": [], "mode": "offline"}), 429
        refresh_result = refresh_if_needed(force_refresh)
        cleanup_if_needed()
        limit = min(max(int(request.args.get("limit", "60")), 1), 100)

        result = (
            supabase.table("articles")
            .select("*")
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )

        now = datetime.now(timezone.utc)
        articles = []
        for row in (result.data or []):
            published = row["published_at"]
            try:
                published_dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                if published_dt.tzinfo is None:
                    published_dt = published_dt.replace(tzinfo=timezone.utc)
                is_new = now - published_dt <= timedelta(hours=24)
            except (TypeError, ValueError):
                is_new = False

            tags = row.get("tags") or []
            articles.append({
                "id": row["id"],
                "sourceId": row["source_id"],
                "source": row["source"],
                "title": row["title"],
                "summary": row["summary"],
                "url": row["url"],
                "publishedAt": row["published_at"],
                "category": row["category"],
                "tags": tags,
                "image": row.get("image") or "",
                "severity": severity_for(row["title"], row["summary"], row["category"], tags),
                "isNew": is_new,
            })

        return jsonify({
            "mode": "live-api",
            "articles": articles,
            "count": len(articles),
            "refresh": refresh_result,
        })
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid request", "articles": [], "mode": "offline"}), 400
    except Exception as exc:
        logger.exception("News API failed: %s", exc)
        return jsonify({"error": "News service temporarily unavailable", "articles": [], "mode": "offline"}), 503


@app.get("/api/sources")
def sources():
    if supabase is None:
        return jsonify({"sources": SOURCES})

    try:
        result = supabase.table("sources").select("*").order("name").execute()
        return jsonify({"sources": result.data or []})
    except Exception as exc:
        logger.exception("Sources API failed: %s", exc)
        return jsonify({"error": "Sources service temporarily unavailable", "sources": []}), 503


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


if __name__ == "__main__":
    logger.warning("Using Flask development server; use a production WSGI server for deployment.")
    app.run(host="0.0.0.0", port=PORT, debug=False)
