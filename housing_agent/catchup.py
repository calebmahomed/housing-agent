"""Recovery path: re-scan recent mail (not just unseen) and notify on
anything that passes filters but isn't already recorded in seen_listings.json
— covers cases where a run's state commit failed to persist (e.g. a git
push race) even though the emails were already consumed. Sends immediately,
ignoring quiet hours, since it's an explicit on-demand catch-up."""

import sys

from .config import load_prefs, require_env
from .ingest import fetch_recent_alert_emails
from .main import SEEN_PATH, prepare
from .notify import send_notification
from .state import load, save


def run(hours: int = 12) -> int:
    require_env()
    prefs = load_prefs()

    seen = load(SEEN_PATH)
    sent = 0
    for listing in fetch_recent_alert_emails(hours):
        item = prepare(listing, prefs, seen)
        if item:
            send_notification(item["caption"], item["image_urls"], item.get("key"))
            sent += 1

    save(SEEN_PATH, seen)
    return sent


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    count = run(hours)
    print(f"sent {count} catch-up notifications")
