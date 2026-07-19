from completeness_gate import run_stats, baseline_from_stats, evaluate


def _row(city, locality, brand, product):
    return {"city_raw": city, "locality_raw": locality, "brand_searched": brand,
            "product_name": product}


def test_run_stats_counts_cities_localities_brands_and_real_rows():
    rows = [
        _row("Mumbai", "Bandra", "Pintola Oats", "Pintola 1kg"),
        _row("Mumbai", "Andheri", "Pintola Oats", "Pintola 500g"),
        _row("Delhi", "Saket", "Quaker Oats", "Quaker 1kg"),
        _row("Delhi", "Saket", "Quaker Oats", "Not Serviceable"),  # placeholder, not real
    ]
    assert run_stats(rows) == {"cities": 2, "localities": 3, "brands": 2, "real_rows": 3}


def test_run_stats_ignores_none_and_empty_brand():
    rows = [
        _row("Mumbai", "Bandra", None, "Some Rank Tracker Product"),
        _row("Mumbai", "Bandra", "", "Another Product"),
        _row("Mumbai", "Bandra", "Pintola Oats", "Pintola 1kg"),
    ]
    assert run_stats(rows)["brands"] == 1


def test_baseline_from_stats_takes_max_per_dimension():
    prior = [
        {"cities": 10, "localities": 498, "brands": 10, "real_rows": 55000},
        {"cities": 8, "localities": 400, "brands": 10, "real_rows": 10000},
    ]
    assert baseline_from_stats(prior) == {
        "cities": 10, "localities": 498, "brands": 10, "real_rows": 55000,
    }


def test_baseline_from_stats_empty_is_none():
    assert baseline_from_stats([]) is None


def test_evaluate_passes_when_no_baseline_exists():
    candidate = {"cities": 8, "localities": 100, "brands": 10, "real_rows": 5000}
    result = evaluate(candidate, None)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_evaluate_fails_when_real_rows_far_below_baseline():
    # This is the run 424 case: ~18% of the healthy row count.
    baseline = {"cities": 10, "localities": 498, "brands": 10, "real_rows": 55000}
    candidate = {"cities": 8, "localities": 395, "brands": 8, "real_rows": 10000}
    result = evaluate(candidate, baseline, min_ratio=0.7)
    assert result["ok"] is False
    assert any("real_rows" in r for r in result["reasons"])


def test_evaluate_passes_when_all_dimensions_within_ratio():
    baseline = {"cities": 10, "localities": 498, "brands": 10, "real_rows": 55000}
    candidate = {"cities": 10, "localities": 480, "brands": 10, "real_rows": 52000}
    result = evaluate(candidate, baseline, min_ratio=0.7)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_evaluate_flags_missing_brands_even_when_rows_ok():
    baseline = {"cities": 10, "localities": 498, "brands": 10, "real_rows": 55000}
    candidate = {"cities": 10, "localities": 498, "brands": 6, "real_rows": 50000}
    result = evaluate(candidate, baseline, min_ratio=0.7)
    assert result["ok"] is False
    assert any("brands" in r for r in result["reasons"])


def test_evaluate_skips_dimension_when_baseline_is_zero():
    # goatlife has brand_searched of essentially one term; a zero baseline
    # dimension must not divide-by-zero or spuriously fail.
    baseline = {"cities": 10, "localities": 498, "brands": 0, "real_rows": 7000}
    candidate = {"cities": 10, "localities": 498, "brands": 0, "real_rows": 7000}
    result = evaluate(candidate, baseline, min_ratio=0.7)
    assert result["ok"] is True
