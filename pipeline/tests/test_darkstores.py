import os

from pipeline.darkstores import load_darkstores, haversine_km, attach_serviceability

ROOT = r"C:\Users\singh\Desktop\GOATLife"


def test_haversine_known():
    d = haversine_km(28.6315, 77.2167, 28.4595, 77.0266)
    assert 20 < d < 35


def test_load_darkstores_normalizes_city():
    ds = load_darkstores(os.path.join(ROOT, "web", "darkstores.json"))
    assert len(ds) == 4081
    cities = set(d["city"] for d in ds)
    assert "New Delhi" in cities and "Delhi" not in cities


def test_attach_serviceability():
    locs = [{"lat": 28.4595, "lng": 77.0266}]
    ds = [{"lat": 28.4600, "lng": 77.0270, "brand": "Blinkit", "city": "Gurugram", "name": "X"}]
    attach_serviceability(locs, ds, radius=3.5)
    assert locs[0]["qc_serviceable"] is True
    assert locs[0]["nearest_darkstore_km"] < 1
    assert "Blinkit" in locs[0]["nearest_by_brand"]
