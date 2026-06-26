# NB08 Darkstore Serviceability — Build Guide for Claude Code

> **Context:** The master feature store (`localities_features_master.parquet`, 1,001 × 128) is complete
> through NB07. This guide specifies how to build NB08 to fuse it with the three darkstore CSV files.
> Approach A (distance + confidence heuristic) from the design spec is the right choice over Approach B.
> But the data reveals four critical problems the spec didn't anticipate that will produce wrong labels
> if not fixed. Fix those first. The rest of this document is the complete build spec.

---

## Section 0 — Is Approach A good enough?

Yes — with the four fixes in Section 1. Approach B (coverage-probability model) is deferred correctly
because it's speculative and slightly circular at this dataset size. Approach A is transparent,
explainable, and recoverable when new darkstore data arrives.

What makes Approach A worth trusting here: presence of a darkstore within N km is falsifiable evidence.
Absence is genuinely ambiguous at sample scale. The 3-state output (Confirmed / Likely / Unknown) is
honest about this asymmetry. No downstream consumer will be misled if the confidence flags are surfaced.

---

## Section 1 — Four critical bugs to fix before writing a single feature

### Bug 1 — Coordinate resolution collapse (CRITICAL, affects all cities)

**What the data shows:** pgeocode maps pincodes to centroids. Multiple distinct localities sharing
a pincode all receive the identical lat/lng. The scale of collapse is severe:

| City | Geocoded | Unique coords | Largest group sharing one coord |
|---|---|---|---|
| Bangalore | 99 | 13 | **83 localities — same point** |
| Mumbai | 96 | 16 | **62 localities — same point** |
| Kolkata | 99 | 24 | 37 localities |
| Lucknow | 82 | 18 | 20 localities |
| Hyderabad | 99 | 46 | 17 localities |
| Chandigarh | 39 | 9 | 14 localities |
| Gurugram | 75 | 10 | 23 localities |
| Pune | 100 | 27 | 13 localities |
| New Delhi | 99 | 33 | 12 localities |
| Chennai | 98 | 57 | 7 localities |

**Why it matters:** 83 Bangalore localities all compute the same haversine distance to every darkstore
because they all share one coordinate. Every one of them gets the same `serviceability_state`. This
is a measurement artifact, not a real serviceability signal.

**The fix — two-step coordinate refinement:**

Step 1: For each (lat, lng) group with more than 1 locality sharing the coordinate, extract the
`area_core` names (locality names stripped of city suffix) and attempt Google Maps / Nominatim geocoding
on `"{area_core}, {city}, India"` to get genuine per-locality coordinates. Cache results.

Step 2: Where geocoding fails or returns coordinates outside a 25 km radius of the city centroid,
keep the pincode centroid but add a `coord_is_centroid = True` flag and set `coord_precision = "pincode"`
vs `"locality"`. Downstream serviceability for centroid-precision rows must use a wider radius (+2 km)
to compensate for the positional uncertainty.

```python
# Pseudo-code for coordinate refinement
from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="goatlife-nb08")

def refine_coord(area, city, fallback_lat, fallback_lng):
    query = f"{area.split(',')[0].strip()}, {city}, India"
    try:
        loc = geolocator.geocode(query, timeout=5)
        if loc:
            # Sanity check: within 30km of city centroid
            d = haversine_km(loc.latitude, loc.longitude, city_centroid_lat, city_centroid_lng)
            if d < 30:
                return loc.latitude, loc.longitude, "locality"
    except Exception:
        pass
    return fallback_lat, fallback_lng, "pincode"

# Apply to all localities where coord is shared with >= 2 others
shared_mask = df.duplicated(subset=['lat', 'lng'], keep=False)
for idx, row in df[shared_mask].iterrows():
    lat, lng, precision = refine_coord(row['AREA'], row['ADDRESS'], row['lat'], row['lng'])
    df.at[idx, 'lat_refined'] = lat
    df.at[idx, 'lng_refined'] = lng
    df.at[idx, 'coord_precision'] = precision

# Use lat_refined / lng_refined for all distance calculations in NB08
```

If Nominatim rate limits, batch with 1-second delays. The 1,001-row set means this runs in under
20 minutes. Cache results to a `coord_cache.json` to avoid re-running.

---

### Bug 2 — Blinkit coordinate reliability (HIGH, affects Blinkit-confirmed labels)

