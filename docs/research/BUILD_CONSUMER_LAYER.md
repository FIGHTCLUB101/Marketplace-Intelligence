# GOAT Life — Consumer Layer Build Spec
## What to build on top of `localities_master_serviceable.parquet`

> **For Claude Code.** This document specifies three products to build in sequence on top of the
> enriched locality master store (1,001 localities × ~139 features). Read all three before starting
> any of them — they share a data layer and the dashboard is the biggest, so sequence matters.

---

## Why these three, in this order

The master store answers three distinct questions for different people on different timelines:

| Question | Who asks it | When | Product |
|---|---|---|---|
| "Which pincodes should our ads target RIGHT NOW?" | Marketing team | Daily | Pincode export (Day 1) |
| "Show me the full map — where are we, where should we go?" | CEO, investors | Weekly | Where to Win v2 dashboard (Weeks 2–4) |
| "Given ₹X budget, what's the activation sequence for this city?" | Founder, growth | Monthly | Attack sequence engine (Month 2) |

The RAG and ML API are NOT in this build spec. They become valuable once real sales data flows
back and you can answer "why did Koramangala outperform?" — right now you don't have that.
Build the things that create decisions first.

---

## Product 1 — Pincode export (Day 1, ~2 hours)

### What it is

A Python script that reads the master store and outputs two CSVs ready for ad platform upload:

1. `push_now_pincodes.csv` — all PUSH-NOW localities, their pincodes, ICP score, confirmed brands
2. `sample_test_pincodes.csv` — all SAMPLE-QC-TEST localities, for sampling campaign geo-targeting

### Why it matters

The PUSH-NOW pincodes are localities where `icp_verdict = GO` AND `serviceability_state = Confirmed`.
These are people who can order from Blinkit/Zepto within 10 minutes of seeing an ad. Targeting
these pincodes with performance marketing is the most direct path from the ML pipeline to revenue.
A Meta Ads geographic target list is the only consumer that matters today.

### Build spec

```python
# scripts/export_push_pincodes.py
from pathlib import Path
import pandas as pd
import numpy as np

ART = Path("notebooks/artifacts")
df = pd.read_parquet(ART / "localities_master_serviceable.parquet")

# PUSH-NOW: GO + Confirmed (any serviceability_state that starts with Confirmed)
push_now = df[
    (df["icp_verdict"] == "GO") &
    (df["serviceability_state"].str.startswith("Confirmed")) &
    df["PINCODE"].notna()
].copy()

push_now_out = push_now[[
    "AREA", "ADDRESS", "PINCODE", "icp_score", "archetype_ml",
    "n_brands_confirmed", "brands_confirmed_list",
    "nearest_known_darkstore_km", "employer_quality", "lifecycle",
]].sort_values("icp_score", ascending=False)

# SAMPLE-FIRST + Confirmed → sampling campaign targets
sample_test = df[
    (df["icp_verdict"] == "SAMPLE-FIRST") &
    (df["serviceability_state"].str.startswith("Confirmed")) &
    df["PINCODE"].notna()
].copy()

sample_out = sample_test[[
    "AREA", "ADDRESS", "PINCODE", "icp_score", "archetype_ml",
    "n_brands_confirmed", "brands_confirmed_list", "lifecycle",
]].sort_values("icp_score", ascending=False)

push_now_out.to_csv("push_now_pincodes.csv", index=False)
sample_out.to_csv("sample_test_pincodes.csv", index=False)

print(f"PUSH-NOW localities: {len(push_now_out)}")
print(f"PUSH-NOW unique pincodes: {push_now_out['PINCODE'].nunique()}")
print(f"\nSAMPLE-TEST localities: {len(sample_out)}")
print(f"SAMPLE-TEST unique pincodes: {sample_out['PINCODE'].nunique()}")

# Summary by city
print("\nPUSH-NOW by city:")
print(push_now_out.groupby("ADDRESS").agg(
    localities=("AREA","count"),
    pincodes=("PINCODE","nunique"),
    avg_icp=("icp_score","mean"),
).round(1).sort_values("localities", ascending=False).to_string())
```

### Output format for Meta Ads

Meta Ads accepts Indian pincodes as "Postal code" geographic targets. The upload format is:
- Country: India
- Location type: Postal code
- Values: 6-digit pincode, one per row

Export the `PINCODE` column from `push_now_pincodes.csv` as a plain text list.

