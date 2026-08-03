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


def commute_highlight(origin_address: str) -> Optional[str]:
    """'🚲 18 min · 🚆 25 min', or None if both lookups fail."""
    bike = _duration_minutes(origin_address, "BICYCLE")
    transit = _duration_minutes(origin_address, "TRANSIT")
    parts = []
    if bike is not None:
        parts.append(f"\U0001F6B2 {bike} min")
    if transit is not None:
        parts.append(f"\U0001F686 {transit} min")
    return " · ".join(parts) if parts else None
