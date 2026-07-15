# Shelf Monitor Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Shelf Monitor's flat, unfiltered change feed with a grouped/filterable "This Week" view, and add a new "Compare Brands" view surfacing the previously-unused Blinkit/Instamart/Zepto competitor-sweep data.

**Architecture:** Two sub-tabs rendered inside the existing `#shelf-monitor` container (no `index.html` changes — it already renders entirely via `web/shelf-monitor.js`'s `innerHTML`). This Week groups the existing `/api/shelf/changes` payload by `(event type, product)` client-side. Compare Brands adds one small backend endpoint (`GET /api/shelf/snapshot?platform=X`) and fetches+caches each platform's current snapshot client-side on first selection.

**Tech Stack:** FastAPI + psycopg2 (backend, `web/api/`), vanilla JS with `node --test` for pure-function tests (frontend, `web/`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-shelf-monitor-redesign-design.md` — read it if anything below is ambiguous.
- Backend tests use the exact `requires_db` skip-marker + `TestXyzXYZ`/`test_platform_xyz`-prefixed-fixture + explicit-`DELETE`-cleanup convention already used throughout `web/api/test_api.py` and `web/api/test_queries.py`. Do not introduce a different DB test pattern.
- Frontend tests are pure-function only (`node --test`, no DOM framework available in this repo) — mirror `web/tests/shelf-monitor.test.js`'s existing style exactly.
- No changes to `web/index.html`, `web/api/models.py`, or `sync_shelf_snapshots.py` — out of scope per the spec.
- Rank column must be omitted (not shown empty) for platforms that never populate it (`blinkit`, `swiggy`).

---

### Task 1: Backend — `fetch_current_snapshot` query function

**Files:**
- Modify: `web/api/queries.py`
- Test: `web/api/test_queries.py`

**Interfaces:**
- Produces: `fetch_current_snapshot(conn, scrape_run_id) -> list[dict]`, each dict having keys `shelf_snapshot_id, platform, locality_id, city_raw, locality_raw, brand_searched, rank, product_name, pack_size, selling_price, mrp, discount_pct, stock_left, rating, reviews, sponsored, serviceable, is_goat, started_at, finished_at`.

- [ ] **Step 1: Write the failing test**

Add to `web/api/test_queries.py`, after the existing `test_fetch_snapshot_rows_returns_expected_columns` test (around line 118):

```python
@requires_db
def test_fetch_current_snapshot_returns_full_columns_for_run():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_snapshot", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, rank, product_name, selling_price, mrp, discount_pct, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_snapshot", "TestCityXYZ", "TestLocalityXYZ",
                 "Pintola Oats", 3, "Pintola High Protein Oats", 199.0, 249.0, 20.0, False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        rows = fetch_current_snapshot(conn, scrape_run_id)
        assert len(rows) == 1
        assert rows[0]["product_name"] == "Pintola High Protein Oats"
        assert rows[0]["brand_searched"] == "Pintola Oats"
        assert rows[0]["rank"] == 3
        assert rows[0]["mrp"] == 249.0
        assert rows[0]["started_at"] is not None
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()
```

Update the import line at the top of `web/api/test_queries.py` (currently `from queries import (compute_belts, fetch_brand_defence_rate, fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_shelf_trends, fetch_snapshot_rows)`) to add `fetch_current_snapshot`:

```python
from queries import (
    compute_belts, fetch_brand_defence_rate, fetch_current_snapshot, fetch_drop_calendar,
    fetch_latest_two_scrape_run_ids, fetch_shelf_trends, fetch_snapshot_rows,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web/api && python -m pytest test_queries.py::test_fetch_current_snapshot_returns_full_columns_for_run -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_current_snapshot'`

- [ ] **Step 3: Write minimal implementation**

Add to `web/api/queries.py`, after `fetch_snapshot_rows` (after line 185):

```python
SHELF_CURRENT_SNAPSHOT_SQL = """
    SELECT
        s.shelf_snapshot_id, s.platform, s.locality_id, s.city_raw, s.locality_raw,
        s.brand_searched, s.rank, s.product_name, s.pack_size, s.selling_price,
        s.mrp, s.discount_pct, s.stock_left, s.rating, s.reviews, s.sponsored,
        s.serviceable, s.is_goat, r.started_at, r.finished_at
    FROM shelf_snapshots s
    JOIN scrape_runs r ON r.scrape_run_id = s.scrape_run_id
    WHERE s.scrape_run_id = %s
    ORDER BY s.city_raw, s.locality_raw
"""


def fetch_current_snapshot(conn, scrape_run_id):
    """Returns every shelf_snapshots row for one run (all columns), unlike
    fetch_snapshot_rows which only selects the narrow subset shelf_changes.py's
    diff functions need. Used for current-state (non-diffed) views."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SHELF_CURRENT_SNAPSHOT_SQL, (scrape_run_id,))
        return cur.fetchall()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web/api && python -m pytest test_queries.py::test_fetch_current_snapshot_returns_full_columns_for_run -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/api/queries.py web/api/test_queries.py
git commit -m "feat: add fetch_current_snapshot query for full-column current-run reads"
```

---

### Task 2: Backend — `GET /api/shelf/snapshot` endpoint

**Files:**
- Modify: `web/api/index.py`
- Test: `web/api/test_api.py`

**Interfaces:**
- Consumes: `queries.fetch_current_snapshot(conn, scrape_run_id)` and `queries.fetch_latest_two_scrape_run_ids(conn, platform)` (both from Task 1 / pre-existing).
- Produces: `GET /api/shelf/snapshot?platform=X` → `list[ShelfSnapshot]` JSON (empty list `[]` if the platform has zero scrape runs).

- [ ] **Step 1: Write the failing tests**

Add to `web/api/test_api.py`, after the existing `test_get_shelf_trends_returns_empty_series_for_unknown_platform` test (end of file, after line 397):

```python
@requires_db
def test_get_shelf_snapshot_returns_empty_list_for_platform_with_no_runs():
    response = client.get("/api/shelf/snapshot?platform=test_platform_xyz_empty_snap")
    assert response.status_code == 200
    assert response.json() == []


@requires_db
def test_get_shelf_snapshot_returns_current_rows_for_seeded_platform():
    conn = get_connection()
    scrape_run_id = None
    snapshot_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (platform, source_file) VALUES (%s, %s) "
                "RETURNING scrape_run_id",
                ("test_platform_xyz_snap", "test.xlsx"),
            )
            scrape_run_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO shelf_snapshots (scrape_run_id, platform, city_raw, locality_raw, "
                "brand_searched, rank, product_name, selling_price, is_goat) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING shelf_snapshot_id",
                (scrape_run_id, "test_platform_xyz_snap", "TestCityXYZ", "TestLocalityXYZ",
                 "Yoga Bar Oats", None, "Yoga Bar Premium Golden Rolled Oats", 230.0, False),
            )
            snapshot_id = cur.fetchone()[0]
        conn.commit()

        response = client.get("/api/shelf/snapshot?platform=test_platform_xyz_snap")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["product_name"] == "Yoga Bar Premium Golden Rolled Oats"
        assert body[0]["rank"] is None
    finally:
        with conn.cursor() as cur:
            if snapshot_id is not None:
                cur.execute("DELETE FROM shelf_snapshots WHERE shelf_snapshot_id = %s", (snapshot_id,))
            if scrape_run_id is not None:
                cur.execute("DELETE FROM scrape_runs WHERE scrape_run_id = %s", (scrape_run_id,))
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web/api && python -m pytest test_api.py -k test_get_shelf_snapshot -v`
Expected: FAIL with 404 Not Found (route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Add to `web/api/index.py`, after `get_shelf_trends` (end of file, after line 148):

```python
@app.get("/api/shelf/snapshot", response_model=list[ShelfSnapshot])
def get_shelf_snapshot(platform: str = Query(...)):
    conn = get_connection()
    try:
        newest_id, _ = queries.fetch_latest_two_scrape_run_ids(conn, platform)
        if newest_id is None:
            return []
        return queries.fetch_current_snapshot(conn, newest_id)
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web/api && python -m pytest test_api.py -k test_get_shelf_snapshot -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add web/api/index.py web/api/test_api.py
git commit -m "feat: add GET /api/shelf/snapshot endpoint for current-state platform reads"
```

---

### Task 3: Frontend — brand normalization + visibility rate pure helpers

**Files:**
- Modify: `web/shelf-monitor.js`
- Test: `web/tests/shelf-monitor.test.js`

**Interfaces:**
- Produces: `normalizeBrandName(name: string) -> string` (strips a trailing `" Oats"` suffix, case-insensitive).
- Produces: `computeVisibilityRate(rows: {is_goat: boolean}[]) -> number | null` (percentage 0-100, `null` for an empty array).

- [ ] **Step 1: Write the failing tests**

Add to `web/tests/shelf-monitor.test.js`, after the existing `formatBrandDefenceRate` test (end of file, after line 35):

```js
test('normalizeBrandName strips a trailing " Oats" suffix', () => {
  assert.equal(normalizeBrandName('Pintola Oats'), 'Pintola');
  assert.equal(normalizeBrandName('The Whole Truth Oats'), 'The Whole Truth');
  assert.equal(normalizeBrandName('Pintola'), 'Pintola');
});

test('computeVisibilityRate: percentage of is_goat rows, null for empty', () => {
  assert.equal(computeVisibilityRate([]), null);
  assert.equal(computeVisibilityRate([{ is_goat: true }, { is_goat: false }]), 50);
  assert.equal(computeVisibilityRate([{ is_goat: false }, { is_goat: false }]), 0);
  assert.equal(computeVisibilityRate([{ is_goat: true }]), 100);
});
```

Update the import line at the top of `web/tests/shelf-monitor.test.js` (currently `import { formatBrandDefenceRate, formatTrendRows, severityFor } from '../shelf-monitor.js';`):

```js
import {
  computeVisibilityRate, formatBrandDefenceRate, formatTrendRows, normalizeBrandName, severityFor,
} from '../shelf-monitor.js';
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: FAIL — `normalizeBrandName is not a function` / `computeVisibilityRate is not a function`

- [ ] **Step 3: Write minimal implementation**

Add to `web/shelf-monitor.js`, after `formatBrandDefenceRate` (after line 21):

```js
export function normalizeBrandName(name) {
  return name.replace(/\s+Oats$/i, '').trim();
}

export function computeVisibilityRate(rows) {
  if (!rows.length) return null;
  return (100 * rows.filter((r) => r.is_goat).length) / rows.length;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add web/shelf-monitor.js web/tests/shelf-monitor.test.js
git commit -m "feat: add brand-name normalization and visibility-rate helpers"
```

---

### Task 4: Frontend — `groupChangesByProduct` pure function

**Files:**
- Modify: `web/shelf-monitor.js`
- Test: `web/tests/shelf-monitor.test.js`

**Interfaces:**
- Consumes: a `ShelfChanges`-shaped object (fields `goat_displaced, goat_gone, rank_intrusions, price_changes, new_products, gone_products` — matches `web/api/models.py`'s `ShelfChanges`).
- Produces: `groupChangesByProduct(changes) -> Array<{ key: string, eventType: string, severity: 'critical'|'warning'|'info', label: string, product: string, entries: Array<{ city: string, locality: string, detail: string }> }>`. `entries` within a group are in the same order the source arrays were processed; `gone_products` entries with `is_goat: true` are excluded (matches the existing `renderChangeRows` behavior being replaced).

- [ ] **Step 1: Write the failing test**

Add to `web/tests/shelf-monitor.test.js`, after the tests added in Task 3:

```js
test('groupChangesByProduct groups same (eventType, product) pairs and counts entries', () => {
  const changes = {
    goat_displaced: [
      { city: 'Mumbai', locality: 'Sion', rank: 1, was: 'GOAT Life Mocha Marvel', now: 'MISSING' },
      { city: 'Pune', locality: 'Wakad', rank: 2, was: 'GOAT Life Mocha Marvel', now: 'Still listed, now rank 5' },
    ],
    goat_gone: [],
    rank_intrusions: [
      { city: 'Delhi', locality: 'Saket', rank: 1, intruder: 'Yoga Bar Oats' },
    ],
    price_changes: [],
    new_products: [],
    gone_products: [
      { city: 'Pune', locality: 'Baner', rank: 4, product: 'Saffola Oats', is_goat: false },
      { city: 'Delhi', locality: 'Saket', rank: 2, product: 'GOAT Life Mocha Marvel', is_goat: true },
    ],
  };
  const groups = groupChangesByProduct(changes);
  assert.equal(groups.length, 3);

  const displaced = groups.find((g) => g.eventType === 'goat_displaced');
  assert.equal(displaced.product, 'GOAT Life Mocha Marvel');
  assert.equal(displaced.severity, 'critical');
  assert.equal(displaced.entries.length, 2);
  assert.deepEqual(displaced.entries[0], { city: 'Mumbai', locality: 'Sion', detail: 'MISSING' });

  const intrusion = groups.find((g) => g.eventType === 'rank_intrusions');
  assert.equal(intrusion.severity, 'warning');
  assert.equal(intrusion.entries[0].detail, 'intruded at rank 1');

  // GOAT's own gone_products entry (is_goat: true) must be excluded.
  const gone = groups.find((g) => g.eventType === 'gone_products');
  assert.equal(gone.entries.length, 1);
  assert.equal(gone.product, 'Saffola Oats');
});

test('groupChangesByProduct returns an empty array for no changes', () => {
  const changes = {
    goat_displaced: [], goat_gone: [], rank_intrusions: [], price_changes: [],
    new_products: [], gone_products: [],
  };
  assert.deepEqual(groupChangesByProduct(changes), []);
});
```

Update the import line again to add `groupChangesByProduct`:

```js
import {
  computeVisibilityRate, formatBrandDefenceRate, formatTrendRows, groupChangesByProduct,
  normalizeBrandName, severityFor,
} from '../shelf-monitor.js';
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: FAIL — `groupChangesByProduct is not a function`

- [ ] **Step 3: Write minimal implementation**

Add to `web/shelf-monitor.js`, after `computeVisibilityRate` (added in Task 3):

```js
const EVENT_META = {
  goat_displaced: { severity: 'critical', label: 'displaced' },
  goat_gone: { severity: 'critical', label: 'no longer listed' },
  rank_intrusions: { severity: 'warning', label: 'intruded' },
  price_changes: { severity: 'warning', label: 'price moved' },
  new_products: { severity: 'info', label: 'appeared' },
  gone_products: { severity: 'info', label: 'no longer listed' },
};

function entryFor(eventType, e) {
  switch (eventType) {
    case 'goat_displaced':
      return { city: e.city, locality: e.locality, product: e.was, detail: e.now };
    case 'goat_gone':
      return { city: e.city, locality: e.locality, product: e.product, detail: `last seen rank ${e.rank}` };
    case 'rank_intrusions':
      return { city: e.city, locality: e.locality, product: e.intruder, detail: `intruded at rank ${e.rank}` };
    case 'price_changes': {
      const dir = e.change < 0 ? '▼' : '▲';
      return {
        city: e.city, locality: e.locality, product: e.product,
        detail: `${dir}₹${Math.abs(e.change).toFixed(0)} (₹${e.old_price} → ₹${e.new_price})`,
      };
    }
    case 'new_products':
      return { city: e.city, locality: e.locality, product: e.product, detail: `appeared at rank ${e.rank}` };
    case 'gone_products':
      return { city: e.city, locality: e.locality, product: e.product, detail: 'no longer listed' };
    default:
      throw new Error(`unknown eventType: ${eventType}`);
  }
}

export function groupChangesByProduct(changes) {
  const eventLists = {
    goat_displaced: changes.goat_displaced,
    goat_gone: changes.goat_gone,
    rank_intrusions: changes.rank_intrusions,
    price_changes: changes.price_changes,
    new_products: changes.new_products,
    gone_products: changes.gone_products.filter((e) => !e.is_goat),
  };
  const groups = new Map();
  Object.entries(eventLists).forEach(([eventType, list]) => {
    list.forEach((e) => {
      const entry = entryFor(eventType, e);
      const key = `${eventType}::${entry.product}`;
      if (!groups.has(key)) {
        groups.set(key, {
          key, eventType, severity: EVENT_META[eventType].severity, label: EVENT_META[eventType].label,
          product: entry.product, entries: [],
        });
      }
      groups.get(key).entries.push({ city: entry.city, locality: entry.locality, detail: entry.detail });
    });
  });
  return [...groups.values()];
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add web/shelf-monitor.js web/tests/shelf-monitor.test.js
git commit -m "feat: add groupChangesByProduct helper for the This Week grouped feed"
```

---

### Task 5: Frontend — sub-tab shell + This Week grouped/filtered render

**Files:**
- Modify: `web/shelf-monitor.js`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: `severityFor`, `formatBrandDefenceRate`, `formatTrendRows`, `groupChangesByProduct` (all pre-existing/Task 4), `SEVERITY_LABEL` (existing module-level const).
- Produces: `render()` (replaces the current default export target of `AppState.initShelfMonitor`) which draws two sub-tab pill buttons ("This Week", "Compare Brands") and delegates to per-tab render functions. `renderThisWeek(el)` is the first tab, rendering into whatever container element it's passed.

This task replaces `renderChangeRows` and the top-level `render` function. Read the current full file first — it should match what's shown in Task 4's diff (helpers through `groupChangesByProduct` already added), plus the original `fetchJson`, `alertRow`, `renderConquestBreadth`, `renderTrendsTable`, `render`, and `AppState.initShelfMonitor = render;` at the bottom unchanged from before this plan started.

- [ ] **Step 1: Replace `render` and remove `renderChangeRows` + its now-unused `alertRow` helper**

In `web/shelf-monitor.js`, delete the `alertRow` function (the three-line block `function alertRow(cls, html) { return \`<div class="alert-row ${cls}">${html}</div>\`; }`) and the `renderChangeRows` function entirely (the block starting `function renderChangeRows(changes) {` through its closing `}`) — `alertRow` has no other caller once `renderChangeRows` is gone (`renderConquestBreadth` builds its `alert-row` markup inline via its own template literal, not through this helper). Then replace the existing `render` function and the `AppState.initShelfMonitor = render;` line at the end of the file with:

```js
function cityLocalityIndex(groups) {
  const byCity = new Map();
  groups.forEach((g) => g.entries.forEach((e) => {
    if (!byCity.has(e.city)) byCity.set(e.city, new Set());
    byCity.get(e.city).add(e.locality);
  }));
  return byCity;
}

function groupCard(g) {
  const collapsed = g.entries.length > 5;
  const entriesHtml = g.entries.map((e) =>
    `<div class="group-entry">${e.city} (${e.locality}) — ${e.detail}</div>`
  ).join('');
  return `
    <div class="alert-row ${g.severity} group-card" data-key="${g.key}">
      <div class="group-head">
        <strong>${g.product}</strong> ${g.label}
        <span class="group-count">in ${g.entries.length} localit${g.entries.length === 1 ? 'y' : 'ies'}</span>
        ${collapsed ? '<button type="button" class="group-toggle">Show</button>' : ''}
      </div>
      <div class="group-entries" ${collapsed ? 'style="display:none"' : ''}>${entriesHtml}</div>
    </div>`;
}

function renderGroupedChanges(groups, cityFilter, localityFilter) {
  const filtered = groups
    .map((g) => ({
      ...g,
      entries: g.entries.filter((e) =>
        (cityFilter === 'all' || e.city === cityFilter) &&
        (localityFilter === 'all' || e.locality === localityFilter)),
    }))
    .filter((g) => g.entries.length > 0);
  if (!filtered.length) return '<p class="info">No changes match this filter.</p>';
  return filtered.map(groupCard).join('');
}

function wireGroupToggles(container) {
  container.querySelectorAll('.group-toggle').forEach((btn) => btn.addEventListener('click', () => {
    const entries = btn.closest('.group-card').querySelector('.group-entries');
    const open = entries.style.display !== 'none';
    entries.style.display = open ? 'none' : 'block';
    btn.textContent = open ? 'Show' : 'Hide';
  }));
}

function fillLocalityOptions(select, byCity, city) {
  const localities = city === 'all'
    ? [...new Set([...byCity.values()].flatMap((s) => [...s]))]
    : [...(byCity.get(city) || [])];
  select.innerHTML = '<option value="all">All localities</option>' +
    localities.sort().map((l) => `<option>${l}</option>`).join('');
}

async function renderThisWeek(el) {
  el.innerHTML = '<p class="info">Loading…</p>';
  try {
    const [changes, trends] = await Promise.all([
      fetchJson('/api/shelf/changes?platform=blinkit_goatlife'),
      fetchJson('/api/shelf/trends?platform=blinkit_goatlife'),
    ]);
    if (changes.status === 'insufficient_history') {
      el.innerHTML = `<p class="info">${changes.narrative[0]}</p>`;
      return;
    }
    const sev = severityFor(changes);
    const groups = groupChangesByProduct(changes);
    const byCity = cityLocalityIndex(groups);
    el.innerHTML = `
      <p class="vd">Week-over-week changes to GOAT Life's Blinkit brand-search shelf, comparing run ${changes.old_run_id} → ${changes.new_run_id}.</p>
      <div class="severity-banner ${sev}">${SEVERITY_LABEL[sev]}</div>
      <div class="stat-label">Brand Defence Rate</div>
      <div class="stat-val">${formatBrandDefenceRate(changes.brand_defence_rate)}</div>
      <div class="narrative">${changes.narrative.join('<br>')}</div>
      <div class="filter-row">
        <div class="field"><label>City</label><select class="f-tw-city"><option value="all">All cities</option>${[...byCity.keys()].sort().map((c) => `<option>${c}</option>`).join('')}</select></div>
        <div class="field"><label>Locality</label><select class="f-tw-locality"></select></div>
      </div>
      <div class="group-list"></div>
      ${renderConquestBreadth(changes.conquest_breadth)}
      <h3 class="gh">Observed Digital Shelf Position</h3>
      <p class="info">We observe the output of Blinkit's ranking algorithm, not its inputs — this is rank as it actually appeared, tracked week over week.</p>
      ${renderTrendsTable(trends)}`;

    const citySel = el.querySelector('.f-tw-city');
    const localitySel = el.querySelector('.f-tw-locality');
    const groupList = el.querySelector('.group-list');
    const rerenderGroups = () => {
      groupList.innerHTML = renderGroupedChanges(groups, citySel.value, localitySel.value);
      wireGroupToggles(groupList);
    };
    fillLocalityOptions(localitySel, byCity, 'all');
    citySel.addEventListener('change', () => { fillLocalityOptions(localitySel, byCity, citySel.value); rerenderGroups(); });
    localitySel.addEventListener('change', rerenderGroups);
    rerenderGroups();
  } catch (e) {
    console.error('shelf-monitor This Week render failed', e);
    el.innerHTML = '<p class="info">Failed to load — check the API is running.</p>';
  }
}

const SUBTABS = [
  { id: 'this-week', label: 'This Week', render: renderThisWeek },
];

async function render() {
  const el = document.getElementById('shelf-monitor');
  el.innerHTML = `
    <h2 class="vt">Shelf Monitor</h2>
    <div class="subtabs">${SUBTABS.map((t, i) => `<button type="button" class="subtab${i === 0 ? ' active' : ''}" data-subtab="${t.id}">${t.label}</button>`).join('')}</div>
    <div class="subtab-body"></div>`;
  const body = el.querySelector('.subtab-body');
  const activate = (id) => {
    el.querySelectorAll('.subtab').forEach((b) => b.classList.toggle('active', b.dataset.subtab === id));
    SUBTABS.find((t) => t.id === id).render(body);
  };
  el.querySelectorAll('.subtab').forEach((b) => b.addEventListener('click', () => activate(b.dataset.subtab)));
  activate(SUBTABS[0].id);
}

AppState.initShelfMonitor = render;
```

(`SUBTABS` has one entry for now — Task 6 adds the second and expands this array. This keeps Task 5 independently testable/mergeable without a half-wired second tab.)

- [ ] **Step 2: Add CSS for sub-tabs, filters, and group cards**

Add to `web/styles.css`, after the existing `.alert-row.info{border-left-color:var(--goat)}` line (end of file):

```css

.subtabs{display:flex;gap:4px;margin:14px 0 18px;border-bottom:1px solid var(--line)}
.subtab{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:none;border:none;padding:8px 4px;margin-right:14px;cursor:pointer;border-bottom:2px solid transparent}
.subtab:hover{color:var(--ink)}
.subtab.active{color:var(--ink);border-bottom-color:var(--goat)}

.filter-row{display:flex;gap:14px;margin:14px 0;flex-wrap:wrap}
.field select{font-family:var(--sans);font-size:13px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:6px 8px;outline:none;min-width:160px}
.field select:focus{border-color:var(--goat)}

.group-card{display:flex;flex-direction:column;gap:6px}
.group-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.group-count{color:var(--muted);font-size:12px}
.group-toggle{margin-left:auto;font-family:var(--mono);font-size:11px;text-transform:uppercase;color:var(--goat);background:none;border:1px solid var(--line);border-radius:6px;padding:3px 8px;cursor:pointer}
.group-entries{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted)}
```

- [ ] **Step 3: Run the existing pure-function test suite to confirm nothing broke**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: PASS (all tests — this task didn't touch any of the tested pure functions)

- [ ] **Step 4: Manually verify in browser**

Using the local dev setup (from `web/api/`: `uvicorn index:app --reload`; separately, the dev-proxy script serving `web/` and forwarding `/api/*` to it — see prior session notes, or use `vercel dev` if the Windows sibling-import bug has since been fixed): open the dashboard, click **Shelf Monitor**. Confirm:
- The "This Week" pill is visible and active by default.
- The weekly-change feed now shows grouped cards (e.g. one "GOAT Life ... Mocha Marvel displaced — in N localities" card instead of N separate rows).
- Groups with ≤5 localities are expanded by default; larger groups show a "Show" toggle that expands/collapses on click.
- The City filter populates with real city names; selecting one narrows both the Locality dropdown and which groups/entries are visible. Selecting "All cities" restores everything.
- Severity banner, brand defence rate, narrative, conquest breadth, and the trends table still render as before.

- [ ] **Step 5: Commit**

```bash
git add web/shelf-monitor.js web/styles.css
git commit -m "feat: group and filter the This Week shelf-change feed"
```

---

### Task 6: Frontend — Compare Brands tab

**Files:**
- Modify: `web/shelf-monitor.js`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: `fetchJson`, `normalizeBrandName`, `computeVisibilityRate` (existing/Task 3), `GET /api/shelf/snapshot?platform=X` (Task 2), the `SUBTABS` array and `render()`/`renderThisWeek` from Task 5.
- Produces: `renderCompareBrands(el)`, registered as the second entry in `SUBTABS`.

- [ ] **Step 1: Add the Compare Brands render function and register it**

Add to `web/shelf-monitor.js`, after `renderThisWeek` (added in Task 5) and before the `const SUBTABS = [...]` line:

```js
const COMPETITOR_PLATFORMS = [
  { value: 'blinkit', label: 'Blinkit' },
  { value: 'swiggy', label: 'Instamart' },
  { value: 'zepto', label: 'Zepto' },
];
const COMPETITOR_BRANDS = [
  'Alpino', 'Cosmix', 'MuscleBlaze', 'Pintola', 'Quaker', 'Saffola', 'SuperYou',
  'The Whole Truth', 'True Elements', 'Yoga Bar',
];

const compareState = { snapshots: {}, visibilityRates: {} };

async function fetchPlatformSnapshot(platform) {
  if (!compareState.snapshots[platform]) {
    compareState.snapshots[platform] = await fetchJson(`/api/shelf/snapshot?platform=${platform}`);
    compareState.visibilityRates[platform] = computeVisibilityRate(compareState.snapshots[platform]);
  }
  return compareState.snapshots[platform];
}

function headlineStatRow() {
  const stats = COMPETITOR_PLATFORMS.map((p) => {
    const rate = compareState.visibilityRates[p.value];
    const text = rate === null || rate === undefined ? '…' : `${rate.toFixed(1)}%`;
    return `<div class="visibility-stat"><span class="stat-label">${p.label}</span><span class="stat-val">${text}</span></div>`;
  }).join('');
  return `<div class="visibility-row">${stats}</div>`;
}

function compareTableRows(rows, brand, city, locality) {
  const normalized = normalizeBrandName(brand);
  const brandRows = rows.filter((r) => normalizeBrandName(r.brand_searched || '') === normalized);
  const goatLocalities = new Set(
    rows.filter((r) => r.is_goat).map((r) => `${r.city_raw}|||${r.locality_raw}`)
  );
  const filtered = brandRows.filter((r) =>
    (city === 'all' || r.city_raw === city) && (locality === 'all' || r.locality_raw === locality));
  const hasRank = brandRows.some((r) => r.rank !== null && r.rank !== undefined);
  return { filtered, hasRank, goatLocalities };
}

function renderCompareTable(rows, brand, city, locality) {
  const { filtered, hasRank, goatLocalities } = compareTableRows(rows, brand, city, locality);
  if (!filtered.length) return '<p class="info">No data for this brand/filter combination.</p>';
  const head = `<tr><th>City</th><th>Locality</th>${hasRank ? '<th>Rank</th>' : ''}<th>Price</th><th>MRP</th><th>Discount %</th><th>GOAT also here?</th></tr>`;
  const body = filtered.map((r) => {
    const goatHere = goatLocalities.has(`${r.city_raw}|||${r.locality_raw}`) ? 'Yes' : 'No';
    return `<tr><td>${r.city_raw}</td><td>${r.locality_raw}</td>${hasRank ? `<td class="mono">${r.rank ?? '—'}</td>` : ''}<td class="mono">${r.selling_price ?? '—'}</td><td class="mono">${r.mrp ?? '—'}</td><td class="mono">${r.discount_pct ?? '—'}</td><td>${goatHere}</td></tr>`;
  }).join('');
  return `<table class="lb">${head}${body}</table>`;
}

function fillCompareCityLocality(citySel, localitySel, rows, onChange) {
  const byCity = new Map();
  rows.forEach((r) => {
    if (!byCity.has(r.city_raw)) byCity.set(r.city_raw, new Set());
    byCity.get(r.city_raw).add(r.locality_raw);
  });
  citySel.innerHTML = '<option value="all">All cities</option>' +
    [...byCity.keys()].sort().map((c) => `<option>${c}</option>`).join('');
  fillLocalityOptions(localitySel, byCity, 'all');
  citySel.onchange = () => { fillLocalityOptions(localitySel, byCity, citySel.value); onChange(); };
}

async function renderCompareBrands(el) {
  el.innerHTML = `
    ${headlineStatRow()}
    <div class="filter-row">
      <div class="field"><label>Platform</label><select class="f-cmp-platform"><option value="">Select a platform</option>${COMPETITOR_PLATFORMS.map((p) => `<option value="${p.value}">${p.label}</option>`).join('')}</select></div>
      <div class="field"><label>Brand</label><select class="f-cmp-brand">${COMPETITOR_BRANDS.map((b) => `<option>${b}</option>`).join('')}</select></div>
      <div class="field"><label>City</label><select class="f-cmp-city"><option value="all">All cities</option></select></div>
      <div class="field"><label>Locality</label><select class="f-cmp-locality"><option value="all">All localities</option></select></div>
    </div>
    <div class="compare-table"><p class="info">Select a platform to see current shelf data.</p></div>`;

  const platformSel = el.querySelector('.f-cmp-platform');
  const brandSel = el.querySelector('.f-cmp-brand');
  const citySel = el.querySelector('.f-cmp-city');
  const localitySel = el.querySelector('.f-cmp-locality');
  const table = el.querySelector('.compare-table');

  const rerenderTable = () => {
    const rows = compareState.snapshots[platformSel.value] || [];
    table.innerHTML = renderCompareTable(rows, brandSel.value, citySel.value, localitySel.value);
  };

  platformSel.addEventListener('change', async () => {
    const platform = platformSel.value;
    if (!platform) {
      table.innerHTML = '<p class="info">Select a platform to see current shelf data.</p>';
      return;
    }
    table.innerHTML = '<p class="info">Loading…</p>';
    try {
      const rows = await fetchPlatformSnapshot(platform);
      el.querySelector('.visibility-row').outerHTML = headlineStatRow();
      fillCompareCityLocality(citySel, localitySel, rows, rerenderTable);
    } catch (e) {
      console.error('Compare Brands snapshot fetch failed', e);
      table.innerHTML = '<p class="info">Failed to load — check the API is running.</p>';
      return;
    }
    rerenderTable();
  });
  brandSel.addEventListener('change', rerenderTable);
  localitySel.addEventListener('change', rerenderTable);
}
```

- [ ] **Step 2: Register the second sub-tab**

In `web/shelf-monitor.js`, change the `SUBTABS` array (added in Task 5) from:

```js
const SUBTABS = [
  { id: 'this-week', label: 'This Week', render: renderThisWeek },
];
```

to:

```js
const SUBTABS = [
  { id: 'this-week', label: 'This Week', render: renderThisWeek },
  { id: 'compare', label: 'Compare Brands', render: renderCompareBrands },
];
```

- [ ] **Step 3: Add CSS for the headline stat row**

Add to `web/styles.css`, after the `.group-entries{...}` line added in Task 5:

```css

.visibility-row{display:flex;gap:22px;margin-bottom:18px}
.visibility-stat{display:flex;flex-direction:column;gap:2px}
```

- [ ] **Step 4: Run the existing pure-function test suite to confirm nothing broke**

Run: `node --test web/tests/shelf-monitor.test.js`
Expected: PASS (all tests)

- [ ] **Step 5: Manually verify in browser**

With the local dev setup running, open Shelf Monitor and click the **Compare Brands** pill. Confirm:
- The headline stat row shows three tiles (Blinkit / Instamart / Zepto), each starting at "…".
- Selecting "Blinkit" from the Platform dropdown fetches data (one network request to `/api/shelf/snapshot?platform=blinkit`, visible in DevTools Network tab), then the Blinkit tile in the headline row updates to a real percentage, the City/Locality dropdowns populate, and the table renders with columns City/Locality/Price/MRP/Discount %/GOAT also here? (**no Rank column**, since Blinkit never captures it).
- Selecting "Zepto" instead shows a **Rank column** (Zepto does capture it).
- Changing the Brand dropdown re-filters the table instantly with no new network request (check DevTools Network tab — should be empty on brand change).
- Re-selecting a previously-fetched platform doesn't trigger a second network request (cached).
- Selecting a City narrows the table and the Locality dropdown; "GOAT also here?" correctly shows "Yes" for at least one row if GOAT happens to appear in that platform's data (Blinkit should show at least a few "Yes" rows, per the 1.4% visibility finding from the spec's research).

- [ ] **Step 6: Commit**

```bash
git add web/shelf-monitor.js web/styles.css
git commit -m "feat: add Compare Brands tab surfacing blinkit/swiggy/zepto competitor data"
```

---

### Task 7: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd web/api && python -m pytest -q`
Expected: all tests pass (existing + the 4 new tests from Tasks 1-2)

- [ ] **Step 2: Run the full frontend pure-function test suite**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/scoreDisplay.test.js web/tests/shelf-monitor.test.js`
Expected: all tests pass (confirms this work didn't regress any other tab's pure functions)

- [ ] **Step 3: Manual end-to-end walkthrough**

With the local dev setup running (uvicorn + a way to reach `/api/*` from the same origin as the static site — see prior session's dev-proxy workaround if `vercel dev`'s Windows sibling-import bug is still present):
- Load the dashboard fresh, click Shelf Monitor, confirm This Week loads by default with no console errors.
- Switch to Compare Brands and back to This Week — confirm This Week's filters/groups still work correctly on the second visit (re-fetches `/api/shelf/changes` again; this is expected, not cached, per the spec).
- Test the `insufficient_history` path: temporarily change the fetch URL in `renderThisWeek` to a platform with zero runs (e.g. `?platform=doesnotexist`) and confirm the "First week of tracking" message renders without a JS error, then revert the change.
- Confirm no other nav tab (Map, `++` dropdown, Launch Roadmap, Method) regressed — click through each once.

- [ ] **Step 4: Commit (only if Step 3 required fixes)**

If manual verification surfaced any bugs, fix them, re-run the affected step, then:

```bash
git add -A
git commit -m "fix: address issues found in shelf monitor redesign regression pass"
```

If no fixes were needed, skip this step — nothing to commit.
