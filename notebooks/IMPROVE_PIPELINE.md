# Improvement Guide — Magicbricks ML Pipeline

> **Audience:** Claude Code (or any developer) working on the `notebooks/` pipeline.
> **Scope:** Only `magicbricks_combined.xlsx` (1,001 localities × 16 columns). No external datasets.
> **Goal:** Extract more knowledge from the same data. Every change must serve a downstream decision.

---

## Current pipeline state (what exists and works)

```
01_clean_structure.ipynb       → localities_clean.parquet        (1001 × 31)
02_feature_engineering.ipynb   → features_base.parquet           (1001 × 45)
03_text_mining.ipynb           → features_text.parquet           (1001 × 61) + embeddings.npz
04_geo_graph.ipynb             → features_geo_graph.parquet      (1001 × 70)
05_unsupervised_segmentation   → localities_segmented.parquet    + kmeans.joblib + UMAP plot
06_supervised_imputation       → features_imputed.parquet        + shap_drivers.png
07_similarity_anomaly_synthesis→ localities_features_master.parquet + INSIGHTS.md
```

**What works well:** sequential parquet artifact chain, leakage guard in NB06, confidence flags on
imputation, SHAP driver analysis, Louvain belt detection, BERTopic themes, zero-shot sector tagging,
cross-city lookalike engine.

**What this document covers:** 13 specific improvements, ordered by notebook, each with the problem
it solves, exact implementation guidance, and validation criteria.

---

## Improvement 1 — Parse office and shop prices (NB01)

### Problem
Only residential buy/rent is parsed. The raw price column contains `Office Space: Buy Rs. X-Y / sqft`
and `Shop: Buy Rs. X-Y / sqft` segments for ~58 localities. These are discarded. Office price is an
independent signal of commercial intensity; shop price signals retail footfall value.

### Implementation
In `01_clean_structure.ipynb`, after `extract_residential_prices`, add two parallel parsers:

```python
def extract_office_prices(price_string):
    cols = ["off_min_buy", "off_max_buy", "off_min_rent", "off_max_rent"]
    vals = {c: np.nan for c in cols}
    if pd.isna(price_string):
        return pd.Series(vals)
    segment = next((s for s in re.split(r"\|\|", str(price_string)) if "Office" in s), "")
    buy = re.search(r"Buy\s*" + _NUM, segment)
    if buy:
        vals["off_min_buy"], vals["off_max_buy"] = _to_float(buy.group(1)), _to_float(buy.group(2))
    rent = re.search(r"Rent\s*" + _NUM, segment)
    if rent:
        vals["off_min_rent"], vals["off_max_rent"] = _to_float(rent.group(1)), _to_float(rent.group(2))
    return pd.Series(vals)

def extract_shop_prices(price_string):
    cols = ["shop_min_buy", "shop_max_buy", "shop_min_rent", "shop_max_rent"]
    vals = {c: np.nan for c in cols}
    if pd.isna(price_string):
        return pd.Series(vals)
    segment = next((s for s in re.split(r"\|\|", str(price_string)) if "Shop" in s), "")
    buy = re.search(r"Buy\s*" + _NUM, segment)
    if buy:
        vals["shop_min_buy"], vals["shop_max_buy"] = _to_float(buy.group(1)), _to_float(buy.group(2))
    rent = re.search(r"Rent\s*" + _NUM, segment)
    if rent:
        vals["shop_min_rent"], vals["shop_max_rent"] = _to_float(rent.group(1)), _to_float(rent.group(2))
    return pd.Series(vals)
```

Concat both to df. Add midpoints: `off_avg_buy`, `off_avg_rent`, `shop_avg_buy`, `shop_avg_rent`.

### Validation
- Expect ~50-60 rows with office data, ~20-30 with shop data.
- Spot-check 5 rows against the raw price string to confirm no cross-segment leakage.

### Downstream value
- `off_avg_buy` becomes a predictor in NB06 (helps impute residential price for mixed-use localities).
- `has_office_market` (boolean) and `has_shop_market` (boolean) become useful cluster features.
- `office_residential_ratio = off_avg_buy / res_avg_buy` identifies commercial-dominant localities.

---

## Improvement 2 — Employer quality scoring (NB02)

