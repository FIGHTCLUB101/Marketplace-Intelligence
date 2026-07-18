# Weekly Oats Competitor Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `scripts/run_weekly.py` so the weekly report also diffs the three oats competitor scrapers (Blinkit, Swiggy, Zepto oats) week-over-week — price, stock/availability, new/delisted SKUs — alongside the existing GOAT Life shelf-rank comparison, combined into one weekly email.

**Architecture:** A new pure-function module `scripts/oats_changes.py` (mirroring `scripts/shelf_changes.py`'s shape) detects price/availability changes for the oats platforms, which don't carry rank data. `scripts/run_weekly.py` becomes a loop over a 4-platform table, dispatching each platform to the rank-based (`shelf_changes.detect_changes`) or price/availability-based (`oats_changes.detect_price_availability_changes`) detector, with each platform isolated from the others' failures. `scripts/alerts.py` moves from one monolithic HTML document to composable per-platform section fragments wrapped by a single combined-email builder.

**Tech Stack:** Python, pandas/openpyxl (existing xlsx I/O), psycopg2 (existing Postgres access), pytest.

## Global Constraints

- Price-change threshold: ₹20 absolute OR 15% percent — same values as the existing `blinkit_goatlife` shelf monitor, applied to oats platforms too.
- No rank-based logic for oats platforms (Blinkit/Swiggy oats capture no rank column at all; Zepto oats' `Rank` column means "position within one brand's search," not a category shelf position — neither is comparable to `blinkit_goatlife`'s rank).
- One combined weekly email covering all 4 platforms, not 4 separate emails.
- Stays a manually-run script (`python run_weekly.py`) — no cron/scheduling automation, matching `blinkit_goatlife`'s existing CAPTCHA-gated, local-only constraint.
- `stock_changes` evaluated only when `stock_left` is non-null/non-empty on *both* sides of a comparison.
- Price comparison requires the raw `display_name` to be identical on both sides (never diff a single-pack price against a "Pack of N" price for the same normalized identity), and both prices must be non-`None` and `> 0`.
- Oats product matching key is `(city_raw, locality_raw, brand_searched, normalize_product_identity(product_name))` — `brand_searched` is part of the key because the same product can legitimately appear under multiple competitor brand searches in the same locality.
- Widening `fetch_snapshot_rows()`'s SELECT is isolated to `scripts/` — `web/api/queries.py` has its own separate copy by design and must not be touched.
- One platform failing (missing file, locked file, sync error, insufficient history) must never block reporting on the others; the script only exits non-zero if every platform fails.
- Out of scope: extending the oats scrapers to capture shelf rank, any cron/scheduling automation, ICP-weighted narrative prioritization or `historical_recurrence` weighting for oats platforms.

Every task's requirements implicitly include this section.

---

## Task 1: Widen `fetch_snapshot_rows()` to include oats-required columns

**Files:**
- Modify: `scripts/queries_shelf.py:26-36`
- Test: `scripts/test_queries_shelf.py`

**Interfaces:**
- Produces: `fetch_snapshot_rows(conn, scrape_run_id) -> list[dict]`, each dict now also containing `brand_searched`, `stock_left`, `serviceable` alongside the existing `city_raw, locality_raw, product_name, rank, selling_price, is_goat`. Task 2 and Task 4 depend on these three new keys being present.

- [ ] **Step 1: Write the failing test**

Add to `scripts/test_queries_shelf.py` (after `test_fetch_snapshot_rows_returns_expected_columns`):

```python
@requires_db
def test_fetch_snapshot_rows_includes_brand_stock_serviceable():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_cols", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, product_name, selling_price, stock_left, serviceable, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_cols", "TestCityXYZ", "TestLocalityXYZ",
                 "Pintola Oats", "Pintola Oats 1kg", 249.0, "In Stock", "Yes", False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        rows = fetch_snapshot_rows(conn, scrape_run_id)
        assert len(rows) == 1
        assert rows[0]["brand_searched"] == "Pintola Oats"
        assert rows[0]["stock_left"] == "In Stock"
        assert rows[0]["serviceable"] == "Yes"
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts && python -m pytest test_queries_shelf.py -v -k brand_stock_serviceable`
Expected: FAIL with `KeyError: 'brand_searched'` (the column isn't selected yet).

- [ ] **Step 3: Widen the SELECT**

In `scripts/queries_shelf.py`, replace `fetch_snapshot_rows`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts && python -m pytest test_queries_shelf.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add scripts/queries_shelf.py scripts/test_queries_shelf.py
git commit -m "feat: widen fetch_snapshot_rows to include brand_searched, stock_left, serviceable"
```

---

## Task 2: `scripts/oats_changes.py` — price/availability change detection

**Files:**
- Create: `scripts/oats_changes.py`
- Test: `scripts/test_oats_changes.py`

**Interfaces:**
- Consumes: `normalize_product_identity(name) -> str` from `scripts/shelf_changes.py` (existing).
- Produces: `detect_price_availability_changes(rows_new, rows_old, price_threshold_inr=20, price_threshold_pct=15) -> dict` with keys `new_products, gone_products, price_changes, stock_changes` (each a `list[dict]`). Task 3 and Task 4 depend on this exact function name, signature, and these four dict keys.

### Step group A — matching, new/gone products, brand-search distinctness, is_goat propagation

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_oats_changes.py`:

```python
from oats_changes import build_oats_snapshot, detect_price_availability_changes


def _row(city, locality, brand, name, price, stock_left=None, is_goat=False):
    return {"city_raw": city, "locality_raw": locality, "brand_searched": brand,
            "product_name": name, "selling_price": price, "stock_left": stock_left,
            "is_goat": is_goat}


def test_build_oats_snapshot_keys_by_locality_brand_and_identity():
    rows = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg", 249.0)]
    snap = build_oats_snapshot(rows)
    assert snap[("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg")] == {
        "price": 249.0, "stock_left": None, "display_name": "Pintola Oats 1kg", "is_goat": False,
    }


def test_new_and_gone_products_detected():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 1kg", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Oats 500g", 149.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert {p["product"] for p in changes["new_products"]} == {"Pintola Oats 500g"}
    assert {p["product"] for p in changes["gone_products"]} == {"Pintola Oats 1kg"}


def test_pack_size_suffix_treated_as_same_product_not_gone_and_new():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats - Pack of 2", 249.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["new_products"] == []
    assert changes["gone_products"] == []


def test_same_product_name_under_different_brand_searched_kept_distinct():
    # GOAT Life's own product can legitimately appear inside more than one
    # competitor's brand search in the same locality -- these are two real,
    # independent observations, not one product that "moved".
    rows_old = [
        _row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
    ]
    rows_new = [
        _row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
        _row("Bangalore", "Indiranagar", "Yoga Bar Oats", "GOAT Life Original Oats", 199.0, is_goat=True),
    ]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert {p["brand_searched"] for p in changes["new_products"]} == {"Yoga Bar Oats"}


def test_is_goat_propagates_through_new_and_gone():
    rows_old = []
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "GOAT Life Original Oats", 199.0, is_goat=True)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["new_products"][0]["is_goat"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_oats_changes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oats_changes'`.

- [ ] **Step 3: Implement the matching/new/gone core**

Create `scripts/oats_changes.py`:

```python
"""Price/availability change-detection for the oats competitor scrapers
(blinkit/swiggy/zepto oats), which capture per-brand-search competitor
listings rather than category shelf rank. Unlike shelf_changes.py's
detect_changes() (rank 1-4 GOAT shelf-position semantics), this operates on
whatever these three platforms actually capture: price, stock/availability,
and new/delisted SKUs. Pure functions only — no DB import here.

Blinkit oats and Swiggy oats capture no rank at all; Zepto oats has a Rank
column but it's rank within one brand's search results, not a category-wide
shelf position -- none of that is comparable to blinkit_goatlife's rank, so
this module never looks at "rank".
"""
from shelf_changes import normalize_product_identity


def build_oats_snapshot(rows):
    """rows: list of dicts with city_raw, locality_raw, brand_searched,
    product_name, selling_price, stock_left, is_goat (shelf_snapshots
    columns). Returns {(city, locality, brand_searched, normalized_identity):
    {"price": float | None, "stock_left": str | None, "display_name": str,
    "is_goat": bool}}."""
    snap = {}
    for r in rows:
        if r["product_name"] is None:
            continue
        identity = normalize_product_identity(r["product_name"])
        key = (r["city_raw"], r["locality_raw"], r["brand_searched"], identity)
        price = float(r["selling_price"]) if r["selling_price"] is not None else None
        snap[key] = {
            "price": price,
            "stock_left": r.get("stock_left"),
            "display_name": r["product_name"],
            "is_goat": bool(r.get("is_goat")),
        }
    return snap


def detect_price_availability_changes(rows_new, rows_old, price_threshold_inr=20, price_threshold_pct=15):
    snap_new = build_oats_snapshot(rows_new)
    snap_old = build_oats_snapshot(rows_old)

    new_products, gone_products = [], []
    price_changes, stock_changes = [], []

    for key in set(snap_new) | set(snap_old):
        city, locality, brand_searched, _identity = key
        new_entry, old_entry = snap_new.get(key), snap_old.get(key)
        is_goat = (new_entry or old_entry)["is_goat"]

        if new_entry and not old_entry:
            new_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                  "product": new_entry["display_name"], "is_goat": is_goat})
            continue

        if old_entry and not new_entry:
            gone_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                   "product": old_entry["display_name"], "is_goat": is_goat})
            continue

    return {
        "new_products": new_products, "gone_products": gone_products,
        "price_changes": price_changes, "stock_changes": stock_changes,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_oats_changes.py -v`
Expected: PASS (all 5 tests from step 1).

### Step group B — price changes with false-positive guards

- [ ] **Step 5: Write the failing tests**

Append to `scripts/test_oats_changes.py`:

```python
def test_price_change_fires_on_rupee_or_percent_threshold():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 224.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert len(changes["price_changes"]) == 1
    assert changes["price_changes"][0]["change"] == -25.0


def test_price_change_does_not_fire_below_both_thresholds():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 245.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_price_change_does_not_fire_when_pack_size_suffix_changed():
    # Same guard as shelf_changes.py: a pack-of-2 naturally costs more than
    # a single pack, so that's not a real per-unit price movement. Only
    # compare prices when the raw listing name is actually unchanged.
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 119.0)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats - Pack of 2", 189.0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []


def test_price_change_skips_none_or_nonpositive_price():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", None)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 0)]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["price_changes"] == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_oats_changes.py -v -k price_change`
Expected: 1 of 4 new tests FAIL — `test_price_change_fires_on_rupee_or_percent_threshold` fails (expects 1 price change, gets 0, since the "both present" branch has no price logic yet). The other three (`test_price_change_does_not_fire_below_both_thresholds`, `test_price_change_does_not_fire_when_pack_size_suffix_changed`, `test_price_change_skips_none_or_nonpositive_price`) all assert `price_changes == []`, which is trivially true against the current empty-list skeleton — they already pass, and become real regression coverage once Step 7 adds the price logic.

- [ ] **Step 7: Implement price comparison**

In `scripts/oats_changes.py`, replace the two `continue` branches' surrounding loop body — insert price/stock comparison after the new/gone checks, before the loop's implicit end (the `continue` statements mean this new code only runs when both entries exist):

```python
        if new_entry and not old_entry:
            new_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                  "product": new_entry["display_name"], "is_goat": is_goat})
            continue

        if old_entry and not new_entry:
            gone_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                   "product": old_entry["display_name"], "is_goat": is_goat})
            continue

        # Only compare prices/stock when the raw listing name (pack size
        # included) is actually unchanged -- see shelf_changes.py's identical
        # guard for why (confirmed real false-positive pattern there).
        if new_entry["display_name"] != old_entry["display_name"]:
            continue

        new_price, old_price = new_entry["price"], old_entry["price"]
        if new_price is not None and old_price is not None and new_price > 0 and old_price > 0:
            change_abs = abs(new_price - old_price)
            change_pct = (change_abs / old_price * 100) if old_price else 0
            if change_abs >= price_threshold_inr or change_pct >= price_threshold_pct:
                price_changes.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                       "product": new_entry["display_name"], "old_price": old_price,
                                       "new_price": new_price, "change": new_price - old_price,
                                       "is_goat": is_goat})
```

(This replaces the previous body's second `continue` and everything after it inside the `for key in ...:` loop — the two `new_products`/`gone_products` blocks stay exactly as they were in Step 3.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_oats_changes.py -v`
Expected: PASS (all 9 tests so far).

### Step group C — stock/availability changes

- [ ] **Step 9: Write the failing tests**

Append to `scripts/test_oats_changes.py`:

```python
def test_stock_flip_in_stock_to_sold_out_detected():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="SOLD OUT")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert len(changes["stock_changes"]) == 1
    assert changes["stock_changes"][0]["new_stock"] == "SOLD OUT"


def test_stock_change_skipped_when_either_side_blank():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left=None)]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="SOLD OUT")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["stock_changes"] == []


def test_stock_change_not_flagged_when_state_unchanged():
    rows_old = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    rows_new = [_row("Bangalore", "Indiranagar", "Pintola Oats", "Pintola Rolled Oats", 249.0, stock_left="In Stock")]
    changes = detect_price_availability_changes(rows_new, rows_old)
    assert changes["stock_changes"] == []
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_oats_changes.py -v -k stock`
Expected: 1 of 3 new tests FAIL — `test_stock_flip_in_stock_to_sold_out_detected` fails (expects 1 stock change, gets 0, since no stock logic exists yet). `test_stock_change_skipped_when_either_side_blank` and `test_stock_change_not_flagged_when_state_unchanged` both assert `stock_changes == []`, which is trivially true against the current skeleton — they already pass, and become real regression coverage once Step 11 adds the stock logic.

- [ ] **Step 11: Implement stock comparison**

In `scripts/oats_changes.py`, add the classifier function above `build_oats_snapshot`:

```python
_OUT_OF_STOCK_MARKERS = ("sold out", "out of stock")


def _stock_state(stock_left):
    if stock_left is None:
        return None
    s = str(stock_left).strip()
    if not s or s.lower() == "nan":
        return None
    lowered = s.lower()
    return "out" if any(marker in lowered for marker in _OUT_OF_STOCK_MARKERS) else "in"
```

Then, in `detect_price_availability_changes`, immediately after the `price_changes.append(...)` block from Step 7 (still inside the same `if new_entry["display_name"] == old_entry["display_name"]:` region — i.e. after the price `if` block, still inside the loop):

```python
        old_state = _stock_state(old_entry["stock_left"])
        new_state = _stock_state(new_entry["stock_left"])
        if old_state is not None and new_state is not None and old_state != new_state:
            stock_changes.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                   "product": new_entry["display_name"], "old_stock": old_entry["stock_left"],
                                   "new_stock": new_entry["stock_left"], "is_goat": is_goat})
```

- [ ] **Step 12: Run the full test file to verify everything passes**

Run: `cd scripts && python -m pytest test_oats_changes.py -v`
Expected: PASS (all 12 tests).

- [ ] **Step 13: Commit**

```bash
git add scripts/oats_changes.py scripts/test_oats_changes.py
git commit -m "feat: add oats_changes.py for price/availability week-over-week diffing"
```

---

## Task 3: Restructure `scripts/alerts.py` into composable sections + combined email

**Files:**
- Modify: `scripts/alerts.py` (full rewrite)
- Test: `scripts/test_alerts.py` (2 existing assertions updated, new tests added)

**Interfaces:**
- Consumes: `generate_narrative_summary`, `goat_gone_unique` from `scripts/shelf_changes.py` (existing, unchanged). Consumes the `changes` dict shape produced by `oats_changes.detect_price_availability_changes` (Task 2) for `build_oats_section_html`.
- Produces: `build_shelf_section_html(changes, label) -> str`, `build_oats_section_html(changes, label) -> str`, `build_combined_email_html(sections, new_run_label, old_run_label) -> str` where `sections: list[{"label": str, "mode": "rank" | "oats", "changes": dict}]`, and `build_email_html(changes, new_run_label, old_run_label) -> str` (back-compat wrapper, unchanged signature). Task 4 depends on `build_combined_email_html`'s exact `sections` shape and on `send_gmail` (unchanged, already in this file).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `scripts/test_alerts.py` entirely with:

```python
from alerts import build_combined_email_html, build_email_html, build_oats_section_html


def test_build_email_html_includes_narrative_and_severity():
    changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "1 CHANGES DETECTED" in html
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


def test_build_email_html_renders_detail_section_for_rank_5_plus_goat_gone():
    changes = {
        "goat_displaced": [], "goat_recovered": [], "new_products": [],
        "gone_products": [{"city": "Mumbai", "locality": "Bandra", "rank": 6,
                            "product": "GOAT Life Choco Hazelnut", "is_goat": True}],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    html = build_email_html(changes, "2026-07-13", "2026-07-06")
    assert "1 CHANGES DETECTED" in html
    assert "GOAT Life Choco Hazelnut" in html
    assert "No Longer Listed" in html


def test_build_oats_section_html_renders_only_nonempty_tables():
    changes = {
        "new_products": [{"city": "Bangalore", "locality": "Indiranagar", "brand_searched": "Pintola Oats",
                           "product": "Pintola Oats 500g", "is_goat": False}],
        "gone_products": [], "price_changes": [], "stock_changes": [],
    }
    html = build_oats_section_html(changes, "Blinkit Oats — Competitor Pricing")
    assert "Pintola Oats 500g" in html
    assert "New Products" in html
    assert "Delisted Products" not in html
    assert "Stock Changes" not in html


def test_build_oats_section_html_all_clear_message_when_nothing_changed():
    changes = {"new_products": [], "gone_products": [], "price_changes": [], "stock_changes": []}
    html = build_oats_section_html(changes, "Zepto Oats — Competitor Pricing")
    assert "No changes detected" in html


def test_build_combined_email_html_sums_totals_across_platforms():
    rank_changes = {
        "goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                             "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
        "goat_recovered": [], "new_products": [], "gone_products": [],
        "rank_intrusions": [], "rank_moved": [], "price_changes": [],
    }
    oats_changes = {
        "new_products": [{"city": "Bangalore", "locality": "Indiranagar", "brand_searched": "Pintola Oats",
                           "product": "Pintola Oats 500g", "is_goat": False}],
        "gone_products": [], "price_changes": [], "stock_changes": [],
    }
    html = build_combined_email_html(
        [
            {"label": "GOAT Life Shelf Monitor (Blinkit)", "mode": "rank", "changes": rank_changes},
            {"label": "Blinkit Oats — Competitor Pricing", "mode": "oats", "changes": oats_changes},
        ],
        "2026-07-18", "previous run",
    )
    assert "2 CHANGES DETECTED" in html
    assert "GOAT Life Shelf Monitor (Blinkit)" in html
    assert "Blinkit Oats — Competitor Pricing" in html
    assert "Pintola Oats 500g" in html


def test_build_combined_email_html_all_clear_across_all_platforms():
    empty_rank = {"goat_displaced": [], "goat_recovered": [], "new_products": [], "gone_products": [],
                  "rank_intrusions": [], "rank_moved": [], "price_changes": []}
    empty_oats = {"new_products": [], "gone_products": [], "price_changes": [], "stock_changes": []}
    html = build_combined_email_html(
        [{"label": "A", "mode": "rank", "changes": empty_rank},
         {"label": "B", "mode": "oats", "changes": empty_oats}],
        "2026-07-18", "previous run",
    )
    assert "ALL CLEAR" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_alerts.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_combined_email_html' from 'alerts'` (and the 2 updated assertions would fail against the old `alerts.py` even if imports were fixed, since it still emits `"GOAT LIFE SHELF DISRUPTED"` not `"1 CHANGES DETECTED"`).

- [ ] **Step 3: Rewrite `alerts.py`**

Replace the entire contents of `scripts/alerts.py`:

```python
"""Email alerts for the weekly competitive report. build_shelf_section_html
and build_oats_section_html each render one platform's changes as an HTML
fragment (no outer <html>/<head> wrapper); build_combined_email_html wraps
one or more fragments into a single document with one severity banner
covering all included platforms. build_email_html is a back-compat wrapper
for the single-platform (blinkit_goatlife-only) case.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shelf_changes import generate_narrative_summary, goat_gone_unique

_STYLE = """
  body { font-family: Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }
  .container { max-width: 620px; margin: 0 auto; background: white; }
  .header { background: #0d0d0d; color: white; padding: 28px 32px; }
  .severity { padding: 16px 32px; font-size: 17px; font-weight: bold; }
  .platform-title { padding: 16px 32px 0; margin: 0; font-size: 16px; border-top: 4px solid #0d0d0d; }
  .section { padding: 20px 32px; border-bottom: 1px solid #eee; }
  .alert-item { background: #fff5f5; border-left: 3px solid #e53e3e; padding: 10px 14px; margin-bottom: 8px; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { background: #f0f0f0; padding: 8px; text-align: left; }
  td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
"""


def build_shelf_section_html(changes, label):
    """HTML fragment for one rank-based (blinkit_goatlife-style) platform."""
    unique_gone = goat_gone_unique(changes)
    narrative_html = "<br>".join(generate_narrative_summary(changes))

    html = f'<h2 class="platform-title">{label}</h2>'
    html += f'<div class="section"><p>{narrative_html}</p></div>'

    if changes["goat_displaced"]:
        html += '<div class="section"><h3>GOAT Life Rank Disruptions</h3>'
        for item in changes["goat_displaced"]:
            html += (f'<div class="alert-item"><strong>{item["was"][:40]}</strong> displaced in '
                      f'{item["city"]} ({item["locality"]}) — {item["now"]}</div>')
        html += "</div>"

    if unique_gone:
        html += '<div class="section"><h3>GOAT Life Products No Longer Listed</h3>'
        for item in unique_gone:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> no longer listed in '
                      f'{item["city"]} ({item["locality"]}) — last seen rank {item["rank"]}</div>')
        html += "</div>"

    if changes["rank_intrusions"]:
        html += '<div class="section"><h3>Competitors in GOAT Territory</h3>'
        for item in changes["rank_intrusions"]:
            html += (f'<div class="alert-item"><strong>{item["intruder"][:40]}</strong> at rank '
                      f'{item["rank"]} in {item["city"]} ({item["locality"]})</div>')
        html += "</div>"

    if changes["price_changes"]:
        html += ('<div class="section"><h3>Price Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    return html


def build_oats_section_html(changes, label):
    """HTML fragment for one price/availability-based (oats platform) section."""
    html = f'<h2 class="platform-title">{label}</h2>'
    any_changes = False

    if changes["new_products"]:
        any_changes = True
        html += '<div class="section"><h3>New Products</h3>'
        for item in changes["new_products"]:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> appeared in '
                      f'{item["city"]} ({item["locality"]}) — {item["brand_searched"]}</div>')
        html += "</div>"

    if changes["gone_products"]:
        any_changes = True
        html += '<div class="section"><h3>Delisted Products</h3>'
        for item in changes["gone_products"]:
            html += (f'<div class="alert-item"><strong>{item["product"][:40]}</strong> no longer listed in '
                      f'{item["city"]} ({item["locality"]}) — {item["brand_searched"]}</div>')
        html += "</div>"

    if changes["price_changes"]:
        any_changes = True
        html += ('<div class="section"><h3>Price Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["price_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>Rs.{item["old_price"]:.0f}</td>'
                      f'<td>Rs.{item["new_price"]:.0f}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    if changes["stock_changes"]:
        any_changes = True
        html += ('<div class="section"><h3>Stock Changes</h3><table>'
                  '<tr><th>Product</th><th>Old</th><th>New</th><th>City</th></tr>')
        for item in changes["stock_changes"]:
            html += (f'<tr><td>{item["product"][:38]}</td><td>{item["old_stock"]}</td>'
                      f'<td>{item["new_stock"]}</td><td>{item["city"]}</td></tr>')
        html += "</table></div>"

    if not any_changes:
        html += '<div class="section"><p>No changes detected this week.</p></div>'

    return html


def build_combined_email_html(sections, new_run_label, old_run_label):
    """sections: list of {"label": str, "mode": "rank" | "oats", "changes": dict}.
    Renders one document: header, a total-change-count severity banner, then
    one section fragment per platform."""
    total = 0
    fragments = []
    for s in sections:
        changes = s["changes"]
        total += sum(len(v) for v in changes.values())
        if s["mode"] == "rank":
            fragments.append(build_shelf_section_html(changes, s["label"]))
        else:
            fragments.append(build_oats_section_html(changes, s["label"]))

    severity = "ALL CLEAR" if total == 0 else f"{total} CHANGES DETECTED"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
{_STYLE}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>Weekly Competitive Report</h1>
    <div>{old_run_label} to {new_run_label}</div></div>
  <div class="severity">{severity}</div>
"""
    html += "".join(fragments)
    html += "</div></body></html>"
    return html


def build_email_html(changes, new_run_label, old_run_label):
    """Back-compat single-platform wrapper (blinkit_goatlife-only callers)."""
    return build_combined_email_html(
        [{"label": "GOAT Life Shelf Monitor", "mode": "rank", "changes": changes}],
        new_run_label, old_run_label,
    )


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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_alerts.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/alerts.py scripts/test_alerts.py
git commit -m "feat: restructure alerts.py into composable per-platform sections + combined email"
```

---

## Task 4: Restructure `scripts/run_weekly.py` into a per-platform loop

**Files:**
- Modify: `scripts/run_weekly.py` (full rewrite)
- Test: `scripts/test_run_weekly.py` (new)

**Interfaces:**
- Consumes: `detect_changes` (`scripts/shelf_changes.py`, existing), `detect_price_availability_changes` (`scripts/oats_changes.py`, Task 2), `build_combined_email_html` + `send_gmail` (`scripts/alerts.py`, Task 3), `fetch_snapshot_rows` (`scripts/queries_shelf.py`, Task 1), `fetch_latest_two_scrape_run_ids` + `fetch_drop_calendar` (`scripts/queries_shelf.py`, existing), `sync_shelf_snapshots` (`scripts/sync_shelf_snapshots.py`, existing), `get_connection` (`scripts/db_connection.py`, existing).
- Produces: `process_platform(platform, conn, drop_calendar) -> dict` with keys `key, label, mode, status ("ok"|"skipped"), reason, changes, new_run_label, old_run_label`; module-level `PLATFORMS: list[dict]`; `main()` (CLI entry point, unchanged external usage: `python run_weekly.py [--dry-run]`).

### Step group A — `process_platform()` happy paths

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_run_weekly.py`:

```python
import sys

import pytest

import run_weekly
from run_weekly import process_platform


class _FakeConn:
    def close(self):
        pass


def _platform(key="testplatform", mode="rank", xlsx=None):
    return {"key": key, "label": f"Label for {key}", "mode": mode, "xlsx": xlsx}


def test_process_platform_rank_mode_returns_ok_with_changes(tmp_path, monkeypatch):
    xlsx = tmp_path / "blinkit_goatlife_data.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 2})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (2, 1))

    def _fake_fetch_snapshot_rows(conn, scrape_run_id):
        if scrape_run_id == 1:
            return [{"city_raw": "Mumbai", "locality_raw": "Bandra", "product_name": "GOAT Life Mocha Marvel",
                      "rank": 1, "selling_price": 119.0, "is_goat": True}]
        return [{"city_raw": "Mumbai", "locality_raw": "Bandra", "product_name": "Prustlr Discovery Protein Oats",
                  "rank": 1, "selling_price": 449.0, "is_goat": False}]
    monkeypatch.setattr(run_weekly, "fetch_snapshot_rows", _fake_fetch_snapshot_rows)

    platform = _platform(key="blinkit_goatlife", mode="rank", xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "ok"
    assert len(result["changes"]["goat_displaced"]) == 1
    assert result["new_run_label"] == "2"
    assert result["old_run_label"] == "1"


def test_process_platform_oats_mode_returns_ok_with_changes(tmp_path, monkeypatch):
    xlsx = tmp_path / "blinkit_oats_data.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 2})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (2, 1))

    def _fake_fetch_snapshot_rows(conn, scrape_run_id):
        if scrape_run_id == 1:
            return [{"city_raw": "Bangalore", "locality_raw": "Indiranagar", "brand_searched": "Pintola Oats",
                      "product_name": "Pintola Rolled Oats", "selling_price": 249.0, "stock_left": None,
                      "is_goat": False}]
        return [{"city_raw": "Bangalore", "locality_raw": "Indiranagar", "brand_searched": "Pintola Oats",
                  "product_name": "Pintola Rolled Oats", "selling_price": 224.0, "stock_left": None,
                  "is_goat": False}]
    monkeypatch.setattr(run_weekly, "fetch_snapshot_rows", _fake_fetch_snapshot_rows)

    platform = _platform(key="blinkit", mode="oats", xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "ok"
    assert len(result["changes"]["price_changes"]) == 1
    assert result["changes"]["price_changes"][0]["change"] == -25.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_run_weekly.py -v`
Expected: FAIL with `ImportError: cannot import name 'process_platform' from 'run_weekly'`.

- [ ] **Step 3: Rewrite `run_weekly.py` (happy-path skeleton)**

Replace the entire contents of `scripts/run_weekly.py`:

```python
"""Weekly orchestrator: sync each platform's latest scrape into Postgres,
diff it against the previous run, and email one combined report covering
all platforms.

Run this AFTER the relevant scraper(s) have finished (all local,
CAPTCHA-gated for blinkit_goatlife -- see Global Constraints in the Sprint 4
plan for why that stays unchanged). A platform's data file being missing,
locked, or having fewer than 2 scrape_runs does not block the others --
see process_platform(). Usage:
    python run_weekly.py [--dry-run]
"""
import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from alerts import build_combined_email_html, send_gmail
from db_connection import get_connection
from oats_changes import detect_price_availability_changes
from queries_shelf import fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_snapshot_rows
from shelf_changes import detect_changes
from sync_shelf_snapshots import sync_shelf_snapshots

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_OUTPUT_DIR = ROOT / "scraper" / "output"

PLATFORMS = [
    {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)",
     "xlsx": SCRAPER_OUTPUT_DIR / "blinkit_goatlife_data.xlsx", "mode": "rank"},
    {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "blinkit_oats_data.xlsx", "mode": "oats"},
    {"key": "swiggy", "label": "Swiggy Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "swiggy_oats_data.xlsx", "mode": "oats"},
    {"key": "zepto", "label": "Zepto Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "zepto_oats_data.xlsx", "mode": "oats"},
]


def process_platform(platform, conn, drop_calendar):
    """Syncs and diffs one platform. Never raises for expected per-platform
    conditions (missing file, locked file, insufficient history, sync
    failure) -- returns a status dict instead so one platform's problem
    never blocks the others.

    Returns {"key": str, "label": str, "mode": str, "status": "ok" | "skipped",
    "reason": str | None, "changes": dict | None,
    "new_run_label": str | None, "old_run_label": str | None}."""
    key, label, mode, xlsx = platform["key"], platform["label"], platform["mode"], platform["xlsx"]

    sync_result = sync_shelf_snapshots(xlsx, key, conn)
    logging.info(f"[{key}] Synced: {sync_result}")

    newest_id, second_id = fetch_latest_two_scrape_run_ids(conn, key)

    rows_new = fetch_snapshot_rows(conn, newest_id)
    rows_old = fetch_snapshot_rows(conn, second_id)
    changes = (detect_changes(rows_new, rows_old, drop_calendar=drop_calendar) if mode == "rank"
               else detect_price_availability_changes(rows_new, rows_old))

    return {"key": key, "label": label, "mode": mode, "status": "ok", "reason": None,
            "changes": changes, "new_run_label": str(newest_id), "old_run_label": str(second_id)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip sending the email — print the subject/summary instead.")
    args = parser.parse_args()

    conn = get_connection()
    try:
        drop_calendar = fetch_drop_calendar(conn)
        results = [process_platform(p, conn, drop_calendar) for p in PLATFORMS]

        for r in results:
            logging.info(f"[{r['key']}] {sum(len(v) for v in r['changes'].values())} changes")

        total = sum(sum(len(v) for v in r["changes"].values()) for r in results)
        subject = (f"Weekly Competitive Report — {total} changes detected" if total > 0
                   else "Weekly Competitive Report — All Clear")

        if args.dry_run:
            logging.info(f"[--dry-run] Would send: {subject}")
            return

        sections = [{"label": r["label"], "mode": r["mode"], "changes": r["changes"]} for r in results]
        html = build_combined_email_html(sections, date.today().isoformat(), "previous run")

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_run_weekly.py -v`
Expected: PASS (both tests from step 1).

### Step group B — per-platform error isolation

- [ ] **Step 5: Write the failing tests**

Append to `scripts/test_run_weekly.py`:

```python
def test_process_platform_missing_file_returns_skipped(tmp_path, monkeypatch):
    def _fail_if_called(*a, **k):
        raise AssertionError("sync_shelf_snapshots should not be called for a missing file")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _fail_if_called)

    platform = _platform(xlsx=tmp_path / "does_not_exist.xlsx")
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "no data available"
    assert result["changes"] is None


def test_process_platform_permission_error_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "locked.xlsx"
    xlsx.write_text("placeholder")

    def _raise_permission_error(*a, **k):
        raise PermissionError("file is open in Excel")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _raise_permission_error)

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert "locked" in result["reason"]


def test_process_platform_sync_failure_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "bad.xlsx"
    xlsx.write_text("placeholder")

    def _raise_value_error(*a, **k):
        raise ValueError("malformed xlsx")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _raise_value_error)

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "sync failed"


def test_process_platform_insufficient_history_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "fresh.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 5})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (42, None))

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "not enough history yet"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_run_weekly.py -v -k "missing_file or permission_error or sync_failure or insufficient_history"`
Expected: FAIL on all 4 — `test_process_platform_missing_file_returns_skipped` raises `AssertionError` from inside `_fail_if_called` (the current code calls `sync_shelf_snapshots` unconditionally, with no existence check first); `test_process_platform_permission_error_returns_skipped` raises `PermissionError` uncaught; `test_process_platform_sync_failure_returns_skipped` raises `ValueError` uncaught; `test_process_platform_insufficient_history_returns_skipped` raises `AttributeError` (the skeleton doesn't check for `second_id is None`, so it proceeds to call the real `fetch_snapshot_rows(conn, None)` against `_FakeConn`, which only defines `close()` — no `.cursor()`).

- [ ] **Step 7: Add per-platform isolation to `process_platform`**

In `scripts/run_weekly.py`, replace `process_platform`:

```python
def process_platform(platform, conn, drop_calendar):
    """Syncs and diffs one platform. Never raises for expected per-platform
    conditions (missing file, locked file, insufficient history, sync
    failure) -- returns a status dict instead so one platform's problem
    never blocks the others.

    Returns {"key": str, "label": str, "mode": str, "status": "ok" | "skipped",
    "reason": str | None, "changes": dict | None,
    "new_run_label": str | None, "old_run_label": str | None}."""
    key, label, mode, xlsx = platform["key"], platform["label"], platform["mode"], platform["xlsx"]
    skipped = {"key": key, "label": label, "mode": mode, "status": "skipped",
               "changes": None, "new_run_label": None, "old_run_label": None}

    if not xlsx.exists():
        logging.warning(f"[{key}] Scraper output not found: {xlsx} — skipping this platform.")
        return {**skipped, "reason": "no data available"}

    try:
        sync_result = sync_shelf_snapshots(xlsx, key, conn)
        logging.info(f"[{key}] Synced: {sync_result}")
    except PermissionError:
        logging.warning(f"[{key}] {xlsx} is locked (open in Excel?) — skipping, try again next cycle.")
        return {**skipped, "reason": "file locked, try again next cycle"}
    except Exception:
        logging.exception(f"[{key}] Sync failed — skipping this platform.")
        return {**skipped, "reason": "sync failed"}

    newest_id, second_id = fetch_latest_two_scrape_run_ids(conn, key)
    if second_id is None:
        logging.warning(f"[{key}] Only one scrape_run exists — nothing to compare against yet.")
        return {**skipped, "reason": "not enough history yet"}

    rows_new = fetch_snapshot_rows(conn, newest_id)
    rows_old = fetch_snapshot_rows(conn, second_id)
    changes = (detect_changes(rows_new, rows_old, drop_calendar=drop_calendar) if mode == "rank"
               else detect_price_availability_changes(rows_new, rows_old))

    return {"key": key, "label": label, "mode": mode, "status": "ok", "reason": None,
            "changes": changes, "new_run_label": str(newest_id), "old_run_label": str(second_id)}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd scripts && python -m pytest test_run_weekly.py -v`
Expected: PASS (all 6 tests so far).

### Step group C — `main()` orchestration: partial success, dry-run, total failure

- [ ] **Step 9: Write the failing tests**

Append to `scripts/test_run_weekly.py`:

```python
def test_main_continues_when_one_platform_skipped_and_sends_no_email_on_dry_run(monkeypatch):
    ok_changes = {"goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                                       "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
                  "goat_recovered": [], "new_products": [], "gone_products": [],
                  "rank_intrusions": [], "rank_moved": [], "price_changes": []}

    def _fake_process_platform(platform, conn, drop_calendar):
        if platform["key"] == "blinkit_goatlife":
            return {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "mode": "rank",
                    "status": "ok", "reason": None, "changes": ok_changes,
                    "new_run_label": "2", "old_run_label": "1"}
        return {"key": platform["key"], "label": platform["label"], "mode": platform["mode"],
                "status": "skipped", "reason": "no data available", "changes": None,
                "new_run_label": None, "old_run_label": None}

    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "xlsx": None, "mode": "rank"},
        {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "xlsx": None, "mode": "oats"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", _fake_process_platform)
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())

    def _fail_if_called(*a, **k):
        raise AssertionError("send_gmail should not be called during --dry-run")
    monkeypatch.setattr(run_weekly, "send_gmail", _fail_if_called)

    monkeypatch.setattr(sys, "argv", ["run_weekly.py", "--dry-run"])
    run_weekly.main()  # must not raise


def test_main_sends_combined_email_when_ok_results_exist(monkeypatch):
    ok_changes = {"new_products": [{"city": "Bangalore", "locality": "Indiranagar",
                                     "brand_searched": "Pintola Oats", "product": "Pintola Oats 500g",
                                     "is_goat": False}],
                  "gone_products": [], "price_changes": [], "stock_changes": []}

    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "xlsx": None, "mode": "oats"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", lambda platform, conn, drop_calendar: {
        "key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "mode": "oats",
        "status": "ok", "reason": None, "changes": ok_changes,
        "new_run_label": "2", "old_run_label": "1",
    })
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())

    sent = {}
    def _fake_send_gmail(subject, html_body, sender, app_password, recipients):
        sent["subject"] = subject
        sent["html_body"] = html_body
    monkeypatch.setattr(run_weekly, "send_gmail", _fake_send_gmail)

    monkeypatch.setenv("GMAIL_SENDER", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("GMAIL_RECIPIENTS", "a@example.com,b@example.com")
    monkeypatch.setattr(sys, "argv", ["run_weekly.py"])

    run_weekly.main()

    assert "1 changes detected" in sent["subject"]
    assert "Pintola Oats 500g" in sent["html_body"]


def test_main_exits_nonzero_when_all_platforms_skipped(monkeypatch):
    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "xlsx": None, "mode": "rank"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", lambda platform, conn, drop_calendar: {
        "key": platform["key"], "label": platform["label"], "mode": platform["mode"],
        "status": "skipped", "reason": "no data available", "changes": None,
        "new_run_label": None, "old_run_label": None,
    })
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())
    monkeypatch.setattr(sys, "argv", ["run_weekly.py"])

    with pytest.raises(SystemExit) as exc_info:
        run_weekly.main()
    assert exc_info.value.code == 1
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd scripts && python -m pytest test_run_weekly.py -v -k "test_main"`
Expected: 2 of the 3 FAIL — `test_main_continues_when_one_platform_skipped_and_sends_no_email_on_dry_run` and `test_main_exits_nonzero_when_all_platforms_skipped` both raise `AttributeError: 'NoneType' object has no attribute 'values'` inside `main()`'s logging loop (`sum(len(v) for v in r['changes'].values())` — the skipped platform's `changes` is `None`, and nothing filters it out yet). `test_main_sends_combined_email_when_ok_results_exist` has no skipped platform in its scenario, so it already PASSES against the current `main()` — it's included here as regression coverage for the final behavior, not as a new-failure case.

- [ ] **Step 11: Make `main()` skip-aware**

In `scripts/run_weekly.py`, replace `main()`'s body between `results = [...]` and the email-building section:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip sending the email — print the subject/summary instead.")
    args = parser.parse_args()

    conn = get_connection()
    try:
        drop_calendar = fetch_drop_calendar(conn)
        results = [process_platform(p, conn, drop_calendar) for p in PLATFORMS]

        for r in results:
            if r["status"] == "skipped":
                logging.info(f"[{r['key']}] Skipped: {r['reason']}")
            else:
                logging.info(f"[{r['key']}] {sum(len(v) for v in r['changes'].values())} changes")

        ok_results = [r for r in results if r["status"] == "ok"]
        if not ok_results:
            logging.error("Every platform was skipped — nothing to report.")
            sys.exit(1)

        total = sum(sum(len(v) for v in r["changes"].values()) for r in ok_results)
        subject = (f"Weekly Competitive Report — {total} changes detected" if total > 0
                   else "Weekly Competitive Report — All Clear")

        if args.dry_run:
            logging.info(f"[--dry-run] Would send: {subject}")
            return

        sections = [{"label": r["label"], "mode": r["mode"], "changes": r["changes"]} for r in ok_results]
        html = build_combined_email_html(sections, date.today().isoformat(), "previous run")

        sender = os.environ["GMAIL_SENDER"]
        app_password = os.environ["GMAIL_APP_PASSWORD"]
        recipients = os.environ["GMAIL_RECIPIENTS"].split(",")
        send_gmail(subject, html, sender, app_password, recipients)
        logging.info(f"Sent: {subject}")
    finally:
        conn.close()
```

