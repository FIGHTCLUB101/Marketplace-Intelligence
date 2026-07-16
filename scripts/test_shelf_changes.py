from shelf_changes import (
    build_shelf_snapshot,
    detect_changes,
    generate_narrative_summary,
    goat_gone_unique,
    normalize_product_identity,
    not_serviceable_localities,
)


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity_not_position():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {
        "rank": 1, "price": 119.0, "display_name": "GOAT Life Mocha Marvel",
    }


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


def test_goat_gone_unique_excludes_skus_already_in_goat_displaced():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                            "product": "GOAT Life Mocha Marvel", "is_goat": True}],
    }
    assert goat_gone_unique(changes) == []


def test_goat_gone_unique_includes_rank_5_plus_goat_sku_that_vanished():
    changes = {
        "goat_displaced": [],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 6,
                            "product": "GOAT Life Choco Hazelnut", "is_goat": True}],
    }
    result = goat_gone_unique(changes)
    assert len(result) == 1
    assert result[0]["product"] == "GOAT Life Choco Hazelnut"


def test_goat_gone_unique_does_not_exclude_same_named_sku_in_different_locality():
    # "GOAT Life X" displaced (rank 1-4) in Bandra AND separately vanished
    # (rank 5+) in Andheri, same week — two distinct real events, not a
    # duplicate. The Andheri one must NOT be excluded just because the same
    # product name appears in goat_displaced for a different locality.
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life X", "now": "MISSING"}],
        "gone_products": [{"city": "Mumbai", "locality": "Andheri", "rank": 6,
                            "product": "GOAT Life X", "is_goat": True}],
    }
    result = goat_gone_unique(changes)
    assert len(result) == 1
    assert result[0]["locality"] == "Andheri"


def test_narrative_does_not_double_count_rank_1_4_goat_sku_that_vanished():
    # A GOAT SKU displaced from rank 1-4 AND gone is ONE event, not two.
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "rank_intrusions": [],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                            "product": "GOAT Life Mocha Marvel", "is_goat": True}],
    }
    result = generate_narrative_summary(changes)
    assert len(result) == 1  # lead sentence only, no "N other changes"
    assert "Mocha Marvel" in result[0]


def test_narrative_gives_lead_sentence_to_rank_5_plus_goat_sku_that_vanished():
    changes = {
        "goat_displaced": [],
        "rank_intrusions": [],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 6,
                            "product": "GOAT Life Choco Hazelnut", "is_goat": True}],
    }
    result = generate_narrative_summary(changes)
    assert "Choco Hazelnut" in result[0]
    assert "disappeared" in result[0]


def test_normalize_product_identity_strips_pack_of_suffix():
    # Confirmed real-world case (2026-07-13 production data): Blinkit's own
    # listing for the exact same physical SKU sometimes carries a
    # "- Pack of N" suffix and sometimes doesn't, between scrapes.
    assert normalize_product_identity(
        "GOAT Life High Protein Overnight Instant Oats Choco-Nut Crunch - Pack of 2"
    ) == "GOAT Life High Protein Overnight Instant Oats Choco-Nut Crunch"


def test_normalize_product_identity_strips_combo_suffix():
    assert normalize_product_identity("Prustlr Discovery Protein Oats - Combo") == "Prustlr Discovery Protein Oats"
    assert normalize_product_identity("Prustlr Discovery Protein Oats - Combo of 3") == "Prustlr Discovery Protein Oats"


def test_normalize_product_identity_is_a_no_op_for_plain_names():
    assert normalize_product_identity("GOAT Life Mocha Marvel") == "GOAT Life Mocha Marvel"
    assert normalize_product_identity("Not Serviceable") == "Not Serviceable"


def test_build_shelf_snapshot_keys_by_normalized_identity_and_keeps_display_name():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch - Pack of 2", 2, 199.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch")] == {
        "rank": 2, "price": 199.0, "display_name": "GOAT Life Choco-Nut Crunch - Pack of 2",
    }


def test_detect_changes_treats_pack_size_suffix_as_same_product_not_gone_and_new():
    # This is the exact false-positive pattern found in real 2026-07-13
    # production data: the SAME product gets a "- Pack of 2" suffix added
    # between scrapes. Must be recognized as one product whose rank/price
    # may have changed, not a "gone" + "new" pair.
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch", 2, 199.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch - Pack of 2", 2, 199.0, is_goat=True)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["new_products"] == []
    assert changes["gone_products"] == []
    assert changes["goat_displaced"] == []


def test_price_change_does_not_fire_when_pack_size_suffix_changed():
    # Confirmed real 2026-07-13 production artifact: comparing a single-pack
    # listing's price to the same product's "- Pack of 2" listing price
    # produced a spurious ~496-locality "price change" spike -- a pack-of-2
    # naturally costs more than one pack, so that's not a real per-unit
    # price movement. Only compare prices when the raw listing name (pack
    # size included) is actually unchanged between weeks.
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch", 2, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "GOAT Life Choco-Nut Crunch - Pack of 2", 2, 189.0, is_goat=True)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_detect_changes_displays_the_new_raw_name_when_rank_actually_changes():
    # Same product-identity-despite-suffix-change case, but this time the
    # rank also genuinely moved -- the display name shown to a human should
    # be the current (new) raw scraped name, not the normalized identity.
    rows_old = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 449.0)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats - Pack of 2", 3, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["rank_moved"]) == 1
    assert changes["rank_moved"][0]["product"] == "Prustlr Discovery Protein Oats - Pack of 2"
    assert changes["rank_moved"][0]["old_rank"] == 5
    assert changes["rank_moved"][0]["new_rank"] == 3
