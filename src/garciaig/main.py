from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from . import affiliate, discord, history, render, scrape, select
from .models import Game, Week

ROOT = Path(__file__).resolve().parents[2]


class PipelineError(RuntimeError):
    pass


def _game_dict(g: Game | None) -> dict | None:
    if g is None:
        return None
    d = asdict(g)
    d["release_date"] = g.release_date.isoformat() if g.release_date else None
    d["url"] = affiliate.game_url(g.id, g.seo_name)
    return d


def _week_dict(w: Week) -> dict:
    return {
        "week": w.key,
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "featured": _game_dict(w.featured),
        "preorder": _game_dict(w.preorder),
        "tiers": {k: [_game_dict(g) for g in games] for k, games in w.tiers.items()},
        "warnings": w.warnings,
    }


def run(today: date, *, offline_dir: Path | None, data_dir: Path, out_dir: Path, site_url: str, dry_run: bool) -> Week:
    htmls = scrape.load_offline(offline_dir) if offline_dir else scrape.fetch_all()
    pool = scrape.build_pool(htmls["trend"], htmls["pre"], htmls["upcoming"])

    data_dir = Path(data_dir)
    hist = history.load(data_dir / "history.json")
    key = select.week_key(today)
    week = select.select_week(pool, history.recent_ids(hist, key), history.preorder_ids(hist), today)

    if week.featured is None or week.preorder is None:
        raise PipelineError("Sem destaque ou sem pré-venda: " + "; ".join(week.warnings))

    payload = discord.build_payload(week, site_url)  # valida links antes de escrever
    render.render_site(week, out_dir, today)
    (data_dir / "week.json").write_text(json.dumps(_week_dict(week), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data_dir / "discord_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not dry_run:
        history.save(data_dir / "history.json", history.record(hist, week))
    return week


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera o site semanal de jogos (Instant Gaming, ref garciap).")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="Data de referência (AAAA-MM-DD)")
    ap.add_argument("--offline", type=Path, default=None, help="Diretoria com HTML guardado em vez de pedir ao site")
    ap.add_argument("--dry-run", action="store_true", help="Não grava o histórico")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "site")
    a = ap.parse_args(argv)
    a.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        week = run(a.today, offline_dir=a.offline, data_dir=a.data_dir, out_dir=a.out_dir, site_url=a.site_url, dry_run=a.dry_run)
    except (PipelineError, scrape.ScrapeError) as e:
        print(f"ERRO: {e}")
        return 1
    print(f"Semana {week.key}: destaque={week.featured.name!r}, pré-venda={week.preorder.name!r}")
    for key, games in week.tiers.items():
        print(f"  até {key} €: {len(games)} jogos")
    for w in week.warnings:
        print(f"  AVISO: {w}")
    print(f"Site em {a.out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
