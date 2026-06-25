import json
import math

_CITY_FIX = {"Delhi": "New Delhi", "Bengaluru": "Bangalore"}


def load_darkstores(path):
    raw = json.load(open(path, encoding="utf-8"))["markers"]
    out = []
    for m in raw:
        out.append({
            "lat": m["lat"], "lng": m["lng"], "brand": m["brand"],
            "city": _CITY_FIX.get(m["city"], m["city"]), "name": m.get("name", ""),
        })
    return out


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def attach_serviceability(localities, darkstores, radius=3.5):
    """Add nearest_darkstore_km, nearest_by_brand, qc_serviceable per locality.
    Uses a ~0.1deg grid (~11km cells) for a fast neighbourhood scan."""
    grid = {}
    for d in darkstores:
        if d["lat"] is None:
            continue
        key = (round(d["lat"] / 0.1), round(d["lng"] / 0.1))
        grid.setdefault(key, []).append(d)

    for l in localities:
        if l.get("lat") is None:
            l["nearest_darkstore_km"] = None
            l["nearest_by_brand"] = {}
            l["qc_serviceable"] = False
            continue
        gk = (round(l["lat"] / 0.1), round(l["lng"] / 0.1))
        by_brand = {}
        nearest = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for d in grid.get((gk[0] + di, gk[1] + dj), []):
                    km = haversine_km(l["lat"], l["lng"], d["lat"], d["lng"])
                    if nearest is None or km < nearest:
                        nearest = km
                    if d["brand"] not in by_brand or km < by_brand[d["brand"]]:
                        by_brand[d["brand"]] = round(km, 2)
        l["nearest_darkstore_km"] = round(nearest, 2) if nearest is not None else None
        l["nearest_by_brand"] = by_brand
        l["qc_serviceable"] = nearest is not None and nearest <= radius
