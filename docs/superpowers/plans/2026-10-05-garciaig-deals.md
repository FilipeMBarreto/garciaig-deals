# GarciaIG Deals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline semanal que recolhe jogos da Instant Gaming (PT), escolhe 6 blocos, gera um site estático com links `?igr=garciap` e um payload de Discord.

**Architecture:** Módulos pequenos e puros (`affiliate`, `scrape`, `select`, `history`, `render`, `discord`) orquestrados por `main.py`. O scraping é HTTP + extração do JSON embebido nas páginas (`window.searchResults`, `window.productsListedByTimeFrame`). Tudo o que decide é função pura testável com snapshot real.

**Tech Stack:** Python 3.11+, requests, Jinja2, pytest. GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-10-05-garciaig-deals-design.md`

## Global Constraints

- Todo URL publicado (site e Discord) para a Instant Gaming é exatamente `https://www.instant-gaming.com/pt/{id}-comprar-{seo_name}/?igr=garciap`; nenhum outro parâmetro.
- Nunca pedir `/pt/pesquisar/`, nunca usar a chave Algolia exposta, nunca usar `?igr=` nos pedidos de scraping.
- Pausa de 2,5 s entre pedidos; User-Agent identificável; 3 pedidos por execução.
- Semana = semana ISO (segunda a domingo). Pausa de repetição = 4 semanas, só nos blocos de preço.
- Escalões de preço (EUR): 20 → (10,20], 10 → (5,10], 5 → (2,5], 2 → (0,2]. 5 jogos por escalão. Sem DLCs, sem gratuitos.
- Textos do site e do Discord em português de Portugal.
- Sem commits git neste plano (o repositório não está inicializado e o utilizador não os pediu). Cada tarefa termina com um checkpoint de testes.
- Comandos assumem diretoria de trabalho `/Volumes/Dock SSD/Projetos/GarciaIG` e o venv `.venv` ativo (`source .venv/bin/activate`).

---

### Task 1: Scaffold, modelos e links de afiliado

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/garciaig/__init__.py`, `src/garciaig/models.py`, `src/garciaig/affiliate.py`, `src/garciaig/fmt.py`
- Test: `tests/test_affiliate.py`, `tests/test_fmt.py`

**Interfaces:**
- Produces:
  - `models.Game` (frozen dataclass): `id:int, name:str, seo_name:str, price:float, retail:float, discount:int, avail_date:int|None, preorder:bool, is_dlc:bool, is_pc:bool, updated_at:int=0, rank:int=10_000`; propriedades `release_date -> date|None` (UTC) e `cover_url -> str`.
  - `models.Week` (dataclass): `key:str, start:date, end:date, featured:Game|None, preorder:Game|None, tiers:dict[str,list[Game]], warnings:list[str]`.
  - `affiliate.REF = "garciap"`, `affiliate.with_ref(url:str)->str`, `affiliate.game_url(game_id:int, seo_name:str)->str`, `affiliate.assert_all_affiliate(urls:Iterable[str])->None` (levanta `ValueError`).
  - `fmt.fmt_price(v:float)->str` (`"12,39 €"`), `fmt.fmt_date(d:date)->str` (`"6 de outubro"`).

- [ ] **Step 1: Criar ambiente e ficheiros base**

```bash
cd "/Volumes/Dock SSD/Projetos/GarciaIG"
python3 -m venv .venv && source .venv/bin/activate
mkdir -p src/garciaig tests/fixtures templates data site
```

`pyproject.toml`:
```toml
[project]
name = "garciaig"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "jinja2>=3.1"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
site/
```

`src/garciaig/__init__.py`: ficheiro vazio.

Run: `pip install -e ".[dev]"` — Expected: instala sem erros.

- [ ] **Step 2: Escrever os testes que falham**

`tests/test_affiliate.py`:
```python
import pytest
from garciaig import affiliate


def test_game_url_matches_user_example():
    assert (
        affiliate.game_url(21378, "star-wars-galactic-racer-pc-steam")
        == "https://www.instant-gaming.com/pt/21378-comprar-star-wars-galactic-racer-pc-steam/?igr=garciap"
    )


def test_with_ref_strips_existing_query_and_fragment():
    url = "https://www.instant-gaming.com/pt/12335-comprar-x-pc-steam/?itm_source=daily_deals&itm_medium=product_deals#top"
    assert affiliate.with_ref(url) == "https://www.instant-gaming.com/pt/12335-comprar-x-pc-steam/?igr=garciap"


def test_assert_all_affiliate_passes_and_fails():
    good = "https://www.instant-gaming.com/pt/1-comprar-a/?igr=garciap"
    affiliate.assert_all_affiliate([good])
    with pytest.raises(ValueError):
        affiliate.assert_all_affiliate([good, "https://www.instant-gaming.com/pt/2-comprar-b/"])
    with pytest.raises(ValueError):
        affiliate.assert_all_affiliate(["https://www.instant-gaming.com/pt/2-comprar-b/?igr=garciap&x=1"])
```

`tests/test_fmt.py`:
```python
from datetime import date
from garciaig.fmt import fmt_price, fmt_date


def test_fmt_price_pt():
    assert fmt_price(12.39) == "12,39 €"
    assert fmt_price(2) == "2,00 €"


def test_fmt_date_pt():
    assert fmt_date(date(2026, 10, 6)) == "6 de outubro"
    assert fmt_date(date(2026, 3, 1)) == "1 de março"
```

- [ ] **Step 3: Correr e confirmar falha**

Run: `pytest tests/test_affiliate.py tests/test_fmt.py -v`
Expected: FAIL (`ModuleNotFoundError` / `ImportError`).

- [ ] **Step 4: Implementar**

`src/garciaig/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class Game:
    id: int
    name: str
    seo_name: str
    price: float
    retail: float
    discount: int
    avail_date: int | None
    preorder: bool
    is_dlc: bool
    is_pc: bool
    updated_at: int = 0
    rank: int = 10_000

    @property
    def release_date(self) -> date | None:
        if self.avail_date is None:
            return None
        return datetime.fromtimestamp(self.avail_date, tz=timezone.utc).date()

    @property
    def cover_url(self) -> str:
        return f"https://gaming-cdn.com/images/products/{self.id}/380x218/{self.id}-cover.jpg?v={self.updated_at}"


@dataclass
class Week:
    key: str
    start: date
    end: date
    featured: Game | None
    preorder: Game | None
    tiers: dict[str, list[Game]]
    warnings: list[str] = field(default_factory=list)
```

`src/garciaig/affiliate.py`:
```python
from __future__ import annotations

from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

REF = "garciap"
BASE = "https://www.instant-gaming.com/pt"
_SUFFIX = f"?igr={REF}"


