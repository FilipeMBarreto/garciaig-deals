from __future__ import annotations

import json
from pathlib import Path

from .models import Week

MAX_WEEKS = 52


def load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"weeks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, hist: dict) -> None:
    Path(path).write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def recent_ids(hist: dict, week_key: str, weeks: int = 4) -> set[int]:
    previous = sorted((w for w in hist["weeks"] if w["week"] < week_key), key=lambda w: w["week"])[-weeks:]
    return {i for w in previous for ids in [*w["tiers"].values(), w.get("discounts", [])] for i in ids}


def preorder_ids(hist: dict) -> set[int]:
    return {w["preorder"] for w in hist["weeks"] if w.get("preorder") is not None}


def record(hist: dict, week: Week) -> dict:
    entry = {
        "week": week.key,
        "featured": week.featured.id if week.featured else None,
        "preorder": week.preorder.id if week.preorder else None,
        "tiers": {k: [g.id for g in games] for k, games in week.tiers.items()},
        "discounts": [g.id for g in week.discounts],
    }
    others = [w for w in hist["weeks"] if w["week"] != week.key]
    return {"weeks": sorted(others + [entry], key=lambda w: w["week"])[-MAX_WEEKS:]}
