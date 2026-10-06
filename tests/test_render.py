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
        tiers={"20": [game(3, "A", 15)], "10": [game(4, "B", 8)]},
        warnings=["Bloco 'até 10 €': só 0 de 4 candidatos disponíveis."],
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
    assert "Até 20 €" in html and "Até 2 €" not in html
    assert "Sem candidatos esta semana" in html  # blocos vazios (tendências e descontos)
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
        "Bloco 'até 10 €': só 0 de 4 candidatos disponíveis.",
    ]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert '<p class="note">Sem pré-venda para a semana seguinte; usada a mais próxima depois dela.</p>' in html
    assert '<p class="note">Sem candidato a destaque &lt;esta&gt; semana.</p>' in html
    assert "<esta>" not in html
    assert "só 0 de 4" not in html
    assert html.index("Sem candidato a destaque") < html.index("<h2>⏳ Pré-venda</h2>") < html.index("Sem pré-venda para")


def test_render_heading_has_no_zero_jogos(tmp_path):
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "0 jogos" not in html
    assert "<h2>Até 10 €</h2>" in html and "<h2>Até 20 €</h2>" in html


def test_streamer_section_first_with_badge_and_escaped_note(tmp_path):
    w = make_week()
    w.streamer = game(7, "Pick <b>Game</b>", 12.5)
    w.streamer_note = "Joguem <script>alert(1)</script> & divirtam-se"
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "🎙️ Destaque do Streamer" in html
    assert html.index("Destaque do Streamer") < html.index("Destaque da Semana") < html.index("Pré-venda")
    assert "Escolha do streamer" in html and 'class="badge-streamer"' in html
    assert '<blockquote class="note-streamer">Joguem &lt;script&gt;alert(1)&lt;/script&gt; &amp; divirtam-se</blockquote>' in html
    assert "<script>" not in html and "Pick &lt;b&gt;Game&lt;/b&gt;" in html
    assert "https://www.instant-gaming.com/pt/7-comprar-slug-7/?igr=garciap" in html


def test_streamer_without_note_has_no_blockquote(tmp_path):
    w = make_week()
    w.streamer = game(7, "Pick", 12.5)
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "Destaque do Streamer" in html and "<blockquote" not in html


def test_no_streamer_no_section(tmp_path):
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "badge-streamer" not in html and "<blockquote" not in html and "Destaque do Streamer" not in html


def test_zero_price_shows_see_price_label(tmp_path):
    w = make_week()
    w.streamer = game(7, "Pick", 0)
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "Ver preço na Instant Gaming" in html and "0,00 €" not in html
    assert html.count("Ver na Instant Gaming") >= 4  # botões mantêm o texto


def test_tier_grid_shows_only_existing_games_no_placeholders(tmp_path):
    w = make_week()
    w.tiers["20"] = [game(30 + i, f"G{i}", 15) for i in range(3)]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    start = html.index("Até 20 €")
    section = html[start:html.index("</section>", start)]
    assert section.count('<article class="card">') == 3 and "empty" not in section


def test_trending_section_between_preorder_and_first_tier(tmp_path):
    w = make_week()
    w.trending = [game(50 + i, f"Hot {i}", 12) for i in range(4)]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "<h2>🔥 Tendências</h2>" in html
    assert html.index("Pré-venda") < html.index("Tendências") < html.index("Até 20 €")
    assert "https://www.instant-gaming.com/pt/50-comprar-slug-50/?igr=garciap" in html


def test_trending_singular_and_empty(tmp_path):
    w = make_week()
    w.trending = [game(50, "Hot", 12)]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "<h2>🔥 Tendências</h2>" in html
    html = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    start = html.index("Tendências")
    assert "Sem candidatos esta semana." in html[start:html.index("</section>", start)]


def test_discounts_section_order_saving_line_only_there_and_empty(tmp_path):
    w = make_week()
    w.trending = [game(50, "Hot", 12)]
    w.discounts = [game(60 + i, f"Deal {i}", 10) for i in range(4)]  # retail = 15 -> poupa 5,00 €
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "<h2>🏷️ Maiores Descontos</h2>" in html
    assert html.index("Tendências") < html.index("Maiores Descontos") < html.index("Até 20 €")
    assert html.count("Poupas 5,00 €") == 4
    start = html.index("Maiores Descontos")
    assert html[start:html.index("</section>", start)].count("Poupas") == 4
    assert "https://www.instant-gaming.com/pt/60-comprar-slug-60/?igr=garciap" in html
    empty = render.render_site(make_week(), tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    start = empty.index("Maiores Descontos")
    assert "Sem candidatos esta semana." in empty[start:empty.index("</section>", start)]
    assert "Poupas" not in empty


def test_only_two_tier_blocks_and_no_ate_5_text(tmp_path):
    w = make_week()
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "Até 5" not in html and "até 5" not in html
    assert "Até 20 €" in html and "Até 10 €" in html


def test_legacy_week_with_tier_5_renders_only_two_tiers(tmp_path):
    w = make_week()
    w.tiers["5"] = [game(99, "Legacy Cheap", 3)]
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    assert "Legacy Cheap" not in html and "Até 5" not in html


def test_no_count_text_in_site_headings_or_discord_titles(tmp_path):
    from garciaig import discord
    w = make_week()
    w.trending = [game(50 + i, f"Hot {i}", 12) for i in range(4)]
    w.discounts = [game(60 + i, f"Deal {i}", 10) for i in range(4)]
    w.streamer = game(7, "Pick", 12)
    html = render.render_site(w, tmp_path, date(2026, 10, 5)).read_text(encoding="utf-8")
    heads = re.findall(r"<h2>(.*?)</h2>", html)
    assert heads == ["🎙️ Destaque do Streamer", "⭐ Destaque da Semana", "⏳ Pré-venda", "🔥 Tendências",
                     "🏷️ Maiores Descontos", "Até 20 €", "Até 10 €"]
    assert not any("jogo" in h.lower() for h in heads)
    titles = [e["title"] for e in discord.build_payload(w)["embeds"]]
    assert titles == ["🎙️ Destaque do streamer", "⭐ Destaque da Semana", "⏳ Pré-venda", "🔥 Tendências",
                      "🏷️ Maiores Descontos", "💶 Até 20 €", "💶 Até 10 €"]
    assert not any("jogo" in t.lower() for t in titles)