### Problem
NB03 counts employers and tags sectors, but treats TCS (mass IT services, ₹6-15L CTC) identically to
McKinsey (elite consulting, ₹25-80L CTC). Employer *quality* directly predicts household income
distribution and purchasing power, but this signal is flattened into a count.

### Implementation
In `02_feature_engineering.ipynb`, after the amenity features, add a tiered employer scoring system.
This operates on the raw `Nearby employment hubs` text column (no dependency on NB03 NER output).

```python
EMPLOYER_TIERS = {
    5: ["mckinsey", "bcg", "bain", "deloitte", "kpmg", "pwc", "ernst & young",
        "ernst and young", "e&y", "ey"],
    4: ["google", "american express", "oracle", "dell", "samsung", "microsoft",
        "amazon", "adobe", "sap"],
    3: ["tcs", "infosys", "wipro", "cognizant", "capgemini", "accenture",
        "tech mahindra", "hcl", "mindtree", "mphasis"],
    2: ["genpact", "concentrix", "aon", "xceedance", "ntt data", "xerox",
        "fidelity", "boston scientific"],
    1: ["hero motocorp", "maruti suzuki", "honda", "suzuki motorcycle",
        "carrier air conditioning"],
}

def employer_quality_score(text):
    if pd.isna(text):
        return 0.0
    t = str(text).lower()
    score = 0.0
    for weight, names in EMPLOYER_TIERS.items():
        for name in names:
            if name in t:
                score += weight
    return score

df["employer_quality"] = df["Nearby employment hubs"].apply(employer_quality_score)
```

Also derive `employer_tier_max` (the highest tier found in the text) — this distinguishes "has one
McKinsey mention" from "has five TCS mentions" even when the total scores are similar.

```python
def employer_tier_max(text):
    if pd.isna(text):
        return 0
    t = str(text).lower()
    for tier in [5, 4, 3, 2, 1]:
        for name in EMPLOYER_TIERS[tier]:
            if name in t:
                return tier
    return 0

df["employer_tier_max"] = df["Nearby employment hubs"].apply(employer_tier_max)
```

### Validation
- Confirm Golf Course Road Gurgaon scores higher than Sector 92 Gurgaon.
- Confirm South Delhi embassies (Vasant Vihar) score lower than Cyber City corridor (expected: fewer
  named IT employers, but this is correct — the score measures corporate tech concentration).
- Correlation of `employer_quality` with `res_avg_buy` should be meaningfully positive (>0.15).

### Downstream value
- Replaces or supplements `num_employers` as a predictor in NB06 (should improve imputation R²).
- Becomes a component of the ICP score in NB07 (replaces the current flat `num_employers` term).

---

## Improvement 3 — Lifecycle stage classification (NB03)

### Problem
NB03 derives a `maturity` flag with 3 values: `emerging`, `established`, `mixed`. This is too coarse.
A locality's lifecycle stage is the most important strategic variable for timing market entry, and the
text contains enough signal to distinguish 4 stages.

### Implementation
In `03_text_mining.ipynb`, replace the current `maturity` function with a 4-stage classifier:

```python
STAGE_PATTERNS = {
    "nascent": r"under[- ]?construction|proposed|likely to (improve|develop)|yet to develop|"
               r"nascent|in its infancy|limited.*infrastructure|social.*yet to",
    "emerging": r"upcoming|developing|emerging|fast[- ]?developing|witnessing growth|"
                r"attracting (buyers|investors)|budding|evolving|promising",
    "established": r"well[- ]?developed|established|prominent|sought[- ]?after|"
                   r"self[- ]?sustain|preferred|reputed|thriving|popular|"
                   r"posh|upscale|premium|affluent",
    "saturated": r"densely populated|old (gurgaon|delhi|city)|dominated by|"
                 r"primarily consists of|congested|one of the oldest",
}

def lifecycle_stage(text):
    if pd.isna(text):
        return np.nan
    t = str(text).lower()
    hits = {}
    for stage, pat in STAGE_PATTERNS.items():
        hits[stage] = len(re.findall(pat, t))
    if sum(hits.values()) == 0:
        return np.nan
    return max(hits, key=hits.get)

df["lifecycle"] = df[INTRO].apply(lifecycle_stage)
```

Keep the old `maturity` column for backward compatibility, but add `lifecycle` alongside it.

