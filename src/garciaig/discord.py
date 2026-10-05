from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

from . import affiliate
from .fmt import fmt_price
from .models import Game, Week
from .render import NO_PRICE, TIER_TITLES


def _md(text: str) -> str:
    return re.sub(r"([\[\]\\*_`~|>])", r"\\\1", text)


def _line(g: Game) -> str:
    price = fmt_price(g.price) if g.price > 0 else NO_PRICE
    return f"[{_md(g.name)}]({affiliate.game_url(g.id, g.seo_name)}) — **{price}**"


def build_payload(week: Week, site_url: str = "") -> dict:
    embeds = []
    if week.streamer:
        description = _line(week.streamer)
        if week.streamer_note.strip():
            description += f"\n\n> {_md(week.streamer_note.strip())}"
        embeds.append({
            "title": "🎙️ Destaque do streamer",
            "description": description,
            "color": 0xF59E0B,
            "image": {"url": week.streamer.cover_url},
        })
    if week.featured:
        embeds.append({
            "title": "⭐ Destaque da Semana",
            "description": _line(week.featured),
            "color": 0x8B5CF6,
            "image": {"url": week.featured.cover_url},
        })
    if week.preorder:
        embeds.append({"title": "⏳ Pré-venda da Próxima Semana", "description": _line(week.preorder), "color": 0x22D3EE})
    if week.trending:
        embeds.append({
            "title": "🔥 Tendências do momento",
            "description": "\n".join(f"• {_line(g)}" for g in week.trending),
            "color": 0xEF4444,
        })
    for key in ("20", "10", "5"):
        games = week.tiers.get(key) or []
        if games:
            embeds.append({
                "title": f"🎮 {len(games)} {'jogo' if len(games) == 1 else 'jogos'} {TIER_TITLES[key].lower()}",
                "description": "\n".join(f"• {_line(g)}" for g in games),
                "color": 0x34D399,
            })
    content = f"🎮 **Jogos da semana ({week.key})** — links com o código do GarciaP."
    if site_url:
        content += f"\nTudo num só sítio: {site_url}"
    payload = {"content": content, "embeds": embeds, "allowed_mentions": {"parse": []}}
    text = json.dumps(payload, ensure_ascii=False)
    links = re.findall(r"\((https://www\.instant-gaming\.com[^)]*)\)", text)
    # qualquer outro URL da Instant Gaming (ex.: solto num comentário) também tem de ter o código
    stray = [u.rstrip(").,;:!?\"'\\]*") for u in re.findall(r"https?://[^\s\"\\<>]+", text) if "instant-gaming.com" in u.lower()]
    affiliate.assert_all_affiliate(links + stray)
    return payload


def send(payload: dict, webhook_url: str, post=requests.post) -> None:
    post(webhook_url, json=payload, timeout=30).raise_for_status()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0] if argv else "data/discord_payload.json")
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("DISCORD_WEBHOOK_URL não definido; nada enviado.")
        return 0
    try:
        send(json.loads(path.read_text(encoding="utf-8")), webhook)
        print("Mensagem enviada para o Discord.")
        return 0
    except requests.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            print(f"Falha ao enviar para o Discord (HTTP {e.response.status_code}).")
        else:
            print(f"Falha ao enviar para o Discord ({type(e).__name__}).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
