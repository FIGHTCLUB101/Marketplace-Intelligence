"""Sync notebooks/artifacts/localities_master_serviceable.parquet into Postgres.

Replaces build_locality_data.py's JS-writing role: reads the master parquet,
upserts the localities dimension table, records a pipeline_runs row, and
appends the scored columns into locality_scores. Run this after every NB08
rerun (locally or via the GitHub Actions "Run workflow" button in Sprint 2).
"""
from pathlib import Path

import pandas as pd
import psycopg2.extras

from shelf_common import compute_loc_key

SCORE_COLUMNS = [
    "icp_score", "icp_verdict", "gtm_action", "serviceability_state",
    "serviceability_confidence", "archetype_ml", "lifecycle",
    "n_brands_confirmed", "brands_confirmed_list", "nearest_known_darkstore_km",
    "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed",
    "res_avg_buy_imputed", "price_is_imputed", "employer_quality",
    "primary_sector", "is_metro_connected", "pareto_optimal",
    "hidden_gem_v2", "spillover_gem",
]


def _clean(value):
    """Convert pandas NaN to None so psycopg2 writes SQL NULL, not the string 'nan'."""
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def build_locality_rows(df: pd.DataFrame) -> list[dict]:
    # Only geocoded localities, same filter build_locality_data.py already applies.
    geo = df[df["lat_r"].notna()].copy()
    rows = []
    for _, r in geo.iterrows():
        area = str(r["AREA"]).split(",")[0].strip()
        city = str(r["ADDRESS"]).strip()
        rows.append({
            "loc_key": compute_loc_key(city, area),
            "area": area,
            "city": city,
            "pincode": _clean(r.get("PINCODE")),
            "lat": _clean(r["lat_r"]),
            "lng": _clean(r["lng_r"]),
            "belt_id": _clean(r.get("belt_id")),
            "belt_size": _clean(r.get("belt_size")),
        })
    # De-dupe by loc_key, last-wins: Postgres raises "ON CONFLICT DO UPDATE
    # command cannot affect row a second time" if execute_values below is
    # handed two rows with the same loc_key in one batch, so the upsert
    # target must already be unique per loc_key.
    return list({r["loc_key"]: r for r in rows}.values())


def build_score_rows(df: pd.DataFrame, loc_key_to_id: dict, pipeline_run_id: int) -> list[dict]:
    geo = df[df["lat_r"].notna()].copy()
    rows = []
    for _, r in geo.iterrows():
        area = str(r["AREA"]).split(",")[0].strip()
        city = str(r["ADDRESS"]).strip()
        loc_key = compute_loc_key(city, area)
        locality_id = loc_key_to_id.get(loc_key)
        if locality_id is None:
            continue
        row = {"locality_id": locality_id, "pipeline_run_id": pipeline_run_id}
        for col in SCORE_COLUMNS:
            row[col] = _clean(r.get(col))
        rows.append(row)
    return rows


def sync_locality_scores(parquet_path: Path, conn) -> dict:
    df = pd.read_parquet(parquet_path)
    locality_rows = build_locality_rows(df)

    with conn.cursor() as cur:
        # Upsert localities, get back locality_id for every loc_key.
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO localities (loc_key, area, city, pincode, lat, lng, belt_id, belt_size)
            VALUES %s
            ON CONFLICT (loc_key) DO UPDATE SET
                area = EXCLUDED.area, city = EXCLUDED.city, pincode = EXCLUDED.pincode,
                lat = EXCLUDED.lat, lng = EXCLUDED.lng, belt_id = EXCLUDED.belt_id,
                belt_size = EXCLUDED.belt_size
            """,
            [(r["loc_key"], r["area"], r["city"], r["pincode"], r["lat"], r["lng"],
              r["belt_id"], r["belt_size"]) for r in locality_rows],
        )
        cur.execute("SELECT loc_key, locality_id FROM localities;")
        loc_key_to_id = dict(cur.fetchall())

        cur.execute(
            "INSERT INTO pipeline_runs (source_parquet_filename, row_count) "
            "VALUES (%s, %s) RETURNING pipeline_run_id;",
            (str(parquet_path.name), len(locality_rows)),
        )
        pipeline_run_id = cur.fetchone()[0]

        score_rows = build_score_rows(df, loc_key_to_id, pipeline_run_id)
        if score_rows:
            cols = list(score_rows[0].keys())
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO locality_scores ({', '.join(cols)}) VALUES %s",
                [tuple(r[c] for c in cols) for r in score_rows],
            )
    conn.commit()

    return {
        "localities_upserted": len(locality_rows),
        "scores_inserted": len(score_rows),
        "pipeline_run_id": pipeline_run_id,
    }


if __name__ == "__main__":
    import sys

    from db_connection import get_connection

    default_path = Path(__file__).resolve().parents[1] / "notebooks" / "artifacts" / "localities_master_serviceable.parquet"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    conn = get_connection()
    try:
        result = sync_locality_scores(path, conn)
        print(f"Synced {path.name}: {result}")
    finally:
        conn.close()
