from health_report import assess_runs, has_degraded_valid_run


def _run(run_id, platform, status, cities, localities, brands, real_rows):
    return {"run_id": run_id, "platform": platform, "status": status,
            "stats": {"cities": cities, "localities": localities,
                      "brands": brands, "real_rows": real_rows}}


def test_assess_runs_flags_degraded_run_against_platform_baseline():
    runs = [
        _run(4, "blinkit", "valid", 10, 500, 10, 55000),
        _run(424, "blinkit", "valid", 8, 397, 10, 8700),
    ]
    assessed = {r["run_id"]: r for r in assess_runs(runs, min_ratio=0.7)}
    assert assessed[4]["ok"] is True
    assert assessed[424]["ok"] is False
    assert any("real_rows" in reason for reason in assessed[424]["reasons"])


def test_assess_runs_baseline_uses_only_valid_runs():
    # A quarantined giant run must not raise the bar for the valid ones.
    runs = [
        _run(1, "swiggy", "quarantined", 10, 500, 10, 999999),
        _run(2, "swiggy", "valid", 10, 500, 10, 50000),
        _run(3, "swiggy", "valid", 10, 500, 10, 48000),
    ]
    assessed = {r["run_id"]: r for r in assess_runs(runs, min_ratio=0.7)}
    assert assessed[2]["ok"] is True
    assert assessed[3]["ok"] is True


def test_has_degraded_valid_run_true_when_a_valid_run_is_below_bar():
    runs = [
        _run(4, "blinkit", "valid", 10, 500, 10, 55000),
        _run(424, "blinkit", "valid", 8, 397, 10, 8700),
    ]
    assert has_degraded_valid_run(assess_runs(runs)) is True


def test_has_degraded_valid_run_false_when_degraded_run_is_quarantined():
    runs = [
        _run(4, "blinkit", "valid", 10, 500, 10, 55000),
        _run(424, "blinkit", "quarantined", 8, 397, 10, 8700),
    ]
    assert has_degraded_valid_run(assess_runs(runs)) is False
