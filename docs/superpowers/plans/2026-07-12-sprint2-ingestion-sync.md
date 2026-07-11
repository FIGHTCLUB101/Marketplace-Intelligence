# Sprint 2 — Ingestion & Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the 6 GOAT Life scrapers into the repo as a version-controlled `scraper/` module, fix the reliability bugs that were crashing the Swiggy/Zepto scrapers around ~200 localities, wire each `.bat` launcher to sync its output straight into the Sprint-1 database, and add a GitHub Actions button that syncs new notebook output without a local Python environment.

**Architecture:** A new `scraper/` module holds the 4 oats-brand scrapers (which share a new `scraper/_reliability.py` toolkit: driver-restart, dead-session recovery, block detection, incremental save) plus the 2 locality/store scrapers (relocated as-is, no reliability rewrite — they're structurally different and weren't part of the diagnosed crash). Every `.bat` launcher moves with its script and gets repointed at the new in-repo paths. A `.github/workflows/` file adds a manual-trigger CI job that calls Sprint 1's already-built `scripts/sync_locality_scores.py`.

**Tech Stack:** Python, Selenium + `undetected_chromedriver` (already in use, no new dependency), `openpyxl` (already in use), GitHub Actions (`workflow_dispatch`).

## Global Constraints

- The scraper stays a **local, manually-triggered, human-in-the-loop process** — CAPTCHA-solving requires a visible browser and a human. Nothing in this sprint attempts to run a scraper unattended or in CI.
- Only 4 of 6 scrapers write to `shelf_snapshots`: `blinkit_goatlife`, `blinkit_oats`, `swiggy`, `zepto`. Magicbricks and Reliance produce `data/`-input files for the ML notebooks, not shelf-pricing rows — their `.bat` files do not call any sync script.
- Reliability fixes (driver restart every 25 localities, dead-session auto-recovery, incremental save, block detection with real pause-and-wait, resume/dedup) apply only to the 4 oats scrapers — this is the diagnosed scope from the crash investigation (Sprint 1 planning), not a blanket rewrite.
- The dead Swiggy v1 script (`scrape_swiggy_oats.py`, superseded by v2) is never migrated.
- No subagent can run these scrapers end-to-end (they require live CAPTCHA-solving against real websites from a visible browser). Verification for scraper tasks is: (a) real unit tests for each script's pure parsing/price functions (currently zero coverage), and (b) `python -m py_compile` to confirm the file is syntactically valid and importable. Do not attempt to launch Chrome or scrape a live site as a verification step.
- Source files to migrate from (absolute paths on this machine, already read in full during design):
  - `C:\Users\singh\Desktop\SCRAPE\scrape_blinkit_goatlife.py`
  - `C:\Users\singh\Desktop\SCRAPE\scrape_blinkit_oats.py`
  - `C:\Users\singh\Desktop\SCRAPE\scrape_swiggy_oats_v2.py`
  - `C:\Users\singh\Desktop\SCRAPE\scrape_zepto_oats.py`
  - `C:\Users\singh\Desktop\SCRAPE\scrape_magicbricks_manual.py`
  - `C:\Users\singh\Desktop\SCRAPE\scrape_reliance_manual.py`
  - `C:\Users\singh\Desktop\Run_Blinkit_GoatLife_Scraper.bat`, `Run_Blinkit_Oats_Scraper.bat`, `Run_Swiggy_Oats_Scraper.bat`, `Run_Zepto_Oats_Scraper.bat`, `Run_Magicbricks_Scraper.bat`, `Run_Reliance_Scraper.bat`
- Existing test convention: tests live alongside the code they test, run via `cd scripts && python -m pytest -q` for `scripts/`, and (new in this sprint) `cd scraper && python -m pytest -q` for `scraper/`.
- Existing import convention: flat imports relying on running scripts from their own directory (e.g. `from db_connection import get_connection` inside `scripts/`). The new `scraper/` module follows the same flat-import convention internally.
- Sprint 1 is complete and merged to `main` at `https://github.com/FIGHTCLUB101/Marketplace-Intelligence`. `scripts/sync_locality_scores.py` and `scripts/sync_shelf_snapshots.py` already exist and work — this sprint wires things to call them, not rebuild them.

---

### Task 1: Shared scraper reliability module

**Files:**
- Create: `scraper/_reliability.py`
- Test: `scraper/test_reliability.py`

**Interfaces:**
- Produces (all used by Tasks 3-6):
  - `is_blocked(driver) -> bool` — checks `driver.title` and `driver.page_source` for CAPTCHA/WAF markers.
  - `wait_for_manual_unblock(driver, beep_fn, max_wait_s=180, poll_s=3) -> bool` — pauses and beeps until `is_blocked()` clears or `max_wait_s` elapses; returns whether it cleared.
  - `jittered_sleep(base_s, jitter_s=1.0) -> None`.
  - `should_restart_driver(locality_index, restart_every=25) -> bool`.
  - `is_dead_session_error(exc) -> bool`.
  - `IncrementalWorkbook(path, columns)` class with `.append_row(row: dict)`, `.save()`, `.done_keys(key_columns: list[str]) -> set[str]`.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_reliability.py`:
```python
import time

import pytest
from openpyxl import load_workbook

from _reliability import (
    IncrementalWorkbook,
    is_blocked,
    is_dead_session_error,
    jittered_sleep,
    should_restart_driver,
    wait_for_manual_unblock,
)


class FakeDriver:
    def __init__(self, title="GOAT Life Oats", body="normal page content"):
        self.title = title
        self._body = body

    @property
    def page_source(self):
        return self._body


def test_is_blocked_detects_title_keywords():
    assert is_blocked(FakeDriver(title="Please solve this CAPTCHA")) is True
    assert is_blocked(FakeDriver(title="Robot check")) is True
    assert is_blocked(FakeDriver(title="Normal Product Page")) is False


def test_is_blocked_detects_body_markers():
    assert is_blocked(FakeDriver(title="Blinkit", body="<div>Access Denied</div>")) is True
    assert is_blocked(FakeDriver(title="Blinkit", body="AwsWafIntegration challenge")) is True
    assert is_blocked(FakeDriver(title="Blinkit", body="<div>Yoga Bar Oats ₹399</div>")) is False


def test_wait_for_manual_unblock_returns_true_immediately_if_not_blocked():
    driver = FakeDriver(title="Normal page")
    beeped = []
    assert wait_for_manual_unblock(driver, beep_fn=lambda: beeped.append(1), poll_s=0.01) is True
    assert beeped == []


