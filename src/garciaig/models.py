from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class Game:
    id: int
    name: str
    seo_name: str
    price: float
    retail: float
    discount: int
    avail_date: int | None
    preorder: bool
    is_dlc: bool
    is_pc: bool
    updated_at: int = 0
    rank: int = 10_000

    @property
    def release_date(self) -> date | None:
        if self.avail_date is None:
            return None
        return datetime.fromtimestamp(self.avail_date, tz=timezone.utc).date()

    @property
    def cover_url(self) -> str:
        return f"https://gaming-cdn.com/images/products/{self.id}/380x218/{self.id}-cover.jpg?v={self.updated_at}"


@dataclass
class Week:
    key: str
    start: date
    end: date
    featured: Game | None
    preorder: Game | None
    tiers: dict[str, list[Game]]
    warnings: list[str] = field(default_factory=list)
    streamer: Game | None = None
    streamer_note: str = ""
    trending: list[Game] = field(default_factory=list)
    discounts: list[Game] = field(default_factory=list)
