"""IMAP ingestion of Pararius+/Funda alert emails.

# ponytail: parse_pararius/parse_funda (including image-URL extraction) are
# best-guess regexes against typical alert formats — nobody has captured a
# real one yet (that's Phase 0). Once real emails land, update these two
# functions and their fixtures; nothing else in the pipeline needs to change.
"""

import email
import imaplib
import os
import re
from email.message import Message
from typing import Optional

from .listing import Listing

IMAP_HOST = "IMAP_HOST"
IMAP_USER = "IMAP_USER"
IMAP_PASSWORD = "IMAP_PASSWORD"
IMAP_FOLDER = "INBOX"  # move behind a label/folder filter once alerts are live


def _part_text(msg: Message, content_type: str) -> str:
    if msg.is_multipart():
        parts = [p.get_payload(decode=True) for p in msg.walk() if p.get_content_type() == content_type]
        return "\n".join(p.decode(errors="replace") for p in parts if p)
    if msg.get_content_type() != content_type:
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def _body_text(msg: Message) -> str:
    return _part_text(msg, "text/plain")


IMAGE_URL_RE = re.compile(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', re.I)
IMAGE_SKIP_WORDS = ("logo", "icon", "pixel", "spacer", "tracking")


def extract_image_urls(html: str, limit: int = 5) -> list:
    urls = []
    for url in IMAGE_URL_RE.findall(html):
        if any(skip in url.lower() for skip in IMAGE_SKIP_WORDS):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def parse_pararius(subject: str, body: str, html: str = "") -> Optional[Listing]:
    url_m = re.search(r"https?://www\.pararius\.nl/\S+", body)
    addr_m = re.search(r"^(.*?),\s*(.+)$", subject.strip())
    rent_m = re.search(r"€\s?([\d.,]+)\s*(?:per maand|p/m|kale huur)", body, re.I)
    size_m = re.search(r"(\d+)\s?m2", body, re.I)
    if not (url_m and addr_m and rent_m):
        return None
    return Listing(
        source="pararius",
        external_id=url_m.group(0).rstrip("/").rsplit("/", 1)[-1],
        url=url_m.group(0),
        address=addr_m.group(1).strip(),
        city=addr_m.group(2).strip(),
        rent=float(rent_m.group(1).replace(".", "").replace(",", ".")),
        size_m2=float(size_m.group(1)) if size_m else None,
        description=body,
        image_urls=extract_image_urls(html),
    )


def parse_funda(subject: str, body: str, html: str = "") -> Optional[Listing]:
    url_m = re.search(r"https?://www\.funda\.nl/\S+", body)
    addr_m = re.search(r"^(.*?),\s*(.+)$", subject.strip())
    rent_m = re.search(r"€\s?([\d.,]+)\s*(?:per maand|p/m|kosten koper)?", body, re.I)
    size_m = re.search(r"(\d+)\s?m2", body, re.I)
    if not (url_m and addr_m and rent_m):
        return None
    return Listing(
        source="funda",
        external_id=url_m.group(0).rstrip("/").rsplit("/", 1)[-1],
        url=url_m.group(0),
        address=addr_m.group(1).strip(),
        city=addr_m.group(2).strip(),
        rent=float(rent_m.group(1).replace(".", "").replace(",", ".")),
        size_m2=float(size_m.group(1)) if size_m else None,
        description=body,
        image_urls=extract_image_urls(html),
    )


PARSERS = {
    "pararius": parse_pararius,
    "funda": parse_funda,
}


def _source_for(from_addr: str, body: str = "") -> Optional[str]:
    """Prefer the From header, but fall back to a body URL match — a manually
    forwarded email (vs. a true mail-flow auto-forward) rewrites From to the
    forwarder's own address, so the original sender is gone from the headers."""
    haystack = from_addr.lower() + "\n" + body.lower()
    if "pararius" in haystack:
        return "pararius"
    if "funda" in haystack:
        return "funda"
    return None


def fetch_new_alert_emails() -> list[Listing]:
    """Connect over IMAP, read unseen mail, parse into Listings, mark seen."""
    conn = imaplib.IMAP4_SSL(os.environ[IMAP_HOST])
    conn.login(os.environ[IMAP_USER], os.environ[IMAP_PASSWORD])
    conn.select(IMAP_FOLDER)

    _, data = conn.search(None, "UNSEEN")
    listings = []
    for num in data[0].split():
        _, msg_data = conn.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        body = _body_text(msg)
        source = _source_for(msg.get("From", ""), body)
        if source is None:
            continue
        listing = PARSERS[source](msg.get("Subject", ""), body, _part_text(msg, "text/html"))
        if listing is not None:
            listings.append(listing)

    conn.close()
    conn.logout()
    return listings
