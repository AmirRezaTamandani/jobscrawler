from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    source: str
    source_id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: str | None = None
