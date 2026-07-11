"""One-time backfill: loads every existing data file into the fresh database.

Run this once after Task 3's schema has been applied to a new database. Safe
to re-run (every sync function is idempotent/append-only), but re-running
will create duplicate scrape_runs/pipeline_runs entries for files already
loaded — intended for disaster recovery, not routine use.

NOTE: SCRAPE/shelf_history/2026-07-02.xlsx is byte-identical to
SCRAPE/blinkit_goatlife_data.xlsx (confirmed during design: same 332775
byte size, same timestamp) — it is NOT a separate data point and is
deliberately not loaded here to avoid duplicate rows.
"""
import argparse
from pathlib import Path

from apply_schema import apply_schema
from db_connection import get_connection
from sync_locality_scores import sync_locality_scores
from sync_shelf_snapshots import sync_shelf_snapshots

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PARQUET = ROOT / "notebooks" / "artifacts" / "localities_master_serviceable.parquet"
DEFAULT_XLSX = {
    "blinkit": ROOT / "blinkit_oats_data.xlsx",
    "swiggy": ROOT / "swiggy_oats_data.xlsx",
    "zepto": ROOT / "zepto_oats_data.xlsx",
    # No default for blinkit_goatlife — it currently lives outside this repo
    # at C:\Users\singh\Desktop\SCRAPE\blinkit_goatlife_data.xlsx. Pass its
    # path explicitly with --blinkit-goatlife-file.
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--blinkit-file", type=Path, default=DEFAULT_XLSX["blinkit"])
    parser.add_argument("--swiggy-file", type=Path, default=DEFAULT_XLSX["swiggy"])
    parser.add_argument("--zepto-file", type=Path, default=DEFAULT_XLSX["zepto"])
    parser.add_argument("--blinkit-goatlife-file", type=Path, default=None)
    args = parser.parse_args()

    apply_schema()
    conn = get_connection()
    try:
        print(f"Syncing locality scores from {args.parquet} ...")
        print(sync_locality_scores(args.parquet, conn))

        for platform, path in [
            ("blinkit", args.blinkit_file),
            ("swiggy", args.swiggy_file),
            ("zepto", args.zepto_file),
        ]:
            if path.exists():
                print(f"Syncing {platform} shelf snapshots from {path} ...")
                print(sync_shelf_snapshots(path, platform, conn))
            else:
                print(f"SKIP {platform}: {path} not found")

        if args.blinkit_goatlife_file and args.blinkit_goatlife_file.exists():
            print(f"Syncing blinkit_goatlife shelf snapshots from {args.blinkit_goatlife_file} ...")
            print(sync_shelf_snapshots(args.blinkit_goatlife_file, "blinkit_goatlife", conn))
        else:
            print("SKIP blinkit_goatlife: pass --blinkit-goatlife-file <path> to include it "
                  "(currently lives at C:\\Users\\singh\\Desktop\\SCRAPE\\blinkit_goatlife_data.xlsx)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