**What the data shows:** The Blinkit CSV has an `accuracy` field. 693 of 1,954 stores have
`accuracy = 0`, meaning zero geocoding confidence — their coordinates could be completely wrong.
Only 304 stores have accuracy < 25 (high confidence).

**The fix — filter before use:**

```python
# Weight Blinkit stores by geocoding reliability
# accuracy field: lower value = higher reliability (meters of uncertainty)
# 0 = no confidence data (treat as medium uncertainty)
# > 100 = clearly unreliable, exclude

blinkit_hq = blinkit[blinkit['accuracy'] <= 50].copy()   # excludes 13 very-low stores
blinkit_mq = blinkit[(blinkit['accuracy'] > 50)].copy()  # 13 stores, flag separately

# Use hq for Confirmed labels, full set for Likely
# Add a brand-level confidence column
blinkit['store_coord_reliable'] = blinkit['accuracy'].between(0, 50) | (blinkit['accuracy'] == 0)
```

For the `nearest_blinkit_km` computation: use only `accuracy <= 50` stores. A darkstore with
accuracy=400 meters is just noise in the geocoding, but accuracy=0 (unknown) is a different beast —
treat those as medium confidence rather than excluding them entirely.

---

### Bug 3 — Single-brand confirmation asymmetry (HIGH, affects Chennai and Pune)

**What the data shows:**

| City | Blinkit | Swiggy | Zepto | Total in target cities |
|---|---|---|---|---|
| Chennai | 0 | 0 | 83 | 83 |
| Pune | 0 | 0 | 54 | 54 |
| Mumbai | 12 | 7 | 119 | 138 |

Chennai and Pune have **zero Blinkit or Swiggy stores** in the dataset. A `Confirmed` label in
Chennai means "a Zepto store is within 3.5 km." If GOAT Life's sales funnel runs through Blinkit
or Swiggy in those cities, a Zepto-only `Confirmed` label could send budget to cities where the
brand can't actually deliver.

**The fix — per-brand flags plus a `brands_confirmed` count:**

Do not collapse to a single `serviceability_state` before computing per-brand distances. Add:

```python
# Per brand
for brand, col_prefix, df_stores in [
    ('Blinkit', 'blinkit', blinkit_hq),
    ('Swiggy',  'swiggy',  swiggy),
    ('Zepto',   'zepto',   zepto),
]:
    dists = ...  # haversine to all stores of this brand
    df[f'nearest_{col_prefix}_km'] = dists.min()
    df[f'{col_prefix}_confirmed'] = dists.min() <= 3.5

# Combined
df['n_brands_confirmed'] = (
    df['blinkit_confirmed'].astype(int) +
    df['swiggy_confirmed'].astype(int) +
    df['zepto_confirmed'].astype(int)
)

# Richer serviceability states — distinguish single vs multi-brand confirmation
def serviceability_state(row):
    n = row['n_brands_confirmed']
    nearest = row['nearest_known_darkstore_km']
    if n >= 2:
        return 'Confirmed-Multi'   # 2+ brands within 3.5 km — strong
    elif n == 1:
        return 'Confirmed-Single'  # 1 brand — weaker, flag which brand
    elif nearest <= 6.0:
        return 'Likely'
    else:
        return 'Unknown'
```

This gives downstream consumers the option to filter on `n_brands_confirmed >= 2` for high-confidence
multi-platform reach, or use `Confirmed-Single` with `blinkit_confirmed = True` if they're building
a Blinkit-first strategy.

---

### Bug 4 — 3.5 km threshold applied to pincode centroids is systematically wrong (MEDIUM)

**What the data shows:** The current geocoding produces pincode-level centroids. A pincode in urban
India covers 3–8 km of street network. A locality "within" a pincode can be at any point within that
boundary. Applying a 3.5 km threshold from the centroid means the actual locality street could be
3.5 + 4 = 7.5 km from the nearest darkstore — not confirmed at all.

**The fix — radius adjustment by coord_precision:**

```python
CONFIRM_RADIUS_LOCALITY = 3.5   # refined locality coordinate — tight threshold
CONFIRM_RADIUS_CENTROID = 5.5   # pincode centroid — compensate for positional uncertainty
LIKELY_RADIUS_LOCALITY  = 6.0
LIKELY_RADIUS_CENTROID  = 8.0

def assign_state(row):
    r_conf = CONFIRM_RADIUS_LOCALITY if row.get('coord_precision') == 'locality' else CONFIRM_RADIUS_CENTROID
    r_like = LIKELY_RADIUS_LOCALITY  if row.get('coord_precision') == 'locality' else LIKELY_RADIUS_CENTROID
    if row['nearest_known_darkstore_km'] <= r_conf:
        return 'Confirmed'
    if row['nearest_known_darkstore_km'] <= r_like:
        return 'Likely'
    return 'Unknown'
```

