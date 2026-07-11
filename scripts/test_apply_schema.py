import os

import pytest

from apply_schema import apply_schema
from db_connection import get_connection

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)

EXPECTED_TABLES = {
    "localities",
    "pipeline_runs",
    "locality_scores",
    "scrape_runs",
    "shelf_snapshots",
    "locality_annotations",
}


@requires_db
def test_apply_schema_creates_all_tables():
    apply_schema()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public';
            """)
            found = {row[0] for row in cur.fetchall()}
        assert EXPECTED_TABLES.issubset(found)
    finally:
        conn.close()


@requires_db
def test_apply_schema_is_idempotent():
    apply_schema()
    apply_schema()  # must not raise
