import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from db_connection import get_connection
from sync_shelf_snapshots import build_snapshot_rows, sync_shelf_snapshots

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


def test_build_snapshot_rows_blinkit_platform():
    df = pd.DataFrame([{
        "City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": "Yoga Bar Oats",
        "Product Name": "Yoga Bar 26% High Protein Oats", "Pack Size": "400 g",
        "Selling Price": "₹399", "MRP": "₹499", "Discount %": "20%",
        "Stock Left": "N/A", "Rating": "4.2", "Sponsored": "False", "Serviceable": "Yes",
    }])
    rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={"bangalore|indiranagar": 5})
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 5
    assert row["city_raw"] == "Bangalore"
    assert row["locality_raw"] == "Indiranagar"
    assert row["selling_price"] == 399.0
    assert row["mrp"] == 499.0
    assert row["discount_pct"] == 20.0
    assert row["is_goat"] is False
    assert row["sponsored"] is False


def test_build_snapshot_rows_blinkit_platform_captures_sponsored_intrusion():
    # e.g. Alpino buying sponsored placement in a "Pintola Oats" search.
    df = pd.DataFrame([{
        "City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": "Pintola Oats",
        "Product Name": "Alpino High Protein Oats Chocolate 1 kg", "Pack Size": "1 kg",
        "Selling Price": "₹448", "MRP": "₹549", "Discount %": "18%",
        "Stock Left": "N/A", "Rating": "N/A", "Sponsored": "True", "Serviceable": "Yes",
    }])
    rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={"bangalore|indiranagar": 5})
    assert rows[0]["sponsored"] is True
    assert rows[0]["brand_searched"] == "Pintola Oats"
    assert rows[0]["product_name"] == "Alpino High Protein Oats Chocolate 1 kg"


def test_build_snapshot_rows_handles_na_placeholder_via_real_xlsx_roundtrip():
    # Regression test: pd.DataFrame([{"Stock Left": "N/A"}]) constructed
    # directly in Python keeps "N/A" as a literal string, but a real
    # pd.read_excel() round-trip (what every scraper's actual output goes
    # through) silently converts "N/A" cells to a NaN float on read. Building
    # the DataFrame directly here would not have caught the bug this
    # regresses -- pack_size/stock_left/rating landing in the DB as the
    # literal string "NaN" instead of NULL, because those three fields (unlike
    # selling_price/mrp/discount_pct/sponsored/rank) had no NaN-aware cleanup.
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = Path(tmpdir) / "roundtrip.xlsx"
        pd.DataFrame([{
            "City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": "Quaker Oats",
            "Product Name": "Not Available", "Pack Size": "N/A", "Selling Price": "N/A",
            "MRP": "N/A", "Discount %": "N/A", "Stock Left": "N/A", "Rating": "N/A",
            "Sponsored": "N/A", "Serviceable": "Yes",
        }]).to_excel(xlsx_path, index=False)

        df = pd.read_excel(xlsx_path)
        rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={})
        row = rows[0]
        assert row["pack_size"] is None
        assert row["stock_left"] is None
        assert row["rating"] is None
        assert row["selling_price"] is None
        assert row["sponsored"] is None
        assert row["product_name"] == "Not Available"  # meaningful sentinel text, not nulled


def test_build_snapshot_rows_zepto_platform_splits_combined_locality():
    df = pd.DataFrame([{
        "Locality": "Koramangala, Bangalore", "Brand Searched": "GOAT Life", "Rank": 1,
        "Product Name": "GOAT Life Mocha Marvel", "Selling Price": "₹99", "MRP": "₹99",
        "Discount": "N/A", "Pack Size": "50 g", "Rating": "4.5", "Reviews": "(120)",
        "Sponsored": "False",
    }])
    rows = build_snapshot_rows(df, "zepto", loc_key_to_id={"bangalore|koramangala": 9})
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 9
    assert row["city_raw"] == "Bangalore"
    assert row["locality_raw"] == "Koramangala"
    assert row["rank"] == 1
    assert row["is_goat"] is True
    assert row["sponsored"] is False


def test_build_snapshot_rows_unmatched_locality_keeps_row_with_null_id():
    df = pd.DataFrame([{
        "City": "Pune", "Locality": "Unknown Colony", "Brand Searched": "Quaker Oats",
        "Product Name": "Quaker Oats", "Pack Size": "N/A", "Selling Price": "N/A",
        "MRP": "N/A", "Discount %": "N/A", "Stock Left": "N/A", "Rating": "N/A",
        "Serviceable": "No",
    }])
    rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={})
    assert len(rows) == 1
    assert rows[0]["locality_id"] is None
    assert rows[0]["city_raw"] == "Pune"


