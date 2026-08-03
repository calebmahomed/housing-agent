import os
from typing import Optional

import requests

from .listing import Listing


def format_listing(listing: Listing, commute: Optional[str] = None) -> str:
    text = f"{listing.address}, {listing.city} — €{listing.total_monthly:.0f}/mo\n{listing.url}"
    if commute:
        text += f"\n{commute}"
    return text


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=10,
    )
