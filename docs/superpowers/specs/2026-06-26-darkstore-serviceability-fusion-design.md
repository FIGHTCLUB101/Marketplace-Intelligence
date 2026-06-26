# Darkstore-Serviceability Fusion — Design Spec (v2)
**2026-06-26**

> Enrich the 1,001-locality ML feature store (`localities_features_master.parquet`) with a
> **confidence-aware quick-commerce serviceability layer**, fusing in the geocoded Blinkit / Zepto /
> Swiggy Instamart darkstore locations. The darkstore set is a **sample, not the full population**, so the
> method is deliberately **asymmetric**: a nearby known store *confirms* reach; the absence of one only
> *lowers confidence* — it never declares a locality "unserviceable."

> **v2 changelog** — folds in findings from `notebooks/IMPROVE_NB08_DARKSTORE.md`, after verifying its claims
> against the data:
> - **Adopted (verified real):** coordinate-collapse fix (§4a) — pgeocode centroials make up to **83 Bangalore
>   localities share one coordinate**; precision-adjusted radii (§4c).
> - **Adopted (useful):** per-brand `*_confirmed` flags + `n_brands_confirmed` (§4b) — GOAT Life is Blinkit-first,
>   so *which* brand confirms matters.
> - **Rejected (false):** the claim that "Chennai/Pune are Zepto-only." Verified `darkstores.json` has
>   **Chennai = Blinkit 65 / Swiggy 71 / Zepto 83** and **Pune = 94 / 49 / 54**. That alarm was an artifact of
>   reading the raw CSVs without normalization — which is exactly the trap §2 guards against.

---

## 1. Purpose & success criteria

**Problem:** the master feature store captures *demand context* (affluence, employers, sectors, amenities)
but says nothing about whether GOAT Life can actually **deliver** to a locality via quick commerce. Darkstore
proximity is the missing **serviceability** dimension that turns *"right kind of place?"* into *"right kind of
place AND quick-commerce-reachable?"*

**Success =** every locality gains a serviceability state + confidence + a combined go-to-market action, such
that:
1. No locality is ever wrongly labelled "unserviceable" because a darkstore is missing from our sample.
2. No serviceability label is a **coordinate artifact** (localities sharing a pincode centroid must not all
   inherit one identical label).
3. The two dimensions (demand `icp_verdict` × serviceability) collapse into one actionable `gtm_action`,
   with *which brands* confirm surfaced (Blinkit-first relevance).
4. Every value carries an explicit confidence reflecting both coordinate precision and city mapping density.

**This is an enrichment, not a product.** The consumer (RAG / dashboard / ML API / report) is a separate,
later decision; this spec produces the richer data foundation only.

---

## 2. Inputs

| Input | Source | Notes |
|---|---|---|
| `localities_features_master.parquet` | `notebooks/artifacts/` (NB07 output) | 1,001 × 128; has `lat`, `lng` (886 geocoded), `icp_verdict`, `icp_score`, `dist_to_city_centroid_km`, `ADDRESS` (city), `AREA` |
| `darkstores.json` | `web/darkstores.json` (in repo) | 4,081 geocoded darkstores, **already city-normalized**. Per-brand × 10-city counts verified present for **all three brands in all cities** |

**Primary source = `darkstores.json`** (already normalized in the original darkstore project). We do **not**
read the raw per-brand CSVs as the primary path: that route requires re-doing city normalization and is where
the rejected "Chennai/Pune Zepto-only" error came from.

**City normalization (must hold):** `Delhi→New Delhi`, `Bengaluru→Bangalore`. Reuse the haversine +
~0.1° spatial-grid scan from `darkstore version 1` / `pipeline/darkstores.py`.

**Optional (not in v1 build):** the raw Blinkit CSV carries an `accuracy` field; if a later iteration wants to
weight Blinkit stores by geocoding reliability, switch that brand to the raw CSV — but only with the
normalization above re-applied and validated.

**Key assumption (stated, not hidden):** `darkstores.json` is a **partial sample** of the true darkstore
population. All inference treats *presence* as evidence and *absence* as uncertainty.

---

## 3. Where it lives

