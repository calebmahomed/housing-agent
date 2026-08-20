"""Plain assert-based self-check. Run: python test_housing_agent.py"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from housing_agent import heartbeat as heartbeat_mod
from housing_agent.notify import send_telegram

from housing_agent.config import load_prefs, require_env
from housing_agent.commute import _parse_duration_seconds, format_minutes, within_commute
from housing_agent.dedup import is_duplicate
import os

import requests
import yaml

from housing_agent.detail_check import _strip_html, contains_exclusion, contains_excluded_phrase
from housing_agent.filters import max_affordable_rent, passes_hard_filters
from housing_agent.ingest import _source_for, extract_image_urls, parse_funda, parse_pararius
from housing_agent.listing import Listing
from housing_agent.notify import format_listing
from housing_agent.quiet_hours import in_quiet_hours
from housing_agent.scrape import _parse_ikwilhuren_card, _to_listing

IKWILHUREN_CARD = """<div class="card card-woning shadow-sm">
<div class="card-img-top"><picture><img src='//d.static.nbo.nl/media/6f/abc/768x510/thumb.jpg' alt="x"/></picture></div>
<div class="card-body d-flex flex-column">
<span class="card-title h5 text-secondary mb-0">
<a class="stretched-link" href="/object/amsterdam-1067cp-528-dr-h-colijnstraat-e908b12c/" >
                    Eengezinswoning Dr. H. Colijnstraat 528 
                </a>
