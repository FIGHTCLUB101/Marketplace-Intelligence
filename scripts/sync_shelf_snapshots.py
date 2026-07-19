"""Sync a scraper's xlsx output into Postgres (scrape_runs + shelf_snapshots).

Handles the column-layout differences across the 4 scrapers directly (Blinkit
and Swiggy use separate City/Locality columns; Zepto uses one combined
"Area, City" Locality column). See PLATFORM_COLUMNS.
"""
from pathlib import Path

import pandas as pd
import psycopg2.extras

from completeness_gate import PLACEHOLDER_NAMES, baseline_from_stats, evaluate, run_stats
from queries_shelf import fetch_valid_run_stats
from shelf_common import compute_loc_key, is_goat_brand, to_bool, to_float, to_int, to_str

# Maps our DB column name -> the source xlsx column name for each platform.
# None means the platform's scraper doesn't capture that field.
PLATFORM_COLUMNS = {
    "blinkit": {
        "brand_searched": "Brand Searched", "rank": "Rank", "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount %", "stock_left": "Stock Left", "rating": "Rating",
        "reviews": None, "sponsored": "Sponsored", "serviceable": "Serviceable",
    },
    "blinkit_goatlife": {
        "brand_searched": "Search Term", "rank": "Rank", "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount %", "stock_left": "Stock Left", "rating": "Rating",
        "reviews": None, "sponsored": "Sponsored", "serviceable": "Serviceable",
    },
    "swiggy": {
        "brand_searched": "Brand Searched", "rank": "Rank", "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount %", "stock_left": "Stock Left", "rating": "Rating",
        "reviews": None, "sponsored": "Sponsored", "serviceable": "Serviceable",
    },
    "zepto": {
        "brand_searched": "Brand Searched", "rank": "Rank", "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount", "stock_left": None, "rating": "Rating",
        "reviews": "Reviews", "sponsored": "Sponsored", "serviceable": None,
    },
}

# Platforms whose xlsx has a single combined "Area, City" Locality column
# instead of separate City/Locality columns.
COMBINED_LOCALITY_PLATFORMS = {"zepto"}


def _split_city_locality(row, platform: str) -> tuple[str, str]:
    if platform in COMBINED_LOCALITY_PLATFORMS:
        parts = [p.strip() for p in str(row["Locality"]).split(",")]
        area, city = parts[0], parts[1] if len(parts) > 1 else ""
        return city, area
    return str(row["City"]).strip(), str(row["Locality"]).strip()


def build_snapshot_rows(df: pd.DataFrame, platform: str, loc_key_to_id: dict) -> list[dict]:
    col_map = PLATFORM_COLUMNS[platform]
    rows = []
    for _, r in df.iterrows():
        city, area = _split_city_locality(r, platform)
        loc_key = compute_loc_key(city, area)
        product_name = r.get(col_map["product_name"]) if col_map["product_name"] else None
        rows.append({
            "platform": platform,
            "locality_id": loc_key_to_id.get(loc_key),
            "city_raw": city,
            "locality_raw": area,
            "brand_searched": r.get(col_map["brand_searched"]) if col_map["brand_searched"] else None,
            "rank": to_int(r.get(col_map["rank"])) if col_map["rank"] else None,
            "product_name": product_name,
            "pack_size": to_str(r.get(col_map["pack_size"])) if col_map["pack_size"] else None,
            "selling_price": to_float(r.get(col_map["selling_price"])) if col_map["selling_price"] else None,
            "mrp": to_float(r.get(col_map["mrp"])) if col_map["mrp"] else None,
            "discount_pct": to_float(r.get(col_map["discount_pct"])) if col_map["discount_pct"] else None,
            "stock_left": to_str(r.get(col_map["stock_left"])) if col_map["stock_left"] else None,
            "rating": to_str(r.get(col_map["rating"])) if col_map["rating"] else None,
            "reviews": to_str(r.get(col_map["reviews"])) if col_map["reviews"] else None,
            "sponsored": to_bool(r.get(col_map["sponsored"])) if col_map["sponsored"] else None,
            "serviceable": r.get(col_map["serviceable"]) if col_map["serviceable"] else None,
            "is_goat": is_goat_brand(product_name) if product_name else False,
        })
    return rows


def sync_shelf_snapshots(xlsx_path: Path, platform: str, conn, min_ratio=0.7, enforce_gate=True) -> dict:
    """Loads a scraper's xlsx into Postgres, but only after the completeness
    gate confirms the run is trustworthy. A run that fails the gate (e.g. the
    2026-07-17 blinkit run that captured ~18% of the shelf) is still recorded
    in scrape_runs for the audit trail, marked status='quarantined' with a
    reason, but its snapshot rows are NOT ingested — so a degraded scrape can
    never become the source of truth for a week-over-week comparison.

    enforce_gate=False bypasses the gate (used by tests exercising column
    mapping rather than gating). min_ratio is the fraction of the rolling
    baseline each coverage dimension must reach to pass."""
    df = pd.read_excel(xlsx_path)

    with conn.cursor() as cur:
        cur.execute("SELECT loc_key, locality_id FROM localities;")
        loc_key_to_id = dict(cur.fetchall())

    rows = build_snapshot_rows(df, platform, loc_key_to_id)
    matched = sum(1 for r in rows if r["locality_id"] is not None)

    # Completeness gate — evaluated before any write decision.
    if enforce_gate:
        baseline = baseline_from_stats(fetch_valid_run_stats(conn, platform, PLACEHOLDER_NAMES))
        decision = evaluate(run_stats(rows), baseline, min_ratio=min_ratio)
    else:
        decision = {"ok": True, "reasons": []}

    status = "valid" if decision["ok"] else "quarantined"
    reason = None if decision["ok"] else "; ".join(decision["reasons"])

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO scrape_runs (platform, source_file, row_count, status, quarantine_reason) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING scrape_run_id;",
            (platform, str(xlsx_path), len(df), status, reason),
        )
        scrape_run_id = cur.fetchone()[0]

        inserted = 0
        if decision["ok"] and rows:
            cols = ["scrape_run_id"] + list(rows[0].keys())
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO shelf_snapshots ({', '.join(cols)}) VALUES %s",
                [tuple([scrape_run_id] + [r[c] for c in rows[0].keys()]) for r in rows],
            )
            inserted = len(rows)
        cur.execute(
            "UPDATE scrape_runs SET finished_at = now(), row_count = %s WHERE scrape_run_id = %s",
            (inserted, scrape_run_id),
        )
    conn.commit()

    return {"rows_inserted": inserted, "rows_matched": matched if decision["ok"] else 0,
            "scrape_run_id": scrape_run_id, "status": status, "quarantine_reason": reason}


if __name__ == "__main__":
    import sys

    from db_connection import get_connection

    if len(sys.argv) != 3:
        print("Usage: python sync_shelf_snapshots.py <platform> <xlsx_path>")
        sys.exit(1)

    platform, path = sys.argv[1], Path(sys.argv[2])
    conn = get_connection()
    try:
        result = sync_shelf_snapshots(path, platform, conn)
        print(f"Synced {path.name} ({platform}): {result}")
    finally:
        conn.close()
