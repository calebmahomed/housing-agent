"""Plain assert-based self-check. Run: python test_housing_agent.py"""

from datetime import datetime
from pathlib import Path

from housing_agent.commute import _parse_duration_seconds, format_minutes
from housing_agent.dedup import is_duplicate
from housing_agent.detail_check import _strip_html, contains_excluded_phrase
from housing_agent.filters import passes_hard_filters
from housing_agent.ingest import _source_for, extract_image_urls, parse_funda, parse_pararius
from housing_agent.listing import Listing
from housing_agent.notify import format_listing
from housing_agent.quiet_hours import in_quiet_hours
from housing_agent.scrape import _verra_to_listing

PREFS = {
    "cities": ["Den Haag", "Delft"],
    "annual_income": 55000,
    "income_to_rent_ratio": 3,
    "min_bedrooms": 2,
    "exclude_phrases": ["55+", "alleen studenten"],
}


def load_fixture(name: str) -> tuple[str, str]:
    text = Path("fixtures", name).read_text()
    subject_line, _, body = text.partition("\n\n")
    subject = subject_line.removeprefix("Subject: ").strip()
    return subject, body


def test_parse_pararius():
    # fixture is a real captured Pararius+ alert email (2026-08-04)
    subject, body = load_fixture("pararius_alert.txt")
    html = Path("fixtures", "pararius_alert.html").read_text()
    listing = parse_pararius(subject, body, html)
    assert listing is not None
    assert listing.address == "Rokin"
    assert listing.city == "Amsterdam"
    assert listing.rent == 1301.0
    assert listing.size_m2 == 50.0
    assert listing.bedrooms == 1
    assert "pararius.nl" in listing.url
    assert listing.image_urls == ["https://casco-media-prod.global.ssl.fastly.net/photo/22d538909e9d77dfea0bc780435d5242.jpg"]


def test_parse_pararius_survives_forward_encoding_corruption():
    # a manual Outlook forward regenerates the body from HTML and mangles
    # €/²/· into U+FFFD — verified against a real forwarded copy (2026-08-04)
    subject = "Fw: Just found for you: €1,495 per month, Godetiaweg in Den Haag"  # subject header survives forwarding intact
    html = Path("fixtures", "pararius_alert_forwarded.html").read_text()
    listing = parse_pararius(subject, "", html)
    assert listing is not None
    assert listing.address == "Godetiaweg"
    assert listing.city == "Den Haag"
    assert listing.rent == 1495.0
    assert listing.size_m2 == 66.0
    assert listing.bedrooms == 1


def test_parse_funda():
    subject, body = load_fixture("funda_alert.txt")
    listing = parse_funda(subject, body)
    assert listing is not None
    assert listing.address == "Voorstraat 5"
    assert listing.city == "Delft"
    assert listing.rent == 1800.0


def test_total_monthly_uses_service_costs():
    listing = Listing(source="x", external_id="1", url="", address="A", city="Delft", rent=1950, service_costs=300)
    assert listing.total_monthly == 2250


def test_hard_filters_reject_over_budget_on_total():
    # rent alone is under budget, but rent + service_costs isn't
    listing = Listing(source="x", external_id="1", url="", address="A", city="Delft", rent=2100, service_costs=200)
    assert not passes_hard_filters(listing, PREFS)


def test_hard_filters_reject_wrong_city():
    listing = Listing(source="x", external_id="1", url="", address="A", city="Amsterdam", rent=1500)
    assert not passes_hard_filters(listing, PREFS)


def test_cross_source_dedup():
    seen = [{"address": "Voorstraat 5, Delft", "size_m2": 60, "total_monthly": 1800}]
    dup = Listing(source="funda", external_id="2", url="", address="voorstraat  5, delft", city="Delft", rent=1850, size_m2=61)
    assert is_duplicate(dup, seen)


def test_hard_filters_reject_excluded_phrase():
    listing = Listing(source="x", external_id="1", url="", address="A", city="Delft", rent=1000,
                       description="Woning alleen voor 55-plussers, alleen studenten toegestaan")
    assert not passes_hard_filters(listing, PREFS)


