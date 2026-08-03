import re

from .listing import Listing


def normalize_address(addr: str) -> str:
    return re.sub(r"\s+", " ", addr.strip().lower())


def is_duplicate(listing: Listing, seen: list[dict]) -> bool:
    addr = normalize_address(listing.address)
    for s in seen:
        if normalize_address(s["address"]) != addr:
            continue
        if s.get("size_m2") is not None and listing.size_m2 is not None:
            if abs(s["size_m2"] - listing.size_m2) > 2:
                continue
        if abs(s["total_monthly"] - listing.total_monthly) > 100:
            continue
        return True
    return False