Document this explicitly in the notebook: "Thresholds are wider for pincode-centroid coordinates
to account for ≤4 km positional uncertainty. Treat centroid-precision Confirmed labels as Likely
in any high-stakes decision."

---

## Section 2 — Input preparation

### 2a. File loading

```python
from pathlib import Path
import numpy as np
import pandas as pd

ART = Path.cwd() / "artifacts"

# Master feature store from NB07
df = pd.read_parquet(ART / "localities_features_master.parquet").reset_index(drop=True)
print("Master store:", df.shape)
print("Geocoded:", df['lat'].notna().sum(), "/ 1001")

# Darkstores — three separate files
blinkit = pd.read_csv(find_file("blinkit-darkstores-geocoded.csv"))
swiggy  = pd.read_csv(find_file("swiggy-darkstores-geocoded.csv"))
zepto   = pd.read_csv(find_file("zepto-darkstores.csv"))

blinkit['brand'] = 'Blinkit'
swiggy['brand']  = 'Swiggy'
zepto['brand']   = 'Zepto'

# City normalization — must match ADDRESS values in master store
CITY_MAP = {
    'bengaluru': 'Bangalore', 'bangalore': 'Bangalore',
    'new delhi': 'New Delhi', 'delhi': 'New Delhi',
    'gurugram': 'Gurugram', 'gurgaon': 'Gurugram',
    'mumbai': 'Mumbai', 'pune': 'Pune',
    'hyderabad': 'Hyderabad', 'chennai': 'Chennai',
    'kolkata': 'Kolkata', 'lucknow': 'Lucknow',
    'chandigarh': 'Chandigarh', 'tamilnadu': None,
}

for ds in [blinkit, swiggy, zepto]:
    ds['city_norm'] = ds['city'].str.lower().str.strip().map(CITY_MAP).fillna(ds['city'])

TARGET_CITIES = df['ADDRESS'].unique().tolist()
```

### 2b. Blinkit quality filtering

```python
# Exclude Blinkit stores with extreme positional uncertainty
# accuracy field: radius of uncertainty in meters (0 = unknown, not necessarily bad)
# Only exclude the clearly wrong ones (>100m uncertainty AND known)
blinkit_use = blinkit[~((blinkit['accuracy'] > 100) & (blinkit['accuracy'] > 0))].copy()
print(f"Blinkit: {len(blinkit)} total, {len(blinkit_use)} after quality filter")
print(f"Excluded: {len(blinkit) - len(blinkit_use)} very-low-accuracy stores")
```

---

## Section 3 — Core computation

### 3a. Coordinate refinement (run once, cache)

```python
import json
import time
from geopy.geocoders import Nominatim

CACHE_FILE = ART / "coord_cache.json"
coord_cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

geolocator = Nominatim(user_agent="goatlife-nb08-v1")

def city_centroid(city):
    city_rows = df[df['ADDRESS'] == city].dropna(subset=['lat','lng'])
    return city_rows['lat'].mean(), city_rows['lng'].mean()

CITY_CENTROIDS = {city: city_centroid(city) for city in TARGET_CITIES}

def refine_coord(area, city, fallback_lat, fallback_lng):
    key = f"{area}|{city}"
    if key in coord_cache:
        return coord_cache[key]

    name = area.split(',')[0].strip()
    query = f"{name}, {city}, India"
    try:
        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
        loc = geolocator.geocode(query, timeout=10)
        if loc:
            clat, clng = CITY_CENTROIDS[city]
            d = haversine_km(loc.latitude, loc.longitude, clat, clng)
            if d < 35:  # sanity: within 35km of city center
                result = (round(loc.latitude, 5), round(loc.longitude, 5), "locality")
                coord_cache[key] = result
                CACHE_FILE.write_text(json.dumps(coord_cache))
                return result
    except Exception as e:
        pass

    result = (fallback_lat, fallback_lng, "pincode")
    coord_cache[key] = result
    return result

# Apply only where coordinate is shared (duplicate coord = centroid artifact)
df['lat_r'] = df['lat']
df['lng_r'] = df['lng']
df['coord_precision'] = 'pincode'

shared_coords = df.duplicated(subset=['lat','lng'], keep=False) & df['lat'].notna()
print(f"Localities with shared/centroid coordinates: {shared_coords.sum()}")

for idx, row in df[shared_coords].iterrows():
    la, lg, prec = refine_coord(row['AREA'], row['ADDRESS'], row['lat'], row['lng'])
    df.at[idx, 'lat_r'] = la
    df.at[idx, 'lng_r'] = lg
    df.at[idx, 'coord_precision'] = prec

# Localities with unique coords (already locality-level from pgeocode)
unique_coords = df['lat'].notna() & ~shared_coords
df.loc[unique_coords, 'coord_precision'] = 'locality'
print("Coord precision distribution:")
print(df['coord_precision'].value_counts(dropna=False).to_string())
```

