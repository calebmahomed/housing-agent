"""Weekly "still running" message.

Silence from this bot currently means either "nothing matched" or "the bot is
dead", and there's no way to tell which. Scheduled workflows are auto-disabled
after 60 days of repo inactivity (plan §1) and that failure looks exactly like
a quiet week.

Rides the poll run rather than getting a cron of its own: a separate scheduled
workflow would be disabled by the same rule it exists to detect. No heartbeat
means no poll runs, which is the signal.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from .notify import send_telegram
from .state import load, save

PATH = "data/heartbeat.json"
INTERVAL = timedelta(days=7)


def heartbeat(alerts: int, seen_count: int, now: Optional[datetime] = None) -> None:
    """Count this run's alerts; report once a week. Never raises — call it
    after state is saved, and a Telegram failure just skips a week."""
    now = now or datetime.now(timezone.utc)
    state = load(PATH, dict)
    state["alerts"] = state.get("alerts", 0) + alerts

    last = state.get("sent")
    if last and now - datetime.fromisoformat(last) < INTERVAL:
        save(PATH, state)  # byte-identical when alerts is 0, so no state commit
        return

    if last:  # the very first run only starts the clock; nothing to report yet
        new_listings = seen_count - state.get("seen_count", seen_count)
        send_telegram(
            f"\U0001fac0 Still running. Past week: {state['alerts']} alert(s) sent, "
            f"{new_listings} new listing(s) seen, {seen_count} known in total."
        )
    state.update(sent=now.isoformat(), seen_count=seen_count, alerts=0)
    save(PATH, state)
