"""IMAP ingestion of Pararius+/Funda alert emails.

# ponytail: parse_pararius is built and verified against a real captured
# Pararius alert email (2026-08-04). parse_funda is still best-guess
# regexes pending a real Funda sample — update it the same way once one
# arrives.
"""

import email
import hashlib
import imaplib
import os
import re
from email.header import decode_header
from email.message import Message
from typing import Optional

from .listing import Listing

IMAP_HOST = "IMAP_HOST"
IMAP_USER = "IMAP_USER"
IMAP_PASSWORD = "IMAP_PASSWORD"
IMAP_FOLDER = "INBOX"  # move behind a label/folder filter once alerts are live


def _decode_subject(raw: str) -> str:
    parts = decode_header(raw)
    return "".join(t.decode(enc or "utf-8") if isinstance(t, bytes) else t for t, enc in parts)


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
# sendgrid/mcauto-images serve Pararius's own template chrome (logo, spacers),
# not property photos — verified against a real alert email's HTML part.
IMAGE_SKIP_WORDS = ("logo", "icon", "pixel", "spacer", "tracking", "sendgrid", "mcauto-images")


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


def _stable_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


# Parses the property card from the HTML part, not plain text: a manually
# forwarded email (Outlook re-generates plain text from HTML on forward) can
# mangle special characters (€, ², ·) into U+FFFD, and drops the *bold*
# markup the plain-text version relies on. The HTML tag structure and the
# address link's href survive forwarding intact, so anchor on those instead.
# � tolerance verified against a real forwarded copy (2026-08-04).
PARARIUS_HTML_RE = re.compile(
    r'href="(https?://[^"]+)"[^>]*>\s*<span[^>]*>\s*<strong>([^<]{1,80})</strong>\s*</span>\s*</a>\s*<br\s*/?>\s*'
    r"<strong>[€�]?\s?([\d.,]+)\s*per month</strong>\s*<br\s*/?>\s*"
    r"(\d+)\s?m[²�]\s*[·�]\s*(\d+)\s?bedroom",
    re.I | re.DOTALL,
)
PARARIUS_CITY_RE = re.compile(r"\bin\s+([A-Za-zÀ-ÿ\s]+)$")  # subject header survives forwarding intact


def parse_pararius(subject: str, body: str, html: str = "") -> Optional[Listing]:
    detail_m = PARARIUS_HTML_RE.search(html)
    city_m = PARARIUS_CITY_RE.search(subject.strip())
    if not (detail_m and city_m):
        return None

    url, address_raw, rent_raw, size_raw, bedrooms_raw = detail_m.groups()
    address = address_raw.strip()
    rent = float(rent_raw.replace(",", ""))  # Pararius uses "1,301" = thousands comma, English format
    size_m2 = float(size_raw)
    bedrooms = int(bedrooms_raw)
    city = city_m.group(1).strip()

    return Listing(
        source="pararius",
        external_id=_stable_id("pararius", address, city, rent, size_m2),
        url=url,
        address=address,
        city=city,
        rent=rent,
        size_m2=size_m2,
        bedrooms=bedrooms,
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
        subject = _decode_subject(msg.get("Subject", ""))
        listing = PARSERS[source](subject, body, _part_text(msg, "text/html"))
        if listing is not None:
            listings.append(listing)

    conn.close()
    conn.logout()
    return listings