### 3b. Spatial grid for fast lookup

Reuse the spatial hash grid pattern from darkstore version 1. Grid cell size 0.1° (~11 km).

```python
from collections import defaultdict

def build_grid(stores_df, cell_size=0.1):
    grid = defaultdict(list)
    for _, row in stores_df.iterrows():
        cell = (int(row['lat'] // cell_size), int(row['lng'] // cell_size))
        grid[cell].append((row['lat'], row['lng'], row.get('brand', '')))
    return grid

def nearby_from_grid(lat, lng, grid, radius_km, cell_size=0.1):
    """Return list of (distance_km, brand) for stores within radius_km."""
    lat_cells = int(radius_km / 111) + 1
    lng_cells = int(radius_km / (111 * np.cos(np.radians(lat)))) + 1
    cell_lat = int(lat // cell_size)
    cell_lng = int(lng // cell_size)
    candidates = []
    for dlat in range(-lat_cells, lat_cells + 1):
        for dlng in range(-lng_cells, lng_cells + 1):
            for slat, slng, brand in grid.get((cell_lat + dlat, cell_lng + dlng), []):
                d = haversine_km(lat, lng, slat, slng)
                if d <= radius_km:
                    candidates.append((d, brand))
    return candidates

# Build per-brand grids
grid_blinkit  = build_grid(blinkit_use)
grid_swiggy   = build_grid(swiggy)
grid_zepto    = build_grid(zepto)
grid_all      = build_grid(pd.concat([blinkit_use, swiggy, zepto], ignore_index=True))
```

### 3c. Per-locality distance features

```python
# Thresholds — wider for pincode centroids (Bug 4 fix)
RADIUS_SCAN = 10.0  # scan window (conservative, filter by precision below)
CONFIRM_THRESH = {'locality': 3.5, 'pincode': 5.5}
LIKELY_THRESH  = {'locality': 6.0, 'pincode': 8.0}

results = []
for idx, row in df.iterrows():
    lat, lng = row['lat_r'], row['lng_r']
    prec = row.get('coord_precision', 'pincode')

    if pd.isna(lat) or pd.isna(lng):
        results.append({
            'nearest_blinkit_km': np.nan, 'nearest_swiggy_km': np.nan,
            'nearest_zepto_km': np.nan, 'nearest_known_darkstore_km': np.nan,
            'n_darkstores_3km': 0, 'n_darkstores_5km': 0,
            'n_brands_confirmed': 0, 'blinkit_confirmed': False,
            'swiggy_confirmed': False, 'zepto_confirmed': False,
            'brands_confirmed_list': '',
        })
        continue

    r_conf = CONFIRM_THRESH[prec]
    r_like = LIKELY_THRESH[prec]

    b_near = nearby_from_grid(lat, lng, grid_blinkit, RADIUS_SCAN)
    s_near = nearby_from_grid(lat, lng, grid_swiggy,  RADIUS_SCAN)
    z_near = nearby_from_grid(lat, lng, grid_zepto,   RADIUS_SCAN)
    all_near = nearby_from_grid(lat, lng, grid_all,   RADIUS_SCAN)

    nb = min([d for d,_ in b_near], default=np.nan)
    ns = min([d for d,_ in s_near], default=np.nan)
    nz = min([d for d,_ in z_near], default=np.nan)
    na = min([d for d,_ in all_near], default=np.nan)

    b_conf = not pd.isna(nb) and nb <= r_conf
    s_conf = not pd.isna(ns) and ns <= r_conf
    z_conf = not pd.isna(nz) and nz <= r_conf

    brands = [br for br, flag in [('Blinkit', b_conf), ('Swiggy', s_conf), ('Zepto', z_conf)] if flag]

    results.append({
        'nearest_blinkit_km': round(nb, 2) if not pd.isna(nb) else np.nan,
        'nearest_swiggy_km':  round(ns, 2) if not pd.isna(ns) else np.nan,
        'nearest_zepto_km':   round(nz, 2) if not pd.isna(nz) else np.nan,
        'nearest_known_darkstore_km': round(na, 2) if not pd.isna(na) else np.nan,
        'n_darkstores_3km':   sum(1 for d,_ in all_near if d <= 3.5),
        'n_darkstores_5km':   sum(1 for d,_ in all_near if d <= 5.5),
        'n_brands_confirmed': len(brands),
        'blinkit_confirmed': b_conf,
        'swiggy_confirmed':  s_conf,
        'zepto_confirmed':   z_conf,
        'brands_confirmed_list': '+'.join(brands) if brands else '',
    })

svc_df = pd.DataFrame(results, index=df.index)
df = pd.concat([df, svc_df], axis=1)
```

