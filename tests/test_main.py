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


# ---------- Destaque do streamer ----------

from garciaig import scrape, streamer  # noqa: E402

PICK_URL = "https://www.instant-gaming.com/pt/777-comprar-pick-game-pc-steam/"


def pick_page(name="Pick Game", price="9.99"):
    return (
        f'<meta property="og:title" content="Comprar {name} - PC (Steam) - Europe">'
        '<meta property="og:image" content="https://gaming-cdn.com/images/products/777/380x218/777-cover.jpg?v=42">'
        f'<script>window.productModel = {{"prod_id": 777, "price": "{price}", "retail": "19.99", "discount": 50, "preorder": false}};</script>'
    )


def run_pick(tmp_path, pick_html=None, **kw):
    return main.run(TODAY, offline_dir=FIX, data_dir=tmp_path / "data", out_dir=tmp_path / "site",
                    site_url="https://garcia.example/", dry_run=False, fetch_pick=lambda url: pick_html or pick_page(), **kw)


def read(tmp_path, name):
    return (tmp_path / name).read_text(encoding="utf-8")


def test_run_with_pick_puts_streamer_in_week_site_and_payload(tmp_path):
    (tmp_path / "data").mkdir()
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "Este é <i>bom</i>")
    week = run_pick(tmp_path)
    assert week.streamer.id == 777 and week.streamer_note == "Este é <i>bom</i>"
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert saved["streamer"]["id"] == 777 and saved["streamer_note"] == "Este é <i>bom</i>"
    assert saved["streamer"]["url"] == "https://www.instant-gaming.com/pt/777-comprar-pick-game-pc-steam/?igr=garciap"
    html = read(tmp_path, "site/index.html")
    assert html.index("Destaque do Streamer") < html.index("Destaque da Semana")
    assert "Este é &lt;i&gt;bom&lt;/i&gt;" in html and "Este é <i>" not in html
    assert 'href="https://www.instant-gaming.com/pt/777-comprar-pick-game-pc-steam/?igr=garciap"' in html
    payload = json.loads(read(tmp_path, "data/discord_payload.json"))
    assert payload["embeds"][0]["title"].startswith("🎙️")


def test_run_without_pick_has_no_streamer(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    assert week.streamer is None
    assert json.loads(read(tmp_path, "data/week.json"))["streamer"] is None
    assert "treamer" not in read(tmp_path, "site/index.html")
    assert not any("treamer" in e["title"] for e in json.loads(read(tmp_path, "data/discord_payload.json"))["embeds"])


def test_streamer_fetch_failure_does_not_abort_run(tmp_path):
    (tmp_path / "data").mkdir()
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "nota")

    def boom(url):
        raise scrape.ScrapeError("x")

    week = main.run(TODAY, offline_dir=FIX, data_dir=tmp_path / "data", out_dir=tmp_path / "site",
                    site_url="", dry_run=False, fetch_pick=boom)
    assert week.streamer is None and any(w.startswith("Escolha do streamer indisponível") for w in week.warnings)
    assert "Destaque do Streamer" not in read(tmp_path, "site/index.html")
    assert (tmp_path / "data" / "history.json").exists()


def test_week_dict_roundtrip(tmp_path):
    (tmp_path / "data").mkdir()
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "nota")
    week = run_pick(tmp_path)
    assert main._week_from_dict(main._week_dict(week)) == week
    assert main._week_from_dict(json.loads(read(tmp_path, "data/week.json"))) == week


