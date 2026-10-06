import json

import pytest
import requests

from garciaig import scrape, streamer

GOOD = "https://www.instant-gaming.com/pt/21378-comprar-star-wars-galactic-racer-pc-steam/"


# ---------- parse_pick_url ----------

@pytest.mark.parametrize("url", [
    GOOD,
    GOOD.rstrip("/"),
    GOOD + "?igr=garciap",
    GOOD + "?itm_source=newsletter&x=1#frag",
    "https://instant-gaming.com/pt/21378-comprar-star-wars-galactic-racer-pc-steam/",
    "  " + GOOD + "  ",
])
def test_parse_pick_url_accepts_product_pages(url):
    assert streamer.parse_pick_url(url) == (21378, "star-wars-galactic-racer-pc-steam")


@pytest.mark.parametrize("url", [
    "",
    "   ",
    GOOD.replace("https://", "http://"),
    "https://www.example.com/pt/21378-comprar-x/",
    "https://instant-gaming.com.evil.io/pt/21378-comprar-x/",
    "https://www.instant-gaming.com.evil.io/pt/21378-comprar-x/",
    "https://evil.io/https://www.instant-gaming.com/pt/21378-comprar-x/",
    "https://user@www.instant-gaming.com/pt/21378-comprar-x/",
    "https://www.instant-gaming.com/pt/tendencias/",
    "https://www.instant-gaming.com/pt/",
    "https://www.instant-gaming.com/en/21378-comprar-x/",
    "https://www.instant-gaming.com/pt/21378-buy-x/",
    "https://www.instant-gaming.com/pt/abc-comprar-x/",
    "https://www.instant-gaming.com/pt/21378-comprar-X_y/",
    "https://www.instant-gaming.com/pt/21378-comprar-x/extra/",
    "not a url",
])
def test_parse_pick_url_rejects_everything_else(url):
    with pytest.raises(ValueError) as e:
        streamer.parse_pick_url(url)
    assert str(e.value)  # mensagem pt-PT não vazia


# ---------- save / load / clear ----------

def test_save_pick_normalises_url_and_note(tmp_path):
    p = tmp_path / "pick.json"
    streamer.save_pick(p, GOOD.rstrip("/") + "?igr=outro&itm_source=x", "  linha 1\n\nlinha   2\t fim  ")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"url": GOOD, "note": "linha 1 linha 2 fim"}
    assert streamer.load_pick(p) == data


def test_save_pick_truncates_note_to_280(tmp_path):
    p = tmp_path / "pick.json"
    streamer.save_pick(p, GOOD, "x" * 500)
    assert len(json.loads(p.read_text(encoding="utf-8"))["note"]) == 280


def test_save_pick_invalid_url_writes_nothing(tmp_path):
    p = tmp_path / "pick.json"
    with pytest.raises(ValueError):
        streamer.save_pick(p, "http://www.instant-gaming.com/pt/1-comprar-x/")
    assert not p.exists()


def test_clear_pick_and_load_missing(tmp_path):
    p = tmp_path / "pick.json"
    assert streamer.load_pick(p) is None
    streamer.clear_pick(p)  # não falha se não existir
    streamer.save_pick(p, GOOD)
    streamer.clear_pick(p)
    assert not p.exists() and streamer.load_pick(p) is None


@pytest.mark.parametrize("content", ["{not json", "[]", '{"note": "sem url"}', '{"url": 5}'])
def test_load_pick_malformed_raises_value_error(tmp_path, content):
    p = tmp_path / "pick.json"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        streamer.load_pick(p)


# ---------- parse_product_page ----------

EUR_META = ('<meta itemprop="priceCurrency" content="EUR" />'
            '<meta itemprop="price" content="24.99" data-price-eur="24.99" />')


def page(title='Comprar Transport Fever 3 - Deluxe Edition - PC (Steam) - Europe', image="https://gaming-cdn.com/images/products/21378/380x218/21378-cover.jpg?v=1790779184",
         model='{"prod_id": 21378, "price": "24.99", "retail": "49.99", "discount": 50, "preorder": false}',
         currency_meta=EUR_META, extra=""):
    parts = ["<html><head>", currency_meta]
    if title is not None:
        parts.append(f'<meta property="og:title" content="{title}">')
    if image is not None:
        parts.append(f'<meta content="{image}" property="og:image">')
    parts.append("</head><body>")
    if model is not None:
        parts.append(f"<script>window.productModel = {model};</script>")
    parts.append(extra)
    parts.append("</body></html>")
    return "\n".join(parts)