---

## Section 4 — City coverage confidence

The spec's tertile approach is correct. Implement it with explicit per-city store counts printed
for inspection, as specified.

```python
# Per-city store counts (for our 10 target cities only)
city_store_counts = {}
for city in TARGET_CITIES:
    b_ct = len(blinkit_use[blinkit_use['city_norm'] == city])
    s_ct = len(swiggy[swiggy['city_norm'] == city])
    z_ct = len(zepto[zepto['city_norm'] == city])
    city_store_counts[city] = {'blinkit': b_ct, 'swiggy': s_ct, 'zepto': z_ct,
                                'total': b_ct + s_ct + z_ct}

counts_df = pd.DataFrame(city_store_counts).T.sort_values('total', ascending=False)
print("City store counts (INSPECT BEFORE PROCEEDING):")
print(counts_df.to_string())

# Coverage confidence from tertiles of total count
totals = counts_df['total']
t33, t67 = totals.quantile(0.33), totals.quantile(0.67)
def coverage_confidence(city):
    total = city_store_counts[city]['total']
    if total >= t67: return 'High'
    if total >= t33: return 'Medium'
    return 'Low'

df['city_known_darkstores'] = df['ADDRESS'].map({c: v['total'] for c, v in city_store_counts.items()})
df['city_coverage_confidence'] = df['ADDRESS'].map({c: coverage_confidence(c) for c in TARGET_CITIES})

# ALSO: add brand-specific coverage confidence
# Crucial for Chennai/Pune where only Zepto has data
for brand, ds in [('blinkit', blinkit_use), ('swiggy', swiggy), ('zepto', zepto)]:
    brand_counts = ds[ds['city_norm'].isin(TARGET_CITIES)]['city_norm'].value_counts().to_dict()
    col = f'city_{brand}_count'
    df[col] = df['ADDRESS'].map(brand_counts).fillna(0).astype(int)

# Flag cities where a brand has zero presence — critical for honest labelling
df['blinkit_zero_in_city'] = df['city_blinkit_count'] == 0
df['swiggy_zero_in_city']  = df['city_swiggy_count'] == 0
df['zepto_zero_in_city']   = df['city_zepto_count'] == 0
```

---

## Section 5 — Serviceability state and GTM action

