"""One Claude call per surviving listing: fill in what the alert email left
out, score the match, say why in one line. Runs on the page text
detail_check.py already fetched, so there's no second page load.
"""

import json
import os
from typing import Optional

import anthropic

from .feedback import examples
from .listing import Listing

MODEL = "claude-opus-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "1-10 match against the preferences"},
        "reason": {"type": "string", "description": "One short sentence. Lead with the deciding factor."},
        "rent_basis": {
            "type": "string",
            "enum": ["kale", "inclusief", "unknown"],
            "description": "Whether the advertised rent excludes or includes servicekosten",
        },
        "total_monthly": {
            "type": ["number", "null"],
            "description": "Best estimate of all-in monthly cost, null if the page doesn't say",
        },
        "size_m2": {"type": ["number", "null"]},
        "bedrooms": {"type": ["integer", "null"]},
    },
    "required": ["score", "reason", "rent_basis", "total_monthly", "size_m2", "bedrooms"],
    "additionalProperties": False,
}


def _prompt(listing: Listing, page_text: str, prefs: dict) -> str:
    return f"""Score this Dutch rental listing for a tenant with these preferences:

{json.dumps(prefs, ensure_ascii=False, indent=2)}
{examples()}
They commute to Singel 542, Amsterdam. Gross annual income €{prefs.get('annual_income')}; \
most landlords require gross monthly income of {prefs.get('income_to_rent_ratio')}x the rent.

From the alert/feed:
  address: {listing.address}, {listing.city}
  advertised rent: €{listing.rent:.0f}
  size: {listing.size_m2} m2
  bedrooms: {listing.bedrooms}
  url: {listing.url}

Listing page text:
{page_text[:12000]}

Resolve whether the advertised rent is kale huur (excl. servicekosten) or inclusief, and \
estimate the real all-in monthly cost. Fill in size and bedrooms from the page if the feed \
missed them. Then score 1-10 on fit and give one sentence saying what decides it — the thing \
that would make them open the listing or skip it. Be blunt about dealbreakers."""


def score_listing(listing: Listing, page_text: str, prefs: dict) -> Optional[dict]:
    """None on any failure — a scoring outage must not drop the alert."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": _prompt(listing, page_text, prefs)}],
        )
        if resp.stop_reason == "refusal":
            print(f"scoring refused for {listing.url}")
            return None
        return json.loads(next(b.text for b in resp.content if b.type == "text"))
    except Exception as e:
        print(f"scoring failed for {listing.url}: {e}")
        return None
