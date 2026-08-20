"""Accept/reject decisions from the Telegram buttons, and the few-shot block
they become in the scoring prompt.

A button press can't write to the repo directly — the webhook is a Vercel
function with no checkout — so it dispatches feedback.yml, which runs this and
commits the result. Same GH_PAT + commit-state path /run already uses, so
there's no second datastore to keep in sync.
"""

import hashlib
import sys

from .state import load, save

PATH = "data/feedback.json"
SEEN_PATH = "data/seen_listings.json"

# Few-shot examples in the prompt. Older decisions stay on disk — this only
# bounds what we pay tokens for. Plan §5: this works from ~5 data points, and a
# stale rejection from six months ago is worse signal than a recent one.
KEEP = 20

# Keys are what ride in callback_data; values are what the scoring model reads.
REASONS = {
    "price": "too expensive",
    "commute": "commute too long",
    "size": "too small",
    "outdoor": "no outdoor space",
    "other": "not a fit",
}


def key(source: str, external_id: str) -> str:
    """Short stable id for a listing. Telegram caps callback_data at 64 bytes,
    so the full source+id won't fit — this is what rides in the button instead,
    and what we look the listing back up by."""
    return hashlib.blake2s(f"{source}:{external_id}".encode(), digest_size=6).hexdigest()


def _lookup(k: str) -> dict:
    """The seen record behind a button press. Already holds address, size and
    total_monthly — enough for a few-shot line — so feedback stores a pointer
    rather than a second copy that could drift."""
    for record in load(SEEN_PATH):
        if key(record.get("source", ""), record.get("external_id", "")) == k:
            return record
    return {}


def record(k: str, decision: str, reason: str = "") -> dict:
    """Append a decision. Re-tapping the same listing replaces the old one —
    a changed mind is a correction, not a second data point."""
    entry = {"key": k, "decision": decision, "reason": reason, "listing": _lookup(k)}
    entries = [e for e in load(PATH) if e.get("key") != k]
    entries.append(entry)
    save(PATH, entries)
    return entry


def _describe(listing: dict) -> str:
    bits = [f"{listing.get('address', 'unknown')}"]
    if listing.get("total_monthly"):
        bits.append(f"€{listing['total_monthly']:.0f}/mo")
    if listing.get("size_m2"):
        bits.append(f"{listing['size_m2']:.0f} m²")
    return ", ".join(bits)


def examples() -> str:
    """Recent decisions as few-shot lines, or "" when there are none.

    Deliberately not a weight vector: "rejected — ground floor on a busy road"
    carries nuance no learned score does, and at ~30 decisions/month there
    isn't the data for anything statistical anyway (plan §5).
    """
    lines = []
    for entry in load(PATH)[-KEEP:]:
        listing = entry.get("listing")
        if not listing:
            continue  # pruned from state; nothing to show the model
        verdict = "interested" if entry.get("decision") == "interested" else "passed"
        why = f" — {entry['reason']}" if entry.get("reason") else ""
        lines.append(f"- {_describe(listing)}: {verdict}{why}")
    if not lines:
        return ""
    return (
        "\nTheir past decisions on listings like this — weigh these heavily, "
        "they override the stated preferences where they conflict:\n" + "\n".join(lines) + "\n"
    )


if __name__ == "__main__":  # called by feedback.yml with the button's values
    k, decision = sys.argv[1], sys.argv[2]
    reason = REASONS.get(sys.argv[3] if len(sys.argv) > 3 else "", "")
    print(f"recorded: {record(k, decision, reason)}")
