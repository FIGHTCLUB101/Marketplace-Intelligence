import os

import pytest

from db import get_connection
from queries import (
    compute_belts, fetch_brand_defence_rate, fetch_drop_calendar, fetch_latest_two_scrape_run_ids,
    fetch_snapshot_rows,
)

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


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


@requires_db
def test_fetch_latest_two_scrape_run_ids_orders_by_started_at_desc():
    conn = get_connection()
    run_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '2 days') RETURNING scrape_run_id",
                ("test_platform_xyz", "old.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now()) RETURNING scrape_run_id",
                ("test_platform_xyz", "new.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])
        conn.commit()

        newest, second = fetch_latest_two_scrape_run_ids(conn, "test_platform_xyz")
        assert newest == run_ids[1]
        assert second == run_ids[0]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_snapshot_rows_returns_expected_columns():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz", "TestCityXYZ", "TestLocalityXYZ",
                 "GOAT Life Mocha Marvel", 1, 119.0, True),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        rows = fetch_snapshot_rows(conn, scrape_run_id)
        assert len(rows) == 1
        assert rows[0]["product_name"] == "GOAT Life Mocha Marvel"
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_drop_calendar_returns_paused_skus():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sku_drop_calendar (sku_name) VALUES (%s) "
                "ON CONFLICT (sku_name) DO NOTHING",
                ("TestSkuXYZ",),
            )
        conn.commit()
        assert "TestSkuXYZ" in fetch_drop_calendar(conn)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sku_drop_calendar WHERE sku_name = %s", ("TestSkuXYZ",))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_brand_defence_rate_computes_percentage():
    conn = get_connection()
    scrape_run_id = None
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            # 2 localities total, GOAT at rank 1 in one of them -> 50%
            rows = [
                ("TestCityXYZ", "TestLocalityA", "GOAT Life Mocha Marvel", 1, True),
                ("TestCityXYZ", "TestLocalityB", "Prustlr Discovery Protein Oats", 1, False),
            ]
            for city, locality, name, rank, is_goat in rows:
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "product_name, rank, selling_price, is_goat) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                    (scrape_run_id, "test_platform_xyz", city, locality, name, rank, 119.0, is_goat),
                )
                snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        rate = fetch_brand_defence_rate(conn, scrape_run_id)
        assert rate == 50.0
    finally:
        with conn.cursor() as cur:
            if snapshot_ids:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()