A new pipeline notebook **`notebooks/08_darkstore_serviceability.ipynb`** (built + executed via a
`build_nb08.py` script, like NB01–07).
- **Reads:** the two inputs above (auto-locating `darkstores.json` whether run from `notebooks/` or repo root).
- **Writes:** `artifacts/localities_master_serviceable.parquet` + `notebooks/localities_master_serviceable.csv`
  + `notebooks/localities_master_serviceable.xlsx`.
- **New dependency:** `geopy` (for the coordinate-refinement pass in §4a). Add to `requirements-ml.txt`.

---

## 4. Computation

### 4a. Coordinate refinement — the coordinate-collapse fix *(verified critical)*
pgeocode maps each pincode to one centroid, so many distinct localities share an identical `lat/lng`
(verified: Bangalore 99 geocoded → 13 unique coords, **83 on one point**; Mumbai 62; Kolkata 37; Gurugram 23).
Left unfixed, those localities all compute identical distances → identical serviceability labels (an artifact).

**Refinement (run once, cached):**
1. Flag localities whose `(lat,lng)` is shared with ≥1 other (`df.duplicated(['lat','lng'], keep=False)`).
2. For each, Nominatim-geocode `"{area_core}, {city}, India"` (1 req/sec, `user_agent` set, cached to
   `artifacts/coord_cache.json`). Accept the result only if within **35 km of the city centroid**
   (sanity guard) → set `lat_r`/`lng_r` and `coord_precision = "locality"`.
3. On failure / out-of-range / network unavailable → keep the centroid, `coord_precision = "pincode"`.
4. Unique-coord localities (already locality-level) → `coord_precision = "locality"`; no-geo → unchanged.

All §4b distance math uses `lat_r`/`lng_r`.

**Fallback (first-class, not afterthought):** if the network/geocoder is unavailable, **skip step 2**, mark all
shared-coord localities `coord_precision = "pincode"`, and proceed. The pipeline still runs; centroid-precision
labels simply carry wider radii (§4c) and lower confidence. The notebook prints the precision distribution so
the trade-off is visible.

### 4b. Distance, count & per-brand confirmation features
For each locality with coordinates, scanning known stores via the grid (≤10 km window):
- `nearest_blinkit_km`, `nearest_swiggy_km`, `nearest_zepto_km` — nearest known store per brand (`NaN` if none)
- `nearest_known_darkstore_km` — min across brands
- `n_darkstores_within_3km` — total known stores ≤ 3.5 km
- **Per-brand confirmation** (using the precision-adjusted confirm radius from §4c):
  `blinkit_confirmed`, `swiggy_confirmed`, `zepto_confirmed` (bool)
- `n_brands_confirmed` (0–3) and `brands_confirmed_list` (e.g. `"Blinkit+Zepto"`)

No-geo localities → distances `NaN`, all `*_confirmed = False`.

### 4c. Asymmetric 3-state serviceability — precision-adjusted *(presence confirms, absence lowers confidence)*

Radii widen for centroid-precision coordinates to absorb ≤~4 km positional uncertainty:

| | locality precision | pincode precision |
|---|---|---|
| Confirm radius | 3.5 km | 5.5 km |
| Likely radius | 6.0 km | 8.0 km |

| State | Rule (`nearest_known_darkstore_km` vs the precision radii) |
|---|---|
| **`Confirmed`** | `≤ confirm_radius` — evidence-based |
| **`Likely`** | `≤ likely_radius`, **or** a central locality (`dist_to_city_centroid_km ≤` its city median) in a High/Medium-mapped city |
| **`Unknown`** | otherwise — thinly-mapped / peripheral / no-geo. **Never "unserviceable."** |

`serviceability_confidence` ∈ {High, Medium, Low}:
- `Confirmed` + `coord_precision="locality"` → **High**; `Confirmed` + `"pincode"` → **Medium**
  (a centroid-based confirm is softer — treat as "likely" in high-stakes calls).
- `Likely` → **High** if `city_coverage_confidence`=High else **Medium**.
- `Unknown` → **Low**.

### 4d. City mapping-completeness (calibration)
- `city_known_darkstores` — count of known stores in the locality's city (normalized)
- `city_coverage_confidence` ∈ {High, Medium, Low} — tertiles of `city_known_darkstores` across the 10 cities.
  **Documented as a proxy** (no ground-truth totals). Per-city counts are printed for inspection.