```python
def compute_serviceability(row):
    prec = row.get('coord_precision', 'pincode')
    r_conf = CONFIRM_THRESH[prec]
    r_like = LIKELY_THRESH[prec]
    nearest = row['nearest_known_darkstore_km']
    n_brands = row['n_brands_confirmed']
    city_conf = row['city_coverage_confidence']
    dist_centroid = row.get('dist_to_city_centroid_km', np.nan)
    city = row['ADDRESS']

    # No coordinates — cannot place locality
    if pd.isna(nearest):
        return 'Unknown', 'Low', 'no-geo'

    # Confirmed: strong evidence — at least 1 brand within threshold
    if nearest <= r_conf:
        # Distinguish single-brand vs multi-brand confirmation
        if n_brands >= 2:
            return 'Confirmed', 'High', 'multi-brand'
        else:
            # Single brand — still Confirmed, but note which brand
            brand_note = row.get('brands_confirmed_list', 'single-brand')
            return 'Confirmed', 'High' if city_conf == 'High' else 'Medium', brand_note

    # Likely: within wider radius OR central location in well-mapped city
    is_central = (not pd.isna(dist_centroid) and
                  dist_centroid <= df.groupby('ADDRESS')['dist_to_city_centroid_km'].median().get(city, 15))
    if nearest <= r_like or (city_conf in ('High', 'Medium') and is_central):
        conf = 'High' if city_conf == 'High' else 'Medium'
        return 'Likely', conf, 'proximity'

    return 'Unknown', 'Low', 'peripheral'

states = df.apply(compute_serviceability, axis=1)
df['serviceability_state'] = [s[0] for s in states]
df['serviceability_confidence'] = [s[1] for s in states]
df['serviceability_reason'] = [s[2] for s in states]

# GTM action matrix (extended from spec to handle single-brand confirmation)
GTM_MATRIX = {
    ('GO',           'Confirmed', 'High'):   'PUSH-NOW-ALL-BRANDS',
    ('GO',           'Confirmed', 'Medium'): 'PUSH-NOW-VERIFY-BRANDS',
    ('GO',           'Likely',    'High'):   'LIST-AND-TEST',
    ('GO',           'Likely',    'Medium'): 'LIST-AND-TEST',
    ('GO',           'Unknown',   'Low'):    'D2C-OFFLINE-FIRST',
    ('SAMPLE-FIRST', 'Confirmed', 'High'):   'SAMPLE-QC-TEST',
    ('SAMPLE-FIRST', 'Confirmed', 'Medium'): 'SAMPLE-QC-TEST',
    ('SAMPLE-FIRST', 'Likely',    'High'):   'SAMPLE-QC-TEST',
    ('SAMPLE-FIRST', 'Likely',    'Medium'): 'SAMPLE-DIGITAL-FIRST',
    ('SAMPLE-FIRST', 'Unknown',   'Low'):    'SAMPLE-OFFLINE',
    ('WAIT',         'Confirmed', 'High'):   'HOLD-MONITOR',
    ('WAIT',         'Confirmed', 'Medium'): 'HOLD-MONITOR',
    ('WAIT',         'Likely',    'High'):   'HOLD-MONITOR',
    ('WAIT',         'Likely',    'Medium'): 'HOLD',
    ('WAIT',         'Unknown',   'Low'):    'HOLD',
}

def gtm(row):
    key = (row['icp_verdict'], row['serviceability_state'], row['serviceability_confidence'])
    return GTM_MATRIX.get(key, 'REVIEW-MANUALLY')

df['gtm_action'] = df.apply(gtm, axis=1)
```

---

## Section 6 — Validation (mandatory, not optional)

Print every block below. If any block looks wrong, stop and investigate before saving.

```python
print("=" * 60)
print("SERVICEABILITY STATE DISTRIBUTION")
print(df['serviceability_state'].value_counts(dropna=False).to_string())

print("\nSERVICEABILITY BY CITY")
print(df.groupby('ADDRESS')['serviceability_state'].value_counts().unstack(fill_value=0).to_string())

print("\nCONFIRMED % BY CITY — sanity check")
conf_pct = df.groupby('ADDRESS').apply(
    lambda x: (x['serviceability_state']=='Confirmed').mean()*100
).round(0).sort_values(ascending=False)
print(conf_pct.to_string())
# Expected: Gurugram/Bangalore/New Delhi > 70%; Kolkata/Hyderabad < 70%
# If Chennai or Pune > 60%, note these are Zepto-only

print("\nCHENNAI AND PUNE WARNING")
for city in ['Chennai', 'Pune']:
    city_conf = df[df['ADDRESS']==city]
    only_zepto = city_conf[city_conf['zepto_confirmed'] & ~city_conf['blinkit_confirmed'] & ~city_conf['swiggy_confirmed']]
    print(f"{city}: {len(only_zepto)} localities Zepto-only confirmed (Blinkit+Swiggy absent from dataset)")

print("\nGTM ACTION DISTRIBUTION")
print(df['gtm_action'].value_counts().to_string())

print("\nPUSH-NOW LOCALITIES (top opportunities)")
push_now = df[df['gtm_action'].str.startswith('PUSH-NOW')].nlargest(15, 'icp_score')
print(push_now[['AREA','ADDRESS','icp_score','serviceability_state','n_brands_confirmed','gtm_action']].to_string(index=False))

print("\nCOORD PRECISION DISTRIBUTION")
print(df['coord_precision'].value_counts(dropna=False).to_string())

print("\nSPOT-CHECKS — named localities")
SPOT = ['Koramangala, Bangalore', 'Sushant Lok, Gurgaon', 'Attibele, Bangalore',
        'Baner, Pune', 'Alipore, Kolkata', 'Sector 43, Gurgaon']
for area in SPOT:
    row = df[df['AREA'].str.contains(area.split(',')[0], case=False, na=False)]
    if len(row):
        r = row.iloc[0]
        print(f"  {r['AREA'][:35]:35s} | {r['serviceability_state']:18s} | nearest={r['nearest_known_darkstore_km']:.1f}km | brands={r['n_brands_confirmed']} | {r['gtm_action']}")
# Expected: Koramangala = Confirmed; Attibele = Unknown; Sushant Lok = Confirmed
```

