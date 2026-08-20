"""One-off Telegram delivery test, with a real Routes API commute lookup and a
real Claude scoring call against a fake listing. Not part of the poll pipeline.

Scoring is here rather than in test_scrape because that one dedups against real
state, so once state is warm it sends nothing and exercises nothing.
"""

from .commute import commute_highlight
from .config import load_prefs
from .feedback import key as feedback_key
from .listing import Listing
from .notify import format_listing, send_notification, send_telegram
from .score import score_listing

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

# Enough of a page for scoring to resolve kale vs. inclusief — the thing the
# advertised rent alone can't tell us.
FAKE_PAGE_TEXT = """Prinsegracht 12, Den Haag. Huurprijs € 1.450 per maand kale huur,
exclusief servicekosten van € 75 per maand. Oppervlakte 75 m². 3 slaapkamers.
Gestoffeerd, eigen balkon op het zuiden. Beschikbaar per direct. Inkomenseis:
3x de kale huurprijs bruto per maand. Geen huisdieren toegestaan."""


if __name__ == "__main__":
    send_telegram("Hi Caleb, merhaba Selin \U0001F44B\nTesting the Routes API commute lookup with a fake listing.")

    commute = commute_highlight(f"{FAKE_LISTING.address}, {FAKE_LISTING.city}")
    score = score_listing(FAKE_LISTING, FAKE_PAGE_TEXT, load_prefs())
    print(f"score: {score}")  # None means the Claude call failed — see the log line above
    # keyed so the feedback buttons render: tapping one exercises the whole
    # webhook -> feedback.yml -> commit path. The fake listing isn't in state,
    # so the recorded entry resolves to nothing and examples() skips it.
    send_notification(
        format_listing(FAKE_LISTING, commute, score),
        FAKE_LISTING.image_urls,
        feedback_key(FAKE_LISTING.source, FAKE_LISTING.external_id),
    )
