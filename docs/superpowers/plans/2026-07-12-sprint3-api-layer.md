# Sprint 3 — API Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the six FastAPI endpoints defined in the Sprint 3 design doc, deployed as one Vercel Python
serverless function inside the existing `web/` Vercel project, giving the Sprint 4 Next.js frontend (and
`curl`) a live API over the Sprint 1/2 Postgres schema.

**Architecture:** One FastAPI ASGI app (`web/api/index.py`) with all six routes, backed by raw psycopg2
queries (`web/api/queries.py`) against Neon Postgres, snake_case Pydantic response models
(`web/api/models.py`), and a self-contained connection helper (`web/api/db.py`) that doesn't reach outside
`web/api/`. Deployed via a `web/vercel.json` rewrite so `/api/*` resolves to this one function.

**Tech Stack:** Python, FastAPI, Pydantic, psycopg2 (raw SQL, no ORM), pytest + FastAPI's `TestClient`,
Vercel Python serverless runtime.

## Global Constraints

- No auth, no rate limiting — consistent with the shared spec's "whoever has the link" decision.
- Free-tier hosting only (Vercel + Neon) — no new paid infrastructure.
- Raw psycopg2 for all DB access, no ORM — the only pattern used anywhere in this repo.
- All response fields are snake_case (`area`, `icp_score`, `gtm_action`, ...), not the legacy
  `AREA`/`ADDRESS` parquet-era names.
- `/api/localities` and `/api/competitor/summary` stay separate endpoints — no server-side merge of GTM
  scores and competitor shelf data.
- `POST /api/annotations` always inserts a new row (history log). Never upserts. `updated_at` on
  `locality_annotations` stays unused this sprint.
- DB tests follow the exact existing convention from `scripts/test_sync_locality_scores.py` and
  `scripts/test_sync_shelf_snapshots.py`: a `requires_db = pytest.mark.skipif(not DATABASE_URL, ...)`
  marker, tests run against the real Neon DB (via `DATABASE_URL` from `.env`), using
  `TestLocalityXYZ`/`TestCityXYZ`-prefixed fixture rows with explicit `DELETE` cleanup in a `finally` block.
  No separate local Postgres instance.
- `web/api/requirements.txt` must NOT include `pandas` or `numpy` — keeps Vercel cold starts light. All
  aggregation (e.g. belts) is plain Python over dicts, not DataFrames.
- `db/schema.sql` is not modified by this sprint — the schema from Sprint 1/2 is already sufficient for all
  six endpoints.
- FastAPI's default error shapes are used as-is: `HTTPException(status_code, detail=...)` for expected
  errors (404), automatic 422 from Pydantic validation, and a catch-all handler returning
  `{"detail": "internal server error"}` (with the real traceback logged server-side, never returned to the
  client) for anything unexpected.
- Tests run via `cd web/api && python -m pytest -q`, mirroring `scripts/`'s and `scraper/`'s existing
  per-directory test convention. No `__init__.py` in `web/api/` — same flat-import convention as
  `scripts/` and `scraper/`.

---

### Task 1: Shared infrastructure + `/api/localities` + `/api/belts`

**Files:**
- Create: `web/api/requirements.txt`
- Create: `web/api/db.py`
- Create: `web/api/models.py`
- Create: `web/api/queries.py`
- Create: `web/api/index.py`
- Test: `web/api/test_api.py`
- Test: `web/api/test_db.py`
- Test: `web/api/test_queries.py`

**Interfaces:**
- Produces (used by Tasks 2-4):
  - `db.get_connection() -> psycopg2.connection`
  - `queries.fetch_localities(conn) -> list[dict]` — one row per locality with its current score, joined.
  - `app` (FastAPI instance) in `index.py`, with the global exception handler already wired — later tasks
    add routes to this same `app` object.
  - `models.Locality`, `models.Belt` Pydantic models.

- [ ] **Step 1: Create the requirements file**

Create `web/api/requirements.txt`:
```
fastapi>=0.115
uvicorn>=0.30
httpx>=0.27
pytest>=8.0
psycopg2-binary>=2.9
python-dotenv>=1.0
pydantic>=2.0
```

Run: `cd web/api && pip install -r requirements.txt`
Expected: installs cleanly, no errors.

- [ ] **Step 2: Write the failing test for the DB connection helper**