### Validation

Print the locality count and pincode count. Expected ranges based on simulation:
- PUSH-NOW localities: 80–100
- Unique PUSH-NOW pincodes: 50–75 (some pincodes cover multiple localities)
- Cities represented: at minimum Bangalore, Gurugram, New Delhi, Mumbai, Hyderabad

If any city has zero PUSH-NOW localities, check whether `serviceability_state` was correctly
populated for that city. Chennai and Pune may have fewer due to single-brand (Zepto-only) coverage.

---

## Product 2 — Where to Win v2 dashboard (Weeks 2–4)

### What it is

An extension of the existing darkstore v1 Vercel deployment. Add a second data layer: the 1,001
locality intelligence points on top of the existing 4,081 darkstore markers. The result is a
unified "ground truth" map of demand (localities) and supply (dark stores) for India.

### Architecture

```
web/
├── index.html                 ← existing shell, add tab 5 "Localities"
├── app.js                     ← add locality tab manager
├── locality-map.js            ← NEW: locality layer, belt view, profile panel
├── data-localities.js         ← NEW: pre-bundled locality data (~300KB)
└── data-markers.json          ← existing darkstore markers (unchanged)
```

Two-phase loading pattern (same as darkstore v1):
- Phase 1: `data-localities.js` loads sync → locality stats render instantly
- Phase 2: `data-markers.json` fetches async → darkstore markers appear

### Data preparation

Run this script before building the frontend. It generates the pre-bundled JS data file.

```python
# scripts/build_locality_data.py
import pandas as pd
import json
from pathlib import Path

df = pd.read_parquet("notebooks/artifacts/localities_master_serviceable.parquet")

# Select only what the frontend needs (keep bundle small)
FRONTEND_COLS = [
    "AREA", "ADDRESS", "PINCODE", "lat", "lng",
    "icp_score", "icp_verdict", "gtm_action",
    "archetype_ml", "lifecycle", "serviceability_state",
    "n_brands_confirmed", "brands_confirmed_list",
    "res_avg_buy_imputed", "price_is_imputed",
    "employer_quality", "primary_sector", "is_metro_connected",
    "belt_id", "belt_size", "pareto_optimal",
    "hidden_gem_v2", "spillover_gem",
    "nearest_known_darkstore_km", "blinkit_confirmed",
    "swiggy_confirmed", "zepto_confirmed",
]

# Only export geocoded localities (886/1001)
geo = df[df["lat"].notna()][FRONTEND_COLS].copy()

# Color coding by GTM action for the map
GTM_COLORS = {
    "PUSH-NOW-ALL-BRANDS":    "#1baf7a",   # green
    "PUSH-NOW-VERIFY-BRANDS": "#5DCAA5",   # teal
    "LIST-AND-TEST":          "#2a78d6",   # blue
    "SAMPLE-QC-TEST":         "#eda100",   # amber
    "SAMPLE-DIGITAL-FIRST":   "#EF9F27",   # amber-light
    "SAMPLE-OFFLINE":         "#B4B2A9",   # gray
    "D2C-OFFLINE-FIRST":      "#888780",   # gray
    "HOLD-MONITOR":           "#D3D1C7",   # light gray
    "HOLD":                   "#D3D1C7",   # light gray
    "REVIEW-MANUALLY":        "#E24B4A",   # red
}

geo["color"] = geo["gtm_action"].map(GTM_COLORS).fillna("#888780")

# Round floats for smaller JSON
for col in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km", "employer_quality"]:
    if col in geo.columns:
        geo[col] = geo[col].round(1)

records = geo.fillna("").to_dict("records")

# Write as JS module (sync-loadable, no fetch required)
js_content = f"export const LOCALITIES = {json.dumps(records, ensure_ascii=False)};"
Path("web/data-localities.js").write_text(js_content, encoding="utf-8")
print(f"Wrote {len(records)} localities to web/data-localities.js")

# Also write belt summary for the belt view
belt_summary = df.groupby(["belt_id", "ADDRESS"]).agg(
    size=("belt_id", "count"),
    avg_icp=("icp_score", "mean"),
    go_count=("icp_verdict", lambda x: (x=="GO").sum()),
    confirmed_count=("serviceability_state", lambda x: x.str.startswith("Confirmed").sum()),
    localities=("AREA", list),
).reset_index()
belt_summary["avg_icp"] = belt_summary["avg_icp"].round(1)
belt_summary = belt_summary[belt_summary["size"] >= 3]  # only meaningful belts

belts_js = f"export const BELTS = {json.dumps(belt_summary.to_dict('records'), ensure_ascii=False)};"
Path("web/data-belts.js").write_text(belts_js, encoding="utf-8")
print(f"Wrote {len(belt_summary)} belts to web/data-belts.js")
```

