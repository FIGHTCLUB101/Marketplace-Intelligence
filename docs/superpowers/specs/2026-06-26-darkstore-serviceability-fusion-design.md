# Darkstore-Serviceability Fusion — Design Spec
**2026-06-26**

> Enrich the 1,001-locality ML feature store (`localities_features_master.parquet`) with a
> **confidence-aware quick-commerce serviceability layer**, fusing in the geocoded Blinkit / Zepto /
> Swiggy Instamart darkstore locations. The darkstore set is a **sample, not the full population**, so the
> method is deliberately **asymmetric**: a nearby known store *confirms* reach; the absence of one only
> *lowers confidence* — it never declares a locality "unserviceable."

---

## 1. Purpose & success criteria

**Problem:** the master feature store captures *demand context* (affluence, employers, sectors, amenities)
but says nothing about whether GOAT Life can actually **deliver** to a locality via quick commerce. Darkstore
proximity is the missing **serviceability** dimension that turns *"right kind of place?"* into *"right kind of
place AND quick-commerce-reachable?"*

**Success =** every locality gains a serviceability state + confidence + a combined go-to-market action, such
that:
1. No locality is ever wrongly labelled "unserviceable" due to a darkstore missing from our sample.
2. The two dimensions (demand `icp_verdict` × serviceability) collapse into one actionable `gtm_action`.
3. Every serviceability value carries an explicit confidence that reflects how well its city is mapped.

**This is an enrichment, not a product.** The consumer (RAG / dashboard / ML API / report) is a separate,
later decision; this spec produces the richer data foundation only.

---

## 2. Inputs

| Input | Source | Notes |
|---|---|---|
| `localities_features_master.parquet` | `notebooks/artifacts/` (NB07 output) | 1,001 × 128; has `lat`, `lng` (886 geocoded), `icp_verdict`, `dist_to_city_centroid_km`, `ADDRESS` (city) |
| `darkstores.json` | `web/darkstores.json` (in repo) | 4,081 geocoded darkstores — Blinkit 1,954 / Zepto 1,089 / Swiggy Instamart 1,038, across 83 cities |

**Reuse:** the haversine, ~0.1° spatial-grid neighbourhood scan, and city-name normalization
(`Delhi→New Delhi`, `Bengaluru→Bangalore`) from `darkstore version 1` / the production `pipeline/darkstores.py`.

**Key assumption (stated, not hidden):** `darkstores.json` is a **partial sample** of the true darkstore
population. All inference below treats *presence* as evidence and *absence* as uncertainty.

---

## 3. Where it lives

A new pipeline notebook **`notebooks/08_darkstore_serviceability.ipynb`** (built + executed via a
`build_nb08.py` script, like NB01–07).

- **Reads:** the two inputs above (auto-locating `darkstores.json` whether run from `notebooks/` or repo root).
- **Writes:** `artifacts/localities_master_serviceable.parquet` + `notebooks/localities_master_serviceable.csv`
  + `notebooks/localities_master_serviceable.xlsx`.

---

## 4. Computation

### 4a. Distance & count features (raw evidence)
For each locality **with** `lat`/`lng`, scanning known stores via the spatial grid:
- `nearest_blinkit_km`, `nearest_zepto_km`, `nearest_instamart_km` — nearest known store of that brand (`NaN` if none in window)
- `nearest_known_darkstore_km` — min across the three
- `n_darkstores_within_3km` — total known stores ≤ 3.5 km
- `n_brands_serviceable` — distinct brands (0–3) with a known store ≤ 3.5 km

Localities **without** coords → all distances `NaN`.

### 4b. City mapping-completeness (calibration)
- `city_known_darkstores` — count of known darkstores in the locality's city (city-normalized)
- `city_coverage_confidence` ∈ {**High**, **Medium**, **Low**} — bucketed from `city_known_darkstores`
  (tertiles across the 10 cities). **Documented as a proxy** — there is no ground-truth darkstore total, so
  this calibrates *confidence in absence*, not precision.

### 4c. Asymmetric 3-state serviceability (core)
`serviceability_state` per locality — **presence confirms, absence only lowers confidence:**

| State | Rule |
|---|---|
| **`Confirmed`** | `nearest_known_darkstore_km ≤ 3.5` (evidence-based; high confidence regardless of city mapping) |
| **`Likely`** | not Confirmed, but `nearest_known_darkstore_km ≤ 6.0` **OR** (`city_coverage_confidence` is High/Medium **AND** `dist_to_city_centroid_km ≤` the city's median centroid distance) — i.e. probably covered, our sample missed the exact store |
| **`Unknown`** | none of the above — thinly-mapped city / peripheral / no geo. **Never rendered as "unserviceable."** |

`serviceability_confidence` ∈ {High, Medium, Low}:
- `Confirmed` → **High**
- `Likely` → **High** if `city_coverage_confidence`=High else **Medium**
- `Unknown` → **Low**

### 4d. Go-to-market action matrix
`gtm_action` from `icp_verdict` × serviceability:

| | Confirmed / Likely | Unknown |
|---|---|---|
| **GO** | **PUSH-NOW** (Blinkit listing + ads) | **D2C / OFFLINE — verify QC** |
| **SAMPLE-FIRST** | **SAMPLE + QC test** | **SAMPLE (D2C / offline)** |
| **WAIT** | **HOLD** | **HOLD** |

---

## 5. Outputs

`localities_master_serviceable.parquet` (1,001 × ~139) + CSV + xlsx. **New columns (~11):**
`nearest_blinkit_km`, `nearest_zepto_km`, `nearest_instamart_km`, `nearest_known_darkstore_km`,
`n_darkstores_within_3km`, `n_brands_serviceable`, `city_known_darkstores`, `city_coverage_confidence`,
`serviceability_state`, `serviceability_confidence`, `gtm_action`.

---

## 6. Validation & honesty (in the notebook)

- Distribution of `serviceability_state` (Confirmed / Likely / Unknown) and `gtm_action`.
- **Confirmed-% per city** — sanity: Gurugram / Bangalore / Hyderabad tech belts should be mostly `Confirmed`;
  thinly-mapped cities should skew `Likely`/`Unknown` (not falsely `Confirmed`).
- Spot-check ~6 named localities (e.g. a Cyber City–adjacent area = Confirmed; a peripheral sector = Unknown).
- Markdown states the two non-negotiables: **absence ≠ unserviceable**, and `city_coverage_confidence` is a
  **proxy** (no ground-truth totals).

---

## 7. Out of scope (YAGNI)

- **Coverage-probability modelling** (Approach B) — speculative + slightly circular at N=1,001; deferred.
- **Acquiring more darkstore data** — we work with the existing sample + confidence flags.
- **The consumer product** (RAG / dashboard / ML API / report) — a separate brainstorm/spec on top of this store.
- **Re-feeding the production `web/` "Where to Win" map** — possible later, not here.
- **Gym / Reliance / real-sales fusion** — not part of this layer.

---

## 8. Risks & open questions

- **Likely/Unknown boundary is heuristic.** The 6 km radius + central-in-served-city rule is a judgement call;
  surfaced via `serviceability_confidence` so consumers can weight it. (Assumed acceptable for a shortlisting
  layer, not a precise SLA.)
- **City confidence tertiles** could mislabel a mid-size well-served city. Mitigation: print the per-city store
  counts so the bucketing is inspectable.
- **86% geo coverage** means ~115 localities are `Unknown (no-geo)` — correct (we can't place them), and honest.
