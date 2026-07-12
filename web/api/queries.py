"""SQL query functions for the API layer. Each fetch_* function takes an
open psycopg2 connection and returns plain dicts (via RealDictCursor)."""
from psycopg2.extras import RealDictCursor

COMPETITOR_HISTORY_SQL = """
    SELECT
        s.shelf_snapshot_id, s.platform, s.locality_id, s.city_raw, s.locality_raw,
        s.brand_searched, s.rank, s.product_name, s.pack_size, s.selling_price,
        s.mrp, s.discount_pct, s.stock_left, s.rating, s.reviews, s.sponsored,
        s.serviceable, s.is_goat, r.started_at, r.finished_at
    FROM shelf_snapshots s
    JOIN scrape_runs r ON r.scrape_run_id = s.scrape_run_id
    WHERE (%(locality_id)s IS NULL OR s.locality_id = %(locality_id)s)
      AND (%(platform)s IS NULL OR s.platform = %(platform)s)
    ORDER BY r.started_at ASC
"""


def fetch_competitor_history(conn, locality_id=None, platform=None):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(COMPETITOR_HISTORY_SQL, {"locality_id": locality_id, "platform": platform})
        return cur.fetchall()


COMPETITOR_SUMMARY_SQL = """
    WITH latest_runs AS (
        SELECT DISTINCT ON (platform) platform, scrape_run_id
        FROM scrape_runs
        ORDER BY platform, started_at DESC
    ),
    latest_snapshots AS (
        SELECT s.*
        FROM shelf_snapshots s
        JOIN latest_runs lr
          ON lr.platform = s.platform AND lr.scrape_run_id = s.scrape_run_id
    )
    SELECT
        locality_id, platform,
        COUNT(DISTINCT brand_searched) FILTER (WHERE NOT is_goat) AS n_competitor_brands,
        ROUND(AVG(selling_price) FILTER (WHERE NOT is_goat)::numeric, 1) AS competitor_avg_price,
        BOOL_OR(is_goat) AS goat_present
    FROM latest_snapshots
    WHERE locality_id IS NOT NULL
    GROUP BY locality_id, platform
    ORDER BY locality_id, platform
"""


def fetch_competitor_summary(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(COMPETITOR_SUMMARY_SQL)
        return cur.fetchall()


LOCALITIES_SQL = """
    SELECT
        l.locality_id, l.loc_key, l.area, l.city, l.pincode, l.lat, l.lng,
        l.belt_id, l.belt_size,
        cs.as_of, cs.icp_score, cs.icp_verdict, cs.gtm_action,
        cs.serviceability_state, cs.serviceability_confidence, cs.archetype_ml,
        cs.lifecycle, cs.n_brands_confirmed, cs.brands_confirmed_list,
        cs.nearest_known_darkstore_km, cs.blinkit_confirmed, cs.swiggy_confirmed,
        cs.zepto_confirmed, cs.res_avg_buy_imputed, cs.price_is_imputed,
        cs.employer_quality, cs.primary_sector, cs.is_metro_connected,
        cs.pareto_optimal, cs.hidden_gem_v2, cs.spillover_gem
    FROM localities l
    JOIN current_locality_scores cs ON cs.locality_id = l.locality_id
    ORDER BY l.locality_id
"""


def fetch_localities(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(LOCALITIES_SQL)
        return cur.fetchall()


def compute_belts(locality_rows):
    """Group locality rows (as returned by fetch_localities) into belts of
    size >= 3, matching scripts/build_locality_data.py's pandas groupby."""
    groups = {}
    for r in locality_rows:
        if not r["belt_id"] or not r["belt_size"] or r["belt_size"] < 3:
            continue
        key = (r["belt_id"], r["city"])
        groups.setdefault(key, []).append(r)

    belts = []
    for (belt_id, city), members in groups.items():
        icp_scores = [m["icp_score"] for m in members if m["icp_score"] is not None]
        belts.append({
            "belt_id": belt_id,
            "city": city,
            "size": members[0]["belt_size"],
            "avg_icp": round(sum(icp_scores) / len(icp_scores), 1) if icp_scores else None,
            "go_count": sum(1 for m in members if m["icp_verdict"] == "GO"),
            "confirmed_count": sum(1 for m in members if m["serviceability_state"] == "Confirmed"),
            "members": [m["area"] for m in members[:12]],
        })
    belts.sort(key=lambda b: b["size"], reverse=True)
    return belts


ANNOTATIONS_SELECT_SQL = """
    SELECT annotation_id, locality_id, note, status, budget_note, created_at, updated_at
    FROM locality_annotations
    WHERE (%(locality_id)s IS NULL OR locality_id = %(locality_id)s)
    ORDER BY created_at DESC
"""


def fetch_annotations(conn, locality_id=None):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(ANNOTATIONS_SELECT_SQL, {"locality_id": locality_id})
        return cur.fetchall()


ANNOTATION_INSERT_SQL = """
    INSERT INTO locality_annotations (locality_id, note, status, budget_note)
    VALUES (%(locality_id)s, %(note)s, %(status)s, %(budget_note)s)
    RETURNING annotation_id, locality_id, note, status, budget_note, created_at, updated_at
"""


def insert_annotation(conn, locality_id, note, status, budget_note):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(ANNOTATION_INSERT_SQL, {
            "locality_id": locality_id, "note": note, "status": status, "budget_note": budget_note,
        })
        row = cur.fetchone()
        conn.commit()
        return row
