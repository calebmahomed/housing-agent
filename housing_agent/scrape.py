"""Direct scrape of makelaar sites that publish their own listings.

VERRA (verra.nl) exposes its whole catalogue as JSON at
/en/realtime-listings/consumer — no HTML parsing, no Playwright, no
Cloudflare challenge, and robots.txt allows it (verified 2026-08-19).
Faster than waiting for the same flat to show up in a Pararius+ alert;
dedup.py suppresses the aggregator copy that arrives later.
"""

import hashlib
import time
from typing import Optional

import requests

from .listing import Listing

VERRA_FEED = "https://www.verra.nl/en/realtime-listings/consumer"
VERRA_BASE = "https://www.verra.nl"
UA = "Mozilla/5.0 (compatible; housing-agent/1.0)"


def _verra_to_listing(item: dict) -> Optional[Listing]:
    rent = item.get("rentalsPrice") or 0
    if not rent:
        return None
    # "€ 2.195 p.m. ex." = kale huur, servicekosten on top and not published;
    # "incl." means the quoted figure already covers them. We can't know the
    # ex-listings' servicekosten from the feed, so total_monthly is the floor.
    price_label = item.get("price", "")
    return Listing(
        source="verra",
        external_id=item["_id"],
        url=VERRA_BASE + item["url"],
        address=item.get("address", ""),
        city=item.get("city", ""),
        rent=float(rent),
        size_m2=float(item["livingSurface"]) if item.get("livingSurface") else None,
        bedrooms=item.get("bedrooms"),
        description=price_label,
        image_urls=[item["photo"]] if item.get("photo") else [],
        raw=item,
    )


def fetch_verra_listings(max_age_hours: int = 24) -> list[Listing]:
    """Available rentals added within max_age_hours.

    # ponytail: the age cutoff is what stops the first run alerting on all 79
    # currently-available rentals. Widen it only alongside a seeded state file.
    """
    try:
        resp = requests.get(VERRA_FEED, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"verra feed fetch failed: {e}")
        return []

    cutoff = time.time() - max_age_hours * 3600
    listings = []
    for item in items:
        if not item.get("isRentals") or item.get("status") != "Available":
            continue
        if item.get("added", 0) < cutoff:
            continue
        listing = _verra_to_listing(item)
        if listing:
            listings.append(listing)
    return listings


SCRAPERS = [fetch_verra_listings]


def fetch_scraped_listings(max_age_hours: int = 24) -> list[Listing]:
    out = []
    for scraper in SCRAPERS:
        out.extend(scraper(max_age_hours))
    return out
