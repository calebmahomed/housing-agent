"""Detail-page fetch via headless Chromium (Playwright). Pararius/Funda
listing pages sit behind a Cloudflare JS challenge that a plain HTTP request
can't pass (verified: a bare curl gets a 403 "Just a moment..." page); a
real browser — even headless — executes that challenge JS and gets through.
Only called for listings that already passed the email-based hard filters,
so this runs a handful of times per poll, not per-listing-in-bulk.

# ponytail: this is a deliberate technical workaround for an anti-bot
# control (Cloudflare), not an incidentally-blocked request — a conscious
# tradeoff accepted after discussion (2026-08-04), not a default to copy
# into other scraping contexts without the same conversation.
"""

from playwright.sync_api import sync_playwright


def _contains_excluded_phrase(text: str, exclude_phrases: list) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in exclude_phrases)


def passes_detail_page_check(url: str, exclude_phrases: list, timeout_ms: int = 20000) -> bool:
    """True if the page loaded and contains none of exclude_phrases.
    Fails open (returns True) on any fetch error, so a Cloudflare hiccup or
    slow load doesn't silently drop an otherwise-good listing."""
    if not exclude_phrases:
        return True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            text = page.inner_text("body")
            browser.close()
    except Exception as e:
        print(f"detail page check failed for {url}: {e}")
        return True

    return not _contains_excluded_phrase(text, exclude_phrases)
