from .listing import Listing


def passes_hard_filters(listing: Listing, prefs: dict) -> bool:
    if listing.city.strip().lower() not in {c.lower() for c in prefs["cities"]}:
        return False
    if listing.total_monthly > prefs["max_total_monthly"]:
        return False
    if listing.bedrooms is not None and listing.bedrooms < prefs.get("min_bedrooms", 0):
        return False
    return True
