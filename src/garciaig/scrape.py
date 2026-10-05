from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from .models import Game

BASE = "https://www.instant-gaming.com/pt"
PAGES = {
    "trend": f"{BASE}/tendencias/",
    "pre": f"{BASE}/pre-reservas/",
    "upcoming": f"{BASE}/proximos-lancamentos/",
}
OFFLINE_FILES = {
    "trend": "tendencias.html",
    "pre": "pre-reservas.html",
    "upcoming": "proximos-lancamentos.html",
}
USER_AGENT = "GarciaIG-Deals/0.1 (weekly showcase for garciap; contact via repository)"
DELAY_SECONDS = 2.5
UNRANKED = 10_000

_DECODER = json.JSONDecoder()


class ScrapeError(RuntimeError):
    pass


def extract_window_json(html: str, name: str):
    m = re.search(r"window\." + re.escape(name) + r"\s*=\s*", html)
    if not m:
        return None
    try:
        value, _ = _DECODER.raw_decode(html, m.end())
    except json.JSONDecodeError as e:
        raise ScrapeError(f"JSON inválido em window.{name}: {e}") from e
    return value


def _platform_ids(raw) -> set[str]:
    if raw is None:
        return set()
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    return {str(p).strip() for p in parts if str(p).strip()}


def _to_game(item: dict, rank: int) -> Game:
    price = float(item["price"])
    retail = float(item.get("retail") or price)
    discount = item.get("discount")
    if discount is None:
        discount = round((1 - price / retail) * 100) if retail > 0 else 0
    return Game(
        id=int(item["prod_id"]),
        name=item["name"],
        seo_name=item["seo_name"],
        price=price,
        retail=retail,
        discount=int(discount),
        avail_date=int(item["avail_date"]) if item.get("avail_date") else None,
        preorder=bool(item.get("preorder")),
        is_dlc=bool(item.get("is_dlc")),
        is_pc="1" in _platform_ids(item.get("platforms")),
        updated_at=int(item.get("updated_at") or 0),
        rank=rank,
    )


def _convert(items, ranked: bool) -> list[Game]:
    games = []
    for i, item in enumerate(items):
        try:
            games.append(_to_game(item, i if ranked else UNRANKED))
        except (KeyError, ValueError, TypeError):
            continue  # item incompleto: ignorar
    return games


def parse_search_results(html: str, ranked: bool = True) -> list[Game]:
    data = extract_window_json(html, "searchResults")
    if not data or not data.get("hits"):
        raise ScrapeError("window.searchResults ausente ou vazio")
    games = _convert(data["hits"], ranked)
    if not games:
        raise ScrapeError("nenhum produto válido em window.searchResults")
    return games


def parse_time_frames(html: str) -> list[Game]:
    data = extract_window_json(html, "productsListedByTimeFrame")
    if not data:
        raise ScrapeError("window.productsListedByTimeFrame ausente ou vazio")
    items = [it for group in data.values() for frame in group.values() for it in frame.values()]
    games = _convert(items, ranked=False)
    if not games:
        raise ScrapeError("nenhum produto válido em productsListedByTimeFrame")
    return games


def build_pool(trend_html: str, pre_html: str, upcoming_html: str) -> list[Game]:
    pool: dict[int, Game] = {}
    for game in (
        parse_search_results(trend_html, ranked=True)
        + parse_search_results(pre_html, ranked=False)
        + parse_time_frames(upcoming_html)
    ):
        pool.setdefault(game.id, game)
    return list(pool.values())


def fetch_all(session=None, delay: float = DELAY_SECONDS, sleep=time.sleep) -> dict[str, str]:
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
    out: dict[str, str] = {}
    for i, (key, url) in enumerate(PAGES.items()):
        if i:
            sleep(delay)
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            raise ScrapeError(f"{url} devolveu HTTP {resp.status_code}")
        out[key] = resp.text
    return out


def load_offline(directory: Path) -> dict[str, str]:
    directory = Path(directory)
    return {k: (directory / name).read_text(encoding="utf-8", errors="ignore") for k, name in OFFLINE_FILES.items()}