def test_wait_for_manual_unblock_clears_after_driver_state_changes():
    driver = FakeDriver(title="CAPTCHA")
    beeped = []

    def unblock_after_beep():
        beeped.append(1)
        driver.title = "Normal page"

    assert wait_for_manual_unblock(driver, beep_fn=unblock_after_beep, poll_s=0.01, max_wait_s=1) is True
    assert beeped == [1]


def test_wait_for_manual_unblock_gives_up_after_max_wait():
    driver = FakeDriver(title="CAPTCHA")
    result = wait_for_manual_unblock(driver, beep_fn=lambda: None, poll_s=0.01, max_wait_s=0.05)
    assert result is False


def test_jittered_sleep_sleeps_at_least_base_duration():
    start = time.monotonic()
    jittered_sleep(0.05, jitter_s=0.05)
    assert time.monotonic() - start >= 0.05


def test_should_restart_driver_fires_every_n_localities():
    assert should_restart_driver(0, restart_every=25) is False
    assert should_restart_driver(24, restart_every=25) is False
    assert should_restart_driver(25, restart_every=25) is True
    assert should_restart_driver(50, restart_every=25) is True
    assert should_restart_driver(26, restart_every=25) is False


def test_is_dead_session_error_matches_known_messages():
    assert is_dead_session_error(Exception("chrome not reachable")) is True
    assert is_dead_session_error(Exception("invalid session id")) is True
    assert is_dead_session_error(Exception("session deleted because of page crash")) is True
    assert is_dead_session_error(Exception("element not found")) is False


def test_incremental_workbook_appends_and_saves(tmp_path):
    path = tmp_path / "out.xlsx"
    wb = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    wb.append_row({"City": "Bangalore", "Locality": "Indiranagar", "Price": 99})
    wb.append_row({"City": "Delhi", "Locality": "Saket", "Price": 119})
    wb.save()

    reloaded = load_workbook(path)
    ws = reloaded.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("City", "Locality", "Price")
    assert rows[1] == ("Bangalore", "Indiranagar", 99)
    assert rows[2] == ("Delhi", "Saket", 119)


def test_incremental_workbook_resumes_from_existing_file(tmp_path):
    path = tmp_path / "out.xlsx"
    wb1 = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    wb1.append_row({"City": "Bangalore", "Locality": "Indiranagar", "Price": 99})
    wb1.save()

    wb2 = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    keys = wb2.done_keys(["City", "Locality"])
    assert keys == {"Bangalore|Indiranagar"}

    wb2.append_row({"City": "Delhi", "Locality": "Saket", "Price": 119})
    wb2.save()

    reloaded = load_workbook(path)
    rows = list(reloaded.active.iter_rows(values_only=True))
    assert len(rows) == 3  # header + 2 data rows
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_reliability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '_reliability'` (the `scraper/` directory doesn't exist yet — create it as part of Step 3)

- [ ] **Step 3: Write minimal implementation**

Create `scraper/_reliability.py`:
```python
"""Shared reliability toolkit for the 4 oats-brand scrapers.

Fixes the crash pattern diagnosed during Sprint 1 planning: Chrome's
renderer runs out of memory after ~200 localities of sustained DOM-heavy
automation (repeated full-page reloads, driver.page_source pulls, blind
modal enumeration in set_location), crashing mid-locality with no
recovery -- which cascades into every remaining locality failing the
same way. This module adds: periodic driver recycling before memory
pressure reaches that point, detection of a dead session so the current
locality can be retried instead of the whole run silently degrading,
real CAPTCHA/block detection with a pause-and-wait loop (all 4 scrapers
previously had inconsistent or, for Zepto, entirely absent block
handling), and incremental xlsx saves that don't get slower as the run
accumulates rows.
"""
import random
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook

BLOCK_TITLE_KEYWORDS = ["captcha", "robot", "blocked", "verify"]
BLOCK_BODY_MARKERS = [
    "access denied",
    "unusual traffic",
    "attention required",
    "awswafintegration",
    "challenge-container",
    "are you human",
]

DEAD_SESSION_MARKERS = [
    "chrome not reachable",
    "invalid session id",
    "session deleted",
    "no such window",
    "disconnected",
]


def is_blocked(driver) -> bool:
    title = (driver.title or "").lower()
    if any(k in title for k in BLOCK_TITLE_KEYWORDS):
        return True
    body = (driver.page_source or "").lower()
    return any(m in body for m in BLOCK_BODY_MARKERS)


def wait_for_manual_unblock(driver, beep_fn, max_wait_s=180, poll_s=3) -> bool:
    if not is_blocked(driver):
        return True
    beep_fn()
    waited = 0.0
    while waited < max_wait_s:
        time.sleep(poll_s)
        waited += poll_s
        if not is_blocked(driver):
            return True
    return False


def jittered_sleep(base_s: float, jitter_s: float = 1.0) -> None:
    time.sleep(base_s + random.uniform(0, jitter_s))


def should_restart_driver(locality_index: int, restart_every: int = 25) -> bool:
    return locality_index > 0 and locality_index % restart_every == 0


def is_dead_session_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in DEAD_SESSION_MARKERS)


class IncrementalWorkbook:
    """One in-memory openpyxl workbook, appended to as rows come in and
    saved periodically -- replaces rewriting the whole xlsx file (or, for
    Zepto's old pattern, round-tripping it through disk) on every save
    point, which gets slower as the run accumulates rows."""

    def __init__(self, path: Path, columns: list[str]):
        self.path = Path(path)
        self.columns = columns
        if self.path.exists():
            self.wb = load_workbook(self.path)
            self.ws = self.wb.active
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.wb = Workbook()
            self.ws = self.wb.active
            self.ws.append(columns)

    def append_row(self, row: dict) -> None:
        self.ws.append([row.get(c) for c in self.columns])

    def save(self) -> None:
        self.wb.save(self.path)

    def done_keys(self, key_columns: list[str]) -> set[str]:
        idxs = [self.columns.index(c) for c in key_columns]
        keys = set()
        for row in self.ws.iter_rows(min_row=2, values_only=True):
            keys.add("|".join(str(row[i]) for i in idxs))
        return keys
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_reliability.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add scraper/_reliability.py scraper/test_reliability.py
git commit -m "feat: add shared scraper reliability toolkit"
```

---

### Task 2: GitHub Actions notebook-sync workflow

**Files:**
- Modify: `.gitignore`
- Create: `.github/workflows/sync-locality-scores.yml`

**Interfaces:**
- Consumes: `scripts/sync_locality_scores.py` (Sprint 1, already built and working).
- Produces: nothing other tasks depend on — this is a leaf deliverable.

- [ ] **Step 1: Un-ignore the master parquet only**

Current `.gitignore` has this block:
```
.ipynb_checkpoints/
notebooks/artifacts/

