"""Data-quality health report (P1.6): surfaces every scrape run's completeness
against its platform's baseline, so a silent under-capture becomes visible
before anyone trusts the weekly email.

assess_runs() is the pure core (testable without a DB); the CLI at the bottom
pulls the real runs, prints a table, and exits non-zero if any VALID run is
degraded — the alert hook.

    python health_report.py            # print the table
    python health_report.py --strict   # also exit 1 if a valid run is degraded
"""
from completeness_gate import PLACEHOLDER_NAMES, baseline_from_stats, evaluate


def assess_runs(runs, min_ratio=0.7):
    """runs: list of {run_id, platform, status, stats}. Evaluates each run
    against its own platform's baseline (max coverage over that platform's
    VALID runs only) and returns the same dicts with 'ok' and 'reasons' added."""
    by_platform = {}
    for r in runs:
        by_platform.setdefault(r["platform"], []).append(r)

    assessed = []
    for _platform, platform_runs in by_platform.items():
        valid_stats = [r["stats"] for r in platform_runs if r["status"] == "valid"]
        baseline = baseline_from_stats(valid_stats)
        for r in platform_runs:
            decision = evaluate(r["stats"], baseline, min_ratio=min_ratio)
            assessed.append({**r, "ok": decision["ok"], "reasons": decision["reasons"]})
    return assessed


def has_degraded_valid_run(assessed):
    """True if any run currently marked 'valid' fails its baseline — i.e. a
    bad run is still trusted and should be quarantined. Quarantined runs are
    ignored (already handled)."""
    return any(r["status"] == "valid" and not r["ok"] for r in assessed)


# --- DB-backed CLI -----------------------------------------------------------

def _fetch_runs(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT scrape_run_id, platform, status FROM scrape_runs ORDER BY platform, started_at")
        meta = cur.fetchall()
        runs = []
        ph = list(PLACEHOLDER_NAMES)
        for run_id, platform, status in meta:
            cur.execute(
                "SELECT count(DISTINCT city_raw), count(DISTINCT (city_raw, locality_raw)), "
                "count(DISTINCT brand_searched) FILTER (WHERE brand_searched IS NOT NULL AND brand_searched <> ''), "
                "count(*) FILTER (WHERE product_name IS NOT NULL AND product_name <> '' AND NOT (product_name = ANY(%s))) "
                "FROM shelf_snapshots WHERE scrape_run_id = %s",
                (ph, run_id),
            )
            cities, localities, brands, real_rows = cur.fetchone()
            runs.append({"run_id": run_id, "platform": platform, "status": status,
                         "stats": {"cities": cities, "localities": localities,
                                   "brands": brands, "real_rows": real_rows}})
    return runs


def main():
    import argparse
    import sys

    from db_connection import get_connection

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any run still marked 'valid' fails its baseline.")
    args = parser.parse_args()

    conn = get_connection()
    try:
        assessed = assess_runs(_fetch_runs(conn))
    finally:
        conn.close()

    assessed.sort(key=lambda r: (r["platform"], r["run_id"]))
    print(f"{'run':>5} {'platform':<18} {'status':<12} {'cities':>6} {'local':>6} "
          f"{'brands':>6} {'real_rows':>10}  verdict")
    for r in assessed:
        s = r["stats"]
        verdict = "OK" if r["ok"] else "DEGRADED — " + "; ".join(r["reasons"])
        print(f"{r['run_id']:>5} {r['platform']:<18} {r['status']:<12} "
              f"{s['cities']:>6} {s['localities']:>6} {s['brands']:>6} {s['real_rows']:>10}  {verdict}")

    if has_degraded_valid_run(assessed):
        print("\nALERT: at least one run still marked 'valid' is below its baseline — quarantine it.")
        if args.strict:
            sys.exit(1)
    else:
        print("\nAll valid runs clear their baseline.")


if __name__ == "__main__":
    main()
