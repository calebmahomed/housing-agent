from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo


def in_quiet_hours(now: Optional[datetime] = None, tz: str = "Europe/Amsterdam", start: int = 23, end: int = 8) -> bool:
    now = now or datetime.now(ZoneInfo(tz))
    h = now.hour
    if start > end:  # window wraps midnight
        return h >= start or h < end
    return start <= h < end
