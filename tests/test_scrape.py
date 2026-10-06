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
        '"price":"39.99","retail":"59.99","retail_currency":"EUR","discount":33,"avail_date":1791244800,"preorder":1,'
        '"is_dlc":0,"platforms":["1"],"updated_at":7,"type":" Steam "},'
        '{"prod_id":2,"name":"B","seo_name":"b","price":"5.00","retail":"5.00","retail_currency":"EUR","avail_date":null,'
        '"preorder":0,"is_dlc":1,"platforms":"1,2"}]};'
    )
    a, b = scrape.parse_search_results(html)
    assert (a.id, a.price, a.retail, a.discount, a.preorder, a.is_pc, a.rank) == (1, 39.99, 59.99, 33, True, True, 0)
    assert a.release_date.isoformat() == "2026-10-06"
    assert (a.store, b.store) == ("Steam", "")
    assert (b.is_dlc, b.is_pc, b.avail_date, b.discount, b.rank) == (True, True, None, 0, 1)
    unranked = scrape.parse_search_results(html, ranked=False)
    assert all(g.rank == 10_000 for g in unranked)


def test_platform_not_pc():
    html = 'window.searchResults = {"hits":[{"prod_id":3,"name":"C","seo_name":"c","price":"1","platforms":"5"}]};'
    assert scrape.parse_search_results(html)[0].is_pc is False


def test_parse_time_frames_flattens_groups():
    html = (
        'window.productsListedByTimeFrame = {"5":{"one_month_ago":{"10":{"prod_id":10,"name":"X",'
        '"seo_name":"x","price":"12.39","retail":"14.99","retail_currency":"EUR","avail_date":1788220800,"preorder":0,'
        '"is_dlc":0,"platforms":"1"}}},"7":{"next_month":{"11":{"prod_id":11,"name":"Y",'
        '"seo_name":"y","price":"9.99","retail":"9.99","retail_currency":"EUR","avail_date":1795000000,"preorder":1,'
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


# ---------- retail/desconto só em EUR (no runner dos EUA o retail vem em USD) ----------

import json  # noqa: E402


def one(**kw):
    item = {"prod_id": 1, "name": "G", "seo_name": "g", "price": "39.99", "avail_date": 1791244800, "preorder": 0,
            "is_dlc": 0, "platforms": ["1"]}
    item.update(kw)
    return scrape.parse_search_results("window.searchResults = " + json.dumps({"hits": [item]}) + ";")[0]


def test_pt_style_item_uses_eur_retail_and_computed_discount():
    g = one(retail="59.99", retail_currency="EUR", default_retail="59.99", default_retail_currency="EUR",
            retail_prices={"EUR": "59.99"}, discount=33)
    assert (g.price, g.retail, g.discount, g.retail_known) == (39.99, 59.99, 33, True)


def test_us_visitor_item_uses_default_retail_in_eur_not_usd_retail():
    g = one(retail="67.12", retail_currency="USD", discount=25, default_retail="59.99", default_retail_currency="EUR",
            retail_prices={"USD": "67.12"})
    assert (g.price, g.retail, g.discount, g.retail_known) == (39.99, 59.99, 33, True)


def test_us_visitor_item_without_any_eur_retail_is_unknown():
    g = one(retail="67.12", retail_currency="USD", discount=25, retail_prices={"USD": "67.12"})
    assert (g.price, g.retail, g.discount, g.retail_known) == (39.99, 39.99, 0, False)
    assert one(retail="59.99").retail_known is False  # sem moeda indicada: não confiar


def test_retail_prices_eur_wins_over_usd_retail_field():
    g = one(retail="67.12", retail_currency="USD", retail_prices={"EUR": "59.99", "USD": "67.12"})
    assert (g.retail, g.discount) == (59.99, 33)


def test_numeric_floats_and_currency_prices_eur():
    g = one(price=40.0, currency_prices={"EUR": 39.99, "USD": 44.7}, retail=59.99, retail_currency="EUR",
            retail_prices={"EUR": 59.99})
    assert (g.price, g.retail, g.discount) == (39.99, 59.99, 33)


@pytest.mark.parametrize("price,retail,expected", [(39.99, 59.99, 33), (38.49, 49.99, 23), (56.99, 69.99, 19), (11.09, 29.99, 63)])
def test_discount_is_computed_from_eur_numbers(price, retail, expected):
    g = one(price=str(price), retail=str(retail), retail_currency="EUR", discount=99, discounts={"EUR": 99})
    assert g.discount == expected


def test_retail_not_above_price_means_no_discount_and_free_games_are_not_flagged():
    g = one(price="10", retail="10", retail_currency="EUR")
    assert (g.discount, g.retail_known) == (0, True)
    free = one(price="0.00", retail=None)
    assert free.price == 0 and free.retail_known is True


def test_fixture_items_match_fresh_pt_values():
    h = scrape.load_offline(FIX)
    pool = {g.id: g for g in scrape.build_pool(h["trend"], h["pre"], h["upcoming"])}
    sw = pool[21378]
    assert (sw.price, sw.retail, sw.discount, sw.retail_known) == (39.99, 59.99, 33, True)
    assert sum(not g.retail_known for g in pool.values()) <= 10  # só itens que já não existem nas páginas frescas
