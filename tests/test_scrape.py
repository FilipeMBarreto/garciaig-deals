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
