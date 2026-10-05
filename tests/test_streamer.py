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

def page(title='Comprar Transport Fever 3 - Deluxe Edition - PC (Steam) - Europe', image="https://gaming-cdn.com/images/products/21378/380x218/21378-cover.jpg?v=1790779184",
         model='{"prod_id": 21378, "price": "24.99", "retail": "49.99", "discount": 50, "preorder": false}'):
    parts = ["<html><head>"]
    if title is not None:
        parts.append(f'<meta property="og:title" content="{title}">')
    if image is not None:
        parts.append(f'<meta content="{image}" property="og:image">')
    parts.append("</head><body>")
    if model is not None:
        parts.append(f"<script>window.productModel = {model};</script>")
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
