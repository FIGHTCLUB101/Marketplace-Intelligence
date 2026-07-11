# Sprint 1 — Data Layer (Schema + Backfill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Neon Postgres database for GOAT Life's GTM system and backfill it with everything that currently exists — the locality/ICP master parquet and the four competitor/own-brand shelf xlsx files — so the database becomes the real source of truth instead of scattered xlsx/parquet files.

**Architecture:** Plain SQL DDL (`db/schema.sql`) applied via a small Python script, no ORM — matches this repo's existing style of direct, dependency-light scripts (`pandas` + `openpyxl`, no SQLAlchemy anywhere today). Two idempotent sync scripts (`scripts/sync_locality_scores.py`, `scripts/sync_shelf_snapshots.py`) each split into a pure transform function (unit-testable with no DB) and a thin I/O orchestrator (integration-tested against a real Postgres). A `scripts/backfill_all.py` orchestrator runs both against every existing data file once.

**Tech Stack:** Python, `psycopg2-binary` (raw SQL, no ORM — consistent with existing codebase), `python-dotenv` (env config), `pandas`/`openpyxl` (already in use), `pytest` (already in use).

## Global Constraints

- Free tier only: Neon Postgres free project (spec: "Hosting stack").
- No auth (spec: "Constraints locked in during design").
- `loc_key` is a **composite** `city|area` key (lowercased, stripped) — spec's data-model section describes this as mirroring `enrich_competitor_data.py`, but that script's actual key is area-only, which risks collisions between same-named localities in different cities. This plan uses the safer composite key; it's a superset of the information already collected by every scraper (all of them record `City` separately), so it introduces no new data requirement.
- `shelf_snapshots.locality_id` is a **nullable** FK — a scraped row must always be storable even if it can't be matched to a known locality (imperfect string matching is a known reality of this data), so raw `city_raw`/`locality_raw` text columns are always populated regardless of match success.
- `SCRAPE/shelf_history/2026-07-02.xlsx` is byte-identical (332775 bytes, same timestamp) to `SCRAPE/blinkit_goatlife_data.xlsx` — it is not a separate data point and must not be backfilled as one, to avoid duplicate rows.
- Existing test convention: tests live alongside the scripts they test in `scripts/`, run via `cd scripts && python -m pytest -q` (see `scripts/test_build_locality_data.py`). New tests follow this same convention.
- Existing import convention: scripts in `scripts/` import each other with flat imports (e.g. `import contract`), relying on being run as `python scripts/thatfile.py` from the repo root. New scripts follow this convention.

---

### Task 1: Provision Neon and wire up project config

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `.env.example`
- Create: `.env` (local only, gitignored, not committed)

**Interfaces:**
- Produces: `DATABASE_URL` environment variable, read by every later task via `python-dotenv`.

- [ ] **Step 1: Provision the database**

Go to https://neon.tech, sign up (free tier), create a new project named `goatlife`. In the Neon console, copy the **pooled** connection string (the one with `-pooler` in the hostname — this is the PgBouncer-pooled variant the spec calls for, needed later for serverless functions in Sprint 3). It looks like:

```
postgresql://<user>:<password>@<host>-pooler.<region>.aws.neon.tech/<dbname>?sslmode=require
```

- [ ] **Step 2: Add dependencies to `requirements.txt`**

Current content:
```
openpyxl>=3.1
pgeocode>=0.5
pandas>=2.0
pytest>=8.0
```

New content:
```
openpyxl>=3.1
pgeocode>=0.5
pandas>=2.0
pytest>=8.0
psycopg2-binary>=2.9
python-dotenv>=1.0
```

- [ ] **Step 3: Install the new dependencies**

Run: `pip install -r requirements.txt`
Expected: `psycopg2-binary` and `python-dotenv` install without error (`psycopg2-binary` avoids the C-compiler-required build that plain `psycopg2` needs on Windows).

- [ ] **Step 4: Add `.env` to `.gitignore`**

Current `.gitignore` content:
```
__pycache__/
*.pyc
.pytest_cache/
.vercel/
node_modules/
structured_magicbricks_localities.csv
.ipynb_checkpoints/
notebooks/artifacts/

# generated notebook exports
notebooks/*.csv
notebooks/*.xlsx

scripts/exports/
```

Append:
```

# local secrets
.env
```

- [ ] **Step 5: Create `.env.example`**

```
DATABASE_URL=postgresql://user:password@host-pooler.region.aws.neon.tech/dbname?sslmode=require
```

