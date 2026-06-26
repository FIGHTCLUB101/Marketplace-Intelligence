import os
from nb08lib import normalize_city, load_darkstores, haversine_km, build_grid, nearest_by_brand

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
