# Scraper Parallelization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `blinkit_oats.py` and `zepto_oats.py`'s ~14-15h sequential runtime by splitting each into 3 parallel worker processes, while staying within the machine's 7.7GB RAM budget and surviving individual worker crashes without losing progress.

**Architecture:** A generic supervisor (`parallel_runner.py`) shards the 500-locality list round-robin across N worker subprocesses (each an unmodified invocation of the existing scraper script, just scoped to its shard via new `--shard-index`/`--num-shards` CLI flags). Workers write to their own shard file; the supervisor periodically merges all shard files into the single combined file the rest of the pipeline already reads, re-sorted into the same canonical order the sequential scraper already produces. Crashed workers are auto-restarted (capped) by the supervisor.

**Tech Stack:** Python 3.13, `subprocess` (process isolation), `openpyxl` (existing `IncrementalWorkbook` + new merge logic), `psutil` (RAM checks, already installed in the environment that runs these scrapers), `pytest` (existing test suite conventions).

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-17-scraper-parallelization-design.md` — this plan implements it exactly; consult it for the "why" behind any decision below.
- Scope is `blinkit_oats.py` and `zepto_oats.py` only. Do not touch `swiggy_oats.py` or `blinkit_goatlife.py`.
- 3 workers per scraper is the target worker count (not configurable via requirements, but the code should accept any `--workers N` since it costs nothing extra).
- The final combined output file must remain at today's exact path (`scraper/output/blinkit_oats_data.xlsx` / `scraper/output/zepto_oats_data.xlsx`) with the same columns — nothing downstream changes.
- No headless Chrome, no cloud/Colab execution (see spec's "Why not Colab" section) — workers still open real, visible Chrome windows exactly as today.
- All existing scraping logic (interstitial dismissal, location-bar reopen, per-locality retry/dead-session recovery, brand-search wait logic) must remain untouched. Only "which localities to iterate" and "which file to save to" become parameterizable.
- Every new pure/orchestration function must be unit-testable without spawning a real subprocess or real Chrome — use dependency injection (`popen_fn`, `sleep_fn`, `time_fn`, `ram_check_fn`, `merge_fn` parameters) exactly as specified in each task below.
- Test file conventions already established in this repo (see `scraper/test_reliability.py`, `scraper/test_blinkit_oats.py`): plain `assert`, `tmp_path` fixture for file I/O, no mocking frameworks — the codebase does not use `unittest.mock`, prefer small fake classes/closures instead.
- Run tests with: `cd scraper && py -m pytest <file> -q` (the `py` launcher resolves to the Python install that actually has `selenium`/`undetected_chromedriver`/`psutil` — confirmed working during this session; do **not** use `.venv`'s python, which lacks these packages).

---

### Task 1: `shard_localities()` in `_reliability.py`

**Files:**
- Modify: `scraper/_reliability.py`
- Test: `scraper/test_reliability.py`

**Interfaces:**
- Produces: `shard_localities(localities: list, shard_index: int, num_shards: int) -> list` — round-robin slice, importable by both scrapers and `parallel_runner.py`.

- [ ] **Step 1: Write the failing tests**

Add to `scraper/test_reliability.py` (append at the end of the file, after `test_incremental_workbook_resumes_from_existing_file`):

```python
from _reliability import shard_localities


def test_shard_localities_round_robin_covers_all_with_no_duplicates():
    localities = list(range(10))
    shard0 = shard_localities(localities, 0, 3)
    shard1 = shard_localities(localities, 1, 3)
    shard2 = shard_localities(localities, 2, 3)

    assert shard0 == [0, 3, 6, 9]
    assert shard1 == [1, 4, 7]
    assert shard2 == [2, 5, 8]
    assert sorted(shard0 + shard1 + shard2) == localities


def test_shard_localities_single_shard_returns_everything():
    localities = ["a", "b", "c"]
    assert shard_localities(localities, 0, 1) == localities
```

Also add `shard_localities` to the existing `from _reliability import (...)` block at the top of the file (alphabetical, matching the existing style):

```python
from _reliability import (
    IncrementalWorkbook,
    defeat_visibility_throttling,
    is_blocked,
    is_dead_session_error,
    jittered_sleep,
    keep_window_unminimized,
    should_restart_driver,
    shard_localities,
    wait_for_manual_unblock,
)
```

(Remove the separate `from _reliability import shard_localities` line added above — fold it into this one import block instead.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && py -m pytest test_reliability.py -k shard_localities -v`
Expected: FAIL with `ImportError: cannot import name 'shard_localities'`

- [ ] **Step 3: Implement `shard_localities` in `_reliability.py`**

In `scraper/_reliability.py`, add this function after `jittered_sleep` (before `should_restart_driver`):

```python
def shard_localities(localities: list, shard_index: int, num_shards: int) -> list:
    """Round-robin split so each shard gets an even spread across the whole
    list rather than one contiguous block -- if a particular city has
    connectivity/blocking trouble, that risk is spread across shards
    instead of concentrated in whichever shard owns that city's block."""
    return localities[shard_index::num_shards]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && py -m pytest test_reliability.py -v`
