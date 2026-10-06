from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable

from .models import Game, Week

TIERS = (("20", 10.0, 20.0), ("10", 5.0, 10.0))
PER_TIER = 4
TRENDING_COUNT = 4
DISCOUNT_COUNT = 4
UPCOMING_COUNT = 4
UPCOMING_WINDOW_DAYS = 30
MIN_DISCOUNT = 20
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

    # Próximos lançamentos: pré-vendas ainda por lançar, por relevância (família em /tendencias/, depois PVP)
    excluded = list(exclude_games)
    skip = [g for g in (featured, *excluded) if g]
    skip_ids = {g.id for g in skip}
    skip_families = {family(g.name) for g in skip}
    best_rank: dict[str, int] = {}
    for g in pool:
        fam = family(g.name)
        best_rank[fam] = min(best_rank.get(fam, g.rank), g.rank)
    reps: dict[str, Game] = {}
    for g in base:
        fam = family(g.name)
        if not (g.preorder and g.price > 0 and g.release_date >= today and g.id not in skip_ids and fam not in skip_families):
            continue
        cur = reps.get(fam)
        if cur is None or (is_edition(g), g.rank, g.id) < (is_edition(cur), cur.rank, cur.id):
            reps[fam] = g
    horizon = today + timedelta(days=UPCOMING_WINDOW_DAYS)
    near = sorted((g for g in reps.values() if g.release_date <= horizon),
                  key=lambda g: (best_rank[family(g.name)], -g.retail, g.release_date, g.id))[:UPCOMING_COUNT]
    later = sorted((g for g in reps.values() if g.release_date > horizon), key=lambda g: (g.release_date, g.id))
    upcoming = sorted(near + later[:UPCOMING_COUNT - len(near)], key=lambda g: (g.release_date, g.rank, g.id))
    if not upcoming:
        warnings.append("Sem próximos lançamentos em pré-venda.")
    elif len(upcoming) < UPCOMING_COUNT:
        warnings.append(f"Bloco 'próximos lançamentos': só {len(upcoming)} de {UPCOMING_COUNT} candidatos disponíveis.")

    # Tendências: top de /tendencias/ (sem pausa), sem repetir nada que já esteja na página
    taken = [*skip, *upcoming]
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

    # Maiores descontos: jogos já lançados, com pausa de 4 semanas e sem repetir nada da página
    page = taken + trending
    page_ids = {g.id for g in page}
    page_families = {family(g.name) for g in page}
    deal_pool = sorted(
        (g for g in base
         if not g.preorder and g.release_date <= today and g.price > 0 and g.retail > g.price
         and g.discount >= MIN_DISCOUNT and g.id not in recent_ids
         and g.id not in page_ids and family(g.name) not in page_families),
        key=lambda g: (-g.discount, -(g.retail - g.price), g.rank, g.id),
    )
    discounts: list[Game] = []
    deal_families: set[str] = set()
    for g in deal_pool:
        fam = family(g.name)
        if fam in deal_families:
            continue
        deal_families.add(fam)
        discounts.append(g)
        if len(discounts) == DISCOUNT_COUNT:
            break
    if len(discounts) < DISCOUNT_COUNT:
        warnings.append(f"Bloco 'maiores descontos': só {len(discounts)} de {DISCOUNT_COUNT} candidatos disponíveis.")

    # Blocos de preço
    chosen = page + discounts
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

    return Week(week_key(today), start, end, featured, upcoming, tiers, warnings, trending=trending, discounts=discounts)
