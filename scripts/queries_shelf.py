"""Postgres access for the shelf change-detection pipeline. Self-contained
(only imports psycopg2.extras) — scripts/ and web/api/ intentionally don't
share code across the Vercel bundle boundary (see web/api/db.py's own
duplication of db_connection.py for the same reason).
"""
from psycopg2.extras import RealDictCursor


def fetch_latest_two_scrape_run_ids(conn, platform):
    """Returns (newest_id, second_newest_id). second_newest_id is None if
    only one run exists for this platform; both are None if zero exist."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT scrape_run_id FROM scrape_runs WHERE platform = %s "
            "ORDER BY started_at DESC LIMIT 2",
            (platform,),
        )
        ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return None, None
    if len(ids) == 1:
        return ids[0], None
    return ids[0], ids[1]


def fetch_snapshot_rows(conn, scrape_run_id):
    """Returns list of dicts (city_raw, locality_raw, product_name, rank,
    selling_price, is_goat) for one scrape_run_id — the shape
    shelf_changes.py's pure functions expect."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT city_raw, locality_raw, product_name, rank, selling_price, is_goat "
            "FROM shelf_snapshots WHERE scrape_run_id = %s",
            (scrape_run_id,),
        )
        return cur.fetchall()


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
