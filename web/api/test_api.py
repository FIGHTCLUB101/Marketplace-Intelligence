import os

import pytest
from fastapi.testclient import TestClient

from db import get_connection
from index import app

client = TestClient(app, raise_server_exceptions=False)

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


@requires_db
def test_get_localities_returns_seeded_locality():
    conn = get_connection()
    locality_id = None
    pipeline_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city, pincode, lat, lng, belt_id, belt_size) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ", "560001", 12.9, 77.6, "B1", 4),
            )
            locality_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count) VALUES (%s, %s) "
                "RETURNING pipeline_run_id",
                ("test.parquet", 1),
            )
            pipeline_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO locality_scores (locality_id, pipeline_run_id, icp_score, icp_verdict, gtm_action) "
                "VALUES (%s, %s, %s, %s, %s)",
                (locality_id, pipeline_run_id, 87.5, "GO", "PUSH-NOW"),
            )
        conn.commit()

        response = client.get("/api/localities")
        assert response.status_code == 200
        rows = [r for r in response.json() if r["locality_id"] == locality_id]
        assert len(rows) == 1
        assert rows[0]["area"] == "TestLocalityXYZ"
        assert rows[0]["gtm_action"] == "PUSH-NOW"
    finally:
        with conn.cursor() as cur:
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM locality_scores WHERE pipeline_run_id = %s", (pipeline_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_belts_includes_seeded_belt():
    conn = get_connection()
    locality_ids = []
    pipeline_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count) VALUES (%s, %s) "
                "RETURNING pipeline_run_id",
                ("test.parquet", 3),
            )
            pipeline_run_id = cur.fetchone()[0]
            for i in range(3):
                cur.execute(
                    "INSERT INTO localities (loc_key, area, city, belt_id, belt_size) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING locality_id",
                    (f"testcityxyz|testlocalityxyz{i}", f"TestLocalityXYZ{i}", "TestCityXYZ", "TestBeltXYZ", 3),
                )
                locality_id = cur.fetchone()[0]
                locality_ids.append(locality_id)
                cur.execute(
                    "INSERT INTO locality_scores "
                    "(locality_id, pipeline_run_id, icp_score, icp_verdict, serviceability_state) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (locality_id, pipeline_run_id, 70.0 + i, "GO", "Confirmed"),
                )
        conn.commit()

        response = client.get("/api/belts")
        assert response.status_code == 200
        belts = [b for b in response.json() if b["belt_id"] == "TestBeltXYZ"]
        assert len(belts) == 1
        assert belts[0]["size"] == 3
        assert belts[0]["go_count"] == 3
    finally:
        with conn.cursor() as cur:
            if locality_ids:
                cur.execute("DELETE FROM locality_scores WHERE locality_id = ANY(%s)", (locality_ids,))
                cur.execute("DELETE FROM localities WHERE locality_id = ANY(%s)", (locality_ids,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()


def test_get_localities_returns_generic_500_on_db_error(monkeypatch):
    import index

    def boom():
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(index, "get_connection", boom)
    response = client.get("/api/localities")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}


@requires_db
def test_get_competitor_history_filters_by_locality_and_platform():
    conn = get_connection()
    locality_id = None
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "Yoga Bar", 399, False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        response = client.get(
            f"/api/competitor/history?locality_id={locality_id}&platform=test_platform_xyz"
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["brand_searched"] == "Yoga Bar"

        empty = client.get(f"/api/competitor/history?locality_id={locality_id}&platform=zepto")
        assert empty.json() == []
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_competitor_summary_reflects_latest_run_only():
    conn = get_connection()
    locality_id = None
    old_run_id = None
    new_run_id = None
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '1 day') RETURNING scrape_run_id",
                ("test_platform_xyz", "old.xlsx"),
            )
            old_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (old_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "Old Brand", 199, False),
            )
            snapshot_ids.append(cur.fetchone()[0])

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) VALUES (%s, %s, now()) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz", "new.xlsx"),
            )
            new_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (new_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "New Brand", 299, False),
            )
            snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get("/api/competitor/summary")
        assert response.status_code == 200
        row = next(r for r in response.json() if r["locality_id"] == locality_id)
        assert row["n_competitor_brands"] == 1
        assert row["competitor_avg_price"] == 299.0
        assert row["goat_present"] is False
    finally:
        with conn.cursor() as cur:
            if snapshot_ids:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            if old_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (old_run_id,))
            if new_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (new_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()


@requires_db
def test_post_annotation_creates_row_and_get_lists_it():
    conn = get_connection()
    locality_id = None
    annotation_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]
        conn.commit()

        response = client.post("/api/annotations", json={
            "locality_id": locality_id, "note": "Launched pop-up", "status": "launched",
            "budget_note": 15000,
        })
        assert response.status_code == 201
        body = response.json()
        annotation_id = body["annotation_id"]
        assert body["note"] == "Launched pop-up"
        assert body["status"] == "launched"

        list_response = client.get(f"/api/annotations?locality_id={locality_id}")
        assert list_response.status_code == 200
        notes = [a["note"] for a in list_response.json()]
        assert "Launched pop-up" in notes
    finally:
        with conn.cursor() as cur:
            if annotation_id is not None:
                cur.execute("DELETE FROM locality_annotations WHERE annotation_id = %s", (annotation_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()


@requires_db
def test_post_annotation_returns_404_for_unknown_locality():
    response = client.post("/api/annotations", json={"locality_id": 999999999, "note": "x"})
    assert response.status_code == 404
    assert response.json() == {"detail": "locality not found"}


@requires_db
def test_get_freshness_reflects_latest_timestamps():
    conn = get_connection()
    pipeline_run_id = None
    scrape_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count, triggered_at) "
                "VALUES (%s, %s, now()) RETURNING pipeline_run_id",
                ("test.parquet", 1),
            )
            pipeline_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at, finished_at) "
                "VALUES (%s, %s, now(), now()) RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
        conn.commit()

        response = client.get("/api/meta/freshness")
        assert response.status_code == 200
        body = response.json()
        assert body["last_pipeline_run"] is not None
        assert "test_platform_xyz" in body["last_scrape_by_platform"]
    finally:
        with conn.cursor() as cur:
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_shelf_changes_reports_insufficient_history_with_zero_runs():
    response = client.get("/api/shelf/changes?platform=test_platform_xyz_empty")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_history"
    assert body["new_run_id"] is None


