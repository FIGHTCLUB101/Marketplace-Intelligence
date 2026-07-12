"""Self-contained Postgres connection helper for the API layer.

Duplicated (not imported) from scripts/db_connection.py so this Vercel
function bundles without reaching outside web/api/.
"""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill in your "
            "Neon connection string."
        )
    return psycopg2.connect(dsn)
