# GOAT Life — "Where to Win" Geographic Intelligence Console
**Design Spec · 2026-06-25**

> A brand-specific spatial-intelligence dashboard that scores every locality GOAT Life can target,
> tells the team **where to push next and how**, and grounds it in GOAT Life's real unit economics.
> Built as a portfolio piece to demonstrate capability to GOAT Life — the convergence of the
> author's five existing QC/D2C projects, aimed at one real brand.

---

## 1. Purpose & Success Criteria

**Problem it solves for GOAT Life:** GOAT Life grows through founder-led marketing, limited drops,
gym/pop-up sampling, Blinkit dark-store priority, and selective offline retail. Today those
"where next" decisions are intuition-led. This tool turns three scraped datasets into a ranked,
mapped, defensible answer: *which localities, gyms, and stores deserve the next marketing rupee,
pop-up, gym tie-up, or Blinkit push.*

**Success = a GOAT Life operator can:**
1. Open a map of a city and instantly see localities ranked by **GOAT-Fit Score** (0–100).
2. Click any locality and get a **GO / SAMPLE-FIRST / WAIT** verdict + the *reason* + the *recommended channel*.
3. See a **whitespace** view: high-fit pockets with thin existing modern-retail presence.
4. Pull a **gym partnership hit-list** and a **Reliance offline shelf-test list**, pre-ranked.
5. Sanity-check the economics against GOAT Life's **real Blinkit numbers** (₹119 MRP / ₹99 selling / 57% GM).

**This is a decision-support tool, not a guarantee.** Every score carries a visible methodology and
the same source/confidence discipline as QCompass.

---

## 2. Data Inputs (real, scraped, geocoded)

All three files live in the project root and are already validated + geocoded (pgeocode, offline).

| Dataset | Rows | Key fields used | Role |
|---|---|---|---|
| `magicbricks_localities.xlsx` | 600 localities, 10 cities | AREA, CITY, PINCODE, price range, employment hubs, educational institutes, social/retail infra, transport | **Demand context** — the locality universe + scoring inputs |
| `justdial_gyms_manual.xlsx` | 1,537 gyms, 10 cities | City, Gym Name, Address (pincode embedded) | **Fitness-demand density** + partnership targets |
| `reliance_smart_bazaar_stores.xlsx` | 137 stores, 10 cities | City, Store Name, Address, Pincode | **Modern-retail footprint** — saturation/whitespace + offline shelf-test targets |
| `data-markers.json` (copied from `darkstore version 1`) | 4,081 darkstores (Blinkit 1,954 / Zepto 1,089 / Instamart 1,038), 83 cities | lat, lng, brand, city | **QC delivery infrastructure** — serviceability layer; overlaps all 10 of our cities |

**Self-contained data:** darkstore's `data-markers.json` is **copied into this project** (`web/darkstores.json`)
at build time so the deployment has no external folder dependency. City-name normalization applies
(darkstore *Delhi*→our *New Delhi*; *Bengaluru*↔*Bangalore*).

**Geocoding (validated 2026-06-25, `pgeocode` India, pincode-centroid):**
- Magicbricks: **508/600 (85%)** · Reliance: **134/137 (98%)** · Gyms: **1,532/1,537 (100%)**
- **Known limitation:** pincode-centroid means localities sharing a pincode share a point. Acceptable for
  a city-level demand heatmap. **Refinement (optional, phase 2):** Nominatim area-name geocoding for the
  ~92 missed magicbricks rows + sub-pincode precision, reusing darkstore v1's `geocode_neighborhoods.py`
  pattern (1 req/sec, cached to JSON). Base layer ships on pincode centroids; refinement is additive.

**City coverage (deepest first):** Gurugram (GOAT HQ — 100 localities / 197 gyms / 11 stores),
Delhi, Pune, Chennai, Chandigarh are fullest across all three. Mumbai/Bangalore/Hyderabad/Kolkata/Lucknow
have 20 localities each. **V1 ships all 10 cities and opens on an all-India overview** (national-footprint
view like darkstore v1), then drills into any city. Gurugram remains the data-richest showcase.

---

## 3. The GOAT-Fit Score (the core engine)

Per-locality composite, 0–100, computed in the Python pipeline and shipped pre-baked (like darkstore's
`data-summary.js`). Directly mirrors darkstore's `calculateLocalityMetrics` pattern — multiple
sub-scores → weighted composite → classification.