### `locality-map.js` — core implementation

```javascript
// web/locality-map.js
import { LOCALITIES } from './data-localities.js';
import { BELTS } from './data-belts.js';

const GTM_LABELS = {
  'PUSH-NOW-ALL-BRANDS':    'Push now',
  'PUSH-NOW-VERIFY-BRANDS': 'Push now (verify brands)',
  'LIST-AND-TEST':          'List and test',
  'SAMPLE-QC-TEST':         'Sample + QC test',
  'SAMPLE-DIGITAL-FIRST':   'Sample (digital first)',
  'SAMPLE-OFFLINE':         'Sample (offline)',
  'D2C-OFFLINE-FIRST':      'D2C / offline',
  'HOLD-MONITOR':           'Hold, monitor',
  'HOLD':                   'Hold',
};

let localityMarkers = [];
let beltPolygons = [];
let activeFilters = { city: 'all', verdict: 'all', serviceability: 'all', lifecycle: 'all' };

export function initLocalityLayer(map) {
  // Add locality points as a MapLibre GL source
  map.addSource('localities', {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: LOCALITIES.map(loc => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [loc.lng, loc.lat] },
        properties: loc,
      }))
    }
  });

  // Layer: locality dots
  map.addLayer({
    id: 'locality-circles',
    type: 'circle',
    source: 'localities',
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        8, 4, 12, 8, 14, 12
      ],
      'circle-color': ['get', 'color'],
      'circle-opacity': 0.85,
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
    }
  });

  // Click handler: show profile panel
  map.on('click', 'locality-circles', e => {
    const props = e.features[0].properties;
    showProfilePanel(props);
  });

  map.on('mouseenter', 'locality-circles', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'locality-circles', () => map.getCanvas().style.cursor = '');
}

function showProfilePanel(props) {
  const panel = document.getElementById('locality-panel');
  const icpColor = props.icp_verdict === 'GO' ? '#1baf7a' :
                   props.icp_verdict === 'SAMPLE-FIRST' ? '#eda100' : '#888780';

  panel.innerHTML = `
    <div style="padding: 16px;">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
        <div>
          <div style="font-size:15px; font-weight:500;">${props.AREA}</div>
          <div style="font-size:12px; color:#888780;">${props.ADDRESS} · PIN ${props.PINCODE || '—'}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:20px; font-weight:500; color:${icpColor};">${Math.round(props.icp_score)}</div>
          <div style="font-size:10px; color:#888780;">ICP score</div>
        </div>
      </div>
      <div style="background:#f1efe8; border-radius:6px; padding:8px 10px; margin-bottom:12px; font-size:13px; font-weight:500;">
        ${GTM_LABELS[props.gtm_action] || props.gtm_action}
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px;">
        <div><span style="color:#888780;">Verdict:</span> ${props.icp_verdict}</div>
        <div><span style="color:#888780;">Serviceability:</span> ${props.serviceability_state}</div>
        <div><span style="color:#888780;">Archetype:</span> ${props.archetype_ml}</div>
        <div><span style="color:#888780;">Lifecycle:</span> ${props.lifecycle || '—'}</div>
        <div><span style="color:#888780;">Brands confirmed:</span> ${props.n_brands_confirmed}/3</div>
        <div><span style="color:#888780;">Nearest store:</span> ${props.nearest_known_darkstore_km ? props.nearest_known_darkstore_km + 'km' : '—'}</div>
        <div><span style="color:#888780;">Sector:</span> ${props.primary_sector || '—'}</div>
        <div><span style="color:#888780;">Price:</span> ${props.res_avg_buy_imputed ? '₹' + Math.round(props.res_avg_buy_imputed).toLocaleString('en-IN') + '/sqft' : '—'}${props.price_is_imputed ? ' (est.)' : ''}</div>
        <div><span style="color:#888780;">Metro:</span> ${props.is_metro_connected ? 'Yes' : 'No'}</div>
        <div><span style="color:#888780;">Employer quality:</span> ${props.employer_quality ? Math.round(props.employer_quality) : '—'}</div>
      </div>
      ${props.pareto_optimal ? '<div style="margin-top:8px; font-size:11px; color:#185FA5; background:#E6F1FB; padding:5px 8px; border-radius:4px;">Pareto-optimal — strong on all dimensions</div>' : ''}
      ${props.hidden_gem_v2 ? '<div style="margin-top:4px; font-size:11px; color:#854F0B; background:#FAEEDA; padding:5px 8px; border-radius:4px;">Hidden gem — high ICP, under-priced</div>' : ''}
      ${props.spillover_gem ? '<div style="margin-top:4px; font-size:11px; color:#3B6D11; background:#EAF3DE; padding:5px 8px; border-radius:4px;">Spillover gem — cheaper than adjacent localities</div>' : ''}
    </div>
  `;
  panel.style.display = 'block';
}

// Belt view: highlight all localities in a belt when clicked
export function highlightBelt(beltId) {
  const beltLocalities = LOCALITIES.filter(l => l.belt_id === beltId);
  // Zoom to belt extent and highlight members
  const lngs = beltLocalities.map(l => l.lng);
  const lats = beltLocalities.map(l => l.lat);
  map.fitBounds([
    [Math.min(...lngs) - 0.05, Math.min(...lats) - 0.05],
    [Math.max(...lngs) + 0.05, Math.max(...lats) + 0.05]
  ], { padding: 40 });
}

// Filter controls
export function applyFilters(map, filters) {
  activeFilters = { ...activeFilters, ...filters };
  const filterExprs = ['all'];
  if (activeFilters.city !== 'all') filterExprs.push(['==', ['get', 'ADDRESS'], activeFilters.city]);
  if (activeFilters.verdict !== 'all') filterExprs.push(['==', ['get', 'icp_verdict'], activeFilters.verdict]);
  if (activeFilters.serviceability !== 'all') filterExprs.push(['in', activeFilters.serviceability, ['get', 'serviceability_state']]);
  if (activeFilters.lifecycle !== 'all') filterExprs.push(['==', ['get', 'lifecycle'], activeFilters.lifecycle]);
  map.setFilter('locality-circles', filterExprs.length > 1 ? filterExprs : null);
}
```

