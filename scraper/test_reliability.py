import time

import pytest
from openpyxl import load_workbook

from _reliability import (
    IncrementalWorkbook,
    is_blocked,
    is_dead_session_error,
    jittered_sleep,
    should_restart_driver,
    wait_for_manual_unblock,
)


class FakeDriver:
    def __init__(self, title="GOAT Life Oats", body="normal page content"):
        self.title = title
        self._body = body

    @property
    def page_source(self):
        return self._body


def test_is_blocked_detects_title_keywords():
    assert is_blocked(FakeDriver(title="Please solve this CAPTCHA")) is True
    assert is_blocked(FakeDriver(title="Robot check")) is True
    assert is_blocked(FakeDriver(title="Normal Product Page")) is False


def test_is_blocked_detects_body_markers():
    assert is_blocked(FakeDriver(title="Blinkit", body="<div>Access Denied</div>")) is True
    assert is_blocked(FakeDriver(title="Blinkit", body="AwsWafIntegration challenge")) is True
    assert is_blocked(FakeDriver(title="Blinkit", body="<div>Yoga Bar Oats ₹399</div>")) is False


def test_wait_for_manual_unblock_returns_true_immediately_if_not_blocked():
    driver = FakeDriver(title="Normal page")
    beeped = []
    assert wait_for_manual_unblock(driver, beep_fn=lambda: beeped.append(1), poll_s=0.01) is True
    assert beeped == []


def test_wait_for_manual_unblock_clears_after_driver_state_changes():
    driver = FakeDriver(title="CAPTCHA")
    beeped = []

    def unblock_after_beep():
        beeped.append(1)
        driver.title = "Normal page"

    assert wait_for_manual_unblock(driver, beep_fn=unblock_after_beep, poll_s=0.01, max_wait_s=1) is True
    assert beeped == [1]


def test_wait_for_manual_unblock_gives_up_after_max_wait():
    driver = FakeDriver(title="CAPTCHA")
    result = wait_for_manual_unblock(driver, beep_fn=lambda: None, poll_s=0.01, max_wait_s=0.05)
    assert result is False


def test_jittered_sleep_sleeps_at_least_base_duration():
    start = time.monotonic()
    jittered_sleep(0.05, jitter_s=0.05)
    assert time.monotonic() - start >= 0.05


def test_should_restart_driver_fires_every_n_localities():
    assert should_restart_driver(0, restart_every=25) is False
    assert should_restart_driver(24, restart_every=25) is False
    assert should_restart_driver(25, restart_every=25) is True
    assert should_restart_driver(50, restart_every=25) is True
    assert should_restart_driver(26, restart_every=25) is False


def test_is_dead_session_error_matches_known_messages():
    assert is_dead_session_error(Exception("chrome not reachable")) is True
    assert is_dead_session_error(Exception("invalid session id")) is True
    assert is_dead_session_error(Exception("session deleted because of page crash")) is True
    assert is_dead_session_error(Exception("element not found")) is False


def test_incremental_workbook_appends_and_saves(tmp_path):
    path = tmp_path / "out.xlsx"
    wb = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    wb.append_row({"City": "Bangalore", "Locality": "Indiranagar", "Price": 99})
    wb.append_row({"City": "Delhi", "Locality": "Saket", "Price": 119})
    wb.save()

    reloaded = load_workbook(path)
    ws = reloaded.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("City", "Locality", "Price")
    assert rows[1] == ("Bangalore", "Indiranagar", 99)
    assert rows[2] == ("Delhi", "Saket", 119)


def test_incremental_workbook_resumes_from_existing_file(tmp_path):
    path = tmp_path / "out.xlsx"
    wb1 = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    wb1.append_row({"City": "Bangalore", "Locality": "Indiranagar", "Price": 99})
    wb1.save()

    wb2 = IncrementalWorkbook(path, columns=["City", "Locality", "Price"])
    keys = wb2.done_keys(["City", "Locality"])
    assert keys == {"Bangalore|Indiranagar"}

    wb2.append_row({"City": "Delhi", "Locality": "Saket", "Price": 119})
    wb2.save()

    reloaded = load_workbook(path)
    rows = list(reloaded.active.iter_rows(values_only=True))
    assert len(rows) == 3  # header + 2 data rows