def test_parse_product_page_extracts_game():
    g = streamer.parse_product_page(page(), 21378, "transport-fever-3-pc-steam")
    assert (g.id, g.name, g.seo_name) == (21378, "Transport Fever 3 - Deluxe Edition", "transport-fever-3-pc-steam")
    assert (g.price, g.retail, g.discount, g.preorder) == (24.99, 49.99, 50, False)
    assert (g.avail_date, g.is_dlc, g.is_pc, g.updated_at, g.rank) == (None, False, True, 1790779184, 0)


def test_parse_product_page_unescapes_name_and_handles_preorder():
    html = page(title="Comprar Tom &amp; Jerry: &quot;Rush&quot; - PC (Steam) - Global",
                model='{"prod_id": 5, "price": 10, "retail": 10, "discount": 0, "preorder": true}')
    g = streamer.parse_product_page(html, 5, "tom-jerry")
    assert g.name == 'Tom & Jerry: "Rush"' and g.preorder is True and g.discount == 0


def test_parse_product_page_missing_og_image_gives_zero_version():
    assert streamer.parse_product_page(page(image=None), 21378, "s").updated_at == 0


def test_parse_product_page_missing_og_title_falls_back_to_slug():
    g = streamer.parse_product_page(page(title=None), 21378, "star-wars-galactic-racer")
    assert g.name == "Star Wars Galactic Racer"


def test_parse_product_page_unmatchable_og_title_falls_back_to_slug():
    g = streamer.parse_product_page(page(title="Qualquer coisa sem formato"), 21378, "meu-jogo")
    assert g.name == "Meu Jogo"


def test_parse_product_page_missing_model_raises():
    with pytest.raises(scrape.ScrapeError):
        streamer.parse_product_page(page(model=None), 21378, "s")


def test_parse_product_page_prod_id_mismatch_raises():
    with pytest.raises(scrape.ScrapeError):
        streamer.parse_product_page(page(), 999, "s")


def test_parse_product_page_bad_price_raises_scrape_error():
    with pytest.raises(scrape.ScrapeError):
        streamer.parse_product_page(page(model='{"prod_id": 21378, "price": "abc"}'), 21378, "s")


# ---------- fetch_product_page ----------

class FakeSession:
    def __init__(self, status=200, text="<html/>", final_url=None):
        self.headers, self.status, self.text, self.calls = {}, status, text, []
        self.final_url = final_url

    def get(self, url, timeout=None, headers=None, allow_redirects=True):
        self.calls.append((url, timeout, headers))
        self.allow_redirects = allow_redirects
        return type("R", (), {"status_code": self.status, "text": self.text, "url": self.final_url or url})()


def test_fetch_product_page_single_polite_get():
    s = FakeSession(text="OK")
    assert streamer.fetch_product_page(GOOD, session=s) == "OK"
    assert len(s.calls) == 1
    url, timeout, headers = s.calls[0]
    assert url == GOOD and timeout == 30
    assert (headers or s.headers)["User-Agent"] == scrape.USER_AGENT
    assert "igr" not in url


def test_fetch_product_page_non_200_raises():
    with pytest.raises(scrape.ScrapeError):
        streamer.fetch_product_page(GOOD, session=FakeSession(status=503))


# ---------- resolve ----------

def write_pick(tmp_path, note="Joguem isto!"):
    p = tmp_path / "pick.json"
    streamer.save_pick(p, GOOD, note)
    return p


def test_resolve_without_file(tmp_path):
    assert streamer.resolve(tmp_path / "nope.json", fetch=lambda u: pytest.fail("não devia pedir")) == (None, "", [])


def test_resolve_good_pick(tmp_path):
    seen = []
    game, note, warns = streamer.resolve(write_pick(tmp_path), fetch=lambda u: seen.append(u) or page())
    assert seen == [GOOD]  # pedido sem ?igr
    assert game.id == 21378 and game.name == "Transport Fever 3 - Deluxe Edition"
    assert note == "Joguem isto!" and warns == []


