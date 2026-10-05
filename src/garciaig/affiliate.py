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
