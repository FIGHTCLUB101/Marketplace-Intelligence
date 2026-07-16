# Locality Coverage Ring + Per-Brand Distance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** When a user clicks a locality on the Map view, show a dashed coverage ring (colored by serviceability confidence) around it and a per-brand nearest-darkstore-distance breakdown in the profile panel — both built from data GOAT Life's pipeline already computes but never surfaced.

**Architecture:** One Python data-pipeline change exposes three already-computed columns to the frontend. One new pure geometry function (`circlePolygon`) builds a 32-sided polygon approximating a geodesic circle, rendered via a new MapLibre GeoJSON source/layer. `showProfile()` gains a new panel section and sets/clears the ring; a new exported `hideProfile()` replaces the panel's inline close handler so it can clear both the panel and the ring in one place.

**Tech Stack:** Python (pandas) for the data layer, vanilla JS + MapLibre GL JS for the frontend — no build step, no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-locality-coverage-ring-design.md` — read it if anything below is ambiguous.
- Scope is the existing 1,001 curated localities only — no click-anywhere-on-the-map probe, no always-on per-darkstore coverage wash, no branded darkstore logos. All three are explicitly out of scope per the spec.
- Ring radius and per-brand distance display cutoff are both exactly `3.5` km — they must stay in sync (a locality could have `nearest_zepto_km: 9.89` in the data; that must display as `—`, not `9.89 km`, since it's outside the ring the user sees).
- Ring colors are exact hardcoded hex values matching existing CSS tokens (not derived from CSS at runtime): `Confirmed` → `#059669`, `Likely` → `#d97706`, `Unknown` → `#6B6B66`. This mirrors `contract.js`'s existing, documented precedent for hardcoding hex values that intentionally match `styles.css` tokens.
- `pipeline/darkstores.py` and `pipeline/build.py` are confirmed unused by the current data flow (`web/app.js` reads `window.LOCALITIES` from `web/data-localities.js`, not `window.GOAT_DATA` from `web/data-summary.js`) — do not touch them.

---

### Task 1: Data pipeline — expose per-brand nearest distance

**Files:**
- Modify: `scripts/build_locality_data.py`