- [ ] **Step 12: Run the full test file to verify everything passes**

Run: `cd scripts && python -m pytest test_run_weekly.py -v`
Expected: PASS (all 9 tests).

- [ ] **Step 13: Commit**

```bash
git add scripts/run_weekly.py scripts/test_run_weekly.py
git commit -m "feat: extend run_weekly.py to loop over all 4 platforms with per-platform isolation"
```

---

## Task 5: Live verification against the real database and xlsx files

**Files:** None modified — this task runs the assembled pipeline end to end.

**Interfaces:** None new — exercises `scripts/run_weekly.py`'s `main()` as a real user would.

- [ ] **Step 1: Run the full scripts/ test suite together**

Run: `cd scripts && python -m pytest -v`
Expected: PASS for every test file (existing tests untouched, plus the new/modified ones from Tasks 1-4). If any pre-existing `requires_db` test fails, check `DATABASE_URL` in `.env` before proceeding — do not skip investigating.

- [ ] **Step 2: Dry-run against the real database and xlsx files**

Run: `cd scripts && python run_weekly.py --dry-run`

Read the log output line by line. Confirm:
- All 4 platforms (`blinkit_goatlife`, `blinkit`, `swiggy`, `zepto`) appear in the log, each with either a change count or a skip reason — no platform silently missing.
- Any platform logged as "Skipped: not enough history yet" should be one with fewer than 2 `scrape_run` rows in the database — cross-check with a manual query if anything looks off:
  `python -c "from db_connection import get_connection; c = get_connection(); cur = c.cursor(); cur.execute(\"SELECT platform, count(*) FROM scrape_runs GROUP BY platform;\"); print(cur.fetchall()); c.close()"`
- The final `[--dry-run] Would send: ...` line shows a subject line summing changes only across platforms that actually produced a diff (skipped platforms excluded from the total).
- No unhandled traceback — a traceback here means a real edge case in the production xlsx data wasn't covered by Task 2/4's tests; if one occurs, add a regression test reproducing it to the relevant test file before fixing.

- [ ] **Step 3: Confirm skip reasons match real platform state**

If any platform's oats xlsx file was open in Excel or mid-write when Step 2 ran, re-run Step 2 after closing it and confirm that platform now reports a real diff instead of "file locked."

- [ ] **Step 4: Record the verification outcome**

No code changes in this task. If Step 2 required no fixes, there is nothing to commit. If Step 2 surfaced a bug, fix it under a new regression test in the appropriate task's test file, re-run that file's full suite, then commit with a message describing the specific edge case found (not a generic "fix bug" message).
