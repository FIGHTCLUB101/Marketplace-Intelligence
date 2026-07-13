# Sprint 5 — Shelf Monitor API + Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Sprint 4's shelf change-detection logic visible on the live dashboard — two new FastAPI endpoints (`/api/shelf/changes`, `/api/shelf/trends`) and a new "Shelf Monitor" tab that renders them, following this repo's existing self-serve/no-build conventions exactly.

**Architecture:** `scripts/shelf_changes.py` (Sprint 4, zero imports) is duplicated into `web/api/shelf_changes.py` — the same "duplicate across the Vercel bundle boundary" pattern `web/api/db.py` already uses for `scripts/db_connection.py`, so the serverless function never reaches outside `web/api/`. New query functions are appended to the existing `web/api/queries.py` (matching how Sprint 3 grew that file feature-by-feature), new response models appended to `web/api/models.py`, two new routes appended to `web/api/index.py`. The frontend is a new `web/shelf-monitor.js` module wired into `app.js`/`state.js`/`index.html` exactly the way the (separate, not-yet-merged) margin-calculator branch wired in `margin.js` — same lazy-render-on-tab-click pattern, same vanilla-JS-no-build-step approach.

**Tech Stack:** Python (FastAPI, psycopg2, Pydantic — no new dependencies), vanilla JS (ES modules, no bundler, no charting library — see Task 5's reasoning for why trends render as a table, not a chart, in this sprint).

## Global Constraints

- **Sequencing dependency, not yet resolved:** the `worktree-margin-calculator-wiring` branch (already committed, tests passing) also modifies `web/index.html`, `web/app.js`, `web/state.js`, and `web/styles.css`. This plan's Task 6 modifies the same four files. Whichever branch merges to `main` second will need a trivial manual reconciliation (two new `<button class="tab">` lines instead of one, two new `<section>` blocks, two new lazy-render `if` lines, two blocks of new CSS) — not a logical conflict, just a textual one. Recommend merging the margin branch first since it's smaller and already fully verified; this plan does not depend on it being merged, either order works.
- No `tenant_id` anywhere — this project stays deliberately single-tenant (per the decision recorded in Sprint 4's plan).
- `web/api/requirements.txt` stays free of `pandas`/`numpy` — all new query functions return plain dicts via `psycopg2.extras.RealDictCursor`, matching every existing function in `web/api/queries.py`.
- `web/api/` remains self-contained: no `import` reaching into `scripts/` or `scraper/`. `web/api/shelf_changes.py` is a duplicate file, not a shared import — the same choice already made for `db.py`.
- Default platform for both new endpoints is `"blinkit_goatlife"` (Sprint 4's scope) — callers can override via `?platform=`, but the frontend tab only ever calls the default for now.
- Existing test/import convention: tests live alongside code in `web/api/`, run via `cd web/api && python -m pytest -q`; `@requires_db` tests use the `pytest.mark.skipif(not os.environ.get("DATABASE_URL"), ...)` pattern already used by every other `web/api/test_*.py` file, with `test_platform_xyz`-prefixed fixture rows and **full cleanup of every row inserted, including `scrape_runs` parent rows** — the exact discipline Sprint 4 had to retrofit after Sprint 1 left orphaned rows in production.
- Frontend tests follow the existing convention: pure, DOM-free helper functions get real `node --test` coverage (matching `sequence.js`'s `assignWave`/`buildSequence` and `margin.js`'s `calcEconomics`/`getVerdict`); DOM-rendering code stays untested, matching `views.js`.
- No new CSS token/class collides with the margin branch's additions (`.info`, `.stat-label`, `.stat-val`, `.verdict-badge`, `.field`, `--radius`, `--go`) — this plan's new classes (`.severity-banner`, `.alert-row`, `.narrative`) are distinctly named, so no collision regardless of merge order.

---

### Task 1: Duplicate `shelf_changes.py` into `web/api/` and add its Postgres access layer to `queries.py`

**Files:**
- Create: `web/api/shelf_changes.py`
- Modify: `web/api/queries.py`
- Test: `web/api/test_shelf_changes.py` (new)
- Test: `web/api/test_queries.py` (modify — append)

**Interfaces:**
- Produces: `shelf_changes.detect_changes`, `shelf_changes.generate_narrative_summary`, `shelf_changes.goat_gone_unique` (byte-identical to `scripts/shelf_changes.py`); `queries.fetch_latest_two_scrape_run_ids(conn, platform)`, `queries.fetch_snapshot_rows(conn, scrape_run_id)`, `queries.fetch_drop_calendar(conn)` (byte-identical logic to `scripts/queries_shelf.py`, added to the existing `web/api/queries.py` file rather than a new file). Consumed by Task 3.

- [ ] **Step 1: Copy the pure logic module verbatim**

Read `scripts/shelf_changes.py` in full (already merged to `main` via Sprint 4) and create `web/api/shelf_changes.py` with **identical content** — same docstring, same functions (`build_shelf_snapshot`, `not_serviceable_localities`, `_is_goat_lookup`, `detect_changes`, `goat_gone_unique`, `generate_narrative_summary`), same `PLACEHOLDER_NAMES` constant. This file has zero imports in the source — confirm the copy has zero imports too.

- [ ] **Step 2: Write the failing tests for the copy**

Create `web/api/test_shelf_changes.py`:
```python
from shelf_changes import build_shelf_snapshot, detect_changes, generate_narrative_summary, goat_gone_unique


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {"rank": 1, "price": 119.0}


def test_detect_changes_goat_displaced():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["goat_displaced"]) == 1
    assert changes["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"


def test_goat_gone_unique_excludes_already_displaced():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life X", "now": "MISSING"}],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                            "product": "GOAT Life X", "is_goat": True}],
    }
    assert goat_gone_unique(changes) == []


def test_generate_narrative_summary_all_clear():
    changes = {"goat_displaced": [], "rank_intrusions": [], "gone_products": []}
    result = generate_narrative_summary(changes)
    assert "holds ranks 1-4" in result[0]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_shelf_changes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shelf_changes'`

- [ ] **Step 4: Run tests to verify they pass (after Step 1's copy)**

Run: `cd web/api && python -m pytest test_shelf_changes.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Add the query functions to `web/api/queries.py`**

Append to `web/api/queries.py` (after the existing `fetch_freshness` function, at the end of the file):
```python

SHELF_LATEST_TWO_RUNS_SQL = """
    SELECT scrape_run_id FROM scrape_runs WHERE platform = %s
    ORDER BY started_at DESC LIMIT 2
"""


def fetch_latest_two_scrape_run_ids(conn, platform):
    """Returns (newest_id, second_newest_id). second_newest_id is None if
    only one run exists for this platform; both are None if zero exist."""
    with conn.cursor() as cur:
        cur.execute(SHELF_LATEST_TWO_RUNS_SQL, (platform,))
        ids = [row[0] for row in cur.fetchall()]
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


def fetch_drop_calendar(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT sku_name FROM sku_drop_calendar")
        return {row[0] for row in cur.fetchall()}
```

- [ ] **Step 6: Write the failing tests for the query functions**

Append to `web/api/test_queries.py`:
```python
import os

import pytest

from db import get_connection
from queries import fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_snapshot_rows

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB test",
)


@requires_db
def test_fetch_latest_two_scrape_run_ids_orders_by_started_at_desc():
    conn = get_connection()
    run_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '2 days') RETURNING scrape_run_id",
                ("test_platform_xyz", "old.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now()) RETURNING scrape_run_id",
                ("test_platform_xyz", "new.xlsx"),
            )
            run_ids.append(cur.fetchone()[0])
        conn.commit()

        newest, second = fetch_latest_two_scrape_run_ids(conn, "test_platform_xyz")
        assert newest == run_ids[1]
        assert second == run_ids[0]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_snapshot_rows_returns_expected_columns():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz", "TestCityXYZ", "TestLocalityXYZ",
                 "GOAT Life Mocha Marvel", 1, 119.0, True),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        rows = fetch_snapshot_rows(conn, scrape_run_id)
        assert len(rows) == 1
        assert rows[0]["product_name"] == "GOAT Life Mocha Marvel"
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_drop_calendar_returns_paused_skus():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sku_drop_calendar (sku_name) VALUES (%s) "
                "ON CONFLICT (sku_name) DO NOTHING",
                ("TestSkuXYZ",),
            )
        conn.commit()
        assert "TestSkuXYZ" in fetch_drop_calendar(conn)
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sku_drop_calendar WHERE sku_name = %s", ("TestSkuXYZ",))
        conn.commit()
        conn.close()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd web/api && python -m pytest test_shelf_changes.py test_queries.py -v`
Expected: PASS (all previous `test_queries.py` tests plus the 3 new ones; the 3 new ones report PASSED if `DATABASE_URL` is set, SKIPPED otherwise)

- [ ] **Step 8: Commit**

```bash
git add web/api/shelf_changes.py web/api/queries.py web/api/test_shelf_changes.py web/api/test_queries.py
git commit -m "feat: duplicate shelf_changes.py into web/api, add its Postgres access layer"
```

---

### Task 2: Response models for shelf changes and trends

**Files:**
- Modify: `web/api/models.py`

**Interfaces:**
- Produces: `models.GoatDisplaced`, `models.RankIntrusion`, `models.ProductEvent`, `models.RankMoved`, `models.PriceChange`, `models.ShelfChanges`, `models.TrendSeries`, `models.ShelfTrends`. Consumed by Task 3 and Task 4.

- [ ] **Step 1: Append the models**

Append to `web/api/models.py` (after the existing `Freshness` class):
```python


class GoatDisplaced(BaseModel):
    city: str
    locality: str
    rank: int
    was: str
    now: str


class RankIntrusion(BaseModel):
    city: str
    locality: str
    rank: int
    intruder: str


class ProductEvent(BaseModel):
    """Shape shared by new_products and gone_products entries — gone_products
    additionally carries is_goat, new_products never does."""
    city: str
    locality: str
    rank: Optional[int] = None
    product: str
    is_goat: Optional[bool] = None


class RankMoved(BaseModel):
    city: str
    locality: str
    product: str
    old_rank: int
    new_rank: int
    is_goat: bool


class PriceChange(BaseModel):
    city: str
    locality: str
    product: str
    old_price: float
    new_price: float
    change: float


class ShelfChanges(BaseModel):
    platform: str
    status: str
    new_run_id: Optional[int] = None
    old_run_id: Optional[int] = None
    narrative: list[str]
    goat_displaced: list[GoatDisplaced] = []
    rank_intrusions: list[RankIntrusion] = []
    goat_gone: list[ProductEvent] = []
    new_products: list[ProductEvent] = []
    gone_products: list[ProductEvent] = []
    rank_moved: list[RankMoved] = []
    price_changes: list[PriceChange] = []


class TrendSeries(BaseModel):
    product_name: str
    is_goat: bool
    data: list[Optional[float]]


class ShelfTrends(BaseModel):
    platform: str
    weeks: list[str]
    series: list[TrendSeries]
```

- [ ] **Step 2: Verify the file still imports cleanly**

Run: `cd web/api && python -c "import models; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add web/api/models.py
git commit -m "feat: add response models for shelf changes and trends"
```

---

### Task 3: `GET /api/shelf/changes`

**Files:**
- Modify: `web/api/index.py`
- Modify: `web/api/test_api.py`

**Interfaces:**
- Consumes: `shelf_changes.detect_changes`, `shelf_changes.generate_narrative_summary`, `shelf_changes.goat_gone_unique` (Task 1); `queries.fetch_latest_two_scrape_run_ids`, `queries.fetch_snapshot_rows`, `queries.fetch_drop_calendar` (Task 1); `models.ShelfChanges` (Task 2).
- Produces: `GET /api/shelf/changes?platform=<str>`. No other task depends on this route directly.

- [ ] **Step 1: Write the failing tests**

Append to `web/api/test_api.py`:
```python
@requires_db
def test_get_shelf_changes_reports_insufficient_history_with_zero_runs():
    response = client.get("/api/shelf/changes?platform=test_platform_xyz_empty")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_history"
    assert body["new_run_id"] is None


@requires_db
def test_get_shelf_changes_detects_goat_displaced_between_two_runs():
    conn = get_connection()
    run_ids = []
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now() - interval '7 days') RETURNING scrape_run_id",
                ("test_platform_xyz_changes", "old.xlsx"),
            )
            old_run_id = cur.fetchone()[0]
            run_ids.append(old_run_id)
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (old_run_id, "test_platform_xyz_changes", "TestCityXYZ", "TestLocalityXYZ",
                 "GOAT Life Mocha Marvel", 1, 119.0, True),
            )
            snapshot_ids.append(cur.fetchone()[0])

            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now()) RETURNING scrape_run_id",
                ("test_platform_xyz_changes", "new.xlsx"),
            )
            new_run_id = cur.fetchone()[0]
            run_ids.append(new_run_id)
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "product_name, rank, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (new_run_id, "test_platform_xyz_changes", "TestCityXYZ", "TestLocalityXYZ",
                 "Prustlr Discovery Protein Oats", 1, 449.0, False),
            )
            snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        response = client.get("/api/shelf/changes?platform=test_platform_xyz_changes")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["old_run_id"] == old_run_id
        assert body["new_run_id"] == new_run_id
        assert len(body["goat_displaced"]) == 1
        assert body["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_api.py -v -k shelf_changes`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add the route**

Add to `web/api/index.py`, after the existing `get_freshness` route. First, extend the `from models import (...)` block at the top of the file to include the new models, and add a `shelf_changes` import:
```python
import shelf_changes
from models import (
    Annotation, AnnotationCreate, Belt, CompetitorSummaryRow, Freshness, GoatDisplaced,
    Locality, PriceChange, ProductEvent, RankIntrusion, RankMoved, ShelfChanges, ShelfTrends,
    TrendSeries,
)
```
(`GoatDisplaced`, `PriceChange`, `ProductEvent`, `RankIntrusion`, `RankMoved`, `TrendSeries` are imported here for completeness even though only `ShelfChanges`/`ShelfTrends` are referenced directly as `response_model=` values — FastAPI resolves the nested list types from `ShelfChanges`'/`ShelfTrends`' own field annotations, so the sub-models don't need separate route-level references, but importing them keeps `models.py`'s public surface visible from `index.py` the same way `Locality`/`Belt` already are.)

Then add the route:
```python
@app.get("/api/shelf/changes", response_model=ShelfChanges)
def get_shelf_changes(platform: str = Query(default="blinkit_goatlife")):
    conn = get_connection()
    try:
        newest_id, second_id = queries.fetch_latest_two_scrape_run_ids(conn, platform)
        if second_id is None:
            return {
                "platform": platform, "status": "insufficient_history",
                "narrative": ["First week of tracking — no prior week to compare against yet."],
            }
        rows_new = queries.fetch_snapshot_rows(conn, newest_id)
        rows_old = queries.fetch_snapshot_rows(conn, second_id)
        drop_calendar = queries.fetch_drop_calendar(conn)
    finally:
        conn.close()

    changes = shelf_changes.detect_changes(rows_new, rows_old, drop_calendar=drop_calendar)
    narrative = shelf_changes.generate_narrative_summary(changes)
    return {
        "platform": platform, "status": "ok",
        "new_run_id": newest_id, "old_run_id": second_id,
        "narrative": narrative,
        "goat_displaced": changes["goat_displaced"],
        "rank_intrusions": changes["rank_intrusions"],
        "goat_gone": shelf_changes.goat_gone_unique(changes),
        "new_products": changes["new_products"],
        "gone_products": changes["gone_products"],
        "rank_moved": changes["rank_moved"],
        "price_changes": changes["price_changes"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web/api && python -m pytest test_api.py -v -k shelf_changes`
Expected: PASS (2 passed, or SKIPPED if `DATABASE_URL` is unset)

- [ ] **Step 5: Run the full `web/api` suite once**

Run: `cd web/api && python -m pytest -q`
Expected: all tests pass, no regressions in the pre-existing routes.

- [ ] **Step 6: Commit**

```bash
git add web/api/index.py web/api/test_api.py
git commit -m "feat: add GET /api/shelf/changes endpoint"
```

---

### Task 4: `GET /api/shelf/trends`

**Files:**
- Modify: `web/api/queries.py`
- Modify: `web/api/index.py`
- Modify: `web/api/test_queries.py`
- Modify: `web/api/test_api.py`

**Interfaces:**
- Consumes: `models.ShelfTrends` (Task 2).
- Produces: `queries.fetch_shelf_trends(conn, platform, top_n=3) -> dict`, `GET /api/shelf/trends?platform=<str>`.

- [ ] **Step 1: Write the failing test for the query function**

Append to `web/api/test_queries.py`:
```python
@requires_db
def test_fetch_shelf_trends_includes_goat_and_top_competitor():
    conn = get_connection()
    run_ids = []
    snapshot_ids = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file, started_at) "
                "VALUES (%s, %s, now()) RETURNING scrape_run_id",
                ("test_platform_xyz_trends", "week1.xlsx"),
            )
            run_id = cur.fetchone()[0]
            run_ids.append(run_id)
            for name, rank, is_goat in [
                ("GOAT Life Mocha Marvel", 1, True),
                ("Prustlr Discovery Protein Oats", 5, False),
            ]:
                cur.execute(
                    "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                    "product_name, rank, selling_price, is_goat) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                    (run_id, "test_platform_xyz_trends", "TestCityXYZ", "TestLocalityXYZ",
                     name, rank, 119.0, is_goat),
                )
                snapshot_ids.append(cur.fetchone()[0])
        conn.commit()

        result = fetch_shelf_trends(conn, "test_platform_xyz_trends", top_n=3)
        assert len(result["weeks"]) == 1
        names = {s["product_name"] for s in result["series"]}
        assert "GOAT Life Mocha Marvel" in names
        assert "Prustlr Discovery Protein Oats" in names
        goat_series = next(s for s in result["series"] if s["product_name"] == "GOAT Life Mocha Marvel")
        assert goat_series["is_goat"] is True
        assert goat_series["data"] == [1.0]
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = ANY(%s)", (snapshot_ids,))
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()
```
Add `fetch_shelf_trends` to the existing `from queries import (...)` import line at the top of `web/api/test_queries.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/api && python -m pytest test_queries.py -v -k trends`
Expected: FAIL with `ImportError: cannot import name 'fetch_shelf_trends'`

- [ ] **Step 3: Add `fetch_shelf_trends` to `web/api/queries.py`**

Append to `web/api/queries.py`:
```python

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/api && python -m pytest test_queries.py -v -k trends`
Expected: PASS (1 passed, or SKIPPED if `DATABASE_URL` is unset)

- [ ] **Step 5: Write the failing test for the route**

Append to `web/api/test_api.py`:
```python
def test_get_shelf_trends_returns_empty_series_for_unknown_platform():
    response = client.get("/api/shelf/trends?platform=test_platform_xyz_no_data")
    assert response.status_code == 200
    body = response.json()
    assert body["weeks"] == []
    assert body["series"] == []
```
(This test needs no `@requires_db` marker and no fixture data — an unknown platform legitimately returns empty lists, which is a real code path worth locking in, and it exercises the live route without requiring any live rows, so it runs even when `DATABASE_URL` is unset only if `get_connection()` itself doesn't require a live DB to construct — check this: if `DATABASE_URL` is unset, `get_connection()` still raises `RuntimeError` before any query runs, so this test in practice also needs `DATABASE_URL` set to reach the empty-result path; mark it `@requires_db` like every other DB-touching test in this file for consistency.)

- [ ] **Step 6: Add the route**

Add to `web/api/index.py`, after `get_shelf_changes`:
```python
@app.get("/api/shelf/trends", response_model=ShelfTrends)
def get_shelf_trends(platform: str = Query(default="blinkit_goatlife")):
    conn = get_connection()
    try:
        return queries.fetch_shelf_trends(conn, platform)
    finally:
        conn.close()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd web/api && python -m pytest test_api.py test_queries.py -v -k trends`
Expected: PASS

- [ ] **Step 8: Run the full `web/api` suite once**

Run: `cd web/api && python -m pytest -q`
Expected: all tests pass, no regressions.

- [ ] **Step 9: Commit**

```bash
git add web/api/queries.py web/api/index.py web/api/test_queries.py web/api/test_api.py
git commit -m "feat: add GET /api/shelf/trends endpoint"
```

---

### Task 5: `web/shelf-monitor.js` — pure helpers + render logic

**Files:**
- Create: `web/shelf-monitor.js`
- Create: `web/tests/shelf-monitor.test.js`

**Interfaces:**
- Produces: `severityFor(changes) -> 'critical'|'warning'|'clear'`, `formatTrendRows(trends) -> [{label, isGoat, cells}]` (both pure, tested), `AppState.initShelfMonitor` (a render function, assigned as a side effect on module load — mirrors `margin.js`'s exact `AppState.initMargin = render` pattern). Consumed by Task 6.

**Why trends render as a table, not a chart, in this sprint:** there is currently exactly one scrape_run for the `blinkit_goatlife` platform in production (confirmed live during Sprint 4 planning) — a line chart with one data point communicates nothing a table doesn't, and this repo has zero charting dependency today (`MapLibre` is the only external UI library, loaded via CDN for the map specifically). Introducing a charting library now, before there's more than one week of real history to plot, is speculative. A plain HTML table (using the same `.lb` table class the Leaderboard tab already defines in `styles.css`) shows the same information today and remains genuinely useful once more weeks accumulate — revisit a real chart in a later sprint once that's true.

- [ ] **Step 1: Write the failing tests**

Create `web/tests/shelf-monitor.test.js`:
```js
import { test } from 'node:test';
import assert from 'node:assert';
import { formatTrendRows, severityFor } from '../shelf-monitor.js';

test('severityFor: critical when goat_displaced or goat_gone non-empty', () => {
  assert.equal(severityFor({ goat_displaced: [{}], goat_gone: [], rank_intrusions: [] }), 'critical');
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [{}], rank_intrusions: [] }), 'critical');
});

test('severityFor: warning when only rank_intrusions non-empty', () => {
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [], rank_intrusions: [{}] }), 'warning');
});

test('severityFor: clear when everything empty', () => {
  assert.equal(severityFor({ goat_displaced: [], goat_gone: [], rank_intrusions: [] }), 'clear');
});

test('formatTrendRows maps weeks to cells, using — for missing data points', () => {
  const trends = {
    weeks: ['2026-07-06', '2026-07-13'],
    series: [
      { product_name: 'GOAT Life Mocha Marvel', is_goat: true, data: [1.0, null] },
      { product_name: 'Prustlr Discovery Protein Oats', is_goat: false, data: [null, 5.0] },
    ],
  };
  const rows = formatTrendRows(trends);
  assert.deepEqual(rows[0], { label: 'GOAT Life Mocha Marvel', isGoat: true, cells: [1.0, '—'] });
  assert.deepEqual(rows[1], { label: 'Prustlr Discovery Protein Oats', isGoat: false, cells: ['—', 5.0] });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: FAIL — cannot find module `../shelf-monitor.js`

- [ ] **Step 3: Write the implementation**

Create `web/shelf-monitor.js`:
```js
import AppState from './state.js';

export function severityFor(changes) {
  if (changes.goat_displaced.length + changes.goat_gone.length > 0) return 'critical';
  if (changes.rank_intrusions.length > 0) return 'warning';
  return 'clear';
}

const SEVERITY_LABEL = { critical: 'GOAT LIFE SHELF DISRUPTED', warning: 'CHANGES DETECTED', clear: 'ALL CLEAR' };

export function formatTrendRows(trends) {
  return trends.series.map((s) => ({
    label: s.product_name,
    isGoat: s.is_goat,
    cells: trends.weeks.map((_, i) => (s.data[i] === null || s.data[i] === undefined ? '—' : s.data[i])),
  }));
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function alertRow(cls, html) {
  return `<div class="alert-row ${cls}">${html}</div>`;
}

function renderChangeRows(changes) {
  const rows = [];
  changes.goat_displaced.forEach((e) => rows.push(alertRow('critical',
    `<strong>${e.was}</strong> displaced in ${e.city} (${e.locality}) — ${e.now}`)));
  changes.goat_gone.forEach((e) => rows.push(alertRow('critical',
    `<strong>${e.product}</strong> no longer listed in ${e.city} (${e.locality}) — last seen rank ${e.rank}`)));
  changes.rank_intrusions.forEach((e) => rows.push(alertRow('warning',
    `<strong>${e.intruder}</strong> intruded at rank ${e.rank} in ${e.city} (${e.locality})`)));
  changes.price_changes.forEach((e) => {
    const dir = e.change < 0 ? '▼' : '▲';
    rows.push(alertRow('warning',
      `<strong>${e.product}</strong> ${dir}₹${Math.abs(e.change).toFixed(0)} in ${e.city} (₹${e.old_price} → ₹${e.new_price})`));
  });
  changes.new_products.forEach((e) => rows.push(alertRow('info',
    `<strong>${e.product}</strong> appeared at rank ${e.rank} in ${e.city} (${e.locality})`)));
  changes.gone_products.filter((e) => !e.is_goat).forEach((e) => rows.push(alertRow('info',
    `<strong>${e.product}</strong> no longer listed in ${e.city} (${e.locality})`)));
  return rows.length ? rows.join('') : '<p class="info">No changes detected this week.</p>';
}

function renderTrendsTable(trends) {
  if (!trends.series.length) return '<p class="info">Not enough history yet for a trend table.</p>';
  const rows = formatTrendRows(trends);
  const head = `<tr><th>Product</th>${trends.weeks.map((w) => `<th>${w}</th>`).join('')}</tr>`;
  const body = rows.map((r) =>
    `<tr><td>${r.label}</td>${r.cells.map((c) => `<td class="mono">${c}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="lb">${head}${body}</table>`;
}

async function render() {
  const el = document.getElementById('shelf-monitor');
  el.innerHTML = '<p class="info">Loading…</p>';
  try {
    const [changes, trends] = await Promise.all([
      fetchJson('/api/shelf/changes'),
      fetchJson('/api/shelf/trends'),
    ]);
    if (changes.status === 'insufficient_history') {
      el.innerHTML = `<h2 class="vt">Shelf Monitor</h2><p class="info">${changes.narrative[0]}</p>`;
      return;
    }
    const sev = severityFor(changes);
    el.innerHTML = `
      <h2 class="vt">Shelf Monitor</h2>
      <p class="vd">Week-over-week changes to GOAT Life's Blinkit brand-search shelf, comparing run ${changes.old_run_id} → ${changes.new_run_id}.</p>
      <div class="severity-banner ${sev}">${SEVERITY_LABEL[sev]}</div>
      <div class="narrative">${changes.narrative.join('<br>')}</div>
      ${renderChangeRows(changes)}
      <h3 class="gh">Rank trend</h3>
      ${renderTrendsTable(trends)}`;
  } catch (e) {
    console.error('shelf-monitor render failed', e);
    el.innerHTML = '<h2 class="vt">Shelf Monitor</h2><p class="info">Failed to load — check the API is running.</p>';
  }
}

AppState.initShelfMonitor = render;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full JS suite once**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/shelf-monitor.test.js`
Expected: all pass, no regressions. (Skip `margin.test.js` here unless the margin branch has already been merged into this one — see Global Constraints.)

- [ ] **Step 6: Commit**

```bash
git add web/shelf-monitor.js web/tests/shelf-monitor.test.js
git commit -m "feat: add shelf-monitor.js (severity/trend-table pure helpers + render)"
```

---

### Task 6: Wire the "Shelf Monitor" tab into the dashboard

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/state.js`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: `AppState.initShelfMonitor` (Task 5).
- Produces: nothing further downstream — this is the integration leaf.

- [ ] **Step 1: Add the nav tab and view section to `web/index.html`**

Change:
```html
      <button class="tab" data-view="sequence">Launch Roadmap</button>
      <button class="tab" data-view="methodology">Method</button>
```
to:
```html
      <button class="tab" data-view="sequence">Launch Roadmap</button>
      <button class="tab" data-view="shelf">Shelf Monitor</button>
      <button class="tab" data-view="methodology">Method</button>
```

Change:
```html
  <section id="sequence-view" class="view"><div class="pad"><div id="sequence"></div></div></section>

  <section id="methodology-view" class="view"><div class="pad"><div id="methodology"></div></div></section>
```
to:
```html
  <section id="sequence-view" class="view"><div class="pad"><div id="sequence"></div></div></section>

  <section id="shelf-view" class="view"><div class="pad"><div id="shelf-monitor"></div></div></section>

  <section id="methodology-view" class="view"><div class="pad"><div id="methodology"></div></div></section>
```

(If the margin-calculator branch merged first, both new `<button>`/`<section>` pairs will already be present — just add this one alongside, in either order.)

- [ ] **Step 2: Wire `app.js`**

Change:
```js
import { renderSequence } from './sequence.js';
import AppState from './state.js';
```
to:
```js
import { renderSequence } from './sequence.js';
import AppState from './state.js';
import './shelf-monitor.js';
```

Change:
```js
    if (v === 'sequence' && !rendered.seq) { renderSequence(); rendered.seq = 1; }
  }));
```
to:
```js
    if (v === 'sequence' && !rendered.seq) { renderSequence(); rendered.seq = 1; }
    if (v === 'shelf' && !rendered.shelf) { AppState.initShelfMonitor(); rendered.shelf = 1; }
  }));
