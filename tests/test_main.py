import json
import re
from datetime import date
from pathlib import Path
import pytest
from garciaig import main, scrape, select

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
        '<meta itemprop="priceCurrency" content="EUR" />'
        f'<meta itemprop="price" content="{price}" data-price-eur="{price}" />'
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
    assert out.featured == first.featured and out.upcoming == first.upcoming and out.tiers == first.tiers
    after = json.loads(read(tmp_path, "data/week.json"))
    assert {k: v for k, v in after.items() if k not in ("streamer", "streamer_note", "streamer_source", "streamer_debug")} == \
           {k: v for k, v in week_before.items() if k not in ("streamer", "streamer_note", "streamer_source", "streamer_debug")}
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
    assert "até 20 €" in out and "até 10 €" in out and "até 5" not in out and "até 2 €" not in out


def test_note_with_bare_ig_url_never_reaches_site_or_payload(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "streamer_pick.json").write_text(
        json.dumps({"url": PICK_URL, "note": "vê https://www.instant-gaming.com/pt/1-comprar-x/ e instant-gaming.com/zzzz"}), encoding="utf-8")
    week = run_pick(tmp_path)
    assert week.streamer_note == "vê e"
    blob = read(tmp_path, "site/index.html") + read(tmp_path, "data/discord_payload.json")
    assert "1-comprar-x" not in blob and "zzzz" not in blob


# ---------- Tendências ----------

