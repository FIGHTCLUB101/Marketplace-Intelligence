import os

import pytest

from db_connection import get_connection
from queries_shelf import (
    fetch_drop_calendar,
    fetch_latest_two_scrape_run_ids,
    fetch_snapshot_rows,
    fetch_valid_run_stats,
    pause_sku,
    set_run_status,
    unpause_sku,
)

_PLACEHOLDERS = ("N/A", "Not Available", "Location Error", "Not Serviceable")

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
def test_fetch_latest_two_excludes_quarantined_runs():
    conn = get_connection()
    run_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at, status) "
                "VALUES (%s, %s, now() - interval '2 days', 'valid') RETURNING scrape_run_id",
                ("test_platform_quar", "old_valid.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])  # older, valid
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at, status) "
                "VALUES (%s, %s, now(), 'quarantined') RETURNING scrape_run_id",
                ("test_platform_quar", "new_bad.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])  # newest, quarantined
        conn.commit()

        newest, second = fetch_latest_two_scrape_run_ids(conn, "test_platform_quar")
        # The quarantined newest run must be skipped -> the older valid run wins.
        assert newest == run_ids[0]
        assert second is None
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_set_run_status_updates_status_and_reason():
    conn = get_connection()
    run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_setstatus", "run.xlsx"),
            )
            run_id = cur.fetchone()[0]
        conn.commit()

        set_run_status(conn, run_id, "quarantined", reason="18% capture")
        with conn.cursor() as cur:
            cur.execute("SELECT status, quarantine_reason FROM scrape_runs WHERE scrape_run_id = %s", (run_id,))
            status, reason = cur.fetchone()
        assert status == "quarantined"
        assert reason == "18% capture"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_valid_run_stats_computes_coverage_and_excludes_quarantined():
    conn = get_connection()
    valid_id = quar_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, status) "
                "VALUES (%s, %s, 'valid') RETURNING scrape_run_id",
                ("test_platform_stats", "valid.xlsx"),
            )
            valid_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, status) "
                "VALUES (%s, %s, 'quarantined') RETURNING scrape_run_id",
                ("test_platform_stats", "quar.xlsx"),
            )
            quar_id = cur.fetchone()[0]
            # Valid run: 2 cities, 3 localities, 2 brands, 3 real rows + 1 placeholder.
            valid_rows = [
                ("Mumbai", "Bandra", "Pintola Oats", "Pintola 1kg"),
                ("Mumbai", "Andheri", "Pintola Oats", "Pintola 500g"),
                ("Delhi", "Saket", "Quaker Oats", "Quaker 1kg"),
                ("Delhi", "Saket", "Quaker Oats", "Not Serviceable"),
            ]
            for city, loc, brand, prod in valid_rows:
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "brand_searched, product_name) VALUES (%s,%s,%s,%s,%s,%s)",
                    (valid_id, "test_platform_stats", city, loc, brand, prod),
                )
            # Quarantined run has huge coverage — must NOT leak into the stats.
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, product_name) VALUES (%s,%s,%s,%s,%s,%s)",
                (quar_id, "test_platform_stats", "Chennai", "Adyar", "Alpino Oats", "Alpino 1kg"),
            )
        conn.commit()

        stats = fetch_valid_run_stats(conn, "test_platform_stats", _PLACEHOLDERS, limit=3)
        assert stats == [{"cities": 2, "localities": 3, "brands": 2, "real_rows": 3}]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE scrape_run_id = ANY(%s)", ([valid_id, quar_id],))
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", ([valid_id, quar_id],))
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
