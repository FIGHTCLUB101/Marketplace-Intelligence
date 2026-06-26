"""Single source of truth for the GOAT Life consumer layer.

Canonical gtm_action values (exactly as NB08 / nb08lib.gtm_action produces them), their
map colours and human labels, and per-archetype activation-cost estimates grounded in
GOAT Life's *disclosed* economics. Every consumer product (pincode export, dashboard,
sequence engine) imports from here, so the data contract never drifts from the master store.

Verified against notebooks/artifacts/localities_master_serviceable.parquet on 2026-06-26.
"""

# --- Canonical gtm_action values (the 5 NB08 actually emits; NOT the rejected 15-cell scheme) ---
GTM_ACTIONS = [
    "PUSH-NOW",
    "SAMPLE + QC test",
    "SAMPLE (D2C / offline)",
    "D2C / OFFLINE - verify QC",
    "HOLD",
]

# Map colours for the dashboard (Product 2). Keys MUST equal the gtm_action values above.
GTM_COLORS = {
    "PUSH-NOW":                  "#059669",  # green  — GO + quick-commerce reachable
    "SAMPLE + QC test":          "#d97706",  # amber  — validate; QC can fulfil
    "SAMPLE (D2C / offline)":    "#EF9F27",  # amber-light — validate; no confirmed QC reach
    "D2C / OFFLINE - verify QC": "#2a78d6",  # blue   — high demand, unconfirmed reach
    "HOLD":                      "#888780",  # gray   — not yet
}
GTM_DEFAULT_COLOR = "#888780"

GTM_LABELS = {
    "PUSH-NOW":                  "Push now (Blinkit + ads)",
    "SAMPLE + QC test":          "Sample + QC test",
    "SAMPLE (D2C / offline)":    "Sample (D2C / offline)",
    "D2C / OFFLINE - verify QC": "D2C / offline (verify QC)",
    "HOLD":                      "Hold",
}

# --- Per-locality activation cost estimates (INR), grounded in GOAT Life's disclosed economics ---
# Rationale (replaces the invented numbers in BUILD_CONSUMER_LAYER.md):
#   - GOAT Life spends ~38% of revenue on marketing (knowledge base §8).
#   - The "Blinkit 30-Day Challenge" spent Rs 25,000 on a WHOLE-CITY guerrilla blitz
#     (street thela + Delhi-Metro tastings + "protein langars") -> 1,000 packets/day,
#     1.7M impressions, 700+ inbounds. That is the real cost of a city-level activation.
#   - Phase-1 GTM was 85-100 offline pop-ups run on minimal budget.
# A SINGLE-LOCALITY activation (one pop-up/sampling event + a geo-targeted ad burst on that
# locality's pincodes) is a fraction of the Rs 25k city blitz. Costs are tiered by archetype:
# premium/metro localities cost more (higher ad CPMs + pricier mall pop-up venues).
# These are PLANNING ESTIMATES anchored to disclosed spend, not vendor quotes.
ACTIVATION_COST = {
    "Premium · Metro":             20000,
    "Premium":                     18000,
    "Full-infra · Metro":          13000,
    "Amenity-rich · Metro":        13000,
    "Employer-dense · Metro":      12000,
    "Metro":                       11000,
    "Healthcare-rich · Full-infra":10000,
    "Well-connected":               9000,
    "Employer-dense":               9000,
    "Average / Mixed":              6000,
}
ACTIVATION_COST_DEFAULT = 10000

# Path to the source-of-truth master store (relative to repo root).
MASTER_PARQUET = "notebooks/artifacts/localities_master_serviceable.parquet"