def test_end_to_end_trending_block(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    assert len(week.trending) == 4
    assert len({select.family(g.name) for g in week.trending}) == 4
    assert all(g.rank < scrape.UNRANKED for g in week.trending)
    assert not {g.id for g in week.trending} & ({week.featured.id} | {g.id for g in week.upcoming})
    assert not {g.id for g in week.trending} & {g.id for games in week.tiers.values() for g in games}
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert [g["id"] for g in saved["trending"]] == [g.id for g in week.trending]
    assert main._week_from_dict(saved) == week
    hist = json.loads(read(tmp_path, "data/history.json"))
    assert not {g.id for g in week.trending} & {i for ids in hist["weeks"][0]["tiers"].values() for i in ids}
    html = read(tmp_path, "site/index.html")
    assert html.index("Próximos Lançamentos") < html.index("Tendências") < html.index("Até 20 €")


def test_streamer_pick_is_excluded_from_trending_and_tiers(tmp_path):
    (tmp_path / "data").mkdir()
    base = run_pick(tmp_path)
    top = base.trending[0]
    (tmp_path / "data" / "streamer_pick.json").write_text(
        json.dumps({"url": f"https://www.instant-gaming.com/pt/{top.id}-comprar-{top.seo_name}/", "note": ""}), encoding="utf-8")
    page_html = (f'<meta property="og:title" content="Comprar {top.name} - PC (Steam) - Europe">'
                 f'<script>window.productModel = {{"prod_id": {top.id}, "price": "9.99", "retail": "9.99", "discount": 0, "preorder": false}};</script>')
    (tmp_path / "data" / "history.json").unlink()
    w = run_pick(tmp_path, pick_html=page_html)
    assert w.streamer.id == top.id
    assert top.id not in {g.id for g in w.trending}
    assert len(w.trending) == 4


def test_republish_legacy_week_without_trending_raises(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    run_pick(tmp_path)
    saved = json.loads(read(tmp_path, "data/week.json"))
    del saved["trending"]
    (data / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    no_fetch_all(monkeypatch)
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")


def test_cli_legacy_week_without_trending_falls_back_to_full_run(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path)) == 0
    saved = json.loads(read(tmp_path, "data/week.json"))
    del saved["trending"]
    (tmp_path / "data" / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "Sem semana guardada para esta semana; a fazer execução completa." in out
    assert "tendências: 4 jogos" in out
    assert "trending" in json.loads(read(tmp_path, "data/week.json"))


def test_republish_new_streamer_is_dropped_from_trending_and_tiers(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    first = run_pick(tmp_path)
    victims = [first.trending[0], first.tiers["20"][0]]
    no_fetch_all(monkeypatch)
    for v in victims:
        streamer.save_pick(data / "streamer_pick.json", f"https://www.instant-gaming.com/pt/{v.id}-comprar-{v.seo_name}/")
        page_html = (f'<meta property="og:title" content="Comprar {v.name} - PC (Steam) - Europe">'
                     f'<script>window.productModel = {{"prod_id": {v.id}, "price": "9.99", "retail": "9.99", "discount": 0, "preorder": false}};</script>')
        out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="", fetch_pick=lambda url: page_html)
        assert out.streamer.id == v.id
        assert v.id not in {g.id for g in out.trending}
        assert v.id not in {g.id for games in out.tiers.values() for g in games}
        # blocos podem ficar com menos de 4 jogos; nada é reposto
        assert len(out.trending) <= 4


# ---------- Maiores descontos ----------

def test_end_to_end_discounts_block(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    assert week.discounts and len(week.discounts) <= 4
    assert all(g.discount >= 20 and g.retail > g.price for g in week.discounts)
    page_ids = ([week.featured.id] + [g.id for g in week.upcoming] + [g.id for g in week.trending] + [g.id for g in week.discounts]
                + [g.id for games in week.tiers.values() for g in games])
    assert len(page_ids) == len(set(page_ids))
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert [g["id"] for g in saved["discounts"]] == [g.id for g in week.discounts]
    assert main._week_from_dict(saved) == week
    hist = json.loads(read(tmp_path, "data/history.json"))
    assert hist["weeks"][0]["discounts"] == [g.id for g in week.discounts]
    html = read(tmp_path, "site/index.html")
    assert html.index("Tendências") < html.index("Maiores Descontos") < html.index("Até 20 €")


def test_cli_prints_discounts_count_and_names(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "maiores descontos:" in out


def test_legacy_week_without_discounts_raises_and_cli_falls_back(tmp_path, capsys, monkeypatch):
    assert main.cli(cli_args(tmp_path)) == 0
    saved = json.loads(read(tmp_path, "data/week.json"))
    del saved["discounts"]
    (tmp_path / "data" / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=tmp_path / "data", out_dir=tmp_path / "site", site_url="")
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    assert "Sem semana guardada para esta semana; a fazer execução completa." in capsys.readouterr().out
    assert "discounts" in json.loads(read(tmp_path, "data/week.json"))


def test_republish_new_streamer_dropped_from_discounts(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    first = run_pick(tmp_path)
    v = first.discounts[0]
    no_fetch_all(monkeypatch)
    streamer.save_pick(data / "streamer_pick.json", f"https://www.instant-gaming.com/pt/{v.id}-comprar-{v.seo_name}/")
    page_html = (f'<meta property="og:title" content="Comprar {v.name} - PC (Steam) - Europe">'
                 f'<script>window.productModel = {{"prod_id": {v.id}, "price": "9.99", "retail": "9.99", "discount": 0, "preorder": false}};</script>')
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="", fetch_pick=lambda url: page_html)
    assert v.id not in {g.id for g in out.discounts} and len(out.discounts) == len(first.discounts) - 1


def test_week_json_with_legacy_tier_5_loads_and_republishes_with_two_tiers(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    week = run_pick(tmp_path)
    assert set(week.tiers) == {"20", "10"}
    saved = json.loads(read(tmp_path, "data/week.json"))
    saved["tiers"]["5"] = [saved["featured"]]  # legado: escalão que já não existe
    (data / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    assert "5" in main._week_from_dict(saved).tiers  # lê sem falhar
    no_fetch_all(monkeypatch)
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")
    html = read(tmp_path, "site/index.html")
    assert "Até 5" not in html and "Até 20 €" in html and "Até 10 €" in html
    assert "até 5" not in read(tmp_path, "data/discord_payload.json").lower()


# ---------- Próximos lançamentos + loja ----------

def test_end_to_end_upcoming_block_and_store(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    assert len(week.upcoming) == 4
    assert all(g.preorder and g.price > 0 and g.release_date >= TODAY for g in week.upcoming)
    keys = [(g.release_date, g.rank, g.id) for g in week.upcoming]
    assert keys == sorted(keys)
    page = [week.featured] + week.upcoming + week.trending + week.discounts + [g for games in week.tiers.values() for g in games]
    assert len({g.id for g in page}) == len(page)
    assert len({select.family(g.name) for g in page}) == len(page)
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert [g["id"] for g in saved["upcoming"]] == [g.id for g in week.upcoming] and "preorder" not in saved
    assert main._week_from_dict(saved) == week
    assert any(g.store for g in page)
    hist = json.loads(read(tmp_path, "data/history.json"))
    assert hist["weeks"][0]["upcoming"] == [g.id for g in week.upcoming]
    html = read(tmp_path, "site/index.html")
    assert 'class="store"' in html
    assert html.index("Destaque da Semana") < html.index("Próximos Lançamentos") < html.index("Tendências")


def test_empty_upcoming_warns_and_still_publishes(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    h = scrape.load_offline(FIX)
    full = scrape.build_pool(h["trend"], h["pre"], h["upcoming"])
    fid = select.select_week(full, set(), set(), TODAY).featured.id
    monkeypatch.setattr(scrape, "build_pool", lambda *a: [g for g in full if not g.preorder or g.id == fid])
    week = run_pick(tmp_path)
    assert week.featured.id == fid and week.upcoming == []
    assert "Sem próximos lançamentos em pré-venda." in week.warnings
    assert (tmp_path / "data" / "history.json").exists()
    assert "Sem próximos lançamentos em pré-venda." in read(tmp_path, "site/index.html")


def test_no_featured_still_aborts(tmp_path):
    (tmp_path / "data").mkdir()
    with pytest.raises(main.PipelineError):
        run(tmp_path, today=date(2031, 1, 6))


def test_legacy_week_json_with_preorder_raises_and_cli_falls_back(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path)) == 0
    saved = json.loads(read(tmp_path, "data/week.json"))
    saved["preorder"] = saved["featured"]
    del saved["upcoming"]
    (tmp_path / "data" / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=tmp_path / "data", out_dir=tmp_path / "site", site_url="")
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "Sem semana guardada para esta semana; a fazer execução completa." in out
    assert "próximos lançamentos: 4 jogos" in out


def test_cli_prints_upcoming_names_with_store(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "pré-venda=" not in out and "próximos lançamentos: 4 jogos" in out


def test_republish_new_streamer_dropped_from_upcoming(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    first = run_pick(tmp_path)
    v = first.upcoming[0]
    no_fetch_all(monkeypatch)
    streamer.save_pick(data / "streamer_pick.json", f"https://www.instant-gaming.com/pt/{v.id}-comprar-{v.seo_name}/")
    page_html = (f'<meta property="og:title" content="Comprar {v.name} - PC (Steam) - Europe">'
                 f'<script>window.productModel = {{"prod_id": {v.id}, "price": "9.99", "retail": "9.99", "discount": 0, "preorder": true}};</script>')
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="", fetch_pick=lambda url: page_html)
    assert v.id not in {g.id for g in out.upcoming} and len(out.upcoming) == 3
    assert out.streamer.store == v.store  # vem da lista guardada (EUR), sem pedir a página


def test_week_from_dict_tolerates_games_without_store(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    d = main._week_dict(week)
    for g in [d["featured"], *d["upcoming"], *d["trending"]]:
        g.pop("store", None)
    back = main._week_from_dict(d)
    assert back.featured.store == "" and back.upcoming[0].store == ""


# ---------- Moeda do destaque do streamer ----------

def _pick_for(tmp_path, game):
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json",
                       f"https://www.instant-gaming.com/pt/{game.id}-comprar-{game.seo_name}/", "nota")


def _never_fetch(url):
    raise AssertionError("não devia ir buscar a página do jogo")


def test_pick_in_lists_uses_eur_pool_price_without_fetching(tmp_path):
    other = tmp_path / "base"
    (other / "data").mkdir(parents=True)
    top = run_pick(other).trending[0]
    (tmp_path / "data").mkdir()
    _pick_for(tmp_path, top)
    week = main.run(TODAY, offline_dir=FIX, data_dir=tmp_path / "data", out_dir=tmp_path / "site", site_url="", dry_run=False,
                    fetch_pick=_never_fetch)
    assert week.streamer.id == top.id and week.streamer.price == top.price and week.streamer.retail == top.retail
    assert week.streamer_source == "lista EUR"
    assert top.id not in {g.id for g in week.trending}
    assert json.loads(read(tmp_path, "data/week.json"))["streamer_source"] == "lista EUR"
    from garciaig.fmt import fmt_price
    assert fmt_price(top.price) in read(tmp_path, "site/index.html")


def test_republish_reuses_saved_week_games_without_fetching(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    first = run_pick(tmp_path)
    target = first.upcoming[0]
    _pick_for(tmp_path, target)
    no_fetch_all(monkeypatch)
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="", fetch_pick=_never_fetch)
    assert out.streamer.id == target.id and out.streamer.price == target.price and out.streamer_source == "lista EUR"
    assert target.id not in {g.id for g in out.upcoming}


def test_republish_rereads_page_for_page_derived_streamer(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    streamer.save_pick(data / "streamer_pick.json", PICK_URL, "nota")
    first = run_pick(tmp_path)  # preço da página EUR
    assert first.streamer.id == 777
    no_fetch_all(monkeypatch)
    calls = []
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="",
                         fetch_pick=lambda url: calls.append(url) or pick_page())
    assert len(calls) == 1  # dados vindos da página nunca são reutilizados (podem ser de código antigo)
    assert out.streamer == first.streamer and out.streamer_source == "página EUR"


def test_cli_prints_price_source(tmp_path, capsys, monkeypatch):
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "x") if (tmp_path / "data").mkdir() is None else None
    monkeypatch.setattr(streamer, "fetch_product_page", lambda url: pick_page())
    assert main.cli(cli_args(tmp_path)) == 0
    assert "(preço: página EUR)" in capsys.readouterr().out


# ---------- retail/desconto em EUR ----------

def test_week_json_retail_and_discount_match_eur_list_data(tmp_path):
    (tmp_path / "data").mkdir()
    week = run_pick(tmp_path)
    raw = {}
    for fn, name in [("tendencias", "searchResults"), ("pre-reservas", "searchResults")]:
        for it in scrape.extract_window_json((FIX / f"{fn}.html").read_text(encoding="utf-8"), name)["hits"]:
            raw[it["prod_id"]] = it
    saved = json.loads(read(tmp_path, "data/week.json"))
    cards = [saved["featured"], *saved["upcoming"], *saved["trending"], *saved["discounts"]]
    checked = 0
    for g in cards:
        eur = (raw.get(g["id"], {}).get("retail_prices") or {}).get("EUR")
        if eur is None:
            continue
        retail = float(eur)
        assert g["retail"] == retail and g["price"] == float(raw[g["id"]]["currency_prices"]["EUR"])
        assert g["discount"] == (round((1 - g["price"] / retail) * 100) if retail > g["price"] else 0)
        checked += 1
    assert checked >= 4
    assert saved["featured"]["retail"] == 59.99 and saved["featured"]["discount"] == 33
    assert all(g.discount >= 20 and g.retail_known for g in week.discounts)


def test_unknown_retail_counts_summary_and_majority_warning(tmp_path, monkeypatch, capsys):
    from dataclasses import replace
    real = scrape.build_pool

    def mostly_unknown(*a):
        pool = real(*a)
        return [replace(g, retail=g.price, discount=0, retail_known=False) if i % 4 else g for i, g in enumerate(pool)]

    monkeypatch.setattr(scrape, "build_pool", mostly_unknown)
    assert main.cli(cli_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert saved["retail_unknown"] > saved["pool_size"] / 2
    assert f"preços originais em euros indisponíveis: {saved['retail_unknown']} de {saved['pool_size']} jogos" in out
    msg = "Preços originais indisponíveis para mais de metade dos jogos."
    assert msg in saved["warnings"] and "destaque" not in msg.lower() and "pré-venda" not in msg.lower()
    assert msg not in read(tmp_path, "site/index.html")


def test_few_unknown_retail_prints_line_but_no_warning(tmp_path, monkeypatch, capsys):
    from dataclasses import replace
    real = scrape.build_pool
    monkeypatch.setattr(scrape, "build_pool", lambda *a: [replace(g, retail=g.price, discount=0, retail_known=False) if i == 0 else g
                                                          for i, g in enumerate(real(*a))])
    assert main.cli(cli_args(tmp_path, "--dry-run")) == 0
    out = capsys.readouterr().out
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert "preços originais em euros indisponíveis:" in out
    assert not any("Preços originais" in w for w in saved["warnings"])


# ---------- versão do week.json ----------

def test_week_json_has_schema_version(tmp_path):
    (tmp_path / "data").mkdir()
    run_pick(tmp_path)
    assert json.loads(read(tmp_path, "data/week.json"))["schema"] == main.WEEK_SCHEMA == 3
    assert main._week_dict(main._week_from_dict(json.loads(read(tmp_path, "data/week.json"))))["schema"] == main.WEEK_SCHEMA


@pytest.mark.parametrize("schema", ["missing", main.WEEK_SCHEMA - 1, main.WEEK_SCHEMA + 1, "3"])
def test_republish_rejects_week_json_from_another_version(tmp_path, monkeypatch, schema):
    data = tmp_path / "data"
    data.mkdir()
    run_pick(tmp_path)
    saved = json.loads(read(tmp_path, "data/week.json"))
    if schema == "missing":
        del saved["schema"]
    else:
        saved["schema"] = schema
    (data / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    no_fetch_all(monkeypatch)
    with pytest.raises(main.NoSavedWeek):
        main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="")


def test_cli_falls_back_to_full_run_on_version_mismatch(tmp_path, capsys):
    assert main.cli(cli_args(tmp_path)) == 0
    saved = json.loads(read(tmp_path, "data/week.json"))
    del saved["schema"]
    saved["featured"]["retail"] = 999.0  # dados antigos que não podem ser reutilizados
    (tmp_path / "data" / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "week.json de outra versão; a fazer execução completa." in out
    new = json.loads(read(tmp_path, "data/week.json"))
    assert new["schema"] == main.WEEK_SCHEMA and new["featured"]["retail"] != 999.0


def test_cli_prints_streamer_debug_line_only_for_page_source(tmp_path, capsys, monkeypatch):
    (tmp_path / "data").mkdir()
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "x")
    monkeypatch.setattr(streamer, "fetch_product_page", lambda url: pick_page())
    assert main.cli(cli_args(tmp_path)) == 0
    out = capsys.readouterr().out
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert "  diagnóstico streamer: " in out and saved["streamer_debug"].startswith("moeda=EUR")
    assert out.index("destaque do streamer") < out.index("diagnóstico streamer")


def test_no_debug_line_when_pick_comes_from_lists(tmp_path, capsys):
    base = tmp_path / "b"
    (base / "data").mkdir(parents=True)
    top = run_pick(base).trending[0]
    (tmp_path / "data").mkdir()
    _pick_for(tmp_path, top)
    assert main.cli(cli_args(tmp_path)) == 0
    assert "diagnóstico streamer" not in capsys.readouterr().out
    assert json.loads(read(tmp_path, "data/week.json"))["streamer_debug"] == ""


# ---------- republish nunca reutiliza dados de página antigos ----------

USD_PICK_PAGE = (
    '<meta property="og:title" content="Comprar Pick Game - PC (Steam) - Europe">'
    '<meta itemprop="priceCurrency" content="USD" /><meta itemprop="price" content="55.04" data-price-eur="49.19" />'
    '<script>window.currencies = {"USD": {"tx": "1.118943771"}};</script>'
    '<script>window.productModel = {"prod_id": 777, "price": "55.04", "retail": 78, "discount": 25, "preorder": false};</script>'
)


def _saved_week_with_stale_streamer(tmp_path, source):
    """Semana guardada cujo streamer (id 777) tem retail == price e a origem indicada."""
    data = tmp_path / "data"
    data.mkdir()
    streamer.save_pick(data / "streamer_pick.json", PICK_URL, "nota")
    run_pick(tmp_path)
    saved = json.loads(read(tmp_path, "data/week.json"))
    saved["streamer"].update(price=49.19, retail=49.19, discount=0)
    saved["streamer_source"] = source
    saved["streamer_debug"] = ""
    (data / "week.json").write_text(json.dumps(saved), encoding="utf-8")
    return data


@pytest.mark.parametrize("source", ["página convertida", "", None, "página sem preço"])
def test_republish_refetches_stale_page_derived_streamer(tmp_path, monkeypatch, source):
    data = _saved_week_with_stale_streamer(tmp_path, source)
    no_fetch_all(monkeypatch)
    calls = []
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="",
                         fetch_pick=lambda url: calls.append(url) or USD_PICK_PAGE)
    assert len(calls) == 1
    assert (out.streamer.price, out.streamer.retail, out.streamer.discount) == (49.19, 70.0, 30)
    assert out.streamer_source == "página convertida" and "retail convertido 78→70" in out.streamer_debug
    saved = json.loads(read(tmp_path, "data/week.json"))
    assert saved["streamer"]["retail"] == 70.0 and saved["streamer_debug"] == out.streamer_debug
    assert "<s>70,00 €</s>" in read(tmp_path, "site/index.html")


def test_republish_reuses_saved_streamer_only_when_its_source_is_eur_list(tmp_path, monkeypatch):
    data = _saved_week_with_stale_streamer(tmp_path, "lista EUR")
    no_fetch_all(monkeypatch)
    out = main.republish(TODAY, data_dir=data, out_dir=tmp_path / "site", site_url="", fetch_pick=_never_fetch)
    assert out.streamer.retail == 49.19 and out.streamer_source == "lista EUR" and out.streamer_debug == ""


def test_cli_republish_prints_debug_line_for_page_source(tmp_path, capsys, monkeypatch):
    assert main.cli(cli_args(tmp_path)) == 0
    streamer.save_pick(tmp_path / "data" / "streamer_pick.json", PICK_URL, "x")
    monkeypatch.setattr(streamer, "fetch_product_page", lambda url: USD_PICK_PAGE)
    no_fetch_all(monkeypatch)
    capsys.readouterr()
    assert main.cli(cli_args(tmp_path, "--republish")) == 0
    out = capsys.readouterr().out
    assert "Sem semana guardada" not in out
    assert "  diagnóstico streamer: " in out and "retail convertido 78→70" in out
