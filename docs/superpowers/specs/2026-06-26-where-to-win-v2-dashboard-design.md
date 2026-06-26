# Where to Win v2 — Dashboard Design Spec
**2026-06-26 · Consumer-layer Product 2**

> Repoint the existing `web/` MapLibre app onto the **1,001-locality serviceable master store** as one
> coherent internal decision tool: localities colored by go-to-market action over the darkstore supply layer,
> a light/minimal locality profile panel, belt view, filters, leaderboard, gems, and methodology. The data
> contract is single-source (`localities_master_serviceable.parquet` → `contract.py`/`contract.js`).

---

## 1. Purpose & success criteria

GOAT Life's growth team needs to look at a map and decide **where to push, sample, or hold** — grounded in
demand (ICP) *and* quick-commerce reach (serviceability). v1 answers an older question on stale 600-locality
data with a different score. v2 makes the **serviceable store** the single truth across the whole app.

**Success =**
1. Every view speaks one language: `icp_score` / `icp_verdict` / `serviceability_state` / `gtm_action`.
2. The map renders the 886 geocoded localities colored by `gtm_action` over the 4,081 darkstores; clicking one
   opens a clean, light profile panel; belts highlight; filters narrow the set live.
3. No stale data: re-running NB08 → `build_locality_data.py` regenerates every frontend bundle (the refresh path).
4. The UI reads as a precise, professional instrument — **the only saturated color on the page is GTM status.**

**This is the dashboard product only.** Product 1 (pincode export) is done; Product 3 (attack-sequence engine)
is a later build that may reuse this app's data bundle.

---

## 2. Scope decision (what changes, what's dropped)

**Repoint the whole app** to the serviceable store (chosen over bolt-on-tab / fresh-rewrite). v1's scaffold
(MapLibre setup, tab system, sync-load pattern, margin calculator) is **evolved, not rewritten.**

| v1 tab / asset | v2 |
|---|---|
| Map | ✅ Rebuilt — localities by `gtm_action` over darkstores; profile panel; belt view; filters; Decision Ledger |
| Leaderboard | ✅ Repointed — ranked by `icp_score`, with verdict / serviceability / archetype / gtm columns |
| Whitespace | ➡️ Becomes **Gems** — `pareto_optimal` / `hidden_gem_v2` / `spillover_gem` |
| Gyms | ❌ Dropped — no gym data in the serviceable store |
| Margin | ✅ Kept verbatim (`margin.js`, GOAT economics, data-independent) |
| Methodology | ✅ Rewritten for the serviceable pipeline + honesty caveats |
| `data-summary.js` (600-locality), `data-markers.json` (old gyms/stores) | ❌ Retired; replaced by `data-localities.js` / `data-belts.js` |
| `darkstores.json` (4,081) | ✅ Kept — the supply layer |

Reliance-store and gym markers are dropped (not in the new store). v2 map = **localities (demand) + darkstores (supply).**

---

## 3. Architecture & files

```
scripts/build_locality_data.py   NEW  — master parquet -> web/data-localities.js + web/data-belts.js (imports contract.py)
web/contract.js                  NEW  — JS mirror of contract.py: GTM_ACTIONS, GTM_COLORS, GTM_LABELS (frontend single truth)
web/data-localities.js           GEN  — `window.LOCALITIES = [...]` (886 geocoded rows, frontend cols + color), sync-loaded
web/data-belts.js                GEN  — `window.BELTS = [...]` (belt summaries, size>=3)
web/locality-map.js              NEW  — locality layer, profile panel, belt highlight, filter expr, Decision Ledger wiring
web/charts.js                    MOD  — leaderboard + gems tables on LOCALITIES
web/app.js                       MOD  — tab wiring (drop gyms), Decision Ledger counts, filter events
web/index.html                   MOD  — IBM Plex fonts, Decision Ledger rail, filter bar, profile panel container, legend
web/styles.css                   MOD  — light "color = decision" design system (replaces dark tokens)
web/methodology.js               MOD  — rewrite for serviceable pipeline
web/margin.js                    KEEP — unchanged
web/state.js                     KEEP/MOD — AppState slots
web/tests/*.test.js              NEW/MOD — contract resolution + filter-builder unit tests
```

`build_locality_data.py` and `contract.js` are the contract spine: `contract.py` stays the source of truth; the
build script and `contract.js` derive from it (a unit test asserts `contract.js` colors equal `contract.py`).

---

## 4. Data layer

`scripts/build_locality_data.py`:
1. Reads `localities_master_serviceable.parquet`; **asserts** `set(gtm_action) == contract.GTM_ACTIONS` (drift guard).
2. Selects frontend columns: `AREA, ADDRESS, PINCODE, lat, lng, icp_score, icp_verdict, gtm_action,
   serviceability_state, serviceability_confidence, archetype_ml, lifecycle, n_brands_confirmed,
   brands_confirmed_list, nearest_known_darkstore_km, blinkit_confirmed, swiggy_confirmed, zepto_confirmed,
   res_avg_buy_imputed, price_is_imputed, employer_quality, primary_sector, is_metro_connected,
   belt_id, belt_size, pareto_optimal, hidden_gem_v2, spillover_gem`.
3. Keeps only the **886 geocoded** rows (`lat` not null) — no-geo localities are honestly excluded from the map.
4. Attaches `color = contract.GTM_COLORS[gtm_action]`; rounds floats; writes `window.LOCALITIES = [...]` to
   `web/data-localities.js` (~300 KB, sync) and a belts summary (`belt_id, ADDRESS, size, avg_icp, go_count,
   confirmed_count, member AREAs`, `size>=3`) to `web/data-belts.js`.

