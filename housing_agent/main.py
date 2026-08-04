import yaml

from .commute import commute_highlight
from .dedup import is_duplicate
from .detail_check import passes_detail_page_check
from .filters import passes_hard_filters
from .ingest import fetch_new_alert_emails
from .notify import format_listing, send_notification
from .quiet_hours import in_quiet_hours
from .state import load, save

SEEN_PATH = "data/seen_listings.json"
QUEUED_PATH = "data/queued_listings.json"


def main() -> None:
    with open("preferences.yaml") as f:
        prefs = yaml.safe_load(f)

    seen = load(SEEN_PATH)
    queued = load(QUEUED_PATH)

    to_notify = list(queued)  # anything queued from a previous quiet-hours run
    for listing in fetch_new_alert_emails():
        if not passes_hard_filters(listing, prefs):
            continue
        if is_duplicate(listing, seen):
            continue
        seen.append(listing.to_seen_record())
        if not passes_detail_page_check(listing.url, prefs.get("exclude_phrases", [])):
            continue
        commute = commute_highlight(f"{listing.address}, {listing.city}")
        to_notify.append({"caption": format_listing(listing, commute), "image_urls": listing.image_urls})

    if in_quiet_hours():
        save(QUEUED_PATH, to_notify)
    else:
        for item in to_notify:
            send_notification(item["caption"], item["image_urls"])
        save(QUEUED_PATH, [])

    save(SEEN_PATH, seen)


if __name__ == "__main__":
    main()
