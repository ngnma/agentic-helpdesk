"""Crawl the Acas advice site and save guide text for the HR-assistant RAG index.

The site is a shallow tree of "box" pages:

    /advice  ->  /pay-and-hours  ->  /pay-and-deductions  ->  /national-minimum-wage-entitlement

Leaf guides expose a "Download entire guide - PDF document" link (``/guide-download/<id>``)
whose PDF contains every page of that guide. We walk the boxes breadth-first, and whenever a
page offers that link we download the PDF, extract its text and stop descending — the guide PDF
already covers the child pages.

Guidance lands in ``data/raw/acas/content/`` and blank letter/form/policy templates in
``data/raw/acas/templates/``, each folder with its own ``_manifest.json``.

Usage:
    python data/ingest.py                 # full crawl into data/raw/acas/
    python data/ingest.py --limit 5       # smoke test: only write 5 documents
    python data/ingest.py --delay 1.0     # be gentler on the server

Requires: requests, beautifulsoup4, pypdf
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_URL = "https://www.acas.org.uk"
START_PATH = "/advice"

ACAS_DIR = Path(__file__).resolve().parent / "raw" / "acas"
OUT_DIR = ACAS_DIR / "content"
TEMPLATE_DIR = ACAS_DIR / "templates"
MANIFEST_NAME = "_manifest.json"

# Boxes on /advice that are not "Advice topics" (they sit under "Templates and Codes").
# Remove entries here if you also want those crawled.
SKIP_PATHS = {"/templates", "/codes-of-practice"}

# The bordered boxes that hold the topic links.
BOX_SELECTOR = "article[class*='flexible-bordered-box'] a[href]"
GUIDE_DOWNLOAD_SELECTOR = "a[href*='/guide-download/']"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

# Blank letter/form/policy templates are boilerplate to fill in rather than guidance to answer
# questions from, so they are written to their own folder and can be indexed separately.
TEMPLATE_MARKER = "template"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

log = logging.getLogger("acas-ingest")


# --------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch(session: requests.Session, url: str, delay: float) -> requests.Response | None:
    """GET with simple retry/backoff. Returns None if the URL is unreachable."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            time.sleep(delay)
            return response
        except requests.RequestException as exc:
            wait = delay * attempt * 2
            log.warning("fetch failed (%s/%s) %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt == MAX_RETRIES:
                log.error("giving up on %s", url)
                return None
            time.sleep(wait)
    return None


# --------------------------------------------------------------------------------------
# Page parsing
# --------------------------------------------------------------------------------------


def normalise(url: str) -> str:
    """Absolute URL without query string or fragment, so the same page dedupes to one key."""
    absolute = urljoin(BASE_URL, url)
    parts = urlparse(absolute)
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def is_internal(url: str) -> bool:
    return urlparse(normalise(url)).netloc == urlparse(BASE_URL).netloc


def page_title(soup: BeautifulSoup) -> str:
    heading = soup.select_one("main h1") or soup.select_one("h1")
    if heading:
        # On a guide's first page the h1 reads "<section> – <guide name>"; we want the guide.
        text = heading.get_text(" ", strip=True)
        return text.split("–")[-1].strip() if "–" in text else text
    if soup.title and soup.title.string:
        return soup.title.string.split("|")[0].strip()
    return "Untitled"


def box_links(soup: BeautifulSoup) -> list[str]:
    """Links inside the bordered topic boxes, in page order and de-duplicated."""
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select(BOX_SELECTOR):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        if not is_internal(href):
            continue
        url = normalise(href)
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def guide_download_url(soup: BeautifulSoup) -> str | None:
    """The '/guide-download/<id>' link, i.e. 'Download entire guide - PDF document'."""
    anchor = soup.select_one(GUIDE_DOWNLOAD_SELECTOR)
    if anchor is None:
        return None
    return urljoin(BASE_URL, anchor["href"])


def guide_id(download_url: str) -> str:
    """'/guide-download/68?1789215011' -> '68'. Guides share one id across their pages."""
    match = re.search(r"/guide-download/(\d+)", download_url)
    return match.group(1) if match else download_url


# --------------------------------------------------------------------------------------
# Text extraction / cleaning
# --------------------------------------------------------------------------------------

_PAGE_NUMBER = re.compile(r"^page\s+\d+$", re.IGNORECASE)
_BOILERPLATE = re.compile(
    r"^(©\s*acas|acas\s*\|.*|free updates from acas|print this page|"
    r"download (this page|entire guide).*|did you get the information.*)$",
    re.IGNORECASE,
)


def clean_text(raw: str) -> str:
    """Tidy extracted text into RAG-friendly prose: no page furniture, no runaway blank lines."""
    lines: list[str] = []
    for line in raw.replace("\xa0", " ").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            lines.append("")
            continue
        if _PAGE_NUMBER.match(line) or _BOILERPLATE.match(line):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pdf_to_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # a single broken page should not lose the guide
            log.warning("could not extract a PDF page: %s", exc)
    return clean_text("\n".join(pages))


def html_to_text(soup: BeautifulSoup) -> str:
    """Fallback for leaf pages that publish no guide PDF."""
    main = soup.select_one("main") or soup.body or soup
    stripped = BeautifulSoup(str(main), "html.parser")
    for tag in stripped(["script", "style", "nav", "header", "footer", "form", "noscript"]):
        tag.decompose()
    return clean_text(stripped.get_text("\n"))


# --------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------


def slugify(url: str) -> str:
    path = urlparse(url).path.strip("/") or "index"
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[:120] or "page"


def is_template(url: str, title: str) -> bool:
    """Acas names every fill-in template 'template' in its title and URL slug."""
    return TEMPLATE_MARKER in f"{url} {title}".lower()


def write_document(
    out_dir: Path, url: str, title: str, breadcrumb: list[str], source: str, text: str
) -> Path:
    """One .txt per guide, with a short metadata header the retriever can surface as a citation."""
    path = out_dir / f"{slugify(url)}.txt"
    header = "\n".join(
        [
            f"title: {title}",
            f"url: {url}",
            f"topic: {' > '.join(breadcrumb) if breadcrumb else 'Advice'}",
            f"source: {source}",
            "",
            "---",
            "",
        ]
    )
    path.write_text(header + text + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------------------


@dataclass
class CrawlStats:
    pages_visited: int = 0
    documents_saved: int = 0
    templates_saved: int = 0
    html_fallbacks: int = 0
    skipped_duplicates: int = 0
    failures: list[str] = field(default_factory=list)


def crawl(
    start_url: str,
    out_dir: Path,
    template_dir: Path,
    delay: float = 0.5,
    limit: int | None = None,
    max_depth: int = 6,
) -> tuple[list[dict], list[dict], CrawlStats]:
    session = make_session()
    stats = CrawlStats()
    manifest: list[dict] = []
    template_manifest: list[dict] = []

    out_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    def save(url: str, title: str, breadcrumb: list[str], source: str, text: str) -> Path:
        """Write a document to the content or template folder, and record it in that manifest."""
        template = is_template(url, title)
        path = write_document(
            template_dir if template else out_dir, url, title, breadcrumb, source, text
        )
        entry = {
            "title": title,
            "url": url,
            "topic": breadcrumb,
            "source": source,
            "file": path.name,
            "characters": len(text),
        }
        if template:
            template_manifest.append(entry)
            stats.templates_saved += 1
        else:
            manifest.append(entry)
        stats.documents_saved += 1
        return path

    queue: deque[tuple[str, list[str], int]] = deque([(normalise(start_url), [], 0)])
    seen_pages: set[str] = {normalise(start_url)}
    seen_guides: set[str] = set()

    while queue:
        if limit is not None and stats.documents_saved >= limit:
            log.info("reached --limit %s, stopping", limit)
            break

        url, breadcrumb, depth = queue.popleft()
        response = fetch(session, url, delay)
        if response is None:
            stats.failures.append(url)
            continue

        stats.pages_visited += 1
        soup = BeautifulSoup(response.text, "html.parser")
        title = page_title(soup)
        log.info("[%s] %s", depth, title)

        download_url = guide_download_url(soup)
        if download_url:
            gid = guide_id(download_url)
            if gid in seen_guides:
                stats.skipped_duplicates += 1
                log.debug("guide %s already saved, skipping %s", gid, url)
                continue
            seen_guides.add(gid)

            pdf = fetch(session, download_url, delay)
            text = ""
            source = download_url
            if pdf is not None and pdf.content[:4] == b"%PDF":
                try:
                    text = pdf_to_text(pdf.content)
                except Exception as exc:
                    log.warning("PDF parse failed for %s: %s", download_url, exc)

            if not text:  # PDF missing or unreadable -> keep the page's own text
                text = html_to_text(soup)
                source = url
                stats.html_fallbacks += 1
                log.warning("falling back to HTML text for %s", url)

            if not text:
                stats.failures.append(url)
                continue

            path = save(url, title, breadcrumb, source, text)
            log.info("  saved %s (%s chars)", path.name, len(text))
            continue  # the guide PDF already contains this page's children

        # Not a guide: descend into the boxes.
        if depth >= max_depth:
            log.debug("max depth reached at %s", url)
            continue

        children = box_links(soup)
        if not children:
            # Leaf without a guide PDF and without boxes - keep its HTML text anyway.
            text = html_to_text(soup)
            if text:
                stats.html_fallbacks += 1
                path = save(url, title, breadcrumb, url, text)
                log.info("  saved %s (HTML, %s chars)", path.name, len(text))
            continue

        for child in children:
            if urlparse(child).path.rstrip("/") in SKIP_PATHS:
                continue
            if child in seen_pages:
                continue
            seen_pages.add(child)
            queue.append((child, breadcrumb + [title], depth + 1))

    return manifest, template_manifest, stats


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl acas.org.uk/advice into text documents.")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="guidance output directory")
    parser.add_argument(
        "--templates", type=Path, default=TEMPLATE_DIR, help="template output directory"
    )
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    parser.add_argument("--limit", type=int, default=None, help="stop after N documents")
    parser.add_argument("--max-depth", type=int, default=6, help="maximum box depth to follow")
    parser.add_argument("--start", default=urljoin(BASE_URL, START_PATH), help="start URL")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    manifest, template_manifest, stats = crawl(
        start_url=args.start,
        out_dir=args.out,
        template_dir=args.templates,
        delay=args.delay,
        limit=args.limit,
        max_depth=args.max_depth,
    )

    for directory, entries in ((args.out, manifest), (args.templates, template_manifest)):
        path = directory / MANIFEST_NAME
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("manifest: %s (%s documents)", path, len(entries))

    log.info(
        "done: %s documents from %s pages - %s guidance, %s templates "
        "(%s HTML fallbacks, %s duplicate guides, %s failures)",
        stats.documents_saved,
        stats.pages_visited,
        stats.documents_saved - stats.templates_saved,
        stats.templates_saved,
        stats.html_fallbacks,
        stats.skipped_duplicates,
        len(stats.failures),
    )
    for failure in stats.failures:
        log.warning("failed: %s", failure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
