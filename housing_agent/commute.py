import os
from typing import Optional

import requests

WORK_ADDRESS = "Singel 542, 1017 AZ Amsterdam"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def _parse_duration_seconds(duration: str) -> int:
    return int(duration.rstrip("s"))


def _duration_minutes(origin_address: str, travel_mode: str) -> Optional[int]:
    resp = requests.post(
        ROUTES_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": os.environ["GOOGLE_ROUTES_API_KEY"],
            "X-Goog-FieldMask": "routes.duration",
        },
        json={
            "origin": {"address": origin_address},
            "destination": {"address": WORK_ADDRESS},
            "travelMode": travel_mode,
        },
        timeout=10,
    )
    resp.raise_for_status()
    routes = resp.json().get("routes")
    if not routes:
        return None
    return round(_parse_duration_seconds(routes[0]["duration"]) / 60)


def format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}min" if minutes else f"{hours}h"
    return f"{minutes}min"


def _safe_minutes(origin_address: str, mode: str) -> Optional[int]:
    try:
        return _duration_minutes(origin_address, mode)
    except Exception as e:
        print(f"commute lookup failed ({mode}) for {origin_address}: {e}")
        return None


_CACHE: dict = {}


def commute_info(origin_address: str) -> dict:
    """{'bike': min|None, 'transit': min|None, 'text': str|None}.

    Memoised for the process: the same address can be filtered on and then
    rendered, and repeat cities are common within one run.
    """
    if origin_address in _CACHE:
        return _CACHE[origin_address]

    bike = _safe_minutes(origin_address, "BICYCLE")
    transit = _safe_minutes(origin_address, "TRANSIT")
    parts = []
    if bike is not None:
        parts.append(f"\U0001F6B2 {format_minutes(bike)}")
    if transit is not None:
        parts.append(f"\U0001F686 {format_minutes(transit)}")
    info = {"bike": bike, "transit": transit, "text": " · ".join(parts) if parts else None}
    _CACHE[origin_address] = info
    return info


def within_commute(info: dict, prefs: dict) -> bool:
    """Fails open: if the lookup failed we don't know, so don't silently drop a
    listing over a Routes API hiccup."""
    limit = prefs.get("max_commute_minutes")
    if limit is None or info.get("transit") is None:
        return True
    return info["transit"] <= limit


def commute_highlight(origin_address: str) -> Optional[str]:
    """'🚲 1h 5min · 🚆 25min', or None if both lookups fail."""
    return commute_info(origin_address)["text"]
