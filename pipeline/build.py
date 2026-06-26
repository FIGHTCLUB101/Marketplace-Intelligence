import os
import json
from collections import Counter
from datetime import date

from pipeline.parse import load_localities, load_gyms, load_stores
from pipeline.geocode import make_geocoder, attach_coords
from pipeline.score import (
    gym_counts_by_pincode, store_pincodes, attach_subscores,
    attach_goat_fit, WEIGHTS,
)
from pipeline.darkstores import load_darkstores, attach_serviceability
from pipeline.enrich import attach_enrichment


def build(root):
    web = os.path.join(root, "web")
    os.makedirs(web, exist_ok=True)
    g = make_geocoder()

    localities = load_localities(os.path.join(root, "data", "magicbricks_localities.xlsx"))
    gyms = load_gyms(os.path.join(root, "data", "justdial_gyms_manual.xlsx"))
    stores = load_stores(os.path.join(root, "data", "reliance_smart_bazaar_stores.xlsx"))

    mb_stats = attach_coords(localities, pin_key="pincode", geocode=g)
    gym_stats = attach_coords(gyms, pin_key="pincode", addr_key="addr", geocode=g)
    store_stats = attach_coords(stores, pin_key="pincode", geocode=g)

    attach_subscores(localities, gym_counts_by_pincode(gyms), store_pincodes(stores))

    # serviceability + enrichment BEFORE the final verdict/channel pass so routing sees them
    darkstores = load_darkstores(os.path.join(web, "darkstores.json"))
    attach_serviceability(localities, darkstores)
    attach_enrichment(localities)
    attach_goat_fit(localities)

    # city rollups
    cities = {}
    for l in localities:
        c = cities.setdefault(l["city"], {"city": l["city"], "locality_count": 0,
            "go": 0, "sample": 0, "wait": 0, "qc_ready": 0, "fit_sum": 0.0})
        c["locality_count"] += 1
        c["fit_sum"] += l["goat_fit"]
        c["go"] += l["verdict"] == "GO"
        c["sample"] += l["verdict"] == "SAMPLE-FIRST"
        c["wait"] += l["verdict"] == "WAIT"
        c["qc_ready"] += 1 if l.get("qc_serviceable") else 0
    gym_city = Counter(x["city"] for x in gyms)
    store_city = Counter(x["city"] for x in stores)
    city_list = []
    for c in cities.values():
        c["avg_goat_fit"] = round(c.pop("fit_sum") / c["locality_count"], 1)
        c["gym_count"] = gym_city.get(c["city"], 0)
        c["store_count"] = store_city.get(c["city"], 0)
        city_list.append(c)
    city_list.sort(key=lambda c: c["avg_goat_fit"], reverse=True)

    ds_counts = Counter(d["brand"] for d in darkstores)
    vc = Counter(l["verdict"] for l in localities)
    data = {
        "meta": {
            "generated": date.today().isoformat(),
            "weights": WEIGHTS,
            "geocode_coverage": {
                "magicbricks_hit": mb_stats["hit"], "magicbricks_total": mb_stats["total"],
                "gyms_hit": gym_stats["hit"], "gyms_total": gym_stats["total"],
                "stores_hit": store_stats["hit"], "stores_total": store_stats["total"],
            },
            "darkstores": {
                "Blinkit": ds_counts.get("Blinkit", 0),
                "Zepto": ds_counts.get("Zepto", 0),
                "Swiggy Instamart": ds_counts.get("Swiggy Instamart", 0),
            },
        },
        "summary": {
            "total_localities": len(localities), "total_gyms": len(gyms),
            "total_stores": len(stores), "total_cities": len(city_list),
            "total_darkstores": len(darkstores),
            "go": vc.get("GO", 0), "sample": vc.get("SAMPLE-FIRST", 0), "wait": vc.get("WAIT", 0),
            "qc_ready": sum(1 for l in localities if l.get("qc_serviceable")),
        },
        "cities": city_list,
        "localities": localities,
    }

    with open(os.path.join(web, "data-summary.js"), "w", encoding="utf-8") as f:
        f.write("window.GOAT_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    with open(os.path.join(web, "data-markers.json"), "w", encoding="utf-8") as f:
        json.dump({"gyms": gyms, "stores": stores}, f, ensure_ascii=False)
    return data


if __name__ == "__main__":
    s = build(r"C:\Users\singh\Desktop\GOATLife")
    print("Built.",
          s["summary"]["go"], "GO /",
          s["summary"]["sample"], "SAMPLE /",
          s["summary"]["wait"], "WAIT |",
          s["summary"]["qc_ready"], "QC-ready |",
          "geocode mb", s["meta"]["geocode_coverage"]["magicbricks_hit"], "/600")
