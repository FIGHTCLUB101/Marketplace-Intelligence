# GOAT Life — Full-Stack Platform Design

## Why

The "Where to Win" GTM system is currently a batch pipeline: Jupyter notebooks (NB01–NB08) produce a
parquet file, `scripts/build_locality_data.py` flattens it into static JS files, and a vanilla-JS +
MapLibre site reads those files. Every data refresh means manually re-running notebooks, re-running the
build script, and redeploying. It works for one person iterating locally, but it stops working the moment
this needs to be a real product other people rely on: the founder and marketing lead need to see live
data, and they need to annotate localities (mark launched, leave notes) — actions that have to persist
somewhere, not just live in browser state that resets on reload.

Separately, GOAT Life has a working set of Selenium scrapers (Blinkit/Swiggy/Zepto/Magicbricks/Reliance)
producing one-off xlsx snapshots with no history and no connection to the GTM data. This design brings
both under one system: a real database, a live API, and a rewritten frontend, sequenced as four sprints
that each ship something usable on their own.

## Scope decision: what this design covers

This is specifically about **modularizing the existing GTM locality system** (Option 1 of three
considered) — not building a net-new shelf-price-monitoring product from scratch. The scraper
infrastructure already exists outside this repo; this design brings the relevant parts of it in and wires
it to the same database as the locality/ICP data, per the "include competitor ingestion" decision below.

**Constraints locked in during design:**
- Free-tier hosting only.
- Small internal team (founder + marketing lead + you), no auth for now.
- Users need to read live data *and* write annotations (notes/status per locality) — not read-only.
- Notebooks (NB01–NB08) stay as your R&D/experimentation space; only the tail end (NB08 output → DB)
  gets productionized.
- Competitor scraper output (Blinkit/Swiggy/Zepto/GOAT-Life-own-brand) becomes repeatable, versioned
  ingestion into the same database — not a one-off manual merge.
- The scraper stays a **local, manually-triggered, human-in-the-loop** process. It cannot run in a cloud
  cron job: every scraper requires solving CAPTCHAs in a visible browser window. What gets automated is
  everything *after* the scrape finishes (the sync to the database), not the scrape itself.

---

## File audit: what's already in the right place, what needs to move in

Before designing the new architecture, the following was reviewed end-to-end (contents read, not just
listed) to establish ground truth, since the working assumption going in (a Selenium→shelf_history→email
pipeline) turned out not to match what's actually in this repo.

**`GOATLife/notebooks/`** — correctly placed, no action. This is the real ML pipeline (NB01–NB08,
`nb08lib.py` with test coverage, `requirements-ml.txt`) producing `localities_master_serviceable.parquet`.

**`GOATLife/data/`** — correctly placed, no action. Four raw xlsx inputs (`magicbricks_combined.xlsx`,
`magicbricks_localities.xlsx`, `justdial_gyms_manual.xlsx`, `reliance_smart_bazaar_stores.xlsx`) feeding
NB01, per the README.

**The 6 Desktop `.bat` launchers** — bring into the repo as `scraper/*.bat`, each updated to point at the
new in-repo paths and each appended with a call to the new DB-sync step (see Sprint 2). They stay
manually-triggered; only the post-scrape step becomes automatic.

