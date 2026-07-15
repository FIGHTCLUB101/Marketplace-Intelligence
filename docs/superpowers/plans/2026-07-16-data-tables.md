# Data Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sticky headers and a horizontal-scroll fallback on every `.lb` table, click-to-sort columns on Leaderboard's table and all 4 Gems tables (via one shared module, not 5 reimplementations), a loading skeleton for the KPI ribbon/ledger while `data-localities.js` parses, and an empty state for zero-result Map filters.

**Architecture:** One new shared module (`web/sortable-table.js`) exporting a pure sort-state-transition function (unit-tested) plus a DOM-wiring function (manually verified, consistent with this codebase's existing pure-function-only test convention). Every table-producing function across `views.js`/`sequence.js` gets a `.table-wrap` div and, where scoped, `data-sort-key` attributes wired to the shared module. `index.html`/`app.js` get the loading skeleton and empty-state markup/logic.

**Tech Stack:** Vanilla JS, plain CSS — no build step, no new runtime dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-data-tables-design.md` — read it if anything below is ambiguous.
- **Correction found during planning, not in the spec:** `renderMethodology()`'s action-matrix table (`views.js`) is a 7th `.lb` table instance the spec's "6 places" count didn't name explicitly (it undercounted `renderGems()`'s repeated-helper table as one thing and separately missed Methodology). It gets `.table-wrap` and sticky headers like every other table, but **no sorting** — it's a fixed 3-row legend, not data to explore, the same category of exclusion already applied to Launch Roadmap's tables.
- Sorting scope is exactly: Leaderboard's table (ranks 6-60) + Gems' 4 sub-tables. Nothing else gets `data-sort-key` attributes.
- Sub-project 2's top-5 insight cards (`renderLeaderboard()`) are not touched by any task in this plan.
- No new frontend dependencies, no jsdom — `wireSortableTable`'s DOM-touching half is verified manually; only `nextSortState` (the pure state-transition logic) gets a unit test, per this repo's established testing convention.

---

### Task 1: `web/sortable-table.js` — shared sort module

**Files:**
- Create: `web/sortable-table.js`
- Test: `web/tests/sortable-table.test.js`

**Interfaces:**
- Produces: `nextSortState(current: {key, dir}, clickedKey: string) -> {key, dir}` (pure, exported, tested).
- Produces: `wireSortableTable(tableEl: HTMLTableElement, rows: any[], columns: Array<{key, sort: (a,b)=>number}>, renderRow: (row)=>string) -> void` — queries `th[data-sort-key]` inside `tableEl`, wires click handlers, writes sorted rows into `tableEl.querySelector('tbody')`, and does the initial paint. Consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests for `nextSortState`**

Create `web/tests/sortable-table.test.js`:
```js
import { test } from 'node:test';
import assert from 'node:assert';
import { nextSortState } from '../sortable-table.js';

test('nextSortState: clicking a column with no prior sort starts ascending', () => {
  assert.deepEqual(nextSortState({ key: null, dir: 1 }, 'icp'), { key: 'icp', dir: 1 });
});

test('nextSortState: clicking a different column resets to ascending', () => {
  assert.deepEqual(nextSortState({ key: 'city', dir: -1 }, 'icp'), { key: 'icp', dir: 1 });
});

test('nextSortState: clicking the same column flips direction', () => {
  assert.deepEqual(nextSortState({ key: 'icp', dir: 1 }, 'icp'), { key: 'icp', dir: -1 });
  assert.deepEqual(nextSortState({ key: 'icp', dir: -1 }, 'icp'), { key: 'icp', dir: 1 });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/tests/sortable-table.test.js`
Expected: FAIL — `Cannot find module '../sortable-table.js'`

- [ ] **Step 3: Write the module**

Create `web/sortable-table.js`:
```js
// Shared click-to-sort behavior for Leaderboard's table and all 4 Gems tables —
// one implementation instead of five, since the interaction is identical everywhere.

// Pure: given the current sort state and the key of the column just clicked,
// returns the next sort state. Clicking a new column always starts ascending;
// clicking the already-active column flips direction.
export function nextSortState(current, clickedKey) {
  if (current.key === clickedKey) {
    return { key: clickedKey, dir: -current.dir };
  }
  return { key: clickedKey, dir: 1 };
}

// DOM-coupled: wires click handlers onto every th[data-sort-key] inside tableEl,
// sorts `rows` by the active column's comparator, and writes renderRow(row) output
// into tableEl's <tbody>. Not unit-tested (no DOM harness in this repo) — verified
// manually per the plan's regression-pass task.
export function wireSortableTable(tableEl, rows, columns, renderRow) {
  let state = { key: null, dir: 1 };

  const render = () => {
    const col = columns.find((c) => c.key === state.key);
    const sorted = col ? [...rows].sort((a, b) => state.dir * col.sort(a, b)) : rows;
    tableEl.querySelector('tbody').innerHTML = sorted.map(renderRow).join('');
  };

  tableEl.querySelectorAll('th[data-sort-key]').forEach((th) => {
    th.addEventListener('click', () => {
      state = nextSortState(state, th.dataset.sortKey);
      tableEl.querySelectorAll('th[data-sort-key]').forEach((h) => h.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(state.dir === 1 ? 'sorted-asc' : 'sorted-desc');
      render();
    });
  });

  render();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test web/tests/sortable-table.test.js`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add web/sortable-table.js web/tests/sortable-table.test.js
git commit -m "feat: add shared sortable-table module (nextSortState + wireSortableTable)"
```

---

### Task 2: `styles.css` — sticky headers, sort indicators, scroll wrapper, skeleton, empty state

**Files:**
- Modify: `web/styles.css`

**Interfaces:**
- Produces: sticky `.lb thead th`, `.lb th[data-sort-key]`/`.sorted-asc`/`.sorted-desc`, `.table-wrap`, `.skeleton`/`.skeleton-kpi`/`.skeleton-ledger`, `.map-empty` — consumed by Tasks 3-6.

- [ ] **Step 1: Add sticky-header and sort-indicator rules**

In `web/styles.css`, replace:
```css
.lb{width:100%;border-collapse:collapse;font-size:13px}
.lb th{text-align:left;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--line)}
.lb td{padding:8px 10px;border-bottom:1px solid var(--line)}
.lb td.mono{font-family:var(--mono)}
.lb tr:hover td{background:var(--hover-bg)}
```
with:
```css
.lb{width:100%;border-collapse:collapse;font-size:13px}
.lb th{text-align:left;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--line)}
.lb thead th{position:sticky;top:0;background:var(--paper);z-index:2}
.lb th[data-sort-key]{cursor:pointer;user-select:none}
.lb th[data-sort-key]:hover{color:var(--ink)}
.lb th.sorted-asc::after{content:' \25B2';font-size:9px}
.lb th.sorted-desc::after{content:' \25BC';font-size:9px}
.lb td{padding:8px 10px;border-bottom:1px solid var(--line)}
.lb td.mono{font-family:var(--mono)}
.lb tr:hover td{background:var(--hover-bg)}
.table-wrap{overflow-x:auto}
```

- [ ] **Step 2: Add the skeleton and map-empty classes**

Add to the end of `web/styles.css`:
```css

.skeleton{background:linear-gradient(90deg, var(--line) 25%, var(--surface) 50%, var(--line) 75%);background-size:200% 100%;animation:skeleton-pulse 1.5s ease-in-out infinite;border-radius:var(--radius)}
.skeleton-kpi{height:64px;flex:1;margin:11px 22px}
.skeleton-ledger{height:220px;margin:4px 0}
@keyframes skeleton-pulse{0%{background-position:200% 0}100%{background-position:-200% 0}}

.map-empty{display:none;position:absolute;inset:0;align-items:center;justify-content:center;flex-direction:column;gap:10px;background:var(--paper);z-index:4;text-align:center}
.map-empty.show{display:flex}
.map-empty p{font-size:14px;color:var(--muted)}
.map-empty button{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:8px 16px;cursor:pointer}
.map-empty button:hover{border-color:var(--muted)}
```

- [ ] **Step 3: Commit**

```bash
git add web/styles.css
git commit -m "feat: add sticky headers, sort indicators, scroll wrapper, skeleton, and map-empty CSS"
```

---

### Task 3: `views.js` — Leaderboard table sorting

**Files:**
- Modify: `web/views.js`

**Interfaces:**
- Consumes: `wireSortableTable` from `./sortable-table.js` (Task 1); `.table-wrap`/sort CSS (Task 2).

- [ ] **Step 1: Import `wireSortableTable`**

At the top of `web/views.js`, change:
```js
import { colorFor, labelFor } from './contract.js';
```
to:
```js
import { colorFor, labelFor } from './contract.js';
import { wireSortableTable } from './sortable-table.js';
```

- [ ] **Step 2: Replace the table portion of `renderLeaderboard()`**

Replace (everything from `const tableHtml = ...` to the end of the function):
```js
  const tableHtml = `
    <table class="lb"><thead><tr>
      <th>#</th><th>Locality</th><th>City</th><th>ICP</th><th>Verdict</th><th>Serviceability</th>
      <th>Archetype</th><th>Action</th><th>GOAT on BL</th><th>Price Adv.</th></tr></thead><tbody>
    ${rest.map((l, i) => {
      const a = num(l.price_advantage_blinkit);
      const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
        : '<span style="color:#ccc">n/a</span>';
      return `<tr>
        <td class="mono">${i + 6}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
        <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
        <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
        <td>${gtmDot(l.gtm_action)}</td>
        <td class="mono">${goatBL}</td>
        <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
    }).join('')}
    </tbody></table>`;

  document.getElementById('leaderboard').innerHTML = insightsHtml + tableHtml;
}
```
with:
```js
  const restRanked = rest.map((l, i) => ({ ...l, _rank: i + 6 }));

  const goatRank = (l) => {
    if (l.blinkit_goat_present === '' || l.blinkit_goat_present == null) return 0;
    return truthy(l.blinkit_goat_present) ? 2 : 1;
  };

  const renderTableRow = (l) => {
    const a = num(l.price_advantage_blinkit);
    const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
      ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
      : '<span style="color:#ccc">n/a</span>';
    return `<tr>
      <td class="mono">${l._rank}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
      <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td class="mono">${goatBL}</td>
      <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
  };

  const tableHtml = `
    <div class="table-wrap">
    <table class="lb" id="leaderboard-table"><thead><tr>
      <th>#</th><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th>Verdict</th><th>Serviceability</th>
      <th>Archetype</th><th>Action</th><th data-sort-key="goat">GOAT on BL</th><th data-sort-key="price">Price Adv.</th></tr></thead><tbody></tbody></table>
    </div>`;

  document.getElementById('leaderboard').innerHTML = insightsHtml + tableHtml;

  const columns = [
    { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
    { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
    { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
    { key: 'goat', sort: (a, b) => goatRank(a) - goatRank(b) },
    { key: 'price', sort: (a, b) => (num(a.price_advantage_blinkit) ?? -Infinity) - (num(b.price_advantage_blinkit) ?? -Infinity) },
  ];
  wireSortableTable(document.getElementById('leaderboard-table'), restRanked, columns, renderTableRow);
}
```
(This keeps `insightCard`/`top5`/`insightsHtml` — everything above `const tableHtml = ...` — completely unchanged; only the table's construction and rendering changes.)

- [ ] **Step 2: Visually verify**

Using a local dev server, open Leaderboard. Confirm: table headers (Locality/City/ICP/GOAT on BL/Price Adv.) show a pointer cursor and an arrow appears on click; clicking twice reverses the arrow direction and row order; clicking a different column resets to ascending; the `#` rank numbers stay attached to their original locality (e.g. sorting by City should NOT produce sequential `#6, #7, #8...` — it should show the original ranks out of order). Confirm the 5 top insight cards are unaffected by any of this.

- [ ] **Step 3: Commit**

```bash
git add web/views.js
git commit -m "feat: add click-to-sort columns to Leaderboard's table"
```

---

### Task 4: `views.js` — Gems sorting + Methodology scroll wrapper

**Files:**
- Modify: `web/views.js`

**Interfaces:**
- Consumes: `wireSortableTable` (Task 1, already imported by Task 3's edit to this same file).

- [ ] **Step 1: Replace `renderGems()` in full**

Replace the entire function:
```js
export function renderGems() {
  const table = (title, rows, extraHead, extraCell) => `
    <h3 class="gh">${title} <span class="k">(${rows.length})</span></h3>
    <table class="lb"><thead><tr><th>Locality</th><th>City</th><th>ICP</th><th>Price</th>${extraHead}<th>Action</th></tr></thead><tbody>
    ${rows.slice(0, 25).map((l) => `<tr><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td class="mono">${inr(l.res_avg_buy_imputed)}</td>
      ${extraCell(l)}<td>${gtmDot(l.gtm_action)}</td></tr>`).join('')}
    </tbody></table>`;
  const t = (v) => v === true || v === 'true' || v === 'True';
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const pareto = L.filter((l) => t(l.pareto_optimal)).sort((a, b) => +b.icp_score - +a.icp_score);
  const hidden = L.filter((l) => t(l.hidden_gem_v2)).sort((a, b) => +b.icp_score - +a.icp_score);
  const spill  = L.filter((l) => t(l.spillover_gem)).sort((a, b) => +b.icp_score - +a.icp_score);
  const ws     = L.filter((l) => t(l.is_white_space)).sort((a, b) => +b.icp_score - +a.icp_score);

  const wsTable = ws.length ? `
    <h3 class="gh">White space — no oats competitors on Blinkit or Zepto <span class="k">(${ws.length})</span></h3>
    <p class="vd">These localities have strong demand signals but zero competitor presence in the oats aisle on either Blinkit or Zepto. First-mover advantage is real here.</p>
    <table class="lb"><thead><tr><th>Locality</th><th>City</th><th>ICP</th><th>Verdict</th><th>Action</th><th>GOAT on BL</th></tr></thead><tbody>
    ${ws.slice(0, 30).map((l) => `<tr>
      <td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td>
      <td>${verdictBadge(l.icp_verdict)}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td>${t(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>'}</td>
    </tr>`).join('')}
    </tbody></table>` : '';

  document.getElementById('gems').innerHTML =
    wsTable +
    table('Pareto-optimal — strong on every dimension', pareto, '<th>Serviceability</th>', (l) => `<td>${l.serviceability_state}</td>`) +
    table('Hidden gems — high ICP, under-priced/under-covered', hidden, '<th>Archetype</th>', (l) => `<td>${l.archetype_ml}</td>`) +
    table('Spillover gems — cheaper than graph neighbours', spill, '<th>Nearest store</th>', (l) => `<td class="mono">${l.nearest_known_darkstore_km ? l.nearest_known_darkstore_km + ' km' : '—'}</td>`);
}
```
with:
```js
export function renderGems() {
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const t = (v) => v === true || v === 'true' || v === 'True';
  const goatRank = (l) => {
    if (l.blinkit_goat_present === '' || l.blinkit_goat_present == null) return 0;
    return t(l.blinkit_goat_present) ? 2 : 1;
  };
  const pareto = L.filter((l) => t(l.pareto_optimal)).sort((a, b) => +b.icp_score - +a.icp_score);
  const hidden = L.filter((l) => t(l.hidden_gem_v2)).sort((a, b) => +b.icp_score - +a.icp_score);
  const spill  = L.filter((l) => t(l.spillover_gem)).sort((a, b) => +b.icp_score - +a.icp_score);
  const ws     = L.filter((l) => t(l.is_white_space)).sort((a, b) => +b.icp_score - +a.icp_score);

  const tableConfigs = [];

  const table = (title, rows, extraHead, extraCell, extraCol) => {
    const id = `gems-table-${tableConfigs.length}`;
    const columns = [
      { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
      { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
      { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
      { key: 'price', sort: (a, b) => (num(a.res_avg_buy_imputed) ?? -Infinity) - (num(b.res_avg_buy_imputed) ?? -Infinity) },
    ];
    if (extraCol) columns.push(extraCol);
    const renderRow = (l) => `<tr><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td class="mono">${inr(l.res_avg_buy_imputed)}</td>
      ${extraCell(l)}<td>${gtmDot(l.gtm_action)}</td></tr>`;
    const extraHeadKeyed = extraCol ? extraHead.replace('<th>', `<th data-sort-key="${extraCol.key}">`) : extraHead;
    tableConfigs.push({ id, rows: rows.slice(0, 25), columns, renderRow });
    return `
      <h3 class="gh">${title} <span class="k">(${rows.length})</span></h3>
      <div class="table-wrap">
      <table class="lb" id="${id}"><thead><tr><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th data-sort-key="price">Price</th>${extraHeadKeyed}<th>Action</th></tr></thead><tbody></tbody></table>
      </div>`;
  };

  const wsColumns = [
    { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
    { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
    { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
    { key: 'goat', sort: (a, b) => goatRank(a) - goatRank(b) },
  ];
  const wsRenderRow = (l) => `<tr>
      <td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td>
      <td>${verdictBadge(l.icp_verdict)}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td>${t(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>'}</td>
    </tr>`;
  let wsTable = '';
  if (ws.length) {
    const id = 'gems-white-space';
    tableConfigs.push({ id, rows: ws.slice(0, 30), columns: wsColumns, renderRow: wsRenderRow });
    wsTable = `
      <h3 class="gh">White space — no oats competitors on Blinkit or Zepto <span class="k">(${ws.length})</span></h3>
      <p class="vd">These localities have strong demand signals but zero competitor presence in the oats aisle on either Blinkit or Zepto. First-mover advantage is real here.</p>
      <div class="table-wrap">
      <table class="lb" id="${id}"><thead><tr><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th>Verdict</th><th>Action</th><th data-sort-key="goat">GOAT on BL</th></tr></thead><tbody></tbody></table>
      </div>`;
  }

  document.getElementById('gems').innerHTML =
    wsTable +
    table('Pareto-optimal — strong on every dimension', pareto, '<th>Serviceability</th>', (l) => `<td>${l.serviceability_state}</td>`, { key: 'serviceability', sort: (a, b) => a.serviceability_state.localeCompare(b.serviceability_state) }) +
    table('Hidden gems — high ICP, under-priced/under-covered', hidden, '<th>Archetype</th>', (l) => `<td>${l.archetype_ml}</td>`, { key: 'archetype', sort: (a, b) => a.archetype_ml.localeCompare(b.archetype_ml) }) +
    table('Spillover gems — cheaper than graph neighbours', spill, '<th>Nearest store</th>', (l) => `<td class="mono">${l.nearest_known_darkstore_km ? l.nearest_known_darkstore_km + ' km' : '—'}</td>`, { key: 'nearest', sort: (a, b) => (num(a.nearest_known_darkstore_km) ?? Infinity) - (num(b.nearest_known_darkstore_km) ?? Infinity) });

  tableConfigs.forEach(({ id, rows, columns, renderRow }) => {
    wireSortableTable(document.getElementById(id), rows, columns, renderRow);
  });
}
```

- [ ] **Step 2: Add the scroll wrapper to `renderMethodology()`'s table (no sorting)**

In `renderMethodology()`, replace:
```js
    <h3 class="gh">Action matrix</h3>
    <table class="lb"><thead><tr><th></th><th>Confirmed / Likely</th><th>Unknown</th></tr></thead><tbody>
      <tr><td class="mono">GO</td><td><span style="color:${colorFor('PUSH-NOW')}">● Push now</span></td><td><span style="color:${colorFor('D2C / OFFLINE - verify QC')}">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:${colorFor('SAMPLE + QC test')}">● Sample + QC test</span></td><td><span style="color:${colorFor('SAMPLE (D2C / offline)')}">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td></tr>
    </tbody></table>
```
with:
```js
    <h3 class="gh">Action matrix</h3>
    <div class="table-wrap">
    <table class="lb"><thead><tr><th></th><th>Confirmed / Likely</th><th>Unknown</th></tr></thead><tbody>
      <tr><td class="mono">GO</td><td><span style="color:${colorFor('PUSH-NOW')}">● Push now</span></td><td><span style="color:${colorFor('D2C / OFFLINE - verify QC')}">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:${colorFor('SAMPLE + QC test')}">● Sample + QC test</span></td><td><span style="color:${colorFor('SAMPLE (D2C / offline)')}">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td></tr>
    </tbody></table>
    </div>
```

- [ ] **Step 3: Visually verify**

Using a local dev server, open Untapped Markets (Gems). Confirm: all 4 tables (White space, Pareto-optimal, Hidden gems, Spillover gems) have sortable Locality/City/ICP/Price columns plus their one category-specific column (Serviceability/Archetype/Nearest store/GOAT on BL respectively); clicking sorts correctly and independently per table (sorting one table doesn't affect the others). Open Method and confirm the action-matrix table scrolls horizontally if narrow but has no sort arrows/cursor on its headers.

- [ ] **Step 4: Commit**

```bash
git add web/views.js
git commit -m "feat: add click-to-sort columns to Gems tables, scroll wrapper to Methodology table"
```

---

### Task 5: `sequence.js` — scroll wrapper only

**Files:**
- Modify: `web/sequence.js`

**Interfaces:** none new — purely additive markup, no sorting.

- [ ] **Step 1: Wrap both table templates in `renderPlan()`**

Replace:
```js
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Archetype</th><th>Brands</th><th>Cost</th></tr></thead><tbody>
      ${wd.affordable.map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td>${l.archetype_ml}</td><td class="mono">${l.n_brands_confirmed}/3</td><td class="mono">${inr(l._cost)}</td></tr>`).join('')}
      </tbody></table>`;
```
with:
```js
      <div class="table-wrap">
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Archetype</th><th>Brands</th><th>Cost</th></tr></thead><tbody>
      ${wd.affordable.map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td>${l.archetype_ml}</td><td class="mono">${l.n_brands_confirmed}/3</td><td class="mono">${inr(l._cost)}</td></tr>`).join('')}
      </tbody></table>
      </div>`;
```
Replace:
```js
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Action</th></tr></thead><tbody>
      ${plan.watch.slice(0, 10).map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td><span style="color:${colorFor(l.gtm_action)}">●</span> ${labelFor(l.gtm_action)}</td></tr>`).join('')}
      </tbody></table>`;
```
with:
```js
      <div class="table-wrap">
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Action</th></tr></thead><tbody>
      ${plan.watch.slice(0, 10).map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td><span style="color:${colorFor(l.gtm_action)}">●</span> ${labelFor(l.gtm_action)}</td></tr>`).join('')}
      </tbody></table>
      </div>`;
```

- [ ] **Step 2: Visually verify**

Using a local dev server, open Launch Roadmap, pick a city/platform/budget, click Generate. Confirm the resulting wave tables and watch-list table have no sort cursor/arrows on their headers (unscoped, as designed) but their headers still stick when the page is scrolled with a long result.

- [ ] **Step 3: Commit**

```bash
git add web/sequence.js
git commit -m "feat: add scroll wrapper to Launch Roadmap tables"
```

---

### Task 6: `index.html` + `app.js` — loading skeleton + Map empty state

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `.skeleton`/`.skeleton-kpi`/`.skeleton-ledger`/`.map-empty` CSS (Task 2).

- [ ] **Step 1: Add skeleton placeholders to `#kpi-ribbon`/`#ledger`**

In `web/index.html`, replace:
```html
    <div class="kpi-ribbon" id="kpi-ribbon"></div>
    <div class="map-body">
    <aside class="ledger">
      <h4>Decision ledger</h4>
      <div id="ledger"></div>
```
with:
```html
    <div class="kpi-ribbon" id="kpi-ribbon"><div class="skeleton skeleton-kpi"></div></div>
    <div class="map-body">
    <aside class="ledger">
      <h4>Decision ledger</h4>
      <div id="ledger"><div class="skeleton skeleton-ledger"></div></div>
```
(`renderKpis()`/`buildLedger()` already overwrite these divs' `innerHTML` unconditionally — no JS change needed for the skeleton to disappear once real content loads.)

- [ ] **Step 2: Add the map-empty element**

In `web/index.html`, replace:
```html
    <div class="map-wrap">
      <div id="map-container"></div>
```
with:
```html
    <div class="map-wrap">
      <div id="map-container"></div>
      <div id="map-empty" class="map-empty">
        <p>No localities match these filters.</p>
        <button id="map-empty-clear" type="button">Clear filters</button>
      </div>
```

- [ ] **Step 3: Wire the empty-state toggle into `applyFilter()`**

In `web/app.js`, replace:
```js
function applyFilter() {
  const vis = L.filter(matches);
  setLocalityData(vis);
  const push = vis.filter((l) => l.gtm_action === 'PUSH-NOW').length;
  const samp = vis.filter((l) => l.gtm_action.startsWith('SAMPLE')).length;
  document.getElementById('map-stats').innerHTML =
    `<b>${vis.length}</b> localities · <b>${push}</b> push-now · <b>${samp}</b> sample`;
}
```
with:
```js
function applyFilter() {
  const vis = L.filter(matches);
  setLocalityData(vis);
  const push = vis.filter((l) => l.gtm_action === 'PUSH-NOW').length;
  const samp = vis.filter((l) => l.gtm_action.startsWith('SAMPLE')).length;
  document.getElementById('map-stats').innerHTML =
    `<b>${vis.length}</b> localities · <b>${push}</b> push-now · <b>${samp}</b> sample`;
  document.getElementById('map-empty').classList.toggle('show', vis.length === 0);
}
```

- [ ] **Step 4: Wire the "Clear filters" button**

In `web/app.js`, inside the `document.addEventListener('DOMContentLoaded', () => { ... })` callback, add this immediately after the existing `bsel.addEventListener('change', ...)` line:
```js
  document.getElementById('map-empty-clear').addEventListener('click', () => {
    sel.city = 'all'; sel.verdict = 'all'; sel.serviceability = 'all';
    document.getElementById('f-city').value = 'all';
    document.getElementById('f-verdict').value = 'all';
    document.getElementById('f-svc').value = 'all';
    applyFilter();
  });
```

- [ ] **Step 5: Visually verify**

Using a local dev server: reload the page and watch for the KPI ribbon/ledger skeleton flash before real content appears (may be very brief on a fast local server — throttle network in devtools if needed to see it clearly). Then set the Map filters to a combination that matches zero localities (e.g. pick a city, then a verdict that city has none of) and confirm the centered "No localities match these filters" message appears over the map; click "Clear filters" and confirm all three filter dropdowns reset to "All..." and localities reappear. Repeat in dark mode.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: add loading skeleton for KPI ribbon/ledger and empty state for Map filters"
```

---

### Task 7: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suites**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/shelf-monitor.test.js web/tests/sortable-table.test.js`
Expected: all pass.
Run: `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v`
Expected: PASS (nothing in this plan touches `contract.js`).

- [ ] **Step 2: Manual end-to-end walkthrough, light and dark**

With a local dev server: scroll each of the 7 `.lb` tables (Leaderboard, Gems ×4, Methodology, and a generated Launch Roadmap result) and confirm headers stick; click through every sortable column on Leaderboard and each Gems table, both directions; resize the browser narrow and confirm tables scroll horizontally instead of breaking the page layout; reload and observe the skeleton flash; drive the Map filters to zero results and back via "Clear filters." Click through every other view (Margin Calculator, Shelf Monitor both sub-tabs) to confirm no regression and no console errors. Repeat the whole pass in dark mode.

- [ ] **Step 3: Commit (only if fixes were needed)**

If the walkthrough surfaced any bugs, fix them, re-run the affected step, then:
```bash
git add -A
git commit -m "fix: address issues found in data-tables regression pass"
```
If no fixes were needed, skip this step — nothing to commit.
