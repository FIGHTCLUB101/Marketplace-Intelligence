# Sprint 4 — Shelf Monitor Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the antigravity repo's proven week-over-week shelf change-detection and email-alert logic (`shelf_monitor.py`, 96 tests) into this repo's Postgres schema, and get one real local weekly run producing a genuine second data point — the two things that must exist before any dashboard tab or API endpoint can show real change data.

**Architecture:** Single-tenant, GOAT-Life-only (see decision below — the parallel `2026-07-06-multi-tenant-saas-pivot-design.md` spec stays as-is, untouched, revisit-later). New pure-logic module (`scripts/shelf_changes.py`, DB-free, dict-in/dict-out) ported from `shelf_monitor.py`'s `detect_changes`, adapted to consume `shelf_snapshots` rows instead of pandas DataFrames — `is_goat` is now a precomputed boolean column, so the old case-insensitive keyword matching is no longer needed. A thin DB-access module (`scripts/queries_shelf.py`) and a local orchestrator (`scripts/run_weekly.py`) glue it to Postgres and Gmail. ICP-weighted narrative prioritization and historical recurrence are deliberately deferred to Sprint 5 — there's currently only one real `scrape_run` per platform in the database (confirmed live: `SELECT COUNT(*) FROM scrape_runs` = 4 total, one per platform, all from a single 2026-07-11 backfill), so there's nothing to diff yet and no history to weight.

**Tech Stack:** Python, psycopg2 (raw SQL, no ORM — matches `scripts/`'s existing pattern), pytest, smtplib/ssl (stdlib, matches `shelf_monitor.py`'s existing Gmail approach). No new dependencies.

## Global Constraints