Create `web/api/test_db.py`:
```python
import os

import pytest

from db import get_connection

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

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web/api && python -m pytest test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 4: Create `db.py`**

Create `web/api/db.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web/api && python -m pytest test_db.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Write the failing test for `compute_belts` (pure function, no DB)**

Create `web/api/test_queries.py`:
```python
from queries import compute_belts


def test_compute_belts_groups_by_belt_and_filters_small_belts():
    rows = [
        {"belt_id": "B1", "city": "Bangalore", "area": "A1", "belt_size": 4,
         "icp_score": 80.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
        {"belt_id": "B1", "city": "Bangalore", "area": "A2", "belt_size": 4,
         "icp_score": 60.0, "icp_verdict": "HOLD", "serviceability_state": "Unknown"},
        {"belt_id": "B2", "city": "Delhi", "area": "A3", "belt_size": 2,
         "icp_score": 90.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
    ]
    belts = compute_belts(rows)
    assert len(belts) == 1
    assert belts[0]["belt_id"] == "B1"
    assert belts[0]["size"] == 4
    assert belts[0]["avg_icp"] == 70.0
    assert belts[0]["go_count"] == 1
    assert belts[0]["confirmed_count"] == 1
    assert belts[0]["members"] == ["A1", "A2"]


def test_compute_belts_truncates_members_to_twelve():
    rows = [
        {"belt_id": "B1", "city": "Bangalore", "area": f"A{i}", "belt_size": 15,
         "icp_score": 50.0, "icp_verdict": "HOLD", "serviceability_state": "Unknown"}
        for i in range(15)
    ]
    belts = compute_belts(rows)
    assert len(belts[0]["members"]) == 12


def test_compute_belts_ignores_rows_without_a_belt():
    rows = [
        {"belt_id": None, "city": "Bangalore", "area": "A1", "belt_size": None,
         "icp_score": 80.0, "icp_verdict": "GO", "serviceability_state": "Confirmed"},
    ]
    assert compute_belts(rows) == []
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd web/api && python -m pytest test_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'queries'`

- [ ] **Step 8: Create `queries.py` with `fetch_localities` and `compute_belts`**

Create `web/api/queries.py`:
```python
"""SQL query functions for the API layer. Each fetch_* function takes an
open psycopg2 connection and returns plain dicts (via RealDictCursor)."""
from psycopg2.extras import RealDictCursor

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
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd web/api && python -m pytest test_queries.py -v`
Expected: PASS (3 passed)

- [ ] **Step 10: Create the Pydantic response models**

Create `web/api/models.py`:
```python
"""Pydantic response models for the API layer. Field names are snake_case
throughout — a deliberate departure from the legacy parquet-era AREA/ADDRESS
naming, since Sprint 4's Next.js frontend is a fresh consumer of this API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Locality(BaseModel):
    locality_id: int
    loc_key: str
    area: str
    city: str
    pincode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    belt_id: Optional[str] = None
    belt_size: Optional[int] = None
    as_of: Optional[datetime] = None
    icp_score: Optional[float] = None
    icp_verdict: Optional[str] = None
    gtm_action: Optional[str] = None
    serviceability_state: Optional[str] = None
    serviceability_confidence: Optional[str] = None
    archetype_ml: Optional[str] = None
    lifecycle: Optional[str] = None
    n_brands_confirmed: Optional[int] = None
    brands_confirmed_list: Optional[str] = None
    nearest_known_darkstore_km: Optional[float] = None
    blinkit_confirmed: Optional[bool] = None
    swiggy_confirmed: Optional[bool] = None
    zepto_confirmed: Optional[bool] = None
    res_avg_buy_imputed: Optional[float] = None
    price_is_imputed: Optional[bool] = None
    employer_quality: Optional[str] = None
    primary_sector: Optional[str] = None
    is_metro_connected: Optional[bool] = None
    pareto_optimal: Optional[bool] = None
    hidden_gem_v2: Optional[bool] = None
    spillover_gem: Optional[bool] = None


class Belt(BaseModel):
    belt_id: str
    city: str
    size: int
    avg_icp: Optional[float] = None
    go_count: int
    confirmed_count: int
    members: list[str]
```

- [ ] **Step 11: Write the failing tests for the FastAPI app's first two routes**

