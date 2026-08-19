from .detail_check import contains_exclusion
from .listing import Listing


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
