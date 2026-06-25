# GOAT Life — Where to Win

A geographic intelligence console that scores **600 localities, 1,537 gyms, 137 Reliance Smart Bazaar
stores, and 4,081 quick-commerce darkstores** across 10 Indian cities for GOAT Life's expansion decisions.

## What it does
- **GOAT-Fit Score (0–100)** per locality: affluence + gym density + corporate density + youth.
- **GO / SAMPLE-FIRST / WAIT** verdict + recommended channel (Blinkit/B2B, D2C subscription, gym
  partnership, offline) + a **QC-serviceability** tag (darkstore within 3.5 km).
- **Every Magicbricks column used:** transport/malls/cafés/tourist → Activation Playbook; locality intro
  → archetype; hospital → health-ecosystem flag; nearby localities → adjacency; price/employment/education
  → scores.
- Map, city leaderboard, whitespace finder, gym partnership hit-list, and an interactive margin calculator
  pre-filled with GOAT Life's real Blinkit economics.

## Build the data
```
pip install -r requirements.txt
python -m pipeline.build
```
Generates `web/data-summary.js` and `web/data-markers.json` (reads `web/darkstores.json`).

## Run
```
python -m http.server 8080 --directory web
# open http://localhost:8080
```

## Test
```
python -m pytest pipeline/tests -v
node --test web/tests/scoreDisplay.test.js web/tests/margin.test.js
```

## Stack
Python (openpyxl, pgeocode) · vanilla JS + MapLibre GL JS 3.6.2 · Chart.js · static, zero-build.
Deploy: Vercel (`web/` as root).

Built as a portfolio piece — the convergence of darkstore v1 (spatial/serviceability engine),
DATA 22-26 (whitespace), QCompass (margin/verdict engine), and D2C_QC_Playbook (margin tiers).