Create `web/api/test_api.py`:
```python
import os

import pytest
from fastapi.testclient import TestClient

from db import get_connection
from index import app

client = TestClient(app)

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


@requires_db
def test_get_localities_returns_seeded_locality():
    conn = get_connection()
    locality_id = None
    pipeline_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city, pincode, lat, lng, belt_id, belt_size) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ", "560001", 12.9, 77.6, "B1", 4),
            )
            locality_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count) VALUES (%s, %s) "
                "RETURNING pipeline_run_id",
                ("test.parquet", 1),
            )
            pipeline_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO locality_scores (locality_id, pipeline_run_id, icp_score, icp_verdict, gtm_action) "
                "VALUES (%s, %s, %s, %s, %s)",
                (locality_id, pipeline_run_id, 87.5, "GO", "PUSH-NOW"),
            )
        conn.commit()

        response = client.get("/api/localities")
        assert response.status_code == 200
        rows = [r for r in response.json() if r["locality_id"] == locality_id]
        assert len(rows) == 1
        assert rows[0]["area"] == "TestLocalityXYZ"
        assert rows[0]["gtm_action"] == "PUSH-NOW"
    finally:
        with conn.cursor() as cur:
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM locality_scores WHERE pipeline_run_id = %s", (pipeline_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_belts_includes_seeded_belt():
    conn = get_connection()
    locality_ids = []
    pipeline_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count) VALUES (%s, %s) "
                "RETURNING pipeline_run_id",
                ("test.parquet", 3),
            )
            pipeline_run_id = cur.fetchone()[0]
            for i in range(3):
                cur.execute(
                    "INSERT INTO localities (loc_key, area, city, belt_id, belt_size) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING locality_id",
                    (f"testcityxyz|testlocalityxyz{i}", f"TestLocalityXYZ{i}", "TestCityXYZ", "TestBeltXYZ", 3),
                )
                locality_id = cur.fetchone()[0]
                locality_ids.append(locality_id)
                cur.execute(
                    "INSERT INTO locality_scores "
                    "(locality_id, pipeline_run_id, icp_score, icp_verdict, serviceability_state) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (locality_id, pipeline_run_id, 70.0 + i, "GO", "Confirmed"),
                )
        conn.commit()

        response = client.get("/api/belts")
        assert response.status_code == 200
        belts = [b for b in response.json() if b["belt_id"] == "TestBeltXYZ"]
        assert len(belts) == 1
        assert belts[0]["size"] == 3
        assert belts[0]["go_count"] == 3
    finally:
        with conn.cursor() as cur:
            if locality_ids:
                cur.execute("DELETE FROM locality_scores WHERE locality_id = ANY(%s)", (locality_ids,))
                cur.execute("DELETE FROM localities WHERE locality_id = ANY(%s)", (locality_ids,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()


def test_get_localities_returns_generic_500_on_db_error(monkeypatch):
    import index

    def boom():
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(index, "get_connection", boom)
    response = client.get("/api/localities")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
```

- [ ] **Step 12: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'index'`

- [ ] **Step 13: Create `index.py` with the FastAPI app, exception handler, and first two routes**

Create `web/api/index.py`:
```python
"""GOAT Life API — FastAPI app for all Sprint 3 endpoints.

Deployed as a single Vercel Python serverless function; web/vercel.json
rewrites /api/* to this file. Run locally with:
    cd web/api && uvicorn index:app --reload
"""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import queries
from db import get_connection
from models import Belt, Locality

logger = logging.getLogger("goatlife_api")

app = FastAPI(title="GOAT Life API")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/api/localities", response_model=list[Locality])
def get_localities():
    conn = get_connection()
    try:
        return queries.fetch_localities(conn)
    finally:
        conn.close()


@app.get("/api/belts", response_model=list[Belt])
def get_belts():
    conn = get_connection()
    try:
        rows = queries.fetch_localities(conn)
    finally:
        conn.close()
    return queries.compute_belts(rows)
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `cd web/api && python -m pytest -v`
Expected: PASS (7 passed: 1 db + 3 queries + 3 api — 2 of the api tests skip if `DATABASE_URL` is unset,
the 500-error test always runs)

- [ ] **Step 15: Verify the app runs locally**

Run: `cd web/api && uvicorn index:app --reload` in one terminal, then in another:
`curl http://127.0.0.1:8000/api/localities | head -c 300`
Expected: a JSON array of locality objects (or `[]` if the DB has no scored localities yet). Stop the
`uvicorn` process after confirming.

- [ ] **Step 16: Commit**

