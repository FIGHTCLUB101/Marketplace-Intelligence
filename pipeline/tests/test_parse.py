from pipeline.parse import parse_price_to_midpoint


def test_residential_buy_midpoint():
    s = "Residential: Buy Rs. 8,700- Rs. 15,200 / sqft | Rent Rs. 21- Rs. 34 / sqft || Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft"
    assert parse_price_to_midpoint(s) == 11950.0


def test_missing_residential_returns_none():
    assert parse_price_to_midpoint("Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft") is None


def test_blank_returns_none():
    assert parse_price_to_midpoint("") is None
    assert parse_price_to_midpoint(None) is None
