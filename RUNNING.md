# Running the GOAT Life GTM System

Three things you can do: **run the dashboard**, **export ad pincodes**, or **rebuild the ML pipeline from scratch**. Steps 1–3 cover the common case (dashboard). The ML rebuild is only needed if you've changed the raw data or notebooks.

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (only needed to run frontend tests)
- Git (project already cloned)

---

## 1. Install base dependencies

```bash
pip install -r requirements.txt
```

This installs: `pandas`, `openpyxl`, `pgeocode`, `pytest`.  
Run this once. The parquet file (`notebooks/artifacts/localities_master_serviceable.parquet`) is already generated — you don't need the heavy ML stack just to launch the dashboard.

---

## 2. Build the frontend data bundle

```bash
python scripts/build_locality_data.py
```

Reads `notebooks/artifacts/localities_master_serviceable.parquet` and writes two JS files into `web/`:
- `web/data-localities.js` — 886 geocoded localities with ICP scores, GTM actions, colors
- `web/data-belts.js` — 78+ locality belts (contiguous groups)

Expected output:
```
localities (geocoded): 886 | belts(>=3): 78
gtm distribution: {'SAMPLE + QC test': 450, 'HOLD': 378, 'PUSH-NOW': 97, ...}
```

> If you see `gtm_action drift!` — the parquet and contract.py are out of sync. Re-run NB08 (see Section 5).

---

## 3. Launch the dashboard

```bash
python -m http.server 8092 --directory web
```

Open **http://localhost:8092** in your browser.

### What you'll see

| Tab | What it does |
|-----|-------------|
| **Map** | 886 locality circles colored by GTM action (green = PUSH-NOW, amber = SAMPLE, gray = HOLD) over 4,081 darkstore markers. Click any circle for the full locality profile. |
| **Leaderboard** | Top 60 localities by ICP score with verdict, serviceability, archetype, and action. |
| **Untapped Markets** | Pareto-optimal (70), hidden gems (70), and spillover gems (38) — high-ICP localities with structural advantages. |
| **Launch Roadmap** | Attack-sequence engine: enter city + platform + budget → generates 4 activation waves with afforded localities per wave. |
| **Methodology** | Data caveats, confidence flags, and how GTM actions are assigned. |

---

## 4. Export pincodes for Meta Ads (Product 1)

```bash
python scripts/export_push_pincodes.py
```

Writes three files to `scripts/exports/`:

| File | Contents |
|------|----------|
| `push_now_pincodes.csv` | GO + Confirmed localities with ICP score, archetype, brands, nearest darkstore |
| `sample_test_pincodes.csv` | SAMPLE-FIRST + Confirmed localities |
| `push_now_pincodes.txt` | Deduplicated 6-digit pincodes, one per line — **paste directly into Meta Ads geo-targeting** |

Expected output:
```
Contract OK. Archetypes without an explicit activation cost: none
PUSH-NOW localities: 97 | unique pincodes: 88
SAMPLE-TEST localities: 450 | unique pincodes: 392
```

---

## 5. Run tests

Run all test suites to verify nothing is broken:

```bash
# Python: production pipeline
python -m pytest pipeline/tests -q

# Python: NB08 darkstore serviceability logic (15 assertions)
python -m pytest notebooks/test_nb08lib.py -q

# Python: data bundle drift guard
cd scripts && python -m pytest -q && cd ..

# JS: frontend pure logic (contract colors, wave assignment)
node --test web/tests/frontend.test.js web/tests/sequence.test.js
```

All Python suites should show 0 failures. The JS suite: 13 passing, 1 known failure (`scoreDisplay.test.js` — missing module, deferred).

---

## 6. Rebuild the ML pipeline from scratch (optional)

Only needed if you've changed raw data in `data/` or edited any of the notebooks.

### 6a. Install the ML stack

```bash
pip install -r notebooks/requirements-ml.txt
```

> **Windows note:** If `import torch` fails with a `c10.dll` error, run `pip install msvc-runtime` (no admin rights needed). This is listed in `requirements-ml.txt`.

After install, download the spaCy model:

```bash
python -m spacy download en_core_web_sm
```

### 6b. Run notebooks in order

Open Jupyter and run these in sequence. Each notebook reads the previous one's output from `notebooks/artifacts/`:

| # | Notebook | Output |
|---|----------|--------|
| NB01 | `01_clean_structure.ipynb` | `localities_clean.parquet` |
| NB02 | `02_feature_engineering.ipynb` | `features_base.parquet` |
| NB03 | `03_text_mining.ipynb` | `features_text.parquet` + `embeddings.npy` |
| NB04 | `04_geo_graph.ipynb` | `features_geo_graph.ipynb` |
| NB05 | `05_unsupervised_segmentation.ipynb` | `localities_segmented.parquet` (10 archetypes) |
| NB06 | `06_supervised_imputation_drivers.ipynb` | `features_imputed.parquet` |
| NB07 | `07_similarity_anomaly_synthesis.ipynb` | `localities_features_master.parquet` |
| NB08 | `08_darkstore_serviceability.ipynb` | **`localities_master_serviceable.parquet`** ← dashboard source |

After NB08 finishes, re-run Step 2 (`build_locality_data.py`) to push the new parquet into the frontend.

---

## 8. Sync data into Postgres (Sprint 1+)

The dashboard is migrating from static JS files to a live database. To sync current data in:

```bash
cd scripts
python sync_locality_scores.py          # notebook parquet -> localities + locality_scores
python sync_shelf_snapshots.py blinkit blinkit_oats_data.xlsx   # one call per platform xlsx
```

Requires `DATABASE_URL` set in `.env` (see `.env.example`). Run `python apply_schema.py` once
against a fresh database before the first sync.

---

## 7. Deploy to Vercel (optional)

The `web/` folder is a zero-build static site — no npm, no bundler.

```bash
# Install Vercel CLI if you don't have it
npm i -g vercel

# From the repo root
cd web && vercel
```

`vercel.json` is already configured (`outputDirectory: "."`). The deploy takes ~30 seconds.

---

## Quick reference

| Task | Command |
|------|---------|
| Install base deps | `pip install -r requirements.txt` |
| Build JS data bundle | `python scripts/build_locality_data.py` |
| Launch dashboard | `python -m http.server 8092 --directory web` → http://localhost:8092 |
| Export ad pincodes | `python scripts/export_push_pincodes.py` |
| Run all Python tests | `python -m pytest pipeline/tests notebooks/test_nb08lib.py scripts/ -q` |
| Run JS tests | `node --test web/tests/frontend.test.js web/tests/sequence.test.js` |
| Install ML stack | `pip install -r notebooks/requirements-ml.txt && python -m spacy download en_core_web_sm` |
| Rebuild full pipeline | Run NB01 → NB08 in order, then `build_locality_data.py` |