@pytest.mark.parametrize("exc", [scrape.ScrapeError("boom"), requests.ConnectionError("https://x?token=SEGREDO"), requests.Timeout("t"), ValueError("v")])
def test_resolve_fetch_failure_is_a_warning_not_a_crash(tmp_path, exc):
    def bad(url):
        raise exc

    game, note, warns = streamer.resolve(write_pick(tmp_path), fetch=bad)
    assert game is None and note == "" and len(warns) == 1
    assert warns[0].startswith("Escolha do streamer indisponível")
    low = warns[0].lower()
    assert "destaque" not in low and "pré-venda" not in low
    assert "SEGREDO" not in warns[0]


def test_resolve_bad_page_is_a_warning(tmp_path):
    game, note, warns = streamer.resolve(write_pick(tmp_path), fetch=lambda u: "<html>sem modelo</html>")
    assert game is None and warns and warns[0].startswith("Escolha do streamer indisponível")


@pytest.mark.parametrize("content", ["{not json", "[]", '{"url": "http://www.instant-gaming.com/pt/1-comprar-x/"}'])
def test_resolve_malformed_or_invalid_file_is_a_warning(tmp_path, content):
    p = tmp_path / "pick.json"
    p.write_text(content, encoding="utf-8")
    game, note, warns = streamer.resolve(p, fetch=lambda u: pytest.fail("não devia pedir"))
    assert game is None and note == ""
    assert warns[0].startswith("Escolha do streamer indisponível")
    assert "destaque" not in warns[0].lower() and "pré-venda" not in warns[0].lower()


# ---------- CLI ----------

def test_cli_set_show_clear(tmp_path, capsys):
    p = tmp_path / "pick.json"
    assert streamer.cli(["--path", str(p), "set", "--url", GOOD + "?igr=x", "--note", "olá"]) == 0
    assert json.loads(p.read_text(encoding="utf-8")) == {"url": GOOD, "note": "olá"}
    assert streamer.cli(["--path", str(p), "show"]) == 0
    assert GOOD in capsys.readouterr().out
    assert streamer.cli(["--path", str(p), "clear"]) == 0
    assert not p.exists()


def test_cli_set_invalid_url_exit_1(tmp_path, capsys):
    p = tmp_path / "pick.json"
    assert streamer.cli(["--path", str(p), "set", "--url", "http://example.com"]) == 1
    assert "ERRO" in capsys.readouterr().out and not p.exists()


def test_cli_set_accepts_note_starting_with_dashes(tmp_path):
    p = tmp_path / "pick.json"
    assert streamer.cli(["--path", str(p), "set", f"--url={GOOD}", "--note=--assim"]) == 0
    assert json.loads(p.read_text(encoding="utf-8"))["note"] == "--assim"


def test_fetch_product_page_does_not_follow_redirects():
    s = FakeSession()
    streamer.fetch_product_page(GOOD, session=s)
    assert s.allow_redirects is False


@pytest.mark.parametrize("status", [301, 302, 307, 404])
def test_fetch_product_page_redirect_or_error_status_raises(status):
    with pytest.raises(scrape.ScrapeError):
        streamer.fetch_product_page(GOOD, session=FakeSession(status=status))


@pytest.mark.parametrize("final", ["https://evil.example/x", "http://www.instant-gaming.com/pt/1-comprar-x/"])
def test_fetch_product_page_foreign_final_url_raises(final):
    with pytest.raises(scrape.ScrapeError):
        streamer.fetch_product_page(GOOD, session=FakeSession(final_url=final))


def test_parse_pick_url_rejects_non_ascii_digits():
    with pytest.raises(ValueError):
        streamer.parse_pick_url("https://www.instant-gaming.com/pt/\u0661\u0662\u0663-comprar-x/")


@pytest.mark.parametrize("note,expected", [
    ("vê https://www.instant-gaming.com/pt/1-comprar-x/ já", "vê já"),
    ("http://evil.io/a?b=1 fim", "fim"),
    ("em www.instant-gaming.com/pt/9-comprar-y/ ou instant-gaming.com/x.", "em ou"),
    ("WWW.Instant-Gaming.COM/pt/ ok", "ok"),
])
def test_clean_note_strips_urls(note, expected):
    assert streamer._clean_note(note) == expected


