"""Direct scrape of makelaar sites that publish their own listings.

Several Dutch agencies run the same "realtime-listings" website product, which
serves the whole catalogue as JSON at one shared path — no HTML parsing, no
Playwright, no Cloudflare challenge, and robots.txt allows it. So each new
agency on that product costs one line in PLATFORM_SITES, not a new scraper.

Scraped listings beat waiting for the same flat to appear in a Pararius+
alert; dedup.py suppresses the aggregator copy that arrives later.

# ponytail: probed ~40 agency and landlord sites on 2026-08-19 — only the two
# below use this product. Everything else renders listings client-side and
# needs its own Playwright + selector adapter, which is the per-site
# maintenance the plan warned about. Add those only when the stock justifies it.
"""

import time
from typing import Optional

import requests

from .listing import Listing

FEED_PATH = "/en/realtime-listings/consumer"
PLATFORM_SITES = [
    ("verra", "https://www.verra.nl"),
    ("estata", "https://www.estata.nl"),
]
UA = "Mozilla/5.0 (compatible; housing-agent/1.0)"

# The feed rents out parking spaces and storage too — mainType "other", 0 m²,
# €150-ish. Cheap enough to sail through the rent filter, so exclude by type.
LIVEABLE_TYPES = {"apartment", "house"}


def _to_listing(item: dict, source: str, base: str) -> Optional[Listing]:
    rent = item.get("rentalsPrice") or 0
    if not rent:
        return None
    if item.get("mainType") not in LIVEABLE_TYPES or not item.get("livingSurface"):
        return None
    # sites on this product don't populate the feed identically — estata.nl
    # serves entries with no _id at all. Skip anything we can't link to or
    # identify rather than inventing a key that dedup would then mistrust.
    path = item.get("url")
    external_id = item.get("_id") or path
    if not path or not external_id:
        return None
    # "€ 2.195 p.m. ex." = kale huur, servicekosten on top and not published;
    # "incl." means the quoted figure already covers them. We can't know the
    # ex-listings' servicekosten from the feed, so total_monthly is the floor.
    return Listing(
        source=source,
        external_id=external_id,
        url=base + path,
        address=item.get("address", ""),
        city=item.get("city", ""),
        rent=float(rent),
        size_m2=float(item["livingSurface"]),
        bedrooms=item.get("bedrooms"),
        description=item.get("price", ""),
        image_urls=[item["photo"]] if item.get("photo") else [],
        raw=item,
    )


def fetch_platform_listings(source: str, base: str, max_age_hours: int = 24) -> list[Listing]:
    """Available rentals added within max_age_hours.

    # ponytail: the age cutoff is what stops a first run alerting on every
    # currently-available rental. Widen it only alongside a seeded state file.
    """
    try:
        resp = requests.get(base + FEED_PATH, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"{source} feed fetch failed: {e}")
        return []

    cutoff = time.time() - max_age_hours * 3600
    listings = []
    for item in items:
        if not item.get("isRentals") or item.get("status") != "Available":
            continue
        if item.get("added", 0) < cutoff:
            continue
        listing = _to_listing(item, source, base)
        if listing:
            listings.append(listing)
    return listings


def fetch_scraped_listings(max_age_hours: int = 24) -> list[Listing]:
    out = []
    for source, base in PLATFORM_SITES:
        out.extend(fetch_platform_listings(source, base, max_age_hours))
    return out
