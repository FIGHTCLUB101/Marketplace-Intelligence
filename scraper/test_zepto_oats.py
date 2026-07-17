from zepto_oats import (
    BRANDS, get_brand_keyword, has_sponsored_badge, is_goat_product, is_oats_product,
    make_sort_key_fn, parse_zepto_card,
)


def test_parse_zepto_card_extracts_name_price_pack_rating():
    card_text = "Yoga Bar Oats|₹399|₹499|400g|4.2|(120)"
    result = parse_zepto_card(card_text)
    assert result["sp"] == "Rs.399"
    assert result["mrp"] == "Rs.499"
    assert result["pack_size"] == "400g"
    assert result["rating"] == "4.2"
    assert result["reviews"] == "(120)"


def test_parse_zepto_card_detects_sponsored():
    card_text = "Ad|Quaker Oats|₹199"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "True"


def test_parse_zepto_card_not_sponsored_by_default():
    card_text = "Saffola Oats|₹149"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "False"


def test_parse_zepto_card_handles_missing_fields():
    result = parse_zepto_card("Some Product Name")
    assert result["sp"] == "N/A"
    assert result["mrp"] == "N/A"
    assert result["pack_size"] == "N/A"


def test_has_sponsored_badge_detects_the_ad_asset():
    # Verified against a live zepto.com search results page (2026-07-16):
    # the sponsored badge is an image whose filename ends in "_Ad.png",
    # never visible as text in the card's innerText.
    srcs = [
        "https://cdn.zeptonow.com/production/.../product_variant/x.jpg",
        "https://cdn.zeptonow.com/production/.../inventory/product/y-P3_-_Ad.png",
    ]
    assert has_sponsored_badge(srcs) is True


def test_has_sponsored_badge_false_for_organic_card():
    srcs = ["https://cdn.zeptonow.com/production/.../product_variant/x.jpg"]
    assert has_sponsored_badge(srcs) is False


def test_has_sponsored_badge_handles_missing_src():
    assert has_sponsored_badge([None, ""]) is False


def test_is_oats_product_true_for_oats_names():
    assert is_oats_product("Pintola High Protein Oats (Chocolate)") is True
    assert is_oats_product("QUAKER ROLLED OATS") is True


def test_is_oats_product_false_for_non_oats_names():
    assert is_oats_product("Pintola All Natural Crunchy Peanut Butter") is False


def test_get_brand_keyword_special_cases():
    # zepto's BRANDS entries have no " Oats" suffix, unlike blinkit/swiggy --
    # confirms the shared special-case substrings still match either way.
    assert get_brand_keyword("The Whole Truth") == "whole truth"
    assert get_brand_keyword("Yoga Bar") == "yoga"
    assert get_brand_keyword("True Elements") == "true"


def test_get_brand_keyword_default_first_word():
    assert get_brand_keyword("Quaker") == "quaker"
    assert get_brand_keyword("Saffola") == "saffola"


def test_is_goat_product_matches_case_insensitively():
    assert is_goat_product("GOAT Life High Protein Overnight Instant Oats") is True
    assert is_goat_product("goat life choco-nut crunch") is True


def test_is_goat_product_false_for_competitor_names():
    assert is_goat_product("Pintola High Protein Oats") is False
    assert is_goat_product("Yoga Bar Protein Oats") is False


def test_make_sort_key_fn_orders_by_locality_rank_then_brand_rank():
    localities = [
        {"loc_str": "Indiranagar, Bangalore", "price": 26750, "price_str": "Rs.26,750/sqft"},
        {"loc_str": "Koramangala, Bangalore", "price": 21450, "price_str": "Rs.21,450/sqft"},
    ]
    sort_key = make_sort_key_fn(localities)

    rows = [
        {"Locality": "Koramangala, Bangalore", "Brand Searched": BRANDS[0]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[1]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]},
    ]
    ordered = sorted(rows, key=sort_key)

    assert ordered == [
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[1]},
        {"Locality": "Koramangala, Bangalore", "Brand Searched": BRANDS[0]},
    ]


def test_make_sort_key_fn_puts_unknown_rows_last():
    localities = [{"loc_str": "Indiranagar, Bangalore", "price": 26750, "price_str": "Rs.26,750/sqft"}]
    sort_key = make_sort_key_fn(localities)
    known = {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]}
    unknown = {"Locality": "Saket, Delhi", "Brand Searched": "Nonexistent Brand"}
    assert sort_key(known) < sort_key(unknown)