def test_week_from_dict_accepts_legacy_file_without_streamer(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    d = main._week_dict(week)
    d.pop("streamer"); d.pop("streamer_note")
    assert main._week_from_dict(d) == week


def no_fetch_all(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("não devia ir buscar as listas")
    monkeypatch.setattr(scrape, "fetch_all", boom)
    monkeypatch.setattr(scrape, "load_offline", boom)


def test_republish_updates_only_streamer(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    first = run_pick(tmp_path)  # sem escolha
    hist_before = (data / "history.json").read_bytes()
    week_before = json.loads(read(tmp_path, "data/week.json"))
    streamer.save_pick(data / "streamer_pick.json", PICK_URL, "novo comentário")
    no_fetch_all(monkeypatch)
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="https://garcia.example/",
                         fetch_pick=lambda url: pick_page("Outro Jogo"))
    assert out.streamer.name == "Outro Jogo" and out.streamer_note == "novo comentário"
    assert (data / "history.json").read_bytes() == hist_before
    assert out.featured == first.featured and out.preorder == first.preorder and out.tiers == first.tiers
    after = json.loads(read(tmp_path, "data/week.json"))
    assert {k: v for k, v in after.items() if k not in ("streamer", "streamer_note")} == \
           {k: v for k, v in week_before.items() if k not in ("streamer", "streamer_note")}
    html = read(tmp_path, "site/index.html")
    assert "Destaque do Streamer" in html and "novo comentário" in html and "Outro Jogo" in html
    payload = json.loads(read(tmp_path, "data/discord_payload.json"))
    assert payload["embeds"][0]["title"].startswith("🎙️")
    assert all(len(e["description"]) <= 4096 for e in payload["embeds"])


def test_republish_clear_removes_section_and_old_streamer_warning(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    streamer.save_pick(data / "streamer_pick.json", PICK_URL, "nota")
    main.run(TODAY, offline_dir=FIX, data_dir=data, out_dir=tmp_path / "site", site_url="", dry_run=False,
             fetch_pick=lambda url: "<html>sem modelo</html>")  # falha -> aviso guardado
    assert any(w.startswith("Escolha do streamer indisponível") for w in json.loads(read(tmp_path, "data/week.json"))["warnings"])
    streamer.clear_pick(data / "streamer_pick.json")
    no_fetch_all(monkeypatch)
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")
    assert out.streamer is None and not any(w.startswith("Escolha do streamer indisponível") for w in out.warnings)
    assert "treamer" not in read(tmp_path, "site/index.html")


def test_republish_without_saved_week_or_other_week_raises(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")
    run_pick(tmp_path)
    no_fetch_all(monkeypatch)
    with pytest.raises(main.NoSavedWeek):
        main.republish(date(2026, 10, 12), data_dir=data, out_dir=tmp_path / "site", site_url="")
    assert issubclass(main.NoSavedWeek, main.PipelineError)
    (data / "week.json").write_text("{corrompido", encoding="utf-8")
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")


def cli_args(tmp_path, *extra):
    return ["--offline", str(FIX), "--today", "2026-10-05", "--data-dir", str(tmp_path / "data"),
            "--out-dir", str(tmp_path / "site"), *extra]


def test_cli_republish_falls_back_to_full_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(streamer, "fetch_product_page", lambda url: pick_page())
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "Sem semana guardada para esta semana; a fazer execução completa." in out
    assert (tmp_path / "data" / "history.json").exists() and (tmp_path / "site" / "index.html").exists()


def test_cli_republish_uses_saved_week_and_prints_streamer(tmp_path, capsys, monkeypatch):
    assert main.cli(cli_args(tmp_path)) == 0
    hist = (tmp_path / "data" / "history.json").read_bytes()
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "x")
    monkeypatch.setattr(streamer, "fetch_product_page", lambda url: pick_page())
    no_fetch_all(monkeypatch)
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "Sem semana guardada" not in out and "streamer" in out.lower() and "Pick Game" in out
    assert (tmp_path / "data" / "history.json").read_bytes() == hist


def test_cli_prints_only_three_tiers(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "até 20 €" in out and "até 5 €" in out and "até 2 €" not in out


def test_note_with_bare_ig_url_never_reaches_site_or_payload(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "streamer_pick.json").write_text(
        json.dumps({"url": PICK_URL, "note": "vê https://www.instant-gaming.com/pt/1-comprar-x/ e instant-gaming.com/zzzz"}), encoding="utf-8")
    week = run_pick(tmp_path)
    assert week.streamer_note == "vê e"
    blob = read(tmp_path, "site/index.html") + read(tmp_path, "data/discord_payload.json")
    assert "1-comprar-x" not in blob and "zzzz" not in blob
