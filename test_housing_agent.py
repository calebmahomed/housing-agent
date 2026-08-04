"""Plain assert-based self-check. Run: python test_housing_agent.py"""

from datetime import datetime
from pathlib import Path

from housing_agent.commute import _parse_duration_seconds, format_minutes
from housing_agent.dedup import is_duplicate
from housing_agent.filters import passes_hard_filters
from housing_agent.ingest import _source_for, extract_image_urls, parse_funda, parse_pararius
from housing_agent.listing import Listing
from housing_agent.quiet_hours import in_quiet_hours

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
    subject, body = load_fixture("pararius_alert.txt")
    listing = parse_pararius(subject, body)
    assert listing is not None
    assert listing.address == "Prinsegracht 12"
    assert listing.city == "Den Haag"
    assert listing.rent == 1950.0
    assert listing.size_m2 == 75.0
    assert "pararius.nl" in listing.url


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
