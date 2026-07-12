from blinkit_goatlife import extract_buy_price


def test_extract_buy_price_parses_range_as_midpoint():
    assert extract_buy_price("Buy Rs. 10,000 - Rs. 20,000") == 15000.0


def test_extract_buy_price_handles_na_variants():
    assert extract_buy_price("N/A") == 0
    assert extract_buy_price("nan") == 0
    assert extract_buy_price("") == 0
    assert extract_buy_price(float("nan")) == 0


def test_extract_buy_price_returns_zero_when_unparseable():
    assert extract_buy_price("no numbers here") == 0