- [ ] **Step 6: Create your real `.env`**

Create `.env` in the repo root (this file is gitignored — never commit it) with your actual Neon pooled connection string:
```
DATABASE_URL=postgresql://<your-real-connection-string>
```

- [ ] **Step 7: Verify the connection works**

Run:
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); import psycopg2; psycopg2.connect(os.environ['DATABASE_URL']).close(); print('OK')"
```
Expected output: `OK`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore .env.example
git commit -m "chore: add Postgres dependencies and env config for Sprint 1"
```

(`.env` itself is gitignored and will not be staged — verify with `git status` that it does not appear.)

---

### Task 2: Database connection helper

**Files:**
- Create: `scripts/db_connection.py`
- Test: `scripts/test_db_connection.py`

**Interfaces:**
- Consumes: `DATABASE_URL` env var (Task 1).
- Produces: `get_connection() -> psycopg2.extensions.connection`, used by every later DB-touching script.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_db_connection.py`:
```python
import os

import pytest

from db_connection import get_connection

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


@requires_db
def test_get_connection_runs_select_1():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts && python -m pytest test_db_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_connection'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/db_connection.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts && python -m pytest test_db_connection.py -v`
Expected: PASS (or SKIPPED if `DATABASE_URL` isn't set in the current shell — if so, run `python -c "from dotenv import load_dotenv; load_dotenv()"` first, or run pytest via `python -m pytest` from a shell where `.env` has been sourced; simplest is to confirm `DATABASE_URL` is visible with `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(bool(os.environ.get('DATABASE_URL')))"` which should print `True`)

- [ ] **Step 5: Commit**

```bash
git add scripts/db_connection.py scripts/test_db_connection.py
git commit -m "feat: add shared Postgres connection helper"
```

---

### Task 3: Schema DDL and apply script

**Files:**
- Create: `db/schema.sql`
- Create: `scripts/apply_schema.py`
- Test: `scripts/test_apply_schema.py`

**Interfaces:**
- Consumes: `get_connection()` (Task 2).
- Produces: `apply_schema()` — applies `db/schema.sql` to the configured database, idempotently. All later tasks assume this has been run.

- [ ] **Step 1: Write the schema**

Create `db/schema.sql`:
```sql
-- GOAT Life GTM system — Sprint 1 data layer schema.
-- One dimension table (localities) + append-only fact tables (locality_scores,
-- shelf_snapshots) so historical queries work without ever overwriting data.

CREATE TABLE IF NOT EXISTS localities (
    locality_id     SERIAL PRIMARY KEY,
    loc_key         TEXT UNIQUE NOT NULL,
    area            TEXT NOT NULL,
    city            TEXT NOT NULL,
    pincode         TEXT,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    belt_id         TEXT,
    belt_size       INTEGER,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id          SERIAL PRIMARY KEY,
    triggered_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_parquet_filename    TEXT NOT NULL,
    row_count                   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS locality_scores (
    locality_score_id           SERIAL PRIMARY KEY,
    locality_id                  INTEGER NOT NULL REFERENCES localities(locality_id),
    pipeline_run_id               INTEGER NOT NULL REFERENCES pipeline_runs(pipeline_run_id),
    as_of                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    icp_score                       DOUBLE PRECISION,
    icp_verdict                      TEXT,
    gtm_action                        TEXT,
    serviceability_state               TEXT,
    serviceability_confidence           TEXT,
    archetype_ml                         TEXT,
    lifecycle                             TEXT,
    n_brands_confirmed                     INTEGER,
    brands_confirmed_list                   TEXT,
    nearest_known_darkstore_km               DOUBLE PRECISION,
    blinkit_confirmed                         BOOLEAN,
    swiggy_confirmed                           BOOLEAN,
    zepto_confirmed                             BOOLEAN,
    res_avg_buy_imputed                          DOUBLE PRECISION,
    price_is_imputed                              BOOLEAN,
    employer_quality                               TEXT,
    primary_sector                                  TEXT,
    is_metro_connected                               BOOLEAN,
    pareto_optimal                                    BOOLEAN,
    hidden_gem_v2                                      BOOLEAN,
    spillover_gem                                       BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_locality_scores_locality_id ON locality_scores(locality_id);
CREATE INDEX IF NOT EXISTS idx_locality_scores_as_of ON locality_scores(as_of);

CREATE OR REPLACE VIEW current_locality_scores AS
SELECT DISTINCT ON (locality_id) *
FROM locality_scores
ORDER BY locality_id, as_of DESC;

CREATE TABLE IF NOT EXISTS scrape_runs (
    scrape_run_id   SERIAL PRIMARY KEY,
    platform         TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    row_count            INTEGER NOT NULL DEFAULT 0,
    source_file           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shelf_snapshots (
    shelf_snapshot_id  SERIAL PRIMARY KEY,
    scrape_run_id        INTEGER NOT NULL REFERENCES scrape_runs(scrape_run_id),
    platform               TEXT NOT NULL,
    locality_id              INTEGER REFERENCES localities(locality_id),
    city_raw                  TEXT NOT NULL,
    locality_raw                TEXT NOT NULL,
    brand_searched                TEXT,
    rank                            INTEGER,
    product_name                     TEXT,
    pack_size                          TEXT,
    selling_price                        NUMERIC,
    mrp                                    NUMERIC,
    discount_pct                             NUMERIC,
    stock_left                                 TEXT,
    rating                                       TEXT,
    reviews                                        TEXT,
    sponsored                                       BOOLEAN,
    serviceable                                       TEXT,
    is_goat                                             BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_locality_id ON shelf_snapshots(locality_id);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_platform ON shelf_snapshots(platform);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_scrape_run_id ON shelf_snapshots(scrape_run_id);

CREATE TABLE IF NOT EXISTS locality_annotations (
    annotation_id    SERIAL PRIMARY KEY,
    locality_id        INTEGER NOT NULL REFERENCES localities(locality_id),
    note                 TEXT,
    status                 TEXT,
    budget_note              NUMERIC,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_locality_annotations_locality_id ON locality_annotations(locality_id);
```

- [ ] **Step 2: Write the failing test**

Create `scripts/test_apply_schema.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scripts && python -m pytest test_apply_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apply_schema'`

- [ ] **Step 4: Write minimal implementation**

Create `scripts/apply_schema.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scripts && python -m pytest test_apply_schema.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql scripts/apply_schema.py scripts/test_apply_schema.py
git commit -m "feat: add Postgres schema and idempotent apply script"
```

---

### Task 4: Shared ingestion helpers (loc_key, is_goat, price parsing)

**Files:**
- Create: `scripts/shelf_common.py`
- Test: `scripts/test_shelf_common.py`

**Interfaces:**
- Produces: `compute_loc_key(city: str, area: str) -> str`, `is_goat_brand(product_name) -> bool`, `to_float(value) -> float | None`, `to_int(value) -> int | None`, `to_bool(value) -> bool | None`. Used by both sync scripts (Tasks 5 and 6).

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_shelf_common.py`:
```python
import math

from shelf_common import compute_loc_key, is_goat_brand, to_bool, to_float, to_int


def test_compute_loc_key_lowercases_and_strips():
    assert compute_loc_key("Bangalore", "Indiranagar") == "bangalore|indiranagar"
    assert compute_loc_key(" Delhi ", " Connaught Place ") == "delhi|connaught place"


def test_is_goat_brand_matches_case_insensitively():
    assert is_goat_brand("GOAT Life Mocha Marvel 400g") is True
    assert is_goat_brand("goat life choco-nut crunch") is True
    assert is_goat_brand("Yoga Bar Oats") is False


def test_to_float_parses_currency_strings():
    assert to_float("Rs.399") == 399.0
    assert to_float("₹1,299") == 1299.0
    assert to_float("23%") == 23.0


def test_to_float_returns_none_for_unparseable():
    assert to_float("N/A") is None
    assert to_float(None) is None
    assert math.isnan(float("nan")) or to_float(float("nan")) is None


def test_to_int_parses_and_handles_na():
    assert to_int("3") == 3
    assert to_int(5) == 5
    assert to_int("N/A") is None
    assert to_int(None) is None


def test_to_bool_parses_true_false_strings():
    assert to_bool("True") is True
    assert to_bool("False") is False
    assert to_bool(True) is True
    assert to_bool("N/A") is None
    assert to_bool(None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_shelf_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shelf_common'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/shelf_common.py`:
```python
"""Shared helpers for turning scraped/computed data into DB-ready values.

compute_loc_key mirrors the join logic enrich_competitor_data.py already uses,
tightened to a city+area composite key (every scraper already records City
separately, so this needs no new data) to avoid collisions between
same-named localities in different cities.
"""
import re


def compute_loc_key(city, area) -> str:
    return f"{str(city).strip().lower()}|{str(area).strip().lower()}"


def is_goat_brand(product_name) -> bool:
    return "goat life" in str(product_name).lower()


def to_float(value):
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in ("", "n/a", "nan", "none"):
        return None
    nums = re.findall(r"\d+\.?\d*", s.replace(",", ""))
    if not nums:
        return None
    return float(nums[-1])


def to_int(value):
    f = to_float(value)
    return int(f) if f is not None else None


def to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_shelf_common.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/shelf_common.py scripts/test_shelf_common.py
git commit -m "feat: add shared loc_key/is_goat/type-parsing helpers"
```

---

### Task 5: Locality scores sync (parquet → localities + pipeline_runs + locality_scores)

**Files:**
- Create: `scripts/sync_locality_scores.py`
- Test: `scripts/test_sync_locality_scores.py`

**Interfaces:**
- Consumes: `compute_loc_key` (Task 4), `get_connection` (Task 2).
- Produces: `build_locality_rows(df) -> list[dict]`, `build_score_rows(df, loc_key_to_id, pipeline_run_id) -> list[dict]`, `sync_locality_scores(parquet_path, conn) -> dict` (returns `{"localities_upserted": int, "scores_inserted": int, "pipeline_run_id": int}`). `sync_locality_scores` is what Task 7's backfill orchestrator calls.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_sync_locality_scores.py`:
```python
import os

import pandas as pd
import pytest

from db_connection import get_connection
from sync_locality_scores import build_locality_rows, build_score_rows, sync_locality_scores

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


def _sample_df():
    return pd.DataFrame([
        {
            "AREA": "Indiranagar, Bangalore", "ADDRESS": "Bangalore", "PINCODE": "560038",
            "lat_r": 12.97, "lng_r": 77.64, "belt_id": "B1", "belt_size": 4,
            "icp_score": 87.5, "icp_verdict": "GO", "gtm_action": "PUSH-NOW",
            "serviceability_state": "Confirmed", "serviceability_confidence": "High",
            "archetype_ml": "Premium · Metro", "lifecycle": "established",
            "n_brands_confirmed": 3, "brands_confirmed_list": "blinkit,swiggy,zepto",
            "nearest_known_darkstore_km": 0.8, "blinkit_confirmed": True,
            "swiggy_confirmed": True, "zepto_confirmed": True,
            "res_avg_buy_imputed": 15000.0, "price_is_imputed": False,
            "employer_quality": "High", "primary_sector": "IT",
            "is_metro_connected": True, "pareto_optimal": True,
            "hidden_gem_v2": False, "spillover_gem": False,
        },
        {
            # unmapped locality — lat_r is NaN, must be excluded (mirrors
            # build_locality_data.py's "only geocoded localities" filter)
            "AREA": "Nowhere, Bangalore", "ADDRESS": "Bangalore", "PINCODE": None,
            "lat_r": float("nan"), "lng_r": float("nan"), "belt_id": None, "belt_size": None,
            "icp_score": 10.0, "icp_verdict": "HOLD", "gtm_action": "HOLD",
            "serviceability_state": "Unknown", "serviceability_confidence": "Low",
            "archetype_ml": "Average / Mixed", "lifecycle": "nascent",
            "n_brands_confirmed": 0, "brands_confirmed_list": "",
            "nearest_known_darkstore_km": None, "blinkit_confirmed": False,
            "swiggy_confirmed": False, "zepto_confirmed": False,
            "res_avg_buy_imputed": None, "price_is_imputed": True,
            "employer_quality": None, "primary_sector": None,
            "is_metro_connected": False, "pareto_optimal": False,
            "hidden_gem_v2": False, "spillover_gem": False,
        },
    ])


def test_build_locality_rows_excludes_ungeocoded_and_computes_loc_key():
    rows = build_locality_rows(_sample_df())
    assert len(rows) == 1
    row = rows[0]
    assert row["loc_key"] == "bangalore|indiranagar"
    assert row["area"] == "Indiranagar"
    assert row["city"] == "Bangalore"
    assert row["lat"] == 12.97
    assert row["lng"] == 77.64
    assert row["belt_id"] == "B1"
    assert row["belt_size"] == 4


def test_build_score_rows_maps_via_loc_key():
    df = _sample_df()
    loc_key_to_id = {"bangalore|indiranagar": 42}
    rows = build_score_rows(df, loc_key_to_id, pipeline_run_id=7)
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 42
    assert row["pipeline_run_id"] == 7
    assert row["icp_score"] == 87.5
    assert row["gtm_action"] == "PUSH-NOW"


@requires_db
def test_sync_locality_scores_end_to_end(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    parquet_path = tmp_path / "master.parquet"
    _sample_df().to_parquet(parquet_path, index=False)

    conn = get_connection()
    try:
        result = sync_locality_scores(parquet_path, conn)
        assert result["localities_upserted"] == 1
        assert result["scores_inserted"] == 1

        with conn.cursor() as cur:
            cur.execute("SELECT loc_key FROM localities WHERE loc_key = %s", ("bangalore|indiranagar",))
            assert cur.fetchone() is not None
            cur.execute(
                "SELECT gtm_action FROM current_locality_scores cs "
                "JOIN localities l ON l.locality_id = cs.locality_id "
                "WHERE l.loc_key = %s", ("bangalore|indiranagar",)
            )
            assert cur.fetchone() == ("PUSH-NOW",)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM locality_scores WHERE locality_id IN "
                        "(SELECT locality_id FROM localities WHERE loc_key = %s)", ("bangalore|indiranagar",))
            cur.execute("DELETE FROM localities WHERE loc_key = %s", ("bangalore|indiranagar",))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_sync_locality_scores.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sync_locality_scores'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/sync_locality_scores.py`:
```python
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
    return rows


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_sync_locality_scores.py -v`
Expected: PASS (3 passed — or 2 passed, 1 skipped if `DATABASE_URL` isn't set)

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_locality_scores.py scripts/test_sync_locality_scores.py
git commit -m "feat: add locality scores sync (parquet -> Postgres)"
```

---

### Task 6: Shelf snapshots sync (xlsx → scrape_runs + shelf_snapshots)

**Files:**
- Create: `scripts/sync_shelf_snapshots.py`
- Test: `scripts/test_sync_shelf_snapshots.py`

**Interfaces:**
- Consumes: `compute_loc_key`, `is_goat_brand`, `to_float`, `to_int`, `to_bool` (Task 4), `get_connection` (Task 2).
- Produces: `build_snapshot_rows(df, platform, loc_key_to_id) -> list[dict]`, `sync_shelf_snapshots(xlsx_path, platform, conn) -> dict` (returns `{"rows_inserted": int, "rows_matched": int, "scrape_run_id": int}`). `sync_shelf_snapshots` is what Task 7's backfill orchestrator calls, once per platform.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_sync_shelf_snapshots.py`:
```python
import os

import pandas as pd
import pytest

from db_connection import get_connection
from sync_shelf_snapshots import build_snapshot_rows, sync_shelf_snapshots

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


def test_build_snapshot_rows_blinkit_platform():
    df = pd.DataFrame([{
        "City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": "Yoga Bar Oats",
        "Product Name": "Yoga Bar 26% High Protein Oats", "Pack Size": "400 g",
        "Selling Price": "₹399", "MRP": "₹499", "Discount %": "20%",
        "Stock Left": "N/A", "Rating": "4.2", "Serviceable": "Yes",
    }])
    rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={"bangalore|indiranagar": 5})
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 5
    assert row["city_raw"] == "Bangalore"
    assert row["locality_raw"] == "Indiranagar"
    assert row["selling_price"] == 399.0
    assert row["mrp"] == 499.0
    assert row["discount_pct"] == 20.0
    assert row["is_goat"] is False


def test_build_snapshot_rows_zepto_platform_splits_combined_locality():
    df = pd.DataFrame([{
        "Locality": "Koramangala, Bangalore", "Brand Searched": "GOAT Life", "Rank": 1,
        "Product Name": "GOAT Life Mocha Marvel", "Selling Price": "₹99", "MRP": "₹99",
        "Discount": "N/A", "Pack Size": "50 g", "Rating": "4.5", "Reviews": "(120)",
        "Sponsored": "False",
    }])
    rows = build_snapshot_rows(df, "zepto", loc_key_to_id={"bangalore|koramangala": 9})
    assert len(rows) == 1
    row = rows[0]
    assert row["locality_id"] == 9
    assert row["city_raw"] == "Bangalore"
    assert row["locality_raw"] == "Koramangala"
    assert row["rank"] == 1
    assert row["is_goat"] is True
    assert row["sponsored"] is False


def test_build_snapshot_rows_unmatched_locality_keeps_row_with_null_id():
    df = pd.DataFrame([{
        "City": "Pune", "Locality": "Unknown Colony", "Brand Searched": "Quaker Oats",
        "Product Name": "Quaker Oats", "Pack Size": "N/A", "Selling Price": "N/A",
        "MRP": "N/A", "Discount %": "N/A", "Stock Left": "N/A", "Rating": "N/A",
        "Serviceable": "No",
    }])
    rows = build_snapshot_rows(df, "blinkit", loc_key_to_id={})
    assert len(rows) == 1
    assert rows[0]["locality_id"] is None
    assert rows[0]["city_raw"] == "Pune"


@requires_db
def test_sync_shelf_snapshots_end_to_end(tmp_path):
    from apply_schema import apply_schema
    apply_schema()

    xlsx_path = tmp_path / "blinkit_oats_data.xlsx"
    pd.DataFrame([{
        "City": "Bangalore", "Locality": "TestLocalityXYZ", "Brand Searched": "Yoga Bar Oats",
        "Product Name": "Yoga Bar Oats", "Pack Size": "400 g", "Selling Price": "₹399",
        "MRP": "₹499", "Discount %": "20%", "Stock Left": "N/A", "Rating": "4.2",
        "Serviceable": "Yes",
    }]).to_excel(xlsx_path, index=False)

    conn = get_connection()
    try:
        result = sync_shelf_snapshots(xlsx_path, "blinkit", conn)
        assert result["rows_inserted"] == 1

        with conn.cursor() as cur:
            cur.execute(
                "SELECT platform, selling_price FROM shelf_snapshots WHERE locality_raw = %s",
                ("TestLocalityXYZ",),
            )
            row = cur.fetchone()
            assert row == ("blinkit", 399.0)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE locality_raw = %s", ("TestLocalityXYZ",))
            cur.execute("DELETE FROM scrape_runs WHERE source_file = %s", (str(xlsx_path),))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_sync_shelf_snapshots.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sync_shelf_snapshots'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/sync_shelf_snapshots.py`:
```python
"""Sync a scraper's xlsx output into Postgres (scrape_runs + shelf_snapshots).

Handles the column-layout differences across the 4 scrapers directly (Blinkit
and Swiggy use separate City/Locality columns; Zepto uses one combined
"Area, City" Locality column). See PLATFORM_COLUMNS.
"""
from pathlib import Path

import pandas as pd
import psycopg2.extras

from shelf_common import compute_loc_key, is_goat_brand, to_bool, to_float, to_int

# Maps our DB column name -> the source xlsx column name for each platform.
# None means the platform's scraper doesn't capture that field.
PLATFORM_COLUMNS = {
    "blinkit": {
        "brand_searched": "Brand Searched", "rank": None, "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount %", "stock_left": "Stock Left", "rating": "Rating",
        "reviews": None, "sponsored": None, "serviceable": "Serviceable",
    },
    "blinkit_goatlife": {
        "brand_searched": "Search Term", "rank": "Rank", "product_name": "Product Name",
        "pack_size": "Pack Size", "selling_price": "Selling Price", "mrp": "MRP",
        "discount_pct": "Discount %", "stock_left": "Stock Left", "rating": "Rating",
        "reviews": None, "sponsored": None, "serviceable": "Serviceable",
    },
    "swiggy": {
        "brand_searched": "Brand Searched", "rank": None, "product_name": "Product Name",
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
            "pack_size": r.get(col_map["pack_size"]) if col_map["pack_size"] else None,
            "selling_price": to_float(r.get(col_map["selling_price"])) if col_map["selling_price"] else None,
            "mrp": to_float(r.get(col_map["mrp"])) if col_map["mrp"] else None,
            "discount_pct": to_float(r.get(col_map["discount_pct"])) if col_map["discount_pct"] else None,
            "stock_left": r.get(col_map["stock_left"]) if col_map["stock_left"] else None,
            "rating": r.get(col_map["rating"]) if col_map["rating"] else None,
            "reviews": r.get(col_map["reviews"]) if col_map["reviews"] else None,
            "sponsored": to_bool(r.get(col_map["sponsored"])) if col_map["sponsored"] else None,
            "serviceable": r.get(col_map["serviceable"]) if col_map["serviceable"] else None,
            "is_goat": is_goat_brand(product_name) if product_name else False,
        })
    return rows


def sync_shelf_snapshots(xlsx_path: Path, platform: str, conn) -> dict:
    df = pd.read_excel(xlsx_path)

    with conn.cursor() as cur:
        cur.execute("SELECT loc_key, locality_id FROM localities;")
        loc_key_to_id = dict(cur.fetchall())

        cur.execute(
            "INSERT INTO scrape_runs (platform, source_file, row_count) "
            "VALUES (%s, %s, %s) RETURNING scrape_run_id;",
            (platform, str(xlsx_path), len(df)),
        )
        scrape_run_id = cur.fetchone()[0]

        rows = build_snapshot_rows(df, platform, loc_key_to_id)
        matched = sum(1 for r in rows if r["locality_id"] is not None)
        if rows:
            cols = ["scrape_run_id"] + list(rows[0].keys())
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO shelf_snapshots ({', '.join(cols)}) VALUES %s",
                [tuple([scrape_run_id] + [r[c] for c in rows[0].keys()]) for r in rows],
            )
        cur.execute(
            "UPDATE scrape_runs SET finished_at = now(), row_count = %s WHERE scrape_run_id = %s",
            (len(rows), scrape_run_id),
        )
    conn.commit()

    return {"rows_inserted": len(rows), "rows_matched": matched, "scrape_run_id": scrape_run_id}


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_sync_shelf_snapshots.py -v`
Expected: PASS (4 passed — or 3 passed, 1 skipped if `DATABASE_URL` isn't set)

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_shelf_snapshots.py scripts/test_sync_shelf_snapshots.py
git commit -m "feat: add shelf snapshots sync (scraper xlsx -> Postgres)"
```

---

### Task 7: Backfill orchestrator and real data load

**Files:**
- Create: `scripts/backfill_all.py`
- Modify: `RUNNING.md`

**Interfaces:**
- Consumes: `sync_locality_scores` (Task 5), `sync_shelf_snapshots` (Task 6), `get_connection` (Task 2), `apply_schema` (Task 3).
- Produces: a one-shot CLI script; no other task depends on its internals.

- [ ] **Step 1: Write `scripts/backfill_all.py`**

```python
"""One-time backfill: loads every existing data file into the fresh database.

Run this once after Task 3's schema has been applied to a new database. Safe
to re-run (every sync function is idempotent/append-only), but re-running
will create duplicate scrape_runs/pipeline_runs entries for files already
loaded — intended for disaster recovery, not routine use.

NOTE: SCRAPE/shelf_history/2026-07-02.xlsx is byte-identical to
SCRAPE/blinkit_goatlife_data.xlsx (confirmed during design: same 332775
byte size, same timestamp) — it is NOT a separate data point and is
deliberately not loaded here to avoid duplicate rows.
"""
import argparse
from pathlib import Path

from apply_schema import apply_schema
from db_connection import get_connection
from sync_locality_scores import sync_locality_scores
from sync_shelf_snapshots import sync_shelf_snapshots

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PARQUET = ROOT / "notebooks" / "artifacts" / "localities_master_serviceable.parquet"
DEFAULT_XLSX = {
    "blinkit": ROOT / "blinkit_oats_data.xlsx",
    "swiggy": ROOT / "swiggy_oats_data.xlsx",
    "zepto": ROOT / "zepto_oats_data.xlsx",
    # No default for blinkit_goatlife — it currently lives outside this repo
    # at C:\Users\singh\Desktop\SCRAPE\blinkit_goatlife_data.xlsx. Pass its
    # path explicitly with --blinkit-goatlife-file.
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--blinkit-file", type=Path, default=DEFAULT_XLSX["blinkit"])
    parser.add_argument("--swiggy-file", type=Path, default=DEFAULT_XLSX["swiggy"])
    parser.add_argument("--zepto-file", type=Path, default=DEFAULT_XLSX["zepto"])
    parser.add_argument("--blinkit-goatlife-file", type=Path, default=None)
    args = parser.parse_args()

    apply_schema()
    conn = get_connection()
    try:
        print(f"Syncing locality scores from {args.parquet} ...")
        print(sync_locality_scores(args.parquet, conn))

        for platform, path in [
            ("blinkit", args.blinkit_file),
            ("swiggy", args.swiggy_file),
            ("zepto", args.zepto_file),
        ]:
            if path.exists():
                print(f"Syncing {platform} shelf snapshots from {path} ...")
                print(sync_shelf_snapshots(path, platform, conn))
            else:
                print(f"SKIP {platform}: {path} not found")

        if args.blinkit_goatlife_file and args.blinkit_goatlife_file.exists():
            print(f"Syncing blinkit_goatlife shelf snapshots from {args.blinkit_goatlife_file} ...")
            print(sync_shelf_snapshots(args.blinkit_goatlife_file, "blinkit_goatlife", conn))
        else:
            print("SKIP blinkit_goatlife: pass --blinkit-goatlife-file <path> to include it "
                  "(currently lives at C:\\Users\\singh\\Desktop\\SCRAPE\\blinkit_goatlife_data.xlsx)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backfill against the real data**

Run from the repo root:
```bash
cd scripts
python backfill_all.py --blinkit-goatlife-file "C:\Users\singh\Desktop\SCRAPE\blinkit_goatlife_data.xlsx"
```
Expected: four `Syncing ...` lines each followed by a result dict with non-zero counts, no `SKIP` lines (all four files should be found — `blinkit_oats_data.xlsx`, `swiggy_oats_data.xlsx`, `zepto_oats_data.xlsx` already exist at the repo root; `blinkit_goatlife_data.xlsx` is passed explicitly since it hasn't moved into this repo yet — that happens in Sprint 2).

- [ ] **Step 3: Verify row counts against the database**

Run:
```bash
python -c "
from db_connection import get_connection
conn = get_connection()
with conn.cursor() as cur:
    for table in ['localities', 'locality_scores', 'shelf_snapshots', 'pipeline_runs', 'scrape_runs']:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        print(table, cur.fetchone()[0])
conn.close()
"
```
Expected: `localities` around 886 (matches the "886 geocoded localities" figure from `RUNNING.md`), `shelf_snapshots` in the low thousands (matches the combined row counts of the 4 xlsx files), all counts non-zero.

- [ ] **Step 4: Update `RUNNING.md` with the new backfill step**

Find this section in `RUNNING.md` (after the existing "6. Rebuild the ML pipeline from scratch" section, before "Quick reference"):
```
### 6b. Run notebooks in order
```

Add a new section immediately after the notebook table in that section (after line "After NB08 finishes, re-run Step 2 (`build_locality_data.py`) to push the new parquet into the frontend."):
```markdown

---

## 8. Sync data into Postgres (Sprint 1+)

The dashboard is migrating from static JS files to a live database. To sync current data in:

```bash
cd scripts
python sync_locality_scores.py          # notebook parquet -> localities + locality_scores
python sync_shelf_snapshots.py blinkit blinkit_oats_data.xlsx   # one call per platform xlsx
```

Requires `DATABASE_URL` set in `.env` (see `.env.example`). Run `python apply_schema.py` once
against a fresh database before the first sync.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_all.py RUNNING.md
git commit -m "feat: add backfill orchestrator, load existing data into Postgres"
```

---

## Self-Review Notes

**Spec coverage:** Task 1 covers "Hosting stack" (Neon provisioning) and the `.env`-based credential
handling described under "Ingestion & sync." Task 3's schema covers every table in the spec's "Data
model" section verbatim (`localities`, `locality_scores` + `current_locality_scores` view,
`pipeline_runs`, `shelf_snapshots`, `scrape_runs`, `locality_annotations`), including the full
`locality_scores` column set implied by "everything `build_locality_data.py`'s `COLS` list currently
computes" (the design doc's explicit list omitted `is_metro_connected`/`price_is_imputed`, which are
present in the real `COLS` list — added here for fidelity to the actual source). Tasks 5–6 implement
"Path 1"/"Path 2" sync logic from the "Ingestion & sync" section, including the `loc_key` correction
and nullable-FK decision documented in Global Constraints. Task 7 implements the "Backfill (Sprint 1,
one-time)" paragraph, including the shelf_history-is-a-duplicate finding. `locality_annotations` exists
in the schema (Task 3) but has no sync/write path yet — correct, since the write path is the API's job
in Sprint 3, not Sprint 1's.

**Placeholder scan:** no TBD/TODO; every step has complete, runnable code.

**Type consistency:** `compute_loc_key(city, area)` signature is identical everywhere it's called
(Task 4 definition; Tasks 5 and 6 usage). `sync_locality_scores(parquet_path, conn)` and
`sync_shelf_snapshots(xlsx_path, platform, conn)` signatures match between their definitions (Tasks 5/6)
and their usage in Task 7's `backfill_all.py`. Return dict keys (`localities_upserted`,
`scores_inserted`, `pipeline_run_id` / `rows_inserted`, `rows_matched`, `scrape_run_id`) are consistent
between implementation and tests.