### Validation
- Gurgaon Sector 82-95 should land as `nascent` or `emerging`.
- Golf Course Road / DLF Phase 5 should land as `established`.
- Old Delhi sectors (Karol Bagh, Chandni Chowk) should land as `saturated`.
- Print a cross-tab of `lifecycle × ADDRESS` to verify city-level plausibility.

### Downstream value
- Becomes a categorical predictor in NB06 (lifecycle affects price independently of amenities).
- Feeds the ICP verdict logic in NB07: `nascent` → WAIT, `emerging` → SAMPLE-FIRST.
- Ordinal encoding (nascent=1, emerging=2, established=3, saturated=4) becomes a clustering feature.

---

## Improvement 4 — Graph-based price spillover (NB04)

### Problem
The adjacency graph is built and used for centrality/belt features, but it ignores the richest signal
a graph can provide: **neighbor prices**. A cheap locality surrounded by expensive neighbors is
structurally underpriced. This is fundamentally different from the IsolationForest anomaly in NB07,
which operates in feature space, not spatial/graph space.

### Implementation
In `04_geo_graph.ipynb`, after computing graph features, add neighbor price aggregates:

```python
# Use imputed prices from the price column (will be NaN for ~45%, that's fine)
prices = df["res_avg_buy"].copy()  # real prices only at this stage

def neighbor_stats(node):
    neighbors = list(G.neighbors(node))
    if not neighbors:
        return np.nan, np.nan, np.nan
    neighbor_prices = prices.iloc[neighbors].dropna()
    if neighbor_prices.empty:
        return np.nan, np.nan, np.nan
    return neighbor_prices.mean(), neighbor_prices.median(), neighbor_prices.std()

stats = pd.DataFrame(
    [neighbor_stats(i) for i in df.index],
    columns=["neighbor_avg_price", "neighbor_median_price", "neighbor_price_std"],
    index=df.index,
)
df = pd.concat([df, stats], axis=1)

# Price gap: positive = this locality is cheaper than its neighbors (underpriced)
df["price_gap_vs_neighbors"] = df["neighbor_avg_price"] - df["res_avg_buy"]

# Relative gap (normalized)
df["price_gap_pct"] = df["price_gap_vs_neighbors"] / df["neighbor_avg_price"]
```

### Validation
- `price_gap_vs_neighbors` should be meaningfully positive for known "value" localities adjacent to
  premium corridors (e.g., Sector 37D near Sohna Road, Ardee City near Golf Course Extension).
- Should be near-zero or negative for premium localities surrounded by similar-tier neighbors.
- Check that the graph actually has edges: this only works for localities with ≥1 neighbor in G.

### Downstream value
- `price_gap_pct > 0.20` directly identifies spatial arbitrage opportunities (future gentrification).
- This becomes an alternative hidden-gem signal in NB07, orthogonal to the IsolationForest method.
- Can be used as a SHAP feature in NB06 to see if "underpriced relative to neighbors" is itself
  predictive of anything (it shouldn't be — it's an outcome, not a cause — but worth checking).

---

## Improvement 5 — Belt-level aggregate features (NB04)

### Problem
Louvain belts are assigned (belt_id, belt_size) but no aggregate features are computed at the belt
level. A belt where the average price is ₹25K/sqft is a different go-to-market from a belt averaging
₹8K/sqft, even if both have 20 localities.

### Implementation
In `04_geo_graph.ipynb`, after belt detection:

```python
# Belt-level aggregates (only for belts with ≥2 localities)
belt_agg = df[df["belt_size"] > 1].groupby("belt_id").agg(
    belt_avg_price=("res_avg_buy", "mean"),
    belt_max_price=("res_avg_buy", "max"),
    belt_price_spread=("res_avg_buy", lambda x: x.max() - x.min() if x.notna().sum() > 1 else np.nan),
    belt_avg_amenities=("total_amenities", "mean"),
    belt_metro_share=("is_metro_connected", "mean"),
    belt_avg_employers=("num_employers", "mean"),
).round(2)

df = df.merge(belt_agg, on="belt_id", how="left")

# Within-belt position: is this locality premium or budget relative to its belt?
df["price_vs_belt"] = df["res_avg_buy"] - df["belt_avg_price"]
```

### Validation
- The Gurgaon mega-belt (60 localities) should show a wide `belt_price_spread`.
- `price_vs_belt` should be positive for Golf Course Road within its belt, negative for Sector 83.

