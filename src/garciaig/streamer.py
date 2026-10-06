"""Escolha manual do streamer: validação do link, página do produto e ficheiro data/streamer_pick.json."""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import requests

from . import scrape
from .models import Game

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "streamer_pick.json"
NOTE_MAX = 280
WARNING_PREFIX = "Escolha do streamer indisponível"
_WARNING = WARNING_PREFIX + ": não foi possível carregar o jogo escolhido; o bloco foi omitido."

_HOSTS = {"www.instant-gaming.com", "instant-gaming.com"}
_PATH_RE = re.compile(r"^/pt/([0-9]+)-comprar-([a-z0-9-]+)/?$", re.ASCII)
_URL_RE = re.compile(r"https?://\S+|\b(?:www\.)?instant-gaming\.com\S*", re.IGNORECASE)
_PLATFORM = r"(?:PC|Mac|Linux|Xbox|PlayStation|PS[345]|Nintendo|Switch|Steam)\b[^()]*\((?P<store>[^)]*)\)"
_TITLE_RE = re.compile(rf"^Comprar\s+(.*?)\s+-\s+{_PLATFORM}(?:\s+-\s+.*)?$", re.IGNORECASE)


def parse_pick_url(url: str) -> tuple[int, str]:
    """Valida o link de um produto da Instant Gaming (PT) e devolve (id, slug). Query e fragmento são ignorados."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Falta o link do jogo na Instant Gaming.")
    try:
        p = urlsplit(url)
        host = p.netloc.lower()
    except ValueError as e:
        raise ValueError("O link não é válido.") from e
    if p.scheme != "https":
        raise ValueError("O link tem de começar por https://.")
    if host not in _HOSTS:
        raise ValueError("O link tem de ser de www.instant-gaming.com.")
    if not p.path.startswith("/pt/"):
        raise ValueError("O link tem de ser da versão portuguesa (/pt/).")
    m = _PATH_RE.match(p.path)
    if not m:
        raise ValueError("O link não é de uma página de jogo (esperado /pt/NÚMERO-comprar-nome/).")
    return int(m.group(1)), m.group(2)


def _clean_note(note) -> str:
    text = _URL_RE.sub(" ", str(note or ""))  # links soltos não podem chegar ao site nem ao Discord
    return re.sub(r"\s+", " ", text).strip()[:NOTE_MAX].strip()


def save_pick(path: Path, url: str, note: str = "") -> dict:
    game_id, slug = parse_pick_url(url)
    data = {"url": f"https://www.instant-gaming.com/pt/{game_id}-comprar-{slug}/", "note": _clean_note(note)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def clear_pick(path: Path) -> None:
    Path(path).unlink(missing_ok=True)


def load_pick(path: Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError("O ficheiro da escolha do streamer está corrompido (JSON inválido).") from e
    if not isinstance(data, dict) or not isinstance(data.get("url"), str):
        raise ValueError("O ficheiro da escolha do streamer não tem o formato esperado.")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise ValueError("O comentário do streamer não é texto.")
    return {"url": data["url"], "note": _clean_note(note)}


def _meta_tags(html: str) -> list[dict[str, str]]:
    return [
        {k.lower(): htmllib.unescape(v) for k, _, v in re.findall(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2', tag, flags=re.DOTALL)}
        for tag in re.findall(r"<meta\b[^>]*>", html, flags=re.IGNORECASE)
    ]


def _meta_content(html: str, prop: str) -> str | None:
    for attrs in _meta_tags(html):
        if attrs.get("property", "").lower() == prop and "content" in attrs:
            return attrs["content"]
    return None


def _to_float(value) -> float | None:
    try:
        x = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x == x and x > 0 else None  # exclui NaN e <= 0


def _rate(html: str, currency: str) -> tuple[float | None, str]:
    """Taxa de câmbio (a partir do EUR) da moeda do visitante, em window.currencies, e a razão se faltar."""
    try:
        data = scrape.extract_window_json(html, "currencies")
    except scrape.ScrapeError:
        return None, "JSON inválido"
    if data is None:
        return None, "currencies ausente"
    entry = data.get(currency) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        return None, "moeda ausente em currencies"
    tx = _to_float(entry.get("tx"))
    return (tx, "") if tx is not None else (None, "tx inválido")


def _price_meta(html: str) -> dict[str, str]:
    return next((a for a in _meta_tags(html) if a.get("itemprop", "").lower() == "price"), {})


def _raw(value) -> str:
    return "n/d" if value is None else f"{value!r}({type(value).__name__})"


def _non_eur_prices(html: str, currency: str, model: dict) -> tuple[float, float, int, str]:
    """(preço EUR, retail EUR, desconto, diagnóstico) de uma página na moeda do visitante."""
    pm = _price_meta(html)
    eur_attr = _to_float(pm.get("data-price-eur"))  # só o do meta itemprop="price" é deste produto
    visitor_price = _to_float(pm.get("content")) or _to_float(model.get("price"))
    tx, why = _rate(html, currency) if currency else (None, "moeda ausente")
    derived = False
    if tx is None and visitor_price and eur_attr:
        tx, derived = visitor_price / eur_attr, True
    if eur_attr:
        price = round(eur_attr, 2)
    elif visitor_price and tx:
        price = round(visitor_price / tx, 2)
    else:
        price = 0.0
    visitor_retail = _to_float(model.get("retail"))
    if price <= 0:
        retail, outcome = price, "sem preço"
    elif visitor_retail is None:
        retail, outcome = price, "retail ausente"
    elif tx is None:
        retail, outcome = price, "sem taxa"
    elif tx < 1.0:
        retail, outcome = price, "taxa<1"
    else:
        eur = float(round(visitor_retail / tx))
        if eur > price:
            retail, outcome = eur, f"retail convertido {visitor_retail:g}→{eur:g}"
        else:
            retail, outcome = price, "retail<=preço"
    discount = round((1 - price / retail) * 100) if retail > price else 0
    if tx is None:
        tx_text = f"n/d ({why})"
    elif derived:
        tx_text = f"derivada {tx:.6g} (preço/data-price-eur; currencies: {why})"
    else:
        tx_text = f"{tx} (currencies)"
    debug = (f"moeda={currency or 'n/d'}; meta_preço={pm.get('content', 'n/d')}; data-price-eur={pm.get('data-price-eur', 'n/d')}; "
             f"model: price={_raw(model.get('price'))} retail={_raw(model.get('retail'))} discount={_raw(model.get('discount'))}; "
             f"tx={tx_text}; resultado: {outcome}")
    return price, retail, discount, debug


def _title_parts(og_title: str | None, seo_name: str) -> tuple[str, str]:
    """(nome, loja) a partir do og:title; sem correspondência: nome do slug e loja vazia."""
    if og_title:
        m = _TITLE_RE.match(og_title.strip())
        if m and m.group(1).strip():
            return m.group(1).strip(), m.group("store").strip()
    return seo_name.replace("-", " ").title(), ""


def parse_product_page(html: str, game_id: int, seo_name: str) -> Game:
    return parse_product_page_ex(html, game_id, seo_name)[0]


def parse_product_page_ex(html: str, game_id: int, seo_name: str) -> tuple[Game, str]:
    return parse_product_page_full(html, game_id, seo_name)[:2]


def parse_product_page_full(html: str, game_id: int, seo_name: str) -> tuple[Game, str, str]:
    """(jogo, origem do preço, diagnóstico). A página mostra a moeda do visitante: nunca devolve números que não sejam EUR."""
    model = scrape.extract_window_json(html, "productModel")
    if not isinstance(model, dict):
        raise scrape.ScrapeError("window.productModel ausente na página do jogo")
    try:
        found_id = int(model["prod_id"])
    except (KeyError, ValueError, TypeError) as e:
        raise scrape.ScrapeError("productModel sem prod_id válido") from e
    if found_id != game_id:
        raise scrape.ScrapeError("A página não corresponde ao jogo pedido")
    currency = next((a.get("content", "").strip().upper() for a in _meta_tags(html) if a.get("itemprop", "").lower() == "pricecurrency"), "")
    if currency == "EUR":
        try:
            price = float(model["price"])
            retail = float(model.get("retail") or price)
            discount = model.get("discount")
            if discount is None:
                discount = round((1 - price / retail) * 100) if retail > 0 else 0
            discount = int(discount)
        except (KeyError, ValueError, TypeError) as e:
            raise scrape.ScrapeError("productModel sem preço válido") from e
        source = "página EUR"
        debug = (f"moeda=EUR; model: price={_raw(model.get('price'))} retail={_raw(model.get('retail'))} "
                 f"discount={_raw(model.get('discount'))}; resultado: página em EUR")
    else:
        # moeda desconhecida ou não-EUR: o desconto da página não é fiável (é recalculado)
        price, retail, discount, debug = _non_eur_prices(html, currency, model)
        source = "página convertida" if price > 0 else "página sem preço"
    image = _meta_content(html, "og:image") or ""
    v = re.search(r"[?&]v=(\d+)", image)
    name, store = _title_parts(_meta_content(html, "og:title"), seo_name)
    game = Game(
        id=game_id,
        name=name,
        seo_name=seo_name,
        price=price,
        retail=retail,
        discount=discount,
        avail_date=None,
        preorder=bool(model.get("preorder")),
        is_dlc=False,
        is_pc=True,
        updated_at=int(v.group(1)) if v else 0,
        rank=0,
        store=store,
        retail_known=currency == "EUR",
    )
    return game, source, debug


def fetch_product_page(url: str, session=None) -> str:
    session = session or requests.Session()
    session.headers.update({"User-Agent": scrape.USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
    resp = session.get(url, timeout=30, allow_redirects=False)
    if resp.status_code != 200:  # inclui qualquer 3xx
        raise scrape.ScrapeError(f"A página do jogo devolveu HTTP {resp.status_code}")
    final = urlsplit(str(getattr(resp, "url", url)))
    if final.scheme != "https" or final.netloc.lower() != "www.instant-gaming.com":
        raise scrape.ScrapeError("A página do jogo não é de www.instant-gaming.com")
    return resp.text


def resolve_full(path: Path, fetch=fetch_product_page, pool: list[Game] | None = None,
                 sources: dict[int, str] | None = None) -> tuple[Game | None, str, list[str], str, str]:
    """Nunca levanta: qualquer falha vira um aviso genérico (sem URLs nem detalhes de rede).

    Se o jogo estiver na `pool` (listas, em EUR) usa esses dados e não pede a página.
    Devolve (jogo, nota, avisos, origem do preço, diagnóstico; este só vem de páginas de produto)."""
    try:
        pick = load_pick(path)
        if pick is None:
            return None, "", [], "", ""
        game_id, slug = parse_pick_url(pick["url"])
        note = _clean_note(pick["note"])
        for g in pool or []:
            if g.id == game_id:
                return replace(g, rank=0), note, [], (sources or {}).get(game_id, "lista EUR"), ""
        canonical = f"https://www.instant-gaming.com/pt/{game_id}-comprar-{slug}/"
        game, source, debug = parse_product_page_full(fetch(canonical), game_id, slug)
        return game, note, [], source, debug
    except Exception:  # noqa: BLE001 - a escolha manual nunca pode derrubar a execução semanal
        return None, "", [_WARNING], "", ""


def resolve_ex(path: Path, fetch=fetch_product_page, pool: list[Game] | None = None,
               sources: dict[int, str] | None = None) -> tuple[Game | None, str, list[str], str]:
    return resolve_full(path, fetch, pool, sources)[:4]


def resolve(path: Path, fetch=fetch_product_page, pool: list[Game] | None = None) -> tuple[Game | None, str, list[str]]:
    return resolve_full(path, fetch, pool)[:3]


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="garciaig.streamer", description="Gere o destaque manual do streamer.")
    ap.add_argument("--path", type=Path, default=DEFAULT_PATH, help="Ficheiro da escolha (por omissão data/streamer_pick.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="Define o jogo do streamer (só valida o link; não faz pedidos)")
    s.add_argument("--url", required=True)
    s.add_argument("--note", default="")
    sub.add_parser("clear", help="Remove a escolha do streamer")
    sub.add_parser("show", help="Mostra a escolha atual")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "set":
            data = save_pick(a.path, a.url, a.note)
            print(f"Destaque do streamer guardado: {data['url']}")
        elif a.cmd == "clear":
            clear_pick(a.path)
            print("Destaque do streamer removido.")
        else:
            pick = load_pick(a.path)
            print("Sem destaque do streamer." if pick is None else f"{pick['url']}\n{pick['note']}".rstrip())
    except ValueError as e:
        print(f"ERRO: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