@requires_db
def test_get_shelf_changes_detects_goat_displaced_between_two_runs():
    conn = get_connection()
    run_ids = []
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '7 days') RETURNING scrape_run_id",
                ("test_platform_xyz_changes", "old.xlsx"),
            )
            old_run_id = cur.fetchone()[0]
            run_ids.append(old_run_id)
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (old_run_id, "test_platform_xyz_changes", "TestCityXYZ", "TestLocalityXYZ",
                 "GOAT Life Mocha Marvel", 1, 119.0, True),
            )
            snapshot_ids.append(cur.fetchone()[0])

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now()) RETURNING scrape_run_id",
                ("test_platform_xyz_changes", "new.xlsx"),
            )
            new_run_id = cur.fetchone()[0]
            run_ids.append(new_run_id)
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (new_run_id, "test_platform_xyz_changes", "TestCityXYZ", "TestLocalityXYZ",
                 "Prustlr Discovery Protein Oats", 1, 449.0, False),
            )
            snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get("/api/shelf/changes?platform=test_platform_xyz_changes")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["old_run_id"] == old_run_id
        assert body["new_run_id"] == new_run_id
        assert len(body["goat_displaced"]) == 1
        assert body["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"
        # Only 1 locality in the new run and GOAT holds rank 1 nowhere in it
        # (Prustlr does) -> brand_defence_rate is 0.0, not None.
        assert body["brand_defence_rate"] == 0.0
        # Prustlr is a genuinely new key at this (city, locality) — it wasn't
        # present in the old snapshot under that product name — so it also
        # registers as a rank_intrusion into the vacated rank-1 slot, and
        # conquest_breadth groups it.
        assert body["conquest_breadth"] == [
            {"competitor": "Prustlr Discovery Protein Oats", "locality_count": 1}
        ]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_get_shelf_trends_returns_empty_series_for_unknown_platform():
    response = client.get("/api/shelf/trends?platform=test_platform_xyz_no_data")
    assert response.status_code == 200
    body = response.json()
    assert body["weeks"] == []
    assert body["series"] == []


@requires_db
def test_get_shelf_snapshot_returns_empty_list_for_platform_with_no_runs():
    response = client.get("/api/shelf/snapshot?platform=test_platform_xyz_empty_snap")
    assert response.status_code == 200
    assert response.json() == []


@requires_db
def test_get_shelf_snapshot_returns_current_rows_for_seeded_platform():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_snap", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, rank, product_name, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_snap", "TestCityXYZ", "TestLocalityXYZ",
                 "Yoga Bar Oats", None, "Yoga Bar Premium Golden Rolled Oats", 230.0, False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        response = client.get("/api/shelf/snapshot?platform=test_platform_xyz_snap")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["product_name"] == "Yoga Bar Premium Golden Rolled Oats"
        assert body[0]["rank"] is None
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_shelf_snapshot_filters_by_brand_searched():
    conn = get_connection()
    scrape_run_id = None
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_snapbrand", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            for brand, product in [
                ("Pintola Oats", "Pintola High Protein Oats"),
                ("Alpino Oats", "Alpino Overnight Oats"),
            ]:
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "brand_searched, rank, product_name, selling_price, is_goat) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                    (scrape_run_id, "test_platform_xyz_snapbrand", "TestCityXYZ", "TestLocalityXYZ",
                     brand, 1, product, 199.0, False),
                )
                snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get(
            "/api/shelf/snapshot?platform=test_platform_xyz_snapbrand&brand_searched=Pintola"
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["product_name"] == "Pintola High Protein Oats"
    finally:
        with conn.cursor() as cur:
            for sid in snapshot_ids:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (sid,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_shelf_goat_coverage_returns_distinct_is_goat_localities():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_goatcov_api", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, rank, product_name, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_goatcov_api", "TestCityXYZ", "TestLocalityXYZ",
                 "Pintola Oats", 1, "GOAT Life Oats", 199.0, True),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        response = client.get("/api/shelf/goat-coverage?platform=test_platform_xyz_goatcov_api")
        assert response.status_code == 200
        assert response.json() == [{"city_raw": "TestCityXYZ", "locality_raw": "TestLocalityXYZ"}]
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_shelf_visibility_rate_returns_none_for_platform_with_no_runs():
    response = client.get("/api/shelf/visibility-rate?platform=test_platform_xyz_empty_visrate")
    assert response.status_code == 200
    assert response.json() == {"platform": "test_platform_xyz_empty_visrate", "visibility_rate": None}


@requires_db
def test_get_shelf_visibility_rate_computes_percentage():
    conn = get_connection()
    scrape_run_id = None
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_visrate_api", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            for is_goat in [True, False]:
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "brand_searched, rank, product_name, selling_price, is_goat) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                    (scrape_run_id, "test_platform_xyz_visrate_api", "TestCityXYZ", "TestLocalityXYZ",
                     "Pintola Oats", 1, "Some Oats Product", 199.0, is_goat),
                )
                snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get("/api/shelf/visibility-rate?platform=test_platform_xyz_visrate_api")
        assert response.status_code == 200
        assert response.json() == {"platform": "test_platform_xyz_visrate_api", "visibility_rate": 50.0}
    finally:
        with conn.cursor() as cur:
            for sid in snapshot_ids:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (sid,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()
