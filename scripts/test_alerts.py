from alerts import build_combined_email_html, build_email_html, build_oats_section_html


def test_build_email_html_includes_narrative_and_severity():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "1 CHANGES DETECTED" in html
    assert "GOAT Life Mocha Marvel" in html
    assert "Bandra" in html


def test_build_email_html_all_clear():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [],
        "gone_products": [], "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "ALL CLEAR" in html


def test_build_email_html_includes_price_changes_table():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [],
        "price_changes": [{"city": "Mumbai", "locality": "Bandra", "product": "Prustlr Discovery Protein Oats",
                            "old_price": 449.0, "new_price": 469.0, "change": 20.0}],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "Prustlr Discovery Protein Oats" in html
    assert "469" in html


def test_build_email_html_renders_detail_section_for_rank_5_plus_goat_gone():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 6,
                            "product": "GOAT Life Choco Hazelnut", "is_goat": True}],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "1 CHANGES DETECTED" in html
    assert "GOAT Life Choco Hazelnut" in html
    assert "No Longer Listed" in html


def test_build_oats_section_html_renders_only_nonempty_tables():
    changes = {
        "new_products": [{"city": "Bangalore", "locality": "Indiranagar", "brand_searched": "Pintola Oats",
                           "product": "Pintola Oats 500g", "is_goat": False}],
        "gone_products": [], "price_changes": [], "stock_changes": [],
    }
    html = build_oats_section_html(changes, "Blinkit Oats — Competitor Pricing")
    assert "Pintola Oats 500g" in html
    assert "New Products" in html
    assert "Delisted Products" not in html
    assert "Stock Changes" not in html


def test_build_oats_section_html_all_clear_message_when_nothing_changed():
    changes = {"new_products": [], "gone_products": [], "price_changes": [], "stock_changes": []}
    html = build_oats_section_html(changes, "Zepto Oats — Competitor Pricing")
    assert "No changes detected" in html


def test_build_combined_email_html_sums_totals_across_platforms():
    rank_changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    oats_changes = {
        "new_products": [{"city": "Bangalore", "locality": "Indiranagar", "brand_searched": "Pintola Oats",
                           "product": "Pintola Oats 500g", "is_goat": False}],
        "gone_products": [], "price_changes": [], "stock_changes": [],
    }
    html = build_combined_email_html(
        [
            {"label": "GOAT Life Shelf Monitor (Blinkit)", "mode": "rank", "changes": rank_changes},
            {"label": "Blinkit Oats — Competitor Pricing", "mode": "oats", "changes": oats_changes},
        ],
        "2026-07-18", "previous run",
    )
    assert "2 CHANGES DETECTED" in html
    assert "GOAT Life Shelf Monitor (Blinkit)" in html
    assert "Blinkit Oats — Competitor Pricing" in html
    assert "Pintola Oats 500g" in html


def test_build_combined_email_html_all_clear_across_all_platforms():
    empty_rank = {"goat_displaced": [], "goat_recovered": [], "new_products": [], "gone_products": [],
                  "rank_intrusions": [], "rank_moved": [], "price_changes": []}
    empty_oats = {"new_products": [], "gone_products": [], "price_changes": [], "stock_changes": []}
    html = build_combined_email_html(
        [{"label": "A", "mode": "rank", "changes": empty_rank},
         {"label": "B", "mode": "oats", "changes": empty_oats}],
        "2026-07-18", "previous run",
    )
    assert "ALL CLEAR" in html
