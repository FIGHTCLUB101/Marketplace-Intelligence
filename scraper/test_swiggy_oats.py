from swiggy_oats import get_brand_keyword, is_goat_product, is_oats_product, parse_card_block


def test_parse_card_block_extracts_name_price_and_pack_size():
    card_text = "Yoga Bar 26% High Protein Oats\n400 g\n₹399\n₹499\n4.2"
    products = parse_card_block(card_text)
    assert len(products) == 1
    p = products[0]
    assert p["name"] == "Yoga Bar 26% High Protein Oats"
    assert p["pack_size"] == "400 g"
    assert p["sp"] == "₹399"
    assert p["mrp"] == "₹499"
    assert p["rating"] == "4.2"


def test_parse_card_block_detects_sponsored():
    card_text = "SPONSORED\nQuaker Oats\n₹199"
    products = parse_card_block(card_text)
    assert products[0]["sponsored"] == "True"


def test_parse_card_block_filters_noise_lines():
    card_text = "ADD\nCUSTOMISABLE\n15 MINS\nSaffola Oats\n₹149"
    products = parse_card_block(card_text)
    assert len(products) == 1
    assert products[0]["name"] == "Saffola Oats"


def test_parse_card_block_returns_empty_for_no_product_lines():
    assert parse_card_block("15 MINS\nADD") == []


def test_is_oats_product_true_for_oats_names():
    assert is_oats_product("Pintola High Protein Oats (Chocolate)") is True
    assert is_oats_product("QUAKER ROLLED OATS") is True


def test_is_oats_product_false_for_non_oats_names():
    assert is_oats_product("Pintola All Natural Crunchy Peanut Butter") is False


def test_get_brand_keyword_special_cases():
    assert get_brand_keyword("The Whole Truth Oats") == "whole truth"
    assert get_brand_keyword("Yoga Bar Oats") == "yoga"
    assert get_brand_keyword("True Elements Oats") == "true"


def test_get_brand_keyword_default_first_word():
    assert get_brand_keyword("Quaker Oats") == "quaker"
    assert get_brand_keyword("Saffola Oats") == "saffola"


def test_is_goat_product_matches_case_insensitively():
    assert is_goat_product("GOAT Life High Protein Overnight Instant Oats") is True
    assert is_goat_product("goat life choco-nut crunch") is True


def test_is_goat_product_false_for_competitor_names():
    assert is_goat_product("Pintola High Protein Oats") is False
    assert is_goat_product("Yoga Bar Protein Oats") is False
