# Where to Win v2 Dashboard — Implementation Plan

> **For agentic workers:** Execute inline (same session). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Repoint the `web/` MapLibre app onto `localities_master_serviceable.parquet` as one coherent internal tool — localities colored by `gtm_action` over darkstores, light/minimal profile panel, belt view, filters, leaderboard, gems, methodology.

**Architecture:** A Python build script bakes the parquet into sync JS globals (`window.LOCALITIES`, `window.BELTS`) via `contract.py`. The frontend (vanilla ES modules + MapLibre) renders them with a light "color = decision" design system (IBM Plex). Pure logic (contract color/label, filter-expression builder) is unit-tested; map/views verified by screenshot.

**Tech Stack:** Python (pandas, pyarrow) + pytest · vanilla JS ES modules · MapLibre GL JS 3.6.2 (CDN) · IBM Plex Sans/Mono (Google Fonts) · `node --test`.

## Global Constraints

- Single source of truth: `notebooks/artifacts/localities_master_serviceable.parquet` → `scripts/contract.py`. `web/contract.js` mirrors it; a pytest asserts equality.
- Canonical `gtm_action` (5): `PUSH-NOW`, `SAMPLE + QC test`, `SAMPLE (D2C / offline)`, `D2C / OFFLINE - verify QC`, `HOLD`. Colors: `#059669 / #d97706 / #EF9F27 / #2a78d6 / #888780`. Default `#888780`.
- Design tokens: `--paper #FAFAF7`, `--surface #FFFFFF`, `--ink #1A1A1A`, `--muted #6B6B66`, `--line #E6E4DD`, `--goat #E8A317` (brand/active ONLY). Color = decision: only GTM status is saturated.
- Type: IBM Plex Sans (UI) + IBM Plex Mono (numbers/codes/micro-labels).
- Map: MapLibre 3.6.2, dark tiles (`https://tiles.openfreemap.org/styles/dark`) as the working surface; light chrome around it. Only the 886 geocoded localities render. Darkstores from `web/darkstores.json` (kept).
- Views: Map (hero), Leaderboard, Gems, Margin (keep `margin.js`), Methodology. **Drop Gyms.** Retire `data-summary.js` / `data-markers.json`.
- Signature: Decision Ledger (left rail = legend + count + filter). No 01/02/03 numbering.
- Honesty (Methodology): absence ≠ unserviceable; coverage confidence is a proxy; centroid `Confirmed` softer; 115 no-geo excluded.

---

## Task 1: Data bundles + drift guard

**Files:** Create `scripts/build_locality_data.py` (DONE), `web/contract.js` (DONE), `scripts/test_build_locality_data.py`.

- [ ] **Step 1: Write the drift/shape test**
```python
# scripts/test_build_locality_data.py
import re, json, subprocess, sys
from pathlib import Path
import pandas as pd
import contract
ROOT = Path(__file__).resolve().parents[1]

def test_contract_js_matches_py():
    js = (ROOT / "web" / "contract.js").read_text(encoding="utf-8")
    for action, hexv in contract.GTM_COLORS.items():
        assert f"'{action}':" in js and hexv in js, f"{action} {hexv} missing from contract.js"

def test_bundle_built_and_shaped():
    subprocess.run([sys.executable, str(ROOT/"scripts"/"build_locality_data.py")], check=True, cwd=ROOT/"scripts")
    df = pd.read_parquet(ROOT / contract.MASTER_PARQUET)
    n_geo = int(df["lat"].notna().sum())
    js = (ROOT / "web" / "data-localities.js").read_text(encoding="utf-8")
    data = json.loads(js[js.index("["): js.rindex("]") + 1])
    assert len(data) == n_geo
    assert all("color" in r and r["color"].startswith("#") for r in data)
```
- [ ] **Step 2: Run → expect FAIL** (`cd scripts && python -m pytest test_build_locality_data.py -v`) until build runs.
- [ ] **Step 3:** Implementation already exists (`build_locality_data.py`, `contract.js`). Run the build once: `cd scripts && python build_locality_data.py`. Expected: prints geocoded count (~886) + belts(>=3) + gtm distribution.
- [ ] **Step 4: Run test → PASS** (2 passed).
- [ ] **Step 5: Commit** `git add scripts/build_locality_data.py scripts/test_build_locality_data.py web/contract.js web/data-localities.js web/data-belts.js && git commit -m "feat(web2): locality data bundles + contract drift guard"` (data files git-ignored under web/ — commit only if not ignored; otherwise commit scripts + contract.js).

---

## Task 2: contract.js + filter-builder unit tests

**Files:** Create `web/filters.js`, `web/tests/frontend.test.js`.

**Interfaces produced:**
- `colorFor(action) / labelFor(action)` (in `contract.js`, DONE).
- `buildFilter(active)` in `web/filters.js`: takes `{city, verdict, serviceability, gtm}` (each value or `'all'`/`null`) and returns a MapLibre filter expression array or `null` (all-pass). gtm may be a Set of actions.

