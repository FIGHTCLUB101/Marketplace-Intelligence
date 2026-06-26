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
    # Use a conservative 8 km/cell divisor: a 0.1deg longitude cell is only ~9.8 km
    # at 28N, so dividing by 11 could miss stores near a cell boundary. 8.0 over-covers.
    span = int(scan_km / 8.0) + 1
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
                if b in per_brand and (per_brand[b] is None or d < per_brand[b]):
                    per_brand[b] = round(d, 2)
                if nearest_any is None or d < nearest_any:
                    nearest_any = round(d, 2)
                if d <= 3.5:
                    n_within_3km += 1
    return {"per_brand": per_brand, "nearest_any": nearest_any, "n_within_3km": n_within_3km}


def area_core(area):
    return str(area).split(",")[0].strip().lower()


def refine_coordinates(records, geocode_fn, city_centroids, accept_km=35.0):
    # which (lat,lng) coordinates are shared by >=2 geocoded records
    counts = defaultdict(int)
    for r in records:
        if r["lat"] is not None and r["lng"] is not None:
            counts[(r["lat"], r["lng"])] += 1

    stats = {"refined": 0, "pincode": 0, "no_geo": 0}
    for r in records:
        if r["lat"] is None or r["lng"] is None:
            r["lat_r"], r["lng_r"], r["coord_precision"] = None, None, "no-geo"
            stats["no_geo"] += 1
            continue
        shared = counts[(r["lat"], r["lng"])] > 1
        # default: keep as-is
        r["lat_r"], r["lng_r"] = r["lat"], r["lng"]
        r["coord_precision"] = "pincode" if shared else "locality"
        if not shared:
            continue
        res = geocode_fn(f"{area_core(r['AREA'])}, {r['ADDRESS']}, India")
        if res is not None:
            clat, clng = city_centroids.get(r["ADDRESS"], (None, None))
            if clat is not None and haversine_km(res[0], res[1], clat, clng) <= accept_km:
                r["lat_r"], r["lng_r"], r["coord_precision"] = round(res[0], 5), round(res[1], 5), "locality"
                stats["refined"] += 1
                continue
        stats["pincode"] += 1
    return stats


_CONFIRM = {"locality": 3.5, "pincode": 5.5}
_LIKELY = {"locality": 6.0, "pincode": 8.0}


def precision_radii(coord_precision):
    return (_CONFIRM.get(coord_precision, 5.5), _LIKELY.get(coord_precision, 8.0))


def confirmed_brands(per_brand, confirm_km):
    return [b for b in BRANDS if per_brand.get(b) is not None and per_brand[b] <= confirm_km]


def assign_state(nearest_any, coord_precision, dist_to_centroid, city_median_centroid, city_coverage_conf):
    if nearest_any is None:
        return "Unknown"
    confirm_km, likely_km = precision_radii(coord_precision)
    if nearest_any <= confirm_km:
        return "Confirmed"
    is_central = (dist_to_centroid is not None and city_median_centroid is not None
                  and dist_to_centroid <= city_median_centroid)
    if nearest_any <= likely_km or (city_coverage_conf in ("High", "Medium") and is_central):
        return "Likely"
    return "Unknown"


def serviceability_confidence(state, coord_precision, city_coverage_conf):
    if state == "Confirmed":
        return "High" if coord_precision == "locality" else "Medium"
    if state == "Likely":
        return "High" if city_coverage_conf == "High" else "Medium"
    return "Low"


def coverage_confidence_buckets(city_counts):
    vals = sorted(city_counts.values())
    if not vals:
        return {}
    t33 = vals[int(len(vals) * 0.33)]
    t67 = vals[int(len(vals) * 0.67)]
    out = {}
    for city, n in city_counts.items():
        out[city] = "High" if n >= t67 else ("Medium" if n >= t33 else "Low")
    return out


_GTM = {
    ("GO", "reachable"): "PUSH-NOW",
    ("GO", "Unknown"): "D2C / OFFLINE - verify QC",
    ("SAMPLE-FIRST", "reachable"): "SAMPLE + QC test",
    ("SAMPLE-FIRST", "Unknown"): "SAMPLE (D2C / offline)",
    ("WAIT", "reachable"): "HOLD",
    ("WAIT", "Unknown"): "HOLD",
}


def gtm_action(icp_verdict, state):
    key = "Unknown" if state == "Unknown" else "reachable"
    return _GTM.get((icp_verdict, key), "REVIEW")
