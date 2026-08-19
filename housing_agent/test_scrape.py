"""One-off live test of the makelaar scrape -> Telegram path.

Runs the real pipeline (filters, dedup against real state, detail-page check,
Telegram send) but is READ-ONLY: it never saves seen_listings.json, so a
listing sent here will still be sent normally by the next poll run. Bounded by
--limit so a wide --hours window can't blast the chat.

Usage: python -m housing_agent.test_scrape [hours] [limit]
"""

import sys

import yaml

from .main import SEEN_PATH, prepare
from .notify import send_notification, send_telegram
from .scrape import fetch_scraped_listings
from .state import load


def run(hours: int = 720, limit: int = 3) -> int:
    with open("preferences.yaml") as f:
        prefs = yaml.safe_load(f)

    listings = fetch_scraped_listings(hours)
    seen = load(SEEN_PATH)  # read-only: deliberately never saved back

    send_telegram(
        f"\U0001f9ea Scrape test — {len(listings)} available rental(s) added in the last "
        f"{hours}h at VERRA. Sending up to {limit} that pass your filters. "
        "State is not saved, so these will alert again normally."
    )

    sent = 0
    for listing in listings:
        if sent >= limit:
            break
        item = prepare(listing, prefs, seen)
        if item:
            send_notification(item["caption"], item["image_urls"])
            sent += 1

    if not sent:
        send_telegram("No listings passed the filters in that window.")
    return sent


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 720
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    print(f"sent {run(hours, limit)} test notifications")