### Tab 5 HTML (add to index.html)

```html
<!-- Add to tab bar -->
<button class="tab-btn" data-tab="localities">Localities</button>

<!-- Localities tab content -->
<div id="tab-localities" class="tab-content" style="display:none;">
  <!-- Filter bar -->
  <div id="locality-filters" style="padding:12px; border-bottom:1px solid var(--border); display:flex; gap:8px; flex-wrap:wrap;">
    <select id="filter-city" onchange="applyLocFilter()">
      <option value="all">All cities</option>
      <option>Bangalore</option><option>Gurugram</option><option>New Delhi</option>
      <option>Mumbai</option><option>Hyderabad</option><option>Pune</option>
      <option>Chennai</option><option>Kolkata</option><option>Lucknow</option><option>Chandigarh</option>
    </select>
    <select id="filter-verdict" onchange="applyLocFilter()">
      <option value="all">All verdicts</option>
      <option>GO</option><option>SAMPLE-FIRST</option><option>WAIT</option>
    </select>
    <select id="filter-svc" onchange="applyLocFilter()">
      <option value="all">All serviceability</option>
      <option value="Confirmed">Confirmed</option>
      <option value="Likely">Likely</option>
      <option value="Unknown">Unknown</option>
    </select>
    <select id="filter-lifecycle" onchange="applyLocFilter()">
      <option value="all">All lifecycle</option>
      <option>established</option><option>emerging</option><option>nascent</option><option>saturated</option>
    </select>
    <button onclick="showBeltView()">Belt view</button>
  </div>

  <!-- Stats bar -->
  <div id="locality-stats" style="padding:8px 12px; font-size:12px; color:var(--text-muted); border-bottom:1px solid var(--border);">
    Showing <span id="stat-count">886</span> localities ·
    <span id="stat-push" style="color:#1baf7a;font-weight:500;">0 Push-now</span> ·
    <span id="stat-sample" style="color:#eda100;font-weight:500;">0 Sample-test</span>
  </div>
</div>

<!-- Locality profile panel (right sidebar) -->
<div id="locality-panel" style="display:none; position:absolute; right:12px; top:60px; width:280px; background:white; border:0.5px solid var(--border); border-radius:12px; z-index:100; max-height:80vh; overflow-y:auto;"></div>
```

