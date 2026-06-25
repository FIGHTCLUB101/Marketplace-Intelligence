import json
import os

from pipeline.build import build

ROOT = r"C:\Users\singh\Desktop\GOATLife"


def test_build_writes_files_and_shape():
    summary = build(ROOT)
    assert os.path.exists(os.path.join(ROOT, "web", "data-summary.js"))
    assert os.path.exists(os.path.join(ROOT, "web", "data-markers.json"))
    assert summary["summary"]["total_localities"] == 600
    # every locality has verdict + enrichment + serviceability
    for l in summary["localities"]:
        assert "verdict" in l and "archetype" in l and "qc_serviceable" in l and "activation" in l
    # geocode coverage within validated range
    assert summary["meta"]["geocode_coverage"]["magicbricks_hit"] >= 480
    # darkstore counts present
    assert summary["meta"]["darkstores"]["Blinkit"] == 1954
    js = open(os.path.join(ROOT, "web", "data-summary.js"), encoding="utf-8").read()
    assert js.startswith("window.GOAT_DATA =")
    markers = json.load(open(os.path.join(ROOT, "web", "data-markers.json"), encoding="utf-8"))
    assert len(markers["gyms"]) == 1537 and len(markers["stores"]) == 137