```bash
git add web/api/requirements.txt web/api/db.py web/api/models.py web/api/queries.py web/api/index.py \
        web/api/test_db.py web/api/test_queries.py web/api/test_api.py
git commit -m "feat: add API scaffolding, localities and belts endpoints"
```

---

### Task 2: `/api/competitor/history` and `/api/competitor/summary`

**Files:**
- Modify: `web/api/queries.py`
- Modify: `web/api/models.py`
- Modify: `web/api/index.py`
- Modify: `web/api/test_api.py`

**Interfaces:**
- Consumes: `db.get_connection()`, the `app` object from Task 1.
- Produces: `queries.fetch_competitor_history(conn, locality_id=None, platform=None) -> list[dict]`,
  `queries.fetch_competitor_summary(conn) -> list[dict]`, `models.ShelfSnapshot`,
  `models.CompetitorSummaryRow`.

- [ ] **Step 1: Write the failing tests**

Add to `web/api/test_api.py`:
```python
@requires_db
def test_get_competitor_history_filters_by_locality_and_platform():
    conn = get_connection()
    locality_id = None
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "Yoga Bar", 399, False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        response = client.get(
            f"/api/competitor/history?locality_id={locality_id}&platform=test_platform_xyz"
        )
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["brand_searched"] == "Yoga Bar"

        empty = client.get(f"/api/competitor/history?locality_id={locality_id}&platform=zepto")
        assert empty.json() == []
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()


@requires_db
def test_get_competitor_summary_reflects_latest_run_only():
    conn = get_connection()
    locality_id = None
    old_run_id = None
    new_run_id = None
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '1 day') RETURNING scrape_run_id",
                ("test_platform_xyz", "old.xlsx"),
            )
            old_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (old_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "Old Brand", 199, False),
            )
            snapshot_ids.append(cur.fetchone()[0])

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) VALUES (%s, %s, now()) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz", "new.xlsx"),
            )
            new_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, locality_id, city_raw, locality_raw, "
                "brand_searched, selling_price, is_goat) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING shelf_snapshot_id",
                (new_run_id, "test_platform_xyz", locality_id, "TestCityXYZ", "TestLocalityXYZ",
                 "New Brand", 299, False),
            )
            snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get("/api/competitor/summary")
        assert response.status_code == 200
        row = next(r for r in response.json() if r["locality_id"] == locality_id)
        assert row["n_competitor_brands"] == 1
        assert row["competitor_avg_price"] == 299.0
        assert row["goat_present"] is False
    finally:
        with conn.cursor() as cur:
            if snapshot_ids:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            if old_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (old_run_id,))
            if new_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (new_run_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()
```

`test_platform_xyz` (not a real platform name like `blinkit`/`zepto`/`swiggy`) is deliberate: the summary
query picks the single latest `scrape_run_id` per platform globally, so using a real platform name here
would briefly perturb what `/api/competitor/summary` returns for that platform's real localities for the
duration of the test transaction. A fake platform name sidesteps that entirely.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_api.py -v -k competitor`
Expected: FAIL with `AttributeError` or 404 (routes don't exist yet)

- [ ] **Step 3: Add the query functions**

Add to `web/api/queries.py`:
```python
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
```

Add near the top of `web/api/queries.py`, next to the existing `from psycopg2.extras import RealDictCursor`
import (no new import needed — `RealDictCursor` is already imported from Task 1).

- [ ] **Step 4: Add the response models**

Add to `web/api/models.py`:
```python
class ShelfSnapshot(BaseModel):
    shelf_snapshot_id: int
    platform: str
    locality_id: Optional[int] = None
    city_raw: str
    locality_raw: str
    brand_searched: Optional[str] = None
    rank: Optional[int] = None
    product_name: Optional[str] = None
    pack_size: Optional[str] = None
    selling_price: Optional[float] = None
    mrp: Optional[float] = None
    discount_pct: Optional[float] = None
    stock_left: Optional[str] = None
    rating: Optional[str] = None
    reviews: Optional[str] = None
    sponsored: Optional[bool] = None
    serviceable: Optional[str] = None
    is_goat: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CompetitorSummaryRow(BaseModel):
    locality_id: int
    platform: str
    n_competitor_brands: int
    competitor_avg_price: Optional[float] = None
    goat_present: bool
