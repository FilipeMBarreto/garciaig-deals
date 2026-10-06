from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import affiliate
from .fmt import fmt_date, fmt_price
from .models import Game, Week

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
TIER_TITLES = {"20": "Até 20 €", "10": "Até 10 €"}


NO_PRICE = "Ver preço na Instant Gaming"


def _card(g: Game) -> dict:
    has_price = g.price > 0
    return {
        "name": g.name,
        "url": affiliate.game_url(g.id, g.seo_name),
        "cover": g.cover_url,
        "price": fmt_price(g.price) if has_price else NO_PRICE,
        "retail": fmt_price(g.retail) if has_price and g.discount > 0 else None,
        "discount": g.discount,
        "date": fmt_date(g.release_date) if g.release_date else None,
        "preorder": g.preorder,
        "saving": fmt_price(g.retail - g.price) if g.price > 0 and g.retail > g.price else None,
    }


def _notes(week: Week, *keywords: str) -> list[str]:
    return [w for w in week.warnings if any(k in w.lower() for k in keywords)]


def render_site(week: Week, out_dir: Path, today: date) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("index.html.j2").render(
        week_label=week.key,
        period=f"{fmt_date(week.start)} a {fmt_date(week.end)}",
        updated=fmt_date(today),
        streamer=_card(week.streamer) if week.streamer else None,
        streamer_note=week.streamer_note.strip() if week.streamer else "",
        trending=[_card(g) for g in week.trending],
        discounts=[_card(g) for g in week.discounts],
        featured=_card(week.featured) if week.featured else None,
        preorder=_card(week.preorder) if week.preorder else None,
        featured_notes=_notes(week, "destaque"),
        preorder_notes=_notes(week, "pré-venda"),
        tiers=[(TIER_TITLES[k], [_card(g) for g in week.tiers[k]]) for k in ("20", "10")],
    )
    links = re.findall(r'href="(https://www\.instant-gaming\.com[^"]*)"', html)
    affiliate.assert_all_affiliate(links)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(TEMPLATES / "style.css", out_dir / "style.css")
    return out_dir / "index.html"
