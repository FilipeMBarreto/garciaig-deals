from datetime import date
from garciaig.fmt import fmt_price, fmt_date


def test_fmt_price_pt():
    assert fmt_price(12.39) == "12,39 €"
    assert fmt_price(2) == "2,00 €"


def test_fmt_date_pt():
    assert fmt_date(date(2026, 10, 6)) == "6 de outubro"
    assert fmt_date(date(2026, 3, 1)) == "1 de março"
