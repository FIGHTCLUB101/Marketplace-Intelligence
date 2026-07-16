from blinkit_oats import (
    extract_buy_price, get_brand_keyword, has_sponsored_badge, is_goat_product, is_oats_product,
)


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


def test_is_goat_product_matches_case_insensitively():
    assert is_goat_product("GOAT Life High Protein Overnight Instant Oats") is True
    assert is_goat_product("goat life choco-nut crunch") is True


def test_is_goat_product_false_for_competitor_names():
    assert is_goat_product("Pintola High Protein Oats") is False
    assert is_goat_product("Yoga Bar Protein Oats") is False


def test_has_sponsored_badge_detects_the_ad_asset():
    # Verified against a live blinkit.com search results page (2026-07-16):
    # the sponsored "Ad" badge is an image overlay at this asset path, not text.
    srcs = [
        "https://cdn.grofers.com/.../da/cms-assets/cms/product/rc-upload-x.png",
        "https://cdn.grofers.com/.../assets/ui/ad_without_bg.png",
    ]
    assert has_sponsored_badge(srcs) is True


def test_has_sponsored_badge_false_for_organic_card():
    srcs = [
        "https://cdn.grofers.com/.../da/cms-assets/cms/product/rc-upload-x.png",
        "https://cdn.grofers.com/.../assets/eta-icons/15-mins.png",
    ]
    assert has_sponsored_badge(srcs) is False


def test_has_sponsored_badge_handles_missing_src():
    assert has_sponsored_badge([None, ""]) is False


def test_is_oats_product_true_for_oats_names():
    assert is_oats_product("Pintola High Protein Oats (Chocolate)") is True
    assert is_oats_product("QUAKER ROLLED OATS") is True


def test_is_oats_product_false_for_non_oats_names():
    # Confirmed real case: a "Pintola oats" search on Blinkit still surfaced
    # this non-oats product from the same brand.
    assert is_oats_product("Pintola All Natural Crunchy Peanut Butter") is False
