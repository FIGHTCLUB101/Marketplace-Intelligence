"""Completeness gate: decides whether a scrape run is complete enough to be
trusted as a source of truth, BEFORE it is allowed to drive week-over-week
comparisons.

The failure this exists to stop (2026-07-17 production data, run 424): a
scrape can finish without crashing yet capture only ~18% of the shelf — 2 of
10 cities missing, 2 of 10 brands returning zero, the rest at 14-33% of their
normal product count. The reliability toolkit catches crashes and CAPTCHAs;
nothing caught this silent under-capture, so a degraded run became the
"newest" run and poisoned the diff with tens of thousands of phantom
"delisted" events.

Pure functions only — no DB import here. run_stats() summarizes a run's
snapshot rows; baseline_from_stats() derives the bar from prior valid runs;
evaluate() compares the two and returns a pass/fail decision with reasons.
"""

PLACEHOLDER_NAMES = ("N/A", "Not Available", "Location Error", "Not Serviceable")
DIMENSIONS = ("cities", "localities", "brands", "real_rows")


def run_stats(rows):
    """rows: list of snapshot dicts (the shape build_snapshot_rows produces).
    Returns coverage stats: distinct cities, distinct (city, locality)
    localities, distinct non-empty brand_searched values, and real_rows
    (rows whose product_name is a genuine listing, not a placeholder)."""
    cities, localities, brands = set(), set(), set()
    real_rows = 0
    for r in rows:
        city, locality = r.get("city_raw"), r.get("locality_raw")
        cities.add(city)
        localities.add((city, locality))
        brand = r.get("brand_searched")
        if brand:
            brands.add(brand)
        name = r.get("product_name")
        if name and name not in PLACEHOLDER_NAMES:
            real_rows += 1
    return {"cities": len(cities), "localities": len(localities),
            "brands": len(brands), "real_rows": real_rows}


def baseline_from_stats(prior_stats):
    """prior_stats: list of run_stats dicts from prior VALID runs of the same
    platform. Returns the per-dimension max (the healthiest run we've seen is
    the bar — a good scrape should roughly match our best, not an average
    dragged down by earlier bad runs). Empty list -> None (no baseline yet)."""
    if not prior_stats:
        return None
    return {dim: max(s[dim] for s in prior_stats) for dim in DIMENSIONS}


def evaluate(candidate_stats, baseline, min_ratio=0.7):
    """Returns {"ok": bool, "reasons": [str], "ratios": {dim: float}}.

    A run passes if every dimension is at least `min_ratio` of the baseline.
    baseline None (the platform's first run) always passes — there is nothing
    to compare against yet. A baseline dimension of 0 is skipped (no divide,
    no spurious failure) — e.g. the goatlife rank tracker has no meaningful
    brand_searched spread."""
    if baseline is None:
        return {"ok": True, "reasons": [], "ratios": {}}

    reasons, ratios = [], {}
    for dim in DIMENSIONS:
        base = baseline[dim]
        if base <= 0:
            continue
        ratio = candidate_stats[dim] / base
        ratios[dim] = ratio
        if ratio < min_ratio:
            reasons.append(
                f"{dim}: {candidate_stats[dim]} vs baseline {base} "
                f"({ratio:.0%} < {min_ratio:.0%} required)"
            )
    return {"ok": not reasons, "reasons": reasons, "ratios": ratios}
