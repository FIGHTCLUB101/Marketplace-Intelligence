import os
from nb08lib import normalize_city, load_darkstores, haversine_km, build_grid, nearest_by_brand, area_core, refine_coordinates, precision_radii, confirmed_brands, assign_state, serviceability_confidence, coverage_confidence_buckets, gtm_action

ROOT = r"C:\Users\singh\Desktop\GOATLife"


def test_normalize_city():
    assert normalize_city("Delhi") == "New Delhi"
    assert normalize_city("Bengaluru") == "Bangalore"
    assert normalize_city("Mumbai") == "Mumbai"


def test_load_darkstores_normalized():
    ds = load_darkstores(os.path.join(ROOT, "web", "darkstores.json"))
    assert len(ds) == 4081
    cities = {d["city"] for d in ds}
    assert "New Delhi" in cities and "Delhi" not in cities
    assert "Bangalore" in cities and "Bengaluru" not in cities
    brands = {d["brand"] for d in ds}
    assert brands == {"Blinkit", "Zepto", "Swiggy Instamart"}


def test_haversine_known():
    d = haversine_km(28.6315, 77.2167, 28.4595, 77.0266)  # CP -> Gurugram
    assert 20 < d < 35


def test_nearest_by_brand():
    stores = [
        {"lat": 28.460, "lng": 77.027, "brand": "Blinkit", "city": "Gurugram", "name": "B1"},
        {"lat": 28.470, "lng": 77.040, "brand": "Zepto", "city": "Gurugram", "name": "Z1"},
        {"lat": 19.000, "lng": 72.800, "brand": "Blinkit", "city": "Mumbai", "name": "B2"},
    ]
    grid = build_grid(stores)
    r = nearest_by_brand(28.4595, 77.0266, grid)
    assert r["per_brand"]["Blinkit"] < 1.0          # B1 ~ adjacent
    assert r["per_brand"]["Zepto"] < 2.0
    assert r["per_brand"]["Swiggy Instamart"] is None
    assert r["nearest_any"] == r["per_brand"]["Blinkit"]
    assert r["n_within_3km"] >= 2


def test_area_core():
    assert area_core("Sector 47, Gurgaon") == "sector 47"


def test_refine_coordinates_with_fake_geocoder():
    # Two localities share one pincode centroid; one is uniquely placed; one has no geo.
    recs = [
        {"AREA": "Koramangala, Bangalore", "ADDRESS": "Bangalore", "lat": 12.95, "lng": 77.60},
        {"AREA": "Indiranagar, Bangalore", "ADDRESS": "Bangalore", "lat": 12.95, "lng": 77.60},
        {"AREA": "Unique Area, Bangalore", "ADDRESS": "Bangalore", "lat": 12.90, "lng": 77.55},
        {"AREA": "NoGeo Area, Bangalore", "ADDRESS": "Bangalore", "lat": None, "lng": None},
    ]
    centroids = {"Bangalore": (12.95, 77.60)}
    fake = {
        "koramangala, bangalore, india": (12.935, 77.624),
        "indiranagar, bangalore, india": (12.971, 77.640),
    }

    def geocode_fn(q):
        return fake.get(q.lower())

    stats = refine_coordinates(recs, geocode_fn, centroids)
    assert recs[0]["coord_precision"] == "locality" and recs[0]["lat_r"] == 12.935
    assert recs[1]["coord_precision"] == "locality"
    assert recs[2]["coord_precision"] == "locality"        # unique coord, not shared -> locality, unchanged
    assert recs[2]["lat_r"] == 12.90
    assert recs[3]["coord_precision"] == "no-geo"
    assert stats["refined"] == 2 and stats["no_geo"] == 1


def test_refine_rejects_out_of_range():
    recs = [
        {"AREA": "A, Bangalore", "ADDRESS": "Bangalore", "lat": 12.95, "lng": 77.60},
        {"AREA": "B, Bangalore", "ADDRESS": "Bangalore", "lat": 12.95, "lng": 77.60},
    ]
    centroids = {"Bangalore": (12.95, 77.60)}

    def geocode_fn(q):
        return (28.6, 77.2)  # Delhi — >35km from Bangalore centroid -> reject

    refine_coordinates(recs, geocode_fn, centroids)
    assert all(r["coord_precision"] == "pincode" for r in recs)  # rejected -> keep centroid


def test_precision_radii():
    assert precision_radii("locality") == (3.5, 6.0)
    assert precision_radii("pincode") == (5.5, 8.0)
    assert precision_radii("no-geo") == (5.5, 8.0)  # default to wider


def test_confirmed_brands():
    per = {"Blinkit": 1.2, "Zepto": 7.0, "Swiggy Instamart": None}
    assert confirmed_brands(per, 3.5) == ["Blinkit"]
    assert confirmed_brands(per, 8.0) == ["Blinkit", "Zepto"]


def test_assign_state_confirmed_likely_unknown():
    # locality precision: confirm 3.5, likely 6.0
    assert assign_state(2.0, "locality", 5.0, 8.0, "High") == "Confirmed"
    assert assign_state(5.0, "locality", 5.0, 8.0, "High") == "Likely"      # within likely radius
    # central locality in High-mapped city, beyond likely radius -> Likely
    assert assign_state(7.0, "locality", 4.0, 8.0, "High") == "Likely"
    # peripheral in Low-mapped city, beyond radii -> Unknown
    assert assign_state(9.0, "locality", 12.0, 8.0, "Low") == "Unknown"
    # no geo
    assert assign_state(None, "no-geo", None, None, "Low") == "Unknown"


def test_serviceability_confidence():
    assert serviceability_confidence("Confirmed", "locality", "Low") == "High"
    assert serviceability_confidence("Confirmed", "pincode", "High") == "Medium"
    assert serviceability_confidence("Likely", "locality", "High") == "High"
    assert serviceability_confidence("Likely", "pincode", "Medium") == "Medium"
    assert serviceability_confidence("Unknown", "locality", "High") == "Low"


def test_coverage_confidence_buckets():
    counts = {"A": 300, "B": 200, "C": 100, "D": 50, "E": 20, "F": 10}
    b = coverage_confidence_buckets(counts)
    assert b["A"] == "High" and b["F"] == "Low"
    assert set(b.values()) <= {"High", "Medium", "Low"}


def test_gtm_action_matrix():
    assert gtm_action("GO", "Confirmed") == "PUSH-NOW"
    assert gtm_action("GO", "Likely") == "PUSH-NOW"
    assert gtm_action("GO", "Unknown") == "D2C / OFFLINE - verify QC"
    assert gtm_action("SAMPLE-FIRST", "Confirmed") == "SAMPLE + QC test"
    assert gtm_action("SAMPLE-FIRST", "Unknown") == "SAMPLE (D2C / offline)"
    assert gtm_action("WAIT", "Confirmed") == "HOLD"
    assert gtm_action("WAIT", "Unknown") == "HOLD"


def test_refine_handles_nan_coords():
    recs = [{"AREA": "NaN Area, Bangalore", "ADDRESS": "Bangalore", "lat": float("nan"), "lng": float("nan")}]
    stats = refine_coordinates(recs, lambda q: None, {"Bangalore": (12.95, 77.60)})
    assert recs[0]["coord_precision"] == "no-geo"
    assert recs[0]["lat_r"] is None
    assert stats["no_geo"] == 1


def test_assign_state_nan_is_unknown():
    assert assign_state(float("nan"), "locality", 1.0, 5.0, "High") == "Unknown"