```

Note: `selling_price`, `mrp`, `discount_pct`, and `competitor_avg_price` come back from psycopg2 as
`Decimal` (Postgres `NUMERIC` columns) — Pydantic coerces `Decimal` to `float` automatically for these
fields, no manual conversion needed.

- [ ] **Step 5: Add the routes**

Add to `web/api/index.py`, after the `get_belts` route:
```python
from typing import Optional

from fastapi import Query

from models import CompetitorSummaryRow, ShelfSnapshot


@app.get("/api/competitor/history", response_model=list[ShelfSnapshot])
def get_competitor_history(
    locality_id: Optional[int] = Query(default=None),
    platform: Optional[str] = Query(default=None),
):
    conn = get_connection()
    try:
        return queries.fetch_competitor_history(conn, locality_id=locality_id, platform=platform)
    finally:
        conn.close()


@app.get("/api/competitor/summary", response_model=list[CompetitorSummaryRow])
def get_competitor_summary():
    conn = get_connection()
    try:
        return queries.fetch_competitor_summary(conn)
    finally:
        conn.close()
```

Place the two new imports (`from typing import Optional`, `from fastapi import Query`) and the
`from models import ...` addition at the top of the file, alongside the existing imports — don't leave
imports mid-file. The updated top of `web/api/index.py` should read:
```python
import logging
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

import queries
from db import get_connection
from models import Belt, CompetitorSummaryRow, Locality, ShelfSnapshot
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web/api && python -m pytest -v`
Expected: PASS (9 passed)

- [ ] **Step 7: Commit**

```bash
git add web/api/queries.py web/api/models.py web/api/index.py web/api/test_api.py
git commit -m "feat: add competitor history and summary endpoints"
```

---

### Task 3: `/api/annotations` (GET + POST)

**Files:**
- Modify: `web/api/queries.py`
- Modify: `web/api/models.py`
- Modify: `web/api/index.py`
- Modify: `web/api/test_api.py`

**Interfaces:**
- Consumes: `db.get_connection()`, the `app` object.
- Produces: `queries.fetch_annotations(conn, locality_id=None) -> list[dict]`,
  `queries.insert_annotation(conn, locality_id, note, status, budget_note) -> dict`,
  `models.Annotation`, `models.AnnotationCreate`.

- [ ] **Step 1: Write the failing tests**

Add to `web/api/test_api.py`:
```python
@requires_db
def test_post_annotation_creates_row_and_get_lists_it():
    conn = get_connection()
    locality_id = None
    annotation_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO localities (loc_key, area, city) VALUES (%s, %s, %s) RETURNING locality_id",
                ("testcityxyz|testlocalityxyz", "TestLocalityXYZ", "TestCityXYZ"),
            )
            locality_id = cur.fetchone()[0]
        conn.commit()

        response = client.post("/api/annotations", json={
            "locality_id": locality_id, "note": "Launched pop-up", "status": "launched",
            "budget_note": 15000,
        })
        assert response.status_code == 201
        body = response.json()
        annotation_id = body["annotation_id"]
        assert body["note"] == "Launched pop-up"
        assert body["status"] == "launched"

        list_response = client.get(f"/api/annotations?locality_id={locality_id}")
        assert list_response.status_code == 200
        notes = [a["note"] for a in list_response.json()]
        assert "Launched pop-up" in notes
    finally:
        with conn.cursor() as cur:
            if annotation_id is not None:
                cur.execute("DELETE FROM locality_annotations WHERE annotation_id = %s", (annotation_id,))
            if locality_id is not None:
                cur.execute("DELETE FROM localities WHERE locality_id = %s", (locality_id,))
        conn.commit()
        conn.close()