- No `tenant_id` anywhere — this is deliberately single-tenant. If a multi-tenant pivot happens later, it follows the already-written `2026-07-06-multi-tenant-saas-pivot-design.md` spec as its own project, not a retrofit of these tables.
- `scripts/shelf_changes.py` has zero DB imports — every function takes plain lists of dicts (the shape `psycopg2.extras.RealDictCursor` returns) and returns plain dicts/lists. This mirrors `scripts/queries.py`'s existing `compute_belts(locality_rows)` pattern (pure function, DB access is a separate caller).
- Every `@requires_db` test in this plan **deletes every row it creates, including the `scrape_runs`/`pipeline_runs` parent row** — Sprint 1's `test_sync_locality_scores_end_to_end` did not do this and left 5 orphaned `pipeline_runs` rows in the live production Neon database (confirmed via live query: ids 14, 15, 16, 18, 47, all `source_parquet_filename = 'master.parquet'`, `row_count = 1`). Task 3 below cleans those up as part of this plan.
- Test fixture data uses `test_platform_xyz` / `TestCityXYZ` / `TestLocalityXYZ` / `TestSkuXYZ` prefixes, matching the existing convention from `web/api/test_api.py`'s `test_platform_xyz` (a fake platform name specifically avoids perturbing `/api/competitor/summary`'s real per-platform "latest run" results during the test transaction).
- Existing test/import convention: tests live alongside the code they test in `scripts/`, run via `cd scripts && python -m pytest -q`, flat imports (`from queries_shelf import ...`).
- `winsound.Beep()` / hardcoded `version_main=149` in the scrapers are **not** touched by this plan. The scraper stays local, human-supervised, CAPTCHA-gated (per the 2026-07-06 SaaS spec's own explicit rejection of cloud/headless scraping as *more* detectable, not less) — there is no near-term need to run it in CI, so "fixing" it now is unnecessary work.
- `db/schema.sql` changes must be idempotent (`CREATE TABLE IF NOT EXISTS`), applied via the existing `scripts/apply_schema.py` — no new apply mechanism.

---

### Task 1: `sku_drop_calendar` table

**Files:**
- Modify: `db/schema.sql`
- Modify: `scripts/test_apply_schema.py`

**Interfaces:**
- Produces: `sku_drop_calendar` table (`sku_name TEXT UNIQUE`, `paused_since`, `note`), consumed by Task 3's `queries_shelf.py`.

- [ ] **Step 1: Add the table to the schema**

Append to `db/schema.sql`:
```sql

-- Sprint 4: replaces the antigravity repo's drop_calendar.json file. A SKU
-- in this table is suppressed from goat_displaced/gone_products alerts —
-- GOAT Life runs intentional limited "drops" (streetwear-style scarcity),
-- so a SKU going out of stock is often deliberate, not a real disruption.
CREATE TABLE IF NOT EXISTS sku_drop_calendar (
    drop_calendar_id  SERIAL PRIMARY KEY,
    sku_name          TEXT UNIQUE NOT NULL,
    paused_since      TIMESTAMPTZ NOT NULL DEFAULT now(),
    note              TEXT
);
```

- [ ] **Step 2: Add it to the expected-tables test**

In `scripts/test_apply_schema.py`, modify `EXPECTED_TABLES`:
```python
EXPECTED_TABLES = {
    "localities",
    "pipeline_runs",
    "locality_scores",
    "scrape_runs",
    "shelf_snapshots",
    "locality_annotations",
    "sku_drop_calendar",
}
```

- [ ] **Step 3: Apply the schema and run the test**

Run:
```bash
cd scripts
python apply_schema.py
python -m pytest test_apply_schema.py -v
```
Expected: `Schema applied from .../db/schema.sql`, then `2 passed`.

- [ ] **Step 4: Clean up the 5 orphaned test rows from Sprint 1**

Run once, from `scripts/`:
```bash
python -c "
from db_connection import get_connection
conn = get_connection()
with conn.cursor() as cur:
    cur.execute(\"DELETE FROM pipeline_runs WHERE source_parquet_filename = 'master.parquet'\")
    print('Deleted', cur.rowcount, 'orphaned test rows')
conn.commit()
conn.close()
"
```
Expected: `Deleted 5 orphaned test rows`. (Safe — real pipeline runs always use `source_parquet_filename = 'localities_master_serviceable.parquet'`, confirmed via live query before writing this plan.)

- [ ] **Step 5: Commit**

```bash
git add db/schema.sql scripts/test_apply_schema.py
git commit -m "feat: add sku_drop_calendar table, clean up orphaned Sprint 1 test rows"
```

---

### Task 2: Pure change-detection logic (`scripts/shelf_changes.py`)

**Files:**
- Create: `scripts/shelf_changes.py`
- Test: `scripts/test_shelf_changes.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB).
- Produces: `build_shelf_snapshot(rows) -> dict`, `not_serviceable_localities(rows) -> set`, `detect_changes(rows_new, rows_old, drop_calendar=None, price_threshold_inr=20, price_threshold_pct=15) -> dict`, `generate_narrative_summary(changes) -> list[str]`. Consumed by Task 5's `run_weekly.py` and (Sprint 5) the API layer.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_shelf_changes.py`:
```python
from shelf_changes import (
    build_shelf_snapshot,
    detect_changes,
    generate_narrative_summary,
    not_serviceable_localities,
)


def _row(city, locality, name, rank, price, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "product_name": name,
            "rank": rank, "selling_price": price, "is_goat": is_goat}


def test_build_shelf_snapshot_keys_by_identity_not_position():
    rows = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    snap = build_shelf_snapshot(rows)
    assert snap[("Mumbai", "Bandra", "GOAT Life Mocha Marvel")] == {"rank": 1, "price": 119.0}


def test_build_shelf_snapshot_skips_null_rank_rows():
    rows = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    assert build_shelf_snapshot(rows) == {}


def test_insertion_does_not_cascade_false_positives():
    # A new product inserted at rank 5 pushes 3 pre-existing products down a
    # slot each. None of them should be reported as new/gone — only the
    # genuinely new one. This is the exact bug class the antigravity repo's
    # original position-keyed comparison had before it was fixed.
    rows_old = [
        _row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 449.0),
        _row("Mumbai", "Bandra", "Quaker Rolled Oats", 6, 86.0),
        _row("Mumbai", "Bandra", "Saffola Masala Oats", 7, 199.0),
    ]
    rows_new = [
        _row("Mumbai", "Bandra", "ProOats High Protein", 5, 89.0),
        _row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 449.0),
        _row("Mumbai", "Bandra", "Quaker Rolled Oats", 7, 86.0),
        _row("Mumbai", "Bandra", "Saffola Masala Oats", 8, 199.0),
    ]
    changes = detect_changes(rows_new, rows_old)
    assert {p["product"] for p in changes["new_products"]} == {"ProOats High Protein"}
    assert changes["gone_products"] == []


def test_goat_displaced_from_ranks_1_to_4():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["goat_displaced"]) == 1
    assert changes["goat_displaced"][0]["was"] == "GOAT Life Mocha Marvel"


def test_rank_intrusion_into_goat_zone():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Almond Kulfi", 4, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 4, 449.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["rank_intrusions"]) == 1
    assert changes["rank_intrusions"][0]["intruder"] == "Prustlr Discovery Protein Oats"


def test_not_serviceable_locality_excluded_from_comparison():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["goat_displaced"] == []
    assert changes["gone_products"] == []


def test_price_change_fires_on_rupee_or_percent_threshold():
    rows_old = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 599.0)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 5, 574.0)]
    changes = detect_changes(rows_new, rows_old)
    assert len(changes["price_changes"]) == 1
    assert changes["price_changes"][0]["change"] == -25.0


def test_price_change_does_not_fire_below_both_thresholds():
    rows_old = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 599.0)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 6, 590.0)]
    changes = detect_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_drop_calendar_suppresses_goat_displaced():
    rows_old = [_row("Mumbai", "Bandra", "GOAT Life Mocha Marvel", 1, 119.0, is_goat=True)]
    rows_new = [_row("Mumbai", "Bandra", "Prustlr Discovery Protein Oats", 1, 449.0)]
    changes = detect_changes(rows_new, rows_old, drop_calendar={"GOAT Life Mocha Marvel"})
    assert changes["goat_displaced"] == []


def test_not_serviceable_localities_finds_marked_rows():
    rows = [_row("Mumbai", "Bandra", "Not Serviceable", None, None)]
    assert not_serviceable_localities(rows) == {("Mumbai", "Bandra")}


def test_generate_narrative_summary_all_clear():
    changes = {"goat_displaced": [], "rank_intrusions": [], "gone_products": []}
    result = generate_narrative_summary(changes)
    assert len(result) == 1
    assert "holds ranks 1" in result[0]


def test_generate_narrative_summary_leads_with_most_frequent_threat():
    changes = {
        "goat_displaced": [],
        "rank_intrusions": [
            {"city": "Chennai", "locality": "Adyar", "intruder": "Yoga Bar Golden Oats"},
            {"city": "Bangalore", "locality": "BTM Layout", "intruder": "Prustlr Discovery Protein Oats"},
            {"city": "Mumbai", "locality": "Andheri", "intruder": "Prustlr Discovery Protein Oats"},
        ],
        "gone_products": [],
    }
    result = generate_narrative_summary(changes)
    assert "Prustlr" in result[0]
    assert "1 other change" in result[1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_shelf_changes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shelf_changes'`

- [ ] **Step 3: Write the implementation**

Create `scripts/shelf_changes.py`:
```python
"""Shelf change-detection, ported from the antigravity repo's
shelf_monitor.py (detect_changes/build_shelf_snapshot/generate_narrative_summary,
96 tests) to operate on Postgres shelf_snapshots rows (list[dict], the shape
RealDictCursor returns) instead of pandas DataFrames.

Pure functions only — no DB import here. is_goat is now a precomputed
boolean column (set by the scraper's is_goat_brand() at scrape time), which
replaces the original's runtime case-insensitive keyword matching.

ICP-weighted narrative prioritization and historical_recurrence (both real
features of the original) are deferred to Sprint 5 — there is currently
only one scrape_run per platform in the database, so there is no history to
weight yet.
"""

PLACEHOLDER_NAMES = ("N/A", "Not Available", "Location Error")


def build_shelf_snapshot(rows):
    """rows: list of dicts with city_raw, locality_raw, product_name, rank,
    selling_price (shelf_snapshots columns). Returns
    {(city, locality, product_name): {"rank": int, "price": float | None}}.
    Rows with rank=None (Not Serviceable / Location Error placeholders) are
    skipped — matches the original's numeric-rank-only filter."""
    snap = {}
    for r in rows:
        if r["rank"] is None:
            continue
        key = (r["city_raw"], r["locality_raw"], r["product_name"])
        price = float(r["selling_price"]) if r["selling_price"] is not None else None
        snap[key] = {"rank": r["rank"], "price": price}
    return snap


def not_serviceable_localities(rows):
    """Returns {(city, locality)} for rows the scraper marked Not Serviceable."""
    return {(r["city_raw"], r["locality_raw"]) for r in rows if r["product_name"] == "Not Serviceable"}


def _is_goat_lookup(rows_new, rows_old):
    lookup = {}
    for r in rows_new + rows_old:
        if r["rank"] is not None:
            lookup[(r["city_raw"], r["locality_raw"], r["product_name"])] = r["is_goat"]
    return lookup


def detect_changes(rows_new, rows_old, drop_calendar=None, price_threshold_inr=20, price_threshold_pct=15):
    snap_new = build_shelf_snapshot(rows_new)
    snap_old = build_shelf_snapshot(rows_old)
    is_goat_of = _is_goat_lookup(rows_new, rows_old)
    ns_new = not_serviceable_localities(rows_new)
    drop_calendar = drop_calendar or set()

    goat_displaced, goat_recovered = [], []
    new_products, gone_products = [], []
    rank_intrusions, rank_moved = [], []
    price_changes = []

    for key in set(snap_new) | set(snap_old):
        city, locality, name = key
        if (city, locality) in ns_new:
            continue
        new_entry, old_entry = snap_new.get(key), snap_old.get(key)
        new_rank = new_entry["rank"] if new_entry else None
        old_rank = old_entry["rank"] if old_entry else None
        new_price = new_entry["price"] if new_entry else None
        old_price = old_entry["price"] if old_entry else None
        is_goat = is_goat_of.get(key, False)
        is_placeholder = name in PLACEHOLDER_NAMES

        if new_entry and not old_entry and not is_placeholder:
            new_products.append({"city": city, "locality": locality, "rank": new_rank, "product": name})

        if old_entry and not new_entry and not is_placeholder:
            if not (is_goat and name in drop_calendar):
                gone_products.append({"city": city, "locality": locality, "rank": old_rank,
                                       "product": name, "is_goat": is_goat})

        if new_entry and old_entry and new_rank != old_rank and not is_placeholder:
            rank_moved.append({"city": city, "locality": locality, "product": name,
                                "old_rank": old_rank, "new_rank": new_rank, "is_goat": is_goat})

        if not is_placeholder and is_goat and old_entry and old_rank in (1, 2, 3, 4):
            if not new_entry or new_rank not in (1, 2, 3, 4):
                if name not in drop_calendar:
                    now_label = f"Still listed, now rank {new_rank}" if new_entry else "MISSING"
                    goat_displaced.append({"city": city, "locality": locality, "rank": old_rank,
                                            "was": name, "now": now_label})

        if not is_placeholder and is_goat and new_entry and new_rank in (1, 2, 3, 4):
            if not old_entry or old_rank not in (1, 2, 3, 4):
                goat_recovered.append({"city": city, "locality": locality, "rank": new_rank, "product": name})

        if not is_placeholder and not is_goat and new_entry and new_rank in (1, 2, 3, 4):
            if not old_entry or old_rank not in (1, 2, 3, 4):
                rank_intrusions.append({"city": city, "locality": locality, "rank": new_rank, "intruder": name})

        if new_price and old_price and not is_placeholder:
            change_abs = abs(new_price - old_price)
            change_pct = (change_abs / old_price * 100) if old_price else 0
            if change_abs >= price_threshold_inr or change_pct >= price_threshold_pct:
                price_changes.append({"city": city, "locality": locality, "product": name,
                                       "old_price": old_price, "new_price": new_price,
                                       "change": new_price - old_price})

    return {
        "goat_displaced": goat_displaced, "goat_recovered": goat_recovered,
        "new_products": new_products, "gone_products": gone_products,
        "rank_intrusions": rank_intrusions, "rank_moved": rank_moved,
        "price_changes": price_changes,
    }


def generate_narrative_summary(changes):
    """Returns 1-2 plain-language sentences. Lead sentence is whichever
    threat's product name recurs most often this week (frequency-only —
    ICP-weighted prioritization is Sprint 5)."""
    goat_gone = [g for g in changes["gone_products"] if g["is_goat"]]
    threats = list(changes["goat_displaced"]) + list(changes["rank_intrusions"])

    if not threats and not goat_gone:
        return ["GOAT Life holds ranks 1-4 across all monitored localities. "
                "No competitor has moved into your shelf space this week."]

    def product_name_of(entry):
        return entry.get("was") or entry.get("intruder") or ""

    name_counts = {}
    for e in threats:
        name_counts[product_name_of(e)] = name_counts.get(product_name_of(e), 0) + 1

    sentences = []
    lead = max(threats, key=lambda e: name_counts[product_name_of(e)]) if threats else None
    if lead is not None:
        product, city = product_name_of(lead), lead["city"]
        if "intruder" in lead:
            sentences.append(f"{product[:40]} intruded into GOAT Life's shelf space in {city} this week.")
        else:
            sentences.append(f"GOAT Life lost shelf position for {product[:40]} in {city} this week.")

    other_count = len(threats) + len(goat_gone) - (1 if lead is not None else 0)
    if other_count > 0:
        sentences.append(f"{other_count} other change{'s' if other_count != 1 else ''} detected this week.")

    return sentences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_shelf_changes.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/shelf_changes.py scripts/test_shelf_changes.py
git commit -m "feat: port shelf change-detection logic to operate on Postgres rows"
```

---

### Task 3: Postgres access layer (`scripts/queries_shelf.py`)

**Files:**
- Create: `scripts/queries_shelf.py`
- Test: `scripts/test_queries_shelf.py`

**Interfaces:**
- Consumes: `get_connection()` (`scripts/db_connection.py`, already exists).
- Produces: `fetch_latest_two_scrape_run_ids(conn, platform) -> (int|None, int|None)`, `fetch_snapshot_rows(conn, scrape_run_id) -> list[dict]`, `fetch_drop_calendar(conn) -> set[str]`, `pause_sku(conn, sku_name, note=None) -> None`, `unpause_sku(conn, sku_name) -> None`. Consumed by Task 5's `run_weekly.py`.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_queries_shelf.py`:
```python
import os

import pytest

from db_connection import get_connection
from queries_shelf import (
    fetch_drop_calendar,
    fetch_latest_two_scrape_run_ids,
    fetch_snapshot_rows,
    pause_sku,
    unpause_sku,
)

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
        # Deletes the scrape_runs parent rows too — Sprint 1's equivalent
        # test did not do this and left orphaned rows in production (Task 1).
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = ANY(%s)", (run_ids,))
        conn.commit()
        conn.close()


@requires_db
def test_fetch_latest_two_returns_none_second_when_only_one_run_exists():
    conn = get_connection()
    run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_solo", "only.xlsx"),
            )
            run_id = cur.fetchone()[0]
        conn.commit()

        newest, second = fetch_latest_two_scrape_run_ids(conn, "test_platform_xyz_solo")
        assert newest == run_id
        assert second is None
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (run_id,))
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
        assert rows[0]["rank"] == 1
        assert rows[0]["is_goat"] is True
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()


@requires_db
def test_pause_and_unpause_sku_roundtrip():
    conn = get_connection()
    try:
        pause_sku(conn, "TestSkuXYZ", note="test pause")
        assert "TestSkuXYZ" in fetch_drop_calendar(conn)

        unpause_sku(conn, "TestSkuXYZ")
        assert "TestSkuXYZ" not in fetch_drop_calendar(conn)
    finally:
        unpause_sku(conn, "TestSkuXYZ")  # safety net if an assert above failed
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_queries_shelf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'queries_shelf'`

- [ ] **Step 3: Write the implementation**

Create `scripts/queries_shelf.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_queries_shelf.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/queries_shelf.py scripts/test_queries_shelf.py
git commit -m "feat: add Postgres access layer for shelf change-detection"
```

---

### Task 4: Email alerts (`scripts/alerts.py`)

**Files:**
- Create: `scripts/alerts.py`
- Test: `scripts/test_alerts.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `generate_narrative_summary(changes)` (Task 2).
- Produces: `build_email_html(changes, new_run_label, old_run_label) -> str`, `send_gmail(subject, html_body, sender, app_password, recipients) -> None`. Consumed by Task 5's `run_weekly.py`.

- [ ] **Step 1: Add Gmail config to `.env.example`**

Append to `.env.example`:
```
GMAIL_SENDER=your.email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENTS=your.email@gmail.com,yash@goatlife.co.in
```

- [ ] **Step 2: Write the failing test**

Create `scripts/test_alerts.py`:
```python
from alerts import build_email_html


def test_build_email_html_includes_narrative_and_severity():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "GOAT LIFE SHELF DISRUPTED" in html
    assert "GOAT Life Mocha Marvel" in html
    assert "Bandra" in html


def test_build_email_html_all_clear():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [],
        "gone_products": [], "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "ALL CLEAR" in html


def test_build_email_html_includes_price_changes_table():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [],
        "price_changes": [{"city": "Mumbai", "locality": "Bandra", "product": "Prustlr Discovery Protein Oats",
                            "old_price": 449.0, "new_price": 469.0, "change": 20.0}],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "Prustlr Discovery Protein Oats" in html
    assert "469" in html
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alerts'`

- [ ] **Step 4: Write the implementation**

Create `scripts/alerts.py`:
```python
"""Email alerts, ported near-verbatim from the antigravity repo's
shelf_monitor.py (build_email_html/send_gmail). Takes the new-style
detect_changes() dict shape (new_products/gone_products, not
new_competitors/gone_competitors) from shelf_changes.py.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shelf_changes import generate_narrative_summary


def build_email_html(changes, new_run_label, old_run_label):
    goat_gone_count = len([g for g in changes["gone_products"] if g["is_goat"]])
    total_displaced = len(changes["goat_displaced"]) + goat_gone_count
    total_intrusions = len(changes["rank_intrusions"])

    severity = "ALL CLEAR" if total_displaced == 0 and total_intrusions == 0 else \
               "CHANGES DETECTED" if total_displaced == 0 else \
               "GOAT LIFE SHELF DISRUPTED"

    narrative_html = "<br>".join(generate_narrative_summary(changes))

    html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }}
  .container {{ max-width: 620px; margin: 0 auto; background: white; }}
  .header {{ background: #0d0d0d; color: white; padding: 28px 32px; }}
  .severity {{ padding: 16px 32px; font-size: 17px; font-weight: bold; }}
  .section {{ padding: 20px 32px; border-bottom: 1px solid #eee; }}
  .alert-item {{ background: #fff5f5; border-left: 3px solid #e53e3e; padding: 10px 14px; margin-bottom: 8px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: #f0f0f0; padding: 8px; text-align: left; }}
  td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; }}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>GOAT Life — Shelf Monitor</h1>
    <div>{old_run_label} to {new_run_label}</div></div>
  <div class="severity">{severity}</div>
  <div class="section"><p>{narrative_html}</p></div>
"""

    if changes["goat_displaced"]:
        html += '<div class="section"><h2>GOAT Life Rank Disruptions</h2>'
        for item in changes["goat_displaced"]:
            html += (f'<div class="alert-item"><strong>{item["was"][:40]}</strong> displaced in '
                      f'{item["city"]} ({item["locality"]}) — {item["now"]}</div>')
        html += "</div>"

    if changes["rank_intrusions"]:
        html += '<div class="section"><h2>Competitors in GOAT Territory</h2>'
        for item in changes["rank_intrusions"]:
            html += (f'<div class="alert-item"><strong>{item["intruder"][:40]}</strong> at rank '
                      f'{item["rank"]} in {item["city"]} ({item["locality"]})</div>')
        html += "</div>"

    if changes["price_changes"]:
        html += "<div class=\"section\"><h2>Price Changes</h2><table><tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>"
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    html += "</div></body></html>"
    return html


def send_gmail(subject, html_body, sender, app_password, recipients):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipients, msg.as_string())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_alerts.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add scripts/alerts.py scripts/test_alerts.py .env.example
git commit -m "feat: port email alert HTML/send logic"
```

---

### Task 5: Weekly orchestrator (`scripts/run_weekly.py`)

**Files:**
- Create: `scripts/run_weekly.py`

**Interfaces:**
- Consumes: `sync_shelf_snapshots` (existing, Sprint 1), `fetch_latest_two_scrape_run_ids`/`fetch_snapshot_rows`/`fetch_drop_calendar` (Task 3), `detect_changes` (Task 2), `build_email_html`/`send_gmail` (Task 4).
- Produces: a CLI entry point; no other task depends on its internals.

- [ ] **Step 1: Write `scripts/run_weekly.py`**

```python
"""Weekly orchestrator: sync the latest GOAT Life Blinkit scrape into
Postgres, diff it against the previous run, and email the result.

Run this AFTER scraper/blinkit_goatlife.py has finished (still local,
CAPTCHA-gated — see Global Constraints in the Sprint 4 plan for why that
stays unchanged). Usage:
    python run_weekly.py [--dry-run]
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from alerts import build_email_html, send_gmail
from db_connection import get_connection
from queries_shelf import fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_snapshot_rows
from shelf_changes import detect_changes
from sync_shelf_snapshots import sync_shelf_snapshots

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_OUTPUT = ROOT / "scraper" / "output" / "blinkit_goatlife_data.xlsx"
PLATFORM = "blinkit_goatlife"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip sending the email — print the subject/severity instead.")
    args = parser.parse_args()

    if not SCRAPER_OUTPUT.exists():
        logging.error(f"Scraper output not found: {SCRAPER_OUTPUT}. Run scraper/blinkit_goatlife.py first.")
        sys.exit(1)

    conn = get_connection()
    try:
        logging.info(f"Syncing {SCRAPER_OUTPUT} into shelf_snapshots...")
        sync_result = sync_shelf_snapshots(SCRAPER_OUTPUT, PLATFORM, conn)
        logging.info(f"  {sync_result}")

        newest_id, second_id = fetch_latest_two_scrape_run_ids(conn, PLATFORM)
        if second_id is None:
            logging.warning("Only one scrape_run exists for this platform — nothing to compare against yet. "
                             "Run the scraper again next week to get a real diff.")
            return

        rows_new = fetch_snapshot_rows(conn, newest_id)
        rows_old = fetch_snapshot_rows(conn, second_id)
        drop_calendar = fetch_drop_calendar(conn)
        changes = detect_changes(rows_new, rows_old, drop_calendar=drop_calendar)

        logging.info(f"  GOAT displaced   : {len(changes['goat_displaced'])}")
        logging.info(f"  Rank intrusions  : {len(changes['rank_intrusions'])}")
        logging.info(f"  Price changes    : {len(changes['price_changes'])}")

        total = len(changes["goat_displaced"]) + len(changes["rank_intrusions"])
        subject = (f"GOAT Life Shelf Alert — {total} changes detected" if total > 0
                   else "GOAT Life Shelf Monitor — All Clear")

        if args.dry_run:
            logging.info(f"[--dry-run] Would send: {subject}")
            return

        html = build_email_html(changes, str(newest_id), str(second_id))
        sender = os.environ["GMAIL_SENDER"]
        app_password = os.environ["GMAIL_APP_PASSWORD"]
        recipients = os.environ["GMAIL_RECIPIENTS"].split(",")
        send_gmail(subject, html, sender, app_password, recipients)
        logging.info(f"Sent: {subject}")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Weekly run failed")
        sys.exit(1)
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd scripts && python -m py_compile run_weekly.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Dry-run against real data once a second scrape exists**

This cannot be fully exercised until `scraper/blinkit_goatlife.py` has been run a second time (Global Constraints: only one real `scrape_run` currently exists per platform). Once it has:
```bash
cd scripts
python run_weekly.py --dry-run
```
Expected: logs showing sync result, displaced/intrusion/price counts, and `[--dry-run] Would send: ...` — confirms the full pipeline runs end-to-end without sending a real email yet.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_weekly.py
git commit -m "feat: add weekly orchestrator (sync -> diff -> email)"
```

---

### Task 6: Cross-platform GOAT-presence audit

**Files:**
- Create: `scripts/audit_goat_presence.py`

**Interfaces:**
- Produces: a one-off diagnostic CLI script. No other task depends on it — this exists to resolve an open question before Sprint 5 builds any cross-platform UI on top of `shelf_snapshots`.

**Why this task exists:** live query during planning found `is_goat=True` on 2,000/7,500 Blinkit-GOAT-Life rows and 767/56,688 general-Blinkit rows (both plausible), but only **24/35,708 Zepto rows** and **0/36,514 Swiggy rows**. That's either a real fact (GOAT Life's Swiggy/Zepto presence is currently near-zero) or a scraper brand-matching bug in `scraper/swiggy_oats.py`/`scraper/zepto_oats.py`. This must be resolved before Sprint 5 builds a "360° cross-platform" feature on data that might not mean what it appears to.