### Legend

Add a locality-specific legend panel below the existing darkstore legend:

```html
<div id="locality-legend" style="margin-top:12px; font-size:11px;">
  <div style="font-weight:500; margin-bottom:6px; color:var(--text-secondary);">Localities</div>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;"><span style="width:10px;height:10px;border-radius:50%;background:#1baf7a;display:inline-block;"></span> Push now</div>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;"><span style="width:10px;height:10px;border-radius:50%;background:#2a78d6;display:inline-block;"></span> List and test</div>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;"><span style="width:10px;height:10px;border-radius:50%;background:#eda100;display:inline-block;"></span> Sample first</div>
  <div style="display:flex; align-items:center; gap:6px; margin-bottom:3px;"><span style="width:10px;height:10px;border-radius:50%;background:#888780;display:inline-block;"></span> Hold / offline</div>
</div>
```

---

## Product 3 — Attack sequence engine (Month 2)

### What it is

A standalone web tool (or a new tab in the dashboard) that takes a city + platform + budget as
input and generates a week-by-week activation plan. Not a visualisation — an action document.

### The core logic

The lifecycle stage + ICP score + serviceability state define natural activation waves:

```
Wave 1 (Week 1-2):  GO + Confirmed + established     → proven demand, infrastructure ready
Wave 2 (Week 3-4):  GO + Confirmed + emerging         → capture before competitors
Wave 3 (Month 2):   GO + Likely + (established OR emerging)  → expand, lower confidence
Wave 4 (Month 3+):  SAMPLE-FIRST + Confirmed + established   → test adjacent demand
Watch list:         spillover_gems + hidden_gem_v2    → monitor for reclassification
```

### Build spec

