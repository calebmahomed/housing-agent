from typing import Optional

from .detail_check import contains_exclusion
from .listing import Listing


def income_shortfall(total_monthly: float, prefs: dict, stated_ratio: Optional[float] = None) -> Optional[str]:
    """Whether we'd clear the landlord's income test. None means we would.

    `stated_ratio` is what the listing page actually asks for; where the page is
    silent we assume something stricter, because assuming the friendliest number
    is how you end up applying for flats you were never eligible for.

    Warns, never drops. The assumed ratio is a guess about an unstated rule, and
    dropping on a guess is how the city whitelist used to hide the listings that
    suited us best.
    """
    ratio = stated_ratio or prefs.get("assumed_income_to_rent_ratio", 3.5)
    needed = total_monthly * ratio
    monthly_income = prefs["annual_income"] / 12
    if monthly_income >= needed:
        return None
    basis = f"{ratio:g}x stated" if stated_ratio else f"{ratio:g}x assumed, not stated"
    return f"needs €{needed:.0f}/mo gross ({basis}); you have €{monthly_income:.0f}"


def max_affordable_rent(prefs: dict) -> float:
    """Whichever binds first: what landlords will accept on this income, or the
    self-imposed cap. max_rent is the real-world one — a listing can clear the
    income test and still lose to better-funded applicants."""
    income_cap = prefs["annual_income"] / 12 / prefs["income_to_rent_ratio"]
    return min(income_cap, prefs.get("max_rent", float("inf")))


def passes_hard_filters(listing: Listing, prefs: dict) -> bool:
    """Cheap, offline checks only. Location is judged on commute time instead of
    a city whitelist — see commute.within_commute, called separately because it
    costs an API round trip and should run only on listings that got this far."""
    if listing.total_monthly > max_affordable_rent(prefs):
        return False
    if listing.bedrooms is not None and listing.bedrooms < prefs.get("min_bedrooms", 0):
        return False
    if contains_exclusion(listing.description, prefs):
        return False
    return True