```
GOAT-Fit = 0.35 · Affluence
         + 0.30 · FitnessDensity
         + 0.25 · CorporateDensity
         + 0.10 · YouthDensity
```

| Sub-score | Source | Computation | Normalization |
|---|---|---|---|
| **Affluence** | magicbricks price range (residential buy ₹/sqft) | parse low–high, take midpoint | percentile-rank across all localities (0–100) |
| **FitnessDensity** | gyms joined by pincode | count gyms in locality's pincode | percentile-rank (capped) |
| **CorporateDensity** | "Nearby employment" + "Commercial Hub" text | count distinct named hubs/companies | percentile-rank |
| **YouthDensity** | "Educational Institute" text | count distinct institutions | percentile-rank |

**Missing-data rule (explicit, non-fabricated):** when a sub-score input is absent (e.g. ~247 localities
lack price data), that sub-score is marked `null`, the weight is **redistributed across present
sub-scores**, and the locality is flagged `partial-data` in the UI (greyed confidence). Never imputed
silently — same discipline as QCompass's `⬛ UNAVAILABLE`.

**Why these weights:** GOAT Life's ICP is the affluent, fitness-conscious, time-poor urban professional
(see knowledge base §15). Affluence = can pay the QC premium; FitnessDensity = proximity to the exact
buyer; CorporateDensity = the busy-professional "30-second breakfast" need + B2B pantry upside;
Youth = drop-culture / social-virality audience. Weights are surfaced and editable in the Methodology panel.

---

## 3b. Full Column Utilization (every field has a job)

The 4 weighted scoring signals above are the **quantitative core**. The remaining magicbricks columns
(and the darkstore overlay) drive **four additional structured outputs** — none are decoration.

### (i) QC Serviceability layer  *(darkstore `data-markers.json` + Physical infrastructure)*
- **`nearest_darkstore_km`** per locality + per brand, via darkstore v1's haversine + spatial-hash engine.
- **`qc_serviceable`** = a Blinkit/Zepto/Instamart darkstore within **3.5 km**.
- **Physical infrastructure** text → parsed `metro_connected` (bool) + `airport_min` (if stated) →
  a D2C-logistics feasibility note. Complements `qc_serviceable` for the no-darkstore case.
- This makes the verdict **delivery-aware**: a GO locality with no darkstore is D2C/offline-only, not QC.

### (ii) Activation Playbook  *(Transportation Hub + Shopping Centre + Social & retail infra + Tourist Spot)*
Per locality, a concrete sampling/pop-up venue list — matched to GOAT Life's real GTM (metro tastings,
mall pop-ups, café sampling, Phase-1 protein langars):
- **Transportation Hub** → metro/transit tasting spots
- **Shopping Centre** → mall pop-up venues
- **Social & retail infra** → cafés/restaurants for sampling
- **Tourist Spot** → high-footfall brand-visibility spots
Shown in the inspector and used to flesh out SAMPLE-FIRST recommendations.

### (iii) Locality Archetype  *(Locality introduction + signals)*
Each locality classified into a persona that sharpens channel routing and gives the inspector a one-line
character blurb:
- **Corporate Belt** (high corporate + commercial intro) → Blinkit + B2B
- **Premium Residential** (high affluence + residential intro) → D2C subscription
- **Student Hub** (high youth) → campus drops + social
- **Commercial/Retail** (mall/market-dense) → offline + pop-up
- **Emerging** (low signals) → Hold

### (iv) Context flags & links
- **Hospital** → `health_ecosystem` flag (health-aware population supports a protein brand) — inspector context.
- **Nearby Localities** → adjacency list in the inspector (neighbor name + verdict) → "attack this belt".
- **URL** → Magicbricks **source link** per locality (source transparency, QCompass discipline).
- **Locality introduction** → shown verbatim as the inspector's one-line context blurb.

**Column → job coverage:** AREA, ADDRESS, PINCODE (identity/geo) · Price (Affluence) · Employment +
Commercial Hub (Corporate) · Education (Youth) · Physical infra (serviceability/logistics) · Transport +
Shopping + Social infra + Tourist (Activation Playbook) · Locality intro (Archetype + blurb) · Hospital
(health flag) · Nearby Localities (adjacency) · URL (source). **No column is unused.**

