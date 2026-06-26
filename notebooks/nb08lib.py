import json

_CITY_FIX = {"Delhi": "New Delhi", "Bengaluru": "Bangalore"}


def normalize_city(name):
    return _CITY_FIX.get(name, name)


def load_darkstores(path):
    markers = json.load(open(path, encoding="utf-8"))["markers"]
    return [
        {"lat": m["lat"], "lng": m["lng"], "brand": m["brand"],
         "city": normalize_city(m["city"]), "name": m.get("name", "")}
        for m in markers
    ]
