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
        "is_metro_connected", "belt_id", "belt_size", "pareto_optimal", "hidden_gem_v2", "spillover_gem"]

geo = df[df["lat"].notna()][COLS].copy()
geo["color"] = geo["gtm_action"].map(contract.GTM_COLORS).fillna(contract.GTM_DEFAULT_COLOR)
for c in ["icp_score", "res_avg_buy_imputed", "nearest_known_darkstore_km", "employer_quality"]:
    geo[c] = geo[c].round(1)
for c in ["pareto_optimal", "hidden_gem_v2", "spillover_gem", "is_metro_connected",
          "blinkit_confirmed", "swiggy_confirmed", "zepto_confirmed", "price_is_imputed"]:
    geo[c] = geo[c].astype(bool)

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
