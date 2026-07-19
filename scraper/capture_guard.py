"""Per-(city, brand) capture guard — the scraper-side complement to the
completeness gate.

The gate (scripts/completeness_gate.py) is the last line of defence: it stops
a degraded run from reaching the database. This module is the first line: it
lets the scraper notice, mid-run, that a brand search came back
anomalously low against that brand's own established norm — the exact
signature of the 2026-07-17 failure, where brands that normally return
~40 cards silently returned 0-7 under parallel load — and retry it before
the bad number is ever written.

Pure functions only — no Selenium, no DB, no sleeping of its own (the retry
helper takes an injected `sleep`), so all of it is unit-testable without a
browser.
"""


def running_median(values):
    """Median of a list; None if empty."""
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def brand_norms(records, min_samples=3):
    """records: list of (city, brand, count). Returns {brand: median_count}
    for every brand with at least `min_samples` observations. Brands with too
    few samples are omitted — we don't judge a brand against a norm we haven't
    established yet."""
    by_brand = {}
    for _city, brand, count in records:
        by_brand.setdefault(brand, []).append(count)
    return {brand: running_median(counts)
            for brand, counts in by_brand.items() if len(counts) >= min_samples}


def should_retry_yield(count, norm, low_ratio=0.4):
    """True when a single (city, brand) result is worth re-scraping: we have an
    established norm for the brand and this observation fell below
    low_ratio * norm. No norm -> never retry (don't chase a guess)."""
    if norm is None:
        return False
    return count < low_ratio * norm


def scrape_with_yield_retry(scrape_fn, norm, low_ratio=0.4, max_attempts=3,
                            base_delay=2.0, sleep=None):
    """Calls scrape_fn() (returns a list of products); if the result is
    anomalously low against `norm`, backs off exponentially and retries, up to
    max_attempts total. Returns the BEST (largest) attempt seen — a retry that
    recovers the full card set wins, but if every attempt stays low we still
    keep the most complete one rather than the last. `sleep` is injected for
    testability."""
    if sleep is None:
        import time
        sleep = time.sleep

    best = scrape_fn()
    for attempt in range(1, max_attempts):
        if not should_retry_yield(len(best), norm, low_ratio):
            return best
        sleep(base_delay * (2 ** (attempt - 1)))
        candidate = scrape_fn()
        if len(candidate) > len(best):
            best = candidate
    return best


def pairs_below_norm(records, low_ratio=0.4, min_samples=3):
    """records: list of (city, brand, count) for a completed run. Returns the
    [(city, brand)] pairs whose count fell below low_ratio * the brand's norm —
    the straggler queue to re-scrape before the run is finalised. Brands
    without an established norm are never flagged."""
    norms = brand_norms(records, min_samples=min_samples)
    flagged = []
    for city, brand, count in records:
        norm = norms.get(brand)
        if norm is not None and count < low_ratio * norm:
            flagged.append((city, brand))
    return flagged
