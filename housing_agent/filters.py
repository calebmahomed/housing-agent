from .listing import Listing


def max_affordable_rent(prefs: dict) -> float:
    return prefs["annual_income"] / 12 / prefs["income_to_rent_ratio"]


def passes_hard_filters(listing: Listing, prefs: dict) -> bool:
    if listing.city.strip().lower() not in {c.lower() for c in prefs["cities"]}:
        return False
    if listing.total_monthly > max_affordable_rent(prefs):
        return False
    if listing.bedrooms is not None and listing.bedrooms < prefs.get("min_bedrooms", 0):
        return False
    description = listing.description.lower()
    if any(phrase.lower() in description for phrase in prefs.get("exclude_phrases", [])):
        return False
    return True
