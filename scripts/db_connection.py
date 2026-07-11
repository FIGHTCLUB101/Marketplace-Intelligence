"""Shared Postgres connection helper for the GOAT Life data layer.

Reads DATABASE_URL from the environment (loaded from .env via python-dotenv).
Every sync/backfill script in this directory imports get_connection() from here.
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