### Downstream value
- `belt_avg_price` and `belt_metro_share` become clustering inputs in NB05 (captures neighborhood context).
- `price_vs_belt` identifies which localities are the "anchor premiums" vs "value entries" within an
  attackable contiguous group.

---

## Improvement 6 — Hospital and school name extraction from text (NB03)

### Problem
The amenity count columns (`num_hospital`, `num_educational_institute`) count comma-separated items
in the structured columns. But the `Social & retail infra` free-text column names specific hospitals
and schools that aren't in the structured columns. Medanta, Fortis, Max, AIIMS, Artemis are mentioned
in text but not counted. Similarly, DPS, Lancers, Shiv Nadar, Ryan International in text.

### Implementation
In `03_text_mining.ipynb`, after the employer NER block, add brand extraction:

```python
PREMIUM_HOSPITALS = [
    "medanta", "fortis", "max hospital", "max super", "artemis", "aiims",
    "apollo", "narayana", "manipal hospital", "cloudnine", "paras hospital",
    "columbia asia", "ck birla",
]
PREMIUM_SCHOOLS = [
    "dps", "delhi public school", "lancers", "shiv nadar", "ryan international",
    "scottish high", "amity international", "gd goenka", "excelsior american",
    "pathways", "the shri ram", "lotus valley", "modern school",
]

def count_brands(text, brand_list):
    if pd.isna(text):
        return 0
    t = str(text).lower()
    return sum(1 for b in brand_list if b in t)

# Search both structured and text columns
social = df["Social & retail infra"].fillna("")
hosp_col = df["Hospital"].fillna("")
edu_col = df["Educational Institute"].fillna("")
combined_health = social + " " + hosp_col
combined_edu = social + " " + edu_col

df["num_premium_hospitals"] = combined_health.apply(lambda t: count_brands(t, PREMIUM_HOSPITALS))
df["num_premium_schools"] = combined_edu.apply(lambda t: count_brands(t, PREMIUM_SCHOOLS))
```

### Validation
- Gurgaon Golf Course Road localities should show 2-4 premium hospitals (Medanta, Fortis, Artemis, Paras).
- South Delhi localities should show AIIMS, Safdarjung, Max.
- Kolkata/Lucknow should show lower counts (fewer national chain hospitals).

### Downstream value
- `num_premium_hospitals` is a stronger affluence proxy than `num_hospital` (a premium hospital locates
  where it expects paying patients).
- `num_premium_schools` directly identifies family-household-dominant areas (relevant for family-oriented
  products vs. young-professional-oriented products).

---

## Improvement 7 — Rental yield as a standalone feature (NB02)

### Problem
`buy_rent_ratio` is computed but its inverse (rental yield = annual rent / buy price) is the metric
real estate investors and D2C brands actually use to assess whether an area is renter-heavy (transient,
young professionals) vs owner-heavy (families, settled).

### Implementation
In `02_feature_engineering.ipynb`:

```python
# Annual rental yield (%) = (monthly rent × 12) / buy price × 100
df["rental_yield_pct"] = (df["res_avg_rent"] * 12) / df["res_avg_buy"] * 100

# Renter-vs-owner signal: high yield = renter market, low yield = owner market
# (in India, <2% yield = owner-heavy, >3.5% = renter-heavy)
df["renter_heavy"] = df["rental_yield_pct"] > 3.5
```

### Validation
- IT corridors near offices (Sohna Road, Whitefield, HITEC City) should show higher yields.
- Old-money residential (Defence Colony, Vasant Vihar, Panchsheel Park) should show lower yields.
- Compute correlation: `rental_yield_pct` should correlate positively with `sector_information_technology`.

### Downstream value
- Renter-heavy areas → younger, more mobile, D2C-friendly, supplement-trial-ready.
- Owner-heavy areas → family-oriented, value loyalty, offline retail dominant.
- This directly informs channel strategy (digital-first vs. retail-first).

---

## Improvement 8 — Improve imputation R² (NB06)

### Problem
Current imputation R² is 0.52. This is directional but weak. Three changes can improve it without
adding external data.

### Implementation changes in `06_supervised_imputation_drivers.ipynb`:

**(a) Add the new features as predictors:**
Add `employer_quality`, `employer_tier_max`, `lifecycle` (ordinal-encoded), `num_premium_hospitals`,
`num_premium_schools`, `rental_yield_pct` (only for localities where rent exists but buy is missing —
careful about partial leakage), `off_avg_buy` (office price, where present), `neighbor_avg_price`,
`price_vs_belt`.

