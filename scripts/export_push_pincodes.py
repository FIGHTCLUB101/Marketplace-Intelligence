"""Product 1 — Pincode export for ad geo-targeting.

Reads the master serviceable store and writes two CSVs ready for Meta Ads / Blinkit ad
geo-targeting, plus a plain pincode list:
  - push_now_pincodes.csv   : GO + Confirmed localities (order-in-10-minutes audiences)
  - sample_test_pincodes.csv: SAMPLE-FIRST + Confirmed localities (sampling-campaign geo)
  - push_now_pincodes.txt   : deduped 6-digit pincodes, one per row (Meta Ads upload)

Also validates that contract.py has not drifted from the live data (the reason we build
this first: it locks the schema before the bigger dashboard/sequence-engine builds).
"""
from pathlib import Path

import pandas as pd

import contract

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "exports"
OUT.mkdir(exist_ok=True)

df = pd.read_parquet(ROOT / contract.MASTER_PARQUET)

# --- Contract validation (fail loudly if the data and contract have drifted) ---
real_actions = set(df["gtm_action"].dropna().unique())
assert real_actions == set(contract.GTM_ACTIONS), (
    f"gtm_action drift! data={sorted(real_actions)} contract={contract.GTM_ACTIONS}")
assert set(contract.GTM_COLORS) == set(contract.GTM_ACTIONS), "GTM_COLORS keys != GTM_ACTIONS"
unknown_arch = set(df["archetype_ml"].dropna().unique()) - set(contract.ACTIVATION_COST)
print("Contract OK. Archetypes without an explicit activation cost (use default):",
      sorted(unknown_arch) or "none")

# --- PUSH-NOW: GO + Confirmed serviceability ---
push_cols = ["AREA", "ADDRESS", "PINCODE", "icp_score", "archetype_ml",
             "n_brands_confirmed", "brands_confirmed_list",
             "nearest_known_darkstore_km", "employer_quality", "lifecycle"]
push_now = (df[(df["icp_verdict"] == "GO")
               & (df["serviceability_state"] == "Confirmed")
               & df["PINCODE"].notna()]
            [push_cols].sort_values("icp_score", ascending=False))

# --- SAMPLE-FIRST + Confirmed: sampling-campaign targets ---
sample_cols = ["AREA", "ADDRESS", "PINCODE", "icp_score", "archetype_ml",
               "n_brands_confirmed", "brands_confirmed_list", "lifecycle"]
sample_test = (df[(df["icp_verdict"] == "SAMPLE-FIRST")
                  & (df["serviceability_state"] == "Confirmed")
                  & df["PINCODE"].notna()]
               [sample_cols].sort_values("icp_score", ascending=False))

push_now.to_csv(OUT / "push_now_pincodes.csv", index=False)
sample_test.to_csv(OUT / "sample_test_pincodes.csv", index=False)
# Meta Ads upload: deduped 6-digit pincodes, one per row
(OUT / "push_now_pincodes.txt").write_text(
    "\n".join(sorted(push_now["PINCODE"].dropna().unique())), encoding="utf-8")

print(f"\nPUSH-NOW localities: {len(push_now)} | unique pincodes: {push_now['PINCODE'].nunique()}")
print(f"SAMPLE-TEST localities: {len(sample_test)} | unique pincodes: {sample_test['PINCODE'].nunique()}")
print("\nPUSH-NOW by city:")
print(push_now.groupby("ADDRESS").agg(
    localities=("AREA", "count"),
    pincodes=("PINCODE", "nunique"),
    avg_icp=("icp_score", "mean"),
).round(1).sort_values("localities", ascending=False).to_string())
print(f"\nWrote -> {OUT.relative_to(ROOT)}/ (push_now_pincodes.csv, sample_test_pincodes.csv, push_now_pincodes.txt)")
