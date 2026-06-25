import os

from pipeline.parse import (
    parse_price_to_midpoint,
    count_named_entities,
    load_localities,
    load_gyms,
    load_stores,
)

ROOT = r"C:\Users\singh\Desktop\GOATLife"


def test_residential_buy_midpoint():
    s = "Residential: Buy Rs. 8,700- Rs. 15,200 / sqft | Rent Rs. 21- Rs. 34 / sqft || Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft"
    assert parse_price_to_midpoint(s) == 11950.0


def test_missing_residential_returns_none():
    assert parse_price_to_midpoint("Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft") is None


def test_blank_returns_none():
    assert parse_price_to_midpoint("") is None
    assert parse_price_to_midpoint(None) is None


def test_count_named_entities():
    assert count_named_entities("G D Goenka University, Ryan International, KIIT school") == 3
    assert count_named_entities("N/A") == 0
    assert count_named_entities("") == 0
    assert count_named_entities(None) == 0


def test_load_localities_shape():
    rows = load_localities(os.path.join(ROOT, "magicbricks_localities.xlsx"))
    assert len(rows) == 600
    r = rows[0]
    assert set(["area", "city", "pincode", "price_mid", "employment_count", "education_count"]).issubset(r)
    assert r["city"] == "Gurugram"
    # full-column capture (scope addendum)
    for k in ["physical_infra", "intro", "social_infra", "transport", "shopping", "hospital", "nearby", "tourist", "url"]:
        assert k in r


def test_load_gyms_and_stores():
    gyms = load_gyms(os.path.join(ROOT, "justdial_gyms_manual.xlsx"))
    stores = load_stores(os.path.join(ROOT, "reliance_smart_bazaar_stores.xlsx"))
    assert len(gyms) == 1537
    assert len(stores) == 137
    assert "addr" in gyms[0] and "pincode" in stores[0]