---

## 4. The Verdict & Channel-Routing Layer

Each locality gets a **verdict** (QCompass GO/CAUTION/STOP pattern, re-themed for expansion):

| Verdict | Trigger | Meaning |
|---|---|---|
| **GO** | GOAT-Fit ≥ 70 | High-priority: direct marketing spend, Blinkit dark-store priority, anchor pop-up |
| **SAMPLE-FIRST** | 45 ≤ GOAT-Fit < 70 | Validate with a pop-up / gym sampling before committing spend |
| **WAIT** | GOAT-Fit < 45 | Insufficient ICP density today — revisit later |

**Serviceability tag (appended to every verdict):** `qc_serviceable` → **"QC-ready"** (darkstore ≤ 3.5 km)
vs **"D2C/offline-only"** (no darkstore nearby). A GO/QC-ready locality is a push-now Blinkit target;
a GO/D2C-only locality routes to subscription or offline instead.

**Channel routing** (rule-based, from the locality's archetype + strongest signal + serviceability):

| Dominant signal | Routed channel |
|---|---|
| High Corporate + qc_serviceable | **Blinkit priority + B2B corporate-pantry** (employment column names the target companies) |
| High Affluence + residential archetype | **D2C subscription** push |
| High FitnessDensity | **Gym partnership + sampling** (links to the gym hit-list) |
| Reliance store present + GOAT-Fit ≥ 55 | **Offline shelf-test** candidate |
| High GOAT-Fit but **not** qc_serviceable | **D2C / offline only** (flag: no QC reach yet) |

---

## 5. Views / Components

Single-page app, tabbed like darkstore v1. Each view is an isolated module.

1. **Where-to-Win Map** *(hero)* — MapLibre dark map. Localities as circles colored by verdict
   (GO/SAMPLE/WAIT), gyms as small dots, Reliance as squares, **and 4,081 darkstores as brand-colored
   dots (Blinkit gold / Zepto purple / Instamart orange) with per-brand toggle filters**. City search.
   Click a locality → Intelligence panel.
2. **Locality Intelligence panel** *(darkstore inspector pattern)* — GOAT-Fit gauge + the 4 sub-score
   bars + verdict badge + **serviceability tag (QC-ready / D2C-only + nearest-darkstore km per brand)** +
   **archetype** + routed channel + **Activation Playbook venue list** (metro/malls/cafés/tourist) +
   **health-ecosystem flag** + **adjacency list** (neighbor localities + verdicts) + the raw magicbricks
   intro blurb + **Magicbricks source link**.
3. **City Leaderboard** — ranked table of localities per city by GOAT-Fit, with verdict + channel columns
   (the "Monday morning hit-list").
4. **Whitespace Finder** *(DATA 22-26 bubble pattern)* — x = GOAT-Fit, y = affluence, bubble = fitness
   density; dashed "GOAT white space" box = high-fit + low modern-retail saturation.
5. **Gym Partnership Hit-List** — 1,537 gyms ranked by the GOAT-Fit of their pincode → where to run
   sampling / tie-ups first.
6. **Margin Reality calculator** *(full port of QCompass `calculations.js` + D2C playbook)* — a fully
   **interactive** calculator: editable MRP / COGS / gross-margin / discount / platform, returning the
   per-order unit-economics waterfall and a GO/CAUTION/STOP contribution verdict. **Pre-filled with GOAT
   Life's real Blinkit numbers** (₹119 MRP, ₹99 selling = 16% brand-funded discount, 57% GM, 17.9%
   commission, ₹50 fulfilment) so it opens on-message, but any pack/platform can be modeled. Reuses the
   commission/price-tolerance tiers and the GO/CAUTION/STOP thresholds verbatim from the existing engines.
7. **Methodology panel** — formula, weights (editable), geocoding coverage, sources, confidence levels,
   data-gap disclosure.

---

## 6. Architecture

Mirror darkstore v1 exactly so it reads as a continuation of that work.

**Data pipeline (Python, offline):**
```
xlsx (3 files)
  → parse + clean (openpyxl)
  → geocode by pincode (pgeocode)              [+ optional Nominatim area refinement]
  → join gyms & stores to localities by pincode
  → compute sub-scores + GOAT-Fit + verdict + channel
  → emit  data-summary.js   (stats + city rollups, sync-loaded for instant FCP)
          data-markers.json  (per-locality + gym + store points, lazy-fetched)
```
Two-phase load is the darkstore pattern (`app.js` Phase 1/Phase 2).

