# Locality Coverage Ring + Per-Brand Distance

## Why

Sparked by studying two reference quick-commerce mapping projects (`darkstores.vercel.app` and a
locally-built "darkstore version 1" analytics dashboard — the latter runs on MapLibre GL JS, the
same engine GOAT Life already uses). The second project's "click anywhere, see a coverage radius
and per-brand distance breakdown" pattern doesn't need porting wholesale — GOAT Life's own pipeline
already computes almost the same thing offline, it just never reached the frontend.

Verified before designing (not assumed):
- `pipeline/darkstores.py` computes `nearest_by_brand` per locality via a spatial grid + haversine
  distance, but this module is legacy/unused by the current data flow (writes to `web/data-summary.js`
  / `window.GOAT_DATA`, which nothing in `web/app.js` reads).
- The actual live pipeline is `notebooks/08_darkstore_serviceability.ipynb` → 
  `notebooks/artifacts/localities_master_serviceable.parquet` → `scripts/build_locality_data.py` →
  `web/data-localities.js` → `window.LOCALITIES`. The notebook already computes per-brand distance
  as three flat scalar columns — `nearest_blinkit_km`, `nearest_zepto_km`, `nearest_swiggy_km` —
  confirmed present in the current parquet with real values (819/808/787 non-null out of 1001 rows).
  `scripts/build_locality_data.py`'s `COLS` allowlist simply never includes them.
- `serviceability_state` has exactly three values in the current data: `Confirmed` (792), `Unknown`
  (190), `Likely` (19).