def test_save_pick_strips_urls_from_note(tmp_path):
    p = tmp_path / "pick.json"
    streamer.save_pick(p, GOOD, "compra em https://www.instant-gaming.com/pt/1-comprar-x/ já")
    assert json.loads(p.read_text(encoding="utf-8"))["note"] == "compra em já"


def test_resolve_cleans_hand_edited_note(tmp_path):
    p = tmp_path / "pick.json"
    p.write_text(json.dumps({"url": GOOD, "note": "olha https://www.instant-gaming.com/pt/1-comprar-x/ isto"}), encoding="utf-8")
    _, note, _ = streamer.resolve(p, fetch=lambda u: page())
    assert note == "olha isto"


STORES = {
    "Comprar Gears of War: E-Day - PC & XBOX Series X|S (Microsoft Store)": "Microsoft Store",
    "Comprar Call of Duty: Modern Warfare 4 - PC & XBOX Series X|S (Microsoft Store)": "Microsoft Store",
    "Comprar Star Wars: Galactic Racer - PC (Steam) - Europe & USA & Canada": "Steam",
    "Comprar Transport Fever 3 - Deluxe Edition - PC (Steam) - Europe": "Steam",
    "Comprar Game - Remastered (Edition) - PC (Steam) - Europe": "Steam",
}


@pytest.mark.parametrize("title,expected", [
    ("Comprar Gears of War: E-Day - PC & XBOX Series X|S (Microsoft Store)", "Gears of War: E-Day"),
    ("Comprar Call of Duty: Modern Warfare 4 - PC & XBOX Series X|S (Microsoft Store)", "Call of Duty: Modern Warfare 4"),
    ("Comprar Star Wars: Galactic Racer - PC (Steam) - Europe & USA & Canada", "Star Wars: Galactic Racer"),
    ("Comprar Transport Fever 3 - Deluxe Edition - PC (Steam) - Europe", "Transport Fever 3 - Deluxe Edition"),
    ("Comprar Game - Remastered (Edition) - PC (Steam) - Europe", "Game - Remastered (Edition)"),
])
def test_real_og_titles(title, expected):
    g = streamer.parse_product_page(page(title=title), 21378, "slug-fallback-should-not-be-used")
    assert g.name == expected
    assert g.store == STORES[title]


def test_store_empty_when_title_unmatched():
    assert streamer.parse_product_page(page(title=None), 21378, "x").store == ""
    assert streamer.parse_product_page(page(title="Qualquer coisa"), 21378, "x").store == ""


# ---------- moeda do preço (a página adapta-se à moeda do visitante) ----------

GEARS_MODEL_EUR = '{"prod_id": 21378, "price": "49.19", "retail": 70, "discount": 30, "preorder": true}'
GEARS_MODEL_USD = '{"prod_id": 21378, "price": "55.04", "retail": 78, "discount": 25, "preorder": true}'
CURRENCIES = '<script>window.currencies = {"EUR": {"tx": 1}, "USD": {"tx": "1.118943771"}};</script>'


def test_page_eur_uses_product_model():
    meta = '<meta itemprop="priceCurrency" content="EUR" /><meta itemprop="price" content="49.19" data-price-eur="49.19" />'
    g, source = streamer.parse_product_page_ex(page(model=GEARS_MODEL_EUR, currency_meta=meta), 21378, "s")
    assert (g.price, g.retail, g.discount) == (49.19, 70.0, 30) and source == "página EUR"


def test_page_usd_uses_data_price_eur_and_converts_integer_retail():
    meta = '<meta itemprop="priceCurrency" content="USD" /><meta itemprop="price" content="55.04" data-price-eur="49.19" />'
    html = page(model=GEARS_MODEL_USD, currency_meta=meta, extra='<span data-price-eur="1.23"></span>' + CURRENCIES)
    g, source = streamer.parse_product_page_ex(html, 21378, "s")
    assert (g.price, g.retail, g.discount) == (49.19, 70.0, 30) and source == "página convertida"  # retail 78 USD -> 70 EUR
    assert streamer.parse_product_page(html, 21378, "s") == g


