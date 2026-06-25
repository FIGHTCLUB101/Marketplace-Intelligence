# GOAT Life "Where to Win" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static spatial-intelligence dashboard that scores GOAT Life's 600 localities by a GOAT-Fit Score, maps them with a GO/SAMPLE-FIRST/WAIT verdict + channel routing, and includes an interactive margin calculator pre-filled with GOAT Life's real Blinkit economics.

**Architecture:** A Python data pipeline parses + geocodes 3 xlsx datasets and bakes scores into `data-summary.js` (sync) + `data-markers.json` (lazy). A zero-build vanilla-JS + MapLibre frontend renders the map, locality inspector, leaderboard, whitespace chart, and margin calculator — reusing the patterns from `darkstore version 1` (map/scoring/two-phase load), `QCompass` (margin engine/verdict), and `DATA 22-26` (whitespace bubble).

**Tech Stack:** Python 3.13 (openpyxl, pgeocode, pandas) + pytest · vanilla JS ES modules · MapLibre GL JS 3.6.2 (CDN) · Chart.js (CDN) · Node built-in test runner (`node --test`) for pure JS · Vercel static deploy.

## Global Constraints

- **Project root:** `C:\Users\singh\Desktop\GOATLife`. Pipeline in `pipeline/`, frontend in `web/`, generated data in `web/`.
- **Source data (in project root):** `magicbricks_localities.xlsx` (600 rows), `justdial_gyms_manual.xlsx` (1537), `reliance_smart_bazaar_stores.xlsx` (137).
- **GOAT-Fit weights (exact):** `Affluence 0.35, FitnessDensity 0.30, CorporateDensity 0.25, YouthDensity 0.10`.
- **Verdict thresholds (exact):** `GO ≥ 70`, `SAMPLE-FIRST 45–69`, `WAIT < 45`.
- **Missing sub-score rule:** mark sub-score `None`, redistribute its weight proportionally across present sub-scores, set `partial_data = true`. Never impute.
- **GOAT Life real economics (margin calculator defaults):** MRP `₹119`, selling `₹99` (16% brand-funded discount), gross margin `57%`, Blinkit commission `17.9%`, fulfilment fee `₹50`.
- **Margin verdict thresholds (from QCompass, exact):** GO = GM ≥ 65% AND netRealization ≥ ₹250 AND adBudget ≥ ₹2L; STOP = GM < 50% OR netRealization < ₹150 OR adBudget < ₹1L; else CAUTION.
- **Design tokens (exact):** `--bg-base:#09090b`, `--bg-surface:#18181b`, `--border:rgba(255,255,255,.08)`, `--text:#fafafa`, GOAT gold `--goat-gold:#F5A623`, GO `#059669`, SAMPLE `#d97706`, WAIT `#52525b`. Font: **Outfit**.
- **Map:** MapLibre GL JS 3.6.2, style `https://tiles.openfreemap.org/styles/dark`, India center `[78.9629, 20.5937]` zoom 4.5.
- **No backend, no build step, no framework.** Static files only.
- **Geocoding:** offline via `pgeocode` India, pincode-centroid. Coverage baseline already validated: magicbricks 508/600, reliance 134/137, gyms 1532/1537.

---

## File Structure

```
GOATLife/
  pipeline/
    parse.py        # xlsx → cleaned dicts; price + entity parsing
    geocode.py      # pincode extraction + pgeocode lookup
    score.py        # percentile ranks, sub-scores, GOAT-Fit, verdict, channel
    build.py        # orchestrator → writes web/data-summary.js + web/data-markers.json
    tests/
      test_parse.py
      test_geocode.py
      test_score.py
  web/
    index.html      # shell + tab nav + panels
    styles.css      # darkstore token system + GOAT gold
    state.js        # AppState slot object
    app.js          # orchestrator + two-phase load + tab wiring
    map.js          # MapLibre init, spatial grid, layers, inspector
    scoreDisplay.js # pure verdict/channel/gauge display helpers
    charts.js       # whitespace bubble + city leaderboard table
    margin.js       # ported QCompass economics + GO/CAUTION/STOP verdict
    methodology.js  # formula/weights/coverage/sources panel
    data-summary.js   # GENERATED (sync)
    data-markers.json # GENERATED (lazy)
    tests/
      scoreDisplay.test.js
      margin.test.js
    vercel.json
  requirements.txt
  README.md
```

---

## Task 1: Pipeline scaffold + price parser

**Files:**
- Create: `pipeline/parse.py`, `pipeline/__init__.py`, `pipeline/tests/__init__.py`, `requirements.txt`
- Test: `pipeline/tests/test_parse.py`

**Interfaces:**
- Produces: `parse_price_to_midpoint(price_str: str) -> float | None` — residential-buy midpoint ₹/sqft, or None.

- [ ] **Step 1: Write `requirements.txt`**

```
openpyxl>=3.1
pgeocode>=0.5
pandas>=2.0
pytest>=8.0
```

- [ ] **Step 2: Write the failing test**

```python
# pipeline/tests/test_parse.py
from pipeline.parse import parse_price_to_midpoint

def test_residential_buy_midpoint():
    s = "Residential: Buy Rs. 8,700- Rs. 15,200 / sqft | Rent Rs. 21- Rs. 34 / sqft || Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft"
    assert parse_price_to_midpoint(s) == 11950.0

def test_missing_residential_returns_none():
    assert parse_price_to_midpoint("Office Space: Buy Rs. 8,500- Rs. 14,600 / sqft") is None

def test_blank_returns_none():
    assert parse_price_to_midpoint("") is None
    assert parse_price_to_midpoint(None) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.parse'`

- [ ] **Step 4: Write minimal implementation**

```python
# pipeline/parse.py
import re

def parse_price_to_midpoint(price_str):
    """Return midpoint of the Residential Buy ₹/sqft range, or None."""
    if not price_str:
        return None
    m = re.search(r"Residential:\s*Buy\s*Rs\.?\s*([\d,]+)\s*-\s*Rs\.?\s*([\d,]+)", str(price_str))
    if not m:
        return None
    low = float(m.group(1).replace(",", ""))
    high = float(m.group(2).replace(",", ""))
    return (low + high) / 2
```

Also create empty `pipeline/__init__.py` and `pipeline/tests/__init__.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_parse.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pipeline/ requirements.txt
git commit -m "feat(pipeline): price-range parser + scaffold"
```

---

## Task 2: Entity counter + dataset loaders

**Files:**
- Modify: `pipeline/parse.py`
- Test: `pipeline/tests/test_parse.py`

**Interfaces:**
- Consumes: `parse_price_to_midpoint`.
- Produces:
  - `count_named_entities(text: str) -> int` — comma-separated non-"N/A" entity count.
  - `load_localities(path: str) -> list[dict]` — keys: `area, city, pincode, price_mid, employment_count, education_count, commercial_raw, employment_raw, education_raw`.
  - `load_gyms(path: str) -> list[dict]` — keys: `city, name, addr`.
  - `load_stores(path: str) -> list[dict]` — keys: `city, name, addr, pincode`.

- [ ] **Step 1: Write the failing test**

```python
# append to pipeline/tests/test_parse.py
from pipeline.parse import count_named_entities, load_localities, load_gyms, load_stores
import os

ROOT = r"C:\Users\singh\Desktop\GOATLife"

def test_count_named_entities():
    assert count_named_entities("G D Goenka University, Ryan International, KIIT school") == 3
    assert count_named_entities("N/A") == 0
    assert count_named_entities("") == 0
    assert count_named_entities(None) == 0

def test_load_localities_shape():
    rows = load_localities(os.path.join(ROOT, "magicbricks_localities.xlsx"))
    assert len(rows) == 600
    r = rows[0]
    assert set(["area","city","pincode","price_mid","employment_count","education_count"]).issubset(r)
    assert r["city"] == "Gurugram"

def test_load_gyms_and_stores():
    gyms = load_gyms(os.path.join(ROOT, "justdial_gyms_manual.xlsx"))
    stores = load_stores(os.path.join(ROOT, "reliance_smart_bazaar_stores.xlsx"))
    assert len(gyms) == 1537
    assert len(stores) == 137
    assert "addr" in gyms[0] and "pincode" in stores[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_parse.py -v`
Expected: FAIL with `ImportError: cannot import name 'count_named_entities'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to pipeline/parse.py
import openpyxl

def count_named_entities(text):
    if not text:
        return 0
    parts = [p.strip() for p in str(text).split(",")]
    return len([p for p in parts if p and p.upper() != "N/A"])

def _rows(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    data = list(ws.iter_rows(values_only=True))
    wb.close()
    return data[1:]  # drop header

def load_localities(path):
    out = []
    for r in _rows(path):
        # cols: AREA, ADDRESS(city), PINCODE, price range, phys infra, intro,
        #       social, employment(7), education(8), transport, shopping, hospital,
        #       nearby, tourist, commercial(14), url
        out.append({
            "area": r[0], "city": r[1], "pincode": r[2],
            "price_mid": parse_price_to_midpoint(r[3]),
            "employment_count": count_named_entities(r[7]),
            "education_count": count_named_entities(r[8]),
            "employment_raw": r[7], "education_raw": r[8], "commercial_raw": r[14],
        })
    return out

def load_gyms(path):
    return [{"city": r[0], "name": r[1], "addr": str(r[2] or "")} for r in _rows(path)]

def load_stores(path):
    return [{"city": r[0], "name": r[1], "addr": r[2], "pincode": r[3]} for r in _rows(path)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_parse.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/parse.py pipeline/tests/test_parse.py
git commit -m "feat(pipeline): entity counter + xlsx loaders"
```