</span>
<span>1067CP Amsterdam</span>
<span class="small">
<span title="Sinds 0.81898148148148 dagen online">Nieuw</span>
</span>
<div class="pt-4 dotted-spans mt-auto">
<span class="fw-bold">€ 1.780,- /mnd</span>
<span>99 m<sup>2</sup></span>
<span>3  slaapkamers </span>
</div></div></div>"""

PREFS = {
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


def test_hard_filters_ignore_city_now_that_commute_decides_location():
    # a fixed whitelist used to drop these; location is judged on travel time
    for city in ("Rijswijk", "'s-Gravenhage", "Oegstgeest"):
        listing = Listing(source="x", external_id="1", url="", address="A", city=city, rent=1200)
        assert passes_hard_filters(listing, PREFS), city


def test_within_commute_uses_transit_and_fails_open():
    prefs = {"max_commute_minutes": 90}
    assert within_commute({"transit": 62}, prefs)
    assert not within_commute({"transit": 140}, prefs)
    # a Routes API failure must not silently hide a listing
    assert within_commute({"transit": None}, prefs)
    # no limit configured means no location filtering at all
    assert within_commute({"transit": 999}, {})


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


def test_platform_item_maps_to_listing():
    listing = _to_listing(
        {
            "_id": "abc123",
            "url": "/en/listings/residential/rotterdam/factorij-129/abc123",
            "address": "Factorij 129",
            "city": "Rotterdam",
            "isRentals": True,
            "mainType": "apartment",
            "rentalsPrice": 2195,
            "price": "&euro; 2.195 p.m. ex.",
            "livingSurface": 107,
            "bedrooms": 3,
            "photo": "https://media02.ogonline.nl/x.jpg",
        },
        "verra",
        "https://www.verra.nl",
    )
    assert listing.source == "verra"
    assert listing.url.startswith("https://www.verra.nl/en/listings/")
    assert listing.rent == 2195 and listing.size_m2 == 107 and listing.bedrooms == 3
    assert listing.image_urls == ["https://media02.ogonline.nl/x.jpg"]


def test_platform_sale_listing_is_skipped():
    # sales entries carry rentalsPrice 0 and must never reach the filters
    assert _to_listing({"_id": "x", "url": "/en/l/x", "isRentals": False, "rentalsPrice": 0},
                       "verra", "https://www.verra.nl") is None


def test_platform_parking_space_is_skipped():
    # the feed also rents parking/storage: mainType "other", 0 m2, ~EUR 150 —
    # cheap enough to clear the rent filter and get alerted on as a home
    parking = {"_id": "p", "url": "/en/l/p", "address": "Vissersdijk", "city": "Rotterdam",
               "isRentals": True, "status": "Available", "mainType": "other",
               "rentalsPrice": 150, "livingSurface": 0, "bedrooms": 0}
    assert _to_listing(parking, "verra", "https://www.verra.nl") is None


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


def test_max_rent_cap_binds_before_income_cap():
    # income alone allows EUR 1528/mo; the self-imposed cap is stricter and must win
    prefs = dict(PREFS, max_rent=1400, min_bedrooms=0)
    assert max_affordable_rent(prefs) == 1400
    over = Listing(source="x", external_id="1", url="", address="A", city="Delft", rent=1450)
    assert not passes_hard_filters(over, prefs)
    under = Listing(source="x", external_id="2", url="", address="B", city="Delft", rent=1390)
    assert passes_hard_filters(under, prefs)
    # with no max_rent set, the income cap still applies as before
    assert max_affordable_rent(PREFS) == 55000 / 12 / 3


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


def test_ikwilhuren_card_parses_real_markup():
    listing = _parse_ikwilhuren_card(IKWILHUREN_CARD, max_age_hours=24)
    assert listing.source == "ikwilhuren"
    assert listing.address == "Dr. H. Colijnstraat 528"   # dwelling type stripped
    assert listing.city == "Amsterdam"
    assert listing.rent == 1780.0
    assert listing.size_m2 == 99 and listing.bedrooms == 3
    assert listing.url == "https://www.ikwilhuren.nu/object/amsterdam-1067cp-528-dr-h-colijnstraat-e908b12c/"
    assert listing.image_urls == ["https://d.static.nbo.nl/media/6f/abc/768x510/thumb.jpg"]


def test_ikwilhuren_card_respects_age_cutoff():
    # "Sinds 0.818 dagen online" ~= 19.6h, so a 12h window must exclude it
    assert _parse_ikwilhuren_card(IKWILHUREN_CARD, max_age_hours=12) is None
    assert _parse_ikwilhuren_card(IKWILHUREN_CARD, max_age_hours=24) is not None


def test_exclusion_catches_real_age_limit_phrasings():
    # both taken verbatim from Vesteda listing pages that were wrongly alerted on
    prefs = yaml.safe_load(open("preferences.yaml"))
    for text in ("De Vesteda woningen (min.leeftijd 50 jaar) zijn gelegen in de Kleurenbuurt",
                 "min. leeftijd 50 jr, gelegen tegenover winkelcentrum In de Bogaard",
                 "Dit is een seniorenwoning in een rustig complex",
                 "Verhuur vanaf 55 jaar",
                 "Alleen voor 55-plussers"):
        assert contains_exclusion(text, prefs), text


def test_exclusion_does_not_fire_on_ordinary_listing_text():
    prefs = yaml.safe_load(open("preferences.yaml"))
    for text in ("Ruim appartement aan de Churchilllaan 55, gebouwd in 1965",
                 "Woonoppervlakte 55 m2, bouwjaar 1950",
                 "Op 50 meter van het station"):
        assert not contains_exclusion(text, prefs), text


def test_telegram_post_swallows_network_errors():
    # a read timeout here once aborted the whole poll run before it saved
    # state, losing the record of everything already sent that run
    import housing_agent.notify as notify

    def boom(*a, **kw):
        raise requests.exceptions.ReadTimeout("read timed out")

    original, os.environ["TELEGRAM_BOT_TOKEN"] = notify.requests.post, "test-token"
    notify.requests.post = boom
    try:
        assert notify._post("sendMessage", {"chat_id": 1, "text": "hi"}) is False
    finally:
        notify.requests.post = original


def test_private_values_are_not_in_the_repo():
    # this repo is public: income and work address must come from secrets
    assert "annual_income" not in yaml.safe_load(Path("preferences.yaml").read_text())
    assert "Singel" not in Path("housing_agent/commute.py").read_text()


def test_missing_secrets_fail_loudly_rather_than_degrading():
    # a missing income silently relaxes the rent cap; a missing work address
    # silently disables location filtering. Both look like working software.
    saved = {k: os.environ.pop(k, None) for k in ("ANNUAL_INCOME", "WORK_ADDRESS")}
    try:
        try:
            require_env()
        except SystemExit as e:
            assert "ANNUAL_INCOME" in str(e) and "WORK_ADDRESS" in str(e)
        else:
            raise AssertionError("require_env() should have exited")
        os.environ.update(ANNUAL_INCOME="55000", WORK_ADDRESS="Somewhere 1, Amsterdam")
        require_env()
        assert load_prefs()["annual_income"] == 55000.0
    finally:
        for k, v in saved.items():
            os.environ[k] = v if v is not None else ""
            if not v:
                os.environ.pop(k, None)


def test_heartbeat_reports_weekly_and_accumulates_alerts_between_runs():
    sent = []
    heartbeat_mod.send_telegram = sent.append
    heartbeat_mod.PATH = str(Path(tempfile.mkdtemp()) / "heartbeat.json")
    t0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    try:
        # first ever run only starts the clock — no "past week" to report yet
        heartbeat_mod.heartbeat(alerts=1, seen_count=100, now=t0)
        assert sent == []

        heartbeat_mod.heartbeat(alerts=2, seen_count=105, now=t0 + timedelta(days=3))
        assert sent == [], "must not report before a full week"

        heartbeat_mod.heartbeat(alerts=1, seen_count=112, now=t0 + timedelta(days=7))
        assert len(sent) == 1, "a week on, silence should be broken"
        assert "3 alert(s)" in sent[0], f"alerts must survive intervening runs: {sent[0]}"
        assert "12 new listing(s)" in sent[0] and "112 known" in sent[0], sent[0]

        # window resets: the next report counts from the last one, not from t0
        heartbeat_mod.heartbeat(alerts=0, seen_count=120, now=t0 + timedelta(days=14))
        assert "0 alert(s)" in sent[1] and "8 new listing(s)" in sent[1], sent[1]
    finally:
        heartbeat_mod.send_telegram = send_telegram


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