def test_page_usd_without_data_price_eur_converts_with_currency_rate():
    meta = '<meta itemprop="priceCurrency" content="USD" /><meta itemprop="price" content="55.04" />'
    g, source = streamer.parse_product_page_ex(page(model=GEARS_MODEL_USD, currency_meta=meta, extra=CURRENCIES), 21378, "s")
    assert (g.price, g.retail, g.discount) == (49.19, 70.0, 30) and source == "página convertida"


@pytest.mark.parametrize("meta,extra", [
    ('<meta itemprop="priceCurrency" content="USD" /><meta itemprop="price" content="55.04" />', ""),
    ('<meta itemprop="priceCurrency" content="GBP" /><meta itemprop="price" content="40" />', CURRENCIES),
    ("", ""),  # sem meta de moeda: não dá para saber -> nunca arriscar
])
def test_page_non_eur_without_conversion_gives_zero_price(meta, extra):
    g, source = streamer.parse_product_page_ex(page(model=GEARS_MODEL_USD, currency_meta=meta, extra=extra), 21378, "s")
    assert (g.price, g.retail, g.discount) == (0.0, 0.0, 0) and source == "página sem preço"


def pool_game(**kw):
    from garciaig.models import Game
    base = dict(id=21378, name="Gears of War: E-Day", seo_name="gears-pc", price=49.19, retail=70.0, discount=30,
                avail_date=1791244800, preorder=True, is_dlc=False, is_pc=True, updated_at=5, rank=3, store="Microsoft Store")
    base.update(kw)
    return Game(**base)


def test_resolve_prefers_pool_and_never_fetches(tmp_path):
    p = write_pick(tmp_path, "nota")

    def boom(url):
        raise AssertionError("não devia ir buscar a página")

    g, note, warns, source = streamer.resolve_ex(p, boom, pool=[pool_game(id=1), pool_game()])
    assert (g.price, g.retail, g.discount, g.store, g.rank, g.name) == (49.19, 70.0, 30, "Microsoft Store", 0, "Gears of War: E-Day")
    assert note == "nota" and warns == [] and source == "lista EUR"
    assert streamer.resolve(p, boom, pool=[pool_game()])[0].price == 49.19


def test_resolve_pool_source_override_and_miss_uses_fetch(tmp_path):
    p = write_pick(tmp_path)
    _, _, _, source = streamer.resolve_ex(p, lambda u: pytest.fail("não"), pool=[pool_game()], sources={21378: "página convertida"})
    assert source == "página convertida"
    seen = []
    g, _, warns, source = streamer.resolve_ex(p, lambda u: seen.append(u) or page(), pool=[pool_game(id=999)])
    assert seen == [GOOD] and g.price == 24.99 and source == "página EUR" and warns == []


# ---------- preço original em páginas não-EUR (retail inteiro / tx) ----------

TX_USD = '<script>window.currencies = {"EUR": {"tx": 1}, "USD": {"tx": "1.118943771"}, "GBP": {"tx": "0.847877"}};</script>'


def usd_page(eur_price, visitor_price, retail, *, currency="USD", extra=TX_USD, eur_attr=True):
    attr = f' data-price-eur="{eur_price}"' if eur_attr else ""
    meta = f'<meta itemprop="priceCurrency" content="{currency}" /><meta itemprop="price" content="{visitor_price}"{attr} />'
    model = f'{{"prod_id": 21378, "price": "{visitor_price}", "retail": {retail}, "discount": 25, "preorder": false}}'
    return page(model=model, currency_meta=meta, extra=extra)


@pytest.mark.parametrize("eur,visitor,retail,exp_retail,exp_discount", [
    (49.19, 55.04, 78, 70.0, 30),      # Gears of War: E-Day
    (69.99, 78.31, 112, 100.0, 30),    # Premium Edition
    (17.99, 20.13, 62, 55.0, 67),      # Beast of Reincarnation
])
def test_non_eur_page_converts_integer_retail_back_to_eur(eur, visitor, retail, exp_retail, exp_discount):
    g, source = streamer.parse_product_page_ex(usd_page(eur, visitor, retail), 21378, "s")
    assert (g.price, g.retail, g.discount) == (eur, exp_retail, exp_discount) and source == "página convertida"


