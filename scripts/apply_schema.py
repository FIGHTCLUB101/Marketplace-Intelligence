"""Applies db/schema.sql to the database configured by DATABASE_URL.

Safe to run repeatedly — every statement in schema.sql uses IF NOT EXISTS /
CREATE OR REPLACE.
"""
from pathlib import Path

from db_connection import get_connection

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "db" / "schema.sql"


def apply_schema():
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    apply_schema()
    print(f"Schema applied from {SCHEMA_FILE}")