- [ ] **Step 1: Write the script**

Create `scripts/audit_goat_presence.py`:
```python
"""One-off diagnostic: for each platform, print is_goat row counts and a
sample of product names, to check whether the near-zero GOAT Life presence
on Swiggy/Zepto (found during Sprint 4 planning) is real or a scraper bug.
"""
from db_connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT platform, is_goat, COUNT(*)
            FROM shelf_snapshots GROUP BY platform, is_goat ORDER BY platform, is_goat
        """)
        print("--- is_goat counts by platform ---")
        for row in cur.fetchall():
            print(row)

        print("\n--- sample product_names containing 'goat' (any platform, case-insensitive) ---")
        cur.execute("""
            SELECT DISTINCT platform, product_name FROM shelf_snapshots
            WHERE product_name ILIKE '%goat%' LIMIT 20
        """)
        for row in cur.fetchall():
            print(row)

        print("\n--- sample product_names, Swiggy, is_goat=false (first 15) ---")
        cur.execute("""
            SELECT DISTINCT product_name FROM shelf_snapshots
            WHERE platform = 'swiggy' LIMIT 15
        """)
        for row in cur.fetchall():
            print(row)
```

- [ ] **Step 2: Run it and record the result**

Run: `cd scripts && python audit_goat_presence.py`