- [ ] **Step 1: Write the test**
```javascript
// web/tests/frontend.test.js
import { test } from 'node:test';
import assert from 'node:assert';
import { colorFor, labelFor } from '../contract.js';
import { buildFilter } from '../filters.js';

test('contract colors + labels', () => {
  assert.equal(colorFor('PUSH-NOW'), '#059669');
  assert.equal(colorFor('???'), '#888780');
  assert.equal(labelFor('PUSH-NOW'), 'Push now');
});
test('buildFilter all-pass is null', () => {
  assert.equal(buildFilter({ city:'all', verdict:'all', serviceability:'all', gtm:null }), null);
});
test('buildFilter composes facets', () => {
  const f = buildFilter({ city:'Mumbai', verdict:'GO', serviceability:'all', gtm:null });
  assert.equal(f[0], 'all');
  assert.deepEqual(f[1], ['==', ['get','ADDRESS'], 'Mumbai']);
  assert.deepEqual(f[2], ['==', ['get','icp_verdict'], 'GO']);
});
test('buildFilter gtm set -> in expr', () => {
  const f = buildFilter({ city:'all', verdict:'all', serviceability:'all', gtm:new Set(['PUSH-NOW']) });
  assert.deepEqual(f[1], ['in', ['get','gtm_action'], ['literal', ['PUSH-NOW']]]);
});
```
- [ ] **Step 2: Run → FAIL** (`node --test web/tests/frontend.test.js`).
- [ ] **Step 3: Implement `web/filters.js`**
```javascript
export function buildFilter({ city, verdict, serviceability, gtm }) {
  const e = ['all'];
  if (city && city !== 'all') e.push(['==', ['get', 'ADDRESS'], city]);
  if (verdict && verdict !== 'all') e.push(['==', ['get', 'icp_verdict'], verdict]);
  if (serviceability && serviceability !== 'all') e.push(['==', ['get', 'serviceability_state'], serviceability]);
  if (gtm && gtm.size) e.push(['in', ['get', 'gtm_action'], ['literal', [...gtm]]]);
  return e.length > 1 ? e : null;
}
```
- [ ] **Step 4: Run → PASS** (4 tests).
- [ ] **Step 5: Commit** `git add web/contract.js web/filters.js web/tests/frontend.test.js && git commit -m "feat(web2): contract + filter-expression builder (tested)"`

---

## Task 3: Design system + shell (`styles.css`, `index.html`)

**Files:** Rewrite `web/styles.css`, `web/index.html`.

- [ ] **Step 1: `styles.css`** — light design system. Define the token `:root` vars (Global Constraints). Layout: top bar (`.topbar`: brand gold `◆`, mono tabs, active = `--goat`), 3-column body `grid-template-columns: 220px 1fr 0` (ledger | map | panel slides to 320px). `.ledger` rail: rows `.ledger-row` with a status dot (`background` set inline from data), count in IBM Plex Mono, hover/active state; a divider; filters (`<select>` styled minimal: `--surface`, `--line` border, no shadow). `.profile` panel: `--surface`, 1px `--line`, `border-radius:12px`, single soft shadow `0 8px 24px rgba(0,0,0,.06)`, padding 20px. Micro-label class `.k` (IBM Plex Mono, 10px, uppercase, `letter-spacing:.08em`, `--muted`). Status word `.gtm-status` (mono, 18px, color inline). Tables `.lb` (hairline rows). Tabs/`.view` show-hide. `prefers-reduced-motion` + `:focus-visible` outlines. Map container dark bg `#0d0f12`.
- [ ] **Step 2: `index.html`** — head loads IBM Plex Sans+Mono, MapLibre CSS, `styles.css`. Body: `.topbar` (brand + tabs: Map/Leaderboard/Gems/Margin/Methodology). `#map-view` = `.ledger` (id `ledger`) + `#map-container` + `#profile` (hidden) + a floating filter bar (`#f-city #f-verdict #f-svc` selects + a `#belt-select`). `#leaderboard-view`, `#gems-view`, `#margin-view`, `#methodology-view` empty mounts. Scripts (order): `contract`? No—load data globals first: `<script src="data-localities.js"></script>`, `<script src="data-belts.js"></script>`, then MapLibre CDN, then `<script type="module" src="app.js"></script>` (app imports the rest). Keep `margin.js`.
- [ ] **Step 3: Manual check** — `python -m http.server 8090 --directory web`; page renders top bar + empty ledger + dark map area, no console errors except modules not yet wired.
- [ ] **Step 4: Commit** `git add web/styles.css web/index.html && git commit -m "feat(web2): light color=decision design system + shell"`

---

## Task 4: Map + profile + belt (`locality-map.js`)

**Files:** Create `web/locality-map.js`.

