"""
NEST pension member help centre ingestion.

Structural note: NEST's site doesn't have a clean DOM pattern like ACAS's
card-links, so instead of matching by structure we allowlist by URL path —
only follow links under the member-facing sections, not employer/adviser/
login/legal pages that live on the same domain.
"""

import json
import logging
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAW_DIR = Path("data/raw/nest")
CONTENT_DIR = RAW_DIR / "content"
MANIFEST_PATH = CONTENT_DIR / "_manifest.json"

SEED_URLS = [
    "https://www.nestpensions.org.uk/schemeweb/memberhelpcentre/opting-out/how-to-opt-out.html",
    "https://www.nestpensions.org.uk/schemeweb/memberhelpcentre/frequently-asked-questions.html",
]

# Only these path prefixes are real member-facing content —
# everything else (employer/adviser/login/legal) is out of scope
ALLOWED_PATH_PREFIXES = [
    "/schemeweb/memberhelpcentre",
    "/schemeweb/nest/my-nest-pension",
]

MAX_DEPTH = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
CRAWL_DELAY = 1.0

# Everything from this heading onward is feedback/live-chat widget junk
CUTOFF_MARKERS = [
    "We value your feedback",
]

log = logging.getLogger("nest-ingest")
logging.basicConfig(level=logging.INFO, format="%(message)s")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    """GET with simple retry/backoff. Returns None if the URL is unreachable."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt} failed for {url}: {e}")
            time.sleep(CRAWL_DELAY * attempt)
    log.error(f"Giving up on {url} after {MAX_RETRIES} attempts")
    return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    for marker in CUTOFF_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].strip()

    return text


def is_allowed_path(url: str) -> bool:
    path = urlparse(url).path
    return any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def extract_links(html: str, base_url: str) -> set[str]:
    """Only keep links that are real http(s) URLs on an allowed member-content path."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()

        # Skip JS-triggered widgets, anchors, mailto links — not real pages
        if href.startswith(("javascript:", "mailto:", "#")) or href == "":
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        if parsed.netloc != urlparse(base_url).netloc:
            continue
        if not is_allowed_path(full_url):
            continue

        links.add(full_url)

    return links


def save_text(text: str, filename: str) -> Path:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTENT_DIR / filename
    path.write_text(text, encoding="utf-8")
    return path


def url_to_filename(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1].replace(".html", "") + ".txt"


def extract_title(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return fallback


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def save_manifest(entries: list[dict]) -> None:
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

def crawl(seed_urls, max_depth=MAX_DEPTH):
    session = make_session()
    visited = set()
    manifest = []
    queue = deque((url, 0) for url in seed_urls)

    while queue:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        log.info(f"Fetching (depth {depth}): {url}")
        response = fetch(session, url)
        if response is None:
            continue

        html = response.text
        text = extract_text(html)
        filename = url_to_filename(url)
        path = save_text(text, filename)

        manifest.append({
            "title": extract_title(html, fallback=filename),
            "url": url,
            "topic": ["NEST", "Pension", "Member help centre"],
            "source": url,
            "file": filename,
            "characters": len(text),
        })
        log.info(f"Saved: {path} ({len(text)} chars)")

        if depth < max_depth:
            for link in extract_links(html, url):
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(CRAWL_DELAY)

    save_manifest(manifest)
    log.info(f"Manifest written: {MANIFEST_PATH} ({len(manifest)} entries)")


if __name__ == "__main__":
    crawl(SEED_URLS)