`neighbor_avg_price` and `price_vs_belt` are computed from real neighbor prices and are not
self-referential (a locality's own price is not used to compute its neighbors' average), so there is
no leakage.

**(b) Add text embedding PCA components as features:**
The current NB06 uses only tabular features. Adding the first 15-20 PCA components of the combined
embedding gives the model access to semantic similarity without overfitting on 384 raw dimensions.

```python
emb = np.load(ART / "embeddings.npz")["combined"]
emb_pca = PCA(n_components=20, random_state=42).fit_transform(
    StandardScaler().fit_transform(emb)
)
for i in range(emb_pca.shape[1]):
    X[f"emb_pc{i}"] = emb_pca[:, i]
```

**(c) Target-encode the city variable:**
Currently `ADDRESS` is passed as a categorical to LightGBM. Target encoding (mean price per city,
computed in-fold to avoid leakage) is more informative for tree models with small categorical cardinality.

```python
from sklearn.model_selection import KFold

df["city_target_enc"] = np.nan
kf = KFold(n_splits=5, shuffle=True, random_state=42)
for tr, te in kf.split(df):
    means = df.iloc[tr].groupby("ADDRESS")["res_avg_buy"].mean()
    df.iloc[te, df.columns.get_loc("city_target_enc")] = (
        df.iloc[te]["ADDRESS"].map(means)
    )
```

Add `city_target_enc` to the predictor matrix and drop the categorical `ADDRESS`.

### Expected improvement
- R² should reach 0.60-0.70 with these additions. If it doesn't, report honestly and note that the
  remaining variance is genuinely unobservable from this dataset (micro-location quality, builder
  brand, age of construction — none of which Magicbricks text captures).

### Validation
- Still benchmark against city-mean baseline.
- Still use 5-fold CV with `cross_val_predict`.
- Print the MAE improvement in Rs/sqft — this is the metric that matters for business use.

---

## Improvement 9 — Learn the ICP weights instead of assuming them (NB07)

### Problem
The ICP score is `0.30 × affluence + 0.30 × corporate + 0.10 × youth + 0.15 × access + 0.15 ×
centrality`. These weights are hand-chosen. There is no calibration against any outcome, so the
entire ranking reflects the analyst's priors, not the data's structure.

### Implementation — two options, implement both:

**(a) PCA-derived weights (unsupervised):**
Stack the 5 ICP component percentile vectors into a matrix. Run PCA with 1 component. The loadings
of PC1 are the data-implied weights (the direction of maximum variance across all 5 dimensions).

```python
components = np.column_stack([affluence, corporate, youth, access, centrality])
from sklearn.decomposition import PCA
pca = PCA(n_components=1).fit(components)
learned_weights = pca.components_[0]
learned_weights = learned_weights / learned_weights.sum()  # normalize to sum to 1
print("PCA-learned ICP weights:", dict(zip(
    ["affluence", "corporate", "youth", "access", "centrality"],
    learned_weights.round(3)
)))

df["icp_score_pca"] = (components * learned_weights).sum(axis=1).round(1)
```

**(b) Pareto frontier (no weights needed):**
Rank each locality on each of the 5 dimensions. A locality is Pareto-dominant if no other locality
beats it on *all* 5 dimensions simultaneously. Localities on the Pareto frontier are unambiguous
"GO" regardless of weight choice.

```python
def is_pareto_dominant(costs):
    """Return boolean mask of Pareto-optimal rows (higher = better on all dims)."""
    is_optimal = np.ones(costs.shape[0], dtype=bool)
    for i, c in enumerate(costs):
        is_optimal[i] = not np.any(np.all(costs >= c, axis=1) & np.any(costs > c, axis=1))
    return is_optimal

ranks = np.column_stack([affluence, corporate, youth, access, centrality])
df["pareto_optimal"] = is_pareto_dominant(ranks)
print("Pareto-optimal localities:", df["pareto_optimal"].sum())
```

Note: for 1,001 rows × 5 dimensions, the naive O(n²) check is fine (~1M comparisons).

### Validation
- Compare the top 20 localities under hand-weighted ICP, PCA-weighted ICP, and Pareto frontier.
- Report which localities move most between methods — these are the ones most sensitive to weight
  choice, meaning the analyst should look at them individually rather than trusting any score.

