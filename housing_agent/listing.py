from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Listing:
    source: str
    external_id: str
    url: str
    address: str
    city: str
    rent: float
    service_costs: float = 0.0
    size_m2: Optional[float] = None
    bedrooms: Optional[int] = None
    posted_at: Optional[datetime] = None
    raw: dict = field(default_factory=dict)

    @property
    def total_monthly(self) -> float:
        return self.rent + self.service_costs

    def to_seen_record(self) -> dict:
        return {
            "source": self.source,
            "external_id": self.external_id,
            "address": self.address,
            "size_m2": self.size_m2,
            "total_monthly": self.total_monthly,
        }
