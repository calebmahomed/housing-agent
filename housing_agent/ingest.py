"""IMAP ingestion of Pararius+/Funda alert emails.

# ponytail: parse_pararius/parse_funda are best-guess regexes against typical
# alert formats — nobody has captured a real one yet (that's Phase 0). Once
# real emails land, update these two functions and their fixtures; nothing
# else in the pipeline needs to change.
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


def _body_text(msg: Message) -> str:
    if msg.is_multipart():
        parts = [p.get_payload(decode=True) for p in msg.walk() if p.get_content_type() == "text/plain"]
        return "\n".join(p.decode(errors="replace") for p in parts if p)
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def parse_pararius(subject: str, body: str) -> Optional[Listing]:
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
    )


def parse_funda(subject: str, body: str) -> Optional[Listing]:
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
    )


PARSERS = {
    "pararius": parse_pararius,
    "funda": parse_funda,
}


def _source_for(from_addr: str) -> Optional[str]:
    if "pararius" in from_addr.lower():
        return "pararius"
    if "funda" in from_addr.lower():
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
        source = _source_for(msg.get("From", ""))
        if source is None:
            continue
        listing = PARSERS[source](msg.get("Subject", ""), _body_text(msg))
        if listing is not None:
            listings.append(listing)

    conn.close()
    conn.logout()
    return listings
