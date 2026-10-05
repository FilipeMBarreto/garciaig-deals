from datetime import date, datetime, timezone
from pathlib import Path
from garciaig import scrape, select
from garciaig.models import Game

TODAY = date(2026, 10, 5)  # segunda-feira, semana 2026-W41 (5 a 11 de outubro)


def ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def mk(i, name, price, release, *, preorder=False, dlc=False, pc=True, rank=10_000, retail=None, discount=0):
    return Game(i, name, f"s{i}", price, retail or price, discount, ts(release) if release else None, preorder, dlc, pc, 0, rank)


def test_week_key_and_bounds():
    assert select.week_key(TODAY) == "2026-W41"
    assert select.week_bounds(TODAY) == (date(2026, 10, 5), date(2026, 10, 11))
    assert select.week_bounds(date(2026, 10, 11)) == (date(2026, 10, 5), date(2026, 10, 11))


def test_family_and_edition():
    assert select.family("Transport Fever 3 - Deluxe Edition") == "transport fever 3"
    assert select.family("Planet Zoo 2 Deluxe Edition") == select.family("Planet Zoo 2")
    assert select.family("ACE COMBAT 8: WINGS OF THEVE Deluxe Edition") == select.family("ACE COMBAT 8: WINGS OF THEVE")
    assert select.family("Gears of War: E-Day Premium Edition + Acesso avançado") == select.family("Gears of War: E-Day")
    assert select.family("Castlevania: Belmont's Curse Midnight Edition") == select.family("Castlevania: Belmont's Curse")
    assert select.is_edition(mk(1, "Planet Zoo 2 Deluxe Edition", 1, TODAY))
    assert not select.is_edition(mk(2, "Planet Zoo 2", 1, TODAY))


