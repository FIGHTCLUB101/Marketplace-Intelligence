"""Postgres access for the shelf change-detection pipeline. Self-contained
(only imports psycopg2.extras) — scripts/ and web/api/ intentionally don't
share code across the Vercel bundle boundary (see web/api/db.py's own
duplication of db_connection.py for the same reason).
"""
from psycopg2.extras import RealDictCursor


def fetch_latest_two_scrape_run_ids(conn, platform):
    """Returns (newest_id, second_newest_id) for the platform's two most
    recent VALID runs. Quarantined runs (status != 'valid') are excluded so a
    known-bad scrape can never be selected as the source of truth. second_id
    is None if fewer than two valid runs exist; both None if zero."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT scrape_run_id FROM scrape_runs "
            "WHERE platform = %s AND status = 'valid' "
            "ORDER BY started_at DESC LIMIT 2",
            (platform,),
        )
        ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return None, None
    if len(ids) == 1:
        return ids[0], None
    return ids[0], ids[1]


def set_run_status(conn, scrape_run_id, status, reason=None):
    """Sets a scrape run's trust status ('valid' | 'quarantined'). Reversible —
    call again with status='valid', reason=None to restore. quarantine_reason
    records why, for the audit trail."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE scrape_runs SET status = %s, quarantine_reason = %s "
            "WHERE scrape_run_id = %s",
            (status, reason, scrape_run_id),
        )
    conn.commit()


def fetch_snapshot_rows(conn, scrape_run_id):
    """Returns list of dicts (city_raw, locality_raw, product_name, rank,
    selling_price, is_goat, brand_searched, stock_left, serviceable) for one
    scrape_run_id — the shape shelf_changes.py's and oats_changes.py's pure
    functions expect."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT city_raw, locality_raw, product_name, rank, selling_price, is_goat, "
            "brand_searched, stock_left, serviceable "
            "FROM shelf_snapshots WHERE scrape_run_id = %s",
            (scrape_run_id,),
        )
        return cur.fetchall()


def fetch_valid_run_stats(conn, platform, placeholder_names, limit=3):
    """Per-run coverage stats — {cities, localities, brands, real_rows} — for
    the most recent `limit` VALID runs of a platform, computed in SQL (no rows
    loaded). Feeds the completeness-gate baseline. Quarantined runs are
    excluded so a bad run can't inflate the bar. placeholder_names is passed in
    (not imported) to keep this module self-contained; the real_rows definition
    here must mirror completeness_gate.run_stats()."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT city_raw) AS cities, "
            "count(DISTINCT (city_raw, locality_raw)) AS localities, "
            "count(DISTINCT brand_searched) "
            "  FILTER (WHERE brand_searched IS NOT NULL AND brand_searched <> '') AS brands, "
            "count(*) FILTER (WHERE product_name IS NOT NULL AND product_name <> '' "
            "  AND NOT (product_name = ANY(%s))) AS real_rows "
            "FROM shelf_snapshots "
            "WHERE scrape_run_id IN ("
            "  SELECT scrape_run_id FROM scrape_runs "
            "  WHERE platform = %s AND status = 'valid' "
            "  ORDER BY started_at DESC LIMIT %s) "
            "GROUP BY scrape_run_id",
            (list(placeholder_names), platform, limit),
        )
        return [{"cities": c, "localities": l, "brands": b, "real_rows": rr}
                for (c, l, b, rr) in cur.fetchall()]


def fetch_drop_calendar(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT sku_name FROM sku_drop_calendar")
        return {row[0] for row in cur.fetchall()}


def pause_sku(conn, sku_name, note=None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sku_drop_calendar (sku_name, note) VALUES (%s, %s) "
            "ON CONFLICT (sku_name) DO UPDATE SET paused_since = now(), note = EXCLUDED.note",
            (sku_name, note),
        )
    conn.commit()


def unpause_sku(conn, sku_name):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sku_drop_calendar WHERE sku_name = %s", (sku_name,))
    conn.commit()