```python
# scripts/attack_sequence.py

import pandas as pd
import numpy as np
from pathlib import Path

ART = Path("notebooks/artifacts")

def generate_attack_sequence(city: str, platform: str, monthly_budget_inr: float,
                              df: pd.DataFrame = None) -> dict:
    """
    Generate a wave-by-wave activation sequence for a city.

    platform: 'blinkit' | 'swiggy' | 'zepto' | 'all'
    monthly_budget_inr: total activation budget in rupees
    """
    if df is None:
        df = pd.read_parquet(ART / "localities_master_serviceable.parquet")

    city_df = df[df["ADDRESS"] == city].copy()

    # Filter by platform serviceability
    if platform != "all":
        city_df = city_df[city_df[f"{platform}_confirmed"] == True]

    # Wave assignment
    def assign_wave(row):
        verdict = row.get("icp_verdict", "")
        svc = str(row.get("serviceability_state", ""))
        lifecycle = str(row.get("lifecycle", ""))

        if verdict == "GO" and svc.startswith("Confirmed") and lifecycle == "established":
            return 1
        if verdict == "GO" and svc.startswith("Confirmed") and lifecycle in ("emerging", "nascent"):
            return 2
        if verdict == "GO" and svc == "Likely":
            return 3
        if verdict == "SAMPLE-FIRST" and svc.startswith("Confirmed") and lifecycle == "established":
            return 4
        if row.get("spillover_gem") or row.get("hidden_gem_v2"):
            return 5  # watch list
        return 6  # hold

    city_df["wave"] = city_df.apply(assign_wave, axis=1)

    # Sort within each wave by ICP score
    city_df = city_df.sort_values(["wave", "icp_score"], ascending=[True, False])

    # Budget allocation (rough: each locality activation = ₹5,000-15,000 depending on archetype)
    ACTIVATION_COST = {
        "Premium · Metro": 15000, "Full-infra · Metro": 12000,
        "Amenity-rich · Metro": 10000, "Employer-dense · Metro": 10000,
        "Premium": 12000, "Metro": 8000, "Well-connected": 7000,
        "Average / Mixed": 6000, "Employer-dense": 7000,
        "Healthcare-rich · Full-infra": 8000,
    }
    city_df["est_activation_cost"] = city_df["archetype_ml"].map(ACTIVATION_COST).fillna(8000)

    waves = {}
    for wave_num in [1, 2, 3, 4, 5]:
        wave_localities = city_df[city_df["wave"] == wave_num]
        if len(wave_localities) == 0:
            continue

        waves[wave_num] = {
            "localities": wave_localities[[
                "AREA", "icp_score", "archetype_ml", "lifecycle",
                "serviceability_state", "n_brands_confirmed", "brands_confirmed_list",
                "nearest_known_darkstore_km", "est_activation_cost",
                "res_avg_buy_imputed", "employer_quality",
            ]].to_dict("records"),
            "total_localities": len(wave_localities),
            "est_total_cost": int(wave_localities["est_activation_cost"].sum()),
            "avg_icp": round(wave_localities["icp_score"].mean(), 1),
        }

    # Fit within budget: allocate budget across waves sequentially
    remaining_budget = monthly_budget_inr
    plan = {"city": city, "platform": platform, "budget": monthly_budget_inr, "waves": {}}
    for wave_num, wave_data in waves.items():
        affordable = []
        wave_cost = 0
        for loc in wave_data["localities"]:
            if wave_cost + loc["est_activation_cost"] <= remaining_budget:
                affordable.append(loc)
                wave_cost += loc["est_activation_cost"]
        if affordable:
            plan["waves"][wave_num] = {
                **wave_data,
                "affordable_localities": affordable,
                "wave_cost": int(wave_cost),
            }
            remaining_budget -= wave_cost

    return plan

def print_plan(plan: dict):
    WAVE_NAMES = {
        1: "Wave 1 — Confirmed GO, established (highest conviction)",
        2: "Wave 2 — Confirmed GO, emerging (capture early)",
        3: "Wave 3 — Likely GO (expand with lower confidence)",
        4: "Wave 4 — Confirmed SAMPLE-FIRST (test adjacent demand)",
        5: "Watch list — hidden gems and spillover candidates",
    }
    print(f"\nATTACK SEQUENCE: {plan['city']} | {plan['platform']} | ₹{plan['budget']:,.0f} budget")
    print("=" * 70)
    for wave_num, wave in plan["waves"].items():
        print(f"\n{WAVE_NAMES[wave_num]}")
        print(f"  {len(wave['affordable_localities'])} localities | est. cost ₹{wave['wave_cost']:,} | avg ICP {wave['avg_icp']}")
        for loc in wave["affordable_localities"][:8]:
            print(f"  · {loc['AREA'][:40]:40s} | ICP {loc['icp_score']:.0f} | {loc['archetype_ml']}")
        if len(wave["affordable_localities"]) > 8:
            print(f"    + {len(wave['affordable_localities'])-8} more")

# Usage
if __name__ == "__main__":
    plan = generate_attack_sequence(
        city="Bangalore",
        platform="all",
        monthly_budget_inr=500_000,
    )
    print_plan(plan)
```

### Web interface (simple HTML form)

Build this as a new page `web/sequence.html` or add as tab 6 in the dashboard.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <title>GOAT Life — Attack Sequence Planner</title>
  <meta charset="utf-8">