```

- [ ] **Step 3: Add the AppState slot**

In `web/state.js`, add `initShelfMonitor: null,` to the object (matching the existing declared-slot convention).

- [ ] **Step 4: Add the CSS**

Append to `web/styles.css`:
```css

.narrative{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;margin:14px 0;font-size:14px;line-height:1.6}
.severity-banner{padding:10px 16px;border-radius:var(--radius);font-family:var(--mono);font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;display:inline-block}
.severity-banner.critical{background:#FDEDEC;color:#991B1B}
.severity-banner.warning{background:#FEF6E7;color:#92400E}
.severity-banner.clear{background:#EAF7F0;color:#166534}
.alert-row{border-left:3px solid var(--line);padding:8px 12px;margin-bottom:6px;font-size:13px;background:var(--surface)}
.alert-row.critical{border-left-color:#991B1B}
.alert-row.warning{border-left-color:#d97706}
.alert-row.info{border-left-color:var(--goat)}
```
(`--radius`, `--go` were added by the margin branch — if that branch hasn't merged yet, `--radius` won't exist yet either; the rule above only uses `--radius`, which is safe to add here too if missing. Before adding, grep the current `styles.css` for `--radius:` — if it's already defined (margin branch merged first), do not redefine it a second time inside `:root{}`; if it's genuinely absent, add `--radius:8px;` to the existing `:root{}` block the same way the margin branch's plan did.)

- [ ] **Step 5: Verify in a real browser**

```bash
cd web
python -m http.server 8094
```
Open `http://localhost:8094`, click the "Shelf Monitor" tab. Since there is no local API server running against this static file server, the fetch calls will fail — confirm the catch-block failure state renders cleanly ("Failed to load — check the API is running.") rather than a raw unhandled-exception or blank page. This confirms the tab, nav wiring, and error-handling path all work; it does **not** confirm the real-data rendering path, which depends on Task 3/4's endpoints actually running (via `uvicorn` or a real Vercel deploy) — note this gap explicitly rather than claim full verification.
- [ ] **Step 5a:** For a fuller check, run `cd web/api && uvicorn index:app --reload` in a second terminal, then serve `web/` with something that proxies `/api/*` to `localhost:8000` (or temporarily edit `fetchJson`'s URLs to `http://localhost:8000/api/...` for this manual check only, reverting before commit) — confirm the "insufficient_history" placeholder copy renders correctly, since that's the real state production is in today (one scrape_run only).

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js web/state.js web/styles.css
git commit -m "feat: wire Shelf Monitor tab into the dashboard nav"
```

---

## Self-Review Notes

**Spec coverage:** Both endpoints from the user's stated Sprint 5 scope (`/api/shelf/changes`, `/api/shelf/trends`) are covered (Tasks 3-4), plus the dashboard tab that surfaces them (Tasks 5-6). Task 1-2 are the necessary plumbing (duplicated pure logic + DB access + response models) neither of which was explicitly named but both of which the two endpoints depend on. Margin-calculator wiring and Blinkit sponsored-ad detection are explicitly out of scope for this plan (separate branches/sprints per the user's own sequencing).

**Placeholder scan:** No TBD/TODO. Every step has complete, runnable code. Task 6, Step 5 explicitly documents what its manual verification does and does NOT prove, rather than claiming full end-to-end verification it cannot actually perform without a running API server.

**Type consistency:** `detect_changes`/`generate_narrative_summary`/`goat_gone_unique` signatures in Task 1's copy match Task 3's usage exactly (verified against the real Sprint-4-merged `scripts/shelf_changes.py`, not reconstructed from memory). `fetch_latest_two_scrape_run_ids`/`fetch_snapshot_rows`/`fetch_drop_calendar`/`fetch_shelf_trends` signatures are consistent between Task 1/4's definitions and Task 3/4's route usage. The `changes` dict keys (`goat_displaced`, `rank_intrusions`, `goat_gone`, `new_products`, `gone_products`, `rank_moved`, `price_changes`) are identical across `shelf_changes.py`'s output, `ShelfChanges`'s Pydantic field names, and `shelf-monitor.js`'s consumption of the fetched JSON — same names throughout, no snake_case/camelCase drift since the frontend reads the API's JSON keys as-is.

**Known open item carried forward, not silently dropped:** this plan was written against local `main` at commit `7aa80a9`, which has never been pushed to `origin` — 9 commits (all of Sprint 4) exist only locally. Anyone branching from `origin/main` (as this plan's own worktree initially did, by accident, before being fast-forwarded) will be missing Sprint 4 entirely. Push `main` to `origin` before or alongside merging this branch.