**Interfaces:** exports `initMap()`, `showProfile(props)`, `setMapFilter(expr)`, `highlightBelt(beltId)`; reads `window.LOCALITIES`, `window.BELTS`, fetches `darkstores.json`.

- [ ] **Step 1: Implement** — MapLibre map (dark tiles, India center `[78.9629,20.5937]` zoom 4.5). On load: add `darkstores` source (3 brand circle layers, small, low-opacity) from `darkstores.json`; add `localities` GeoJSON source from `window.LOCALITIES` (features with all props + `[lng,lat]`); layer `locality-circles` paint `circle-color ['get','color']`, `circle-radius` interpolate by `['get','icp_score']` (0→4,100→11), white 1px stroke. Click → `showProfile(props)` (renders the §6 panel HTML into `#profile`, light theme, mono labels via `.k`, `gtm-status` word colored by `colorFor`, gem pills only if true, `·est` chip if `price_is_imputed`). `setMapFilter(expr)` → `map.setFilter('locality-circles', expr)`. `highlightBelt(id)` → filter to `belt_id==id`, fitBounds to members. Hover pointer.
- [ ] **Step 2: Manual verify** — reload; colored locality dots over darkstores; click → light profile panel with real fields; no errors.
- [ ] **Step 3: Commit** `git add web/locality-map.js && git commit -m "feat(web2): locality map layer + light profile panel + belt highlight"`

---

## Task 5: Orchestrator + ledger + views (`app.js`, `views.js`)

**Files:** Create `web/app.js`, `web/views.js`.

- [ ] **Step 1: `views.js`** — exports `renderLeaderboard()`, `renderGems()`, `renderMethodology()`. Leaderboard: top 60 by `icp_score`, table (AREA, city, ICP mono, verdict badge, serviceability, archetype, gtm label, brands `n/3`). Gems: 3 tables (pareto_optimal / hidden_gem_v2 / spillover_gem) with ICP + price. Methodology: the serviceable-pipeline explanation + GTM matrix + honesty caveats (verbatim from Global Constraints), + the geocode note (886/1001 mapped).
- [ ] **Step 2: `app.js`** — on DOMContentLoaded: import `initMap, showProfile, setMapFilter, highlightBelt` from `locality-map.js`, `buildFilter` from `filters.js`, `colorFor,labelFor,GTM_ACTIONS` from `contract.js`, `renderLeaderboard,renderGems,renderMethodology` from `views.js`, `initMargin` from `margin.js`. Build the **Decision Ledger** from `GTM_ACTIONS` with live counts from `window.LOCALITIES` (dot color `colorFor`, count mono); clicking a row toggles it in an `activeGtm` Set and re-applies `setMapFilter(buildFilter({...selects, gtm:activeGtm}))` + updates a stats line. Wire the 3 filter selects + belt-select likewise. Tab switching shows/hides views and lazily renders each once; `map.resize()` on returning to map. Call `initMap()`, `initMargin()`, `renderMethodology()`.
- [ ] **Step 3: Manual verify** — all tabs work; ledger counts correct (Push 97 / Sample 450 / D2C 17 / Hold 378…); clicking ledger filters the map; selects filter; belt-select highlights+zooms; leaderboard/gems/margin/methodology render.
- [ ] **Step 4: Commit** `git add web/app.js web/views.js && git commit -m "feat(web2): orchestrator, Decision Ledger, leaderboard/gems/methodology"`

---

## Task 6: Cleanup + end-to-end verify

**Files:** Delete `web/data-summary.js`, `web/data-markers.json`, `web/map.js`, `web/charts.js`, `web/scoreDisplay.js` (v1 leftovers superseded). Keep `margin.js`, `state.js` if used.

- [ ] **Step 1:** Remove the retired v1 files; confirm nothing imports them (grep).
- [ ] **Step 2: Full test suite** — `cd scripts && python -m pytest test_build_locality_data.py -q` and `node --test web/tests/frontend.test.js`. All pass.
- [ ] **Step 3: Headless smoke** — serve `web/`, load in Chrome DevTools, screenshot the map (colored dots + ledger), click a locality (panel), check console = no errors.
- [ ] **Step 4: Commit** `git add -A && git commit -m "chore(web2): retire v1 data/files; end-to-end verified"`

---

## Self-Review

- **Spec coverage:** repoint+data (T1) · contract/filters (T2) · design system+shell (T3) · map/profile/belt (T4) · ledger/leaderboard/gems/methodology + drop-gyms (T5) · retire v1 + verify (T6). Margin kept (T3/T5). Darkstore layer kept (T4). Honesty caveats (T5). ✔
- **Placeholders:** testable code is complete; frontend tasks specify exact DOM ids, layer paint, panel fields, and token values — assembled inline this session with full spec context.
- **Type consistency:** `colorFor/labelFor` (contract.js) and `buildFilter` (filters.js) signatures match their tests and their `app.js`/`locality-map.js` callers; `window.LOCALITIES` shape == `build_locality_data.py` COLS + `color`.