# generated notebook exports
notebooks/*.csv
notebooks/*.xlsx
```

Replace the `notebooks/artifacts/` line so the directory's contents are still ignored by default, but the one file GitHub Actions needs is explicitly un-ignored (the other intermediate artifacts — `embeddings.npz` at 7.7MB, the `features_*.parquet` files, etc. — stay ignored; only the final master store needs to be committed):
```
.ipynb_checkpoints/
notebooks/artifacts/*
!notebooks/artifacts/localities_master_serviceable.parquet

# generated notebook exports
notebooks/*.csv
notebooks/*.xlsx
```

(Note the `/*` instead of `/` on the `notebooks/artifacts/` line — a bare trailing-slash directory-ignore pattern blocks git from recursing into the directory at all, which prevents the negation on the next line from working. Using `/*` still ignores every file in the directory by default, but lets git evaluate the negation for the one named file.)

- [ ] **Step 2: Commit the current master parquet**

```bash
git add notebooks/artifacts/localities_master_serviceable.parquet .gitignore
git status
```
Expected: `git status` shows the parquet as a new tracked file (~1MB) and `.gitignore` modified — nothing else from `notebooks/artifacts/` should appear as staged (confirms the ignore pattern is scoped correctly).

- [ ] **Step 3: Write the workflow**

Create `.github/workflows/sync-locality-scores.yml`:
```yaml
name: Sync locality scores to Postgres

on:
  workflow_dispatch: {}

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Sync locality scores
        working-directory: scripts
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python sync_locality_scores.py
```

- [ ] **Step 4: Add the DATABASE_URL secret (manual, one-time)**

This step cannot be automated from this environment (no `gh` CLI is installed, and repository secrets require either the GitHub web UI or an authenticated `gh`/API call). Do this manually:

1. Go to `https://github.com/FIGHTCLUB101/Marketplace-Intelligence/settings/secrets/actions`
2. Click "New repository secret"
3. Name: `DATABASE_URL`
4. Value: the same connection string from your local `.env` file (the pooled Neon connection string)
5. Click "Add secret"

- [ ] **Step 5: Commit and push**

```bash
git add .github/workflows/sync-locality-scores.yml
git commit -m "feat: add GitHub Actions button to sync locality scores"
git push
```

- [ ] **Step 6: Verify the workflow runs (manual)**

Go to `https://github.com/FIGHTCLUB101/Marketplace-Intelligence/actions/workflows/sync-locality-scores.yml`, click "Run workflow", wait for it to complete, and confirm it shows a green check. This step requires the secret from Step 4 to already be set, and needs a human to click the button in the GitHub UI — it cannot be verified by an automated implementer.

---

### Task 3: Migrate Blinkit GOAT Life scraper (reference implementation)

**Files:**
- Create: `scraper/blinkit_goatlife.py`
- Create: `scraper/output/.gitkeep`
- Modify: `.gitignore`
- Create: `scraper/test_blinkit_goatlife.py`
- Create: `C:\Users\singh\Desktop\Run_Blinkit_GoatLife_Scraper.bat` (overwrite in place)

**Interfaces:**
- Consumes: `scraper/_reliability.py`'s `is_blocked`, `wait_for_manual_unblock`, `jittered_sleep`, `should_restart_driver`, `is_dead_session_error`, `IncrementalWorkbook` (Task 1).
- Produces: the canonical restructured-main-loop pattern that Tasks 4-6 follow (driver restart, dead-session retry-same-locality, incremental save, real block detection).

This task is the fully-worked reference: read it in full before starting Tasks 4-6, which apply the same pattern to their own file's loop shape.

- [ ] **Step 1: Ignore scraper output**

Add to `.gitignore`:
```

# scraper output (regenerated by running the scrapers; not source)
scraper/output/*.xlsx
```

- [ ] **Step 2: Create the output directory placeholder**

Create `scraper/output/.gitkeep` (empty file) so the directory exists in git even though its `.xlsx` contents are ignored.

- [ ] **Step 3: Write the failing tests for the pure functions**

The original script (`C:\Users\singh\Desktop\SCRAPE\scrape_blinkit_goatlife.py`) has one pure function with zero existing test coverage: `extract_buy_price`. Create `scraper/test_blinkit_goatlife.py`:
```python
import math

from blinkit_goatlife import extract_buy_price


def test_extract_buy_price_parses_range_as_midpoint():
    assert extract_buy_price("Buy Rs. 10,000 - Rs. 20,000") == 15000.0


def test_extract_buy_price_handles_na_variants():
    assert extract_buy_price("N/A") == 0
    assert extract_buy_price("nan") == 0
    assert extract_buy_price("") == 0
    assert extract_buy_price(float("nan")) == 0


def test_extract_buy_price_returns_zero_when_unparseable():
    assert extract_buy_price("no numbers here") == 0
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_blinkit_goatlife.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blinkit_goatlife'`

- [ ] **Step 5: Create the migrated, fixed scraper**

Read the source file at `C:\Users\singh\Desktop\SCRAPE\scrape_blinkit_goatlife.py` to confirm you have its exact current content, then create `scraper/blinkit_goatlife.py` with this content (path constants repointed into the repo, reliability toolkit wired into the main loop; `extract_buy_price`, `beep`, `create_driver`, `set_location`, `is_serviceable`, `scrape_brand`, `not_available_row` are unchanged from the source — copy them verbatim into the corresponding spots below):

```python
"""
Blinkit Goat Life Brand Scraper
Scrapes Goat Life product availability, pricing, and ratings across
Top 50 localities (by residential property price = spending power)
in each of the 10 cities.

Output: scraper/output/blinkit_goatlife_data.xlsx
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import os, re, time, winsound
from pathlib import Path

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from _reliability import (
    IncrementalWorkbook, is_blocked, is_dead_session_error,
    jittered_sleep, should_restart_driver, wait_for_manual_unblock,
)

# ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"
OUTPUT_FILE      = ROOT / "scraper" / "output" / "blinkit_goatlife_data.xlsx"
TOP_N            = 50

BRAND = "Goat Life"

COLUMNS = ["City", "Locality", "Search Term", "Rank", "Product Name",
           "Pack Size", "Selling Price", "MRP", "Discount %", "Stock Left",
           "Rating", "Serviceable"]

# ─────────────────────────────────────────────
def extract_buy_price(price_str):
    if pd.isna(price_str) or str(price_str).strip() in ('N/A','nan',''): return 0
    m = re.search(r'Buy Rs\.\s*([\d,]+)\s*-\s*Rs\.\s*([\d,]+)', str(price_str))
    if m:
        return (int(m.group(1).replace(',','')) + int(m.group(2).replace(',',''))) / 2
    return 0

def beep():
    for _ in range(2):
        winsound.Beep(1000, 500)
        time.sleep(0.3)

def create_driver():
    opts = uc.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-IN")
    return uc.Chrome(options=opts, version_main=149)

# ─────────────────────────────────────────────
def set_location(driver, locality, city):
    search_query = f"{locality}, {city}"
    print(f"  📍 Setting location → {search_query}", flush=True)

    for attempt in range(3):
        try:
            driver.get("https://blinkit.com/")
            time.sleep(5)
            if not wait_for_manual_unblock(driver, beep):
                print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

            input_box = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='search delivery location']"))
            )

            driver.execute_script("""
                arguments[0].value = '';
                arguments[0].focus();
            """, input_box)
            time.sleep(0.5)

            actions = ActionChains(driver)
            actions.click(input_box)
            actions.send_keys(search_query)
            actions.perform()
            time.sleep(3.5)

            suggestion_clicked = False
            suggestion_text = "None found"

            modal_xpaths = [
                "//div[contains(@class,'LocationDropDown')]",
                "//div[contains(@class,'location__shake-container')]",
                "//div[contains(@class,'LocationModal')]",
            ]

            modal = None
            for mx in modal_xpaths:
                try:
                    modal = driver.find_element(By.XPATH, mx)
                    if modal: break
                except: pass

            if modal:
                child_divs = modal.find_elements(By.XPATH, ".//div")
                location_divs = []
                for d in child_divs:
                    try:
                        if not d.is_displayed(): continue
                        text = d.text.strip()
                        if (len(text) > 5 and
                            any(kw in text for kw in [city, 'India', 'Maharashtra', 'Delhi',
                                                       'Karnataka', 'Punjab', 'Uttar Pradesh',
                                                       'Haryana', 'Tamil Nadu', 'West Bengal',
                                                       'Telangana', locality[:5]]) and
                            'Please provide' not in text and
                            'Detect my location' not in text and
                            'search delivery' not in text.lower()):
                            location_divs.append((d, text))
                    except: pass

                if location_divs:
                    first_div, first_text = location_divs[0]
                    suggestion_text = first_text.split('\n')[0][:60]
                    driver.execute_script("arguments[0].click();", first_div)
                    suggestion_clicked = True

            if not suggestion_clicked:
                try:
                    time.sleep(1)
                    candidates = driver.find_elements(By.XPATH,
                        f"//*[contains(text(),'{locality[:8]}') and not(contains(@class,'Footer')) and not(contains(@class,'Input'))]")
                    visible = [c for c in candidates if c.is_displayed() and c.text.strip() and
                               len(c.text.strip()) > 10]
                    if visible:
                        suggestion_text = visible[0].text.split('\n')[0][:60]
                        driver.execute_script("arguments[0].click();", visible[0])
                        suggestion_clicked = True
                except: pass

            if not suggestion_clicked:
                input_box = driver.find_element(By.XPATH, "//input[@placeholder='search delivery location']")
                input_box.send_keys(Keys.RETURN)
                suggestion_text = "(pressed Enter)"

            print(f"  ✅ Selected: {suggestion_text}", flush=True)
            time.sleep(4)
            return True

        except Exception as e:
            print(f"  ❌ Attempt {attempt+1}: {str(e)[:100]}", flush=True)
            time.sleep(3)

    return False

# ─────────────────────────────────────────────
def is_serviceable(driver):
    pt = driver.page_source.lower()
    return not any(p in pt for p in [
        "we don't deliver here", "not serviceable", "outside our delivery",
        "not available in your area", "coming soon to your area"
    ])

# ─────────────────────────────────────────────
def scrape_brand(driver, brand, locality, city):
    products = []
    try:
        driver.get(f"https://blinkit.com/s/?q={brand.replace(' ','%20')}")
        time.sleep(3)
        if not wait_for_manual_unblock(driver, beep):
            print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        page_lower = driver.page_source.lower()
        if any(x in page_lower for x in ["no products","0 results","couldn't find","no result"]):
            print(f"    ⚪ No results for '{brand}'", flush=True)
            return products

        cards = []
        try:
            add_buttons = driver.find_elements(By.XPATH, "//div[text()='ADD' or text()='Add']")
            for btn in add_buttons:
                try:
                    parent = btn.find_element(By.XPATH, "./../../..")
                    if '₹' in parent.text:
                        cards.append(parent)
                except: pass
        except: pass

        print(f"    🔍 '{brand}': {len(cards)} card(s) found on page", flush=True)

        for rank, card in enumerate(cards[:15], 1):
            try:
                ct = card.text
                if not ct or len(ct) < 5: continue

                lines = [l.strip() for l in ct.split('\n') if l.strip() and len(l.strip()) > 3]
                name = lines[0] if lines else "Unknown"

                pack_size = "N/A"
                m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g\b|ml|L\b|gm)\b', ct, re.I)
                if m: pack_size = f"{m.group(1)} {m.group(2)}"

                prices = sorted(set([int(x.replace(',','')) for x in re.findall(r'₹\s*(\d+(?:,\d+)?)', ct)]))
                sp = mrp = disc = "N/A"
                if len(prices) >= 2:
                    sp, mrp = f"₹{prices[0]}", f"₹{prices[-1]}"
                    d = round((1 - prices[0]/prices[-1])*100) if prices[-1] > 0 else 0
                    disc = f"{d}%"
                elif prices: sp = mrp = f"₹{prices[0]}"
                dm = re.search(r'(\d+)%\s*OFF', ct, re.I)
                if dm: disc = f"{dm.group(1)}%"

                stock = "N/A"
                sm = re.search(r'(\d+)\s+left|only\s+(\d+)', ct, re.I)
                if sm: stock = f"{(sm.group(1) or sm.group(2))} left"
                elif "out of stock" in ct.lower(): stock = "Out of Stock"

                rating = "N/A"
                rm = re.search(r'(\d\.\d)\s*\(', ct)
                if rm and 1.0 <= float(rm.group(1)) <= 5.0: rating = rm.group(1)

                products.append({
                    "City": city, "Locality": locality, "Search Term": brand, "Rank": rank,
                    "Product Name": name, "Pack Size": pack_size,
                    "Selling Price": sp, "MRP": mrp, "Discount %": disc,
                    "Stock Left": stock, "Rating": rating, "Serviceable": "Yes",
                })
                print(f"    ✅ [Rank {rank}] {name[:31]:<31} {pack_size:<8} {sp} (MRP:{mrp})", flush=True)

            except: pass

    except Exception as e:
        print(f"    ❌ Error: {str(e)[:80]}", flush=True)
    return products

# ─────────────────────────────────────────────
def not_available_row(city, locality, reason="Not Available"):
    return {
        "City": city, "Locality": locality, "Search Term": BRAND, "Rank": "N/A",
        "Product Name": reason, "Pack Size": "N/A", "Selling Price": "N/A",
        "MRP": "N/A", "Discount %": "N/A", "Stock Left": "N/A",
        "Rating": "N/A", "Serviceable": "Yes" if reason == "Not Available" else "No",
    }

# ─────────────────────────────────────────────
def main():
    print("="*65, flush=True)
    print("  BLINKIT — GOAT LIFE SCRAPER", flush=True)
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

    print(f"\n📋 Localities: {len(target_localities)} | Brand: {BRAND} | Est. searches: {len(target_localities)}", flush=True)

    wb = IncrementalWorkbook(OUTPUT_FILE, columns=COLUMNS)
    done_keys = wb.done_keys(["City", "Locality"])
    if done_keys:
        print(f"📂 Resuming — {len(done_keys)} localities already saved.", flush=True)

    driver = create_driver()
    total = len(target_localities)
    i = 0
    retries = 0

    try:
        while i < total:
            loc = target_localities[i]
            locality, city, price = loc['locality'], loc['city'], loc['price']

            if f"{city}|{locality}" in done_keys:
                print(f"\n⏭️  [{i+1}/{total}] SKIP {locality}, {city} (already done)", flush=True)
                i += 1
                continue

            if should_restart_driver(i, restart_every=25):
                print(f"\n🔄 Restarting browser at locality {i+1} to keep memory healthy...", flush=True)
                try: driver.quit()
                except: pass
                driver = create_driver()

            print(f"\n{'='*65}", flush=True)
            print(f"[{i+1}/{total}] {locality}, {city}  (Rs.{price:,.0f}/sqft)", flush=True)
            print(f"{'='*65}", flush=True)

            try:
                ok = set_location(driver, locality, city)
                if not ok:
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                elif not is_serviceable(driver):
                    print(f"  🚫 NOT SERVICEABLE in {locality}, {city}", flush=True)
                    wb.append_row(not_available_row(city, locality, "Not Serviceable"))
                else:
                    print(f"\n  🛒 Searching: {BRAND}", flush=True)
                    prods = scrape_brand(driver, BRAND, locality, city)
                    if not prods:
                        wb.append_row(not_available_row(city, locality))
                    else:
                        for p in prods: wb.append_row(p)

                done_keys.add(f"{city}|{locality}")
                wb.save()
                print(f"\n  💾 Saved (locality {i+1}/{total})", flush=True)
                i += 1
                retries = 0

            except Exception as e:
                if is_dead_session_error(e) and retries < 2:
                    retries += 1
                    print(f"\n🔁 Browser session died ({str(e)[:60]}) — restarting and retrying "
                          f"{locality}, {city} (attempt {retries+1})...", flush=True)
                    try: driver.quit()
                    except: pass
                    driver = create_driver()
                    continue  # retry same i
                elif is_dead_session_error(e):
                    print(f"\n⚠️  {locality}, {city} failed after {retries} restarts — marking error and moving on.", flush=True)
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                    done_keys.add(f"{city}|{locality}")
                    wb.save()
                    i += 1
                    retries = 0
                else:
                    print(f"\n❌ Unexpected error on {locality}, {city}: {str(e)[:100]}", flush=True)
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                    done_keys.add(f"{city}|{locality}")
                    wb.save()
                    i += 1
                    retries = 0

            jittered_sleep(1.0, jitter_s=1.5)

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.", flush=True)
    finally:
        wb.save()
        print(f"\n✅ Final save → {OUTPUT_FILE}", flush=True)
        try: driver.quit()
        except: pass

    print("\n" + "="*65, flush=True)
    print("  SCRAPING COMPLETE!", flush=True)
    print("="*65, flush=True)

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_blinkit_goatlife.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Verify the file compiles and imports cleanly**

Run: `cd scraper && python -m py_compile blinkit_goatlife.py`
Expected: no output, exit code 0 (confirms valid syntax — this does not launch a browser or scrape anything)

- [ ] **Step 8: Update the launcher and wire it to the DB sync**

Overwrite `C:\Users\singh\Desktop\Run_Blinkit_GoatLife_Scraper.bat` with:
```bat
@echo off
title Blinkit Goat Life Scraper
echo Starting Blinkit Goat Life Scraper...
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python blinkit_goatlife.py
if errorlevel 1 (
    echo Scraper reported an error - skipping DB sync.
    pause
    exit /b 1
)
echo Syncing to database...
cd /d C:\Users\singh\Desktop\GOATLife\scripts
python sync_shelf_snapshots.py blinkit_goatlife ..\scraper\output\blinkit_goatlife_data.xlsx
pause
```

- [ ] **Step 9: Commit**

```bash
git add scraper/blinkit_goatlife.py scraper/test_blinkit_goatlife.py scraper/output/.gitkeep .gitignore
git commit -m "feat: migrate Blinkit GOAT Life scraper with reliability fixes"
```

(The `.bat` file lives outside the repo on the Desktop, not tracked by git — no commit needed for it, just confirm Step 8 was applied.)

---

### Task 4: Migrate Blinkit competitor-oats scraper

**Files:**
- Create: `scraper/blinkit_oats.py`
- Create: `scraper/test_blinkit_oats.py`
- Modify: `C:\Users\singh\Desktop\Run_Blinkit_Oats_Scraper.bat` (overwrite in place)

**Interfaces:**
- Consumes: same `scraper/_reliability.py` interfaces as Task 3, applied via the same canonical pattern (driver restart, dead-session retry-same-locality via a `while i < total` loop with a `retries` counter, `IncrementalWorkbook`, `wait_for_manual_unblock` replacing `check_captcha`).

This file has one structural difference from Task 3: an inner `for brand in brands_todo:` loop (10 brands per locality, not 1), and a `get_brand_keyword` filter with zero existing test coverage.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_blinkit_oats.py`:
```python
from blinkit_oats import extract_buy_price, get_brand_keyword


def test_extract_buy_price_parses_range_as_midpoint():
    assert extract_buy_price("Buy Rs. 10,000 - Rs. 20,000") == 15000.0


def test_extract_buy_price_handles_na():
    assert extract_buy_price("N/A") == 0


def test_get_brand_keyword_special_cases():
    assert get_brand_keyword("The Whole Truth Oats") == "whole truth"
    assert get_brand_keyword("Yoga Bar Oats") == "yoga"
    assert get_brand_keyword("True Elements Oats") == "true"


def test_get_brand_keyword_default_first_word():
    assert get_brand_keyword("Quaker Oats") == "quaker"
    assert get_brand_keyword("Saffola Oats") == "saffola"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_blinkit_oats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blinkit_oats'`

- [ ] **Step 3: Create the migrated, fixed scraper**

Read `C:\Users\singh\Desktop\SCRAPE\scrape_blinkit_oats.py` to confirm its exact current content. Create `scraper/blinkit_oats.py` following the exact same pattern as `scraper/blinkit_goatlife.py` (Task 3), with these differences:

- Keep `BRANDS` (the 10-brand list), `get_brand_keyword`, and the brand-matching `if keyword not in name.lower(): continue` filter inside `scrape_brand` exactly as in the source — these are unchanged.
- `MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"`, `OUTPUT_FILE = ROOT / "scraper" / "output" / "blinkit_oats_data.xlsx"`.
- `COLUMNS = ["City", "Locality", "Brand Searched", "Product Name", "Pack Size", "Selling Price", "MRP", "Discount %", "Stock Left", "Rating", "Serviceable"]`.
- `not_available_row(city, locality, brand, reason="Not Available")` takes a `brand` parameter (unlike Task 3's, which hardcodes `BRAND`) — keep this signature from the source.
- The main loop's inner structure changes from "one action per locality" to "one action per (locality, brand) pair": replace `check_captcha` calls in `set_location`/`scrape_brand` with `wait_for_manual_unblock(driver, beep)` exactly as in Task 3. Restructure the main loop identically to Task 3's `while i < total` / `retries` / `should_restart_driver` / `is_dead_session_error` pattern, but with an inner loop over `brands_todo = [b for b in BRANDS if f"{city}|{locality}|{b}" not in done_keys]` (matching the source's existing per-locality-per-brand `done_keys` granularity — use `wb.done_keys(["City", "Locality", "Brand Searched"])` instead of Task 3's 2-column key). On a dead-session exception inside the brand loop, apply the same restart-and-retry-current-locality logic as Task 3 (retry the whole locality, including any brands within it not yet done, rather than trying to resume mid-brand-loop — simpler and matches the granularity `done_keys` already tracks).
- Call `jittered_sleep(1.0, jitter_s=1.5)` once per locality (after all its brands are processed and saved), not once per brand — matching Task 3's per-locality pacing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_blinkit_oats.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify the file compiles and imports cleanly**

Run: `cd scraper && python -m py_compile blinkit_oats.py`
Expected: no output, exit code 0

- [ ] **Step 6: Update the launcher and wire it to the DB sync**

Overwrite `C:\Users\singh\Desktop\Run_Blinkit_Oats_Scraper.bat` with:
```bat
@echo off
title Blinkit Oats Scraper
echo Starting Blinkit Oats Scraper...
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python blinkit_oats.py
if errorlevel 1 (
    echo Scraper reported an error - skipping DB sync.
    pause
    exit /b 1
)
echo Syncing to database...
cd /d C:\Users\singh\Desktop\GOATLife\scripts
python sync_shelf_snapshots.py blinkit ..\scraper\output\blinkit_oats_data.xlsx
pause
```

- [ ] **Step 7: Commit**

```bash
git add scraper/blinkit_oats.py scraper/test_blinkit_oats.py
git commit -m "feat: migrate Blinkit competitor-oats scraper with reliability fixes"
```

---

### Task 5: Migrate Swiggy competitor-oats scraper (drop dead v1)

**Files:**
- Create: `scraper/swiggy_oats.py`
- Create: `scraper/test_swiggy_oats.py`
- Modify: `C:\Users\singh\Desktop\Run_Swiggy_Oats_Scraper.bat` (overwrite in place)

**Interfaces:**
- Consumes: same `scraper/_reliability.py` interfaces, same canonical pattern as Tasks 3-4.

`scrape_swiggy_oats.py` (v1) is never migrated — it's the superseded version the plan's Global Constraints call out as dead code. Migrate only `scrape_swiggy_oats_v2.py`, renamed to drop the version suffix now that there's no v1 alongside it. This file additionally has `wait_for_waf` (a body-text WAF check) and `parse_card_block` (zero test coverage) that the other two Blinkit scrapers don't have.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_swiggy_oats.py`:
```python
from swiggy_oats import parse_card_block


def test_parse_card_block_extracts_name_price_and_pack_size():
    card_text = "Yoga Bar 26% High Protein Oats\n400 g\n₹399\n₹499\n4.2"
    products = parse_card_block(card_text)
    assert len(products) == 1
    p = products[0]
    assert p["name"] == "Yoga Bar 26% High Protein Oats"
    assert p["pack_size"] == "400 g"
    assert p["sp"] == "₹399"
    assert p["mrp"] == "₹499"
    assert p["rating"] == "4.2"


def test_parse_card_block_detects_sponsored():
    card_text = "SPONSORED\nQuaker Oats\n₹199"
    products = parse_card_block(card_text)
    assert products[0]["sponsored"] == "True"


def test_parse_card_block_filters_noise_lines():
    card_text = "ADD\nCUSTOMISABLE\n15 MINS\nSaffola Oats\n₹149"
    products = parse_card_block(card_text)
    assert len(products) == 1
    assert products[0]["name"] == "Saffola Oats"


def test_parse_card_block_returns_empty_for_no_product_lines():
    assert parse_card_block("15 MINS\nADD") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_swiggy_oats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swiggy_oats'`

- [ ] **Step 3: Create the migrated, fixed scraper**

Read `C:\Users\singh\Desktop\SCRAPE\scrape_swiggy_oats_v2.py` to confirm its exact current content. Create `scraper/swiggy_oats.py` following the same pattern as Tasks 3-4, with these differences:

- Keep `BRANDS`, `parse_card_block`, `get_visible_input`, `click_element` unchanged from the source.
- Replace `wait_for_waf(driver)` (the source's own body-text WAF poll, which only checks 2 markers and gives up silently after 15 iterations) with `wait_for_manual_unblock(driver, beep)` from `_reliability` at both call sites (inside `set_location` and inside `scrape_brand`) — this is the fix for the "CAPTCHA detection only checks the page `<title>`" gap identified during Sprint 1 planning; `is_blocked` checks both title and body markers, and actually pauses for a human instead of giving up after a fixed short wait. You'll need to add a `beep()` function (copy the same 2-beep pattern from Task 3) since this source file didn't have one.
- `MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"`, `OUTPUT_FILE = ROOT / "scraper" / "output" / "swiggy_oats_data.xlsx"`.
- `COLUMNS = ["City", "Locality", "Brand Searched", "Product Name", "Protein Info", "Sponsored", "Pack Size", "Selling Price", "MRP", "Discount %", "Stock Left", "Rating", "Serviceable"]`.
- Same `while i < total` restructuring as Task 4 (inner brand loop, `done_keys` on `["City", "Locality", "Brand Searched"]`, dead-session retry restarts and retries the whole locality).
- `jittered_sleep(1.0, jitter_s=1.5)` once per locality.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_swiggy_oats.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Verify the file compiles and imports cleanly**

Run: `cd scraper && python -m py_compile swiggy_oats.py`
Expected: no output, exit code 0

- [ ] **Step 6: Update the launcher and wire it to the DB sync**

Overwrite `C:\Users\singh\Desktop\Run_Swiggy_Oats_Scraper.bat` with:
```bat
@echo off
title Swiggy Instamart Oats Scraper
color 0B
echo =================================================================
echo   SWIGGY INSTAMART OATS SCRAPER
echo =================================================================
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python swiggy_oats.py
if errorlevel 1 (
    color 0C
    echo Scraper reported an error - skipping DB sync.
    pause
    exit /b 1
)
color 0A
echo Syncing to database...
cd /d C:\Users\singh\Desktop\GOATLife\scripts
python sync_shelf_snapshots.py swiggy ..\scraper\output\swiggy_oats_data.xlsx
color 07
pause
```

- [ ] **Step 7: Commit**

```bash
git add scraper/swiggy_oats.py scraper/test_swiggy_oats.py
git commit -m "feat: migrate Swiggy competitor-oats scraper with reliability fixes, drop dead v1"
```

---

### Task 6: Migrate Zepto competitor-oats scraper (largest fix — no prior block handling or resume logic)

**Files:**
- Create: `scraper/zepto_oats.py`
- Create: `scraper/test_zepto_oats.py`
- Modify: `C:\Users\singh\Desktop\Run_Zepto_Oats_Scraper.bat` (overwrite in place)

**Interfaces:**
- Consumes: same `scraper/_reliability.py` interfaces.

This is the scraper the crash investigation was originally about, and the one with the most gaps: zero CAPTCHA/block detection, zero resume/dedup logic, and the worst version of the per-save I/O problem (`load_workbook()`-from-disk then `save()`, once per brand — up to ~5,000 full disk round-trips in a complete run). All three are fixed by this migration.

- [ ] **Step 1: Write the failing tests**

Create `scraper/test_zepto_oats.py`:
```python
from zepto_oats import parse_zepto_card


def test_parse_zepto_card_extracts_name_price_pack_rating():
    card_text = "Yoga Bar Oats|₹399|₹499|400g|4.2|(120)"
    result = parse_zepto_card(card_text)
    assert result["sp"] == "Rs.399"
    assert result["mrp"] == "Rs.499"
    assert result["pack_size"] == "400g"
    assert result["rating"] == "4.2"
    assert result["reviews"] == "(120)"


def test_parse_zepto_card_detects_sponsored():
    card_text = "Ad|Quaker Oats|₹199"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "True"


def test_parse_zepto_card_not_sponsored_by_default():
    card_text = "Saffola Oats|₹149"
    result = parse_zepto_card(card_text)
    assert result["sponsored"] == "False"


def test_parse_zepto_card_handles_missing_fields():
    result = parse_zepto_card("Some Product Name")
    assert result["sp"] == "N/A"
    assert result["mrp"] == "N/A"
    assert result["pack_size"] == "N/A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest test_zepto_oats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zepto_oats'`

- [ ] **Step 3: Create the migrated, fixed scraper**

Read `C:\Users\singh\Desktop\SCRAPE\scrape_zepto_oats.py` to confirm its exact current content. Create `scraper/zepto_oats.py` following the same overall shape as Tasks 3-5, with these differences (this file needs more new code than the others, since it's missing what they already had):

- Keep `BRANDS`, `extract_buy_price`, `load_localities`, `parse_zepto_card` unchanged from the source.
- `MAGICBRICKS_FILE` and localities loading: the source's `load_localities("magicbricks_combined.xlsx")` takes a relative path — change the call site to `load_localities(str(ROOT / "data" / "magicbricks_combined.xlsx"))` with `ROOT = Path(__file__).resolve().parents[1]` added near the top of the file (matching Tasks 3-5's `ROOT` pattern).
- `OUTPUT_FILE = ROOT / "scraper" / "output" / "zepto_oats_data.xlsx"` (source used a bare relative `"zepto_oats_data.xlsx"`).
- Add a `beep()` function (same 2-beep pattern as Task 3 — this source file had none).
- **Add block detection**: after every `driver.get(...)` call inside `scrape_zepto`'s main flow (both the initial `driver.get('https://www.zeptonow.com/')` and each per-brand `driver.get(f"https://www.zeptonow.com/search?query={query}")`), insert `if not wait_for_manual_unblock(driver, beep): print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)` — this source file never checked for CAPTCHA/blocks at all.
- **Replace the per-brand `load_workbook(output_file)` / `ws.append(...)` / `wb.save(output_file)` pattern** (the source's worst-case I/O: full disk round-trip on every brand) with a single `IncrementalWorkbook` created once before the locality loop starts, with `COLUMNS = ["Locality", "Brand Searched", "Rank", "Product Name", "Selling Price", "MRP", "Discount", "Pack Size", "Rating", "Reviews", "Sponsored"]`, `.append_row(r)` called per record inside the existing `for r in records:` loop (replacing `ws.append(list(r.values()))`), and `.save()` called once per locality (after all its brands are done) instead of once per brand.
- **Add resume/dedup**: before the `for idx, loc_obj in enumerate(localities, 1):` loop, compute `done_keys = wb.done_keys(["Locality", "Brand Searched"])` and print a resume message if non-empty (matching Tasks 3-5's pattern). Inside the loop, skip a `(locality, brand)` pair already in `done_keys`, and add newly-processed pairs to it after each brand completes.
- **Add driver restart**: same `should_restart_driver(idx-1, restart_every=25)` check as Tasks 3-5, positioned at the top of the per-locality loop, before the location-setting step.
- **Add dead-session recovery**: wrap the per-locality block (location-setting + all its brand searches) in the same `try/except` + `is_dead_session_error` + restart-and-retry-current-locality pattern as Tasks 3-5. Since the source's loop is a `for idx, loc_obj in enumerate(...)`, not indexable by a mutable counter, restructure it into the same `while i < total: ... i += 1` shape used in Tasks 3-5 (with `retries` reset per locality) so a dead-session retry can re-run the same locality without advancing.
- Add `jittered_sleep(1.0, jitter_s=1.5)` once per locality, after its `wb.save()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scraper && python -m pytest test_zepto_oats.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Verify the file compiles and imports cleanly**

Run: `cd scraper && python -m py_compile zepto_oats.py`
Expected: no output, exit code 0

- [ ] **Step 6: Update the launcher and wire it to the DB sync**

Overwrite `C:\Users\singh\Desktop\Run_Zepto_Oats_Scraper.bat` with:
```bat
@echo off
title Zepto Instamart Oats Scraper
color 0D
echo =================================================================
echo   ZEPTO INSTAMART OATS SCRAPER
echo =================================================================
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python zepto_oats.py
if errorlevel 1 (
    color 0C
    echo Scraper reported an error - skipping DB sync.
    pause
    exit /b 1
)
color 0A
echo Syncing to database...
cd /d C:\Users\singh\Desktop\GOATLife\scripts
python sync_shelf_snapshots.py zepto ..\scraper\output\zepto_oats_data.xlsx
color 07
pause
```

- [ ] **Step 7: Commit**

```bash
git add scraper/zepto_oats.py scraper/test_zepto_oats.py
git commit -m "feat: migrate Zepto scraper, add block detection and resume logic it never had"
```

---

### Task 7: Migrate Magicbricks and Reliance scrapers (no reliability rewrite)

**Files:**
- Create: `scraper/magicbricks.py`
- Create: `scraper/reliance.py`
- Modify: `C:\Users\singh\Desktop\Run_Magicbricks_Scraper.bat` (overwrite in place)
- Modify: `C:\Users\singh\Desktop\Run_Reliance_Scraper.bat` (overwrite in place)

**Interfaces:**
- Consumes: nothing from `scraper/_reliability.py` — per Global Constraints, these two are structurally different (single pass over ~10 cities, not a 500-locality×10-brand nested loop) and out of the diagnosed crash scope.
- Produces: nothing other tasks depend on.

These two scrapers produce raw `data/`-input files for the ML notebooks (`magicbricks_combined.xlsx`, `reliance_smart_bazaar_stores.xlsx`), not `shelf_snapshots` rows — their `.bat` files do not call any sync script.

- [ ] **Step 1: Migrate Magicbricks scraper**

Read `C:\Users\singh\Desktop\SCRAPE\scrape_magicbricks_manual.py` in full to get its exact current content. Create `scraper/magicbricks.py` with identical content, except:
- Add `from pathlib import Path` and `ROOT = Path(__file__).resolve().parents[1]` near the top.
- Change the output file path (wherever the source writes its resulting xlsx — check the source for the exact variable name and current hardcoded path) to write into `ROOT / "data" / "magicbricks_combined.xlsx"` instead of the source's `C:\Users\singh\Desktop\SCRAPE\...` path, so the scraper's output lands directly where NB01 already expects it.

- [ ] **Step 2: Migrate Reliance scraper**

Read `C:\Users\singh\Desktop\SCRAPE\scrape_reliance_manual.py` in full to get its exact current content. Create `scraper/reliance.py` with identical content, except:
- Add `from pathlib import Path` and `ROOT = Path(__file__).resolve().parents[1]` near the top.
- Change the output file path to write into `ROOT / "data" / "reliance_smart_bazaar_stores.xlsx"` instead of the source's hardcoded `SCRAPE` path.

- [ ] **Step 3: Verify both files compile and import cleanly**

Run:
```bash
cd scraper
python -m py_compile magicbricks.py
python -m py_compile reliance.py
```
Expected: no output, exit code 0 for both

- [ ] **Step 4: Update the launchers**

Overwrite `C:\Users\singh\Desktop\Run_Magicbricks_Scraper.bat` with:
```bat
@echo off
echo Starting the Magicbricks Localities Scraper...
echo If a browser window opens and asks you to solve a CAPTCHA, please solve it!
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python magicbricks.py
echo Scraper finished!
pause
```

Overwrite `C:\Users\singh\Desktop\Run_Reliance_Scraper.bat` with:
```bat
@echo off
echo Starting the Reliance Smart Bazaar Scraper...
echo If a browser window opens and asks you to solve a CAPTCHA, please solve it!
cd /d C:\Users\singh\Desktop\GOATLife\scraper
python reliance.py
echo Scraper finished!
pause
```

- [ ] **Step 5: Commit**

```bash
git add scraper/magicbricks.py scraper/reliance.py
git commit -m "feat: migrate Magicbricks and Reliance scrapers (no reliability rewrite — out of diagnosed scope)"
```

---

## Self-Review Notes

**Spec coverage:** Task 1 covers the full `_reliability.py` toolkit from the design doc's "Scraper reliability fixes" section (all 6 items: driver restart, dead-session recovery, incremental save, resume/dedup, block detection, jitter). Task 2 covers the GitHub Actions button, correcting the design doc's unstated assumption that the master parquet would already be committed. Tasks 3-6 cover all 4 oats scrapers with the reliability fixes applied; Task 7 covers the 2 locality/store scrapers explicitly *without* the reliability rewrite, correcting the design doc's implication that "the 6 scrapers" uniformly get a `sync_to_db.py` call — only the 4 that produce shelf-pricing data do.

**Placeholder scan:** no TBD/TODO. Tasks 4-6 use "apply the same pattern as Task 3, with these differences" rather than repeating ~150 lines of unchanged Selenium boilerplate per file — every actual *change* is given as real code or a precise, itemized instruction (exact line replacements, exact new constants), not a vague "handle appropriately." This is a deliberate deviation from reproducing full-file content in every task, justified by the source files being 3-4x larger than Sprint 1's, with most of their content (card-parsing regex, suggestion-clicking XPath logic) genuinely unchanged.

**Type consistency:** `IncrementalWorkbook`, `is_blocked`, `wait_for_manual_unblock`, `jittered_sleep`, `should_restart_driver`, `is_dead_session_error` are defined once in Task 1 and consumed with identical signatures across Tasks 3-6. `sync_shelf_snapshots.py <platform> <xlsx_path>` (Sprint 1) is called with `platform` values (`blinkit_goatlife`, `blinkit`, `swiggy`, `zepto`) matching exactly the `PLATFORM_COLUMNS` keys already defined in that script.
