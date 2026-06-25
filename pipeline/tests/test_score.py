from pipeline.score import (
    percentile_ranks,
    gym_counts_by_pincode,
    store_pincodes,
    attach_subscores,
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
