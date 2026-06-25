from pipeline.score import (
    percentile_ranks,
    gym_counts_by_pincode,
    store_pincodes,
    attach_subscores,
    goat_fit,
    verdict,
    route_channel,
    attach_goat_fit,
    WEIGHTS,
)


def test_percentile_ranks_basic():
    assert percentile_ranks([10, 20, 30]) == [33.33, 66.67, 100.0]


def test_percentile_ranks_preserves_none():
    out = percentile_ranks([10, None, 30])
    assert out[1] is None
    assert out[0] == 50.0 and out[2] == 100.0


def test_gym_counts_and_store_pins():
    gyms = [{"pincode": "110001"}, {"pincode": "110001"}, {"pincode": "560001"}]
    assert gym_counts_by_pincode(gyms) == {"110001": 2, "560001": 1}
    stores = [{"pincode": "110001"}]
    assert store_pincodes(stores) == {"110001"}


def test_attach_subscores():
    locs = [
        {"pincode": "110001", "price_mid": 10000, "employment_count": 2, "education_count": 1},
        {"pincode": "560001", "price_mid": 20000, "employment_count": 0, "education_count": 3},
    ]
    attach_subscores(locs, {"110001": 5, "560001": 0}, {"110001"})
    assert locs[0]["affluence"] == 50.0 and locs[1]["affluence"] == 100.0
    assert locs[0]["fitness"] == 100.0 and locs[1]["fitness"] == 50.0
    assert locs[0]["has_store"] is True and locs[1]["has_store"] is False


def test_goat_fit_all_present():
    score, partial = goat_fit({"affluence": 100, "fitness": 100, "corporate": 100, "youth": 100})
    assert score == 100.0 and partial is False


def test_goat_fit_redistributes_when_affluence_missing():
    loc = {"affluence": None, "fitness": 100, "corporate": 0, "youth": 0}
    score, partial = goat_fit(loc)
    assert partial is True
    assert score == round(100 * (0.30 / 0.65), 2)  # 46.15


def test_verdict_bands():
    assert verdict(70) == "GO"
    assert verdict(69.9) == "SAMPLE-FIRST"
    assert verdict(45) == "SAMPLE-FIRST"
    assert verdict(44.9) == "WAIT"


def test_route_channel_priority():
    assert route_channel({"corporate": 90, "fitness": 10, "affluence": 50, "youth": 10, "has_store": False}) == "Blinkit + B2B"
    assert route_channel({"corporate": 10, "fitness": 90, "affluence": 50, "youth": 10, "has_store": False}) == "Gym Partnership"
    assert route_channel({"corporate": 10, "fitness": 10, "affluence": 90, "youth": 80, "has_store": False}) == "D2C Subscription"
    assert route_channel({"corporate": 10, "fitness": 10, "affluence": 60, "youth": 10, "has_store": True}) == "Offline Shelf-Test"
    assert route_channel({"corporate": 10, "fitness": 10, "affluence": 10, "youth": 10, "has_store": False}) == "Hold"
