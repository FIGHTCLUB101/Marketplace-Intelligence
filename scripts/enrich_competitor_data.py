"""Merge competitor oats intelligence (Blinkit / Swiggy / Zepto xlsx) into the master parquet.

New columns added to localities_master_serviceable.parquet:
  blinkit_n_competitor_brands           -- distinct oats brands (not GOAT Life) in that locality on Blinkit
  blinkit_competitor_avg_price_per_100g -- avg Rs./100g of those competitors (pack-size normalized, see
                                            pack_pricing.py — a 25g sachet and a 1kg bag aren't comparable
                                            at face value)
  blinkit_goat_present                  -- 1 if GOAT Life is listed on Blinkit in that locality
  zepto_n_competitor_brands             -- same for Zepto
  zepto_competitor_avg_price_per_100g   -- same for Zepto
  zepto_goat_present                    -- same for Zepto
  price_advantage_blinkit_per_100g      -- blinkit_competitor_avg_price_per_100g minus GOAT Life's own
                                            Rs./100g on Blinkit (computed from GOAT's actual listed rows,
                                            not a fixed reference price — GOAT sells more than one pack size)
  is_white_space                        -- True if no competitor brands found on Blinkit OR Zepto

Run:  python scripts/enrich_competitor_data.py
"""
import io
import re
import sys
from pathlib import Path

import pandas as pd

from pack_pricing import goat_price_per_100g, parse_pack_size_grams, price_per_100g

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "notebooks" / "artifacts" / "localities_master_serviceable.parquet"


def parse_price(s):
    """Parse price strings like 'Rs.399' or 'Rs.544' to float."""
    if pd.isna(s):
        return float("nan")
    nums = re.findall(r"\d+\.?\d*", str(s))
    return float(nums[-1]) if nums else float("nan")


def is_goat(name):
    return "goat life" in str(name).lower()


def add_price_per_100g(df):
    """Adds a price_per_100g column, pack-size normalized (see pack_pricing.py)."""
    df["pack_size_grams"] = df["Pack Size"].apply(parse_pack_size_grams)
    df["price_per_100g"] = df.apply(
        lambda r: price_per_100g(r["price_num"], r["pack_size_grams"]), axis=1
    )
    return df


def locality_metrics(df, loc_col, brand_col, prefix):
    """Compute per-locality competitive metrics for one platform. Competitor
    prices are averaged on a Rs./100g basis (not raw selling price) so packs
    of very different sizes aren't compared at face value."""
    rows = []
    for loc, grp in df.groupby(loc_col):
        comp = grp[~grp["is_goat"]]
        goat = grp[grp["is_goat"]]
        avg_price = comp["price_per_100g"].mean() if len(comp) > 0 else None
        avg_price_clean = round(float(avg_price), 1) if (avg_price is not None and not pd.isna(avg_price)) else None
        rows.append({
            "loc_key": loc,
            f"{prefix}_n_competitor_brands": int(comp[brand_col].nunique()),
            f"{prefix}_competitor_avg_price_per_100g": avg_price_clean,
            f"{prefix}_goat_present": int(len(goat) > 0),
        })
    return pd.DataFrame(rows)


# Blinkit
print("Reading blinkit_oats_data.xlsx...")
bl = pd.read_excel(ROOT / "blinkit_oats_data.xlsx")
bl["price_num"] = bl["Selling Price"].apply(parse_price)
bl["is_goat"] = bl["Product Name"].apply(is_goat)
bl["loc_key"] = bl["Locality"].str.strip().str.lower()
bl = add_price_per_100g(bl)
bl_metrics = locality_metrics(bl, "loc_key", "Brand Searched", "blinkit")
goat_bl_price_per_100g = goat_price_per_100g(bl)

# Swiggy
print("Reading swiggy_oats_data.xlsx...")
sw = pd.read_excel(ROOT / "swiggy_oats_data.xlsx")
sw["price_num"] = sw["Selling Price"].apply(parse_price)
sw["is_goat"] = sw["Product Name"].apply(is_goat)
sw["loc_key"] = sw["Locality"].str.strip().str.lower()
sw = add_price_per_100g(sw)
sw_metrics = locality_metrics(sw, "loc_key", "Brand Searched", "swiggy")

# Zepto — locality format is "Indiranagar, Bangalore", strip city suffix
print("Reading zepto_oats_data.xlsx...")
zt = pd.read_excel(ROOT / "zepto_oats_data.xlsx")
zt["price_num"] = zt["Selling Price"].apply(parse_price)
zt["is_goat"] = zt["Product Name"].apply(is_goat)
zt["loc_key"] = zt["Locality"].str.split(",").str[0].str.strip().str.lower()
zt = add_price_per_100g(zt)
zt_metrics = locality_metrics(zt, "loc_key", "Brand Searched", "zepto")
goat_zt_price_per_100g = goat_price_per_100g(zt)

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

master["price_advantage_blinkit_per_100g"] = (
    master["blinkit_competitor_avg_price_per_100g"] - goat_bl_price_per_100g
).round(1) if goat_bl_price_per_100g is not None else None

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
def format_price_advantage(value):
    """Rs.X/100g cheaper|pricier framing for the console report -- avoids
    hardcoding "cheaper" regardless of sign (this ratio can and does go
    negative in real data, meaning GOAT is pricier per 100g, not cheaper),
    and avoids printing the literal text "nan" when no localities in this
    run matched the master parquet (mean of an all-NaN column)."""
    if pd.isna(value):
        return "no data (no localities in this run matched the master parquet)"
    return f"Rs.{abs(value):.1f}/100g {'cheaper' if value >= 0 else 'pricier'} than competitor avg"


print(f"Parquet enriched  : {len(master)} localities")
print(f"Blinkit coverage  : {matched_bl} localities matched")
print(f"GOAT Rs./100g     : Blinkit={goat_bl_price_per_100g}  Zepto={goat_zt_price_per_100g}")
print(f"\nPUSH-NOW localities ({len(push)} total):")
print(f"  GOAT on Blinkit : {int(push['blinkit_goat_present'].sum())}")
print(f"  GOAT on Zepto   : {int(push['zepto_goat_present'].sum())}")
print(f"  White space     : {int(push['is_white_space'].sum())} (no competitors on BL or Zepto)")
print(f"  Avg price adv.  : {format_price_advantage(push['price_advantage_blinkit_per_100g'].mean())}")
print(f"\nAll localities:")
print(f"  White space     : {int(master['is_white_space'].sum())}")
print(f"  Avg price adv.  : {format_price_advantage(master['price_advantage_blinkit_per_100g'].mean())}")
print(f"{'='*55}")
print("\nDone. Now run: python scripts/build_locality_data.py")