### 4e. Go-to-market action matrix
`gtm_action` from `icp_verdict` × serviceability (`Confirmed`/`Likely` grouped as "reachable"):

| | Confirmed / Likely | Unknown |
|---|---|---|
| **GO** | **PUSH-NOW** (Blinkit listing + ads) | **D2C / OFFLINE — verify QC** |
| **SAMPLE-FIRST** | **SAMPLE + QC test** | **SAMPLE (D2C / offline)** |
| **WAIT** | **HOLD** | **HOLD** |

`brands_confirmed_list` rides alongside so a Blinkit-first reader can filter `PUSH-NOW` rows to those where
`blinkit_confirmed = True`.

---

## 5. Outputs

`localities_master_serviceable.parquet` (1,001 × ~146) + CSV + xlsx. **New columns (~18):**
`coord_precision`, `lat_r`, `lng_r`, `nearest_blinkit_km`, `nearest_swiggy_km`, `nearest_zepto_km`,
`nearest_known_darkstore_km`, `n_darkstores_within_3km`, `blinkit_confirmed`, `swiggy_confirmed`,
`zepto_confirmed`, `n_brands_confirmed`, `brands_confirmed_list`, `city_known_darkstores`,
`city_coverage_confidence`, `serviceability_state`, `serviceability_confidence`, `gtm_action`.

---

## 6. Validation & honesty (in the notebook)

- `coord_precision` distribution (how many refined to locality-level vs left as centroid).
- `serviceability_state` and `gtm_action` distributions.
- **Confirmed-% per city** — sanity: Gurugram / Bangalore / Hyderabad tech belts mostly `Confirmed`; thinly-mapped
  cities skew `Likely`/`Unknown` (not falsely `Confirmed`).
- **Per-brand presence check** — print per-city counts for all three brands and assert each target city has
  ≥1 store per brand where expected (guards against re-introducing the normalization bug; verified Chennai/Pune
  have all three).
- Spot-check ~6 named localities (Koramangala = Confirmed; a peripheral sector = Unknown; Sushant Lok = Confirmed).
- Markdown states the non-negotiables: **absence ≠ unserviceable**; `city_coverage_confidence` is a **proxy**;
  centroid-precision `Confirmed` is softer than locality-precision `Confirmed`.

---

## 7. Out of scope (YAGNI)

- **Coverage-probability modelling** — speculative + circular at N=1,001; deferred.
- **Acquiring more darkstore data** — work with the existing sample + confidence flags.
- **Raw-CSV `accuracy` weighting for Blinkit** — optional later iteration, not v1.
- **The consumer product** (RAG / dashboard / ML API / report) — a separate brainstorm/spec on top of this store.
- **Re-feeding the production `web/` "Where to Win" map** — possible later, not here.
- **Gym / Reliance / real-sales fusion** — not this layer.
- **A 15-cell confidence-granular GTM matrix** (from IMPROVE_NB08) — over-engineered; the 2×3 matrix +
  `brands_confirmed_list` carries the same signal more simply.

---

## 8. Risks & open questions

- **Nominatim refinement reliability.** Re-geocoding ~600 shared-coord localities is slow (≈1 req/sec, ~15–20 min)
  and imperfect for Indian locality names; the 35 km sanity guard + cache mitigate, and the "skip → pincode"
  fallback (§4a) keeps the build runnable offline. *Open: is the refinement run worth the time, or ship v1 on
  centro­id precision with wider radii?* (Recommendation: attempt refinement, cache, but the fallback is fully valid.)
- **Likely/Unknown boundary is heuristic** (radius + central-in-served-city). Surfaced via `serviceability_confidence`.
- **City confidence tertiles** could mislabel a mid-size well-served city; mitigated by printing per-city counts.
- **86% geo coverage** → ~115 localities are `Unknown (no-geo)` — correct and honest.
- **Normalization is load-bearing.** The rejected Bug 3 proves that reading darkstores without careful city
  normalization produces false "no coverage" conclusions. Using the pre-normalized `darkstores.json` + the
  per-brand presence assertion in §6 is the guard.
