import os

import pandas as pd
import pytest

from db_connection import get_connection
from sync_locality_scores import build_locality_rows, build_score_rows, sync_locality_scores

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


def _sample_df():
    return pd.DataFrame([
        {
            "AREA": "Indiranagar, Bangalore", "ADDRESS": "Bangalore", "PINCODE": "560038",
            "lat_r": 12.97, "lng_r": 77.64, "belt_id": "B1", "belt_size": 4,
            "icp_score": 87.5, "icp_verdict": "GO", "gtm_action": "PUSH-NOW",
            "serviceability_state": "Confirmed", "serviceability_confidence": "High",
            "archetype_ml": "Premium · Metro", "lifecycle": "established",
            "n_brands_confirmed": 3, "brands_confirmed_list": "blinkit,swiggy,zepto",
            "nearest_known_darkstore_km": 0.8, "blinkit_confirmed": True,
            "swiggy_confirmed": True, "zepto_confirmed": True,
            "res_avg_buy_imputed": 15000.0, "price_is_imputed": False,
            "employer_quality": "High", "primary_sector": "IT",
            "is_metro_connected": True, "pareto_optimal": True,
            "hidden_gem_v2": False, "spillover_gem": False,
        },
        {
            # unmapped locality — lat_r is NaN, must be excluded (mirrors
            # build_locality_data.py's "only geocoded localities" filter)
            "AREA": "Nowhere, Bangalore", "ADDRESS": "Bangalore", "PINCODE": None,
            "lat_r": float("nan"), "lng_r": float("nan"), "belt_id": None, "belt_size": None,
            "icp_score": 10.0, "icp_verdict": "HOLD", "gtm_action": "HOLD",
            "serviceability_state": "Unknown", "serviceability_confidence": "Low",
            "archetype_ml": "Average / Mixed", "lifecycle": "nascent",
            "n_brands_confirmed": 0, "brands_confirmed_list": "",
            "nearest_known_darkstore_km": None, "blinkit_confirmed": False,
            "swiggy_confirmed": False, "zepto_confirmed": False,
            "res_avg_buy_imputed": None, "price_is_imputed": True,
            "employer_quality": None, "primary_sector": None,
            "is_metro_connected": False, "pareto_optimal": False,
            "hidden_gem_v2": False, "spillover_gem": False,
        },
    ])


def test_build_locality_rows_excludes_ungeocoded_and_computes_loc_key():
    rows = build_locality_rows(_sample_df())
    assert len(rows) == 1
    row = rows[0]
    assert row["loc_key"] == "bangalore|indiranagar"
    assert row["area"] == "Indiranagar"
    assert row["city"] == "Bangalore"
    assert row["lat"] == 12.97
    assert row["lng"] == 77.64
    assert row["belt_id"] == "B1"
    assert row["belt_size"] == 4


def test_build_score_rows_maps_via_loc_key():
    df = _sample_df()
    loc_key_to_id = {"bangalore|indiranagar": 42}
    rows = build_score_rows(df, loc_key_to_id, pipeline_run_id=7)
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 42
    assert row["pipeline_run_id"] == 7
    assert row["icp_score"] == 87.5
    assert row["gtm_action"] == "PUSH-NOW"


@requires_db
def test_sync_locality_scores_end_to_end(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    parquet_path = tmp_path / "master.parquet"
    _sample_df().to_parquet(parquet_path, index=False)

    conn = get_connection()
    try:
        result = sync_locality_scores(parquet_path, conn)
        assert result["localities_upserted"] == 1
        assert result["scores_inserted"] == 1

        with conn.cursor() as cur:
            cur.execute("SELECT loc_key FROM localities WHERE loc_key = %s", ("bangalore|indiranagar",))
            assert cur.fetchone() is not None
            cur.execute(
                "SELECT gtm_action FROM current_locality_scores cs "
                "JOIN localities l ON l.locality_id = cs.locality_id "
                "WHERE l.loc_key = %s", ("bangalore|indiranagar",)
            )
            assert cur.fetchone() == ("PUSH-NOW",)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM locality_scores WHERE locality_id IN "
                        "(SELECT locality_id FROM localities WHERE loc_key = %s)", ("bangalore|indiranagar",))
            cur.execute("DELETE FROM localities WHERE loc_key = %s", ("bangalore|indiranagar",))
        conn.commit()
        conn.close()