**Frontend (vanilla JS ES modules, zero build):**
- `index.html`, `styles.css`, `state.js` (AppState slot pattern), `app.js` (orchestrator),
  `map.js` (MapLibre + spatial-hash grid + haversine — reused), `score.js` (verdict/channel display
  logic), `charts.js` (Chart.js whitespace + leaderboard), `methodology.js`.
- Libraries via CDN: **MapLibre GL JS 3.6.2**, **Chart.js**, OpenFreeMap dark tiles — identical to darkstore.

**Why vanilla, not React:** darkstore v1 (the piece this most extends) is vanilla; matching it makes the
lineage obvious and keeps it deployable as static files on Vercel with no build step.

---

## 7. Visual Design

Reuse darkstore's token system, tinted with GOAT Life's brand.

- **Chassis:** darkstore dark — `--bg-base:#09090b`, `--bg-surface:#18181b`, `--border:rgba(255,255,255,.08)`.
- **Brand accent:** GOAT warm gold (from packaging/site) `--goat-gold:#F5A623` → primary accents, live
  data highlights, and the Whitespace zone.
- **Verdict palette:** GO `#059669` (green), SAMPLE-FIRST `#d97706` (amber), WAIT `#52525b` (grey),
  Whitespace highlight `#F5A623`.
- **Type:** **Outfit** (darkstore's font) for UI; consider **DM Sans/DM Mono** echo for data readouts
  (the author's cross-project signature). Single family decision finalized at build.
- `ⓘ` info-tooltip pattern + methodology disclaimers throughout (darkstore + QCompass discipline).

---

## 8. Build Phases (for the implementation plan)

1. **Data pipeline** — parser + pgeocode + pincode joins + GOAT-Fit/verdict/channel → `data-summary.js` + `data-markers.json`.
2. **Map + Intelligence panel** — MapLibre dark map, verdict-colored localities, click-to-inspect.
3. **Leaderboard + Whitespace + Gym hit-list** — Chart.js + ranked tables.
4. **Margin Reality calculator + Methodology** — port QCompass `calculations.js` (interactive, GOAT-prefilled) + transparency panel.
5. **Polish + deploy** — GOAT-gold theming, responsive, Vercel static deploy, README/case-study bullet.

---

## 9. Out of Scope (YAGNI)

- No backend / database / live API (static, client-side — like darkstore).
- No real-time scraping; datasets are fixed snapshots (June 2026).
- No login, no per-user state.
- No precise sub-pincode geocoding in V1 (pincode-centroid base; Nominatim refinement is optional phase 2).
- No cities beyond the 10 in the data.

---

## 10. Risks & Open Questions

- **Geocoding granularity:** pincode-centroid clusters co-pincode localities. Mitigated by Intelligence
  panel showing the named locality; refinement optional. *Acceptable for V1?* (assumed yes)
- **Magicbricks text parsing:** employment/education counts depend on free-text parsing — will need a
  simple, documented heuristic (count comma-separated named entities), flagged MEDIUM confidence.
- **Affluence coverage:** ~247/600 localities lack price data → weight redistribution + `partial-data`
  flag. Confirm that's preferable to dropping them. (assumed: keep + flag)
- **Default scope:** ships all 10 cities, **opens on all-India overview** (confirmed).
- **Margin Reality:** **full interactive calculator** ported from QCompass, GOAT-prefilled (confirmed).

---

## 11. Portfolio Framing

This piece deliberately fuses all five prior projects, pointed at one real brand:
- **darkstore v1** → the map + spatial-hash engine + locality scoring grid
- **DATA 22-26** → the whitespace finder + opportunity-score lineage (already cross-referenced)
- **QCompass** → the GO/verdict pattern + source/confidence discipline + real margin engine
- **D2C_QC_Playbook** → the margin-reality calculator + commission/price-tolerance tiers
- **Surge_Simulator** → the pure-function, testable engine discipline

Pitch line: *"Here's where GOAT Life's next 50 pop-ups, gym tie-ups, and Blinkit dark-store priorities
should go — scored from real data, with the economics to back it."*
