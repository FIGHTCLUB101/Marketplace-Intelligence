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
    corp = percentile_ranks([l.get("employment_count", 0) for l in localities])
    yth = percentile_ranks([l.get("education_count", 0) for l in localities])
    for i, l in enumerate(localities):
        l["affluence"] = affl[i] if l.get("price_mid") is not None else None
        l["fitness"] = fitv[i]
        l["corporate"] = corp[i]
        l["youth"] = yth[i]
        l["has_store"] = _pin(l) in store_pins
