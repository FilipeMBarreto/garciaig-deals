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
from .render import TIER_TITLES


def _md(text: str) -> str:
    return re.sub(r"([\[\]\\*_`~|>])", r"\\\1", text)


def _line(g: Game) -> str:
    return f"[{_md(g.name)}]({affiliate.game_url(g.id, g.seo_name)}) — **{fmt_price(g.price)}**"


def build_payload(week: Week, site_url: str = "") -> dict:
    embeds = []
    if week.featured:
        embeds.append({
            "title": "⭐ Destaque da Semana",
            "description": _line(week.featured),
            "color": 0x8B5CF6,
            "image": {"url": week.featured.cover_url},
        })
    if week.preorder:
        embeds.append({"title": "⏳ Pré-venda da Próxima Semana", "description": _line(week.preorder), "color": 0x22D3EE})
    for key in ("20", "10", "5", "2"):
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
    links = re.findall(r"\((https://www\.instant-gaming\.com[^)]*)\)", json.dumps(payload, ensure_ascii=False))
    affiliate.assert_all_affiliate(links)
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
