from blinkit_goatlife import extract_buy_price, has_sponsored_badge


def test_extract_buy_price_parses_range_as_midpoint():
    assert extract_buy_price("Buy Rs. 10,000 - Rs. 20,000") == 15000.0


def test_extract_buy_price_handles_na_variants():
    assert extract_buy_price("N/A") == 0
    assert extract_buy_price("nan") == 0
    assert extract_buy_price("") == 0
    assert extract_buy_price(float("nan")) == 0


def test_extract_buy_price_returns_zero_when_unparseable():
    assert extract_buy_price("no numbers here") == 0


def test_has_sponsored_badge_detects_the_ad_asset():
    srcs = [
        "https://cdn.grofers.com/.../da/cms-assets/cms/product/rc-upload-x.png",
        "https://cdn.grofers.com/.../assets/ui/ad_without_bg.png",
    ]
    assert has_sponsored_badge(srcs) is True


def test_has_sponsored_badge_false_for_organic_card():
    srcs = ["https://cdn.grofers.com/.../da/cms-assets/cms/product/rc-upload-x.png"]
    assert has_sponsored_badge(srcs) is False
