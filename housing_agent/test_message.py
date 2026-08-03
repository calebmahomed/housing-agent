"""One-off Telegram delivery test, with a real Routes API commute lookup
against a fake listing. Not part of the poll pipeline."""

from .commute import commute_highlight
from .listing import Listing
from .notify import format_listing, send_notification, send_telegram

FAKE_LISTING = Listing(
    source="pararius",
    external_id="abc123",
    url="https://www.pararius.nl/huurwoning/den-haag/abc123/prinsegracht-12",
    address="Prinsegracht 12",
    city="Den Haag",
    rent=1450,
    service_costs=75,
    size_m2=75,
    bedrooms=3,
    # ponytail: placeholder stock photos, not real listing images (Phase 0 hasn't
    # captured a real alert email yet, so there's nothing real to point at).
    image_urls=[
        "https://picsum.photos/id/1040/800/600",
        "https://picsum.photos/id/1041/800/600",
    ],
)

if __name__ == "__main__":
    send_telegram("Hi Caleb, merhaba Selin \U0001F44B\nTesting the Routes API commute lookup with a fake listing.")

    commute = commute_highlight(f"{FAKE_LISTING.address}, {FAKE_LISTING.city}")
    send_notification(format_listing(FAKE_LISTING, commute), FAKE_LISTING.image_urls)