### Downstream value
- PCA-ICP replaces the assumed-weight ICP as the primary score.
- Pareto-optimal flag identifies the "no-brainer" localities that rank highly regardless of methodology.
- The weight comparison table itself is an insight: if PCA puts 0.45 on affluence and 0.05 on youth,
  it means youth-signal barely differentiates localities in this dataset.

---

## Improvement 10 — Hidden gem detection via graph spillover (NB07)

### Problem
Current hidden gems are defined as `icp_score >= 65 AND (below-median price OR imputed price)`. This
is a single-dimensional filter. Graph-based spillover offers a second, orthogonal hidden-gem signal.

### Implementation
In `07_similarity_anomaly_synthesis.ipynb`, after the IsolationForest block:

```python
# Graph-spillover hidden gems: localities that are cheap but whose graph neighbors
# are significantly more expensive (spatial arbitrage / gentrification candidates)
df["spillover_gem"] = (
    (df["price_gap_pct"] > 0.20) &   # ≥20% cheaper than neighbors
    (df["graph_degree"] >= 2) &        # actually connected (not isolated node)
    (df["neighbor_avg_price"].notna())
)

# Combined hidden gem: either ICP-based OR spillover-based
df["hidden_gem_v2"] = df["hidden_gem"] | df["spillover_gem"]
```

### Validation
- Spillover gems should be geographically adjacent to premium corridors — verify on a map.
- There should be minimal overlap with IsolationForest anomalies (they measure different things).
- Print the spillover gems with their `price_gap_pct` for manual review.

---

## Improvement 11 — Competitive density and choice intensity (NB02)

### Problem
Amenity counts measure *presence* but not *competition*. A locality with 1 hospital is captive; a
locality with 5 hospitals has consumer choice. This affects go-to-market: captive markets need
distribution-first strategies; competitive markets need differentiation-first strategies.

### Implementation
In `02_feature_engineering.ipynb`:

```python
# Choice intensity: average number of options per amenity type (where present)
amenity_present = (df[NUM_COLS] > 0).sum(axis=1)  # how many types present
df["choice_intensity"] = df["total_amenities"] / amenity_present.replace(0, np.nan)

# Amenity concentration: is infrastructure concentrated in one type or spread across many?
# Gini coefficient across amenity counts (0 = perfectly equal, 1 = all in one type)
def gini(row):
    counts = np.array([row[c] for c in NUM_COLS], dtype=float)
    counts = counts[counts > 0]
    if len(counts) == 0:
        return np.nan
    n = len(counts)
    mean_c = counts.mean()
    if mean_c == 0:
        return 0.0
    return float(np.sum(np.abs(counts[:, None] - counts[None, :])) / (2 * n * n * mean_c))

df["amenity_gini"] = df[NUM_COLS].apply(gini, axis=1)
```

### Validation
- `choice_intensity` > 3 should correlate with premium, high-competition localities.
- `amenity_gini` near 1 should flag localities where one amenity type dominates (e.g., education-only
  areas near university campuses).

---

## Improvement 12 — Text-derived connectivity features (NB03)

### Problem
`airport_min` is extracted but several other connectivity signals in the physical infrastructure text
are ignored: distance to railway station, distance to highway (NH-48, expressway), and number of
metro stations mentioned.

### Implementation
In `03_text_mining.ipynb`, extend the regex block:

```python
def railway_km(text):
    if pd.isna(text):
        return np.nan
    m = re.search(r"railway station.{0,40}?(\d{1,3})\s*km", str(text), re.I)
    if not m:
        m = re.search(r"(\d{1,3})\s*km.{0,40}?railway station", str(text), re.I)
    return int(m.group(1)) if m else np.nan

def count_metro_stations(text):
    if pd.isna(text):
        return 0
    return len(re.findall(r"metro station", str(text), re.I))

def highway_adjacent(text):
    if pd.isna(text):
        return False
    return bool(re.search(r"NH[- ]?\d+|national highway|expressway|dwarka expressway", str(text), re.I))

df["railway_km"] = df[PHYS].apply(railway_km)
df["num_metro_stations_mentioned"] = df[PHYS].apply(count_metro_stations)
df["is_highway_adjacent"] = df[PHYS].apply(highway_adjacent)
```

