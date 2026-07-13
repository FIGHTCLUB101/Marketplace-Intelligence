from shelf_changes import (
    build_shelf_snapshot,
    detect_changes,
    generate_narrative_summary,
    not_serviceable_localities,
)


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity_not_position():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {"rank": 1, "price": 119.0}


def test_build_shelf_snapshot_skips_null_rank_rows():
    rows = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    assert build_shelf_snapshot(rows) == {}


def test_insertion_does_not_cascade_false_positives():
    # A new product inserted at rank 5 pushes 3 pre-existing products down a
    # slot each. None of them should be reported as new/gone — only the
    # genuinely new one. This is the exact bug class the antigravity repo's
    # original position-keyed comparison had before it was fixed.
    rows_old = [
        _row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 449.0),
        _row("Mumbai", "Bandra", "Quaker Rolled Oats", 6, 86.0),
        _row("Mumbai", "Bandra", "Saffola Masala Oats", 7, 199.0),
    ]
    rows_new = [
        _row("Mumbai", "Bandra", "ProOats High Protein", 5, 89.0),
        _row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 449.0),
        _row("Mumbai", "Bandra", "Quaker Rolled Oats", 7, 86.0),
        _row("Mumbai", "Bandra", "Saffola Masala Oats", 8, 199.0),
    ]
    changes = detect_changes(rows_new, rows_old)
    assert {p["product"] for p in changes["new_products"]} == {"ProOats High Protein"}
    assert changes["gone_products"] == []


def test_goat_displaced_from_ranks_1_to_4():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["goat_displaced"]) == 1
    assert changes["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"


def test_rank_intrusion_into_goat_zone():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Almond Kulfi", 4, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 4, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["rank_intrusions"]) == 1
    assert changes["rank_intrusions"][0]["intruder"] == "Prustlr Discovery Protein Oats"


def test_not_serviceable_locality_excluded_from_comparison():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["goat_displaced"] == []
    assert changes["gone_products"] == []


def test_price_change_fires_on_rupee_or_percent_threshold():
    rows_old = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 599.0)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 574.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["price_changes"]) == 1
    assert changes["price_changes"][0]["change"] == -25.0


def test_price_change_does_not_fire_below_both_thresholds():
    rows_old = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 599.0)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 590.0)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_drop_calendar_suppresses_goat_displaced():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old, drop_calendar={"GOAT Life Mocha Marvel"})
    assert changes["goat_displaced"] == []


def test_not_serviceable_localities_finds_marked_rows():
    rows = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    assert not_serviceable_localities(rows) == {("Mumbai", "Bandra")}


def test_generate_narrative_summary_all_clear():
    changes = {"goat_displaced": [], "rank_intrusions": [], "gone_products": []}
    result = generate_narrative_summary(changes)
    assert len(result) == 1
    assert "holds ranks 1" in result[0]


def test_generate_narrative_summary_leads_with_most_frequent_threat():
    changes = {
        "goat_displaced": [],
        "rank_intrusions": [
            {"city": "Chennai", "locality": "Adyar", "intruder": "Yoga Bar Golden Oats"},
            {"city": "Bangalore", "locality": "BTM Layout", "intruder": "Prustlr Discovery Protein Oats"},
            {"city": "Mumbai", "locality": "Andheri", "intruder": "Prustlr Discovery Protein Oats"},
        ],
        "gone_products": [],
    }
    result = generate_narrative_summary(changes)
    assert "Prustlr" in result[0]
    assert "1 other change" in result[1]