---

## Task 3: Geocoding (pincode extraction + pgeocode)

**Files:**
- Create: `pipeline/geocode.py`
- Test: `pipeline/tests/test_geocode.py`

**Interfaces:**
- Produces:
  - `extract_pincode(text: str) -> str | None` — first 6-digit token.
  - `make_geocoder() -> callable` — returns `geocode(pin: str) -> tuple[float,float] | None`.
  - `attach_coords(records: list[dict], pin_key="pincode", addr_key=None, geocode=...) -> dict` — mutates records adding `lat`/`lng`; returns `{"total","hit"}`. If `pin_key` missing/empty and `addr_key` given, extracts pincode from that address field first.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_geocode.py
from pipeline.geocode import extract_pincode, make_geocoder, attach_coords

def test_extract_pincode():
    assert extract_pincode("Modern College Road, Shivaji Nagar, Pune, 411005") == "411005"
    assert extract_pincode("no pin here") is None
    assert extract_pincode(None) is None

def test_geocode_known_pincode():
    g = make_geocoder()
    res = g("411005")  # Pune
    assert res is not None
    lat, lng = res
    assert 17 < lat < 20 and 72 < lng < 75

def test_attach_coords_from_address():
    g = make_geocoder()
    recs = [{"city":"Pune","name":"X","addr":"Kharadi Road, Pune, 411014"}]
    stats = attach_coords(recs, pin_key="pincode", addr_key="addr", geocode=g)
    assert recs[0]["lat"] is not None
    assert stats["hit"] == 1 and stats["total"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_geocode.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/geocode.py
import re
import pandas as pd
import pgeocode

def extract_pincode(text):
    if not text:
        return None
    m = re.search(r"\b(\d{6})\b", str(text))
    return m.group(1) if m else None

def make_geocoder():
    nomi = pgeocode.Nominatim("in")
    cache = {}
    def geocode(pin):
        if not pin:
            return None
        pin = re.sub(r"\D", "", str(pin))[:6]
        if len(pin) != 6:
            return None
        if pin in cache:
            return cache[pin]
        r = nomi.query_postal_code(pin)
        res = None if (r is None or pd.isna(r.latitude)) else (round(float(r.latitude),5), round(float(r.longitude),5))
        cache[pin] = res
        return res
    return geocode

def attach_coords(records, pin_key="pincode", addr_key=None, geocode=None):
    if geocode is None:
        geocode = make_geocoder()
    hit = 0
    for rec in records:
        pin = rec.get(pin_key)
        if not pin and addr_key:
            pin = extract_pincode(rec.get(addr_key))
            rec[pin_key] = pin
        res = geocode(pin)
        rec["lat"], rec["lng"] = (res if res else (None, None))
        if res:
            hit += 1
    return {"total": len(records), "hit": hit}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_geocode.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/geocode.py pipeline/tests/test_geocode.py
git commit -m "feat(pipeline): offline pincode geocoding"
```

---

## Task 4: Sub-scores (percentile ranks + pincode joins)

**Files:**
- Create: `pipeline/score.py`
- Test: `pipeline/tests/test_score.py`

**Interfaces:**
- Produces:
  - `percentile_ranks(values: list[float|None]) -> list[float|None]` — each present value → 0–100 percentile (share of present values ≤ it × 100); None stays None.
  - `gym_counts_by_pincode(gyms: list[dict]) -> dict[str,int]`.
  - `store_pincodes(stores: list[dict]) -> set[str]`.
  - `attach_subscores(localities, gym_counts, store_pins) -> None` — mutates each locality adding `affluence, fitness, corporate, youth` (0–100 or None) and `has_store` (bool).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_score.py
from pipeline.score import percentile_ranks, gym_counts_by_pincode, store_pincodes, attach_subscores

def test_percentile_ranks_basic():
    assert percentile_ranks([10, 20, 30]) == [33.33, 66.67, 100.0]

def test_percentile_ranks_preserves_none():
    out = percentile_ranks([10, None, 30])
    assert out[1] is None
    assert out[0] == 50.0 and out[2] == 100.0

def test_gym_counts_and_store_pins():
    gyms = [{"pincode":"110001"},{"pincode":"110001"},{"pincode":"560001"}]
    assert gym_counts_by_pincode(gyms) == {"110001":2,"560001":1}
    stores = [{"pincode":"110001"}]
    assert store_pincodes(stores) == {"110001"}

def test_attach_subscores():
    locs = [
        {"pincode":"110001","price_mid":10000,"employment_count":2,"education_count":1},
        {"pincode":"560001","price_mid":20000,"employment_count":0,"education_count":3},
    ]
    attach_subscores(locs, {"110001":5,"560001":0}, {"110001"})
    assert locs[0]["affluence"] == 50.0 and locs[1]["affluence"] == 100.0
    assert locs[0]["fitness"] == 100.0 and locs[1]["fitness"] == 50.0
    assert locs[0]["has_store"] is True and locs[1]["has_store"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_score.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/score.py
from collections import Counter

def percentile_ranks(values):
    present = [v for v in values if v is not None]
    n = len(present)
    if n == 0:
        return [None] * len(values)
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            le = sum(1 for p in present if p <= v)
            out.append(round(le / n * 100, 2))
    return out

def gym_counts_by_pincode(gyms):
    return dict(Counter(g["pincode"] for g in gyms if g.get("pincode")))

def store_pincodes(stores):
    return set(s["pincode"] for s in stores if s.get("pincode"))

def attach_subscores(localities, gym_counts, store_pins):
    def pin(l):
        p = l.get("pincode")
        return None if p is None else str(p).strip()
    affl = percentile_ranks([l.get("price_mid") for l in localities])
    fitv = percentile_ranks([gym_counts.get(pin(l), 0) for l in localities])
    corp = percentile_ranks([l.get("employment_count", 0) for l in localities])
    yth  = percentile_ranks([l.get("education_count", 0) for l in localities])
    for i, l in enumerate(localities):
        l["affluence"] = affl[i] if l.get("price_mid") is not None else None
        l["fitness"] = fitv[i]
        l["corporate"] = corp[i]
        l["youth"] = yth[i]
        l["has_store"] = pin(l) in store_pins
```

Note: affluence is None when `price_mid` is None (the redistribution case); fitness/corporate/youth always present (counts default to 0).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_score.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/score.py pipeline/tests/test_score.py
git commit -m "feat(pipeline): percentile sub-scores + pincode joins"
```

---

## Task 5: GOAT-Fit composite + verdict + channel

**Files:**
- Modify: `pipeline/score.py`
- Test: `pipeline/tests/test_score.py`

**Interfaces:**
- Consumes: sub-score keys on each locality.
- Produces:
  - `WEIGHTS = {"affluence":0.35,"fitness":0.30,"corporate":0.25,"youth":0.10}`.
  - `goat_fit(loc: dict) -> tuple[float, bool]` — `(score 0–100 rounded, partial_data)`; redistributes weight over present sub-scores.
  - `verdict(score: float) -> str` — `"GO" | "SAMPLE-FIRST" | "WAIT"`.
  - `route_channel(loc: dict) -> str` — one of `"Blinkit + B2B" | "D2C Subscription" | "Gym Partnership" | "Offline Shelf-Test" | "Hold"`.
  - `attach_goat_fit(localities) -> None` — mutates adding `goat_fit, partial_data, verdict, channel`.

- [ ] **Step 1: Write the failing test**

```python
# append to pipeline/tests/test_score.py
from pipeline.score import goat_fit, verdict, route_channel, attach_goat_fit, WEIGHTS

def test_goat_fit_all_present():
    loc = {"affluence":100,"fitness":100,"corporate":100,"youth":100}
    score, partial = goat_fit(loc)
    assert score == 100.0 and partial is False

def test_goat_fit_redistributes_when_affluence_missing():
    # affluence None -> weight redistributed over the other three (0.30/0.25/0.10 -> /0.65)
    loc = {"affluence":None,"fitness":100,"corporate":0,"youth":0}
    score, partial = goat_fit(loc)
    assert partial is True
    assert score == round(100 * (0.30/0.65), 2)  # 46.15

def test_verdict_bands():
    assert verdict(70) == "GO"
    assert verdict(69.9) == "SAMPLE-FIRST"
    assert verdict(45) == "SAMPLE-FIRST"
    assert verdict(44.9) == "WAIT"

def test_route_channel_priority():
    assert route_channel({"corporate":90,"fitness":10,"affluence":50,"youth":10,"has_store":False}) == "Blinkit + B2B"
    assert route_channel({"corporate":10,"fitness":90,"affluence":50,"youth":10,"has_store":False}) == "Gym Partnership"
    assert route_channel({"corporate":10,"fitness":10,"affluence":90,"youth":80,"has_store":False}) == "D2C Subscription"
    assert route_channel({"corporate":10,"fitness":10,"affluence":60,"youth":10,"has_store":True}) == "Offline Shelf-Test"
    assert route_channel({"corporate":10,"fitness":10,"affluence":10,"youth":10,"has_store":False}) == "Hold"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_score.py -v`
Expected: FAIL with `ImportError: cannot import name 'goat_fit'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to pipeline/score.py
WEIGHTS = {"affluence":0.35, "fitness":0.30, "corporate":0.25, "youth":0.10}

def goat_fit(loc):
    present = {k: loc.get(k) for k in WEIGHTS if loc.get(k) is not None}
    total_w = sum(WEIGHTS[k] for k in present)
    if total_w == 0:
        return 0.0, True
    score = sum(present[k] * WEIGHTS[k] for k in present) / total_w
    partial = len(present) < len(WEIGHTS)
    return round(score, 2), partial

def verdict(score):
    if score >= 70:
        return "GO"
    if score >= 45:
        return "SAMPLE-FIRST"
    return "WAIT"

def route_channel(loc):
    c = loc.get("corporate") or 0
    f = loc.get("fitness") or 0
    a = loc.get("affluence") or 0
    y = loc.get("youth") or 0
    if loc.get("has_store") and a >= 55:
        return "Offline Shelf-Test"
    top = max(c, f, a)
    if top < 40:
        return "Hold"
    if c == top:
        return "Blinkit + B2B"
    if f == top:
        return "Gym Partnership"
    if a == top and y >= 40:
        return "D2C Subscription"
    if a == top:
        return "D2C Subscription"
    return "Hold"

def attach_goat_fit(localities):
    for l in localities:
        score, partial = goat_fit(l)
        l["goat_fit"] = score
        l["partial_data"] = partial
        l["verdict"] = verdict(score)
        l["channel"] = route_channel(l)
```

Note: `route_channel`'s store check runs before the top-signal check so an existing Reliance store in an affluent locality routes to an offline shelf-test.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_score.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/score.py pipeline/tests/test_score.py
git commit -m "feat(pipeline): GOAT-Fit composite, verdict, channel routing"
```

---

## Task 6: Build orchestrator → emit data files

**Files:**
- Create: `pipeline/build.py`
- Test: `pipeline/tests/test_build.py`

**Interfaces:**
- Consumes: all of `parse`, `geocode`, `score`.
- Produces: `build(root: str) -> dict` — writes `web/data-summary.js` (assigns `window.GOAT_DATA = {...}`) and `web/data-markers.json` (`{"gyms":[...],"stores":[...]}`); returns the summary dict. `data-summary.js` contains `meta, summary, cities, localities` (all 600 localities with scores inline). `data-markers.json` contains geocoded gym + store points only.

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_build.py
import json, os
from pipeline.build import build

ROOT = r"C:\Users\singh\Desktop\GOATLife"

def test_build_writes_files_and_shape():
    summary = build(ROOT)
    assert os.path.exists(os.path.join(ROOT, "web", "data-summary.js"))
    assert os.path.exists(os.path.join(ROOT, "web", "data-markers.json"))
    assert summary["summary"]["total_localities"] == 600
    # every locality has a verdict
    assert all("verdict" in l for l in summary["localities"])
    # geocode coverage within validated range
    assert summary["meta"]["geocode_coverage"]["magicbricks_hit"] >= 480
    # data-summary.js is valid JS assignment
    js = open(os.path.join(ROOT,"web","data-summary.js"), encoding="utf-8").read()
    assert js.startswith("window.GOAT_DATA =")
    markers = json.load(open(os.path.join(ROOT,"web","data-markers.json"), encoding="utf-8"))
    assert len(markers["gyms"]) == 1537 and len(markers["stores"]) == 137
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest pipeline/tests/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/build.py
import os, json
from collections import Counter, defaultdict
from datetime import date
from pipeline.parse import load_localities, load_gyms, load_stores
from pipeline.geocode import make_geocoder, attach_coords
from pipeline.score import (
    gym_counts_by_pincode, store_pincodes, attach_subscores,
    attach_goat_fit, WEIGHTS,
)

def build(root):
    g = make_geocoder()
    localities = load_localities(os.path.join(root, "magicbricks_localities.xlsx"))
    gyms = load_gyms(os.path.join(root, "justdial_gyms_manual.xlsx"))
    stores = load_stores(os.path.join(root, "reliance_smart_bazaar_stores.xlsx"))

    mb_stats = attach_coords(localities, pin_key="pincode", geocode=g)
    gym_stats = attach_coords(gyms, pin_key="pincode", addr_key="addr", geocode=g)
    store_stats = attach_coords(stores, pin_key="pincode", geocode=g)

    attach_subscores(localities, gym_counts_by_pincode(gyms), store_pincodes(stores))
    attach_goat_fit(localities)

    # city rollups
    cities = {}
    for l in localities:
        c = cities.setdefault(l["city"], {"city": l["city"], "locality_count": 0,
            "go": 0, "sample": 0, "wait": 0, "fit_sum": 0.0})
        c["locality_count"] += 1
        c["fit_sum"] += l["goat_fit"]
        c["go"] += l["verdict"] == "GO"
        c["sample"] += l["verdict"] == "SAMPLE-FIRST"
        c["wait"] += l["verdict"] == "WAIT"
    gym_city = Counter(g_["city"] for g_ in gyms)
    store_city = Counter(s_["city"] for s_ in stores)
    city_list = []
    for c in cities.values():
        c["avg_goat_fit"] = round(c.pop("fit_sum") / c["locality_count"], 1)
        c["gym_count"] = gym_city.get(c["city"], 0)
        c["store_count"] = store_city.get(c["city"], 0)
        city_list.append(c)
    city_list.sort(key=lambda c: c["avg_goat_fit"], reverse=True)

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
        },
        "summary": {
            "total_localities": len(localities), "total_gyms": len(gyms),
            "total_stores": len(stores), "total_cities": len(city_list),
            "go": vc.get("GO",0), "sample": vc.get("SAMPLE-FIRST",0), "wait": vc.get("WAIT",0),
        },
        "cities": city_list,
        "localities": localities,
    }
    web = os.path.join(root, "web")
    os.makedirs(web, exist_ok=True)
    with open(os.path.join(web, "data-summary.js"), "w", encoding="utf-8") as f:
        f.write("window.GOAT_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    with open(os.path.join(web, "data-markers.json"), "w", encoding="utf-8") as f:
        json.dump({"gyms": gyms, "stores": stores}, f, ensure_ascii=False)
    return data

if __name__ == "__main__":
    s = build(r"C:\Users\singh\Desktop\GOATLife")
    print("Built. Verdicts:", s["summary"]["go"], "GO /", s["summary"]["sample"],
          "SAMPLE /", s["summary"]["wait"], "WAIT")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest pipeline/tests/test_build.py -v`
Expected: PASS. Then run `python -m pipeline.build` and confirm it prints the verdict counts.

- [ ] **Step 5: Commit**

```bash
git add pipeline/build.py pipeline/tests/test_build.py web/data-summary.js web/data-markers.json
git commit -m "feat(pipeline): build orchestrator emits web data files"
```

---

## Task 7: Frontend shell + design tokens + AppState

**Files:**
- Create: `web/index.html`, `web/styles.css`, `web/state.js`, `web/vercel.json`

**Interfaces:**
- Produces: `AppState` (default-exported object with function slots, mirrors darkstore `state.js`), DOM ids: `#map-container`, `#stat-localities`, `#stat-go`, `#stat-gyms`, `#stat-stores`, `#inspector`, tab buttons `.nav-tab[data-target]`, views `#map-view`, `#leaderboard-view`, `#whitespace-view`, `#gyms-view`, `#margin-view`, `#methodology-view`.

- [ ] **Step 1: Write `web/state.js`**

```javascript
const AppState = {
  selectedCity: null,
  mapInstance: null,
  initMap: null,
  showLocality: null,
  renderLeaderboard: null,
  renderWhitespace: null,
  renderGyms: null,
  initMargin: null,
  renderMethodology: null,
};
export default AppState;
```

- [ ] **Step 2: Write `web/styles.css` (tokens + layout)**

```css
:root{
  --bg-base:#09090b; --bg-surface:#18181b; --bg-hover:#27272a;
  --border:rgba(255,255,255,.08); --text:#fafafa; --text2:#a1a1aa; --text3:#71717a;
  --goat-gold:#F5A623; --go:#059669; --sample:#d97706; --wait:#52525b;
  --radius:4px; --font:'Outfit',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--bg-base);color:var(--text);min-height:100vh}
header{max-width:1400px;margin:0 auto 1.5rem;padding:1.5rem 2rem;border-bottom:1px solid var(--border)}
header h1{font-size:1.5rem;font-weight:700}
header h1 span{color:var(--goat-gold)}
header p{color:var(--text2);font-size:.85rem;margin-top:.25rem}
.nav-tabs{display:flex;gap:2px;background:var(--bg-surface);border:1px solid var(--border);padding:2px;border-radius:var(--radius);margin-top:1rem;width:fit-content;flex-wrap:wrap}
.nav-tab{background:transparent;border:none;color:var(--text2);padding:.4rem 1rem;border-radius:2px;font-family:var(--font);font-size:.85rem;font-weight:500;cursor:pointer}
.nav-tab.active{color:#fff;background:var(--bg-hover)}
main{max-width:1400px;margin:0 auto;padding:0 2rem 3rem}
.page-view{display:none}
.page-view.active{display:block}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:1.5rem}
.stat-card{background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);padding:1rem}
.stat-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.5px;color:var(--text3);font-weight:600}
.stat-val{font-size:1.75rem;font-weight:700;margin-top:.25rem}
.map-layout{display:flex;height:650px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
#map-container{flex:1;height:100%;background:#09090b}
#inspector{width:340px;flex-shrink:0;overflow-y:auto;background:var(--bg-surface);border-left:1px solid var(--border);padding:1.25rem}
.verdict-badge{display:inline-block;font-size:.65rem;font-weight:700;padding:.15rem .5rem;border-radius:2px;text-transform:uppercase}
.verdict-GO{background:rgba(5,150,105,.15);color:var(--go)}
.verdict-SAMPLE-FIRST{background:rgba(217,119,6,.15);color:var(--sample)}
.verdict-WAIT{background:rgba(82,82,91,.25);color:var(--text2)}
.score-row{margin:.5rem 0}
.score-meta{display:flex;justify-content:space-between;font-size:.7rem;color:var(--text2)}
.score-bar-bg{height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;margin-top:.15rem}
.score-bar-fill{height:100%;background:var(--goat-gold)}
table.lb{width:100%;border-collapse:collapse;font-size:.8rem}
table.lb th,table.lb td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid var(--border)}
table.lb th{color:var(--text3);font-size:.7rem;text-transform:uppercase}
.info{font-size:.7rem;color:var(--text3);margin-top:.4rem;line-height:1.4}
.partial{opacity:.55}
```

- [ ] **Step 3: Write `web/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GOAT Life — Where to Win</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header>
  <h1>GOAT <span>Life</span> — Where to Win</h1>
  <p>Scoring 600 localities, 1,537 gyms & 137 Reliance stores across 10 cities for GOAT Life's next move.</p>
  <nav class="nav-tabs">
    <button class="nav-tab active" data-target="map-view">Map</button>
    <button class="nav-tab" data-target="leaderboard-view">Leaderboard</button>
    <button class="nav-tab" data-target="whitespace-view">Whitespace</button>
    <button class="nav-tab" data-target="gyms-view">Gym Hit-List</button>
    <button class="nav-tab" data-target="margin-view">Margin Reality</button>
    <button class="nav-tab" data-target="methodology-view">Methodology</button>
  </nav>
</header>
<main>
  <div class="stats-row">
    <div class="stat-card"><div class="stat-label">Localities</div><div class="stat-val" id="stat-localities">0</div></div>
    <div class="stat-card"><div class="stat-label">GO localities</div><div class="stat-val" id="stat-go" style="color:var(--go)">0</div></div>
    <div class="stat-card"><div class="stat-label">Gyms</div><div class="stat-val" id="stat-gyms">0</div></div>
    <div class="stat-card"><div class="stat-label">Reliance stores</div><div class="stat-val" id="stat-stores">0</div></div>
  </div>
  <div id="map-view" class="page-view active">
    <div class="map-layout">
      <div id="map-container"></div>
      <div id="inspector"><p class="info">Click a locality on the map to inspect its GOAT-Fit score, verdict, and recommended channel.</p></div>
    </div>
  </div>
  <div id="leaderboard-view" class="page-view"><div id="leaderboard"></div></div>
  <div id="whitespace-view" class="page-view"><div style="height:560px"><canvas id="whitespaceChart"></canvas></div></div>
  <div id="gyms-view" class="page-view"><div id="gyms"></div></div>
  <div id="margin-view" class="page-view"><div id="margin"></div></div>
  <div id="methodology-view" class="page-view"><div id="methodology"></div></div>
</main>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
<script src="data-summary.js"></script>
<script type="module" src="map.js"></script>
<script type="module" src="charts.js"></script>
<script type="module" src="margin.js"></script>
<script type="module" src="methodology.js"></script>
<script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `web/vercel.json`**

```json
{ "cleanUrls": true, "outputDirectory": "." }
```

- [ ] **Step 5: Manual verification**

Run: `python -m http.server 8080 --directory web` then open `http://localhost:8080`.
Expected: header with gold "Life", 6 tabs, 4 stat cards (zeros for now), empty dark map panel. No console errors except modules not yet wired.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/styles.css web/state.js web/vercel.json
git commit -m "feat(web): shell, design tokens, AppState"
```

---

## Task 8: Map view (MapLibre + layers + inspector)

**Files:**
- Create: `web/map.js`, `web/scoreDisplay.js`
- Test: `web/tests/scoreDisplay.test.js`

**Interfaces:**
- Consumes: `window.GOAT_DATA`, `data-markers.json`, `AppState`.
- Produces (in `scoreDisplay.js`, pure + testable):
  - `verdictColor(verdict: string) -> string` — hex for GO/SAMPLE-FIRST/WAIT.
  - `inspectorHTML(loc: object) -> string` — inspector markup for a locality.
- `map.js` registers `AppState.initMap(data, markers)` building MapLibre map with locality circles colored by verdict, gym dots, store squares; click locality → `#inspector` shows `inspectorHTML`.

- [ ] **Step 1: Write the failing test**

```javascript
// web/tests/scoreDisplay.test.js
import { test } from 'node:test';
import assert from 'node:assert';
import { verdictColor, inspectorHTML } from '../scoreDisplay.js';

test('verdictColor maps each verdict', () => {
  assert.equal(verdictColor('GO'), '#059669');
  assert.equal(verdictColor('SAMPLE-FIRST'), '#d97706');
  assert.equal(verdictColor('WAIT'), '#52525b');
});

test('inspectorHTML includes area, score, verdict, channel', () => {
  const html = inspectorHTML({ area:'Sohna Road', city:'Gurugram', goat_fit:82.5,
    verdict:'GO', channel:'Blinkit + B2B', affluence:90, fitness:80, corporate:70, youth:40,
    partial_data:false });
  assert.ok(html.includes('Sohna Road'));
  assert.ok(html.includes('82.5'));
  assert.ok(html.includes('GO'));
  assert.ok(html.includes('Blinkit + B2B'));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/tests/scoreDisplay.test.js`
Expected: FAIL — cannot find module `../scoreDisplay.js`.

- [ ] **Step 3: Write `web/scoreDisplay.js`**

```javascript
export function verdictColor(verdict){
  return verdict === 'GO' ? '#059669' : verdict === 'SAMPLE-FIRST' ? '#d97706' : '#52525b';
}
function bar(label, val){
  const v = val == null ? 0 : val;
  const txt = val == null ? 'n/a' : Math.round(val);
  return `<div class="score-row"><div class="score-meta"><span>${label}</span><span>${txt}</span></div>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${v}%"></div></div></div>`;
}
export function inspectorHTML(loc){
  return `
    <div class="result-header" style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">
      <h3 style="font-size:.95rem">${loc.area}</h3>
      <span class="verdict-badge verdict-${loc.verdict}">${loc.verdict}</span>
    </div>
    <p class="info">${loc.city}${loc.partial_data ? ' · partial data' : ''}</p>
    <div style="font-size:2rem;font-weight:700;color:var(--goat-gold);margin:.5rem 0">${loc.goat_fit}<span style="font-size:.8rem;color:var(--text3)">/100 GOAT-Fit</span></div>
    <div class="info" style="margin-bottom:.5rem">Recommended channel: <strong style="color:var(--text)">${loc.channel}</strong></div>
    ${bar('Affluence', loc.affluence)}
    ${bar('Fitness density', loc.fitness)}
    ${bar('Corporate density', loc.corporate)}
    ${bar('Youth density', loc.youth)}
  `;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test web/tests/scoreDisplay.test.js`
Expected: 2 tests pass.

- [ ] **Step 5: Write `web/map.js`**

```javascript
import AppState from './state.js';
import { verdictColor, inspectorHTML } from './scoreDisplay.js';

function geojson(points, propsFn){
  return { type:'FeatureCollection', features: points
    .filter(p => p.lat != null && p.lng != null)
    .map(p => ({ type:'Feature', geometry:{type:'Point',coordinates:[p.lng,p.lat]}, properties: propsFn(p) })) };
}

function initMap(data, markers){
  const map = new maplibregl.Map({
    container:'map-container', style:'https://tiles.openfreemap.org/styles/dark',
    center:[78.9629,20.5937], zoom:4.5, minZoom:3, maxZoom:16,
  });
  AppState.mapInstance = map;
  map.addControl(new maplibregl.NavigationControl(), 'top-right');

  map.on('load', () => {
    // stores (squares) and gyms (small dots) underneath localities
    map.addSource('stores', { type:'geojson', data: geojson(markers.stores, s => ({name:s.name})) });
    map.addLayer({ id:'stores', type:'circle', source:'stores',
      paint:{ 'circle-radius':4, 'circle-color':'#3b82f6', 'circle-opacity':.6 } });

    map.addSource('gyms', { type:'geojson', data: geojson(markers.gyms, g => ({name:g.name})) });
    map.addLayer({ id:'gyms', type:'circle', source:'gyms',
      paint:{ 'circle-radius':2.5, 'circle-color':'#a1a1aa', 'circle-opacity':.5 } });

    const locProps = l => ({ idx: data.localities.indexOf(l), verdict:l.verdict, fit:l.goat_fit });
    map.addSource('localities', { type:'geojson',
      data: geojson(data.localities, locProps) });
    map.addLayer({ id:'localities', type:'circle', source:'localities',
      paint:{
        'circle-radius':['interpolate',['linear'],['get','fit'],0,4,100,11],
        'circle-color':['match',['get','verdict'],'GO','#059669','SAMPLE-FIRST','#d97706','#52525b'],
        'circle-stroke-width':1, 'circle-stroke-color':'#09090b', 'circle-opacity':.85,
      } });

    map.on('click','localities',(e)=>{
      const idx = e.features[0].properties.idx;
      AppState.showLocality(data.localities[idx]);
    });
    map.on('mouseenter','localities',()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave','localities',()=>map.getCanvas().style.cursor='');
  });
}

function showLocality(loc){
  document.getElementById('inspector').innerHTML = inspectorHTML(loc);
  if (AppState.mapInstance && loc.lat != null){
    AppState.mapInstance.easeTo({ center:[loc.lng,loc.lat], zoom:11, duration:700 });
  }
}

AppState.initMap = initMap;
AppState.showLocality = showLocality;
```

- [ ] **Step 6: Write `web/app.js` (orchestrator + two-phase load + tabs)**

```javascript
import AppState from './state.js';

document.addEventListener('DOMContentLoaded', () => {
  const data = window.GOAT_DATA;
  if (!data){ console.error('GOAT_DATA missing'); return; }

  document.getElementById('stat-localities').textContent = data.summary.total_localities;
  document.getElementById('stat-go').textContent = data.summary.go;
  document.getElementById('stat-gyms').textContent = data.summary.total_gyms.toLocaleString();
  document.getElementById('stat-stores').textContent = data.summary.total_stores;

  if (AppState.initMargin) AppState.initMargin();
  if (AppState.renderMethodology) AppState.renderMethodology(data);
  if (AppState.renderLeaderboard) AppState.renderLeaderboard(data);

  fetch('data-markers.json').then(r=>r.json()).then(markers => {
    AppState.markers = markers;
    if (AppState.initMap) AppState.initMap(data, markers);
    if (AppState.renderGyms) AppState.renderGyms(data, markers);
    if (AppState.renderWhitespace) AppState.renderWhitespace(data);
  }).catch(e=>console.error('markers load failed', e));

  const tabs = document.querySelectorAll('.nav-tab');
  const views = document.querySelectorAll('.page-view');
  tabs.forEach(tab => tab.addEventListener('click', () => {
    const id = tab.dataset.target;
    tabs.forEach(t=>t.classList.remove('active'));
    views.forEach(v=>v.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(id).classList.add('active');
    if (id === 'map-view' && AppState.mapInstance) setTimeout(()=>AppState.mapInstance.resize(),100);
  }));
});
```

- [ ] **Step 7: Manual verification**

Run: `python -m http.server 8080 --directory web` → open browser. Expected: stats populate (600 / GO count / 1,537 / 137); map shows colored locality dots (green/amber/grey), faint gym dots, blue store dots; clicking a locality fills the inspector with score bars + verdict + channel and zooms in.

- [ ] **Step 8: Commit**

```bash
git add web/map.js web/scoreDisplay.js web/app.js web/tests/scoreDisplay.test.js
git commit -m "feat(web): MapLibre map, locality inspector, two-phase load"
```

---

## Task 9: Leaderboard + Whitespace + Gym hit-list

**Files:**
- Create: `web/charts.js`

**Interfaces:**
- Consumes: `window.GOAT_DATA`, markers, `AppState`, Chart.js global, `verdictColor`.
- Produces: registers `AppState.renderLeaderboard(data)`, `AppState.renderWhitespace(data)`, `AppState.renderGyms(data, markers)`.

- [ ] **Step 1: Write `web/charts.js`**

```javascript
import AppState from './state.js';
import { verdictColor } from './scoreDisplay.js';

function renderLeaderboard(data){
  const rows = [...data.localities].sort((a,b)=>b.goat_fit-a.goat_fit).slice(0,50);
  document.getElementById('leaderboard').innerHTML = `
    <table class="lb"><thead><tr>
      <th>#</th><th>Locality</th><th>City</th><th>GOAT-Fit</th><th>Verdict</th><th>Channel</th>
    </tr></thead><tbody>
    ${rows.map((l,i)=>`<tr class="${l.partial_data?'partial':''}">
      <td>${i+1}</td><td>${l.area}</td><td>${l.city}</td>
      <td style="color:var(--goat-gold);font-weight:600">${l.goat_fit}</td>
      <td><span class="verdict-badge verdict-${l.verdict}">${l.verdict}</span></td>
      <td>${l.channel}</td></tr>`).join('')}
    </tbody></table>`;
}

function renderWhitespace(data){
  const pts = data.localities.filter(l => l.affluence != null);
  const ds = pts.map(l => ({ x:l.goat_fit, y:l.affluence, r:Math.max(4,(l.fitness||0)/8), loc:l }));
  new Chart(document.getElementById('whitespaceChart').getContext('2d'), {
    type:'bubble',
    data:{ datasets:[{ data:ds,
      backgroundColor: pts.map(l=>verdictColor(l.verdict)+'b3'),
      borderColor: pts.map(l=>verdictColor(l.verdict)) }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:(c)=>{
        const l=c.raw.loc; return [`${l.area} (${l.city})`,`GOAT-Fit ${l.goat_fit} · Affluence ${Math.round(l.affluence)}`,
          l.has_store?'Has Reliance store':'No modern retail', l.channel]; } } } },
      scales:{
        x:{ title:{display:true,text:'GOAT-Fit Score'}, grid:{color:'rgba(255,255,255,.05)'} },
        y:{ title:{display:true,text:'Affluence percentile'}, grid:{color:'rgba(255,255,255,.05)'} } } }
  });
}

function renderGyms(data, markers){
  const fitByPin = {};
  data.localities.forEach(l=>{ if(l.pincode!=null) fitByPin[String(l.pincode).trim()] = Math.max(fitByPin[String(l.pincode).trim()]||0, l.goat_fit); });
  const ranked = markers.gyms
    .map(g=>({...g, fit: fitByPin[String(g.pincode).trim()] ?? null}))
    .filter(g=>g.fit!=null)
    .sort((a,b)=>b.fit-a.fit).slice(0,60);
  document.getElementById('gyms').innerHTML = `
    <p class="info" style="margin-bottom:.75rem">Top gyms ranked by the GOAT-Fit of their locality pincode — sampling/partnership priority.</p>
    <table class="lb"><thead><tr><th>#</th><th>Gym</th><th>City</th><th>Area GOAT-Fit</th></tr></thead><tbody>
    ${ranked.map((g,i)=>`<tr><td>${i+1}</td><td>${g.name}</td><td>${g.city}</td>
      <td style="color:var(--goat-gold);font-weight:600">${g.fit}</td></tr>`).join('')}
    </tbody></table>`;
}

AppState.renderLeaderboard = renderLeaderboard;
AppState.renderWhitespace = renderWhitespace;
AppState.renderGyms = renderGyms;
```

- [ ] **Step 2: Manual verification**

Reload the dev server. Expected: **Leaderboard** tab shows top-50 localities with verdict badges + channels; **Whitespace** tab shows a bubble chart (x=GOAT-Fit, y=affluence, colored by verdict); **Gym Hit-List** shows top-60 gyms by area fit. No console errors.

- [ ] **Step 3: Commit**

```bash
git add web/charts.js
git commit -m "feat(web): leaderboard, whitespace bubble, gym hit-list"
```

---

## Task 10: Margin Reality calculator (ported QCompass engine)

**Files:**
- Create: `web/margin.js`
- Test: `web/tests/margin.test.js`

**Interfaces:**
- Consumes: `AppState`, DOM `#margin`.
- Produces (pure + testable):
  - `calcEconomics({mrp, grossMarginPercent, brandDiscountPercent, commissionRate, fulfilmentFee, logisticsRate, returnsRate, monthlyAdBudget, monthlyOrders}) -> {netRealization, netContribution, netContributionPercent, isViable}`.
  - `getVerdict({grossMarginPercent, netRealization, monthlyAdBudget}) -> 'GO'|'CAUTION'|'STOP'`.
- Registers `AppState.initMargin()` rendering the interactive form pre-filled with GOAT defaults.

- [ ] **Step 1: Write the failing test**

```javascript
// web/tests/margin.test.js
import { test } from 'node:test';
import assert from 'node:assert';
import { calcEconomics, getVerdict } from '../margin.js';

test('netRealization = effSP*(1-commission) - fulfilment', () => {
  const r = calcEconomics({ mrp:119, grossMarginPercent:57, brandDiscountPercent:16,
    commissionRate:0.179, fulfilmentFee:50, logisticsRate:0.10, returnsRate:0.025,
    monthlyAdBudget:250000, monthlyOrders:500 });
  // effSP = 119*0.84 = 99.96 ; net real = 99.96*0.821 - 50 = 32.07
  assert.ok(Math.abs(r.netRealization - 32.07) < 0.5);
});

test('verdict STOP when margin below 50', () => {
  assert.equal(getVerdict({grossMarginPercent:45, netRealization:300, monthlyAdBudget:300000}), 'STOP');
});
test('verdict GO when all thresholds clear', () => {
  assert.equal(getVerdict({grossMarginPercent:70, netRealization:260, monthlyAdBudget:250000}), 'GO');
});
test('verdict CAUTION in the middle', () => {
  assert.equal(getVerdict({grossMarginPercent:60, netRealization:200, monthlyAdBudget:150000}), 'CAUTION');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/tests/margin.test.js`
Expected: FAIL — cannot find module `../margin.js`.

- [ ] **Step 3: Write `web/margin.js`**

```javascript
import AppState from './state.js';

export function calcEconomics({mrp, grossMarginPercent, brandDiscountPercent=0,
  commissionRate=0.179, fulfilmentFee=50, logisticsRate=0.10, returnsRate=0.025,
  monthlyAdBudget=250000, monthlyOrders=500}){
  const effSP = mrp * (1 - brandDiscountPercent/100);
  const cogs = mrp * (1 - grossMarginPercent/100);
  const logistics = mrp * logisticsRate;
  const returns = mrp * returnsRate;
  const adPerOrder = monthlyOrders > 0 ? monthlyAdBudget / monthlyOrders : 0;
  const netRealization = effSP * (1 - commissionRate) - fulfilmentFee;
  const netContribution = netRealization - cogs - logistics - returns - adPerOrder;
  return {
    netRealization: Math.round(netRealization*100)/100,
    netContribution: Math.round(netContribution*100)/100,
    netContributionPercent: Math.round(netContribution/mrp*1000)/10,
    isViable: netContribution > 0,
  };
}

// QCompass getViabilityVerdict thresholds (exact)
export function getVerdict({grossMarginPercent, netRealization, monthlyAdBudget}){
  if (grossMarginPercent < 50 || netRealization < 150 || monthlyAdBudget < 100000) return 'STOP';
  if (grossMarginPercent >= 65 && netRealization >= 250 && monthlyAdBudget >= 200000) return 'GO';
  return 'CAUTION';
}

const COLOR = { GO:'#059669', CAUTION:'#d97706', STOP:'#991B1B' };

function render(){
  const el = document.getElementById('margin');
  el.innerHTML = `
    <h2 style="font-size:1.1rem;margin-bottom:.25rem">Margin Reality — GOAT Life on Blinkit</h2>
    <p class="info" style="margin-bottom:1rem">Pre-filled with GOAT Life's real Blinkit economics (₹119 MRP, ₹99 selling, 57% gross margin). Edit any field.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.75rem;max-width:720px">
      ${field('MRP (₹)','m-mrp',119)}
      ${field('Gross margin (%)','m-gm',57)}
      ${field('Brand discount (%)','m-disc',16)}
      ${field('Commission (%)','m-comm',17.9)}
      ${field('Fulfilment fee (₹)','m-ful',50)}
      ${field('Monthly ad budget (₹)','m-ad',250000)}
      ${field('Monthly orders','m-ord',500)}
    </div>
    <div id="m-out" style="margin-top:1.25rem;max-width:720px"></div>`;
  el.querySelectorAll('input').forEach(i=>i.addEventListener('input', update));
  update();
}
function field(label,id,val){
  return `<div><label class="info" for="${id}">${label}</label>
    <input id="${id}" type="number" value="${val}" style="width:100%;padding:.5rem;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-family:var(--font)"></div>`;
}
function num(id){ return parseFloat(document.getElementById(id).value) || 0; }
function update(){
  const mrp=num('m-mrp'), gm=num('m-gm');
  const r = calcEconomics({ mrp, grossMarginPercent:gm, brandDiscountPercent:num('m-disc'),
    commissionRate:num('m-comm')/100, fulfilmentFee:num('m-ful'),
    monthlyAdBudget:num('m-ad'), monthlyOrders:num('m-ord') });
  const v = getVerdict({ grossMarginPercent:gm, netRealization:r.netRealization, monthlyAdBudget:num('m-ad') });
  document.getElementById('m-out').innerHTML = `
    <div style="border:2px solid ${COLOR[v]};border-radius:var(--radius);padding:1rem;background:rgba(255,255,255,.02)">
      <span class="verdict-badge" style="background:${COLOR[v]};color:#fff">${v}</span>
      <div style="display:flex;gap:2rem;margin-top:.75rem;flex-wrap:wrap">
        <div><div class="stat-label">Net realization</div><div class="stat-val">₹${r.netRealization}</div></div>
        <div><div class="stat-label">Net contribution / order</div><div class="stat-val" style="color:${r.isViable?'var(--go)':'#f87171'}">₹${r.netContribution}</div></div>
        <div><div class="stat-label">Contribution %</div><div class="stat-val">${r.netContributionPercent}%</div></div>
      </div>
      <p class="info" style="margin-top:.75rem">Net realization = selling price × (1 − commission) − fulfilment. Contribution subtracts COGS, logistics (10%), returns (2.5%), and ad/order. Thresholds: QCompass GO/CAUTION/STOP.</p>
    </div>`;
}
AppState.initMargin = render;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test web/tests/margin.test.js`
Expected: 4 tests pass.

- [ ] **Step 5: Manual verification**

Reload dev server → Margin Reality tab. Expected: form pre-filled with GOAT numbers; verdict badge updates live as you edit (default ~STOP at 500 orders because ad/order dominates — matches the QCompass screenshot). Raising orders to ~14,000 flips contribution positive.

- [ ] **Step 6: Commit**

```bash
git add web/margin.js web/tests/margin.test.js
git commit -m "feat(web): interactive margin calculator (QCompass port)"
```

---

## Task 11: Methodology panel + README + deploy config

**Files:**
- Create: `web/methodology.js`, `README.md`

**Interfaces:**
- Consumes: `window.GOAT_DATA`, `AppState`, `#methodology`.
- Produces: registers `AppState.renderMethodology(data)`.

- [ ] **Step 1: Write `web/methodology.js`**

```javascript
import AppState from './state.js';

function renderMethodology(data){
  const w = data.meta.weights, g = data.meta.geocode_coverage;
  document.getElementById('methodology').innerHTML = `
    <h2 style="font-size:1.1rem;margin-bottom:.75rem">Methodology & Data Transparency</h2>
    <p class="info">GOAT-Fit Score (0–100) per locality, weighted composite of percentile-ranked sub-scores:</p>
    <ul style="margin:.5rem 0 1rem 1.2rem;font-size:.85rem;color:var(--text2)">
      <li>Affluence (residential ₹/sqft) — weight ${w.affluence}</li>
      <li>Fitness density (gyms in pincode) — weight ${w.fitness}</li>
      <li>Corporate density (named employment hubs) — weight ${w.corporate}</li>
      <li>Youth density (educational institutes) — weight ${w.youth}</li>
    </ul>
    <p class="info">Missing sub-scores (e.g. localities without price data) are excluded and their weight redistributed; such localities are flagged <span class="partial">partial data</span>. No values are imputed.</p>
    <p class="info" style="margin-top:.75rem">Verdict bands: GO ≥ 70 · SAMPLE-FIRST 45–69 · WAIT &lt; 45.</p>
    <p class="info" style="margin-top:.75rem"><strong style="color:var(--text)">Geocoding (offline, pincode-centroid via pgeocode):</strong>
      localities ${g.magicbricks_hit}/${g.magicbricks_total}, gyms ${g.gyms_hit}/${g.gyms_total}, stores ${g.stores_hit}/${g.stores_total}.
      Pincode-centroid means localities sharing a pincode share a point — directional, not survey-grade.</p>
    <p class="info" style="margin-top:.75rem">Sources: Magicbricks (localities), JustDial (gyms), Reliance Smart Bazaar store locator. Margin engine ports QCompass (Morgan Stanley Q3 FY26 Blinkit 17.9% commission). Generated ${data.meta.generated}.</p>`;
}
AppState.renderMethodology = renderMethodology;
```

- [ ] **Step 2: Write `README.md`**

```markdown
# GOAT Life — Where to Win

A geographic intelligence console that scores 600 localities, 1,537 gyms, and 137 Reliance
Smart Bazaar stores across 10 Indian cities for GOAT Life's expansion decisions.

## What it does
- **GOAT-Fit Score (0–100)** per locality: affluence + gym density + corporate density + youth.
- **GO / SAMPLE-FIRST / WAIT** verdict + recommended channel (Blinkit/B2B, D2C subscription, gym partnership, offline).
- Map, city leaderboard, whitespace finder, gym partnership hit-list, and an interactive
  margin calculator pre-filled with GOAT Life's real Blinkit economics.

## Build the data
```
pip install -r requirements.txt
python -m pipeline.build
```
Generates `web/data-summary.js` and `web/data-markers.json`.

## Run
```
python -m http.server 8080 --directory web
# open http://localhost:8080
```

## Test
```
python -m pytest pipeline/tests -v
node --test web/tests
```

## Stack
Python (openpyxl, pgeocode) · vanilla JS + MapLibre GL JS · Chart.js · static, zero-build. Deploy: Vercel (`web/` as root).

Built as a portfolio piece — the convergence of darkstore v1 (spatial engine), DATA 22-26 (whitespace),
QCompass (margin/verdict engine), and D2C_QC_Playbook (margin tiers).
```

- [ ] **Step 3: Manual verification**

Reload dev server → Methodology tab shows weights, verdict bands, and live geocoding coverage numbers from `data.meta`. Run the full test suite: `python -m pytest pipeline/tests -v` (all pass) and `node --test web/tests` (all pass).

- [ ] **Step 4: Commit**

```bash
git add web/methodology.js README.md
git commit -m "feat(web): methodology panel + README"
```

---

## Task 12: End-to-end verification + deploy

**Files:**
- Modify: none (verification + deploy only)

- [ ] **Step 1: Full rebuild from clean data**

Run: `python -m pipeline.build`
Expected: prints verdict counts (GO/SAMPLE/WAIT); `web/data-summary.js` + `web/data-markers.json` regenerated.

- [ ] **Step 2: Full test suite**

Run: `python -m pytest pipeline/tests -v && node --test web/tests`
Expected: all Python + JS tests pass.

- [ ] **Step 3: Manual smoke across all tabs**

Run: `python -m http.server 8080 --directory web`. Verify each tab: Map (colored dots + inspector + zoom), Leaderboard (top 50), Whitespace (bubble), Gym Hit-List (top 60), Margin Reality (live verdict), Methodology (coverage numbers). Confirm no console errors.

- [ ] **Step 4: Deploy to Vercel**

Run: `cd web && vercel --prod` (or connect the repo and set root directory to `web/`).
Expected: a live URL serving the dashboard.

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "chore: end-to-end verification + deploy config"
```

---

## Scope Addendum (approved 2026-06-25): full-column utilization + darkstore serviceability

**Modifications to existing tasks:**
- **Task 2 (loaders):** `load_localities` must also capture every remaining column into the dict:
  `physical_infra` (col 4), `intro` (col 5), `social_infra` (col 6), `transport` (col 9),
  `shopping` (col 10), `hospital` (col 11), `nearby` (col 12), `tourist` (col 13), `url` (col 15).
- **Task 5 (score):** add `route_channel` use of archetype; nothing else changes.
- **Task 6 (build):** copy darkstore data into `web/darkstores.json`; attach serviceability + enrichment
  fields (Tasks 12–13) to each locality before emit; add brand darkstore counts to `meta`.
- **Old Task 12 (deploy) → renumbered Task 15, and remains ON HOLD until the user says go.**

---

### Task 12: Darkstore ingest + QC serviceability

**Files:**
- Create: `pipeline/darkstores.py`
- Test: `pipeline/tests/test_darkstores.py`

**Interfaces:**
- Produces:
  - `load_darkstores(path: str) -> list[dict]` — reads darkstore `data-markers.json`, returns
    `[{lat,lng,brand,city,name}]`; normalizes city (`Delhi`→`New Delhi`, `Bengaluru`→`Bangalore`).
  - `haversine_km(lat1,lng1,lat2,lng2) -> float`.
  - `attach_serviceability(localities, darkstores, radius=3.5) -> None` — adds per locality:
    `nearest_darkstore_km` (float|None), `nearest_by_brand` ({brand:km}), `qc_serviceable` (bool).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_darkstores.py
from pipeline.darkstores import load_darkstores, haversine_km, attach_serviceability
import os
ROOT = r"C:\Users\singh\Desktop\GOATLife"

def test_haversine_known():
    # ~ Connaught Place to Gurugram ~ 25-30km
    d = haversine_km(28.6315, 77.2167, 28.4595, 77.0266)
    assert 20 < d < 35

def test_load_darkstores_normalizes_city():
    ds = load_darkstores(os.path.join(ROOT, "web", "darkstores.json"))
    assert len(ds) == 4081
    cities = set(d["city"] for d in ds)
    assert "New Delhi" in cities and "Delhi" not in cities

def test_attach_serviceability():
    locs = [{"lat":28.4595,"lng":77.0266}]  # Gurugram point
    ds = [{"lat":28.4600,"lng":77.0270,"brand":"Blinkit","city":"Gurugram","name":"X"}]
    attach_serviceability(locs, ds, radius=3.5)
    assert locs[0]["qc_serviceable"] is True
    assert locs[0]["nearest_darkstore_km"] < 1
    assert "Blinkit" in locs[0]["nearest_by_brand"]
```

- [ ] **Step 2: Run to verify fail** — `python -m pytest pipeline/tests/test_darkstores.py -v` → ModuleNotFoundError.
      (First copy the source: `cp "C:/Users/singh/Desktop/darkstore version 1/data-markers.json" web/darkstores.json`.)

- [ ] **Step 3: Implement**

```python
# pipeline/darkstores.py
import json, math

_CITY_FIX = {"Delhi": "New Delhi", "Bengaluru": "Bangalore"}

def load_darkstores(path):
    raw = json.load(open(path, encoding="utf-8"))["markers"]
    out = []
    for m in raw:
        out.append({"lat": m["lat"], "lng": m["lng"], "brand": m["brand"],
                    "city": _CITY_FIX.get(m["city"], m["city"]), "name": m.get("name","")})
    return out

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2-lat1); dlng = math.radians(lng2-lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return R*2*math.atan2(math.sqrt(a), math.sqrt(1-a))

def attach_serviceability(localities, darkstores, radius=3.5):
    # bucket darkstores into a 0.1deg grid for speed (~11km cells)
    grid = {}
    for d in darkstores:
        if d["lat"] is None: continue
        key = (round(d["lat"]/0.1), round(d["lng"]/0.1))
        grid.setdefault(key, []).append(d)
    for l in localities:
        if l.get("lat") is None:
            l["nearest_darkstore_km"]=None; l["nearest_by_brand"]={}; l["qc_serviceable"]=False; continue
        gk = (round(l["lat"]/0.1), round(l["lng"]/0.1))
        by_brand = {}
        nearest = None
        for di in (-1,0,1):
            for dj in (-1,0,1):
                for d in grid.get((gk[0]+di, gk[1]+dj), []):
                    km = haversine_km(l["lat"], l["lng"], d["lat"], d["lng"])
                    if nearest is None or km < nearest: nearest = km
                    if d["brand"] not in by_brand or km < by_brand[d["brand"]]:
                        by_brand[d["brand"]] = round(km,2)
        l["nearest_darkstore_km"] = round(nearest,2) if nearest is not None else None
        l["nearest_by_brand"] = by_brand
        l["qc_serviceable"] = nearest is not None and nearest <= radius
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest pipeline/tests/test_darkstores.py -v` → 3 passed.
- [ ] **Step 5: Commit** — `git add pipeline/darkstores.py pipeline/tests/test_darkstores.py web/darkstores.json && git commit -m "feat(pipeline): darkstore ingest + QC serviceability"`

---

### Task 13: Locality enrichment (infra parse, activation, archetype, health, adjacency)

**Files:**
- Create: `pipeline/enrich.py`
- Test: `pipeline/tests/test_enrich.py`

**Interfaces:**
- Produces:
  - `parse_physical_infra(text) -> dict` → `{"metro_connected": bool, "airport_min": int|None}`.
  - `activation_venues(loc) -> list[dict]` → `[{"type":"metro|mall|cafe|tourist","name":str}]` from
    transport/shopping/social_infra/tourist columns (comma-split named entities, max 6).
  - `classify_archetype(loc) -> str` → `"Corporate Belt"|"Premium Residential"|"Student Hub"|"Commercial/Retail"|"Emerging"`.
  - `health_ecosystem(loc) -> bool` → hospital column has ≥1 named entity.
  - `attach_enrichment(localities) -> None` — adds `metro_connected, airport_min, activation, archetype, health_ecosystem`.
  - Adjacency (`nearby` raw string) is passed through to the frontend as `nearby_raw` (already loaded in Task 2).

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_enrich.py
from pipeline.enrich import parse_physical_infra, activation_venues, classify_archetype, health_ecosystem

def test_parse_physical_infra():
    t = "Nearest metro station is Huda City Centre. IGI Airport can be accessed within 30-40 minutes."
    r = parse_physical_infra(t)
    assert r["metro_connected"] is True
    assert r["airport_min"] == 40

def test_activation_venues():
    loc = {"transport":"Sector 54 Chowk", "shopping":"Sapphire Mall, Omaxe Wedding Mall",
           "social_infra":"", "tourist":"N/A"}
    v = activation_venues(loc)
    types = {x["type"] for x in v}
    assert "metro" in types and "mall" in types
    assert any(x["name"]=="Sapphire Mall" for x in v)

def test_classify_archetype():
    assert classify_archetype({"corporate":90,"affluence":40,"youth":20,"intro":"commercial corridor"}) == "Corporate Belt"
    assert classify_archetype({"corporate":20,"affluence":90,"youth":20,"intro":"residential locality"}) == "Premium Residential"
    assert classify_archetype({"corporate":20,"affluence":30,"youth":90,"intro":""}) == "Student Hub"
    assert classify_archetype({"corporate":10,"affluence":10,"youth":10,"intro":""}) == "Emerging"

def test_health_ecosystem():
    assert health_ecosystem({"hospital":"Medanta, Artemis Hospital"}) is True
    assert health_ecosystem({"hospital":"N/A"}) is False
```

- [ ] **Step 2: Run to verify fail** — `python -m pytest pipeline/tests/test_enrich.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# pipeline/enrich.py
import re
from pipeline.parse import count_named_entities

def parse_physical_infra(text):
    if not text: return {"metro_connected": False, "airport_min": None}
    t = str(text)
    metro = bool(re.search(r"metro", t, re.I))
    mins = [int(x) for x in re.findall(r"(\d{1,3})\s*[-–]?\s*\d{0,3}\s*minutes", t)]
    # take the largest stated minute figure near 'airport'
    air = None
    m = re.search(r"airport.{0,60}?(\d{1,3})\s*[-–]\s*(\d{1,3})\s*minutes", t, re.I)
    if m: air = int(m.group(2))
    elif re.search(r"airport", t, re.I) and mins: air = max(mins)
    return {"metro_connected": metro, "airport_min": air}

def _entities(text, n=6):
    if not text: return []
    parts = [p.strip() for p in str(text).split(",")]
    return [p for p in parts if p and p.upper() != "N/A"][:n]

def activation_venues(loc):
    out = []
    for name in _entities(loc.get("transport")): out.append({"type":"metro","name":name})
    for name in _entities(loc.get("shopping")): out.append({"type":"mall","name":name})
    for name in _entities(loc.get("social_infra"),3): out.append({"type":"cafe","name":name})
    for name in _entities(loc.get("tourist")): out.append({"type":"tourist","name":name})
    return out[:8]

def classify_archetype(loc):
    c = loc.get("corporate") or 0; a = loc.get("affluence") or 0; y = loc.get("youth") or 0
    intro = (loc.get("intro") or "").lower()
    top = max(c, a, y)
    if top < 35: return "Emerging"
    if "commercial" in intro and c >= a: return "Corporate Belt"
    if c == top: return "Corporate Belt"
    if y == top and y >= 60: return "Student Hub"
    if a == top and "residential" in intro: return "Premium Residential"
    if a == top: return "Premium Residential"
    return "Commercial/Retail"

def health_ecosystem(loc):
    return count_named_entities(loc.get("hospital")) >= 1

def attach_enrichment(localities):
    for l in localities:
        pi = parse_physical_infra(l.get("physical_infra"))
        l["metro_connected"] = pi["metro_connected"]
        l["airport_min"] = pi["airport_min"]
        l["activation"] = activation_venues(l)
        l["archetype"] = classify_archetype(l)
        l["health_ecosystem"] = health_ecosystem(l)
        l["nearby_raw"] = l.get("nearby")
```

- [ ] **Step 4: Run to verify pass** — `python -m pytest pipeline/tests/test_enrich.py -v` → 5 passed.
- [ ] **Step 5: Wire into build** — in `pipeline/build.py`, after `attach_goat_fit`, add:
  `from pipeline.darkstores import load_darkstores, attach_serviceability` /
  `from pipeline.enrich import attach_enrichment` ; call
  `attach_serviceability(localities, load_darkstores(os.path.join(web,"darkstores.json")))` and
  `attach_enrichment(localities)`; add `nearest_by_brand`/`qc_serviceable`/`archetype` into city rollups
  (`qc_ready` count per city) and `meta["darkstores"]={"Blinkit":1954,"Zepto":1089,"Instamart":1038}`.
  Update `route_channel` (Task 5) to prefer `archetype` and require `qc_serviceable` for the Blinkit route.
- [ ] **Step 6: Commit** — `git add pipeline/enrich.py pipeline/tests/test_enrich.py pipeline/build.py && git commit -m "feat(pipeline): full-column enrichment (infra, activation, archetype, health)"`

---

### Task 14: Map darkstore layers + enriched inspector

**Files:**
- Modify: `web/map.js`, `web/scoreDisplay.js`, `web/index.html` (add brand toggle controls)
- Test: extend `web/tests/scoreDisplay.test.js`

**Interfaces:**
- `inspectorHTML(loc)` (extend) now also renders: serviceability tag (`qc_serviceable` + `nearest_by_brand`),
  `archetype`, `activation` venue chips, `health_ecosystem` flag, `nearby_raw` adjacency, `url` source link.
- `map.js` adds 3 darkstore layers (`ds-blinkit`/`ds-zepto`/`ds-instamart`) from `web/darkstores.json`,
  colored gold/purple/orange, with checkbox toggles wired to `setLayoutProperty(...,'visibility',...)`.

- [ ] **Step 1: Extend the failing test**

```javascript
// append to web/tests/scoreDisplay.test.js
import { inspectorHTML } from '../scoreDisplay.js';
test('inspectorHTML shows serviceability, archetype, activation, source', () => {
  const html = inspectorHTML({ area:'Sohna Road', city:'Gurugram', goat_fit:82, verdict:'GO',
    channel:'Blinkit + B2B', affluence:90, fitness:80, corporate:70, youth:40, partial_data:false,
    qc_serviceable:true, nearest_by_brand:{Blinkit:1.2}, archetype:'Corporate Belt',
    activation:[{type:'mall',name:'Sapphire Mall'}], health_ecosystem:true,
    nearby_raw:'Sector 47, Sector 48', url:'https://magicbricks.com/x' });
  assert.ok(html.includes('QC-ready'));
  assert.ok(html.includes('Corporate Belt'));
  assert.ok(html.includes('Sapphire Mall'));
  assert.ok(html.includes('magicbricks.com'));
});
```

- [ ] **Step 2: Run to verify fail** — `node --test web/tests/scoreDisplay.test.js` → new test fails.
- [ ] **Step 3: Extend `inspectorHTML`** to append, after the score bars:
  serviceability line (`qc_serviceable ? 'QC-ready · nearest Blinkit X km' : 'D2C/offline-only'`),
  `archetype` chip, `activation` venue chips (type-colored), `health_ecosystem` flag, an adjacency line
  from `nearby_raw`, and `<a href="url" target="_blank">Source: Magicbricks</a>`.
- [ ] **Step 4: Add darkstore layers + toggles in `map.js`/`index.html`** — load `web/darkstores.json`,
  add 3 circle layers (radius 2, colors `#f59e0b`/`#a855f7`/`#f97316`), checkboxes in a floating control
  toggling each layer's visibility.
- [ ] **Step 5: Run JS tests + manual smoke** — `node --test web/tests` all pass; map shows toggleable
  brand darkstores; clicking a locality shows serviceability + archetype + activation venues + source link.
- [ ] **Step 6: Commit** — `git add web/map.js web/scoreDisplay.js web/index.html web/tests/scoreDisplay.test.js && git commit -m "feat(web): darkstore layers + enriched serviceability inspector"`

---

### Task 15 (renumbered, ON HOLD): End-to-end verification + deploy
Same as the original Task 12 below — **do not run until the user explicitly approves deployment.**

---

## Self-Review Notes

- **Spec coverage:** GOAT-Fit (T4–5), verdict/channel (T5), geocoding incl. coverage flag (T3,T6), all 7 views — map+inspector (T8), leaderboard (T9), whitespace (T9), gym hit-list (T9), margin calculator (T10), methodology (T11); all-India default map (T8, center/zoom 4.5); two-phase load (T8); darkstore tokens + GOAT gold (T7); missing-data redistribution (T5); real GOAT economics defaults (T10). ✔
- **Out-of-scope** items (backend, live scraping, Nominatim refinement, sub-pincode precision) correctly excluded.
- **Type consistency:** `AppState` slot names match across `state.js`/`map.js`/`charts.js`/`margin.js`/`methodology.js`/`app.js`; `verdictColor`/`inspectorHTML` defined in `scoreDisplay.js` (T8) and consumed in `charts.js` (T9); `calcEconomics`/`getVerdict` signatures consistent T10 test ↔ impl.
- **Note for executor:** the project root is not yet a git repo — run `git init` before Task 1, or the commit steps will fail.
