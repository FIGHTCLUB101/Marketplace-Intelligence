import sys

import pytest

import run_weekly
from run_weekly import process_platform


class _FakeConn:
    def close(self):
        pass


def _platform(key="testplatform", mode="rank", xlsx=None):
    return {"key": key, "label": f"Label for {key}", "mode": mode, "xlsx": xlsx}


def test_process_platform_rank_mode_returns_ok_with_changes(tmp_path, monkeypatch):
    xlsx = tmp_path / "blinkit_goatlife_data.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 2})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (2, 1))

    def _fake_fetch_snapshot_rows(conn, scrape_run_id):
        if scrape_run_id == 1:
            return [{"city_raw": "Mumbai", "locality_raw": "Bandra", "product_name": "GOAT Life Mocha Marvel",
                      "rank": 1, "selling_price": 119.0, "is_goat": True}]
        return [{"city_raw": "Mumbai", "locality_raw": "Bandra", "product_name": "Prustlr Discovery Protein Oats",
                  "rank": 1, "selling_price": 449.0, "is_goat": False}]
    monkeypatch.setattr(run_weekly, "fetch_snapshot_rows", _fake_fetch_snapshot_rows)

    platform = _platform(key="blinkit_goatlife", mode="rank", xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "ok"
    assert len(result["changes"]["goat_displaced"]) == 1
    assert result["new_run_label"] == "2"
    assert result["old_run_label"] == "1"


def test_process_platform_oats_mode_returns_ok_with_changes(tmp_path, monkeypatch):
    xlsx = tmp_path / "blinkit_oats_data.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 2})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (2, 1))

    def _fake_fetch_snapshot_rows(conn, scrape_run_id):
        if scrape_run_id == 1:
            return [{"city_raw": "Bangalore", "locality_raw": "Indiranagar", "brand_searched": "Pintola Oats",
                      "product_name": "Pintola Rolled Oats", "selling_price": 249.0, "stock_left": None,
                      "is_goat": False}]
        return [{"city_raw": "Bangalore", "locality_raw": "Indiranagar", "brand_searched": "Pintola Oats",
                  "product_name": "Pintola Rolled Oats", "selling_price": 224.0, "stock_left": None,
                  "is_goat": False}]
    monkeypatch.setattr(run_weekly, "fetch_snapshot_rows", _fake_fetch_snapshot_rows)

    platform = _platform(key="blinkit", mode="oats", xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "ok"
    assert len(result["changes"]["price_changes"]) == 1
    assert result["changes"]["price_changes"][0]["change"] == -25.0


def test_process_platform_missing_file_returns_skipped(tmp_path, monkeypatch):
    def _fail_if_called(*a, **k):
        raise AssertionError("sync_shelf_snapshots should not be called for a missing file")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _fail_if_called)

    platform = _platform(xlsx=tmp_path / "does_not_exist.xlsx")
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "no data available"
    assert result["changes"] is None


def test_process_platform_permission_error_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "locked.xlsx"
    xlsx.write_text("placeholder")

    def _raise_permission_error(*a, **k):
        raise PermissionError("file is open in Excel")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _raise_permission_error)

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert "locked" in result["reason"]


def test_process_platform_sync_failure_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "bad.xlsx"
    xlsx.write_text("placeholder")

    def _raise_value_error(*a, **k):
        raise ValueError("malformed xlsx")
    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", _raise_value_error)

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "sync failed"


def test_process_platform_insufficient_history_returns_skipped(tmp_path, monkeypatch):
    xlsx = tmp_path / "fresh.xlsx"
    xlsx.write_text("placeholder")

    monkeypatch.setattr(run_weekly, "sync_shelf_snapshots", lambda *a, **k: {"rows_inserted": 5})
    monkeypatch.setattr(run_weekly, "fetch_latest_two_scrape_run_ids", lambda conn, key: (42, None))

    platform = _platform(xlsx=xlsx)
    result = process_platform(platform, _FakeConn(), drop_calendar=set())

    assert result["status"] == "skipped"
    assert result["reason"] == "not enough history yet"


def test_main_continues_when_one_platform_skipped_and_sends_no_email_on_dry_run(monkeypatch):
    ok_changes = {"goat_displaced": [{"city": "Mumbai", "locality": "Bandra", "rank": 1,
                                       "was": "GOAT Life Mocha Marvel", "now": "MISSING"}],
                  "goat_recovered": [], "new_products": [], "gone_products": [],
                  "rank_intrusions": [], "rank_moved": [], "price_changes": []}

    def _fake_process_platform(platform, conn, drop_calendar):
        if platform["key"] == "blinkit_goatlife":
            return {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "mode": "rank",
                    "status": "ok", "reason": None, "changes": ok_changes,
                    "new_run_label": "2", "old_run_label": "1"}
        return {"key": platform["key"], "label": platform["label"], "mode": platform["mode"],
                "status": "skipped", "reason": "no data available", "changes": None,
                "new_run_label": None, "old_run_label": None}

    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "xlsx": None, "mode": "rank"},
        {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "xlsx": None, "mode": "oats"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", _fake_process_platform)
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())

    def _fail_if_called(*a, **k):
        raise AssertionError("send_gmail should not be called during --dry-run")
    monkeypatch.setattr(run_weekly, "send_gmail", _fail_if_called)

    monkeypatch.setattr(sys, "argv", ["run_weekly.py", "--dry-run"])
    run_weekly.main()  # must not raise


def test_main_sends_combined_email_when_ok_results_exist(monkeypatch):
    ok_changes = {"new_products": [{"city": "Bangalore", "locality": "Indiranagar",
                                     "brand_searched": "Pintola Oats", "product": "Pintola Oats 500g",
                                     "is_goat": False}],
                  "gone_products": [], "price_changes": [], "stock_changes": []}

    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "xlsx": None, "mode": "oats"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", lambda platform, conn, drop_calendar: {
        "key": "blinkit", "label": "Blinkit Oats — Competitor Pricing", "mode": "oats",
        "status": "ok", "reason": None, "changes": ok_changes,
        "new_run_label": "2", "old_run_label": "1",
    })
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())

    sent = {}
    def _fake_send_gmail(subject, html_body, sender, app_password, recipients):
        sent["subject"] = subject
        sent["html_body"] = html_body
    monkeypatch.setattr(run_weekly, "send_gmail", _fake_send_gmail)

    monkeypatch.setenv("GMAIL_SENDER", "sender@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("GMAIL_RECIPIENTS", "a@example.com,b@example.com")
    monkeypatch.setattr(sys, "argv", ["run_weekly.py"])

    run_weekly.main()

    assert "1 changes detected" in sent["subject"]
    assert "Pintola Oats 500g" in sent["html_body"]


def test_main_exits_nonzero_when_all_platforms_skipped(monkeypatch):
    monkeypatch.setattr(run_weekly, "PLATFORMS", [
        {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)", "xlsx": None, "mode": "rank"},
    ])
    monkeypatch.setattr(run_weekly, "process_platform", lambda platform, conn, drop_calendar: {
        "key": platform["key"], "label": platform["label"], "mode": platform["mode"],
        "status": "skipped", "reason": "no data available", "changes": None,
        "new_run_label": None, "old_run_label": None,
    })
    monkeypatch.setattr(run_weekly, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(run_weekly, "fetch_drop_calendar", lambda conn: set())
    monkeypatch.setattr(sys, "argv", ["run_weekly.py"])

    with pytest.raises(SystemExit) as exc_info:
        run_weekly.main()
    assert exc_info.value.code == 1
