import os

import pytest

from db_connection import get_connection
from queries_shelf import (
    fetch_drop_calendar,
    fetch_latest_two_scrape_run_ids,
    fetch_snapshot_rows,
    pause_sku,
    unpause_sku,
)

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


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
        # Deletes the scrape_runs parent rows too — Sprint 1's equivalent
        # test did not do this and left orphaned rows in production (Task 1).
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_latest_two_returns_none_second_when_only_one_run_exists():
    conn = get_connection()
    run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_solo", "only.xlsx"),
            )
            run_id = cur.fetchone()[0]
        conn.commit()

        newest, second = fetch_latest_two_scrape_run_ids(conn, "test_platform_xyz_solo")
        assert newest == run_id
        assert second is None
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (run_id,))
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
        assert rows[0]["rank"] == 1
        assert rows[0]["is_goat"] is True
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_snapshot_rows_includes_brand_stock_serviceable():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_cols", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, product_name, selling_price, stock_left, serviceable, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_cols", "TestCityXYZ", "TestLocalityXYZ",
                 "Pintola Oats", "Pintola Oats 1kg", 249.0, "In Stock", "Yes", False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        rows = fetch_snapshot_rows(conn, scrape_run_id)
        assert len(rows) == 1
        assert rows[0]["brand_searched"] == "Pintola Oats"
        assert rows[0]["stock_left"] == "In Stock"
        assert rows[0]["serviceable"] == "Yes"
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_pause_and_unpause_sku_roundtrip():
    conn = get_connection()
    try:
        pause_sku(conn, "TestSkuXYZ", note="test pause")
        assert "TestSkuXYZ" in fetch_drop_calendar(conn)

        unpause_sku(conn, "TestSkuXYZ")
        assert "TestSkuXYZ" not in fetch_drop_calendar(conn)
    finally:
        unpause_sku(conn, "TestSkuXYZ")  # safety net if an assert above failed
        conn.close()
