"""Weekly orchestrator: sync the latest GOAT Life Blinkit scrape into
Postgres, diff it against the previous run, and email the result.

Run this AFTER scraper/blinkit_goatlife.py has finished (still local,
CAPTCHA-gated — see Global Constraints in the Sprint 4 plan for why that
stays unchanged). Usage:
    python run_weekly.py [--dry-run]
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from alerts import build_email_html, send_gmail
from db_connection import get_connection
from queries_shelf import fetch_drop_calendar, fetch_latest_two_scrape_run_ids, fetch_snapshot_rows
from shelf_changes import detect_changes, goat_gone_unique
from sync_shelf_snapshots import sync_shelf_snapshots

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_OUTPUT = ROOT / "scraper" / "output" / "blinkit_goatlife_data.xlsx"
PLATFORM = "blinkit_goatlife"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Skip sending the email — print the subject/severity instead.")
    args = parser.parse_args()

    if not SCRAPER_OUTPUT.exists():
        logging.error(f"Scraper output not found: {SCRAPER_OUTPUT}. Run scraper/blinkit_goatlife.py first.")
        sys.exit(1)

    conn = get_connection()
    try:
        logging.info(f"Syncing {SCRAPER_OUTPUT} into shelf_snapshots...")
        sync_result = sync_shelf_snapshots(SCRAPER_OUTPUT, PLATFORM, conn)
        logging.info(f"  {sync_result}")

        newest_id, second_id = fetch_latest_two_scrape_run_ids(conn, PLATFORM)
        if second_id is None:
            logging.warning("Only one scrape_run exists for this platform — nothing to compare against yet. "
                             "Run the scraper again next week to get a real diff.")
            return

        rows_new = fetch_snapshot_rows(conn, newest_id)
        rows_old = fetch_snapshot_rows(conn, second_id)
        drop_calendar = fetch_drop_calendar(conn)
        changes = detect_changes(rows_new, rows_old, drop_calendar=drop_calendar)

        logging.info(f"  GOAT displaced   : {len(changes['goat_displaced'])}")
        logging.info(f"  Rank intrusions  : {len(changes['rank_intrusions'])}")
        logging.info(f"  Price changes    : {len(changes['price_changes'])}")

        total = len(changes["goat_displaced"]) + len(changes["rank_intrusions"]) + len(goat_gone_unique(changes))
        subject = (f"GOAT Life Shelf Alert — {total} changes detected" if total > 0
                   else "GOAT Life Shelf Monitor — All Clear")

        if args.dry_run:
            logging.info(f"[--dry-run] Would send: {subject}")
            return

        html = build_email_html(changes, str(newest_id), str(second_id))
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