Sync `<script>` load (no fetch) — instant render, matching v1's `data-summary.js` pattern. `darkstores.json` loads
lazily as before.

---

## 5. Visual design system ("color = decision")

**Principle:** the only saturated color on the page is GTM status. Chrome is neutral; GOAT gold is brand/active only.

**Color tokens:**
`--paper #FAFAF7` (warm near-white canvas) · `--surface #FFFFFF` · `--ink #1A1A1A` · `--muted #6B6B66` ·
`--line #E6E4DD` (hairlines) · `--goat #E8A317` (brand mark + active nav ONLY).
**Status colors come from `contract.js`** (unchanged): PUSH-NOW `#059669`, SAMPLE+QC `#d97706`,
SAMPLE-offline `#EF9F27`, D2C-verify `#2a78d6`, HOLD `#888780`.

**Type:** **IBM Plex Sans** (UI + headings) + **IBM Plex Mono** (all numbers/codes + uppercase tracked
micro-labels). Mono-for-data signals a precise instrument. Loaded from Google Fonts.

**Signature — the Decision Ledger:** a left rail that is legend + live count + filter in one. The GTM actions
listed vertically with their counts, in status colors; clicking one filters the map to that action. No 01/02/03
numbering (the actions aren't a sequence). It is the page's one memorable, content-true device; everything else
stays quiet.

**Discipline:** no gradients, no heavy cards, one soft edge-shadow on the profile panel only, hairline dividers,
generous whitespace. Quality floor: responsive to mobile, visible keyboard focus, `prefers-reduced-motion` respected.

---

## 6. Map view (hero)

MapLibre dark-tile map (the map itself stays dark — it's the working surface; the *chrome* around it is light).
- **Darkstore layer** (under): 3 brand circle layers from `darkstores.json` with toggles (existing).
- **Locality layer** (over): circles colored by `['get','color']` (the baked GTM color), radius interpolated by
  `icp_score`, hairline stroke. Click → profile panel; hover → pointer.
- **Profile panel** (right, light/minimal per §5): area; `city · PIN` (mono); the **`gtm_action` as a large mono
  status word** in its color; `ICP <score>` + `Serviceability <state> · <confidence>`; a 2-col data grid (verdict,
  archetype, lifecycle, brands `n/3 · list`, nearest km, price `₹/sqft` + `·est` chip when imputed, employer
  quality, metro); gem pills (`pareto_optimal` / `hidden_gem_v2` / `spillover_gem`) only when present. Close button.
- **Belt view:** a control listing belts (from `BELTS`); selecting one highlights member localities (a brighter
  stroke / dim others via filter) and `fitBounds` to the belt extent.
- **Filters:** city / verdict / serviceability / lifecycle → a `setFilter` expression builder; the **Decision
  Ledger** push/sample/d2c/hold toggles compose with them. A stats line shows the filtered counts.

---

## 7. Other views

- **Leaderboard:** top localities by `icp_score`; columns AREA, city, ICP (mono), verdict badge,
  serviceability, archetype, gtm, brands-confirmed. Rows link to the map selection.
- **Gems:** three tables — Pareto-optimal, Hidden gems (`hidden_gem_v2`), Spillover gems — each with ICP,
  price, and the relevant signal. Replaces v1 Whitespace.
- **Margin:** kept exactly (`margin.js`).
- **Methodology:** rewrite — the serviceable pipeline (ICP → serviceability → gtm), the GTM matrix, and the
  honesty caveats verbatim: *absence ≠ unserviceable*; `city_coverage_confidence` is a proxy; centroid-precision
  `Confirmed` is softer than locality-precision; 115 no-geo localities excluded from the map.

---

## 8. Testing

- **`web/tests/contract.test.js`** (`node --test`): `colorFor(gtm_action)` / `labelFor(gtm_action)` resolve every
  one of the 5 actions; an unknown action falls back to `GTM_DEFAULT_COLOR`.
- **`web/tests/filters.test.js`**: the filter-expression builder produces the right MapLibre expr for each
  combination (all-pass, single facet, multiple facets).
- **`scripts/test_build_locality_data.py`** (pytest): output bundle row count == geocoded count; every row has a
  `color`; `contract.js` color literals equal `contract.py` `GTM_COLORS` (drift guard across the two mirrors).
- Map rendering verified manually + a headless screenshot (Chrome DevTools), as in the original build.

---

## 9. Out of scope (YAGNI)

- The attack-sequence engine (Product 3) — separate spec; may consume this bundle later.
- RAG / ML-API / Slack digest — deferred (need sales data / refresh cadence).
- Gym & Reliance layers — not in the serviceable store; dropped.
- Server/back-end — static, sync-bundled, Vercel-deployed like v1.
- Real-time data — batch; refresh = re-run NB08 + `build_locality_data.py`.
- Sub-pincode geocoding beyond NB08's refinement.

---

## 10. Risks & open questions

- **Two color mirrors** (`contract.py` + `contract.js`) can drift — mitigated by the build-time equality test (§8).
- **Bundle size:** ~300 KB sync JS is fine; if it grows, fall back to v1's two-phase lazy fetch. (Assumed fine.)
- **886/1,001 on the map:** no-geo localities are invisible (correct, honest) — surfaced in Methodology + a count.
- **Dark map vs light chrome:** intentional (map = working surface, chrome = instrument frame); validated by the
  frontend-design direction.
- **v1 retirement:** the old `data-summary.js`/`data-markers.json` and gyms tab are removed, not preserved; v1 is
  recoverable from git history if ever needed.