**Interfaces:**
- Produces: three new fields on every record in `window.LOCALITIES` — `nearest_blinkit_km`, `nearest_zepto_km`, `nearest_swiggy_km` (float or `""` if null, matching the existing `nearest_known_darkstore_km` null-as-empty-string convention already used by this script's `geo.fillna("")` step). Consumed by Task 3.

- [x] **Step 1: Add the three columns to the field allowlist**

In `scripts/build_locality_data.py`, change:
```python
COLS = ["AREA", "ADDRESS", "PINCODE", "lat", "lng", "icp_score", "icp_verdict", "gtm_action",
        "serviceability_state", "serviceability_confidence", "archetype_ml", "lifecycle",
        "n_brands_confirmed", "brands_confirmed_list", "nearest_known_darkstore_km",
        "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed",
        "res_avg_buy_imputed", "price_is_imputed", "employer_quality", "primary_sector",
        "is_metro_connected", "belt_id", "belt_size", "pareto_optimal", "hidden_gem_v2", "spillover_gem",
        # competitive overlay (added by scripts/enrich_competitor_data.py — optional columns)
        "blinkit_n_competitor_brands", "blinkit_competitor_avg_price", "blinkit_goat_present",
        "zepto_n_competitor_brands", "zepto_competitor_avg_price", "zepto_goat_present",
        "price_advantage_blinkit", "is_white_space"]
```
to:
```python
COLS = ["AREA", "ADDRESS", "PINCODE", "lat", "lng", "icp_score", "icp_verdict", "gtm_action",
        "serviceability_state", "serviceability_confidence", "archetype_ml", "lifecycle",
        "n_brands_confirmed", "brands_confirmed_list", "nearest_known_darkstore_km",
        "nearest_blinkit_km", "nearest_zepto_km", "nearest_swiggy_km",
        "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed",
        "res_avg_buy_imputed", "price_is_imputed", "employer_quality", "primary_sector",
        "is_metro_connected", "belt_id", "belt_size", "pareto_optimal", "hidden_gem_v2", "spillover_gem",
        # competitive overlay (added by scripts/enrich_competitor_data.py — optional columns)
        "blinkit_n_competitor_brands", "blinkit_competitor_avg_price", "blinkit_goat_present",
        "zepto_n_competitor_brands", "zepto_competitor_avg_price", "zepto_goat_present",
        "price_advantage_blinkit", "is_white_space"]
```

- [x] **Step 2: Round the three new numeric columns**

In `scripts/build_locality_data.py`, change:
```python
for c in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km", "employer_quality",
          "blinkit_competitor_avg_price", "zepto_competitor_avg_price", "price_advantage_blinkit"]:
    if c in geo.columns:
        geo[c] = geo[c].round(1)
```
to:
```python
for c in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km",
          "nearest_blinkit_km", "nearest_zepto_km", "nearest_swiggy_km", "employer_quality",
          "blinkit_competitor_avg_price", "zepto_competitor_avg_price", "price_advantage_blinkit"]:
    if c in geo.columns:
        geo[c] = geo[c].round(1)
```

- [x] **Step 3: Regenerate the data file and verify**

Run: `cd scripts && python build_locality_data.py`
Expected: prints `localities (geocoded): 1001 | belts(>=3): <N>` (same locality count as before this change — this script only adds fields to existing records, it doesn't change which rows are kept). Then verify the new fields landed:

```bash
cd scripts && python -c "
import json
text = open('../web/data-localities.js', encoding='utf-8').read()
records = json.loads(text.split('window.LOCALITIES = ', 1)[1].rstrip(';\n'))
sample = [r for r in records if r.get('nearest_blinkit_km') not in (None, '')][:3]
print(len(sample), 'sample records with nearest_blinkit_km:')
for r in sample:
    print(r['AREA'], r.get('nearest_blinkit_km'), r.get('nearest_zepto_km'), r.get('nearest_swiggy_km'))
"
```
Expected: prints 3 sample records with non-empty `nearest_blinkit_km` values, confirming the new fields are present and populated in the regenerated `web/data-localities.js`.

- [x] **Step 4: Run the existing contract test to confirm nothing broke**

Run: `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v`
Expected: PASS (this test checks `contract.js`/`contract.py` GTM color/label parity, unrelated to the fields added here — it should be unaffected, and passing confirms the script still runs cleanly end-to-end).

- [x] **Step 5: Commit**

```bash
git add scripts/build_locality_data.py web/data-localities.js
git commit -m "feat: expose per-brand nearest-darkstore distance to the frontend

nearest_blinkit_km / nearest_zepto_km / nearest_swiggy_km were already
computed in the master parquet by notebooks/08_darkstore_serviceability.ipynb
but never reached window.LOCALITIES. Needed for the upcoming per-brand
distance breakdown in the locality profile panel."
```

---

### Task 2: `locality-map.js` — Node-import guard fix + `circlePolygon()` pure function

**Files:**
- Modify: `web/locality-map.js`
- Test: `web/tests/locality-map.test.js` (new)

**Interfaces:**
- Produces: `circlePolygon(lat, lng, radiusKm, color, points = 32) -> GeoJSON Feature<Polygon>` (pure, exported, tested). Consumed by Task 3.

- [x] **Step 1: Fix the Node-import guard (prerequisite for testing this file at all)**

`web/locality-map.js` currently throws `ReferenceError: window is not defined` when imported outside a browser, because line 3 reads `window.LOCALITIES` unguarded. `web/sequence.js` already solves this with a guarded pattern — apply the same fix here so this file's pure functions can be unit-tested.

In `web/locality-map.js`, change:
```js
const L = window.LOCALITIES || [];
```
to:
```js
const L = (typeof window !== 'undefined' && window.LOCALITIES) || [];
```

- [x] **Step 2: Write the failing tests for `circlePolygon`**

Create `web/tests/locality-map.test.js`:
```js
import { test } from 'node:test';
import assert from 'node:assert';
import { circlePolygon } from '../locality-map.js';

test('circlePolygon: returns a closed Polygon feature with the given color', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669');
  assert.strictEqual(f.type, 'Feature');
  assert.strictEqual(f.geometry.type, 'Polygon');
  assert.strictEqual(f.properties.color, '#059669');
});

test('circlePolygon: ring has points+1 coordinates and is closed', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669', 32);
  const ring = f.geometry.coordinates[0];
  assert.strictEqual(ring.length, 33);
  assert.deepStrictEqual(ring[0], ring[ring.length - 1]);
});

test('circlePolygon: respects a custom points count', () => {
  const f = circlePolygon(12.9716, 77.5946, 3.5, '#059669', 8);
  assert.strictEqual(f.geometry.coordinates[0].length, 9);
});
```

- [x] **Step 3: Run tests to verify they fail**

Run: `node --test web/tests/locality-map.test.js`
Expected: FAIL — `circlePolygon is not a function` (or similar export-not-found error).

- [x] **Step 4: Implement `circlePolygon`**

In `web/locality-map.js`, add this function after `fc()` (around line 17-18), before `export function setLocalityData`:
```js
// Builds a `points`-sided polygon approximating a geodesic circle of radiusKm around [lat,lng].
// Ported from a reference darkstore-mapping project's makeGeoJSONCircle — same 111.32/110.574
// km-per-degree approximation, adequate at the ~3.5km radii this is used for.
function circlePolygon(lat, lng, radiusKm, color, points = 32) {
  const coords = [];
  const distanceX = radiusKm / (111.32 * Math.cos(lat * Math.PI / 180));
  const distanceY = radiusKm / 110.574;
  for (let i = 0; i < points; i++) {
    const theta = (i / points) * (2 * Math.PI);
    coords.push([lng + distanceX * Math.cos(theta), lat + distanceY * Math.sin(theta)]);
  }
  coords.push(coords[0]);
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: { color },
  };
}
```
Then export it by changing:
```js
export function setLocalityData(records) {
```
to (adding the export one line above it):
```js
export { circlePolygon };

export function setLocalityData(records) {
```

- [x] **Step 5: Run tests to verify they pass**

Run: `node --test web/tests/locality-map.test.js`
Expected: PASS (3/3).

- [x] **Step 6: Run the full frontend suite to confirm the guard fix didn't break anything**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/shelf-monitor.test.js web/tests/sortable-table.test.js web/tests/locality-map.test.js`
Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add web/locality-map.js web/tests/locality-map.test.js
git commit -m "feat: add circlePolygon geodesic-ring helper, fix Node-import guard

locality-map.js threw on import outside a browser (window.LOCALITIES
read unguarded), matching an issue sequence.js already solved — applied
the same typeof-guard so this file's pure functions can be unit-tested."
```

---

### Task 3: `locality-map.js` — wire the ring and per-brand distance into the map and profile panel

**Files:**
- Modify: `web/locality-map.js`

**Interfaces:**
- Consumes: `circlePolygon(lat, lng, radiusKm, color, points)` (Task 2, same file). `nearest_blinkit_km`/`nearest_zepto_km`/`nearest_swiggy_km` fields on locality records (Task 1).
- Produces: `hideProfile()` (exported) — later referenced by the panel's close button via `window.__hideLocalityProfile`.

- [x] **Step 1: Add the ring color map and radius constant**

In `web/locality-map.js`, add near the top of the file, after the `truthy` helper (around line 6):
```js
const RING_COLOR = { Confirmed: '#059669', Likely: '#d97706', Unknown: '#6B6B66' };
const RING_RADIUS_KM = 3.5;
```

- [x] **Step 2: Add the coverage-ring source and layer**

In `web/locality-map.js`, inside `initMap()`'s `map.on('load', ...)` handler, add this immediately after the `locality-circles` layer's `map.addLayer({...})` call (after the block ending at the line before `map.on('click', 'clusters', ...)`):
```js
    map.addSource('coverage-ring', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: 'coverage-ring-line', type: 'line', source: 'coverage-ring',
      paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-dasharray': [4, 3], 'line-opacity': 0.85 },
    });
```

- [x] **Step 3: Add `hideProfile()` and wire the window bridge**

In `web/locality-map.js`, replace:
```js
export function showProfile(p) {
```
with:
```js
export function hideProfile() {
  document.getElementById('profile').classList.remove('open');
  const src = map && map.getSource('coverage-ring');
  if (src) src.setData({ type: 'FeatureCollection', features: [] });
}
window.__hideLocalityProfile = hideProfile;

export function showProfile(p) {
```

- [x] **Step 4: Change the panel's close button to use the new handler**

In `web/locality-map.js`, inside `showProfile()`'s template, change:
```js
      <button class="p-x" onclick="document.getElementById('profile').classList.remove('open')">×</button>
```
to:
```js
      <button class="p-x" onclick="window.__hideLocalityProfile()">×</button>
```

- [x] **Step 5: Add the "Nearest by brand" section**

In `web/locality-map.js`, inside `showProfile()`, change:
```js
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const blComp = num(p.blinkit_n_competitor_brands);
```
to:
```js
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const brandDistRow = (label, km) =>
    row(label, (km != null && km <= RING_RADIUS_KM) ? km + ' km' : '—', true);
  const brandSection = `
    <div class="p-sep"></div>
    <div class="p-section-head">Nearest by brand</div>
    <div class="p-grid">
      ${brandDistRow('Blinkit', num(p.nearest_blinkit_km))}
      ${brandDistRow('Zepto', num(p.nearest_zepto_km))}
      ${brandDistRow('Swiggy Instamart', num(p.nearest_swiggy_km))}
    </div>`;
  const blComp = num(p.blinkit_n_competitor_brands);
```
Then change:
```js
    ${compSection}
    <div class="pills">
```
to:
```js
    ${brandSection}
    ${compSection}
    <div class="pills">
```

- [x] **Step 6: Set the ring's data when a locality is selected**

In `web/locality-map.js`, inside `showProfile()`, change:
```js
  panel.classList.add('open');
  if (map && p.lat) map.easeTo({ center: [+p.lng, +p.lat], zoom: 11, duration: 600 });
}
```
to:
```js
  panel.classList.add('open');
  if (map && p.lat) {
    map.easeTo({ center: [+p.lng, +p.lat], zoom: 11, duration: 600 });
    const ring = circlePolygon(+p.lat, +p.lng, RING_RADIUS_KM, RING_COLOR[p.serviceability_state] || RING_COLOR.Unknown);
    map.getSource('coverage-ring').setData({ type: 'FeatureCollection', features: [ring] });
  }
}
```

- [x] **Step 7: Visually verify**

Using a local dev server (with `web/data-localities.js` regenerated from Task 1), open the Map view. Click a `Confirmed` locality (most localities — 792 of 1001) and confirm: the existing profile panel opens as before, a new "Nearest by brand" section appears between the main grid and "Competitive position" showing Blinkit/Zepto/Swiggy Instamart distances (or `—`), and a dashed green ring appears around the clicked locality on the map. Click a different locality while one is selected and confirm the ring moves to the new one rather than leaving two rings. Find and click a `Likely` locality (19 exist) and confirm an amber ring; find an `Unknown` locality (190 exist) and confirm a gray ring. Click the panel's `×` button and confirm both the panel and the ring disappear. Repeat the full check in dark mode.

- [x] **Step 8: Commit**

```bash
git add web/locality-map.js
git commit -m "feat: show a serviceability-colored coverage ring and per-brand distance when a locality is selected"
```

---

### Task 4: Full regression pass

**Files:** none (verification only)

- [x] **Step 1: Run the full test suite**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/shelf-monitor.test.js web/tests/sortable-table.test.js web/tests/locality-map.test.js`
Expected: all pass.
Run: `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v`
Expected: PASS.

- [x] **Step 2: Manual end-to-end walkthrough, light and dark**

With a local dev server: click through several localities of each `serviceability_state` (Confirmed/Likely/Unknown) confirming ring color and per-brand distances are consistent with what the profile panel already shows for "Serviceability" and "Nearest store"; use the Map view's existing filters (city/verdict/serviceability, belt selector) to confirm they still work and that selecting a filtered-out locality's ring behaves sensibly (it shouldn't be selectable if filtered out — confirm no dangling ring appears for a hidden locality); click through every other view (Leaderboard, Untapped Markets, Launch Roadmap, Margin Calculator, Shelf Monitor, Method) to confirm no regression and no console errors from the Task 1-3 changes. Repeat the whole pass in dark mode.

- [x] **Step 3: Commit (only if fixes were needed)**

If the walkthrough surfaced any bugs, fix them, re-run the affected step, then:
```bash
git add -A
git commit -m "fix: address issues found in locality-coverage-ring regression pass"
```
If no fixes were needed, skip this step — nothing to commit.
