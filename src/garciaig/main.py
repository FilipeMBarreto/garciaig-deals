from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from . import affiliate, discord, history, render, scrape, select, streamer
from .models import Game, Week

ROOT = Path(__file__).resolve().parents[2]


class PipelineError(RuntimeError):
    pass


class NoSavedWeek(PipelineError):
    """Não há data/week.json para a semana pedida: não dá para republicar só o destaque do streamer."""


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
        "streamer": _game_dict(w.streamer),
        "streamer_note": w.streamer_note,
        "trending": [_game_dict(g) for g in w.trending],
        "discounts": [_game_dict(g) for g in w.discounts],
    }


def _game_from_dict(d: dict | None) -> Game | None:
    if d is None:
        return None
    return Game(**{k: v for k, v in d.items() if k not in ("release_date", "url")})


def _week_from_dict(d: dict) -> Week:
    return Week(
        key=d["week"],
        start=date.fromisoformat(d["start"]),
        end=date.fromisoformat(d["end"]),
        featured=_game_from_dict(d["featured"]),
        preorder=_game_from_dict(d["preorder"]),
        tiers={k: [_game_from_dict(g) for g in games] for k, games in d["tiers"].items()},
        warnings=list(d.get("warnings", [])),
        streamer=_game_from_dict(d.get("streamer")),
        streamer_note=d.get("streamer_note", ""),
        trending=[_game_from_dict(g) for g in d.get("trending", [])],
        discounts=[_game_from_dict(g) for g in d.get("discounts", [])],
    )


def _write_outputs(week: Week, today: date, data_dir: Path, out_dir: Path, site_url: str) -> None:
    payload = discord.build_payload(week, site_url)  # valida links antes de escrever
    render.render_site(week, out_dir, today)
    (data_dir / "week.json").write_text(json.dumps(_week_dict(week), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data_dir / "discord_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(today: date, *, offline_dir: Path | None, data_dir: Path, out_dir: Path, site_url: str, dry_run: bool,
        pick_path: Path | None = None, fetch_pick=None) -> Week:
    htmls = scrape.load_offline(offline_dir) if offline_dir else scrape.fetch_all()
    pool = scrape.build_pool(htmls["trend"], htmls["pre"], htmls["upcoming"])

    data_dir = Path(data_dir)
    hist = history.load(data_dir / "history.json")
    key = select.week_key(today)
    # fetch_pick=None -> streamer.fetch_product_page (resolvido na chamada)
    pick, pick_note, pick_warnings = streamer.resolve(
        pick_path or data_dir / "streamer_pick.json", fetch_pick or streamer.fetch_product_page)
    week = select.select_week(pool, history.recent_ids(hist, key), history.preorder_ids(hist), today,
                              exclude_games=[pick] if pick else [])
    week.streamer, week.streamer_note = pick, pick_note
    week.warnings.extend(pick_warnings)

    if week.featured is None or week.preorder is None:
        raise PipelineError("Sem destaque ou sem pré-venda: " + "; ".join(week.warnings))

    _write_outputs(week, today, data_dir, Path(out_dir), site_url)
    if not dry_run:
        history.save(data_dir / "history.json", history.record(hist, week))
    return week


STREAMER_WARNING_PREFIX = streamer.WARNING_PREFIX


def republish(today: date, *, data_dir: Path, out_dir: Path, site_url: str,
              pick_path: Path | None = None, fetch_pick=None) -> Week:
    """Refaz site e payload com a semana já guardada, atualizando só o destaque do streamer.

    Não vai buscar as listas, não toca em history.json e não publica nada no Discord."""
    data_dir = Path(data_dir)
    try:
        saved = json.loads((data_dir / "week.json").read_text(encoding="utf-8"))
        if saved["week"] != select.week_key(today):
            raise NoSavedWeek("A semana guardada é de outra semana.")
        if "trending" not in saved or "discounts" not in saved:
            raise NoSavedWeek("A semana guardada é de uma versão antiga (sem tendências).")
        week = _week_from_dict(saved)
    except NoSavedWeek:
        raise
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise NoSavedWeek("Sem semana guardada utilizável.") from e
    week.warnings = [w for w in week.warnings if not w.startswith(STREAMER_WARNING_PREFIX)]
    week.streamer, week.streamer_note, pick_warnings = streamer.resolve(
        pick_path or data_dir / "streamer_pick.json", fetch_pick or streamer.fetch_product_page)
    week.warnings.extend(pick_warnings)
    if week.streamer:
        # o jogo escolhido não pode repetir-se na página: sai das tendências e dos escalões
        # (os blocos podem ficar com menos de 4 jogos; nada é reposto sem nova recolha)
        gone_ids, gone_fam = {week.streamer.id}, {select.family(week.streamer.name)}
        keep = lambda g: g.id not in gone_ids and select.family(g.name) not in gone_fam  # noqa: E731
        week.trending = [g for g in week.trending if keep(g)]
        week.discounts = [g for g in week.discounts if keep(g)]
        week.tiers = {k: [g for g in games if keep(g)] for k, games in week.tiers.items()}
    _write_outputs(week, today, data_dir, Path(out_dir), site_url)
    return week


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera o site semanal de jogos (Instant Gaming, ref garciap).")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="Data de referência (AAAA-MM-DD)")
    ap.add_argument("--offline", type=Path, default=None, help="Diretoria com HTML guardado em vez de pedir ao site")
    ap.add_argument("--republish", action="store_true", help="Só atualiza o destaque do streamer na semana já guardada (sem pedir listas nem tocar no histórico)")
    ap.add_argument("--dry-run", action="store_true", help="Não grava o histórico")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "site")
    a = ap.parse_args(argv)
    a.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        week = None
        if a.republish:
            try:
                week = republish(a.today, data_dir=a.data_dir, out_dir=a.out_dir, site_url=a.site_url)
                print("Republicação: só o destaque do streamer foi atualizado.")
            except NoSavedWeek:
                print("Sem semana guardada para esta semana; a fazer execução completa.")
        if week is None:
            week = run(a.today, offline_dir=a.offline, data_dir=a.data_dir, out_dir=a.out_dir, site_url=a.site_url, dry_run=a.dry_run)
    except (PipelineError, scrape.ScrapeError) as e:
        print(f"ERRO: {e}")
        return 1
    print(f"Semana {week.key}: destaque={week.featured.name!r}, pré-venda={week.preorder.name!r}")
    if week.streamer:
        print(f"  destaque do streamer: {week.streamer.name!r}")
    print(f"  tendências: {len(week.trending)} jogos")
    print(f"  maiores descontos: {len(week.discounts)} jogos" + "".join(f"\n    - {g.name} (-{g.discount} %)" for g in week.discounts))
    for key, games in week.tiers.items():
        print(f"  até {key} €: {len(games)} jogos")
    for w in week.warnings:
        print(f"  AVISO: {w}")
    print(f"Site em {a.out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
