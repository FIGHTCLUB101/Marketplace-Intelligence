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
