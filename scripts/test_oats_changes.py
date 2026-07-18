from oats_changes import build_oats_snapshot, detect_price_availability_changes


def _row(city, locality, brand, name, price, stock_left=None, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "brand_searched": brand,
            "product_name": name, "selling_price": price, "stock_left": stock_left,
            "is_goat": is_goat}


def test_build_oats_snapshot_keys_by_locality_brand_and_identity():
    rows = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg", 249.0)]
    snap = build_oats_snapshot(rows)
    assert snap[("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg")] == {
        "price": 249.0, "stock_left": None, "display_name": "Pintola Oats 1kg", "is_goat": False,
    }


def test_new_and_gone_products_detected():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 500g", 149.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert {p["product"] for p in changes["new_products"]} == {"Pintola Oats 500g"}
    assert {p["product"] for p in changes["gone_products"]} == {"Pintola Oats 1kg"}


def test_pack_size_suffix_treated_as_same_product_not_gone_and_new():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats - Pack of 2", 249.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["new_products"] == []
    assert changes["gone_products"] == []


def test_same_product_name_under_different_brand_searched_kept_distinct():
    # GOAT Life's own product can legitimately appear inside more than one
    # competitor's brand search in the same locality -- these are two real,
    # independent observations, not one product that "moved".
    rows_old = [
        _row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
    ]
    rows_new = [
        _row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
        _row("Bangalore", "Indiranagar", "Yoga Bar Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
    ]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert {p["brand_searched"] for p in changes["new_products"]} == {"Yoga Bar Oats"}


def test_is_goat_propagates_through_new_and_gone():
    rows_old = []
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["new_products"][0]["is_goat"] is True


def test_price_change_fires_on_rupee_or_percent_threshold():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 224.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert len(changes["price_changes"]) == 1
    assert changes["price_changes"][0]["change"] == -25.0


def test_price_change_does_not_fire_below_both_thresholds():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 245.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_price_change_does_not_fire_when_pack_size_suffix_changed():
    # Same guard as shelf_changes.py: a pack-of-2 naturally costs more than
    # a single pack, so that's not a real per-unit price movement. Only
    # compare prices when the raw listing name is actually unchanged.
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 119.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats - Pack of 2", 189.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_price_change_skips_none_or_nonpositive_price():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", None)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_stock_flip_in_stock_to_sold_out_detected():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="SOLD OUT")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert len(changes["stock_changes"]) == 1
    assert changes["stock_changes"][0]["new_stock"] == "SOLD OUT"


def test_stock_change_skipped_when_either_side_blank():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left=None)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="SOLD OUT")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["stock_changes"] == []


def test_stock_change_not_flagged_when_state_unchanged():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["stock_changes"] == []