@requires_db
def test_post_annotation_returns_404_for_unknown_locality():
    response = client.post("/api/annotations", json={"locality_id": 999999999, "note": "x"})
    assert response.status_code == 404
    assert response.json() == {"detail": "locality not found"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_api.py -v -k annotation`
Expected: FAIL with 404 (routes don't exist yet)

- [ ] **Step 3: Add the query functions**

Add to `web/api/queries.py`:
```python
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
```

- [ ] **Step 4: Add the models**

Add to `web/api/models.py`:
```python
class Annotation(BaseModel):
    annotation_id: int
    locality_id: int
    note: Optional[str] = None
    status: Optional[str] = None
    budget_note: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class AnnotationCreate(BaseModel):
    locality_id: int
    note: Optional[str] = None
    status: Optional[str] = None
    budget_note: Optional[float] = None
```

- [ ] **Step 5: Add the routes**

Add to `web/api/index.py`:
```python
import psycopg2.errors
from fastapi import HTTPException

from models import Annotation, AnnotationCreate


@app.get("/api/annotations", response_model=list[Annotation])
def get_annotations(locality_id: Optional[int] = Query(default=None)):
    conn = get_connection()
    try:
        return queries.fetch_annotations(conn, locality_id=locality_id)
    finally:
        conn.close()


@app.post("/api/annotations", response_model=Annotation, status_code=201)
def create_annotation(body: AnnotationCreate):
    conn = get_connection()
    try:
        try:
            return queries.insert_annotation(
                conn, body.locality_id, body.note, body.status, body.budget_note
            )
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise HTTPException(status_code=404, detail="locality not found")
    finally:
        conn.close()
```

Fold the new imports into the top-of-file import block. After this step, the top of `web/api/index.py`
should read exactly:
```python
import logging
from typing import Optional

import psycopg2.errors
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

import queries
from db import get_connection
from models import Annotation, AnnotationCreate, Belt, CompetitorSummaryRow, Locality, ShelfSnapshot
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web/api && python -m pytest -v`
Expected: PASS (11 passed)

- [ ] **Step 7: Commit**

```bash
git add web/api/queries.py web/api/models.py web/api/index.py web/api/test_api.py
git commit -m "feat: add annotations endpoints (GET list, POST insert-only)"
```

---

### Task 4: `/api/meta/freshness`

**Files:**
- Modify: `web/api/queries.py`
- Modify: `web/api/models.py`
- Modify: `web/api/index.py`
- Modify: `web/api/test_api.py`

**Interfaces:**
- Consumes: `db.get_connection()`, the `app` object.
- Produces: `queries.fetch_freshness(conn) -> dict`, `models.Freshness`.

- [ ] **Step 1: Write the failing test**

Add to `web/api/test_api.py`:
```python
@requires_db
def test_get_freshness_reflects_latest_timestamps():
    conn = get_connection()
    pipeline_run_id = None
    scrape_run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pipeline_runs (source_parquet_filename, row_count, triggered_at) "
                "VALUES (%s, %s, now()) RETURNING pipeline_run_id",
                ("test.parquet", 1),
            )
            pipeline_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at, finished_at) "
                "VALUES (%s, %s, now(), now()) RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
        conn.commit()

        response = client.get("/api/meta/freshness")
        assert response.status_code == 200
        body = response.json()
        assert body["last_pipeline_run"] is not None
        assert "test_platform_xyz" in body["last_scrape_by_platform"]
    finally:
        with conn.cursor() as cur:
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
            if pipeline_run_id is not None:
                cur.execute("DELETE FROM pipeline_runs WHERE pipeline_run_id = %s", (pipeline_run_id,))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/api && python -m pytest test_api.py -v -k freshness`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add the query function**

Add to `web/api/queries.py`:
```python
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
```

- [ ] **Step 4: Add the model**

Add to `web/api/models.py`:
```python
class Freshness(BaseModel):
    last_pipeline_run: Optional[datetime] = None
    last_scrape_by_platform: dict[str, Optional[datetime]]
```

- [ ] **Step 5: Add the route**

Add to `web/api/index.py`:
```python
from models import Freshness


@app.get("/api/meta/freshness", response_model=Freshness)
def get_freshness():
    conn = get_connection()
    try:
        return queries.fetch_freshness(conn)
    finally:
        conn.close()
```

Fold `Freshness` into the existing `from models import ...` line at the top of the file rather than adding
a second import line. After this step, the top of `web/api/index.py` should read exactly:
```python
import logging
from typing import Optional

import psycopg2.errors
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

