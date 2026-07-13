from shelf_changes import (
    build_shelf_snapshot, conquest_breadth, detect_changes, generate_narrative_summary, goat_gone_unique,
)


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {"rank": 1, "price": 119.0}


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
