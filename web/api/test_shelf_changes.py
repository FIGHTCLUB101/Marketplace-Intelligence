from shelf_changes import (
    build_shelf_snapshot, conquest_breadth, detect_changes, generate_narrative_summary, goat_gone_unique,
    normalize_product_identity,
)


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {
        "rank": 1, "price": 119.0, "display_name": "GOAT Life Mocha Marvel",
    }


def test_normalize_product_identity_strips_pack_of_suffix():
    # Confirmed real-world case (2026-07-13 production data): Blinkit's own
    # listing for the exact same physical SKU sometimes carries a
    # "- Pack of N" suffix and sometimes doesn't, between scrapes.
    assert normalize_product_identity(
        "GOAT Life High Protein Overnight Instant Oats Choco-Nut Crunch - Pack of 2"
    ) == "GOAT Life High Protein Overnight Instant Oats Choco-Nut Crunch"


def test_normalize_product_identity_is_a_no_op_for_plain_names():
    assert normalize_product_identity("GOAT Life Mocha Marvel") == "GOAT Life Mocha Marvel"


def test_detect_changes_treats_pack_size_suffix_as_same_product_not_gone_and_new():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch", 2, 199.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch - Pack of 2", 2, 199.0, is_goat=True)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["new_products"] == []
    assert changes["gone_products"] == []
    assert changes["goat_displaced"] == []


def test_price_change_does_not_fire_when_pack_size_suffix_changed():
    # Confirmed real 2026-07-13 production artifact: comparing a single-pack
    # price to the same product's "- Pack of 2" price produced a spurious
    # ~496-locality "price change" spike -- not a real per-unit price move.
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch", 2, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch - Pack of 2", 2, 189.0, is_goat=True)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_detect_changes_goat_displaced():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["goat_displaced"]) == 1
    assert changes["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"


def test_goat_gone_unique_excludes_already_displaced():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life X", "now": "MISSING"}],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                            "product": "GOAT Life X", "is_goat": True}],
    }
    assert goat_gone_unique(changes) == []


def test_generate_narrative_summary_all_clear():
    changes = {"goat_displaced": [], "rank_intrusions": [], "gone_products": []}
    result = generate_narrative_summary(changes)
    assert "holds ranks 1-4" in result[0]


def test_conquest_breadth_groups_by_competitor_sorted_desc():
    changes = {"rank_intrusions": [
        {"city": "Chennai", "locality": "Adyar", "rank": 3, "intruder": "The Whole Truth"},
        {"city": "Mumbai", "locality": "Andheri", "rank": 2, "intruder": "The Whole Truth"},
        {"city": "Bangalore", "locality": "BTM Layout", "rank": 4, "intruder": "Yoga Bar"},
    ]}
    result = conquest_breadth(changes)
    assert result[0] == {"competitor": "The Whole Truth", "locality_count": 2}
    assert result[1] == {"competitor": "Yoga Bar", "locality_count": 1}


def test_conquest_breadth_empty_when_no_intrusions():
    assert conquest_breadth({"rank_intrusions": []}) == []
