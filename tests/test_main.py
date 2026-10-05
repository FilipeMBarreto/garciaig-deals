import json
import re
from datetime import date
from pathlib import Path
import pytest
from garciaig import main

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 5)


def run(tmp_path, *, dry_run=False, today=TODAY):
    return main.run(today, offline_dir=FIX, data_dir=tmp_path / "data", out_dir=tmp_path / "site", site_url="https://garcia.example/", dry_run=dry_run)


def test_end_to_end_offline(tmp_path):
    (tmp_path / "data").mkdir()
    week = run(tmp_path)
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    links = re.findall(r'href="(https://www\.instant-gaming\.com[^"]*)"', html)
    assert links and all(l.endswith("?igr=garciap") for l in links)
    payload = json.loads((tmp_path / "data" / "discord_payload.json").read_text(encoding="utf-8"))
    assert payload["embeds"]
    saved = json.loads((tmp_path / "data" / "week.json").read_text(encoding="utf-8"))
    assert saved["week"] == "2026-W41" and saved["featured"]["url"].endswith("?igr=garciap")
    hist = json.loads((tmp_path / "data" / "history.json").read_text(encoding="utf-8"))
    assert hist["weeks"][0]["week"] == "2026-W41"
    assert week.featured is not None


def test_dry_run_does_not_write_history(tmp_path):
    (tmp_path / "data").mkdir()
    run(tmp_path, dry_run=True)
    assert not (tmp_path / "data" / "history.json").exists()
    assert (tmp_path / "site" / "index.html").exists()


def test_second_week_avoids_repeating_price_games(tmp_path):
    (tmp_path / "data").mkdir()
    w1 = run(tmp_path)
    w2 = run(tmp_path, today=date(2026, 10, 12))
    ids1 = {g.id for games in w1.tiers.values() for g in games}
    ids2 = {g.id for games in w2.tiers.values() for g in games}
    assert ids1 and not (ids1 & ids2)


def test_missing_featured_aborts_without_writing(tmp_path):
    (tmp_path / "data").mkdir()
    with pytest.raises(main.PipelineError):
        run(tmp_path, today=date(2031, 1, 6))  # nada lançado nessa semana nem na anterior
    assert not (tmp_path / "site" / "index.html").exists()
    assert not (tmp_path / "data" / "history.json").exists()