Read the output. Two outcomes:
- If the "goat" `ILIKE` search on Swiggy/Zepto turns up real GOAT Life product names that weren't flagged `is_goat=True` — it's a matching bug in `scraper/shelf_common.py`'s `is_goat_brand()` or in how `sync_shelf_snapshots.py` applies it for those platforms. File it as a bug fix before Sprint 5.
- If it turns up nothing — GOAT Life genuinely isn't appearing in these scrapes yet (plausibly because `scraper/swiggy_oats.py`/`scraper/zepto_oats.py` search a fixed competitor `BRANDS` list that may not include "GOAT Life" as a search term at all — check `BRANDS` in both files). Either way, Sprint 5's cross-platform framing should say "Blinkit-verified, Swiggy/Zepto pending" rather than implying equal three-platform coverage.

- [ ] **Step 3: Commit**

```bash
git add scripts/audit_goat_presence.py
git commit -m "chore: add cross-platform GOAT-presence diagnostic"
```

---

## Self-Review Notes

**Spec coverage:** Task 1 covers the drop-calendar gap identified during verification (no table existed for it). Tasks 2-4 port every piece of business logic the merge decision calls for except ICP-weighting and historical recurrence, which are explicitly deferred to Sprint 5 with the reason stated (no history exists yet to weight). Task 5 is the real end-to-end pipeline. Task 6 resolves the Swiggy/Zepto data-quality question before Sprint 5 builds on top of it.