- The existing profile panel (`locality-map.js`'s `showProfile()`) already shows a single combined
  "Nearest store" distance and a "Competitive position" section (Blinkit-only competitor pricing) —
  it has no per-brand distance breakdown and no visual radius indicator.
- `contract.js` already establishes the precedent for hardcoding a small set of hex values in JS
  that intentionally match (not derive from) the CSS custom properties in `styles.css`, documented
  inline as necessary because some consumers of that file have no CSS access. This sub-project's
  ring-color mapping follows the same pattern.

## Decisions locked in during design

- **Scope: enhance the existing 1,001 curated localities only — no click-anywhere-on-the-map probe.**
  The reference tool computes live because it has no precomputed layer; GOAT Life already has one.
  Building a second, live-computed path for arbitrary points is a larger, separately-scoped idea
  (no ICP/serviceability score would exist for such a point anyway) — not part of this sub-project.
- **One ring only, tied to the selected locality — no always-on per-darkstore coverage wash.** The
  reference tool's translucent overlapping circles around every darkstore answer "how saturated is
  this whole city," a different question than "how well is this one locality served," and add real
  visual-tuning surface (opacity, zoom cutoff, toggle UI) this sub-project doesn't need.
- **Per-brand distance is included, not deferred.** The data already exists in the parquet; this is
  a small, low-risk pairing with the ring (the ring visualizes the 3.5km radius, the per-brand rows
  show which brands are actually inside it).
- **Branded darkstore logos (Blinkit/Zepto/Swiggy icons replacing the current faint dots) are
  explicitly out of scope**, deferred to a future sub-project. It's a different visual-hierarchy
  decision (4,081 darkstore markers vs. 1,001 localities, at what zoom, MapLibre needs actual image
  assets via `map.addImage()`) that deserves its own brainstorm.
- **Ring color reflects `serviceability_state`, not a fixed neutral color.** Reuses the existing
  status-token hex values already established across the dashboard (sub-projects 1-4): `Confirmed`
  → `--status-success` (`#059669`), `Likely` → `--status-warning` (`#d97706`), `Unknown` →
  `--status-neutral` (`#6B6B66`). The ring communicates confidence, not just "here's 3.5km."
- **Per-brand distance display is capped at 3.5km, independent of whatever scan radius the notebook
  used to compute the raw nearest-distance value.** A locality's `nearest_zepto_km` could be `9.89`
  (far outside real coverage) — displaying that number next to a 3.5km ring would visually contradict
  the ring. Anything beyond 3.5km (or `null`/`NaN`) displays as `—`, matching the existing
  `nearest_known_darkstore_km` null-display convention already used elsewhere in `views.js`.
- **The circle-polygon math is a pure, testable function** (ported from the reference project's
  `makeGeoJSONCircle`), consistent with this repo's established pattern of extracting the one
  genuinely-new pure logic piece for unit test coverage while leaving DOM/map wiring untested.

## Data pipeline

`scripts/build_locality_data.py`: add `nearest_blinkit_km`, `nearest_zepto_km`, `nearest_swiggy_km`
to the `COLS` allowlist (they already exist in the parquet — this is additive, no notebook changes
needed) and to the existing `.round(1)` numeric-rounding loop, alongside `nearest_known_darkstore_km`:

```python
COLS = ["AREA", "ADDRESS", "PINCODE", "lat", "lng", "icp_score", "icp_verdict", "gtm_action",
        "serviceability_state", "serviceability_confidence", "archetype_ml", "lifecycle",
        "n_brands_confirmed", "brands_confirmed_list", "nearest_known_darkstore_km",
        "nearest_blinkit_km", "nearest_zepto_km", "nearest_swiggy_km",
        "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed",
        ...]
...
for c in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km",
          "nearest_blinkit_km", "nearest_zepto_km", "nearest_swiggy_km", "employer_quality",
          "blinkit_competitor_avg_price", "zepto_competitor_avg_price", "price_advantage_blinkit"]:
```

`scripts/test_build_locality_data.py`'s existing contract-parity test is unaffected (it checks
`contract.js` against `contract.py`'s GTM color/label maps, not the locality field list) — no test
changes needed there, but the new fields should be spot-checked present in a regenerated
`web/data-localities.js` as part of this task's verification.

## Profile panel: per-brand distance

`web/locality-map.js`'s `showProfile()` gains a new section, using the same `row()`/`p-grid`/
`p-section-head`/`p-sep` pattern the existing "Competitive position" section already uses, placed
right after the main `p-grid` and before `compSection`:

```js
const DISPLAY_RADIUS_KM = 3.5;
const brandDistRow = (label, km) =>
  row(label, (km != null && km <= DISPLAY_RADIUS_KM) ? km + ' km' : '—', true);

const brandSection = `
  <div class="p-sep"></div>
  <div class="p-section-head">Nearest by brand</div>
  <div class="p-grid">
    ${brandDistRow('Blinkit', num(p.nearest_blinkit_km))}
    ${brandDistRow('Zepto', num(p.nearest_zepto_km))}
    ${brandDistRow('Swiggy Instamart', num(p.nearest_swiggy_km))}
  </div>`;
```

(`num()` is the existing `(v) => (v !== '' && v != null) ? +v : null` helper already defined in this
function.) `brandSection` is inserted into the panel's template between the closing `</div>` of the
main `p-grid` and `${compSection}`.

## Coverage ring

New pure function in `locality-map.js` (ported from the reference project's `makeGeoJSONCircle`,
adapted to this file's naming conventions):

```js
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

const RING_COLOR = { Confirmed: '#059669', Likely: '#d97706', Unknown: '#6B6B66' };
const RING_RADIUS_KM = 3.5;
```

Source + layer added once in `initMap()`'s `map.on('load', ...)` handler, alongside the existing
`localities`/`darkstores` sources:

```js
map.addSource('coverage-ring', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
map.addLayer({
  id: 'coverage-ring-line', type: 'line', source: 'coverage-ring',
  paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-dasharray': [4, 3], 'line-opacity': 0.85 },
});
```

`showProfile(p)` sets the ring's data when a locality is selected:

```js
if (map && p.lat) {
  const ring = circlePolygon(+p.lat, +p.lng, RING_RADIUS_KM, RING_COLOR[p.serviceability_state] || RING_COLOR.Unknown);
  map.getSource('coverage-ring').setData({ type: 'FeatureCollection', features: [ring] });
}
```

The panel's close button currently has an inline `onclick="document.getElementById('profile').classList.remove('open')"`.
It becomes a call to a small exported function that clears both the panel and the ring:

```js
export function hideProfile() {
  document.getElementById('profile').classList.remove('open');
  const src = map && map.getSource('coverage-ring');
  if (src) src.setData({ type: 'FeatureCollection', features: [] });
}
```
```html
<button class="p-x" onclick="window.__hideLocalityProfile()">×</button>
```
with `window.__hideLocalityProfile = hideProfile;` set once near the top of `locality-map.js` (the
existing inline-onclick pattern already reaches into global scope this way — this keeps that
convention rather than introducing event delegation for one button).

## Testing

- `circlePolygon()` is a pure function (lat/lng/radius/color in, GeoJSON Feature out) — new unit
  tests cover: correct `Polygon` geometry type, exactly `points + 1` coordinates (closed ring),
  first and last coordinate identical (closure), and that `properties.color` passes through
  unchanged.
- No test needed for `RING_COLOR`'s mapping table itself (a static lookup, not logic) or for the
  MapLibre source/layer wiring (DOM/map-coupled, consistent with this file's existing convention of
  leaving `initMap()`/`showProfile()` untested).
- `brandDistRow`'s 3.5km cutoff logic is simple enough to fold into the existing untested
  `showProfile()` — matching how `goatPart`/`pricePart` in `views.js` (similar small display-format
  helpers) are not separately unit-tested today.
- Manual verification: click a `Confirmed` locality, confirm a solid-feeling dashed green ring
  appears around it and per-brand distances show real km values or `—`; click a `Likely` locality,
  confirm an amber ring; click an `Unknown` locality, confirm a gray ring; click a locality with
  `nearest_zepto_km > 3.5` (or `null`), confirm that row shows `—` even though the raw value exists;
  click a different locality while one is already selected, confirm the ring moves (not duplicates);
  close the panel via the × button, confirm the ring disappears; repeat in dark mode.

## Explicitly out of scope

- Click-anywhere-on-the-map live inspector for points outside the curated 1,001 localities.
- Always-on coverage circles around every darkstore (the "saturation wash" visualization).
- Branded logo icons for darkstore markers (Blinkit/Zepto/Swiggy) — separate future sub-project.
- Any change to the existing "Competitive position" (Blinkit-specific competitor pricing) section.
- Any change to `pipeline/darkstores.py` or `pipeline/build.py` — confirmed unused by the current
  data flow; not touched by this sub-project.