---

## Section 7 — Output

```python
# Save master + serviceability
out_parquet = ART / "localities_master_serviceable.parquet"
df.to_parquet(out_parquet, index=False)

# CSV for consumption
df.to_csv(Path.cwd() / "localities_master_serviceable.csv", index=False)

# Excel for stakeholders
df.to_excel(Path.cwd() / "localities_master_serviceable.xlsx", index=False)

# Update INSIGHTS.md with serviceability section
# (append to existing INSIGHTS.md, do not overwrite NB07 content)
```

**New columns added (~17 total):**
`lat_r`, `lng_r`, `coord_precision`, `nearest_blinkit_km`, `nearest_swiggy_km`,
`nearest_zepto_km`, `nearest_known_darkstore_km`, `n_darkstores_3km`, `n_darkstores_5km`,
`n_brands_confirmed`, `blinkit_confirmed`, `swiggy_confirmed`, `zepto_confirmed`,
`brands_confirmed_list`, `city_known_darkstores`, `city_coverage_confidence`,
`city_blinkit_count`, `city_swiggy_count`, `city_zepto_count`,
`blinkit_zero_in_city`, `swiggy_zero_in_city`, `zepto_zero_in_city`,
`serviceability_state`, `serviceability_confidence`, `serviceability_reason`, `gtm_action`.

---

## Section 8 — What the current spec gets wrong (honest assessment)

| Spec claim | Reality | Fix |
|---|---|---|
| "presence confirms, absence lowers confidence" | Correct philosophy | Keep |
| Single `nearest_known_darkstore_km` | Fine as a number but not as a decision input without coord_precision awareness | Use precision-adjusted thresholds |
| `serviceability_state` collapses to 3 values | Loses per-brand signal — Chennai Confirmed looks same as Gurugram Confirmed | Add `n_brands_confirmed` + `brands_confirmed_list` |
| 3.5 km radius | Correct for locality-level coords; systematically wrong for pincode centroids | Adjust by `coord_precision` |
| `city_coverage_confidence` from tertiles | Sound approach | Keep, but add per-brand city counts too |
| Geocoding is already done (886/1001) | pgeocode centroids cause 83 Bangalore rows to share one coordinate — distances are artifacts | Coordinate refinement pass required |
| `Confirmed` = fast signal for PUSH-NOW | Yes for multi-brand; Zepto-only Confirmed in Chennai needs a caveat | Split into Confirmed-Multi and Confirmed-Single |

---

## Section 9 — Non-negotiables (from design spec, confirmed)

These requirements from the original spec are correct and must be preserved:

1. **Absence ≠ unserviceable.** Never. The `Unknown` state means unknown, not unreachable.
2. **Every value carries confidence.** `serviceability_confidence` is mandatory on every row.
3. **`city_coverage_confidence` is a proxy, not precision.** The notebook must print this and say so.
4. **~115 no-geo localities become `Unknown (no-geo)`.** Correct — do not invent coordinates for them.
5. **This is enrichment only.** The consumer product (RAG, dashboard, ML API) is a separate decision.

---

## Section 10 — Dependencies

```
# requirements-ml.txt additions (if not already present):
geopy          # Nominatim geocoding for coordinate refinement
```

Nominatim requires a valid user_agent string and respects 1 request/second. For 1,001 localities
the refinement pass takes 16–20 minutes. Cache to `coord_cache.json` to avoid re-running.

Alternatively, if network is restricted: skip coordinate refinement and add `coord_precision = "pincode"`
for all shared-coordinate localities, with a note in the notebook that distances are centroid-level.
The pipeline still runs; the Confirmed labels just carry more uncertainty.
