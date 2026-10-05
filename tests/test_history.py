from datetime import date
from garciaig import history
from garciaig.models import Game, Week


def g(i):
    return Game(i, f"G{i}", f"g{i}", 5.0, 5.0, 0, None, False, False, True)


def week(key, featured=None, preorder=None, tiers=None):
    return Week(key, date(2026, 1, 1), date(2026, 1, 7), featured, preorder, tiers or {"20": [], "10": [], "5": [], "2": []})


def test_load_missing_file(tmp_path):
    assert history.load(tmp_path / "nope.json") == {"weeks": []}


def test_record_save_load_roundtrip(tmp_path):
    h = history.record({"weeks": []}, week("2026-W40", g(1), g(2), {"20": [g(3)], "10": [], "5": [], "2": []}))
    p = tmp_path / "h.json"
    history.save(p, h)
    assert history.load(p) == h
    assert h["weeks"][0] == {"week": "2026-W40", "featured": 1, "preorder": 2, "tiers": {"20": [3], "10": [], "5": [], "2": []}}


def test_record_same_week_is_idempotent():
    h = history.record({"weeks": []}, week("2026-W40", tiers={"20": [g(1)], "10": [], "5": [], "2": []}))
    h = history.record(h, week("2026-W40", tiers={"20": [g(9)], "10": [], "5": [], "2": []}))
    assert len(h["weeks"]) == 1 and h["weeks"][0]["tiers"]["20"] == [9]


def test_recent_ids_window_excludes_current_and_old():
    h = {"weeks": []}
    for n, gid in enumerate([11, 12, 13, 14, 15, 16], start=30):
        h = history.record(h, week(f"2026-W{n}", tiers={"20": [g(gid)], "10": [], "5": [], "2": []}))
    # semana atual W36: últimas 4 anteriores = W32..W35 -> ids 13,14,15 ... W35 é id 16? (W30=11 ... W35=16)
    assert history.recent_ids(h, "2026-W36", weeks=4) == {13, 14, 15, 16}
    # re-executar W35 não conta W35 nem posteriores
    assert history.recent_ids(h, "2026-W35", weeks=4) == {12, 13, 14, 15}


def test_featured_and_preorder_do_not_count_for_pause():
    h = history.record({"weeks": []}, week("2026-W40", g(1), g(2)))
    assert history.recent_ids(h, "2026-W41") == set()
    assert history.preorder_ids(h) == {2}
