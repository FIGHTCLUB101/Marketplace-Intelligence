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


LAST_PIPELINE_RUN_SQL = "SELECT MAX(triggered_at) AS last_pipeline_run FROM pipeline_runs"

LAST_SCRAPE_PER_PLATFORM_SQL = """
    SELECT platform, MAX(finished_at) AS last_scrape_at
    FROM scrape_runs
    WHERE finished_at IS NOT NULL
    GROUP BY platform
"""


def fetch_freshness(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(LAST_PIPELINE_RUN_SQL)
        last_pipeline_run = cur.fetchone()["last_pipeline_run"]

        cur.execute(LAST_SCRAPE_PER_PLATFORM_SQL)
        by_platform = {row["platform"]: row["last_scrape_at"] for row in cur.fetchall()}

    return {"last_pipeline_run": last_pipeline_run, "last_scrape_by_platform": by_platform}


SHELF_LATEST_TWO_RUNS_SQL = """
    SELECT scrape_run_id FROM scrape_runs WHERE platform = %s
    ORDER BY started_at DESC LIMIT 2
"""


def fetch_latest_two_scrape_run_ids(conn, platform):
    """Returns (newest_id, second_newest_id). second_newest_id is None if
    only one run exists for this platform; both are None if zero exist."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SHELF_LATEST_TWO_RUNS_SQL, (platform,))
        ids = [row["scrape_run_id"] for row in cur.fetchall()]
    if not ids:
        return None, None
    if len(ids) == 1:
        return ids[0], None
    return ids[0], ids[1]


SHELF_SNAPSHOT_ROWS_SQL = """
    SELECT city_raw, locality_raw, product_name, rank, selling_price, is_goat
    FROM shelf_snapshots WHERE scrape_run_id = %s
"""


def fetch_snapshot_rows(conn, scrape_run_id):
    """Returns list of dicts in the shape shelf_changes.py's pure functions expect."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SHELF_SNAPSHOT_ROWS_SQL, (scrape_run_id,))
        return cur.fetchall()


SHELF_CURRENT_SNAPSHOT_SQL = """
    SELECT
        s.shelf_snapshot_id, s.platform, s.locality_id, s.city_raw, s.locality_raw,
        s.brand_searched, s.rank, s.product_name, s.pack_size, s.selling_price,
        s.mrp, s.discount_pct, s.stock_left, s.rating, s.reviews, s.sponsored,
        s.serviceable, s.is_goat, r.started_at, r.finished_at
    FROM shelf_snapshots s
    JOIN scrape_runs r ON r.scrape_run_id = s.scrape_run_id
    WHERE s.scrape_run_id = %s
    ORDER BY s.city_raw, s.locality_raw
"""


def fetch_current_snapshot(conn, scrape_run_id):
    """Returns every shelf_snapshots row for one run (all columns), unlike
    fetch_snapshot_rows which only selects the narrow subset shelf_changes.py's
    diff functions need. Used for current-state (non-diffed) views."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SHELF_CURRENT_SNAPSHOT_SQL, (scrape_run_id,))
        return cur.fetchall()


def fetch_drop_calendar(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT sku_name FROM sku_drop_calendar")
        return {row["sku_name"] for row in cur.fetchall()}


BRAND_DEFENCE_RATE_SQL = """
    SELECT
        COUNT(*) FILTER (WHERE is_goat AND rank = 1) AS goat_rank1_count,
        COUNT(DISTINCT (city_raw, locality_raw)) AS total_localities
    FROM shelf_snapshots
    WHERE scrape_run_id = %s AND rank IS NOT NULL
"""


def fetch_brand_defence_rate(conn, scrape_run_id):
    """Returns the % (0-100, 1 decimal) of localities in this scrape_run
    where a GOAT Life product holds rank 1. None if the run has zero
    numeric-rank rows (shouldn't happen for a real scrape, but avoids a
    divide-by-zero on a pathological/empty run)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(BRAND_DEFENCE_RATE_SQL, (scrape_run_id,))
        row = cur.fetchone()
        goat_rank1_count, total_localities = row["goat_rank1_count"], row["total_localities"]
    if not total_localities:
        return None
    return round(100 * goat_rank1_count / total_localities, 1)


SHELF_RUN_LABELS_SQL = """
    SELECT scrape_run_id, started_at FROM scrape_runs
    WHERE platform = %(platform)s ORDER BY started_at ASC
"""

SHELF_WATCHED_COMPETITORS_SQL = """
    SELECT product_name FROM shelf_snapshots
    WHERE platform = %(platform)s AND NOT is_goat
      AND product_name NOT IN ('N/A', 'Not Available', 'Location Error', 'Not Serviceable')
    GROUP BY product_name
    ORDER BY COUNT(*) DESC
    LIMIT %(top_n)s
"""

SHELF_TREND_AVG_RANK_SQL = """
    SELECT s.product_name, BOOL_OR(s.is_goat) AS is_goat, r.scrape_run_id,
           ROUND(AVG(s.rank)::numeric, 2) AS avg_rank
    FROM shelf_snapshots s
    JOIN scrape_runs r ON r.scrape_run_id = s.scrape_run_id
    WHERE s.platform = %(platform)s AND s.rank IS NOT NULL
      AND (s.is_goat OR s.product_name = ANY(%(watched)s))
    GROUP BY s.product_name, r.scrape_run_id
"""


def fetch_shelf_trends(conn, platform, top_n=3):
    """Returns {"platform", "weeks": [iso date str, ...],
    "series": [{"product_name", "is_goat", "data": [avg_rank|None per week]}, ...]}
    for every GOAT product plus the top_n most-frequently-appearing competitor
    product names (mirrors the antigravity repo's select_watched_competitors)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SHELF_RUN_LABELS_SQL, {"platform": platform})
        runs = cur.fetchall()
        weeks = [r["started_at"].strftime("%Y-%m-%d") for r in runs]
        run_id_to_week = {r["scrape_run_id"]: r["started_at"].strftime("%Y-%m-%d") for r in runs}

        cur.execute(SHELF_WATCHED_COMPETITORS_SQL, {"platform": platform, "top_n": top_n})
        watched = [row["product_name"] for row in cur.fetchall()]

        cur.execute(SHELF_TREND_AVG_RANK_SQL, {"platform": platform, "watched": watched})
        points = cur.fetchall()

    data_by_name = {}
    is_goat_by_name = {}
    for p in points:
        name = p["product_name"]
        is_goat_by_name[name] = p["is_goat"]
        data_by_name.setdefault(name, {})[run_id_to_week[p["scrape_run_id"]]] = float(p["avg_rank"])

    series = [
        {
            "product_name": name,
            "is_goat": is_goat_by_name[name],
            "data": [week_data.get(w) for w in weeks],
        }
        for name, week_data in data_by_name.items()
    ]
    return {"platform": platform, "weeks": weeks, "series": series}
