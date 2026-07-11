import math

from shelf_common import compute_loc_key, is_goat_brand, to_bool, to_float, to_int


def test_compute_loc_key_lowercases_and_strips():
    assert compute_loc_key("Bangalore", "Indiranagar") == "bangalore|indiranagar"
    assert compute_loc_key(" Delhi ", " Connaught Place ") == "delhi|connaught place"


def test_is_goat_brand_matches_case_insensitively():
    assert is_goat_brand("GOAT Life Mocha Marvel 400g") is True
    assert is_goat_brand("goat life choco-nut crunch") is True
    assert is_goat_brand("Yoga Bar Oats") is False


def test_to_float_parses_currency_strings():
    assert to_float("Rs.399") == 399.0
    assert to_float("₹1,299") == 1299.0
    assert to_float("23%") == 23.0


def test_to_float_returns_none_for_unparseable():
    assert to_float("N/A") is None
    assert to_float(None) is None
    assert math.isnan(float("nan")) or to_float(float("nan")) is None


def test_to_int_parses_and_handles_na():
    assert to_int("3") == 3
    assert to_int(5) == 5
    assert to_int("N/A") is None
    assert to_int(None) is None


def test_to_bool_parses_true_false_strings():
    assert to_bool("True") is True
    assert to_bool("False") is False
    assert to_bool(True) is True
    assert to_bool("N/A") is None
    assert to_bool(None) is None