def test_extract_image_urls_skips_logos():
    html = (
        '<img src="https://cdn.example.com/photos/kitchen.jpg">'
        '<img src="https://cdn.example.com/logo.png">'
        '<img src="https://cdn.example.com/photos/kitchen.jpg">'
    )
    assert extract_image_urls(html) == ["https://cdn.example.com/photos/kitchen.jpg"]


def test_source_for_falls_back_to_body_when_from_header_is_forwarder():
    # a manually forwarded email rewrites From to the forwarder's own address
    assert _source_for("caleb@fastmail.com", body="check out https://www.pararius.nl/x") == "pararius"
    assert _source_for("caleb@fastmail.com", body="no relevant links here") is None


def test_contains_excluded_phrase_case_insensitive():
    assert contains_excluded_phrase("Only for STUDENTS, min 1 year lease", ["students"])
    assert not contains_excluded_phrase("Great apartment, no restrictions", ["students"])


def test_strip_html_drops_scripts_and_tags():
    text = _strip_html("<p>Huur €1.500</p><script>var x = 'alleen studenten';</script>")
    assert "Huur €1.500" in text
    assert "alleen studenten" not in text  # script contents must not trip the phrase filter


def test_verra_item_maps_to_listing():
    listing = _verra_to_listing(
        {
            "_id": "abc123",
            "url": "/en/listings/residential/rotterdam/factorij-129/abc123",
            "address": "Factorij 129",
            "city": "Rotterdam",
            "isRentals": True,
            "rentalsPrice": 2195,
            "price": "&euro; 2.195 p.m. ex.",
            "livingSurface": 107,
            "bedrooms": 3,
            "photo": "https://media02.ogonline.nl/x.jpg",
        }
    )
    assert listing.source == "verra"
    assert listing.url.startswith("https://www.verra.nl/en/listings/")
    assert listing.rent == 2195 and listing.size_m2 == 107 and listing.bedrooms == 3
    assert listing.image_urls == ["https://media02.ogonline.nl/x.jpg"]


def test_verra_sale_listing_is_skipped():
    # sales entries carry rentalsPrice 0 and must never reach the filters
    assert _verra_to_listing({"_id": "x", "url": "/en/l/x", "isRentals": False, "rentalsPrice": 0}) is None


def test_format_listing_prefers_llm_total_over_advertised_rent():
    listing = Listing(
        source="verra", external_id="x", url="https://verra.nl/x",
        address="Factorij 129", city="Rotterdam", rent=2195,
    )
    plain = format_listing(listing)
    assert "€2195/mo" in plain and "8/10" not in plain
    scored = format_listing(listing, None, {"score": 8, "reason": "Big, close to work.",
                                            "rent_basis": "kale", "total_monthly": 2350})
    assert "€2350/mo excl. servicekosten" in scored
    assert "8/10" in scored and "Big, close to work." in scored


def test_source_badges_distinguish_direct_from_aggregator():
    def badge(source):
        return format_listing(Listing(source=source, external_id="x", url="https://e.nl/x",
                                      address="A 1", city="Delft", rent=1400)).splitlines()[0]

    assert badge("verra") == "\U0001f534 <b>DIRECT — VERRA Makelaars</b>"
    assert badge("pararius") == "\U0001f535 Pararius"
    assert badge("funda") == "\U0001f7e0 Funda"
    # an unmapped scraper still reads as direct rather than silently looking like an aggregator
    assert badge("de_boer") == "\U0001f534 <b>DIRECT — De Boer</b>"


def test_format_listing_shows_size_and_bedrooms_when_known():
    base = dict(source="verra", external_id="x", url="https://e.nl/x", address="A 1", city="Delft", rent=1400)
    assert "62 m² · 2 bd" in format_listing(Listing(**base, size_m2=62, bedrooms=2))
    assert "·" not in format_listing(Listing(**base)).split("\n")[1]  # nothing dangling when unknown


def test_parse_duration_seconds():
    assert _parse_duration_seconds("1080s") == 1080


def test_format_minutes():
    assert format_minutes(45) == "45min"
    assert format_minutes(65) == "1h 5min"
    assert format_minutes(120) == "2h"


def test_quiet_hours_wraps_midnight():
    assert in_quiet_hours(datetime(2026, 1, 1, 3, 0), start=23, end=8)
    assert not in_quiet_hours(datetime(2026, 1, 1, 12, 0), start=23, end=8)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
