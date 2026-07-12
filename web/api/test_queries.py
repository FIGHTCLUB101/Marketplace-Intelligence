from queries import compute_belts


def test_compute_belts_groups_by_belt_and_filters_small_belts():
    rows = [
        {"belt_id": "B1", "city": "Bangalore", "area": "A1", "belt_size": 4,
         "icp_score": 80.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
        {"belt_id": "B1", "city": "Bangalore", "area": "A2", "belt_size": 4,
         "icp_score": 60.0, "icp_verdict": "HOLD", "serviceability_state": "Unknown"},
        {"belt_id": "B2", "city": "Delhi", "area": "A3", "belt_size": 2,
         "icp_score": 90.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
    ]
    belts = compute_belts(rows)
    assert len(belts) == 1
    assert belts[0]["belt_id"] == "B1"
    assert belts[0]["size"] == 4
    assert belts[0]["avg_icp"] == 70.0
    assert belts[0]["go_count"] == 1
    assert belts[0]["confirmed_count"] == 1
    assert belts[0]["members"] == ["A1", "A2"]


def test_compute_belts_truncates_members_to_twelve():
    rows = [
        {"belt_id": "B1", "city": "Bangalore", "area": f"A{i}", "belt_size": 15,
         "icp_score": 50.0, "icp_verdict": "HOLD", "serviceability_state": "Unknown"}
        for i in range(15)
    ]
    belts = compute_belts(rows)
    assert len(belts[0]["members"]) == 12


def test_compute_belts_ignores_rows_without_a_belt():
    rows = [
        {"belt_id": None, "city": "Bangalore", "area": "A1", "belt_size": None,
         "icp_score": 80.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
    ]
    assert compute_belts(rows) == []