def with_ref(url: str) -> str:
    """Devolve o URL sem query/fragmento e com o código de afiliado."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", "")) + _SUFFIX


def game_url(game_id: int, seo_name: str) -> str:
    return with_ref(f"{BASE}/{game_id}-comprar-{seo_name}/")


def assert_all_affiliate(urls: Iterable[str]) -> None:
    bad = [u for u in urls if not u.endswith(_SUFFIX) or u.count("?") != 1]
    if bad:
        raise ValueError(f"URLs sem o sufixo de afiliado exato: {bad[:3]}")
```

`src/garciaig/fmt.py`:
```python
from __future__ import annotations

from datetime import date

_MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def fmt_price(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " €"


def fmt_date(d: date) -> str:
    return f"{d.day} de {_MONTHS[d.month - 1]}"
```

- [ ] **Step 5: Confirmar que passa**

Run: `pytest tests/test_affiliate.py tests/test_fmt.py -v`
Expected: PASS (5 testes).

---

### Task 2: Recolha e parsing dos dados (scrape)

**Files:**
- Create: `src/garciaig/scrape.py`, `tests/fixtures/tendencias.html`, `tests/fixtures/pre-reservas.html`, `tests/fixtures/proximos-lancamentos.html`
- Test: `tests/test_scrape.py`

**Interfaces:**
- Consumes: `models.Game`.
- Produces:
  - `scrape.PAGES: dict[str,str]` chaves `"trend","pre","upcoming"`; `scrape.OFFLINE_FILES: dict[str,str]` com os nomes dos fixtures.
  - `scrape.ScrapeError(RuntimeError)`.
  - `scrape.extract_window_json(html:str, name:str) -> object|None`.
  - `scrape.parse_search_results(html:str, ranked:bool=True) -> list[Game]`.
  - `scrape.parse_time_frames(html:str) -> list[Game]`.
  - `scrape.build_pool(trend_html:str, pre_html:str, upcoming_html:str) -> list[Game]` (sem ids repetidos; prioridade trend > pre > upcoming).
  - `scrape.fetch_all(session=None, delay:float=2.5, sleep=time.sleep) -> dict[str,str]`.
  - `scrape.load_offline(directory:Path) -> dict[str,str]`.

- [ ] **Step 1: Guardar snapshot real como fixtures**

```bash
S=/private/tmp/claude-501/-Volumes-Dock-SSD-Projetos-GarciaIG/b97e8878-7c45-402d-b1f4-662c74192515/scratchpad
cp "$S/tendencias.html" tests/fixtures/tendencias.html
cp "$S/pre-reservas.html" tests/fixtures/pre-reservas.html
cp "$S/proximos-lancamentos.html" tests/fixtures/proximos-lancamentos.html
ls -l tests/fixtures
```
Expected: 3 ficheiros (cerca de 0,4 a 0,7 MB cada). Se o scratchpad já não existir, recolher de novo com `python -c "from garciaig import scrape; ..."` após a Task 2 (ver Step 4) e gravar aqui.

- [ ] **Step 2: Escrever os testes que falham**

`tests/test_scrape.py`:
```python
from pathlib import Path
import pytest
from garciaig import scrape

FIX = Path(__file__).parent / "fixtures"


def test_extract_window_json_reads_object_and_ignores_trailing_js():
    html = '<script>window.foo = {"a": [1, 2]}; window.bar = 3;</script>'
    assert scrape.extract_window_json(html, "foo") == {"a": [1, 2]}
    assert scrape.extract_window_json(html, "missing") is None


def test_parse_search_results_normalises_item_and_rank():
    html = (
        'window.searchResults = {"hits":[{"prod_id":1,"name":"A","seo_name":"a-pc-steam",'
        '"price":"39.99","retail":"59.99","discount":33,"avail_date":1791244800,"preorder":1,'
        '"is_dlc":0,"platforms":["1"],"updated_at":7},'
        '{"prod_id":2,"name":"B","seo_name":"b","price":"5.00","retail":"5.00","avail_date":null,'
        '"preorder":0,"is_dlc":1,"platforms":"1,2"}]};'
    )
    a, b = scrape.parse_search_results(html)
    assert (a.id, a.price, a.retail, a.discount, a.preorder, a.is_pc, a.rank) == (1, 39.99, 59.99, 33, True, True, 0)
    assert a.release_date.isoformat() == "2026-10-06"
    assert (b.is_dlc, b.is_pc, b.avail_date, b.discount, b.rank) == (True, True, None, 0, 1)
    unranked = scrape.parse_search_results(html, ranked=False)
    assert all(g.rank == 10_000 for g in unranked)


def test_platform_not_pc():
    html = 'window.searchResults = {"hits":[{"prod_id":3,"name":"C","seo_name":"c","price":"1","platforms":"5"}]};'
    assert scrape.parse_search_results(html)[0].is_pc is False


def test_parse_time_frames_flattens_groups():
    html = (
        'window.productsListedByTimeFrame = {"5":{"one_month_ago":{"10":{"prod_id":10,"name":"X",'
        '"seo_name":"x","price":"12.39","retail":"14.99","avail_date":1788220800,"preorder":0,'
        '"is_dlc":0,"platforms":"1"}}},"7":{"next_month":{"11":{"prod_id":11,"name":"Y",'
        '"seo_name":"y","price":"9.99","retail":"9.99","avail_date":1795000000,"preorder":1,'
        '"is_dlc":0,"platforms":"1"}}}};'
    )
    games = scrape.parse_time_frames(html)
    assert sorted(g.id for g in games) == [10, 11]
    assert games[0].discount == round((1 - 12.39 / 14.99) * 100)


def test_missing_data_raises():
    with pytest.raises(scrape.ScrapeError):
        scrape.parse_search_results("<html>sem dados</html>")
    with pytest.raises(scrape.ScrapeError):
        scrape.parse_time_frames("<html>sem dados</html>")


def test_build_pool_on_real_snapshot():
    htmls = scrape.load_offline(FIX)
    pool = scrape.build_pool(htmls["trend"], htmls["pre"], htmls["upcoming"])
    ids = [g.id for g in pool]
    assert len(ids) == len(set(ids))
    assert len(pool) > 300
    assert any(g.preorder for g in pool)
    assert any(g.rank < 60 for g in pool)  # vem de /tendencias/
    assert all(g.price >= 0 for g in pool)


def test_fetch_all_sleeps_between_requests_and_checks_status():
    calls, sleeps = [], []

    class R:
        def __init__(self, code): self.status_code, self.text = code, "<html/>"

    class S:
        headers = {}
        def get(self, url, timeout):
            calls.append(url)
            return R(200)

    out = scrape.fetch_all(session=S(), delay=2.5, sleep=sleeps.append)
    assert list(out) == ["trend", "pre", "upcoming"]
    assert len(calls) == 3 and sleeps == [2.5, 2.5]
    assert all("pesquisar" not in u for u in calls)

    class Bad(S):
        def get(self, url, timeout): return R(403)

    with pytest.raises(scrape.ScrapeError):
        scrape.fetch_all(session=Bad(), sleep=lambda s: None)
```

- [ ] **Step 3: Correr e confirmar falha**

Run: `pytest tests/test_scrape.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 4: Implementar**

`src/garciaig/scrape.py`:
```python
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from .models import Game

BASE = "https://www.instant-gaming.com/pt"
PAGES = {
    "trend": f"{BASE}/tendencias/",
    "pre": f"{BASE}/pre-reservas/",
    "upcoming": f"{BASE}/proximos-lancamentos/",
}
OFFLINE_FILES = {
    "trend": "tendencias.html",
    "pre": "pre-reservas.html",
    "upcoming": "proximos-lancamentos.html",
}
USER_AGENT = "GarciaIG-Deals/0.1 (weekly showcase for garciap; contact via repository)"
DELAY_SECONDS = 2.5
UNRANKED = 10_000

_DECODER = json.JSONDecoder()


class ScrapeError(RuntimeError):
    pass


def extract_window_json(html: str, name: str):
    m = re.search(r"window\." + re.escape(name) + r"\s*=\s*", html)
    if not m:
        return None
    try:
        value, _ = _DECODER.raw_decode(html, m.end())
    except json.JSONDecodeError as e:
        raise ScrapeError(f"JSON inválido em window.{name}: {e}") from e
    return value


def _platform_ids(raw) -> set[str]:
    if raw is None:
        return set()
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    return {str(p).strip() for p in parts if str(p).strip()}


def _to_game(item: dict, rank: int) -> Game:
    price = float(item["price"])
    retail = float(item.get("retail") or price)
    discount = item.get("discount")
    if discount is None:
        discount = round((1 - price / retail) * 100) if retail > 0 else 0
    return Game(
        id=int(item["prod_id"]),
        name=item["name"],
        seo_name=item["seo_name"],
        price=price,
        retail=retail,
        discount=int(discount),
        avail_date=int(item["avail_date"]) if item.get("avail_date") else None,
        preorder=bool(item.get("preorder")),
        is_dlc=bool(item.get("is_dlc")),
        is_pc="1" in _platform_ids(item.get("platforms")),
        updated_at=int(item.get("updated_at") or 0),
        rank=rank,
    )


def _convert(items, ranked: bool) -> list[Game]:
    games = []
    for i, item in enumerate(items):
        try:
            games.append(_to_game(item, i if ranked else UNRANKED))
        except (KeyError, ValueError, TypeError):
            continue  # item incompleto: ignorar
    return games


def parse_search_results(html: str, ranked: bool = True) -> list[Game]:
    data = extract_window_json(html, "searchResults")
    if not data or not data.get("hits"):
        raise ScrapeError("window.searchResults ausente ou vazio")
    games = _convert(data["hits"], ranked)
    if not games:
        raise ScrapeError("nenhum produto válido em window.searchResults")
    return games


def parse_time_frames(html: str) -> list[Game]:
    data = extract_window_json(html, "productsListedByTimeFrame")
    if not data:
        raise ScrapeError("window.productsListedByTimeFrame ausente ou vazio")
    items = [it for group in data.values() for frame in group.values() for it in frame.values()]
    games = _convert(items, ranked=False)
    if not games:
        raise ScrapeError("nenhum produto válido em productsListedByTimeFrame")
    return games


def build_pool(trend_html: str, pre_html: str, upcoming_html: str) -> list[Game]:
    pool: dict[int, Game] = {}
    for game in (
        parse_search_results(trend_html, ranked=True)
        + parse_search_results(pre_html, ranked=False)
        + parse_time_frames(upcoming_html)
    ):
        pool.setdefault(game.id, game)
    return list(pool.values())


def fetch_all(session=None, delay: float = DELAY_SECONDS, sleep=time.sleep) -> dict[str, str]:
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
    out: dict[str, str] = {}
    for i, (key, url) in enumerate(PAGES.items()):
        if i:
            sleep(delay)
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            raise ScrapeError(f"{url} devolveu HTTP {resp.status_code}")
        out[key] = resp.text
    return out


def load_offline(directory: Path) -> dict[str, str]:
    directory = Path(directory)
    return {k: (directory / name).read_text(encoding="utf-8", errors="ignore") for k, name in OFFLINE_FILES.items()}
```

- [ ] **Step 5: Confirmar que passa**

Run: `pytest tests/test_scrape.py -v`
Expected: PASS (7 testes).

- [ ] **Step 6: Verificar o User-Agent identificável contra o site real**

```bash
python - <<'EOF'
from garciaig import scrape
h = scrape.fetch_all()
print({k: len(v) for k, v in h.items()})
pool = scrape.build_pool(h["trend"], h["pre"], h["upcoming"])
print(len(pool), "jogos no pool")
EOF
```
Expected: 3 páginas e centenas de jogos. **Se devolver HTTP 403**, trocar `USER_AGENT` por um UA de browser comum (`Mozilla/5.0 ... Chrome/124 Safari/537.36`), documentar a razão num comentário na constante e repetir. Não contornar de outras formas (sem proxies, sem rotação).

---

### Task 3: Histórico

**Files:**
- Create: `src/garciaig/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `models.Week`.
- Produces:
  - `history.load(path:Path)->dict` (devolve `{"weeks": []}` se o ficheiro não existe).
  - `history.save(path:Path, hist:dict)->None`.
  - `history.recent_ids(hist:dict, week_key:str, weeks:int=4)->set[int]` (ids dos blocos de preço das últimas `weeks` entradas com chave `< week_key`).
  - `history.preorder_ids(hist:dict)->set[int]` (todos os ids que já foram pré-venda destacada).
  - `history.record(hist:dict, week:Week)->dict` (devolve novo dict; substitui a entrada da mesma semana; ordenado; máx. 52).

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_history.py`:
```python
from datetime import date
from garciaig import history
from garciaig.models import Game, Week


def g(i):
    return Game(i, f"G{i}", f"g{i}", 5.0, 5.0, 0, None, False, False, True)


def week(key, featured=None, preorder=None, tiers=None):
    return Week(key, date(2026, 1, 1), date(2026, 1, 7), featured, preorder, tiers or {"20": [], "10": [], "5": [], "2": []})


def test_load_missing_file(tmp_path):
    assert history.load(tmp_path / "nope.json") == {"weeks": []}


def test_record_save_load_roundtrip(tmp_path):
    h = history.record({"weeks": []}, week("2026-W40", g(1), g(2), {"20": [g(3)], "10": [], "5": [], "2": []}))
    p = tmp_path / "h.json"
    history.save(p, h)
    assert history.load(p) == h
    assert h["weeks"][0] == {"week": "2026-W40", "featured": 1, "preorder": 2, "tiers": {"20": [3], "10": [], "5": [], "2": []}}


def test_record_same_week_is_idempotent():
    h = history.record({"weeks": []}, week("2026-W40", tiers={"20": [g(1)], "10": [], "5": [], "2": []}))
    h = history.record(h, week("2026-W40", tiers={"20": [g(9)], "10": [], "5": [], "2": []}))
    assert len(h["weeks"]) == 1 and h["weeks"][0]["tiers"]["20"] == [9]


def test_recent_ids_window_excludes_current_and_old():
    h = {"weeks": []}
    for n, gid in enumerate([11, 12, 13, 14, 15, 16], start=30):
        h = history.record(h, week(f"2026-W{n}", tiers={"20": [g(gid)], "10": [], "5": [], "2": []}))
    # semana atual W36: últimas 4 anteriores = W32..W35 -> ids 13,14,15 ... W35 é id 16? (W30=11 ... W35=16)
    assert history.recent_ids(h, "2026-W36", weeks=4) == {13, 14, 15, 16}
    # re-executar W35 não conta W35 nem posteriores
    assert history.recent_ids(h, "2026-W35", weeks=4) == {12, 13, 14, 15}


def test_featured_and_preorder_do_not_count_for_pause():
    h = history.record({"weeks": []}, week("2026-W40", g(1), g(2)))
    assert history.recent_ids(h, "2026-W41") == set()
    assert history.preorder_ids(h) == {2}
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `pytest tests/test_history.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar**

`src/garciaig/history.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from .models import Week

MAX_WEEKS = 52


def load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"weeks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, hist: dict) -> None:
    Path(path).write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def recent_ids(hist: dict, week_key: str, weeks: int = 4) -> set[int]:
    previous = sorted((w for w in hist["weeks"] if w["week"] < week_key), key=lambda w: w["week"])[-weeks:]
    return {i for w in previous for ids in w["tiers"].values() for i in ids}


def preorder_ids(hist: dict) -> set[int]:
    return {w["preorder"] for w in hist["weeks"] if w.get("preorder") is not None}


def record(hist: dict, week: Week) -> dict:
    entry = {
        "week": week.key,
        "featured": week.featured.id if week.featured else None,
        "preorder": week.preorder.id if week.preorder else None,
        "tiers": {k: [g.id for g in games] for k, games in week.tiers.items()},
    }
    others = [w for w in hist["weeks"] if w["week"] != week.key]
    return {"weeks": sorted(others + [entry], key=lambda w: w["week"])[-MAX_WEEKS:]}
```

- [ ] **Step 4: Confirmar que passa**

Run: `pytest tests/test_history.py -v`
Expected: PASS (5 testes). Nota: a comparação `w["week"] < week_key` usa strings `YYYY-Www`, ordenáveis porque a semana tem sempre 2 dígitos.

---

### Task 4: Seleção dos blocos

**Files:**
- Create: `src/garciaig/select.py`
- Test: `tests/test_select.py`

**Interfaces:**
- Consumes: `models.Game`, `models.Week`.
- Produces:
  - `select.TIERS = (("20",10.0,20.0),("10",5.0,10.0),("5",2.0,5.0),("2",0.0,2.0))`, `select.PER_TIER = 5`.
  - `select.week_key(today:date)->str` (`"2026-W41"`), `select.week_bounds(today:date)->tuple[date,date]`.
  - `select.family(name:str)->str`, `select.is_edition(game:Game)->bool`.
  - `select.select_week(pool:list[Game], recent_ids:set[int], preorder_ids:set[int], today:date)->Week`.

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_select.py`:
```python
from datetime import date, datetime, timezone
from pathlib import Path
from garciaig import scrape, select
from garciaig.models import Game

TODAY = date(2026, 10, 5)  # segunda-feira, semana 2026-W41 (5 a 11 de outubro)


def ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def mk(i, name, price, release, *, preorder=False, dlc=False, pc=True, rank=10_000, retail=None, discount=0):
    return Game(i, name, f"s{i}", price, retail or price, discount, ts(release) if release else None, preorder, dlc, pc, 0, rank)


def test_week_key_and_bounds():
    assert select.week_key(TODAY) == "2026-W41"
    assert select.week_bounds(TODAY) == (date(2026, 10, 5), date(2026, 10, 11))
    assert select.week_bounds(date(2026, 10, 11)) == (date(2026, 10, 5), date(2026, 10, 11))


def test_family_and_edition():
    assert select.family("Transport Fever 3 - Deluxe Edition") == "transport fever 3"
    assert select.family("Planet Zoo 2 Deluxe Edition") == select.family("Planet Zoo 2")
    assert select.family("ACE COMBAT 8: WINGS OF THEVE Deluxe Edition") == select.family("ACE COMBAT 8: WINGS OF THEVE")
    assert select.family("Gears of War: E-Day Premium Edition + Acesso avançado") == select.family("Gears of War: E-Day")
    assert select.family("Castlevania: Belmont's Curse Midnight Edition") == select.family("Castlevania: Belmont's Curse")
    assert select.is_edition(mk(1, "Planet Zoo 2 Deluxe Edition", 1, TODAY))
    assert not select.is_edition(mk(2, "Planet Zoo 2", 1, TODAY))


def test_featured_is_release_this_week_preferring_base_then_rank():
    pool = [
        mk(1, "Game A Deluxe Edition", 60, date(2026, 10, 6), preorder=True, rank=0),
        mk(2, "Game A", 50, date(2026, 10, 6), preorder=True, rank=5),
        mk(3, "Game B", 40, date(2026, 10, 7), preorder=True, rank=1),
        mk(4, "Old", 30, date(2026, 10, 1)),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 3  # base edition com melhor rank (1) vence a Game A (rank 5)


def test_featured_prefers_previous_preorder_highlight():
    pool = [mk(2, "Game A", 50, date(2026, 10, 6), preorder=True, rank=0), mk(3, "Game B", 40, date(2026, 10, 7), preorder=True, rank=1)]
    w = select.select_week(pool, set(), {3}, TODAY)
    assert w.featured.id == 3 or w.featured.id == 2
    assert w.featured.id == 3


def test_featured_falls_back_to_previous_week_with_warning():
    pool = [mk(1, "Last Week", 30, date(2026, 9, 30))]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 1 and any("semana anterior" in x for x in w.warnings)


def test_no_featured_candidate_warns():
    w = select.select_week([mk(1, "Ancient", 30, date(2020, 1, 1))], set(), set(), TODAY)
    assert w.featured is None and any("destaque" in x.lower() for x in w.warnings)


def test_preorder_is_closest_next_week_and_not_featured_family():
    pool = [
        mk(1, "Now Game", 40, date(2026, 10, 6), preorder=True, rank=0),
        mk(2, "Planet Zoo 2 Deluxe Edition", 49, date(2026, 10, 13), preorder=True),
        mk(3, "Planet Zoo 2", 38, date(2026, 10, 13), preorder=True),
        mk(4, "Castlevania", 21, date(2026, 10, 15), preorder=True),
    ]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured.id == 1
    assert w.preorder.id == 3  # data mais próxima, edição base


def test_preorder_falls_back_to_later_with_warning():
    pool = [mk(1, "Now", 40, date(2026, 10, 6), preorder=True), mk(2, "Far", 40, date(2026, 11, 20), preorder=True)]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.preorder.id == 2 and any("pré-venda" in x for x in w.warnings)


def test_tiers_exclusive_ranges_and_exclusions():
    pool = [
        mk(10, "Now", 40, date(2026, 10, 6), preorder=True),
        mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True),
        mk(20, "T20", 15, date(2026, 9, 1)),
        mk(21, "T10 edge", 10, date(2026, 9, 1)),
        mk(22, "T5", 4.99, date(2026, 9, 1)),
        mk(23, "T2", 2, date(2026, 9, 1)),
        mk(24, "Free", 0, date(2026, 9, 1)),
        mk(25, "DLC", 3, date(2026, 9, 1), dlc=True),
        mk(26, "Console", 3, date(2026, 9, 1), pc=False),
        mk(27, "Recent", 3, date(2026, 9, 1)),
        mk(28, "Unreleased", 3, date(2026, 12, 1), preorder=True),
    ]
    w = select.select_week(pool, recent_ids={27}, preorder_ids=set(), today=TODAY)
    ids = {k: [g.id for g in v] for k, v in w.tiers.items()}
    assert ids == {"20": [20], "10": [21], "5": [22], "2": [23]}


def test_tier_caps_at_five_orders_by_rank_then_discount_and_dedupes_families():
    pool = [mk(10, "Now", 40, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True)]
    pool += [mk(100 + i, f"Cheap {i}", 15, date(2026, 9, 1), rank=i) for i in range(8)]
    pool += [mk(200, "Cheap 0 Deluxe Edition", 18, date(2026, 9, 1), rank=0)]
    w = select.select_week(pool, set(), set(), TODAY)
    ids = [g.id for g in w.tiers["20"]]
    assert len(ids) == 5 and ids[0] == 100 and 200 not in ids
    assert ids == [100, 101, 102, 103, 104]


def test_underfilled_tier_warns_never_pads():
    pool = [mk(10, "Now", 40, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 40, date(2026, 10, 13), preorder=True), mk(1, "One", 1.5, date(2026, 9, 1))]
    w = select.select_week(pool, set(), set(), TODAY)
    assert [g.id for g in w.tiers["2"]] == [1]
    assert any("até 2" in x for x in w.warnings) and w.tiers["20"] == []


def test_featured_and_preorder_excluded_from_tiers():
    pool = [mk(10, "Now", 15, date(2026, 10, 6), preorder=True), mk(11, "Zoo", 15, date(2026, 10, 13), preorder=True)]
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.tiers["20"] == []


def test_real_snapshot_selection():
    fix = Path(__file__).parent / "fixtures"
    h = scrape.load_offline(fix)
    pool = scrape.build_pool(h["trend"], h["pre"], h["upcoming"])
    w = select.select_week(pool, set(), set(), TODAY)
    assert w.featured and date(2026, 10, 5) <= w.featured.release_date <= date(2026, 10, 11)
    assert w.preorder and date(2026, 10, 12) <= w.preorder.release_date <= date(2026, 10, 18)
    for key, lo, hi in select.TIERS:
        assert all(lo < g.price <= hi and not g.is_dlc and g.is_pc for g in w.tiers[key])
    ids = [g.id for games in w.tiers.values() for g in games] + [w.featured.id, w.preorder.id]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `pytest tests/test_select.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar**

`src/garciaig/select.py`:
```python
from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Game, Week

TIERS = (("20", 10.0, 20.0), ("10", 5.0, 10.0), ("5", 2.0, 5.0), ("2", 0.0, 2.0))
PER_TIER = 5

_ADJ = r"(?:digital|deluxe|premium|ultimate|gold|complete|collector'?s?|standard|definitive|special|day one|launch)"
_EDITION_RE = re.compile(rf"(?:\s*[-–:])?\s+(?:{_ADJ}\s+)*(?:[\w']+\s+)?edition\b.*$", re.IGNORECASE)


def family(name: str) -> str:
    """Nome base do jogo, sem sufixos de edição (Deluxe, Premium, ...)."""
    return _EDITION_RE.sub("", name).strip().lower()


def is_edition(game: Game) -> bool:
    return family(game.name) != game.name.strip().lower()


def week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def week_key(today: date) -> str:
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _base_order(g: Game):
    return (is_edition(g), g.rank, -g.retail, g.id)


def select_week(pool: list[Game], recent_ids: set[int], preorder_ids: set[int], today: date) -> Week:
    start, end = week_bounds(today)
    warnings: list[str] = []
    base = [g for g in pool if g.is_pc and not g.is_dlc and g.release_date is not None]

    # Destaque
    this_week = [g for g in base if start <= g.release_date <= end and g.price > 0]
    prev_week = [
        g for g in base
        if start - timedelta(days=7) <= g.release_date < start and not g.preorder and g.price > 0
    ]
    featured_pool = this_week or prev_week
    if featured_pool and not this_week:
        warnings.append("Sem lançamentos na semana corrente; destaque tirado da semana anterior.")
    featured = min(featured_pool, key=lambda g: (g.id not in preorder_ids,) + _base_order(g), default=None)
    if featured is None:
        warnings.append("Sem candidato a destaque esta semana.")

    # Pré-venda da semana seguinte
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=7)
    featured_family = family(featured.name) if featured else None

    def eligible(g: Game) -> bool:
        return (g.preorder or g.release_date > today) and (featured is None or (g.id != featured.id and family(g.name) != featured_family))

    nxt = [g for g in base if next_start <= g.release_date <= next_end and eligible(g)]
    order = lambda g: (g.release_date, is_edition(g), g.rank, -g.retail, g.id)  # noqa: E731
    preorder = min(nxt, key=order, default=None)
    if preorder is None:
        later = [g for g in base if g.release_date > next_end and g.preorder and eligible(g)]
        preorder = min(later, key=order, default=None)
        warnings.append(
            "Sem pré-venda para a semana seguinte; usada a mais próxima depois dela."
            if preorder else "Sem nenhuma pré-venda disponível."
        )

    # Blocos de preço
    chosen = [g for g in (featured, preorder) if g]
    chosen_ids = {g.id for g in chosen}
    seen_families = {family(g.name) for g in chosen}
    released = [
        g for g in base
        if not g.preorder and g.release_date <= today and g.price > 0
        and g.id not in recent_ids and g.id not in chosen_ids
    ]
    tiers: dict[str, list[Game]] = {}
    for key, lo, hi in TIERS:
        candidates = sorted((g for g in released if lo < g.price <= hi), key=lambda g: (g.rank, -g.discount, g.name))
        picked: list[Game] = []
        for g in candidates:
            fam = family(g.name)
            if fam in seen_families:
                continue
            seen_families.add(fam)
            picked.append(g)
            if len(picked) == PER_TIER:
                break
        if len(picked) < PER_TIER:
            warnings.append(f"Bloco 'até {key} €': só {len(picked)} de {PER_TIER} candidatos disponíveis.")
        tiers[key] = picked

    return Week(week_key(today), start, end, featured, preorder, tiers, warnings)
```

- [ ] **Step 4: Confirmar que passa**

Run: `pytest tests/test_select.py -v`
Expected: PASS (11 testes). Se `test_family_and_edition` falhar num nome, ajustar **a regex `_EDITION_RE`** (não o teste) até todos os pares de nomes coincidirem; verificar com `python -c "from garciaig.select import family; print(family('...'))"`.

---

### Task 5: Site estático

**Files:**
- Create: `src/garciaig/render.py`, `templates/index.html.j2`, `templates/style.css`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `models.Week`, `affiliate.game_url`, `affiliate.assert_all_affiliate`, `fmt.fmt_price`, `fmt.fmt_date`.
- Produces: `render.render_site(week:Week, out_dir:Path, today:date)->Path` (escreve `index.html` e `style.css`, devolve o caminho do `index.html`; levanta `ValueError` se algum link para a Instant Gaming não tiver o sufixo exato). `render.TIER_TITLES: dict[str,str]`.

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_render.py`:
```python
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
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `pytest tests/test_render.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar `render.py`**

`src/garciaig/render.py`:
```python
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
TIER_TITLES = {"20": "Até 20 €", "10": "Até 10 €", "5": "Até 5 €", "2": "Até 2 €"}


def _card(g: Game) -> dict:
    return {
        "name": g.name,
        "url": affiliate.game_url(g.id, g.seo_name),
        "cover": g.cover_url,
        "price": fmt_price(g.price),
        "retail": fmt_price(g.retail) if g.discount > 0 else None,
        "discount": g.discount,
        "date": fmt_date(g.release_date) if g.release_date else None,
        "preorder": g.preorder,
    }


def render_site(week: Week, out_dir: Path, today: date) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("index.html.j2").render(
        week_label=week.key,
        period=f"{fmt_date(week.start)} a {fmt_date(week.end)}",
        updated=fmt_date(today),
        featured=_card(week.featured) if week.featured else None,
        preorder=_card(week.preorder) if week.preorder else None,
        tiers=[(TIER_TITLES[k], [_card(g) for g in week.tiers[k]]) for k in ("20", "10", "5", "2")],
    )
    links = re.findall(r'href="(https://www\.instant-gaming\.com[^"]*)"', html)
    affiliate.assert_all_affiliate(links)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(TEMPLATES / "style.css", out_dir / "style.css")
    return out_dir / "index.html"
```

- [ ] **Step 4: Implementar o template**

`templates/index.html.j2`:
```html
<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jogos da Semana · GarciaP</title>
  <meta name="description" content="Seleção semanal de jogos e ofertas na Instant Gaming para a comunidade do GarciaP.">
  <link rel="stylesheet" href="style.css">
</head>
<body>
{% macro card(g, big=False) %}
  <article class="card{% if big %} card-big{% endif %}">
    <a class="cover" href="{{ g.url }}" target="_blank" rel="sponsored noopener" aria-label="{{ g.name }}">
      <img src="{{ g.cover }}" alt="" loading="lazy" referrerpolicy="no-referrer">
      {% if g.discount %}<span class="badge">-{{ g.discount }}%</span>{% endif %}
    </a>
    <div class="body">
      <h3>{{ g.name }}</h3>
      {% if g.date %}<p class="meta">{% if g.preorder %}Pré-venda · {% endif %}Lançamento: {{ g.date }}</p>{% endif %}
      <p class="price"><strong>{{ g.price }}</strong>{% if g.retail %} <s>{{ g.retail }}</s>{% endif %}</p>
      <a class="btn" href="{{ g.url }}" target="_blank" rel="sponsored noopener">Ver na Instant Gaming</a>
    </div>
  </article>
{% endmacro %}

<header class="hero">
  <div class="wrap">
    <p class="eyebrow">Semana {{ week_label }} · {{ period }}</p>
    <h1>Jogos da Semana</h1>
    <p class="lede">A seleção semanal de ofertas da Instant Gaming para a comunidade do <strong>GarciaP</strong>.</p>
  </div>
</header>

<main class="wrap">
  <section>
    <h2>⭐ Destaque da Semana</h2>
    {% if featured %}{{ card(featured, true) }}{% else %}<p class="empty">Sem destaque esta semana.</p>{% endif %}
  </section>

  <section>
    <h2>⏳ Pré-venda da Próxima Semana</h2>
    {% if preorder %}{{ card(preorder, true) }}{% else %}<p class="empty">Sem pré-venda disponível.</p>{% endif %}
  </section>

  {% for title, games in tiers %}
  <section>
    <h2>{{ games|length if games else 0 }} {{ 'jogo' if games|length == 1 else 'jogos' }} · {{ title }}</h2>
    {% if games %}
    <div class="grid">{% for g in games %}{{ card(g) }}{% endfor %}</div>
    {% else %}
    <p class="empty">Sem candidatos esta semana.</p>
    {% endif %}
  </section>
  {% endfor %}
</main>

<footer class="wrap foot">
  <p>Os links desta página são links de afiliado: se comprares através deles, o GarciaP pode receber uma comissão, sem custo adicional para ti.</p>
  <p>Preços e disponibilidade podem mudar a qualquer momento. Site independente, não é um site oficial da Instant Gaming. Atualizado a {{ updated }}.</p>
</footer>
</body>
</html>
```

- [ ] **Step 5: Implementar o CSS**

`templates/style.css`:
```css
:root{--bg:#0e1020;--panel:#171a30;--panel2:#1f2342;--text:#eef0ff;--muted:#a3a8cf;--accent:#8b5cf6;--accent2:#22d3ee;--ok:#34d399;--radius:14px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
.hero{padding:48px 0 28px;background:radial-gradient(900px 300px at 20% -10%,#3b2a8a55,transparent),radial-gradient(700px 260px at 90% 0%,#0ea5b755,transparent)}
.eyebrow{margin:0 0 6px;color:var(--accent2);font-weight:600;letter-spacing:.04em;text-transform:uppercase;font-size:13px}
h1{margin:0 0 8px;font-size:clamp(2rem,6vw,3.2rem);line-height:1.1}
.lede{margin:0;color:var(--muted);max-width:60ch}
section{margin:36px 0}
h2{font-size:1.4rem;margin:0 0 14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}
.card{background:var(--panel);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;border:1px solid #ffffff10;transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-3px);border-color:var(--accent)}
.cover{position:relative;display:block;aspect-ratio:380/218;background:var(--panel2)}
.cover img{width:100%;height:100%;object-fit:cover;display:block}
.badge{position:absolute;top:10px;right:10px;background:var(--ok);color:#052e1d;font-weight:800;padding:2px 9px;border-radius:999px;font-size:14px}
.body{padding:14px;display:flex;flex-direction:column;gap:6px;flex:1}
.body h3{margin:0;font-size:1.02rem;line-height:1.25}
.meta{margin:0;color:var(--muted);font-size:13px}
.price{margin:2px 0 8px;font-size:1.25rem}
.price s{color:var(--muted);font-size:.9rem;margin-left:6px}
.btn{margin-top:auto;display:inline-block;text-align:center;text-decoration:none;color:#fff;background:linear-gradient(90deg,var(--accent),#6366f1);padding:10px 14px;border-radius:10px;font-weight:700}
.btn:hover{filter:brightness(1.12)}
.btn:focus-visible,.cover:focus-visible{outline:3px solid var(--accent2);outline-offset:2px}
.card-big{flex-direction:row}
.card-big .cover{flex:0 0 46%;aspect-ratio:auto;min-height:230px}
.card-big .body{padding:22px;justify-content:center}
.card-big h3{font-size:1.6rem}
.card-big .price{font-size:1.7rem}
.card-big .btn{margin-top:10px;align-self:flex-start}
.empty{color:var(--muted);background:var(--panel);border:1px dashed #ffffff22;border-radius:var(--radius);padding:18px;margin:0}
.foot{padding:28px 16px 48px;color:var(--muted);font-size:13px;border-top:1px solid #ffffff12}
@media (max-width:640px){
  .card-big{flex-direction:column}
  .card-big .cover{flex:none;min-height:0;aspect-ratio:380/218}
  .card-big .btn{align-self:stretch}
  .grid{grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
}
@media (prefers-reduced-motion:reduce){.card{transition:none}}
```

- [ ] **Step 6: Confirmar que passa**

Run: `pytest tests/test_render.py -v`
Expected: PASS (3 testes).

---

### Task 6: Payload e envio para o Discord

**Files:**
- Create: `src/garciaig/discord.py`
- Test: `tests/test_discord.py`

**Interfaces:**
- Consumes: `models.Week`, `affiliate.game_url`, `affiliate.assert_all_affiliate`, `fmt.fmt_price`, `render.TIER_TITLES`.
- Produces: `discord.build_payload(week:Week, site_url:str="")->dict` (`{"content": str, "embeds": [...]}`), `discord.send(payload:dict, webhook_url:str, post=requests.post)->None`, `discord.main(argv=None)->int` (lê `data/discord_payload.json` e a env `DISCORD_WEBHOOK_URL`; sai com 0 se não houver webhook).

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_discord.py`:
```python
import json
import re
from datetime import date
import pytest
from garciaig import discord
from garciaig.models import Game, Week


def game(i, name, price, preorder=False):
    return Game(i, name, f"slug-{i}", price, price, 0, 1791244800, preorder, False, True, 5, 0)


def make_week():
    return Week(
        "2026-W41", date(2026, 10, 5), date(2026, 10, 11),
        game(1, "Star [Wars]", 39.99, True), game(2, "Zoo", 38.49, True),
        {"20": [game(3, "A", 15)], "10": [], "5": [], "2": []},
    )


def test_payload_links_all_affiliate_and_markdown_safe():
    p = discord.build_payload(make_week(), "https://garcia.example/")
    text = json.dumps(p, ensure_ascii=False)
    links = re.findall(r"\((https://www\.instant-gaming\.com[^)]*)\)", text)
    assert len(links) == 3
    assert all(l.endswith("?igr=garciap") for l in links)
    assert "Star \\[Wars\\]" in p["embeds"][0]["description"]
    assert "https://garcia.example/" in p["content"]
    assert 1 <= len(p["embeds"]) <= 10
    assert all(len(e["description"]) <= 4096 for e in p["embeds"])
    assert len(p["content"]) <= 2000


def test_empty_blocks_are_omitted():
    titles = [e["title"] for e in discord.build_payload(make_week())["embeds"]]
    assert any("Destaque" in t for t in titles) and any("20" in t for t in titles)
    assert not any("até 2 €" in t.lower() for t in titles)


def test_send_posts_json_and_raises_on_error():
    seen = {}

    class R:
        def __init__(self, ok): self.ok = ok
        def raise_for_status(self):
            if not self.ok: raise RuntimeError("boom")

    def post(url, json, timeout):
        seen.update(url=url, json=json)
        return R(True)

    discord.send({"content": "x"}, "https://hook", post=post)
    assert seen == {"url": "https://hook", "json": {"content": "x"}}
    with pytest.raises(RuntimeError):
        discord.send({}, "https://hook", post=lambda url, json, timeout: R(False))


def test_main_without_webhook_is_noop(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    f.write_text("{}")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert discord.main([str(f)]) == 0
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `pytest tests/test_discord.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar**

`src/garciaig/discord.py`:
```python
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
                "title": f"🎮 {len(games)} jogos {TIER_TITLES[key].lower()}",
                "description": "\n".join(f"• {_line(g)}" for g in games),
                "color": 0x34D399,
            })
    content = f"🎮 **Jogos da semana ({week.key})** — links com o código do GarciaP."
    if site_url:
        content += f"\nTudo num só sítio: {site_url}"
    payload = {"content": content, "embeds": embeds}
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
    send(json.loads(path.read_text(encoding="utf-8")), webhook)
    print("Mensagem enviada para o Discord.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Confirmar que passa**

Run: `pytest tests/test_discord.py -v`
Expected: PASS (4 testes).

---

### Task 7: Orquestração, CLI e execução ponta-a-ponta

**Files:**
- Create: `src/garciaig/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: todos os módulos anteriores.
- Produces: `main.run(today:date, *, offline_dir:Path|None, data_dir:Path, out_dir:Path, site_url:str, dry_run:bool)->Week`; `main.cli(argv=None)->int`; `main.PipelineError(RuntimeError)`. Escreve `out_dir/index.html`, `data_dir/week.json`, `data_dir/discord_payload.json` e, se `dry_run` for falso, `data_dir/history.json`.

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_main.py`:
```python
import json
import re
from datetime import date
from pathlib import Path
import pytest
from garciaig import main

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 5)


def run(tmp_path, *, dry_run=False, today=TODAY):
    return main.run(today, offline_dir=FIX, data_dir=tmp_path / "data", out_dir=tmp_path / "site", site_url="https://garcia.example/", dry_run=dry_run)


def test_end_to_end_offline(tmp_path):
    (tmp_path / "data").mkdir()
    week = run(tmp_path)
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    links = re.findall(r'href="(https://www\.instant-gaming\.com[^"]*)"', html)
    assert links and all(l.endswith("?igr=garciap") for l in links)
    payload = json.loads((tmp_path / "data" / "discord_payload.json").read_text(encoding="utf-8"))
    assert payload["embeds"]
    saved = json.loads((tmp_path / "data" / "week.json").read_text(encoding="utf-8"))
    assert saved["week"] == "2026-W41" and saved["featured"]["url"].endswith("?igr=garciap")
    hist = json.loads((tmp_path / "data" / "history.json").read_text(encoding="utf-8"))
    assert hist["weeks"][0]["week"] == "2026-W41"
    assert week.featured is not None


def test_dry_run_does_not_write_history(tmp_path):
    (tmp_path / "data").mkdir()
    run(tmp_path, dry_run=True)
    assert not (tmp_path / "data" / "history.json").exists()
    assert (tmp_path / "site" / "index.html").exists()


def test_second_week_avoids_repeating_price_games(tmp_path):
    (tmp_path / "data").mkdir()
    w1 = run(tmp_path)
    w2 = run(tmp_path, today=date(2026, 10, 12))
    ids1 = {g.id for games in w1.tiers.values() for g in games}
    ids2 = {g.id for games in w2.tiers.values() for g in games}
    assert ids1 and not (ids1 & ids2)


def test_missing_featured_aborts_without_writing(tmp_path):
    (tmp_path / "data").mkdir()
    with pytest.raises(main.PipelineError):
        run(tmp_path, today=date(2031, 1, 6))  # nada lançado nessa semana nem na anterior
    assert not (tmp_path / "site" / "index.html").exists()
    assert not (tmp_path / "data" / "history.json").exists()
```

- [ ] **Step 2: Correr e confirmar falha**

Run: `pytest tests/test_main.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar**

`src/garciaig/main.py`:
```python
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
```

- [ ] **Step 4: Confirmar que passa**

Run: `pytest -v`
Expected: PASS em toda a suite (affiliate, fmt, scrape, history, select, render, discord, main).

- [ ] **Step 5: Execução ponta-a-ponta contra o site real (dry-run)**

```bash
python -m garciaig.main --dry-run
```
Expected: imprime semana, destaque, pré-venda, contagem por escalão (provavelmente `até 5 €` e `até 2 €` com avisos) e `Site em .../site/index.html`. Se falhar com `HTTP 403`, aplicar o fallback de User-Agent descrito na Task 2, Step 6.

---

### Task 8: Verificação visual, workflow e README

**Files:**
- Create: `.github/workflows/weekly.yml`, `README.md`

- [ ] **Step 1: Verificar o site no browser (desktop e telemóvel)**

```bash
python -m http.server 8765 --directory site
```
(em segundo plano). Abrir `http://localhost:8765/` no browser integrado; confirmar: 6 secções, capas a carregar, preços em formato `12,39 €`, botão "Ver na Instant Gaming" com o URL `…/?igr=garciap` (passar o rato ou ler o href), blocos vazios com a mensagem "Sem candidatos esta semana". Repetir com viewport 375×812. Se as capas não carregarem (hotlink bloqueado), substituir `<img>` por um fundo neutro e registar o problema no README. Parar o servidor no fim.

- [ ] **Step 2: Escrever o workflow**

`.github/workflows/weekly.yml`:
```yaml
name: Atualização semanal

on:
  schedule:
    - cron: "0 8 * * 1"   # segundas-feiras, 08:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: weekly
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .
      - run: python -m garciaig.main
        env:
          SITE_URL: ${{ vars.SITE_URL }}
      - name: Guardar histórico no repositório
        run: |
          git config user.name "garciaig-bot"
          git config user.email "garciaig-bot@users.noreply.github.com"
          git add data/history.json data/week.json
          git diff --cached --quiet || (git commit -m "chore: atualização semanal" && git push)
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - uses: actions/upload-artifact@v4
        with:
          name: discord-payload
          path: data/discord_payload.json

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4

  notify:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e .
      - uses: actions/download-artifact@v4
        with:
          name: discord-payload
          path: data
      - run: python -m garciaig.discord data/discord_payload.json
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
```

- [ ] **Step 3: Escrever o README**

`README.md`:
````markdown
# GarciaIG Deals (prova de conceito)

Site semanal com jogos da Instant Gaming (PT) em destaque, todos com `?igr=garciap`, mais um post automático no Discord.

## Usar localmente
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # testes
python -m garciaig.main --dry-run       # recolhe dados reais e gera site/index.html (sem gravar histórico)
python -m garciaig.main --offline tests/fixtures --today 2026-10-05 --dry-run   # com o snapshot guardado
python -m http.server 8765 --directory site
```

## Como funciona
1. `scrape`: lê `/tendencias/`, `/pre-reservas/` e `/proximos-lancamentos/` (JSON embebido nas páginas; 3 pedidos, 2,5 s de pausa).
2. `select`: escolhe destaque, pré-venda e 4 escalões de preço (20/10/5/2 €), com pausa de 4 semanas.
3. `render` + `discord`: geram `site/` e `data/discord_payload.json`. Todos os links passam por `affiliate.py`.
4. GitHub Actions (`weekly.yml`) corre à segunda-feira, publica no Pages e envia o Discord.

## Ativar na produção
- Repositório GitHub com Pages (Source: GitHub Actions).
- Variable `SITE_URL` (URL público) e Secret `DISCORD_WEBHOOK_URL`.

## Limitações conhecidas
- Os blocos "até 5 €" e "até 2 €" ficam incompletos: as páginas permitidas têm poucos jogos baratos. A solução é um feed oficial do programa de parceiros.
- Depende da estrutura atual das páginas; se mudar, o pipeline falha (não publica dados errados).
- Confirmar com a Instant Gaming que este uso é aceitável antes de produção.
````

- [ ] **Step 4: Checkpoint final**

Run: `pytest -v && python -m garciaig.main --offline tests/fixtures --today 2026-10-05 --dry-run`
Expected: todos os testes passam e o comando termina com código 0.

---

## Self-Review (feita)

- **Cobertura da spec:** fonte de dados (T2), semana ISO e 6 blocos (T4), escalões/pausa/dedup (T3, T4), links exatos (T1, T5, T6), site responsivo (T5, T8), Discord (T6), erros e `--dry-run`/`--offline` (T7), workflow com `build → deploy → notify` (T8), limitações documentadas (T8 README). Sem lacunas.
- **Placeholders:** nenhum; todo o código está escrito.
- **Consistência de tipos:** `Game`/`Week` definidos na T1 e usados com os mesmos campos; `history.recent_ids(hist, week_key)` chamado em T7 com `select.week_key(today)`; `render.TIER_TITLES` usado em T6; `scrape.load_offline` usado em T4 e T7.
