from blinkit_oats import extract_buy_price, get_brand_keyword


def test_extract_buy_price_parses_range_as_midpoint():
    assert extract_buy_price("Buy Rs. 10,000 - Rs. 20,000") == 15000.0


def test_extract_buy_price_handles_na():
    assert extract_buy_price("N/A") == 0


def test_get_brand_keyword_special_cases():
    assert get_brand_keyword("The Whole Truth Oats") == "whole truth"
    assert get_brand_keyword("Yoga Bar Oats") == "yoga"
    assert get_brand_keyword("True Elements Oats") == "true"


def test_get_brand_keyword_default_first_word():
    assert get_brand_keyword("Quaker Oats") == "quaker"
    assert get_brand_keyword("Saffola Oats") == "saffola"