**The 7 scraper `.py` files in `C:\Users\singh\Desktop\SCRAPE\`** — 6 of 7 are relevant and move into a new
`scraper/` module in this repo:

| File | Verdict | Reason |
|---|---|---|
| `scrape_blinkit_goatlife.py` | Bring in | Tracks GOAT Life's own rank/price on Blinkit — the actual shelf-monitor signal. Currently not consumed by anything in this repo. |
| `scrape_blinkit_oats.py` | Bring in | Feeds `blinkit_oats_data.xlsx`, consumed by `enrich_competitor_data.py`. |
| `scrape_swiggy_oats_v2.py` | Bring in | Feeds `swiggy_oats_data.xlsx`. The version actually invoked by the `.bat` file. |
| `scrape_swiggy_oats.py` | **Leave behind** | Superseded v1 — its own docstring lists 6 bugs it had that v2 fixed. The `.bat` file checks for this file's existence but runs v2; that's a latent bug in the launcher, not something to preserve. |
| `scrape_zepto_oats.py` | Bring in (with fixes — see Sprint 2) | Feeds `zepto_oats_data.xlsx`. |
| `scrape_magicbricks_manual.py` | Bring in | Produces `magicbricks_combined.xlsx` — upstream of the entire locality pipeline. |
| `scrape_reliance_manual.py` | Bring in | Produces `reliance_smart_bazaar_stores.xlsx`, already a `data/` input. |

**Left behind in `SCRAPE/`, deliberately:** that folder is a shared scratch workspace for an unrelated
market-research project (Inc42/YourStory/Forbes/Redseer scraping — `pipeline/`, `scrapers/`, `data/`,
`docs/`), two abandoned React app scaffolds (`dashboard/`, `qc-intelligence/`), and roughly 50 one-off
debug/inspect/dump/test scripts used to reverse-engineer DOM selectors. None of it belongs in GOATLife.
Also found: `SCRAPE/shelf_history/` (one dated xlsx) and `SCRAPE/shelf_dashboard.html` — a small prior
prototype of a shelf-monitor dashboard, but with no generator script anywhere producing it and numbers
that don't reconcile with the real GTM data (it claims 500 localities where GOAT Life ranks #1, versus
~97 PUSH-NOW-confirmed localities in the actual pipeline). Treated as a stale, disconnected mockup — not
migrated forward as real functionality, though its one xlsx snapshot can be included in the Sprint 1
backfill if that week of history is worth keeping.

**Gap surfaced by this audit:** `blinkit_goatlife_data.xlsx` (GOAT Life's own-brand shelf tracking) isn't
ingested by anything today — `enrich_competitor_data.py` only reads the three *competitor* files. The
schema below (`shelf_snapshots`, `platform = 'blinkit_goatlife'`) closes this gap.

---

## Program shape: four sprints

| Sprint | Module | Ships |
|---|---|---|
| 1 | **Data layer** — Neon Postgres schema, one-time backfill of the current parquet + existing xlsx snapshots | A queryable DB with full current + historical data. Nothing user-facing yet. |
| 2 | **Ingestion & sync** — scrapers move into the repo (with reliability fixes), each `.bat` ends in a DB-sync call; a GitHub Actions "Run workflow" button syncs new notebook output | Data refresh no longer means manually regenerating JS files. History starts accumulating. |
| 3 | **API** — FastAPI as Vercel Python serverless functions | A live API a frontend (or curl) can hit. |
| 4 | **Frontend rewrite** — Next.js SPA on Vercel, consuming the Sprint-3 API, porting existing views + new annotation UI | The actual product the team uses day to day. |

Each sprint gets its own implementation plan. This spec covers all four because they share one schema and
one data contract — splitting it would just duplicate the schema section four times.

---

## Hosting stack

Vercel-native, chosen for the "free tier only" constraint plus needing a real write path (ruling out a
pure static/CRUD-only approach):

- **Frontend + API:** Next.js and Python serverless functions in the same Vercel project (same-origin,
  no CORS setup, one deploy pipeline).
- **Database:** Neon Postgres (built for pairing with Vercel; pooled/PgBouncer connection string for
  serverless function connections).
- **Scraper→DB sync trigger:** the `.bat` files themselves, run locally (see below — CAPTCHA-solving
  can't be automated in the cloud).
- **Notebook→DB sync trigger:** a GitHub Actions workflow with a manual "Run workflow" button — safe to
  run in CI because it's pure pandas + a DB write, no browser involved.

Two alternatives were considered and rejected: a split Vercel-frontend/Render-API setup (Render's free
tier fully sleeps after 15 minutes idle, causing ~30-50s cold starts — worse than Vercel's ~1-3s, for no
real benefit here) and a Supabase all-in-one setup (fast to build, but the business logic — GTM verdicts,
wave sequencing, margin calculations — isn't simple CRUD, so it would need a bolt-on custom API anyway
and end up as a worse version of the chosen approach).

---

## Data model (Postgres / Neon)

Design principle: one **dimension table** for "what/where a locality is" (stable, rarely changes) plus
**append-only fact tables** for anything re-measured over time (ICP/GTM scores, competitor shelf data).
This gives historical queries for free at near-zero storage cost given the actual row counts (1,001
localities, weekly-ish scrapes).

**`localities`** — dimension, one row per locality, keyed by the same `loc_key` (`area|city`, lowercased)
`enrich_competitor_data.py` already uses to join competitor data. Columns: `locality_id` (PK), `loc_key`
(unique), `area`, `city`, `pincode`, `lat`, `lng`, `belt_id`, `belt_size`, `first_seen_at`.

**`locality_scores`** — append-only, one row per `(locality_id, pipeline_run_id)`. Carries everything
`build_locality_data.py`'s `COLS` list currently computes: `icp_score`, `icp_verdict`, `gtm_action`,
`serviceability_state`, `serviceability_confidence`, `archetype_ml`, `lifecycle`, `n_brands_confirmed`,
`brands_confirmed_list`, `nearest_known_darkstore_km`, the `*_confirmed` platform flags,
`res_avg_buy_imputed`, `employer_quality`, `primary_sector`, `pareto_optimal`, `hidden_gem_v2`,
`spillover_gem`. A `current_locality_scores` view (`DISTINCT ON (locality_id) ORDER BY as_of DESC`) gives
the API "latest state" without ever thinking about history.

**`pipeline_runs`** — one row per notebook→DB sync (`id`, `triggered_at`, `source_parquet_filename`,
`row_count`). What `locality_scores.pipeline_run_id` points to.

**`shelf_snapshots`** — append-only. One table across all 4 scrapers, since their output columns are
consistent enough to share a schema (verified by reading each scraper's row-construction code):
`platform` (`blinkit` / `blinkit_goatlife` / `swiggy` / `zepto`), `locality_id` (FK, matched via
`loc_key`), `brand_searched`, `rank`, `product_name`, `pack_size`, `selling_price`, `mrp`, `discount_pct`,
`stock_left`, `rating`, `reviews` (nullable — Zepto only), `sponsored` (nullable — Swiggy/Zepto only),
`serviceable`, `is_goat` (computed at ingest, same logic as `enrich_competitor_data.py`'s `is_goat()`),
`scrape_run_id`. This is what makes "Mocha Marvel's price in Delhi over 6 months" a real query.

**`scrape_runs`** — one row per scraper execution (`id`, `platform`, `started_at`, `finished_at`,
`row_count`, `source_file`).

**`locality_annotations`** — the write path for the annotate/action requirement: `id`, `locality_id`
(FK), `note` (text, nullable), `status` (free text, e.g. "launched"/"watching"/"deprioritized"),
`budget_note` (numeric, nullable). No `user_id` — no-auth means annotations aren't attributed to a person.

**Deliberately deferred:** a normalized `products` catalog. Product names are free text from scrapers
("Yoga Bar Oats" vs. "Yoga Bar 26% High Protein Oats" differ across runs); forcing a strict product
dimension now means fragile matching logic for a benefit not needed yet. `brand_searched` + `is_goat`
covers the real use cases without it.

---

## Ingestion & sync

**Path 1 — Scraper → DB (local, human-in-the-loop, stays that way).** The 6 scrapers move into
`scraper/` (dropping the dead v1 Swiggy file). Each `.bat` gets one appended line —
`python scraper/sync_to_db.py <platform> <output.xlsx>` — so a double-click does scrape *and* ingest.
`sync_to_db.py` computes `is_goat`/`loc_key` (same logic as today's `enrich_competitor_data.py`), inserts
a `scrape_runs` row, and bulk-inserts into `shelf_snapshots`. No cron, no cloud — this is inherently a
"you're at your desk, solving CAPTCHAs" operation.

**Path 2 — Notebook output → DB (can be a button, since it's pure data transform).**
`scripts/sync_locality_scores.py` replaces `build_locality_data.py`'s JS-writing role: reads
`localities_master_serviceable.parquet`, upserts into `localities`, inserts a `pipeline_runs` row, and
appends the scored columns into `locality_scores`. Runs as a GitHub Actions workflow with a manual
"Run workflow" button — push the new parquet, click the button. Postgres credentials live as a GitHub
Actions secret and a local `.env` (gitignored) for local runs. This script keeps the same drift-guard
pattern `build_locality_data.py` already has (`assert set(df["gtm_action"]...) == set(contract.GTM_ACTIONS)`)
so bad notebook output fails loudly instead of corrupting the live DB.

**Backfill (Sprint 1, one-time):** both sync scripts run once each against everything that already
exists — current parquet, the 3 competitor xlsx, `blinkit_goatlife_data.xlsx`, and optionally the single
`shelf_history/2026-07-02.xlsx` snapshot. After that, the DB is the only source of truth; the standalone
xlsx files become disposable scrape output, not something anyone reads directly again.

**Idempotency:** each sync inserts a fresh `scrape_runs`/`pipeline_runs` row every time, so re-running
against the same file creates a duplicate run rather than corrupting anything. A same-file-hash check can
be added later if accidental double-syncs become a real annoyance; not needed for MVP.

### Scraper reliability fixes (part of Sprint 2, not deferred)

Both Swiggy and Zepto scrapers were reported to crash around ~200 localities, specifically during address
entry, with data gaps afterward. Reading all 4 scrapers end-to-end surfaced one coherent root cause rather
than unrelated bugs: `set_location()` is the heaviest step in every script (a full page reload plus, in
its modal-scanning fallback, `.is_displayed()`/`.text` calls against potentially every `<div>` in a
location-picker modal — dozens to hundreds of browser round-trips per locality), compounded by repeated
`driver.page_source` pulls (one of the most expensive Selenium calls, serializing a whole JS-heavy SPA's
DOM) with a single Chrome process kept alive for the entire multi-hour run. Around ~200 navigations, this
accumulates enough memory pressure to crash the renderer during the heaviest step — matching the reported
symptom exactly. None of the scripts detect or recover from a dead session afterward: `set_location()`'s
retries fail identically against the dead driver, that locality is marked "Location Error," and the outer
loop cascades the same failure through every remaining locality — which is the reported "failure across
all fields/localities."

A shared `scraper/_reliability.py` module, imported by all 4 scraper scripts, replaces near-duplicated
Selenium boilerplate and fixes this:

1. **Periodic driver restart** (every ~25 localities) — quit and recreate the Chrome driver mid-run
   instead of one process for the whole job, preventing memory growth from reaching the crash threshold.
2. **Dead-session auto-recovery** — catch `chrome not reachable` / `invalid session id` specifically,
   recreate the driver, and retry the *current* locality instead of cascading "Location Error" through
   everything after the crash point.
3. **Incremental save via one in-memory `openpyxl` workbook**, appended to and saved periodically —
   replacing Zepto's per-*brand* `load_workbook()`-from-disk-then-save (up to ~5,000 full disk round-trips
   per run) and the other three scripts' per-*locality* full-`DataFrame`-reconstruction, both of which get
   slower as the run accumulates rows.
4. **Resume/dedup logic for Zepto**, matching the pattern the other three already have — currently,
   restarting Zepto after any failure re-scrapes everything from locality 1 and appends duplicate rows on
   top of existing output.
5. **Shared `is_blocked(driver)` check** — title keywords *and* page-body markers ("access denied,"
   "unusual traffic," WAF/Cloudflare strings), with a real pause-and-wait-for-manual-solve loop. Replaces
   Swiggy's give-up-after-30s `wait_for_waf` and Zepto's complete absence of block detection, standardizing
   on the pattern the Blinkit scripts already implement correctly.
6. Randomized jitter on sleep intervals, since fixed uniform timing across hundreds of sequential
   requests to the same origin is itself a signal that gets long sessions flagged.

---

## API layer

FastAPI, Vercel Python serverless functions, same project as the frontend (no CORS). Endpoints derived
directly from what the existing dashboard code (`app.js`, `views.js`, `sequence.js`, `margin.js`)
actually consumes:

| Endpoint | Replaces | Purpose |
|---|---|---|
| `GET /api/localities` | `data-localities.js` | Full current locality + score dataset (`localities` joined to `current_locality_scores`). |
| `GET /api/belts` | `data-belts.js` | Belt aggregation — the `groupby` from `build_locality_data.py`, ported to a SQL view. |
| `GET /api/competitor/history?locality_id=&platform=` | *(new)* | Raw `shelf_snapshots` rows over time. |
| `GET /api/competitor/summary` | `enrich_competitor_data.py` | Latest-run, locality-level competitor rollup, via SQL view instead of a Python merge script. |
| `GET /api/annotations?locality_id=` / `POST /api/annotations` | *(new)* | Read/write the annotate/action feature. |
| `GET /api/meta/freshness` | *(new)* | Last `pipeline_runs`/`scrape_runs` timestamps per platform — "data as of X" indicator for a live multi-user product. |

**Deliberate non-decision:** the attack-sequence engine and margin calculator stay **client-side**,
ported as-is into the Next.js app rather than becoming API endpoints. They're pure functions over the
full locality set already fetched via `/api/localities` (1,001 rows) — server round-trips would add
latency for no benefit at this size, and it preserves the existing test coverage
(`web/tests/sequence.test.js`) without inventing an API-testing layer for logic that doesn't need one.

No auth, so no rate limiting or per-user scoping — consistent with the earlier decision; accepted risk is
"whoever has the link."

---

## Frontend (Next.js rewrite)

Next.js App Router on Vercel. Port the existing tabs 1:1 (Map, Leaderboard, Untapped Markets/Gems, Launch
Roadmap, Methodology) plus two new pieces: an **Annotations panel** and a **Competitor history view**
(price-over-time, backed by `/api/competitor/history`).

Reuse, don't rewrite the logic: `contract.js`, the wave-assignment/`buildSequence` core of `sequence.js`,
and `margin.js`'s calculator are pure, already-tested functions — port them verbatim; only the
DOM-manipulation shell around them becomes React components. Same for the map: keep a thin React wrapper
around the existing vanilla MapLibre calls (`locality-map.js`'s `initMap`/`setLocalityData`/
`highlightBelt`) rather than adopting a heavier map framework.

Data fetching: client fetches `/api/localities` once on load and keeps filtering/sequencing client-side,
same as today. React's built-in state is enough at this scale — no Redux/Zustand.

---

## Testing & error handling

- **API:** pytest against FastAPI endpoints, using a Neon branch or local Postgres as a test DB.
- **Sync scripts:** extend the existing drift-guard pattern into `sync_locality_scores.py` and
  `sync_to_db.py`.
- **Reliability module:** unit-test the parts that don't require a live browser — block-detection against
  saved HTML fixtures, incremental-save/resume logic against a temp file. The Selenium interaction itself
  stays manually verified, as it is today.
- **Frontend:** keep the existing `node --test` pure-logic tests as-is; skip heavy component/UI testing —
  not proportionate to a small internal tool.
- **API error handling:** structured JSON errors, 404 for unknown `locality_id`, automatic 422 via
  Pydantic, 500s logged server-side without leaking stack traces.
- **Frontend error handling:** a failed `/api/localities` fetch shows an explicit "couldn't load data"
  state, not a blank page — this is now a live product other people look at.

---

## Explicitly deferred (not in this design)

- **ML forecasting / anomaly detection** — matches `docs/research/BUILD_CONSUMER_LAYER.md`'s existing
  stance: don't build this until real sales data exists.
- **Per-user auth/attribution** — schema doesn't preclude adding a `user_id` column later.
- **Normalized product catalog** — see Data model section.
- **Saved/named attack-sequence plans** — natural extension of `locality_annotations`, not built now.
- **Automated/cloud scraping** — permanently ruled out by the CAPTCHA/manual-solve requirement, not a
  future TODO.
- **Email/Slack alerting** — same deferral `BUILD_CONSUMER_LAYER.md` already recommended.