@requires_db
def test_sync_shelf_snapshots_end_to_end(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    xlsx_path = tmp_path / "blinkit_oats_data.xlsx"
    pd.DataFrame([{
        "City": "Bangalore", "Locality": "TestLocalityXYZ", "Brand Searched": "Yoga Bar Oats",
        "Product Name": "Yoga Bar Oats", "Pack Size": "400 g", "Selling Price": "₹399",
        "MRP": "₹499", "Discount %": "20%", "Stock Left": "N/A", "Rating": "4.2",
        "Serviceable": "Yes",
    }]).to_excel(xlsx_path, index=False)

    conn = get_connection()
    try:
        # enforce_gate=False: this test verifies column mapping + ingest, not
        # the completeness gate (a 1-row input would rightly be quarantined
        # against blinkit's real baseline — that path is covered separately).
        result = sync_shelf_snapshots(xlsx_path, "blinkit", conn, enforce_gate=False)
        assert result["rows_inserted"] == 1
        assert result["status"] == "valid"

        with conn.cursor() as cur:
            cur.execute(
                "SELECT platform, selling_price FROM shelf_snapshots WHERE locality_raw = %s",
                ("TestLocalityXYZ",),
            )
            row = cur.fetchone()
            assert row == ("blinkit", 399.0)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE locality_raw = %s", ("TestLocalityXYZ",))
            cur.execute("DELETE FROM scrape_runs WHERE source_file = %s", (str(xlsx_path),))
        conn.commit()
        conn.close()


def _one_row_blinkit_xlsx(path, locality):
    pd.DataFrame([{
        "City": "Bangalore", "Locality": locality, "Brand Searched": "Yoga Bar Oats",
        "Product Name": "Yoga Bar Oats", "Pack Size": "400 g", "Selling Price": "₹399",
        "MRP": "₹499", "Discount %": "20%", "Stock Left": "N/A", "Rating": "4.2",
        "Serviceable": "Yes",
    }]).to_excel(path, index=False)


@requires_db
def test_sync_quarantines_degraded_run(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    conn = get_connection()
    baseline_id = None
    xlsx_path = tmp_path / "blinkit_oats_data.xlsx"
    _one_row_blinkit_xlsx(xlsx_path, "TestDegradedXYZ")
    try:
        # Seed a healthy baseline valid run so the gate has a bar to fail against.
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, status) "
                "VALUES ('blinkit', 'baseline_seed.xlsx', 'valid') RETURNING scrape_run_id",
            )
            baseline_id = cur.fetchone()[0]
            for i in range(20):
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "brand_searched, product_name) VALUES (%s,'blinkit',%s,%s,%s,%s)",
                    (baseline_id, f"City{i % 5}", f"Loc{i}", f"Brand{i % 8}", f"Product {i}"),
                )
        conn.commit()

        result = sync_shelf_snapshots(xlsx_path, "blinkit", conn, min_ratio=0.7)
        assert result["status"] == "quarantined"
        assert result["rows_inserted"] == 0
        assert result["quarantine_reason"]  # a non-empty explanation

        # The quarantined run exists (audit trail) but has NO snapshot rows.
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM scrape_runs WHERE scrape_run_id = %s", (result["scrape_run_id"],))
            assert cur.fetchone()[0] == "quarantined"
            cur.execute("SELECT count(*) FROM shelf_snapshots WHERE scrape_run_id = %s", (result["scrape_run_id"],))
            assert cur.fetchone()[0] == 0
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE scrape_run_id = %s", (baseline_id,))
            cur.execute("DELETE FROM scrape_runs WHERE source_file = %s", (str(xlsx_path),))
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (baseline_id,))
        conn.commit()
        conn.close()


@requires_db
def test_sync_ingests_when_gate_passes(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    conn = get_connection()
    xlsx_path = tmp_path / "blinkit_oats_data.xlsx"
    _one_row_blinkit_xlsx(xlsx_path, "TestGatePassXYZ")
    try:
        # min_ratio=0.0 → any coverage clears the gate; proves the ok-branch ingests.
        result = sync_shelf_snapshots(xlsx_path, "blinkit", conn, min_ratio=0.0)
        assert result["status"] == "valid"
        assert result["rows_inserted"] == 1
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE locality_raw = %s", ("TestGatePassXYZ",))
            cur.execute("DELETE FROM scrape_runs WHERE source_file = %s", (str(xlsx_path),))
        conn.commit()
        conn.close()
