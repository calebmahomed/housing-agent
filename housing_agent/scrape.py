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

import re
import time
from html import unescape
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


# --- Vesteda -----------------------------------------------------------------
# Institutional landlord, large portfolio in the €900-1400 band. Its map widget
# POSTs to this endpoint; the response is the same catalogue the public search
# page shows. No date-added field, so freshness comes from `status` plus the
# seen-state file rather than an age cutoff.
VESTEDA_BASE = "https://www.vesteda.com"
VESTEDA_API = VESTEDA_BASE + "/api/units/search"
# From Vesteda's own bundle: getStatusName() maps 1 "nieuw", 2 "verhuurd",
# 3 "verhuurd onder voorbehoud", 4 "gereserveerd". Only 1 is actually rentable
# — the other three are ~80% of the feed and are already gone.
VESTEDA_AVAILABLE = 1


def fetch_vesteda_listings(max_age_hours: int = 24) -> list[Listing]:
    try:
        resp = requests.post(
            VESTEDA_API,
            headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"},
            json={"s": "", "placeType": 0, "rootId": 1303},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
    except Exception as e:
        print(f"vesteda fetch failed: {e}")
        return []

    listings = []
    for item in items:
        if item.get("status") != VESTEDA_AVAILABLE:
            continue
        rent = item.get("priceUnformatted") or 0
        url, street = item.get("url"), item.get("street")
        if not rent or not url or not street:
            continue
        number = " ".join(str(p) for p in (item.get("houseNumber"), item.get("houseNumberAddition")) if p)
        listings.append(
            Listing(
                source="vesteda",
                external_id=str(item.get("id") or url),
                url=VESTEDA_BASE + url,
                address=f"{street} {number}".strip(),
                city=item.get("city", ""),
                rent=float(rent),
                size_m2=float(item["size"]) if item.get("size") else None,
                bedrooms=item.get("numberOfBedRooms"),
                description=item.get("complex", ""),
                image_urls=[item["imageBig"]] if item.get("imageBig") else [],
                raw=item,
            )
        )
    return listings


# --- ikwilhuren.nu (MVGM) -----------------------------------------------------
# Server-rendered cards, robots.txt allows everything ("Disallow:" with no
# value). Each card carries a "Sinds N dagen online" title, which is a real
# freshness signal — so this source can honour max_age_hours properly.
# Apex, not www: on 2026-08-20 the site started 301ing www -> apex and moved
# behind Cloudflare. requests follows the redirect, so this isn't what broke the
# fetch — it just saves a round trip and makes the failing URL the real one.
IKWILHUREN_BASE = "https://ikwilhuren.nu"
IKWILHUREN_LIST = IKWILHUREN_BASE + "/aanbod/"
CARD_RE = re.compile(r'<div class="card card-woning.*?(?=<div class="card card-woning|\Z)', re.S)
TYPE_PREFIX = re.compile(
    r"^(?:vrijstaande\s+|halfvrijstaande\s+)?"
    r"\w*(?:woning|flat|huis|kamer|studio|penthouse|maisonnette|appartement|loft)\b\s*",
    re.I,
)
IKW_FIELDS = {
    "href": re.compile(r'href="(/object/[^"]+)"'),
    "title": re.compile(r'stretched-link[^>]*>\s*([^<]+?)\s*<'),
    "place": re.compile(r"<span>(\d{4}\s?[A-Z]{2})\s+([^<]+)</span>"),
    "price": re.compile(r"€\s*([\d.]+)"),
    "size": re.compile(r"<span>(\d+)\s*m<sup>2</sup></span>"),
    "beds": re.compile(r"<span>(\d+)\s*slaapkamers?\s*</span>"),
    "days": re.compile(r'title="Sinds ([\d.]+) dagen online"'),
    "img": re.compile(r"src='(//[^']+\.jpg[^']*)'"),
}


def _parse_ikwilhuren_card(card: str, max_age_hours: float) -> Optional[Listing]:
    def grab(key, group=1):
        m = IKW_FIELDS[key].search(card)
        return m.group(group) if m else None

    href, price, place = grab("href"), grab("price"), IKW_FIELDS["place"].search(card)
    if not (href and price and place):
        return None

    days = grab("days")
    if days is not None and float(days) * 24 > max_age_hours:
        return None

    title = unescape(grab("title") or "")
    # titles read "<dwelling type> <address>": "Appartement Dr. H. Colijnstraat
    # 528", "Eengezinswoning Schorsmolen 27". Match the type by its suffix
    # rather than listing every compound Dutch word for a home.
    address = TYPE_PREFIX.sub("", title).strip()
    size, beds, img = grab("size"), grab("beds"), grab("img")
    return Listing(
        source="ikwilhuren",
        external_id=href.strip("/").split("/")[-1],
        url=IKWILHUREN_BASE + href,
        address=address,
        city=unescape(place.group(2)).strip(),
        rent=float(price.replace(".", "")),
        size_m2=float(size) if size else None,
        bedrooms=int(beds) if beds else None,
        description=title,
        image_urls=["https:" + img] if img else [],
        raw={"postal_code": place.group(1), "days_online": days},
    )


def fetch_ikwilhuren_listings(max_age_hours: int = 24, max_pages: int = 5) -> list[Listing]:
    listings = []
    # 1-indexed: ?page=0 and ?page=1 both serve the first page
    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                IKWILHUREN_LIST, params={"page": page}, headers={"User-Agent": UA}, timeout=30
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"ikwilhuren page {page} fetch failed: {e}")
            break
        cards = CARD_RE.findall(resp.text)
        if not cards:
            break
        fresh = [_parse_ikwilhuren_card(c, max_age_hours) for c in cards]
        listings.extend(l for l in fresh if l)
        # cards are ordered newest-first, so once a whole page is too old to
        # qualify there is nothing newer deeper in the list
        if not any(l for l in fresh):
            break
    return listings


# Sources with no date-added field can't honour max_age_hours; main.py seeds
# them on first sight instead of alerting on the whole back catalogue.
UNDATED_SOURCES = {"vesteda"}


def fetch_scraped_listings(max_age_hours: int = 24) -> list[Listing]:
    out = []
    for source, base in PLATFORM_SITES:
        out.extend(fetch_platform_listings(source, base, max_age_hours))
    out.extend(fetch_vesteda_listings(max_age_hours))
    out.extend(fetch_ikwilhuren_listings(max_age_hours))
    return out
