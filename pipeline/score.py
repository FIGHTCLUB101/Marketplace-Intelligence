from collections import Counter


def percentile_ranks(values):
    """Map each present value to its percentile (share of present values <= it * 100).
    None values stay None."""
    present = [v for v in values if v is not None]
    n = len(present)
    if n == 0:
        return [None] * len(values)
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            le = sum(1 for p in present if p <= v)
            out.append(round(le / n * 100, 2))
    return out


def gym_counts_by_pincode(gyms):
    return dict(Counter(g["pincode"] for g in gyms if g.get("pincode")))


def store_pincodes(stores):
    return set(s["pincode"] for s in stores if s.get("pincode"))


def _pin(loc):
    p = loc.get("pincode")
    return None if p is None else str(p).strip()


def attach_subscores(localities, gym_counts, store_pins):
    affl = percentile_ranks([l.get("price_mid") for l in localities])
    fitv = percentile_ranks([gym_counts.get(_pin(l), 0) for l in localities])
    # Corporate density combines Nearby employment + Commercial Hub (scope addendum)
    corp = percentile_ranks([
        l.get("employment_count", 0) + l.get("commercial_count", 0) for l in localities
    ])
    yth = percentile_ranks([l.get("education_count", 0) for l in localities])
    for i, l in enumerate(localities):
        l["affluence"] = affl[i] if l.get("price_mid") is not None else None
        l["fitness"] = fitv[i]
        l["corporate"] = corp[i]
        l["youth"] = yth[i]
        l["has_store"] = _pin(l) in store_pins


WEIGHTS = {"affluence": 0.35, "fitness": 0.30, "corporate": 0.25, "youth": 0.10}


def goat_fit(loc):
    """Weighted composite; redistributes weight over present sub-scores. Returns (score, partial)."""
    present = {k: loc.get(k) for k in WEIGHTS if loc.get(k) is not None}
    total_w = sum(WEIGHTS[k] for k in present)
    if total_w == 0:
        return 0.0, True
    score = sum(present[k] * WEIGHTS[k] for k in present) / total_w
    partial = len(present) < len(WEIGHTS)
    return round(score, 2), partial


def verdict(score):
    if score >= 70:
        return "GO"
    if score >= 45:
        return "SAMPLE-FIRST"
    return "WAIT"


def route_channel(loc):
    c = loc.get("corporate") or 0
    f = loc.get("fitness") or 0
    a = loc.get("affluence") or 0
    y = loc.get("youth") or 0
    if loc.get("has_store") and a >= 55:
        return "Offline Shelf-Test"
    top = max(c, f, a)
    if top < 40:
        return "Hold"
    if c == top:
        return "Blinkit + B2B"
    if f == top:
        return "Gym Partnership"
    if a == top and y >= 40:
        return "D2C Subscription"
    if a == top:
        return "D2C Subscription"
    return "Hold"


def attach_goat_fit(localities):
    for l in localities:
        score, partial = goat_fit(l)
        l["goat_fit"] = score
        l["partial_data"] = partial
        l["verdict"] = verdict(score)
        l["channel"] = route_channel(l)