Expected: all PASS (including the two new tests and all pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add scraper/_reliability.py scraper/test_reliability.py
git commit -m "feat: add shard_localities helper for parallel scraper workers"
```

---

### Task 2: `merge_shards()` in new `scraper/_merge.py`

**Files:**
- Create: `scraper/_merge.py`
- Test: `scraper/test_merge.py` (new)

**Interfaces:**
- Consumes: nothing from other tasks (standalone module, only depends on `openpyxl` which is already a project dependency).
- Produces: `merge_shards(shard_paths: list, output_path, columns: list[str], sort_key_fn) -> int` — reads all existing shard files, sorts combined rows with `sort_key_fn(row_dict) -> sortable`, atomically writes `output_path`, returns row count written. Raises `PermissionError` if `output_path` is locked by another program. Used by `parallel_runner.py` in Task 5.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_merge.py`:

```python
from openpyxl import Workbook, load_workbook

from _merge import merge_shards


def _write_shard(path, columns, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_merge_shards_combines_and_sorts(tmp_path):
    columns = ["City", "Locality", "Brand Searched", "Price"]
    shard0 = tmp_path / "shard0.xlsx"
    shard1 = tmp_path / "shard1.xlsx"
    _write_shard(shard0, columns, [
        ("Bangalore", "Koramangala", "Quaker", 86),
    ])
    _write_shard(shard1, columns, [
        ("Bangalore", "Indiranagar", "Pintola", 550),
    ])
    output = tmp_path / "combined.xlsx"

    rank = {("Bangalore", "Indiranagar"): 0, ("Bangalore", "Koramangala"): 1}

    def sort_key(row):
        return (rank.get((row["City"], row["Locality"]), 999), row["Brand Searched"])

    n = merge_shards([shard0, shard1], output, columns, sort_key)

    assert n == 2
    result = load_workbook(output)
    rows = list(result.active.iter_rows(values_only=True))
    assert rows[0] == tuple(columns)
    assert rows[1] == ("Bangalore", "Indiranagar", "Pintola", 550)
    assert rows[2] == ("Bangalore", "Koramangala", "Quaker", 86)


def test_merge_shards_skips_missing_shard_files(tmp_path):
    columns = ["City", "Locality"]
    shard0 = tmp_path / "shard0.xlsx"
    missing = tmp_path / "does_not_exist.xlsx"
    _write_shard(shard0, columns, [("Bangalore", "Koramangala")])
    output = tmp_path / "combined.xlsx"

    n = merge_shards([shard0, missing], output, columns, lambda row: row["Locality"])

    assert n == 1


def test_merge_shards_overwrites_existing_output(tmp_path):
    columns = ["City", "Locality"]
    shard0 = tmp_path / "shard0.xlsx"
    _write_shard(shard0, columns, [("Bangalore", "Koramangala")])
    output = tmp_path / "combined.xlsx"
    _write_shard(output, columns, [("Stale", "Data")])  # simulate a prior merge

    n = merge_shards([shard0], output, columns, lambda row: row["Locality"])

    assert n == 1
    result = load_workbook(output)
    rows = list(result.active.iter_rows(values_only=True))
    assert rows == [tuple(columns), ("Bangalore", "Koramangala")]


def test_merge_shards_returns_zero_when_no_shards_exist(tmp_path):
    output = tmp_path / "combined.xlsx"
    n = merge_shards([tmp_path / "missing.xlsx"], output, ["City"], lambda row: row["City"])
    assert n == 0
    assert output.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && py -m pytest test_merge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '_merge'`

- [ ] **Step 3: Implement `scraper/_merge.py`**

```python
"""Combines per-shard scraper output files into a single, canonically
ordered output file. Used by parallel_runner.py so a parallelized scrape
still produces one file at the same path the rest of the pipeline reads."""
import os
from pathlib import Path

from openpyxl import Workbook, load_workbook


def merge_shards(shard_paths, output_path, columns, sort_key_fn):
    """Reads whatever rows exist across shard_paths (skipping any that
    don't exist yet -- a worker may not have saved its first row), sorts
    them with sort_key_fn, and atomically replaces output_path with the
    result. Returns the number of rows written. Raises PermissionError if
    output_path is locked by another program (e.g. open in Excel) --
    callers should treat that as "try again next cycle", not fatal."""
    rows = []
    for path in shard_paths:
        path = Path(path)
        if not path.exists():
            continue
        wb = load_workbook(path, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            wb.close()
            continue
        for row in rows_iter:
            rows.append(dict(zip(header, row)))
        wb.close()

    rows.sort(key=sort_key_fn)

    output_path = Path(output_path)
    tmp_path = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
    out_wb = Workbook()
    out_ws = out_wb.active
    out_ws.append(columns)
    for row in rows:
        out_ws.append([row.get(c) for c in columns])
    out_wb.save(tmp_path)
    out_wb.close()
    os.replace(tmp_path, output_path)  # atomic on the same filesystem
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && py -m pytest test_merge.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/_merge.py scraper/test_merge.py
git commit -m "feat: add merge_shards for combining parallel worker output files"
```

---

### Task 3: Shard support in `blinkit_oats.py`

**Files:**
- Modify: `scraper/blinkit_oats.py`
- Test: `scraper/test_blinkit_oats.py`

**Interfaces:**
- Consumes: `shard_localities` from Task 1 (`_reliability`).
- Produces: `build_target_localities() -> list[dict]` (each dict has `locality`, `city`, `price` keys), `make_sort_key_fn(target_localities) -> callable` (row-dict → sortable key, for Task 5's merge call), `main(target_localities=None, output_file=None)` (existing function, now parameterized — calling `main()` with no args behaves exactly as before).

- [ ] **Step 1: Write the failing tests**

In `scraper/test_blinkit_oats.py`, change the import line at the top from:

```python
from blinkit_oats import (
    extract_buy_price, get_brand_keyword, has_sponsored_badge, is_goat_product, is_oats_product,
)
```

to:

```python
from blinkit_oats import (
    BRANDS, build_target_localities, extract_buy_price, get_brand_keyword,
    has_sponsored_badge, is_goat_product, is_oats_product, make_sort_key_fn,
)
```

Then append these tests at the end of the file:

```python
def test_build_target_localities_covers_all_cities_at_top_n():
    localities = build_target_localities()
    assert len(localities) > 0
    for loc in localities:
        assert set(loc.keys()) == {"locality", "city", "price"}
    cities = {loc["city"] for loc in localities}
    assert len(cities) == 10  # matches data/magicbricks_combined.xlsx's 10 cities
    for city in cities:
        assert sum(1 for loc in localities if loc["city"] == city) == 50


def test_make_sort_key_fn_orders_by_locality_rank_then_brand_rank():
    target_localities = [
        {"locality": "Indiranagar", "city": "Bangalore", "price": 26750},
        {"locality": "Koramangala", "city": "Bangalore", "price": 21450},
    ]
    sort_key = make_sort_key_fn(target_localities)

    rows = [
        {"City": "Bangalore", "Locality": "Koramangala", "Brand Searched": BRANDS[0]},
        {"City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": BRANDS[1]},
        {"City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": BRANDS[0]},
    ]
    ordered = sorted(rows, key=sort_key)

    assert ordered == [
        {"City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": BRANDS[0]},
        {"City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": BRANDS[1]},
        {"City": "Bangalore", "Locality": "Koramangala", "Brand Searched": BRANDS[0]},
    ]


def test_make_sort_key_fn_puts_unknown_rows_last():
    target_localities = [{"locality": "Indiranagar", "city": "Bangalore", "price": 26750}]
    sort_key = make_sort_key_fn(target_localities)
    known = {"City": "Bangalore", "Locality": "Indiranagar", "Brand Searched": BRANDS[0]}
    unknown = {"City": "Delhi", "Locality": "Saket", "Brand Searched": "Nonexistent Brand"}
    assert sort_key(known) < sort_key(unknown)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && py -m pytest test_blinkit_oats.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_target_localities'`

- [ ] **Step 3: Refactor `blinkit_oats.py`**

First, update the `_reliability` import block near the top of `scraper/blinkit_oats.py` from:

```python
from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, dismiss_blinkit_interstitials,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    should_restart_driver, wait_for_manual_unblock,
)
```

to:

```python
from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, dismiss_blinkit_interstitials,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    shard_localities, should_restart_driver, wait_for_manual_unblock,
)
```

Next, find this block (currently the start of `main()`):

```python
# ─────────────────────────────────────────────
def main():
    print("="*65, flush=True)
    print("  BLINKIT OATS SCRAPER — Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("="*65, flush=True)

    df_mb = pd.read_excel(MAGICBRICKS_FILE)
    df_mb['avg_buy_price'] = df_mb['price range(for residential, office space, shop)'].apply(extract_buy_price)

    target_localities = []
    for city in df_mb['ADDRESS'].unique():
        city_df = df_mb[df_mb['ADDRESS'] == city].copy()
        top = city_df[city_df['avg_buy_price'] > 0].nlargest(TOP_N, 'avg_buy_price')
        if len(top) < TOP_N:
            pad = city_df[city_df['avg_buy_price'] == 0].head(TOP_N - len(top))
            top = pd.concat([top, pad])
        for _, row in top.iterrows():
            area = str(row['AREA']).split(',')[0].strip()
            target_localities.append({'locality': area, 'city': city, 'price': row['avg_buy_price']})

    print(f"\n📋 Localities: {len(target_localities)} | Brands: {len(BRANDS)} | Est. searches: {len(target_localities)*len(BRANDS)}", flush=True)

    wb = IncrementalWorkbook(OUTPUT_FILE, columns=COLUMNS)
```

Replace it with:

```python
# ─────────────────────────────────────────────
def build_target_localities():
    df_mb = pd.read_excel(MAGICBRICKS_FILE)
    df_mb['avg_buy_price'] = df_mb['price range(for residential, office space, shop)'].apply(extract_buy_price)

    target_localities = []
    for city in df_mb['ADDRESS'].unique():
        city_df = df_mb[df_mb['ADDRESS'] == city].copy()
        top = city_df[city_df['avg_buy_price'] > 0].nlargest(TOP_N, 'avg_buy_price')
        if len(top) < TOP_N:
            pad = city_df[city_df['avg_buy_price'] == 0].head(TOP_N - len(top))
            top = pd.concat([top, pad])
        for _, row in top.iterrows():
            area = str(row['AREA']).split(',')[0].strip()
            target_localities.append({'locality': area, 'city': city, 'price': row['avg_buy_price']})
    return target_localities


def make_sort_key_fn(target_localities):
    """Ranks a merged row the same way the sequential scraper already
    orders its output -- by locality's position in target_localities, then
    brand's position in BRANDS -- so parallel_runner.py's periodic merge
    produces a file that reads identically to a single-worker run,
    regardless of which shard actually scraped which row."""
    locality_rank = {(loc['city'], loc['locality']): i for i, loc in enumerate(target_localities)}
    brand_rank = {b: i for i, b in enumerate(BRANDS)}

    def sort_key(row):
        loc_rank = locality_rank.get((row.get('City'), row.get('Locality')), len(locality_rank))
        b_rank = brand_rank.get(row.get('Brand Searched'), len(brand_rank))
        return (loc_rank, b_rank)

    return sort_key


# ─────────────────────────────────────────────
def main(target_localities=None, output_file=None):
    print("="*65, flush=True)
    print("  BLINKIT OATS SCRAPER — Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("="*65, flush=True)

    if target_localities is None:
        target_localities = build_target_localities()
    if output_file is None:
        output_file = OUTPUT_FILE

    print(f"\n📋 Localities: {len(target_localities)} | Brands: {len(BRANDS)} | Est. searches: {len(target_localities)*len(BRANDS)}", flush=True)

    wb = IncrementalWorkbook(output_file, columns=COLUMNS)
```

Next, find the final-save print inside the `finally` block later in `main()`:

```python
    finally:
        wb.save()
        print(f"\n✅ Final save → {OUTPUT_FILE}", flush=True)
```

Replace with:

```python
    finally:
        wb.save()
        print(f"\n✅ Final save → {output_file}", flush=True)
```

Finally, find the bottom of the file:

```python
if __name__ == "__main__":
    main()
```

Replace with:

```python
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, default=None,
                         help="This worker's shard number (0-based). Required with --num-shards > 1.")
    parser.add_argument("--num-shards", type=int, default=1,
                         help="Total number of shards. Omit (or 1) to scrape all 500 localities normally.")
    args = parser.parse_args()

    if args.num_shards > 1:
        if args.shard_index is None:
            parser.error("--shard-index is required when --num-shards > 1")
        all_localities = build_target_localities()
        shard = shard_localities(all_localities, args.shard_index, args.num_shards)
        shard_output = ROOT / "scraper" / "output" / "_shards" / f"blinkit_oats_shard{args.shard_index}.xlsx"
        main(target_localities=shard, output_file=shard_output)
    else:
        main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && py -m pytest test_blinkit_oats.py -v`
Expected: all PASS (existing tests plus the 3 new ones)

Also run the full existing suite to make sure nothing else broke:
Run: `cd scraper && py -m pytest test_reliability.py test_blinkit_oats.py test_blinkit_goatlife.py test_swiggy_oats.py test_zepto_oats.py -q`
Expected: all PASS

- [ ] **Step 5: Manually verify normal (non-sharded) invocation still parses correctly**

Run: `cd scraper && py blinkit_oats.py --help`
Expected: argparse help text listing `--shard-index` and `--num-shards`, exits 0 without opening a browser.

- [ ] **Step 6: Commit**

```bash
git add scraper/blinkit_oats.py scraper/test_blinkit_oats.py
git commit -m "feat: add shard/CLI support to blinkit_oats.py for parallel workers"
```

---

### Task 4: Shard support in `zepto_oats.py`

**Files:**
- Modify: `scraper/zepto_oats.py`
- Test: `scraper/test_zepto_oats.py`

**Interfaces:**
- Consumes: `shard_localities` from Task 1 (`_reliability`).
- Produces: `make_sort_key_fn(localities) -> callable` (row-dict → sortable key). `load_localities` already exists and is reused as-is. `scrape_zepto(localities=None, output_file=None)` (existing function, now parameterized).

- [ ] **Step 1: Write the failing tests**

In `scraper/test_zepto_oats.py`, change the import line at the top from:

```python
from zepto_oats import has_sponsored_badge, is_oats_product, parse_zepto_card
```

to:

```python
from zepto_oats import BRANDS, has_sponsored_badge, is_oats_product, make_sort_key_fn, parse_zepto_card
```

Then append these tests at the end of the file:

```python
def test_make_sort_key_fn_orders_by_locality_rank_then_brand_rank():
    localities = [
        {"loc_str": "Indiranagar, Bangalore", "price": 26750, "price_str": "Rs.26,750/sqft"},
        {"loc_str": "Koramangala, Bangalore", "price": 21450, "price_str": "Rs.21,450/sqft"},
    ]
    sort_key = make_sort_key_fn(localities)

    rows = [
        {"Locality": "Koramangala, Bangalore", "Brand Searched": BRANDS[0]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[1]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]},
    ]
    ordered = sorted(rows, key=sort_key)

    assert ordered == [
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]},
        {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[1]},
        {"Locality": "Koramangala, Bangalore", "Brand Searched": BRANDS[0]},
    ]


def test_make_sort_key_fn_puts_unknown_rows_last():
    localities = [{"loc_str": "Indiranagar, Bangalore", "price": 26750, "price_str": "Rs.26,750/sqft"}]
    sort_key = make_sort_key_fn(localities)
    known = {"Locality": "Indiranagar, Bangalore", "Brand Searched": BRANDS[0]}
    unknown = {"Locality": "Saket, Delhi", "Brand Searched": "Nonexistent Brand"}
    assert sort_key(known) < sort_key(unknown)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && py -m pytest test_zepto_oats.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_sort_key_fn'`

- [ ] **Step 3: Refactor `zepto_oats.py`**

Update the `_reliability` import block near the top of `scraper/zepto_oats.py` from:

```python
from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, is_blocked,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    should_restart_driver, wait_for_manual_unblock,
)
```

to:

```python
from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, is_blocked,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    shard_localities, should_restart_driver, wait_for_manual_unblock,
)
```

Next, add `make_sort_key_fn` right after `load_localities` (before `parse_zepto_card`):

```python
def make_sort_key_fn(localities):
    """Ranks a merged row the same way the sequential scraper already
    orders its output -- by locality's position in `localities`, then
    brand's position in BRANDS -- so parallel_runner.py's periodic merge
    produces a file that reads identically to a single-worker run,
    regardless of which shard actually scraped which row."""
    locality_rank = {loc['loc_str']: i for i, loc in enumerate(localities)}
    brand_rank = {b: i for i, b in enumerate(BRANDS)}

    def sort_key(row):
        loc_rank = locality_rank.get(row.get('Locality'), len(locality_rank))
        b_rank = brand_rank.get(row.get('Brand Searched'), len(brand_rank))
        return (loc_rank, b_rank)

    return sort_key
```

Next, find the start of `scrape_zepto()`:

```python
def scrape_zepto():
    print("=================================================================", flush=True)
    print("  ZEPTO INSTAMART OATS SCRAPER - Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("=================================================================\n", flush=True)

    localities = load_localities(str(MAGICBRICKS_FILE))
    if not localities:
        print("No localities found. Exiting.", flush=True)
        return

    print(f"📋 Localities: {len(localities)} | Brands: {len(BRANDS)} | Est. searches: {len(localities)*len(BRANDS)}\n", flush=True)

    wb = IncrementalWorkbook(OUTPUT_FILE, columns=COLUMNS)
```

Replace with:

```python
def scrape_zepto(localities=None, output_file=None):
    print("=================================================================", flush=True)
    print("  ZEPTO INSTAMART OATS SCRAPER - Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("=================================================================\n", flush=True)

    if localities is None:
        localities = load_localities(str(MAGICBRICKS_FILE))
    if output_file is None:
        output_file = OUTPUT_FILE
    if not localities:
        print("No localities found. Exiting.", flush=True)
        return

    print(f"📋 Localities: {len(localities)} | Brands: {len(BRANDS)} | Est. searches: {len(localities)*len(BRANDS)}\n", flush=True)

    wb = IncrementalWorkbook(output_file, columns=COLUMNS)
```

Next, find the final-save print inside the `finally` block later in `scrape_zepto()`:

```python
    finally:
        wb.save()
        print(f"\n✅ Final save → {OUTPUT_FILE}", flush=True)
```

Replace with:

```python
    finally:
        wb.save()
        print(f"\n✅ Final save → {output_file}", flush=True)
```

Finally, find the bottom of the file:

```python
if __name__ == "__main__":
    scrape_zepto()
```

Replace with:

```python
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, default=None,
                         help="This worker's shard number (0-based). Required with --num-shards > 1.")
    parser.add_argument("--num-shards", type=int, default=1,
                         help="Total number of shards. Omit (or 1) to scrape all 500 localities normally.")
    args = parser.parse_args()

    if args.num_shards > 1:
        if args.shard_index is None:
            parser.error("--shard-index is required when --num-shards > 1")
        all_localities = load_localities(str(MAGICBRICKS_FILE))
        shard = shard_localities(all_localities, args.shard_index, args.num_shards)
        shard_output = ROOT / "scraper" / "output" / "_shards" / f"zepto_oats_shard{args.shard_index}.xlsx"
        scrape_zepto(localities=shard, output_file=shard_output)
    else:
        scrape_zepto()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && py -m pytest test_zepto_oats.py -v`
Expected: all PASS (existing tests plus the 2 new ones)

Also run the full existing suite:
Run: `cd scraper && py -m pytest test_reliability.py test_blinkit_oats.py test_blinkit_goatlife.py test_swiggy_oats.py test_zepto_oats.py -q`
Expected: all PASS

- [ ] **Step 5: Manually verify normal (non-sharded) invocation still parses correctly**

Run: `cd scraper && py zepto_oats.py --help`
Expected: argparse help text listing `--shard-index` and `--num-shards`, exits 0 without opening a browser.

- [ ] **Step 6: Commit**

```bash
git add scraper/zepto_oats.py scraper/test_zepto_oats.py
git commit -m "feat: add shard/CLI support to zepto_oats.py for parallel workers"
```

---

### Task 5: `parallel_runner.py` supervisor

**Files:**
- Create: `scraper/parallel_runner.py`
- Test: `scraper/test_parallel_runner.py` (new)

**Interfaces:**
- Consumes: `merge_shards` from Task 2 (`_merge`); `main`/`build_target_localities`/`make_sort_key_fn` from Task 3 (`blinkit_oats`); `scrape_zepto`/`load_localities`/`make_sort_key_fn` from Task 4 (`zepto_oats`).
- Produces: `free_ram_mb() -> float`, `wait_for_ram(min_mb, check_fn, sleep_fn, max_wait_s)`, `launch_worker(scraper_name, shard_index, num_shards, popen_fn) -> Popen-like`, `_classify_worker_result(exit_code, restarts, max_restarts) -> str`, `run_worker_pool(...)`, `supervise(scraper_name, workers, output_dir=None, **kwargs)`. CLI entry point: `python parallel_runner.py {blinkit_oats|zepto_oats} --workers N`.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_parallel_runner.py`:

```python
import parallel_runner as pr


def test_classify_worker_result_still_running_when_no_exit_code():
    assert pr._classify_worker_result(None, restarts=0, max_restarts=5) == "still_running"


def test_classify_worker_result_done_on_clean_exit():
    assert pr._classify_worker_result(0, restarts=2, max_restarts=5) == "done"


def test_classify_worker_result_restarts_on_crash_under_cap():
    assert pr._classify_worker_result(1, restarts=2, max_restarts=5) == "restart"


def test_classify_worker_result_gives_up_at_cap():
    assert pr._classify_worker_result(1, restarts=5, max_restarts=5) == "give_up"


def test_launch_worker_builds_expected_argv(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    calls = []

    def fake_popen(args, **kwargs):
        calls.append(args)
        return object()

    pr.launch_worker("blinkit_oats", shard_index=1, num_shards=3, popen_fn=fake_popen)

    assert len(calls) == 1
    args = calls[0]
    assert args[1] == str(tmp_path / "blinkit_oats.py")
    assert args[2:] == ["--shard-index", "1", "--num-shards", "3"]


def test_wait_for_ram_returns_immediately_when_ram_is_sufficient():
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: 2000, sleep_fn=slept.append)
    assert slept == []


def test_wait_for_ram_pauses_until_ram_frees_up():
    readings = iter([50, 50, 200])
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: next(readings), sleep_fn=slept.append)
    assert len(slept) == 2


def test_wait_for_ram_gives_up_after_max_wait():
    slept = []
    pr.wait_for_ram(min_mb=100, check_fn=lambda: 10, sleep_fn=slept.append, max_wait_s=12)
    assert len(slept) == 3  # bounded, not infinite -- 3 attempts at 5s bookkeeping each


def test_wait_for_ram_never_raises_if_check_fn_fails():
    def broken():
        raise RuntimeError("psutil not installed")
    pr.wait_for_ram(min_mb=100, check_fn=broken, sleep_fn=lambda s: None)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && py -m pytest test_parallel_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parallel_runner'`

- [ ] **Step 3: Implement `scraper/parallel_runner.py`**

```python
"""
Generic parallel-worker supervisor for the Blinkit/Zepto oats scrapers.
Splits the locality list into N shards, launches one worker subprocess per
shard, restarts any that crash (capped), and periodically merges the shard
output files into the single combined file each scraper normally produces
at scraper/output/{scraper_name}_data.xlsx.

Usage:
    python parallel_runner.py blinkit_oats --workers 3
    python parallel_runner.py zepto_oats --workers 3

See docs/superpowers/specs/2026-07-17-scraper-parallelization-design.md
for the full design rationale.
"""
import importlib
import subprocess
import sys
import time
from pathlib import Path

from _merge import merge_shards

ROOT = Path(__file__).resolve().parent
MAX_RESTARTS_PER_WORKER = 5
RESTART_BACKOFF_S = 10
STAGGER_S = 20
MERGE_INTERVAL_S = 300
MIN_FREE_RAM_MB = 1024

SCRAPER_CONFIGS = {
    "blinkit_oats": {
        "build_localities": lambda mod: mod.build_target_localities(),
        "make_sort_key_fn": lambda mod, localities: mod.make_sort_key_fn(localities),
    },
    "zepto_oats": {
        "build_localities": lambda mod: mod.load_localities(str(mod.MAGICBRICKS_FILE)),
        "make_sort_key_fn": lambda mod, localities: mod.make_sort_key_fn(localities),
    },
}


def free_ram_mb():
    import psutil
    return psutil.virtual_memory().available / (1024 * 1024)


def wait_for_ram(min_mb=MIN_FREE_RAM_MB, check_fn=free_ram_mb, sleep_fn=time.sleep, max_wait_s=120):
    """Blocks (with a warning) until free RAM clears min_mb, or max_wait_s
    elapses -- whichever first. Never raises; a psutil import failure or
    any other error just skips the check (better to proceed than to hang
    the whole run over an optional safety check)."""
    waited = 0.0
    while waited < max_wait_s:
        try:
            free = check_fn()
        except Exception:
            return
        if free >= min_mb:
            return
        print(f"⚠️  Low RAM ({free:.0f}MB free, want {min_mb}MB) — pausing before next launch...", flush=True)
        sleep_fn(5)
        waited += 5


def launch_worker(scraper_name, shard_index, num_shards, popen_fn=subprocess.Popen):
    script = str(ROOT / f"{scraper_name}.py")
    args = [sys.executable, script, "--shard-index", str(shard_index), "--num-shards", str(num_shards)]
    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    return popen_fn(args, creationflags=creationflags)


def _classify_worker_result(exit_code, restarts, max_restarts):
    """Given a worker's poll() result and how many times it's already been
    restarted, decides what the supervisor should do next. Pure/stateless
    so the crash-cap policy itself can be tested without any real or fake
    subprocess machinery."""
    if exit_code is None:
        return "still_running"
    if exit_code == 0:
        return "done"
    if restarts >= max_restarts:
        return "give_up"
    return "restart"


class WorkerHandle:
    def __init__(self, shard_index, popen):
        self.shard_index = shard_index
        self.popen = popen
        self.restarts = 0


def _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_shards):
    try:
        n = merge_fn(shard_paths, final_output, columns, sort_key_fn)
        print(f"🔀 Merged {n} rows → {final_output}", flush=True)
    except PermissionError:
        print(f"⚠️  {final_output} is open elsewhere — merge skipped this cycle.", flush=True)


def run_worker_pool(scraper_name, workers, shard_paths, final_output, columns, sort_key_fn,
                     popen_fn=subprocess.Popen, sleep_fn=time.sleep, ram_check_fn=free_ram_mb,
                     time_fn=time.monotonic, merge_interval_s=MERGE_INTERVAL_S,
                     max_restarts=MAX_RESTARTS_PER_WORKER, merge_fn=merge_shards):
    handles = {}
    for i in range(workers):
        wait_for_ram(check_fn=ram_check_fn, sleep_fn=sleep_fn)
        print(f"🚀 Launching worker {i} ({scraper_name}, shard {i}/{workers})...", flush=True)
        handles[i] = WorkerHandle(i, launch_worker(scraper_name, i, workers, popen_fn=popen_fn))
        if i < workers - 1:
            sleep_fn(STAGGER_S)

    last_merge = time_fn()
    try:
        while handles:
            sleep_fn(5)
            for i in list(handles.keys()):
                h = handles[i]
                code = h.popen.poll()
                result = _classify_worker_result(code, h.restarts, max_restarts)

                if result == "still_running":
                    continue
                if result == "done":
                    print(f"✅ Worker {i} finished its shard.", flush=True)
                    del handles[i]
                    continue
                if result == "give_up":
                    print(f"❌ Worker {i} crashed {h.restarts} times — giving up on this shard.", flush=True)
                    del handles[i]
                    continue

                # result == "restart"
                h.restarts += 1
                print(f"🔁 Worker {i} crashed (exit {code}) — restart {h.restarts}/{max_restarts}...", flush=True)
                sleep_fn(RESTART_BACKOFF_S)
                wait_for_ram(check_fn=ram_check_fn, sleep_fn=sleep_fn)
                handles[i] = WorkerHandle(i, launch_worker(scraper_name, i, workers, popen_fn=popen_fn))
                handles[i].restarts = h.restarts

            if time_fn() - last_merge >= merge_interval_s:
                _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_fn)
                last_merge = time_fn()
    except KeyboardInterrupt:
        print("\n⛔ Stopping all workers...", flush=True)
        for h in handles.values():
            try:
                h.popen.terminate()
            except Exception:
                pass

    _try_merge(shard_paths, final_output, columns, sort_key_fn, merge_fn=merge_fn)
    print(f"✅ Final merge → {final_output}", flush=True)


def supervise(scraper_name, workers, output_dir=None, **kwargs):
    config = SCRAPER_CONFIGS[scraper_name]
    mod = importlib.import_module(scraper_name)
    all_localities = config["build_localities"](mod)
    sort_key_fn = config["make_sort_key_fn"](mod, all_localities)

    if output_dir is None:
        output_dir = ROOT / "output"
    output_dir = Path(output_dir)
    shard_dir = output_dir / "_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_paths = [shard_dir / f"{scraper_name}_shard{i}.xlsx" for i in range(workers)]
    final_output = output_dir / f"{scraper_name}_data.xlsx"

    run_worker_pool(scraper_name, workers, shard_paths, final_output, mod.COLUMNS, sort_key_fn, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("scraper", choices=list(SCRAPER_CONFIGS.keys()))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    supervise(args.scraper, args.workers)
```

Note on `handles[i].restarts = h.restarts` in the restart branch: the new `WorkerHandle` starts with `restarts=0`, so this line carries the incremented count forward onto the new handle — without it, a worker that crashes twice would never hit the cap because each replacement handle resets to 0.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && py -m pytest test_parallel_runner.py -v`
Expected: all 8 tests PASS

Also run the full suite:
Run: `cd scraper && py -m pytest test_reliability.py test_blinkit_oats.py test_blinkit_goatlife.py test_swiggy_oats.py test_zepto_oats.py test_merge.py test_parallel_runner.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scraper/parallel_runner.py scraper/test_parallel_runner.py
git commit -m "feat: add parallel_runner.py supervisor with crash-restart and RAM-aware launch"
```

---

### Task 6: Manual end-to-end smoke test

This task has no automated test — it validates real Chrome windows, real network calls, and real crash recovery, none of which the unit tests above exercise (by design, per the dependency-injection approach). Do this once before relying on the parallel path for a real overnight run.

**Files:** none (verification only)

- [ ] **Step 1: Confirm no stray Chrome processes are running first**

Run (PowerShell): `Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object -Property WorkingSet64 -Sum`

If there's a large count of leftover `chrome.exe` processes from earlier runs, close them (or reboot) before this test — they eat into the RAM budget this whole feature is designed around.

- [ ] **Step 2: Dry-run the supervisor for a short window on Blinkit**

Run: `cd scraper && py parallel_runner.py blinkit_oats --workers 3`

Watch for, within the first ~2 minutes:
- 3 separate Chrome windows opening, staggered ~20s apart (not all at once)
- 3 console windows, each printing that scraper's normal per-locality progress output
- `scraper/output/_shards/blinkit_oats_shard0.xlsx`, `_shard1.xlsx`, `_shard2.xlsx` appearing and growing

Let it run at least 6 minutes (past one `MERGE_INTERVAL_S` = 300s cycle), then confirm:
- `scraper/output/blinkit_oats_data.xlsx` exists and contains rows from more than one shard
- Rows appear in canonical order (grouped by city, then by the same locality-price-descending order as a normal single-worker run — not jumbled)

- [ ] **Step 3: Verify crash recovery**

While the 3 workers are running, manually close one worker's Chrome window (or end its `python.exe` process via Task Manager) to simulate a crash.

Confirm in the supervisor's console output: a `🔁 Worker N crashed ... restart 1/5` message appears within a few seconds, and a new Chrome window opens for that worker, resuming (not restarting from locality 1 — check its shard file's row count didn't reset).

- [ ] **Step 4: Verify clean shutdown**

Press Ctrl+C in the supervisor's console.

Confirm: a `⛔ Stopping all workers...` message, the 3 worker Chrome/console windows close (or are in the process of closing), and a final `✅ Final merge → ...` message with the combined file reflecting everything scraped so far.

- [ ] **Step 5: Repeat steps 2-4 for Zepto**

Run: `cd scraper && py parallel_runner.py zepto_oats --workers 3`

Same checks as above, against `scraper/output/zepto_oats_data.xlsx` and `scraper/output/_shards/zepto_oats_shard*.xlsx`.

- [ ] **Step 6: Clear any partial data from this smoke test before a real run**

Same pattern used earlier in this project: move (don't delete) `scraper/output/_shards/*.xlsx` and the combined `scraper/output/blinkit_oats_data.xlsx` / `zepto_oats_data.xlsx` produced during this test to a dated backup/discard folder, so the next real run starts clean. (No fixed command here — follow whatever the current `scraper/output/` state looks like at the time.)

---

## Self-Review Notes

**Spec coverage:** file layout (Task 3-5 create exactly the files the spec named), sharding (Task 1), merge + canonical ordering (Task 2, Task 3/4's `make_sort_key_fn`), fail-safe mechanisms — process isolation (subprocess in Task 5), auto-restart with cap (`_classify_worker_result`), staggered startup (`STAGGER_S` in `run_worker_pool`), RAM pre-check (`wait_for_ram`), safe merge writes (`_merge.py`'s temp-file+atomic-replace and `PermissionError` handling) — all covered. Lighter Chrome memory flags (`--blink-settings=imagesEnabled=false`) from the spec's fail-safe section were intentionally **not** included as a separate task — deferred, see note below. Usage patterns (one-scraper-at-a-time vs both) require no code, already true of the CLI design (Task 5 self-review confirmed).

**Deferred from spec:** the spec's `--blink-settings=imagesEnabled=false` memory optimization isn't in any task above — it's a one-line addition to each scraper's `create_driver()` `ChromeOptions`, independent of the parallelization mechanism itself, and untested by anything in this plan (it's a Chrome flag, not testable via pytest). Recommend adding it by hand to `create_driver()` in both `blinkit_oats.py` and `zepto_oats.py` after Task 6's smoke test confirms the base parallel path works — bundling it into Task 3/4 would conflate "does sharding work" with "does the memory-lighter Chrome still render correctly," which are better verified separately.
