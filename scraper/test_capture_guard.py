from capture_guard import (
    running_median,
    brand_norms,
    should_retry_yield,
    scrape_with_yield_retry,
    pairs_below_norm,
)


def test_running_median_odd_and_even():
    assert running_median([40, 10, 30]) == 30
    assert running_median([10, 20, 30, 40]) == 25
    assert running_median([]) is None


def test_brand_norms_needs_min_samples():
    records = [
        ("Mumbai", "Pintola", 40), ("Delhi", "Pintola", 42), ("Pune", "Pintola", 38),
        ("Mumbai", "Quaker", 30),  # only 1 sample -> no norm
    ]
    norms = brand_norms(records, min_samples=3)
    assert norms["Pintola"] == 40
    assert "Quaker" not in norms


def test_should_retry_yield_true_when_far_below_norm():
    # 2 cards where the brand normally returns ~40 -> retry.
    assert should_retry_yield(count=2, norm=40, low_ratio=0.4) is True


def test_should_retry_yield_false_when_healthy():
    assert should_retry_yield(count=38, norm=40, low_ratio=0.4) is False


def test_should_retry_yield_false_without_norm():
    # No established norm yet -> never retry on a guess.
    assert should_retry_yield(count=0, norm=None, low_ratio=0.4) is False


def test_scrape_with_yield_retry_returns_best_attempt():
    # First attempt returns a degraded 2 cards, retry recovers 41.
    attempts = iter([[1, 2], list(range(41))])

    def scrape():
        return next(attempts)

    sleeps = []
    result = scrape_with_yield_retry(scrape, norm=40, low_ratio=0.4,
                                     max_attempts=3, base_delay=2.0, sleep=sleeps.append)
    assert len(result) == 41            # kept the better attempt
    assert sleeps == [2.0]              # backed off once before the retry


def test_scrape_with_yield_retry_keeps_best_when_all_low():
    attempts = iter([[1], [1, 2, 3], [1, 2]])

    def scrape():
        return next(attempts)

    result = scrape_with_yield_retry(scrape, norm=40, low_ratio=0.4,
                                     max_attempts=3, base_delay=1.0, sleep=lambda s: None)
    assert len(result) == 3             # best of the three low attempts


def test_scrape_with_yield_retry_no_retry_when_first_is_healthy():
    calls = {"n": 0}

    def scrape():
        calls["n"] += 1
        return list(range(40))

    result = scrape_with_yield_retry(scrape, norm=40, low_ratio=0.4,
                                     max_attempts=3, base_delay=1.0, sleep=lambda s: None)
    assert len(result) == 40
    assert calls["n"] == 1              # healthy first attempt -> no retry


def test_pairs_below_norm_flags_stragglers_for_requeue():
    records = [
        ("Mumbai", "Pintola", 40), ("Delhi", "Pintola", 42), ("Pune", "Pintola", 2),
        ("Mumbai", "Quaker", 30), ("Delhi", "Quaker", 31), ("Pune", "Quaker", 29),
    ]
    flagged = pairs_below_norm(records, low_ratio=0.4, min_samples=3)
    assert flagged == [("Pune", "Pintola")]