import queries
from db import get_connection
from models import (
    Annotation, AnnotationCreate, Belt, CompetitorSummaryRow, Freshness, Locality, ShelfSnapshot,
)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web/api && python -m pytest -v`
Expected: PASS (12 passed)

- [ ] **Step 7: Commit**

```bash
git add web/api/queries.py web/api/models.py web/api/index.py web/api/test_api.py
git commit -m "feat: add meta/freshness endpoint"
```

---

### Task 5: Vercel deployment wiring

**Files:**
- Modify: `web/vercel.json`

**Interfaces:**
- Consumes: `web/api/index.py`'s `app` object (Task 1-4, complete).
- Produces: nothing other tasks depend on — this is the deployment leaf.

- [ ] **Step 1: Add the API rewrite**

Read the current `web/vercel.json` (from Sprint 2's Bash exploration, it is
`{ "cleanUrls": true, "outputDirectory": "." }`). Replace it with:
```json
{
  "cleanUrls": true,
  "outputDirectory": ".",
  "rewrites": [
    { "source": "/api/:path*", "destination": "/api/index" }
  ]
}
```

- [ ] **Step 2: Verify locally one more time with the full route set**

Run: `cd web/api && uvicorn index:app --reload` in one terminal, then in another:
```bash
curl http://127.0.0.1:8000/api/localities | head -c 200
curl http://127.0.0.1:8000/api/belts | head -c 200
curl http://127.0.0.1:8000/api/competitor/summary | head -c 200
curl http://127.0.0.1:8000/api/meta/freshness
```
Expected: each returns a 200 with JSON (empty array `[]` is fine if no data matches — this is confirming
routing and DB connectivity, not specific content). Stop the `uvicorn` process after confirming.

- [ ] **Step 3: Commit**

```bash
git add web/vercel.json
git commit -m "feat: wire /api/* rewrite for the FastAPI serverless function"
```

- [ ] **Step 4: Add DATABASE_URL as a Vercel environment variable (manual, one-time)**

This cannot be automated from this environment (no Vercel CLI is installed, no linked `.vercel/project.json`
in this repo, and environment variables require either the Vercel dashboard or an authenticated `vercel`
CLI). Do this manually:

1. Go to the GOAT Life project on `https://vercel.com/dashboard` → **Settings** → **Environment Variables**.
2. Add a new variable: Name `DATABASE_URL`, Value = the same pooled Neon connection string from your local
   `.env` file. Apply it to the **Production** environment (and **Preview** too, if you want preview
   deployments to hit the same live DB — otherwise preview deploys will 500 on every DB-backed route).
3. Save.

- [ ] **Step 5: Push and verify the deployment (manual)**

```bash
git push
```

Vercel's GitHub integration auto-deploys on push (same as the existing static site). Once the deploy
finishes (check the Vercel dashboard's Deployments tab for a green checkmark), confirm the live API:
```bash
curl https://<your-vercel-domain>/api/meta/freshness
```
Expected: a 200 response with real `last_pipeline_run`/`last_scrape_by_platform` timestamps matching what
you saw when verifying the Sprint 2 GitHub Actions sync. This step needs the Step 4 environment variable
already set and a human to confirm the deploy went green — it cannot be verified by an automated
implementer.

---

## Self-Review Notes

**Spec coverage:** All six endpoints from the design doc's table are covered — Task 1 (`/api/localities`,
`/api/belts`), Task 2 (`/api/competitor/history`, `/api/competitor/summary`), Task 3
(`/api/annotations` GET+POST), Task 4 (`/api/meta/freshness`). The design doc's architecture section
(file layout, snake_case naming, raw psycopg2, no pandas, `requires_db` test convention, error-handling
defaults) is fully reflected: `web/api/{db,models,queries,index}.py` matches the planned layout exactly,
every model uses snake_case fields, every query function takes a plain `conn` and uses raw SQL, no task
adds `pandas`/`numpy` to `requirements.txt`, every DB-touching test uses the `requires_db` marker with
`TestLocalityXYZ`-prefixed rows and explicit cleanup, and the global exception handler (tested in Task 1)
implements the "log real error, return generic 500" requirement. Task 5 covers the Vercel deployment wiring
and the two manual steps (environment variable, push+verify) that mirror Sprint 2's GitHub Actions secret
pattern.

**Placeholder scan:** no TBD/TODO. Every step shows complete, runnable code — SQL strings are the actual
SQL, not descriptions of SQL; test fixtures insert real rows with real cleanup, not "add appropriate test
data."

**Type consistency:** `fetch_localities`, `compute_belts`, `fetch_competitor_history`,
`fetch_competitor_summary`, `fetch_annotations`, `insert_annotation`, `fetch_freshness` are each defined
once (Tasks 1-4) and consumed by exactly the route in `index.py` that the same task adds — no task calls a
query function a later task hasn't defined yet, and no task redefines a function an earlier task already
created (each is a `queries.py`/`models.py` *addition*, appending to files Task 1 created). `get_connection`
signature (`() -> psycopg2.connection`, no arguments) is identical everywhere it's called across all five
tasks.
