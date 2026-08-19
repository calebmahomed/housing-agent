import os
from html import escape
from typing import Optional

import requests

from .listing import Listing

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def format_listing(listing: Listing, commute: Optional[str] = None, score: Optional[dict] = None) -> str:
    address = escape(f"{listing.address}, {listing.city}")
    rent = (score or {}).get("total_monthly") or listing.total_monthly
    basis = {"kale": " excl. servicekosten", "inclusief": " all-in"}.get((score or {}).get("rent_basis"), "")
    text = f'<a href="{escape(listing.url)}">{address}</a> — €{rent:.0f}/mo{basis}'
    if listing.source not in ("pararius", "funda"):
        text += "  🏠 direct from makelaar"
    if commute:
        text += f"\n{escape(commute)}"
    if score:
        text += f"\n<b>{score['score']}/10</b> — {escape(score['reason'])}"
    return text


def _post(method: str, payload: dict) -> bool:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=10)
    if not resp.ok:
        print(f"Telegram {method} failed: {resp.status_code} {resp.text}")
    return resp.ok


def send_telegram(text: str) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    _post("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})


def send_notification(caption: str, image_urls: Optional[list] = None) -> None:
    """Plain text if there are no images; a photo (or album) with caption otherwise.
    Falls back to plain text if the photo/album send fails, so a bad image URL
    never silently drops the whole listing."""
    if not image_urls:
        send_telegram(caption)
        return

    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    urls = image_urls[:10]  # Telegram's sendMediaGroup limit
    if len(urls) == 1:
        ok = _post("sendPhoto", {"chat_id": chat_id, "photo": urls[0], "caption": caption, "parse_mode": "HTML"})
    else:
        media = [
            {"type": "photo", "media": url, **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {})}
            for i, url in enumerate(urls)
        ]
        ok = _post("sendMediaGroup", {"chat_id": chat_id, "media": media})

    if not ok:
        send_telegram(caption)