### Validation
- `railway_km` should be small for old-city localities (Sector 4-5 Gurgaon, Karol Bagh Delhi).
- `num_metro_stations_mentioned` > 2 should be premium well-connected areas.
- `is_highway_adjacent` should be true for sectors along NH-48, Dwarka Expressway, Sohna Road.

---

## Improvement 13 — Validation and reporting improvements (cross-cutting)

### Problem
Several validation gaps exist across notebooks:

1. **NB05 silhouette score is reported but stability is tested only once** (single 80% subsample).
   Run 10 subsamples and report mean ± std ARI.

2. **NB06 reports R² and MAE but not per-city performance.** The model may be excellent for Gurgaon
   (many training rows, well-differentiated) and terrible for Lucknow (few rows, narrow price range).
   Print per-city MAE.

3. **NB07 INSIGHTS.md doesn't include the SHAP top drivers.** The analyst reading INSIGHTS.md has to
   open a PNG to see them. Add the top 10 drivers as a text table.

4. **No notebook validates the geocoding quality.** 886/1001 geocoded, but pgeocode maps to pincode
   centroids — a pincode can span 5-10 km. For dense urban areas this is fine; for rural/peri-urban
   pincodes it can be off by 15+ km. Flag any locality where `dist_to_city_centroid_km > 50` as
   `geo_uncertain = True`.

### Implementation

**NB05 — stability test:**
```python
aris = []
for seed in range(10):
    rng = np.random.RandomState(seed)
    idx = rng.choice(len(Xp), int(0.8 * len(Xp)), replace=False)
    km_sub = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit(Xp[idx])
    aris.append(adjusted_rand_score(df["cluster"].values[idx], km_sub.labels_))
print(f"Cluster stability (10 subsamples): ARI = {np.mean(aris):.3f} ± {np.std(aris):.3f}")
```

**NB06 — per-city MAE:**
```python
city_mae = pd.DataFrame({"city": cities, "actual": yp, "predicted": oof})
print("Per-city MAE (Rs/sqft):")
print(city_mae.groupby("city").apply(
    lambda g: mean_absolute_error(g["actual"], g["predicted"])
).round(0).sort_values().to_string())
```

**NB07 — add SHAP to INSIGHTS.md:**
```python
# After the SHAP section in NB06, save the top drivers as a CSV or add to df metadata
# In NB07, read and insert into the markdown:
lines.append("\n## Top 10 affluence drivers (SHAP)\n")
lines.append("| Feature | Mean |SHAP| |\n| --- | --- |\n")
for feat, val in imp.head(10).items():
    lines.append(f"| {feat} | {val:.1f} |\n")
```

**NB01 — geocoding quality flag:**
```python
df["geo_uncertain"] = df["dist_to_city_centroid_km"] > 50
print("Geocoding uncertain:", df["geo_uncertain"].sum())
```

---

## Summary of changes by notebook

| Notebook | Changes |
|---|---|
| **01** | Parse office + shop prices; geocoding quality flag |
| **02** | Employer quality score (tiered); rental yield; choice intensity; amenity Gini |
| **03** | Lifecycle stage (4-level); premium hospital/school brand counts; railway/highway/metro-count features |
| **04** | Graph price spillover; belt-level aggregates; within-belt price position |
| **05** | 10-subsample stability test |
| **06** | Add new features as predictors; add embedding PCA; target-encode city; per-city MAE |
| **07** | PCA-learned ICP weights; Pareto frontier; graph-spillover hidden gems; SHAP in INSIGHTS.md |

## Expected impact

| Metric | Current | Expected after improvements |
|---|---|---|
| Price imputation R² | 0.52 | 0.60-0.70 |
| Feature count | ~75 | ~100 |
| Hidden gems identified | 67 | 80-100 (with spillover gems) |
| ICP weight method | hand-assumed | data-derived (PCA) + robustness-checked (Pareto) |
| Lifecycle stages | 3 (coarse) | 4 (actionable) |
| Employer signal | flat count | quality-weighted score |

## What these improvements do NOT address

- External data enrichment (satellite, census, Google Trends) — out of scope per user instruction.
- Cross-dataset fusion with gym/Reliance data — out of scope per user instruction.
- Deep learning or fine-tuning — not justified at 1,001 rows.
- Real-time data refresh — this is a batch pipeline; refresh cadence is a product decision.
