"""Merge competitor oats intelligence (Blinkit / Swiggy / Zepto xlsx) into the master parquet.

New columns added to localities_master_serviceable.parquet:
  blinkit_n_competitor_brands   -- distinct oats brands (not GOAT Life) in that locality on Blinkit
  blinkit_competitor_avg_price  -- avg selling price of those competitors (INR)
  blinkit_goat_present          -- 1 if GOAT Life is listed on Blinkit in that locality
  zepto_n_competitor_brands     -- same for Zepto
  zepto_competitor_avg_price    -- same for Zepto
  zepto_goat_present            -- same for Zepto
  price_advantage_blinkit       -- blinkit_competitor_avg_price minus GOAT Life's Rs.99
  is_white_space                -- True if no competitor brands found on Blinkit OR Zepto

Run:  python scripts/enrich_competitor_data.py
"""
import io
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "notebooks" / "artifacts" / "localities_master_serviceable.parquet"
GOAT_PRICE = 99  # GOAT Life's Blinkit selling price


def parse_price(s):
    """Parse price strings like 'Rs.399' or 'Rs.544' to float."""
    if pd.isna(s):
        return float("nan")
    nums = re.findall(r"\d+\.?\d*", str(s))
    return float(nums[-1]) if nums else float("nan")


def is_goat(name):
    return "goat life" in str(name).lower()


def locality_metrics(df, loc_col, brand_col, prefix):
    """Compute per-locality competitive metrics for one platform."""
    rows = []
    for loc, grp in df.groupby(loc_col):
        comp = grp[~grp["is_goat"]]
        goat = grp[grp["is_goat"]]
        avg_price = comp["price_num"].mean() if len(comp) > 0 else None
        avg_price_clean = round(float(avg_price), 1) if (avg_price is not None and not pd.isna(avg_price)) else None
        rows.append({
            "loc_key": loc,
            f"{prefix}_n_competitor_brands": int(comp[brand_col].nunique()),
            f"{prefix}_competitor_avg_price": avg_price_clean,
            f"{prefix}_goat_present": int(len(goat) > 0),
        })
    return pd.DataFrame(rows)


# Blinkit
print("Reading blinkit_oats_data.xlsx...")
bl = pd.read_excel(ROOT / "blinkit_oats_data.xlsx")
bl["price_num"] = bl["Selling Price"].apply(parse_price)
bl["is_goat"] = bl["Product Name"].apply(is_goat)
bl["loc_key"] = bl["Locality"].str.strip().str.lower()
bl_metrics = locality_metrics(bl, "loc_key", "Brand Searched", "blinkit")

# Swiggy
print("Reading swiggy_oats_data.xlsx...")
sw = pd.read_excel(ROOT / "swiggy_oats_data.xlsx")
sw["price_num"] = sw["Selling Price"].apply(parse_price)
sw["is_goat"] = sw["Product Name"].apply(is_goat)
sw["loc_key"] = sw["Locality"].str.strip().str.lower()
sw_metrics = locality_metrics(sw, "loc_key", "Brand Searched", "swiggy")

# Zepto — locality format is "Indiranagar, Bangalore", strip city suffix
print("Reading zepto_oats_data.xlsx...")
zt = pd.read_excel(ROOT / "zepto_oats_data.xlsx")
zt["price_num"] = zt["Selling Price"].apply(parse_price)
zt["is_goat"] = zt["Product Name"].apply(is_goat)
zt["loc_key"] = zt["Locality"].str.split(",").str[0].str.strip().str.lower()
zt_metrics = locality_metrics(zt, "loc_key", "Brand Searched", "zepto")

# Join to master
# Master AREA = "Indiranagar, Bangalore" — strip city suffix to match Blinkit/Zepto bare names
print("Joining to master parquet...")
master = pd.read_parquet(PARQUET)
master["loc_key"] = master["AREA"].str.split(",").str[0].str.strip().str.lower()

# Drop any existing competitive columns so re-runs are safe
drop_prefixes = ("blinkit_n_comp", "blinkit_comp", "blinkit_goat",
                 "swiggy_n_comp", "swiggy_comp", "swiggy_goat",
                 "zepto_n_comp", "zepto_comp", "zepto_goat",
                 "price_advantage", "is_white_space")
stale = [c for c in master.columns if c.startswith(drop_prefixes)]
master.drop(columns=stale, inplace=True, errors="ignore")

master = master.merge(bl_metrics, on="loc_key", how="left")
master = master.merge(sw_metrics, on="loc_key", how="left")
master = master.merge(zt_metrics, on="loc_key", how="left")

master["price_advantage_blinkit"] = (
    master["blinkit_competitor_avg_price"] - GOAT_PRICE
).round(1)

bl_matched = master["blinkit_n_competitor_brands"].notna()
zt_matched = master["zepto_n_competitor_brands"].notna()
master["is_white_space"] = (
    (bl_matched & (master["blinkit_n_competitor_brands"] == 0)) |
    (zt_matched & (master["zepto_n_competitor_brands"] == 0))
)

master.drop(columns=["loc_key"], inplace=True)
master.to_parquet(PARQUET, index=False)

# Report
push = master[master["gtm_action"] == "PUSH-NOW"]
matched_bl = int(master["blinkit_n_competitor_brands"].notna().sum())

print(f"\n{'='*55}")
print(f"Parquet enriched  : {len(master)} localities")
print(f"Blinkit coverage  : {matched_bl} localities matched")
print(f"\nPUSH-NOW localities ({len(push)} total):")
print(f"  GOAT on Blinkit : {int(push['blinkit_goat_present'].sum())}")
print(f"  GOAT on Zepto   : {int(push['zepto_goat_present'].sum())}")
print(f"  White space     : {int(push['is_white_space'].sum())} (no competitors on BL or Zepto)")
bl_adv = push["price_advantage_blinkit"].mean()
print(f"  Avg price adv.  : Rs.{bl_adv:.0f} cheaper than competitor avg on Blinkit")
print(f"\nAll localities:")
print(f"  White space     : {int(master['is_white_space'].sum())}")
all_adv = master["price_advantage_blinkit"].mean()
print(f"  Avg price adv.  : Rs.{all_adv:.0f}")
print(f"{'='*55}")
print("\nDone. Now run: python scripts/build_locality_data.py")
