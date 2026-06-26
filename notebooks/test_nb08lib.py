import os
from nb08lib import normalize_city, load_darkstores

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