</head>
<body>
  <h1 style="font-size:18px; font-weight:500;">Attack sequence planner</h1>

  <div style="display:flex; gap:12px; margin-bottom:1.5rem;">
    <select id="sel-city">
      <option>Bangalore</option><option>Gurugram</option><option>New Delhi</option>
      <option>Mumbai</option><option>Hyderabad</option><option>Pune</option>
      <option>Chennai</option><option>Kolkata</option>
    </select>
    <select id="sel-platform">
      <option value="all">All platforms</option>
      <option value="blinkit">Blinkit only</option>
      <option value="swiggy">Swiggy only</option>
      <option value="zepto">Zepto only</option>
    </select>
    <input type="number" id="inp-budget" value="500000" placeholder="Monthly budget (₹)" style="width:180px;">
    <button onclick="generatePlan()">Generate sequence</button>
  </div>

  <div id="plan-output"></div>

  <script type="module">
    import { LOCALITIES } from './data-localities.js';

    window.generatePlan = function() {
      const city = document.getElementById('sel-city').value;
      const platform = document.getElementById('sel-platform').value;
      const budget = parseInt(document.getElementById('inp-budget').value);

      const WAVE_RULES = [
        { wave: 1, label: 'Wave 1 — Confirmed GO, established', filter: l =>
          l.icp_verdict === 'GO' && l.serviceability_state?.startsWith('Confirmed') && l.lifecycle === 'established' },
        { wave: 2, label: 'Wave 2 — Confirmed GO, emerging', filter: l =>
          l.icp_verdict === 'GO' && l.serviceability_state?.startsWith('Confirmed') && ['emerging','nascent'].includes(l.lifecycle) },
        { wave: 3, label: 'Wave 3 — Likely GO', filter: l =>
          l.icp_verdict === 'GO' && l.serviceability_state === 'Likely' },
        { wave: 4, label: 'Wave 4 — Confirmed SAMPLE-FIRST', filter: l =>
          l.icp_verdict === 'SAMPLE-FIRST' && l.serviceability_state?.startsWith('Confirmed') && l.lifecycle === 'established' },
        { wave: 5, label: 'Watch list — hidden and spillover gems', filter: l =>
          l.hidden_gem_v2 || l.spillover_gem },
      ];

      const city_locs = LOCALITIES.filter(l =>
        l.ADDRESS === city &&
        (platform === 'all' || l[`${platform}_confirmed`])
      );

      let remaining = budget;
      const output = document.getElementById('plan-output');
      output.innerHTML = '';

      WAVE_RULES.forEach(({ label, filter }) => {
        const wave_locs = city_locs.filter(filter).sort((a, b) => b.icp_score - a.icp_score);
        if (!wave_locs.length) return;

        const waveDiv = document.createElement('div');
        waveDiv.style.cssText = 'margin-bottom:1.5rem; padding:16px; background:#f9f9f8; border-radius:8px; border:0.5px solid #e1e0d9;';
        waveDiv.innerHTML = `
          <div style="font-size:14px; font-weight:500; margin-bottom:8px;">${label}</div>
          <div style="font-size:12px; color:#898781; margin-bottom:10px;">${wave_locs.length} localities · avg ICP ${(wave_locs.reduce((s,l)=>s+l.icp_score,0)/wave_locs.length).toFixed(1)}</div>
          ${wave_locs.slice(0,6).map(l => `
            <div style="display:flex; justify-content:space-between; font-size:12px; padding:4px 0; border-bottom:0.5px solid #e1e0d9;">
              <span>${l.AREA}</span>
              <span style="color:#888780;">ICP ${Math.round(l.icp_score)} · ${l.archetype_ml}</span>
            </div>
          `).join('')}
          ${wave_locs.length > 6 ? `<div style="font-size:11px;color:#898781;margin-top:4px;">+ ${wave_locs.length-6} more</div>` : ''}
        `;
        output.appendChild(waveDiv);
      });
    };
  </script>
</body>
</html>
```

---

## What NOT to build yet

### RAG / conversational AI
Valuable but not yet. The master store answers static "where to go" questions well. The RAG's
unique value is "why did X outperform?" — that requires real sales data flowing back from the
platforms. Without it, the RAG will answer the same questions the dashboard answers, just more
slowly and with higher hallucination risk on specific numbers.

### ML API
Build this as a shared data layer once the dashboard and sequence engine are scoped. Do not
build it as a standalone product — it has no user interface and no direct decision value without
a consumer on top of it. When you build it, the surface is: `/score`, `/lookalike`, `/belt/{id}`,
`/city/{city}/summary`. Keep it read-only.

### Slack weekly digest
Easy to build (2 days) but has a fundamental problem: without new data arriving weekly, the digest
repeats the same insights every Monday. Build it only after you've established a data refresh
cadence (new darkstore scrape, updated Magicbricks data, or real sales data). Before that it's
noise, not signal.

---

## Shared data contract

All three products read from the same file. Never duplicate or transform the data into a format
that can drift from the master store.

```
notebooks/artifacts/localities_master_serviceable.parquet  ← source of truth
web/data-localities.js                                      ← frontend bundle (built, not edited)
web/data-belts.js                                          ← belt summary (built, not edited)
push_now_pincodes.csv                                      ← ad export (regenerated on demand)
sample_test_pincodes.csv                                   ← sampling export (regenerated on demand)
```

When NB08 produces a new `localities_master_serviceable.parquet`, run `build_locality_data.py`
to regenerate the frontend bundles. The dashboard reflects the update after the next Vercel deploy.

---

## Dependencies

No new dependencies for Products 1 and 2. Product 3 (attack sequence engine) is pure frontend JS
when implemented as a browser tool; the Python version uses only the existing `pandas`/`pyarrow` stack.
