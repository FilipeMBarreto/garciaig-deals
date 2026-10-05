import re
from datetime import date
from garciaig import render
from garciaig.models import Game, Week


def game(i, name, price, release=1791244800, preorder=False):
    return Game(i, name, f"slug-{i}", price, price * 1.5, 33, release, preorder, False, True, 99, 0)


def make_week():
    return Week(
        "2026-W41", date(2026, 10, 5), date(2026, 10, 11),
        featured=game(1, "Star Wars: Galactic Racer", 39.99, preorder=True),
        preorder=game(2, "Planet <Zoo> 2", 38.49, release=1791849600, preorder=True),
        tiers={"20": [game(3, "A", 15)], "10": [game(4, "B", 8)], "5": [], "2": []},
        warnings=["Bloco 'até 5 €': só 0 de 5 candidatos disponíveis."],
    )


def test_render_writes_files_with_affiliate_links_only(tmp_path):
    out = render.render_site(make_week(), tmp_path, date(2026, 10, 5))
    html = out.read_text(encoding="utf-8")
    assert (tmp_path / "style.css").exists()
    hrefs = re.findall(r'href="(https://www\.instant-gaming\.com[^"]*)"', html)
    assert len(hrefs) >= 4
    assert all(h.endswith("?igr=garciap") and h.count("?") == 1 for h in hrefs)
    assert "https://www.instant-gaming.com/pt/1-comprar-slug-1/?igr=garciap" in hrefs


def test_render_escapes_names_and_formats_pt(tmp_path):
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "Planet &lt;Zoo&gt; 2" in html and "Planet <Zoo> 2" not in html
    assert "39,99 €" in html
    assert "Até 20 €" in html and "Até 2 €" in html
    assert "Sem candidatos esta semana" in html  # blocos vazios (5 € e 2 €)
    assert "2026-W41" in html or "41" in html


def test_render_has_disclosure_and_responsive_meta(tmp_path):
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "afiliado" in html.lower()
    assert 'rel="sponsored noopener"' in html


def test_render_shows_slot_warnings_escaped_and_hides_tier_warnings(tmp_path):
    w = make_week()
    w.warnings = [
        "Sem pré-venda para a semana seguinte; usada a mais próxima depois dela.",
        "Sem candidato a destaque <esta> semana.",
        "Bloco 'até 5 €': só 0 de 5 candidatos disponíveis.",
    ]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert '<p class="note">Sem pré-venda para a semana seguinte; usada a mais próxima depois dela.</p>' in html
    assert '<p class="note">Sem candidato a destaque &lt;esta&gt; semana.</p>' in html
    assert "<esta>" not in html
    assert "só 0 de 5" not in html
    assert html.index("Sem candidato a destaque") < html.index("Pré-venda da Próxima Semana") < html.index("Sem pré-venda para")


def test_render_heading_has_no_zero_jogos(tmp_path):
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "0 jogos" not in html
    assert "<h2>Até 5 €</h2>" in html and "<h2>Até 20 € · 1 jogo</h2>" in html
