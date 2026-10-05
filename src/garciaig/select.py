from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable

from .models import Game, Week

TIERS = (("20", 10.0, 20.0), ("10", 5.0, 10.0), ("5", 2.0, 5.0))
PER_TIER = 4
TRENDING_COUNT = 4
UNRANKED = 10_000  # igual a scrape.UNRANKED (rank < UNRANKED = veio de /tendencias/)

_ADJ = r"(?:digital|deluxe|premium|ultimate|gold|complete|collector'?s?|standard|definitive|special|day one|launch)"
_EDITION_RE = re.compile(
    rf"(?:\s+[-–]\s+(?:[\w']+\s+){{0,3}}|\s*:?\s+(?:{_ADJ}\s+)*(?:[\w']+\s+)?|\s+year\s+\d+\s+)(?:edition|edição)\b.*$",
    re.IGNORECASE,
)


def family(name: str) -> str:
    """Nome base do jogo, sem sufixos de edição (Deluxe, Premium, ...)."""
    return _EDITION_RE.sub("", name).strip().lower()


def is_edition(game: Game) -> bool:
    return family(game.name) != game.name.strip().lower()


def week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def week_key(today: date) -> str:
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _base_order(g: Game):
    return (is_edition(g), g.rank, -g.retail, g.id)


def select_week(pool: list[Game], recent_ids: set[int], preorder_ids: set[int], today: date,
                exclude_games: Iterable[Game] = ()) -> Week:
    start, end = week_bounds(today)
    warnings: list[str] = []
    base = [g for g in pool if g.is_pc and not g.is_dlc and g.release_date is not None]

    # Destaque
    this_week = [g for g in base if start <= g.release_date <= end and g.price > 0]
    prev_week = [
        g for g in base
        if start - timedelta(days=7) <= g.release_date < start and not g.preorder and g.price > 0
    ]
    featured_pool = this_week or prev_week
    if featured_pool and not this_week:
        warnings.append("Sem lançamentos na semana corrente; destaque tirado da semana anterior.")
    featured = min(featured_pool, key=lambda g: (g.id not in preorder_ids,) + _base_order(g), default=None)
    if featured is None:
        warnings.append("Sem candidato a destaque esta semana.")

    # Pré-venda da semana seguinte
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=7)
    featured_family = family(featured.name) if featured else None

    def eligible(g: Game) -> bool:
        return g.preorder and g.price > 0 and (featured is None or (g.id != featured.id and family(g.name) != featured_family))

    nxt = [g for g in base if next_start <= g.release_date <= next_end and eligible(g)]
    order = lambda g: (g.release_date, is_edition(g), g.rank, -g.retail, g.id)  # noqa: E731
    preorder = min(nxt, key=order, default=None)
    if preorder is None:
        later = [g for g in base if g.release_date > next_end and eligible(g)]
        preorder = min(later, key=order, default=None)
        warnings.append(
            "Sem pré-venda para a semana seguinte; usada a mais próxima depois dela."
            if preorder else "Sem nenhuma pré-venda disponível."
        )

    # Tendências: top de /tendencias/ (sem pausa), sem repetir nada que já esteja na página
    excluded = list(exclude_games)
    taken = [g for g in (featured, preorder, *excluded) if g]
    taken_ids = {g.id for g in taken}
    taken_families = {family(g.name) for g in taken}
    by_family: dict[str, Game] = {}
    for g in pool:
        if g.rank < UNRANKED and g.is_pc and not g.is_dlc and g.price > 0 and g.id not in taken_ids and family(g.name) not in taken_families:
            fam = family(g.name)
            cur = by_family.get(fam)
            if cur is None or (is_edition(g), g.rank, g.id) < (is_edition(cur), cur.rank, cur.id):
                by_family[fam] = g
    trending = sorted(by_family.values(), key=lambda g: (g.rank, g.id))[:TRENDING_COUNT]
    if len(trending) < TRENDING_COUNT:
        warnings.append(f"Bloco 'tendências': só {len(trending)} de {TRENDING_COUNT} candidatos disponíveis.")

    # Blocos de preço
    chosen = taken + trending
    chosen_ids = {g.id for g in chosen}
    seen_families = {family(g.name) for g in chosen}
    released = [
        g for g in base
        if not g.preorder and g.release_date <= today and g.price > 0
        and g.id not in recent_ids and g.id not in chosen_ids
    ]
    tiers: dict[str, list[Game]] = {}
    for key, lo, hi in TIERS:
        candidates = sorted((g for g in released if lo < g.price <= hi), key=lambda g: (g.rank, -g.discount, g.name))
        picked: list[Game] = []
        for g in candidates:
            fam = family(g.name)
            if fam in seen_families:
                continue
            seen_families.add(fam)
            picked.append(g)
            if len(picked) == PER_TIER:
                break
        if len(picked) < PER_TIER:
            warnings.append(f"Bloco 'até {key} €': só {len(picked)} de {PER_TIER} candidatos disponíveis.")
        tiers[key] = picked

    return Week(week_key(today), start, end, featured, preorder, tiers, warnings, trending=trending)
