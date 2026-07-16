import pandas as pd
import pytest

from pack_pricing import goat_price_per_100g, parse_pack_size_grams, price_per_100g


def test_parse_pack_size_grams_plain_grams():
    assert parse_pack_size_grams("400 g") == 400
    assert parse_pack_size_grams("225g") == 225
    assert parse_pack_size_grams("75 g") == 75


def test_parse_pack_size_grams_plain_kilograms():
    assert parse_pack_size_grams("1 kg") == 1000
    assert parse_pack_size_grams("2.5 kg") == 2500
    assert parse_pack_size_grams("1.2kg") == 1200


def test_parse_pack_size_grams_parenthesized_wrapper():
    assert parse_pack_size_grams("1 pack (400 g)") == 400
    assert parse_pack_size_grams("1 pc (1 kg)") == 1000


def test_parse_pack_size_grams_multiplication_count_times_weight():
    # "2 x 35 g" — two units of 35g each
    assert parse_pack_size_grams("1 pack (2 x 35 g)") == 70
    assert parse_pack_size_grams("38 g X 4") == 152


def test_parse_pack_size_grams_multiplication_weight_times_count():
    assert parse_pack_size_grams("500 g X 3") == 1500
    assert parse_pack_size_grams("1 kg X 2") == 2000


def test_parse_pack_size_grams_combo_addition():
    assert parse_pack_size_grams("1 kg + 300 g") == 1300
    # trailing number shares the unit from the following term
    assert parse_pack_size_grams("1 pack (400+60 g)") == 460


def test_parse_pack_size_grams_returns_none_for_unparseable():
    assert parse_pack_size_grams(None) is None
    assert parse_pack_size_grams(float("nan")) is None
    assert parse_pack_size_grams("Not Available") is None
    assert parse_pack_size_grams("") is None


def test_price_per_100g_computes_rate():
    assert price_per_100g(550, 1000) == pytest.approx(55.0, abs=0.01)
    assert price_per_100g(99, 75) == pytest.approx(132.0, abs=0.01)
    assert price_per_100g(288, 25) == pytest.approx(1152.0, abs=0.01)


def test_price_per_100g_returns_none_for_missing_or_zero_weight():
    assert price_per_100g(99, None) is None
    assert price_per_100g(None, 75) is None
    assert price_per_100g(99, 0) is None


def test_goat_price_per_100g_averages_only_goat_rows_own_pack_sizes():
    df = pd.DataFrame([
        {"is_goat": True, "price_per_100g": 132.0},
        {"is_goat": True, "price_per_100g": 115.0},
        {"is_goat": False, "price_per_100g": 55.0},
    ])
    assert goat_price_per_100g(df) == pytest.approx(123.5, abs=0.01)


def test_goat_price_per_100g_returns_none_when_no_goat_rows():
    df = pd.DataFrame([{"is_goat": False, "price_per_100g": 55.0}])
    assert goat_price_per_100g(df) is None
