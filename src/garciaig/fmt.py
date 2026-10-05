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
