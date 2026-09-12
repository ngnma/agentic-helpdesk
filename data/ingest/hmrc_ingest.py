"""
HMRC mileage/travel guidance ingestion — via the GOV.UK Content API.

Instead of scraping HTML, gov.uk pages have a matching JSON endpoint:
insert /api/content between the domain and the page's path. This returns
the exact structured content gov.uk uses to render the page — no nav,
footer, or cookie-banner junk to clean up, and no risk of HTML structure
changes breaking a scraper.
"""

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAW_DIR = Path("data/raw/hmrc")
CONTENT_DIR = RAW_DIR / "content"
MANIFEST_PATH = CONTENT_DIR / "_manifest.json"

# The public-facing page URLs — we derive the API URL from these
SEED_PAGES = [
    {
        "url": "https://www.gov.uk/government/publications/rates-and-allowances-travel-mileage-and-fuel-allowances/travel-mileage-and-fuel-rates-and-allowances",
        "topic": ["HMRC", "Expenses", "Mileage rates"],
    },
    {
        "url": "https://www.gov.uk/expenses-and-benefits-business-travel-mileage",
        "topic": ["HMRC", "Expenses", "Business travel"],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
CRAWL_DELAY = 1.0

log = logging.getLogger("hmrc-ingest")
logging.basicConfig(level=logging.INFO, format="%(message)s")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def page_url_to_api_url(page_url: str) -> str:
    """https://www.gov.uk/foo/bar -> https://www.gov.uk/api/content/foo/bar"""
    parsed = urlparse(page_url)
    return f"https://www.gov.uk/api/content{parsed.path}"


def url_to_filename(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1] + ".txt"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_json(session: requests.Session, url: str) -> dict | None:
    """GET with simple retry/backoff. Returns None if unreachable."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt} failed for {url}: {e}")
            time.sleep(CRAWL_DELAY * attempt)
    log.error(f"Giving up on {url} after {MAX_RETRIES} attempts")
    return None


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """Content API bodies are HTML fragments — strip tags to plain text."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def extract_body_text(content_item: dict) -> str:
    """
    Handle the two common GOV.UK content shapes:
    - simple pages: details.body is one HTML string
    - guides: details.parts is a list of {title, body, slug} sections
    """
    details = content_item.get("details", {})

    if "body" in details and isinstance(details["body"], str):
        return html_to_text(details["body"])

    if "parts" in details and isinstance(details["parts"], list):
        sections = []
        for part in details["parts"]:
            title = part.get("title", "")
            body_html = part.get("body", "")
            sections.append(f"## {title}\n{html_to_text(body_html)}")
        return "\n\n".join(sections)

    log.warning("Unrecognized content shape — no 'body' or 'parts' found")
    return ""


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_text(text: str, filename: str) -> Path:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTENT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return path


def save_manifest(entries: list[dict]) -> None:
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    session = make_session()
    manifest = []

    for page in SEED_PAGES:
        api_url = page_url_to_api_url(page["url"])
        log.info(f"Fetching: {api_url}")

        content_item = fetch_json(session, api_url)
        if content_item is None:
            continue

        text = extract_body_text(content_item)
        if not text:
            log.warning(f"No text extracted for {page['url']}, skipping")
            continue

        filename = url_to_filename(page["url"])
        path = save_text(text, filename)

        manifest.append({
            "title": content_item.get("title", filename),
            "url": page["url"],
            "topic": page["topic"],
            "source": api_url,
            "file": filename,
            "characters": len(text),
        })
        log.info(f"Saved: {path} ({len(text)} chars)")

        time.sleep(CRAWL_DELAY)

    save_manifest(manifest)
    log.info(f"Manifest written: {MANIFEST_PATH} ({len(manifest)} entries)")


if __name__ == "__main__":
    run()