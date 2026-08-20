import os
from html import escape
from typing import Optional

import requests

from .listing import Listing

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# Aggregators are the slow path — the flat has already been public for a
# while by the time their alert lands. Anything else is a makelaar's own site,
# where we're likely first, so it gets the loud badge.
AGGREGATORS = {"pararius": "\U0001f535 Pararius", "funda": "\U0001f7e0 Funda"}
MAKELAAR_NAMES = {"verra": "VERRA Makelaars", "estata": "Estata Makelaars"}


def source_badge(source: str) -> str:
    if source in AGGREGATORS:
        return AGGREGATORS[source]
    name = MAKELAAR_NAMES.get(source, source.replace("_", " ").title())
    return f"\U0001f534 <b>DIRECT — {escape(name)}</b>"


def format_listing(listing: Listing, commute: Optional[str] = None, score: Optional[dict] = None) -> str:
    address = escape(f"{listing.address}, {listing.city}")
    rent = (score or {}).get("total_monthly") or listing.total_monthly
    basis = {"kale": " excl. servicekosten", "inclusief": " all-in"}.get((score or {}).get("rent_basis"), "")
    text = f"{source_badge(listing.source)}\n"
    text += f'<a href="{escape(listing.url)}">{address}</a> — €{rent:.0f}/mo{basis}'
    bits = []
    if listing.size_m2:
        bits.append(f"{listing.size_m2:.0f} m²")
    if listing.bedrooms:
        bits.append(f"{listing.bedrooms} bd")
    if bits:
        text += "  ·  " + " · ".join(bits)
    if commute:
        text += f"\n{escape(commute)}"
    if score:
        text += f"\n<b>{score['score']}/10</b> — {escape(score['reason'])}"
    return text


def _post(method: str, payload: dict) -> bool:
    """False on any failure, never raises.

    A read timeout here used to propagate out of main() and abort the run
    before it saved state (poll run 32283629432) — losing the record of
    everything already sent that run. Delivery is best-effort; the state file
    is not.

    Telegram fetches photo URLs itself on sendPhoto/sendMediaGroup, so those
    calls are legitimately slow — hence the timeout well above the 10s that
    was timing out.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        resp = requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=30)
    except Exception as e:
        print(f"Telegram {method} failed: {type(e).__name__}: {e}")
        return False
    if not resp.ok:
        print(f"Telegram {method} failed: {resp.status_code} {resp.text}")
    return resp.ok


def feedback_buttons(key: Optional[str]) -> Optional[dict]:
    """The 👍/👎 row. The 👎 reason row is built by the webhook when it handles
    the tap — keep `feedback.REASONS` and the webhook's copy in step."""
    if not key:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001F44D Interested", "callback_data": f"f:{key}:interested"},
                {"text": "\U0001F44E Pass", "callback_data": f"f:{key}:pass"},
            ]
        ]
    }


def send_telegram(text: str, reply_markup: Optional[dict] = None) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _post("sendMessage", payload)


def send_notification(caption: str, image_urls: Optional[list] = None, key: Optional[str] = None) -> None:
    """Plain text if there are no images; a photo (or album) with caption otherwise.
    Falls back to plain text if the photo/album send fails, so a bad image URL
    never silently drops the whole listing.

    `key` attaches the feedback buttons. sendMediaGroup takes no reply_markup —
    an album therefore goes out uncaptioned and the caption follows as its own
    message carrying the buttons, rather than dropping the extra photos.
    """
    markup = feedback_buttons(key)
    if not image_urls:
        send_telegram(caption, markup)
        return

    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    urls = image_urls[:10]  # Telegram's sendMediaGroup limit
    if len(urls) == 1:
        payload = {"chat_id": chat_id, "photo": urls[0], "caption": caption, "parse_mode": "HTML"}
        if markup:
            payload["reply_markup"] = markup
        ok = _post("sendPhoto", payload)
    elif markup:
        media = [{"type": "photo", "media": url} for url in urls]
        ok = _post("sendMediaGroup", {"chat_id": chat_id, "media": media})
        if ok:
            send_telegram(caption, markup)
            return
    else:
        media = [
            {"type": "photo", "media": url, **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {})}
            for i, url in enumerate(urls)
        ]
        ok = _post("sendMediaGroup", {"chat_id": chat_id, "media": media})

    if not ok:
        send_telegram(caption, markup)
