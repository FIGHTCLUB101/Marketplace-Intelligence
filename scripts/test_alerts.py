from alerts import build_email_html


def test_build_email_html_includes_narrative_and_severity():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "GOAT LIFE SHELF DISRUPTED" in html
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
