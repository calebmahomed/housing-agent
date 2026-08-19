"""Fetch a listing's detail page as plain text, for the exclusion check and
for the LLM scorer (one fetch, both consumers).

Plain HTTP first — makelaar sites like verra.nl serve normal HTML. Pararius
and Funda sit behind a Cloudflare JS challenge that a bare request can't pass
(verified: curl gets a 403 "Just a moment..." page), so those fall back to
headless Chromium, which executes the challenge JS. Only called for listings
that already passed the hard filters, so it runs a handful of times per poll.

# ponytail: the Playwright fallback is a deliberate technical workaround for
# an anti-bot control (Cloudflare), not an incidentally-blocked request — a
# conscious tradeoff accepted after discussion (2026-08-04), not a default to
# copy into other scraping contexts without the same conversation.
"""

import re

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
CHALLENGED = ("just a moment", "enable javascript and cookies", "cf-browser-verification")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


def _via_playwright(url: str, timeout_ms: int) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            return page.inner_text("body")
        finally:
            browser.close()


def fetch_page_text(url: str, timeout_ms: int = 20000) -> str:
    """Page text, or "" if it couldn't be fetched. Callers must treat "" as
    'unknown', not 'clean' — a Cloudflare hiccup shouldn't drop a good listing."""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout_ms / 1000)
        if resp.ok:
            text = _strip_html(resp.text)
            if not any(marker in text[:2000].lower() for marker in CHALLENGED):
                return text
    except Exception as e:
        print(f"plain fetch failed for {url}: {e}")

    try:
        return _via_playwright(url, timeout_ms)
    except Exception as e:
        print(f"playwright fetch failed for {url}: {e}")
        return ""


def contains_excluded_phrase(text: str, exclude_phrases: list) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in exclude_phrases)


def contains_exclusion(text: str, prefs: dict) -> bool:
    """Literal phrases plus regexes.

    Age limits are the reason the regex list exists: Vesteda writes
    "min.leeftijd 50 jaar" and "min. leeftijd 50 jr", which no substring in
    exclude_phrases matches, and the bound varies (50, 55, 65). Patterns stay
    separate from phrases rather than making every phrase a regex — "55+"
    read as a regex means "5" then one-or-more "5", which would match a house
    number.
    """
    if contains_excluded_phrase(text, prefs.get("exclude_phrases", [])):
        return True
    return any(re.search(p, text, re.I) for p in prefs.get("exclude_patterns", []))
