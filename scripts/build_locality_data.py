"""Product 2 data layer — master parquet -> web/data-localities.js + web/data-belts.js.

Single source of truth: reads localities_master_serviceable.parquet, validates against contract.py,
attaches GTM colors, keeps only geocoded localities, and writes sync-loadable JS globals.
"""
import json
from pathlib import Path

import pandas as pd

import contract

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
df = pd.read_parquet(ROOT / contract.MASTER_PARQUET)

assert set(df["gtm_action"].dropna().unique()) == set(contract.GTM_ACTIONS), "gtm_action drift!"

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

# Only keep COLS that actually exist in the parquet (competitive cols are optional)
COLS = [c for c in COLS if c in df.columns]

# Plot the NB08 Nominatim-REFINED coordinates (lat_r/lng_r), not the coarse pincode-centroid
# lat/lng — they fix ~596 localities whose original centroids were wrong (e.g. Kolkata +40km east).
src = df[df["lat_r"].notna()].copy()
geo = src[COLS].copy()
geo["lat"] = src["lat_r"].to_numpy()
geo["lng"] = src["lng_r"].to_numpy()
geo["color"] = geo["gtm_action"].map(contract.GTM_COLORS).fillna(contract.GTM_DEFAULT_COLOR)
for c in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km", "employer_quality",
          "blinkit_competitor_avg_price", "zepto_competitor_avg_price", "price_advantage_blinkit"]:
    if c in geo.columns:
        geo[c] = geo[c].round(1)
for c in ["pareto_optimal", "hidden_gem_v2", "spillover_gem", "is_metro_connected",
          "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed", "price_is_imputed"]:
    geo[c] = geo[c].astype(bool)
for c in ["blinkit_goat_present", "zepto_goat_present", "is_white_space"]:
    if c in geo.columns:
        geo[c] = geo[c].fillna(0).astype(bool)

records = geo.fillna("").to_dict("records")
(WEB / "data-localities.js").write_text(
    "window.LOCALITIES = " + json.dumps(records, ensure_ascii=False) + ";\n", encoding="utf-8")

# belts (>=3 members) for the belt view
bs = (df[df["belt_size"] >= 3].groupby(["belt_id", "ADDRESS"])
      .agg(size=("belt_size", "first"), avg_icp=("icp_score", "mean"),
           go_count=("icp_verdict", lambda x: int((x == "GO").sum())),
           confirmed_count=("serviceability_state", lambda x: int((x == "Confirmed").sum())),
           members=("AREA", lambda x: list(x)[:12]))
      .reset_index().sort_values("size", ascending=False))
bs["avg_icp"] = bs["avg_icp"].round(1)
(WEB / "data-belts.js").write_text(
    "window.BELTS = " + json.dumps(bs.to_dict("records"), ensure_ascii=False) + ";\n", encoding="utf-8")

print(f"localities (geocoded): {len(records)} | belts(>=3): {len(bs)}")
print("gtm distribution:", geo["gtm_action"].value_counts().to_dict())