def test_non_eur_page_with_rate_below_one_keeps_conservative_behaviour():
    g, _ = streamer.parse_product_page_ex(usd_page(49.19, 41.7, 59, currency="GBP"), 21378, "s")
    assert (g.price, g.retail, g.discount) == (49.19, 49.19, 0)


def test_non_eur_page_without_rate_or_retail_keeps_conservative_behaviour():
    g, _ = streamer.parse_product_page_ex(usd_page(49.19, 55.04, 0), 21378, "s")
    assert (g.price, g.retail, g.discount) == (49.19, 49.19, 0)


def test_non_eur_retail_not_above_price_means_no_discount():
    g, _ = streamer.parse_product_page_ex(usd_page(49.19, 55.04, 55), 21378, "s")  # 55 / 1.1189 = 49 <= 49.19
    assert (g.price, g.retail, g.discount) == (49.19, 49.19, 0)


# ---------- diagnóstico e robustez ----------

def full(html):
    return streamer.parse_product_page_full(html, 21378, "s")


def test_debug_for_eur_page():
    g, source, debug = full(page(model=GEARS_MODEL_EUR, currency_meta=(
        '<meta itemprop="priceCurrency" content="EUR" /><meta itemprop="price" content="49.19" data-price-eur="49.19" />')))
    assert source == "página EUR"
    assert "moeda=EUR" in debug and "retail=70" in debug and "resultado: página em EUR" in debug


def test_debug_for_usd_convertible_page():
    g, source, debug = full(usd_page(49.19, 55.04, 78))
    assert (g.retail, g.discount) == (70.0, 30)
    for part in ("moeda=USD", "meta_preço=55.04", "data-price-eur=49.19", "price='55.04'(str)", "retail=78(int)",
                 "discount=25(int)", "tx=1.118943771 (currencies)", "resultado: retail convertido 78→70"):
        assert part in debug, part
    assert "http" not in debug and "cookie" not in debug.lower()


def test_debug_for_gbp_page_rate_below_one():
    g, _, debug = full(usd_page(49.19, 41.7, 59, currency="GBP"))
    assert g.retail == g.price and "tx=0.847877 (currencies)" in debug and "resultado: taxa<1" in debug


def test_missing_currencies_derives_rate_from_price_ratio():
    g, source, debug = full(usd_page(49.19, 55.04, 78, extra=""))
    assert (g.price, g.retail, g.discount) == (49.19, 70.0, 30) and source == "página convertida"
    assert "tx=derivada" in debug and "currencies ausente" in debug and "retail convertido 78→70" in debug


def test_no_rate_at_all_has_no_retail():
    html = usd_page(49.19, 55.04, 78, extra="").replace(' data-price-eur="49.19"', "")
    g, source, debug = full(html)
    assert g.price == 0.0 and source == "página sem preço" and "tx=n/d" in debug


@pytest.mark.parametrize("extra,why", [
    ("<script>window.currencies = {broken json;</script>", "JSON inválido"),
    ('<script>window.currencies = {"EUR": {"tx": 1}};</script>', "moeda ausente em currencies"),
    ('<script>window.currencies = {"USD": {"rate": 2}};</script>', "tx inválido"),
    ('<script>window.currencies = [1, 2];</script>', "moeda ausente em currencies"),
])
def test_malformed_currencies_degrades_without_breaking(extra, why):
    g, source, debug = full(usd_page(49.19, 55.04, 78, extra=extra))
    assert g.price == 49.19 and source == "página convertida"
    assert why in debug  # e a taxa derivada ainda permite converter o retail
    assert g.retail == 70.0


def test_retail_as_string_float_and_lowercase_currency():
    html = usd_page(49.19, 55.04, '"78.0"', currency="usd")
    g, _, debug = full(html)
    assert g.retail == 70.0 and "moeda=USD" in debug
    g, _, debug = full(usd_page(49.19, 55.04, "null"))
    assert g.retail == g.price and "retail ausente" in debug


def test_resolve_full_returns_debug_only_for_page_source(tmp_path):
    p = write_pick(tmp_path)
    *_, source, debug = streamer.resolve_full(p, lambda u: usd_page(49.19, 55.04, 78))
    assert source == "página convertida" and "retail convertido" in debug
    *_, source, debug = streamer.resolve_full(p, lambda u: pytest.fail("não"), pool=[pool_game()])
    assert source == "lista EUR" and debug == ""
