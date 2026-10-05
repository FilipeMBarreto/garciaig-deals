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
