# GOAT Life — Where to Win

A geographic decision system for GOAT Life (D2C protein-oats brand): score **1,001 localities** across
10 Indian cities on demand (ICP) **and** quick-commerce reach (darkstore serviceability), and turn that into
ad targets, an interactive map, and budget-fit activation plans.

## Project structure

```
data/            raw input datasets (.xlsx: magicbricks, justdial gyms, reliance stores)
assets/          reference screenshots / images
docs/
  GOAT_LIFE_KNOWLEDGE_BASE.md      brand research dossier
  research/                        analysis guides (ML plan, NB08 + pipeline improvements, consumer-layer spec)
  superpowers/{specs,plans}        design specs + implementation plans
pipeline/        production geo-pipeline (darkstore/QC scoring) — Python package + pytest
notebooks/       ML feature pipeline (NB01–08) -> the serviceable master store
  nb08lib.py + test_nb08lib.py     tested darkstore-serviceability logic
  artifacts/                       generated parquet/embeddings (git-ignored)
scripts/         consumer layer (Python): contract.py, build_locality_data.py, export_push_pincodes.py
web/             consumer dashboard (vanilla JS + MapLibre) — "color = decision" UI
```

## The three layers

1. **ML feature pipeline (`notebooks/`)** — NB01–08 derive a 128+ column feature store from the raw data,
   ending in `localities_master_serviceable.parquet` (ICP score, verdict, archetype, gems, and confidence-aware
   darkstore **serviceability**). `scripts/contract.py` is the single source of truth for GTM actions + costs.
2. **Consumer dashboard (`web/`)** — "Where to Win v2": localities colored by go-to-market action over the
   darkstore supply, a Decision Ledger, profile panel, belts, leaderboard, gems, an attack-sequence engine,
   and a margin calculator.
3. **Ad export (`scripts/export_push_pincodes.py`)** — PUSH-NOW / sample pincodes ready for Meta Ads.

`pipeline/` is the earlier production geo-pipeline (still tested); the dashboard now reads the ML serviceable store.

## Run the dashboard
```
pip install -r requirements.txt
python scripts/build_locality_data.py            # parquet -> web/data-localities.js + data-belts.js
python -m http.server 8092 --directory web       # open http://localhost:8092
```
Regenerate the master store by re-running the notebooks (`notebooks/requirements-ml.txt`); see `docs/research/ML_PLAN.md`.

## Test
```
python -m pytest pipeline/tests -q                       # production pipeline
python -m pytest notebooks/test_nb08lib.py -q            # NB08 serviceability logic
cd scripts && python -m pytest -q                        # data-bundle drift guard
node --test web/tests/frontend.test.js web/tests/sequence.test.js   # frontend pure logic
```

## Stack
Python (pandas, openpyxl, pgeocode, lightgbm, sentence-transformers) · vanilla JS + MapLibre GL JS · static,
zero-build. Deploy: Vercel (`web/` as root). Single data contract: `scripts/contract.py` ↔ `web/contract.js`.
