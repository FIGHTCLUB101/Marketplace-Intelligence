import json
import math
from collections import defaultdict

_CITY_FIX = {"Delhi": "New Delhi", "Bengaluru": "Bangalore"}

BRANDS = ("Blinkit", "Zepto", "Swiggy Instamart")


def normalize_city(name):
    return _CITY_FIX.get(name, name)


def load_darkstores(path):
    markers = json.load(open(path, encoding="utf-8"))["markers"]
    return [
        {"lat": m["lat"], "lng": m["lng"], "brand": m["brand"],
         "city": normalize_city(m["city"]), "name": m.get("name", "")}
        for m in markers
    ]


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_grid(stores, cell=0.1):
    grid = defaultdict(list)
    for s in stores:
        if s["lat"] is None or s["lng"] is None:
            continue
        grid[(int(s["lat"] // cell), int(s["lng"] // cell))].append(s)
    return grid


def nearest_by_brand(lat, lng, grid, scan_km=10.0, cell=0.1):
    span = int(scan_km / 11) + 1  # ~11 km per 0.1deg cell
    gk = (int(lat // cell), int(lng // cell))
    per_brand = {b: None for b in BRANDS}
    n_within_3km = 0
    nearest_any = None
    for di in range(-span, span + 1):
        for dj in range(-span, span + 1):
            for s in grid.get((gk[0] + di, gk[1] + dj), []):
                d = haversine_km(lat, lng, s["lat"], s["lng"])
                if d > scan_km:
                    continue
                b = s["brand"]
                if per_brand.get(b) is None or d < per_brand[b]:
                    per_brand[b] = round(d, 2)
                if nearest_any is None or d < nearest_any:
                    nearest_any = round(d, 2)
                if d <= 3.5:
                    n_within_3km += 1
    return {"per_brand": per_brand, "nearest_any": nearest_any, "n_within_3km": n_within_3km}
