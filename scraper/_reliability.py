"""Shared reliability toolkit for the 4 oats-brand scrapers.

Fixes the crash pattern diagnosed during Sprint 1 planning: Chrome's
renderer runs out of memory after ~200 localities of sustained DOM-heavy
automation (repeated full-page reloads, driver.page_source pulls, blind
modal enumeration in set_location), crashing mid-locality with no
recovery -- which cascades into every remaining locality failing the
same way. This module adds: periodic driver recycling before memory
pressure reaches that point, detection of a dead session so the current
locality can be retried instead of the whole run silently degrading,
real CAPTCHA/block detection with a pause-and-wait loop (all 4 scrapers
previously had inconsistent or, for Zepto, entirely absent block
handling), and incremental xlsx saves that don't get slower as the run
accumulates rows.
"""
import random
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook

BLOCK_TITLE_KEYWORDS = ["captcha", "robot", "blocked", "verify"]
BLOCK_BODY_MARKERS = [
    "access denied",
    "unusual traffic",
    "attention required",
    "awswafintegration",
    "challenge-container",
    "are you human",
]

DEAD_SESSION_MARKERS = [
    "chrome not reachable",
    "invalid session id",
    "session deleted",
    "no such window",
    "disconnected",
]


def is_blocked(driver) -> bool:
    title = (driver.title or "").lower()
    if any(k in title for k in BLOCK_TITLE_KEYWORDS):
        return True
    body = (driver.page_source or "").lower()
    return any(m in body for m in BLOCK_BODY_MARKERS)


def wait_for_manual_unblock(driver, beep_fn, max_wait_s=180, poll_s=3) -> bool:
    if not is_blocked(driver):
        return True
    beep_fn()
    waited = 0.0
    while waited < max_wait_s:
        time.sleep(poll_s)
        waited += poll_s
        if not is_blocked(driver):
            return True
    return False


def jittered_sleep(base_s: float, jitter_s: float = 1.0) -> None:
    time.sleep(base_s + random.uniform(0, jitter_s))


def should_restart_driver(locality_index: int, restart_every: int = 25) -> bool:
    return locality_index > 0 and locality_index % restart_every == 0


def is_dead_session_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in DEAD_SESSION_MARKERS)


class IncrementalWorkbook:
    """One in-memory openpyxl workbook, appended to as rows come in and
    saved periodically -- replaces rewriting the whole xlsx file (or, for
    Zepto's old pattern, round-tripping it through disk) on every save
    point, which gets slower as the run accumulates rows."""

    def __init__(self, path: Path, columns: list[str]):
        self.path = Path(path)
        self.columns = columns
        if self.path.exists():
            self.wb = load_workbook(self.path)
            self.ws = self.wb.active
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.wb = Workbook()
            self.ws = self.wb.active
            self.ws.append(columns)

    def append_row(self, row: dict) -> None:
        self.ws.append([row.get(c) for c in self.columns])

    def save(self) -> None:
        self.wb.save(self.path)

    def done_keys(self, key_columns: list[str]) -> set[str]:
        idxs = [self.columns.index(c) for c in key_columns]
        keys = set()
        for row in self.ws.iter_rows(min_row=2, values_only=True):
            keys.add("|".join(str(row[i]) for i in idxs))
        return keys