**Placeholder scan:** No TBD/TODO. Every step has complete, runnable code, including the diagnostic script.

**Type consistency:** `detect_changes(rows_new, rows_old, drop_calendar=None, ...)` in Task 2 is called identically in Task 5. `fetch_latest_two_scrape_run_ids`/`fetch_snapshot_rows`/`fetch_drop_calendar` signatures in Task 3 match their usage in Task 5 exactly. `build_email_html(changes, new_run_label, old_run_label)` and `send_gmail(subject, html_body, sender, app_password, recipients)` in Task 4 match Task 5's call sites. The `changes` dict shape (`goat_displaced`, `goat_recovered`, `new_products`, `gone_products`, `rank_intrusions`, `rank_moved`, `price_changes`) is produced once by Task 2 and consumed identically by Tasks 4 and 5 — note this is a deliberate rename from the antigravity original's `new_competitors`/`gone_competitors` to `new_products`/`gone_products`, since "competitor" was misleading for GOAT's own SKUs appearing in that same list.

**Not in this sprint (Sprint 5, once this is merged and a real second scrape exists):** `/api/shelf/changes` + `/api/shelf/trends` endpoints, the "Shelf Monitor" dashboard tab, ICP-weighted narrative + `historical_recurrence`, wiring `margin.js` into the nav, Sponsored/ad detection on the Blinkit scrapers, stock-depletion alerts, `check_missed_run.py`-equivalent watchdog on the new pipeline.
