import itertools
from typing import Optional

import yaml

from .commute import commute_info, within_commute
from .dedup import is_duplicate
from .detail_check import contains_excluded_phrase, fetch_page_text
from .filters import passes_hard_filters
from .ingest import fetch_new_alert_emails
from .listing import Listing
from .notify import format_listing, send_notification
from .quiet_hours import in_quiet_hours
from .scrape import UNDATED_SOURCES, fetch_scraped_listings
from .score import score_listing
from .state import load, save

SEEN_PATH = "data/seen_listings.json"
QUEUED_PATH = "data/queued_listings.json"


def prepare(listing: Listing, prefs: dict, seen: list, seeding: set = frozenset()) -> Optional[dict]:
    """Filter, dedup, enrich. None means don't notify. Mutates `seen`.
    Shared by the poll run and /catchup so the two can't drift apart.

    Sources in `seeding` are recorded but never alerted on — see main()."""
    if not passes_hard_filters(listing, prefs):
        return None
    if is_duplicate(listing, seen):
        return None
    seen.append(listing.to_seen_record())
    if listing.source in seeding:
        return None

    # commute before the detail page: one API round trip beats loading a page
    # for somewhere we'd reject on travel time anyway
    commute = commute_info(f"{listing.address}, {listing.city}")
    if not within_commute(commute, prefs):
        return None

    page_text = fetch_page_text(listing.url)
    if contains_excluded_phrase(page_text, prefs.get("exclude_phrases", [])):
        return None

    score = score_listing(listing, page_text, prefs) if page_text else None
    return {"caption": format_listing(listing, commute["text"], score), "image_urls": listing.image_urls}


def main() -> None:
    with open("preferences.yaml") as f:
        prefs = yaml.safe_load(f)

    seen = load(SEEN_PATH)
    queued = load(QUEUED_PATH)

    # Sources that publish no date-added field can't honour an age cutoff, so
    # the first time one appears its entire back catalogue looks new. Record it
    # silently that run and alert only on what shows up afterwards.
    known_sources = {record.get("source") for record in seen}
    seeding = {s for s in UNDATED_SOURCES if s not in known_sources}
    if seeding:
        print(f"seeding (recording without alerting) for new source(s): {sorted(seeding)}")

    to_notify = list(queued)  # anything queued from a previous quiet-hours run
    # scraped first: same flat from the makelaar beats the aggregator's copy,
    # and dedup then suppresses the Pararius/Funda email when it lands.
    for listing in itertools.chain(fetch_scraped_listings(), fetch_new_alert_emails()):
        item = prepare(listing, prefs, seen, seeding)
        if item:
            to_notify.append(item)

    if in_quiet_hours():
        save(QUEUED_PATH, to_notify)
    else:
        for item in to_notify:
            send_notification(item["caption"], item["image_urls"])
        save(QUEUED_PATH, [])

    save(SEEN_PATH, seen)


if __name__ == "__main__":
    main()
