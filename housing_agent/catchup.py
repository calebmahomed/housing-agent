"""Recovery path: re-scan recent mail (not just unseen) and notify on
anything that passes filters but isn't already recorded in seen_listings.json
— covers cases where a run's state commit failed to persist (e.g. a git
push race) even though the emails were already consumed. Sends immediately,
ignoring quiet hours, since it's an explicit on-demand catch-up."""

import sys

import yaml

from .commute import commute_highlight
from .dedup import is_duplicate
from .detail_check import passes_detail_page_check
from .filters import passes_hard_filters
from .ingest import fetch_recent_alert_emails
from .notify import format_listing, send_notification
from .state import load, save

SEEN_PATH = "data/seen_listings.json"


def run(hours: int = 12) -> int:
    with open("preferences.yaml") as f:
        prefs = yaml.safe_load(f)

    seen = load(SEEN_PATH)
    sent = 0
    for listing in fetch_recent_alert_emails(hours):
        if not passes_hard_filters(listing, prefs):
            continue
        if is_duplicate(listing, seen):
            continue
        seen.append(listing.to_seen_record())
        if not passes_detail_page_check(listing.url, prefs.get("exclude_phrases", [])):
            continue
        commute = commute_highlight(f"{listing.address}, {listing.city}")
        send_notification(format_listing(listing, commute), listing.image_urls)
        sent += 1

    save(SEEN_PATH, seen)
    return sent


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    count = run(hours)
    print(f"sent {count} catch-up notifications")
