import os
from typing import Optional

import requests

from .listing import Listing

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def format_listing(listing: Listing, commute: Optional[str] = None) -> str:
    text = f"{listing.address}, {listing.city} — €{listing.total_monthly:.0f}/mo\n{listing.url}"
    if commute:
        text += f"\n{commute}"
    return text


def _post(method: str, payload: dict) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=10)


def send_telegram(text: str) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    _post("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})


def send_notification(caption: str, image_urls: Optional[list] = None) -> None:
    """Plain text if there are no images; a photo (or album) with caption otherwise."""
    if not image_urls:
        send_telegram(caption)
        return

    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    urls = image_urls[:10]  # Telegram's sendMediaGroup limit
    if len(urls) == 1:
        _post("sendPhoto", {"chat_id": chat_id, "photo": urls[0], "caption": caption})
        return

    media = [{"type": "photo", "media": url, **({"caption": caption} if i == 0 else {})} for i, url in enumerate(urls)]
    _post("sendMediaGroup", {"chat_id": chat_id, "media": media})
