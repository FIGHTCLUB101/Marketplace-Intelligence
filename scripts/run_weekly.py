"""Weekly orchestrator: sync each platform's latest scrape into Postgres,
diff it against the previous run, and email one combined report covering
all platforms.

Run this AFTER the relevant scraper(s) have finished (all local,
CAPTCHA-gated for blinkit_goatlife -- see Global Constraints in the Sprint 4
plan for why that stays unchanged). A platform's data file being missing,
locked, or having fewer than 2 scrape_runs does not block the others --
see process_platform(). Usage:
    python run_weekly.py [--dry-run]
"""
import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from alerts import build_combined_email_html, send_gmail
from db_connection import get_connection
from oats_changes import detect_price_availability_changes
from queries_shelf import fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_snapshot_rows
from shelf_changes import detect_changes
from sync_shelf_snapshots import sync_shelf_snapshots

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_OUTPUT_DIR = ROOT / "scraper" / "output"

PLATFORMS = [
    {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)",
     "xlsx": SCRAPER_OUTPUT_DIR / "blinkit_goatlife_data.xlsx", "mode": "rank"},
    {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "blinkit_oats_data.xlsx", "mode": "oats"},
    {"key": "swiggy", "label": "Swiggy Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "swiggy_oats_data.xlsx", "mode": "oats"},
    {"key": "zepto", "label": "Zepto Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUTPUT_DIR / "zepto_oats_data.xlsx", "mode": "oats"},
]


def process_platform(platform, conn, drop_calendar):
    """Syncs and diffs one platform. Never raises for expected per-platform
    conditions (missing file, locked file, insufficient history, sync
    failure) -- returns a status dict instead so one platform's problem
    never blocks the others.

    Returns {"key": str, "label": str, "mode": str, "status": "ok" | "skipped",
    "reason": str | None, "changes": dict | None,
    "new_run_label": str | None, "old_run_label": str | None}."""
    key, label, mode, xlsx = platform["key"], platform["label"], platform["mode"], platform["xlsx"]
    skipped = {"key": key, "label": label, "mode": mode, "status": "skipped",
               "changes": None, "new_run_label": None, "old_run_label": None}

    if not xlsx.exists():
        logging.warning(f"[{key}] Scraper output not found: {xlsx} — skipping this platform.")
        return {**skipped, "reason": "no data available"}

    try:
        sync_result = sync_shelf_snapshots(xlsx, key, conn)
        logging.info(f"[{key}] Synced: {sync_result}")
    except PermissionError:
        logging.warning(f"[{key}] {xlsx} is locked (open in Excel?) — skipping, try again next cycle.")
        return {**skipped, "reason": "file locked, try again next cycle"}
    except Exception:
        logging.exception(f"[{key}] Sync failed — skipping this platform.")
        return {**skipped, "reason": "sync failed"}

    newest_id, second_id = fetch_latest_two_scrape_run_ids(conn, key)
    if second_id is None:
        logging.warning(f"[{key}] Only one scrape_run exists — nothing to compare against yet.")
        return {**skipped, "reason": "not enough history yet"}

    rows_new = fetch_snapshot_rows(conn, newest_id)
    rows_old = fetch_snapshot_rows(conn, second_id)
    changes = (detect_changes(rows_new, rows_old, drop_calendar=drop_calendar) if mode == "rank"
               else detect_price_availability_changes(rows_new, rows_old))

    return {"key": key, "label": label, "mode": mode, "status": "ok", "reason": None,
            "changes": changes, "new_run_label": str(newest_id), "old_run_label": str(second_id)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip sending the email — print the subject/summary instead.")
    args = parser.parse_args()

    conn = get_connection()
    try:
        drop_calendar = fetch_drop_calendar(conn)
        results = [process_platform(p, conn, drop_calendar) for p in PLATFORMS]

        for r in results:
            if r["status"] == "skipped":
                logging.info(f"[{r['key']}] Skipped: {r['reason']}")
            else:
                logging.info(f"[{r['key']}] {sum(len(v) for v in r['changes'].values())} changes")

        ok_results = [r for r in results if r["status"] == "ok"]
        if not ok_results:
            logging.error("Every platform was skipped — nothing to report.")
            sys.exit(1)

        total = sum(sum(len(v) for v in r["changes"].values()) for r in ok_results)
        subject = (f"Weekly Competitive Report — {total} changes detected" if total > 0
                   else "Weekly Competitive Report — All Clear")

        if args.dry_run:
            logging.info(f"[--dry-run] Would send: {subject}")
            return

        sections = [{"label": r["label"], "mode": r["mode"], "changes": r["changes"]} for r in ok_results]
        html = build_combined_email_html(sections, date.today().isoformat(), "previous run")

        sender = os.environ["GMAIL_SENDER"]
        app_password = os.environ["GMAIL_APP_PASSWORD"]
        recipients = os.environ["GMAIL_RECIPIENTS"].split(",")
        send_gmail(subject, html, sender, app_password, recipients)
        logging.info(f"Sent: {subject}")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Weekly run failed")
        sys.exit(1)