def test_featured_is_release_this_week_preferring_base_then_rank():
    pool = [
        mk(1, "Game A Deluxe Edition", 60, date(2026, 10, 6), preorder=True, rank=0),
        mk(2, "Game A", 50, date(2026, 10, 6), preorder=True, rank=5),
        mk(3, "Game B", 40, date(2026, 10, 7), preorder=True, rank=1),
        mk(4, "Old", 30, date(2026, 10, 1)),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 3  # base edition com melhor rank (1) vence a Game A (rank 5)


def test_featured_prefers_previous_preorder_highlight():
    pool = [mk(2, "Game A", 50, date(2026, 10, 6), preorder=True, rank=0), mk(3, "Game B", 40, date(2026, 10, 7), preorder=True, rank=1)]
    w = select.select_week(pool, set(), {3}, TODAY)
    assert w.featured.id == 3 or w.featured.id == 2
    assert w.featured.id == 3


def test_featured_falls_back_to_previous_week_with_warning():
    pool = [mk(1, "Last Week", 30, date(2026, 9, 30))]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 1 and any("semana anterior" in x for x in w.warnings)


def test_no_featured_candidate_warns():
    w = select.select_week([mk(1, "Ancient", 30, date(2020, 1, 1))], set(), set(), TODAY)
    assert w.featured is None and any("destaque" in x.lower() for x in w.warnings)


def test_preorder_is_closest_next_week_and_not_featured_family():
    pool = [
        mk(1, "Now Game", 40, date(2026, 10, 6), preorder=True, rank=0),
        mk(2, "Planet Zoo 2 Deluxe Edition", 49, date(2026, 10, 13), preorder=True),
        mk(3, "Planet Zoo 2", 38, date(2026, 10, 13), preorder=True),
        mk(4, "Castlevania", 21, date(2026, 10, 15), preorder=True),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 1
    assert w.preorder.id == 3  # data mais próxima, edição base


def test_preorder_falls_back_to_later_with_warning():
    pool = [mk(1, "Now", 40, date(2026, 10, 6), preorder=True), mk(2, "Far", 40, date(2026, 11, 20), preorder=True)]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.preorder.id == 2 and any("pré-venda" in x for x in w.warnings)


def test_tiers_exclusive_ranges_and_exclusions():
    pool = [
        mk(10, "Now", 40, date(2026, 10, 6), preorder=True),
        mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True),
        mk(20, "T20", 15, date(2026, 9, 1)),
        mk(21, "T10 edge", 10, date(2026, 9, 1)),
        mk(22, "T5", 4.99, date(2026, 9, 1)),
        mk(23, "T2", 2, date(2026, 9, 1)),  # 2 € exatos: fora de todos os escalões
        mk(24, "Free", 0, date(2026, 9, 1)),
        mk(25, "DLC", 3, date(2026, 9, 1), dlc=True),
        mk(26, "Console", 3, date(2026, 9, 1), pc=False),
        mk(27, "Recent", 3, date(2026, 9, 1)),
        mk(28, "Unreleased", 3, date(2026, 12, 1), preorder=True),
    ]
    w = select.select_week(pool, recent_ids={27}, preorder_ids=set(), today=TODAY)
    ids = {k: [g.id for g in v] for k, v in w.tiers.items()}
    assert ids == {"20": [20], "10": [21], "5": [22]}


def test_tier_caps_at_four_orders_by_rank_then_discount_and_dedupes_families():
    pool = [mk(10, "Now", 40, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True)]
    pool += [mk(100 + i, f"Cheap {i}", 15, date(2026, 9, 1), rank=i) for i in range(8)]
    pool += [mk(200, "Cheap 0 Deluxe Edition", 18, date(2026, 9, 1), rank=0)]
    w = select.select_week(pool, set(), set(), TODAY)
    ids = [g.id for g in w.tiers["20"]]
    assert len(ids) == 4 and ids[0] == 100 and 200 not in ids
    assert ids == [100, 101, 102, 103]


def test_underfilled_tier_warns_never_pads():
    pool = [mk(10, "Now", 40, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True), mk(1, "One", 3, date(2026, 9, 1))]
    w = select.select_week(pool, set(), set(), TODAY)
    assert [g.id for g in w.tiers["5"]] == [1]
    assert "Bloco 'até 5 €': só 1 de 4 candidatos disponíveis." in w.warnings and w.tiers["20"] == []


def test_featured_and_preorder_excluded_from_tiers():
    pool = [mk(10, "Now", 15, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 15, date(2026, 10, 13), preorder=True)]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.tiers["20"] == []


def test_real_snapshot_selection():
    fix = Path(__file__).parent / "fixtures"
    h = scrape.load_offline(fix)
    pool = scrape.build_pool(h["trend"], h["pre"], h["upcoming"])
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured and date(2026, 10, 5) <= w.featured.release_date <= date(2026, 10, 11)
    assert w.preorder and date(2026, 10, 12) <= w.preorder.release_date <= date(2026, 10, 18)
    assert w.preorder.preorder and w.preorder.price > 0
    for key, lo, hi in select.TIERS:
        assert all(lo < g.price <= hi and not g.is_dlc and g.is_pc for g in w.tiers[key])
    ids = [g.id for games in w.tiers.values() for g in games] + [w.featured.id, w.preorder.id]
    assert len(ids) == len(set(ids))


def test_preorder_never_picks_free_or_non_preorder_items():
    pool = [
        mk(1, "Now", 40, date(2026, 10, 6), preorder=True),
        mk(2, "Free Thing", 0, date(2026, 10, 12), preorder=True),
        mk(3, "Monkey Bizniz", 5, date(2026, 10, 13), preorder=False),
        mk(4, "Real Preorder", 30, date(2026, 10, 16), preorder=True),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.preorder.id == 4 and w.preorder.preorder and w.preorder.price > 0


def test_preorder_only_invalid_candidates_gives_none_with_warning():
    pool = [
        mk(1, "Now", 40, date(2026, 10, 6), preorder=True),
        mk(2, "Free Thing", 0, date(2026, 10, 12), preorder=True),
        mk(3, "Monkey Bizniz", 5, date(2026, 10, 13), preorder=False),
        mk(4, "Free Later", 0, date(2026, 11, 20), preorder=True),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.preorder is None and any("pré-venda" in x for x in w.warnings)


def test_preorder_later_fallback_requires_price():
    pool = [mk(1, "Now", 40, date(2026, 10, 6), preorder=True), mk(2, "Free Later", 0, date(2026, 11, 20), preorder=True),
            mk(3, "Paid Later", 20, date(2026, 12, 1), preorder=True)]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.preorder.id == 3


import pytest  # noqa: E402


@pytest.mark.parametrize("base,edition", [
    ("Woodo", "Woodo - Endless Summer Edition"),
    ("Bus Simulator 27", "Bus Simulator 27 Year 1 Edition"),
    ("MXGP 26", "MXGP 26 - Fox Holeshot Edition"),
    ("Call of Duty: Modern Warfare 4", "Call of Duty: Modern Warfare 4 - Edição Vault"),
    ("Planet Zoo 2", "Planet Zoo 2 Deluxe Edition"),
])
def test_family_collapses_edition_variants(base, edition):
    assert select.family(base) == select.family(edition)
    assert select.is_edition(mk(2, edition, 1, TODAY)) and not select.is_edition(mk(1, base, 1, TODAY))


@pytest.mark.parametrize("name", ["MXGP 26 - The Official Game", "Woodo", "Edition Wars", "Bus Simulator 27", "Hades: Redemption"])
def test_family_leaves_non_editions_untouched(name):
    assert select.family(name) == name.lower()
    assert not select.is_edition(mk(1, name, 1, TODAY))
