# Sprint 3 — API Layer Design

## Why

`docs/superpowers/specs/2026-07-11-goatlife-fullstack-platform-design.md` already defines *what* Sprint 3
ships: six endpoints, FastAPI on Vercel Python serverless functions, no auth. What it doesn't pin down is
*how* — file layout, DB access pattern, test strategy, exact response shapes, and a few semantics the
endpoint table left implicit (annotation upsert-vs-history, whether competitor data merges into
`/api/localities` or stays separate). This document resolves those, scoped to Sprint 3 only. It supplements
the shared spec rather than replacing it — endpoint purposes and the underlying schema (`localities`,
`locality_scores`, `shelf_snapshots`, `locality_annotations`, `pipeline_runs`, `scrape_runs`) are unchanged
from Sprint 1/2 and not repeated here in full.

## Decisions locked in during design

- **API location:** `web/api/`, extending the existing Vercel project that already deploys `web/` as static
  output (`web/vercel.json`). One project, one deploy, no CORS — matches the shared spec's "same Vercel
  project" intent, applied now instead of waiting for the Sprint 4 Next.js rewrite.
- **DB access:** raw psycopg2, no ORM — the only pattern used anywhere else in this repo
  (`scripts/db_connection.py`).
- **Local dev:** plain `uvicorn`, not `vercel dev` — the deployed function is one ASGI app either way, so
  there's no prod-fidelity gap from running it directly.
- **Field naming:** clean snake_case (`area`, `icp_score`, `gtm_action`, ...), not the legacy parquet-era
  `AREA`/`ADDRESS` names — Sprint 4's Next.js frontend is a fresh consumer, not the current vanilla-JS site,
  so there's no compatibility reason to keep the old names.
- **Competitor data:** `/api/localities` and `/api/competitor/summary` stay separate calls, joined
  client-side on `locality_id`, per the shared spec's endpoint table — not merged server-side the way the
  legacy `enrich_competitor_data.py` merges them into one static blob today.
- **Annotations:** `POST /api/annotations` always inserts a new row (history log), never upserts. The
  `locality_annotations` table has no unique constraint on `locality_id`, which only makes sense under a
  history model. `updated_at` stays unused this sprint — reserved for a future edit endpoint, not written by
  this insert-only POST.
- **DB test strategy:** follow the exact convention every Sprint 1 script test already uses —
  `requires_db = pytest.mark.skipif(not DATABASE_URL, ...)`, running against the real Neon DB with
  `TestLocalityXYZ`-prefixed fixture rows and explicit `DELETE` cleanup. No separate local Postgres
  instance — that would be a second, divergent test pattern in a codebase that has exactly one today.

## Architecture

Single FastAPI ASGI app at `web/api/index.py`, deployed as one Vercel Python serverless function.
`web/vercel.json` gains a `rewrites` entry routing `/api/*` to `index.py` — Vercel's Python runtime deploys
one function per file exporting `app`, so all six routes live behind FastAPI's own router inside that one
file's app object, not as six separate Vercel functions.

```
web/
  api/
    index.py          FastAPI app + all 6 route handlers
    db.py              self-contained get_connection() — duplicated from scripts/db_connection.py
                        rather than imported cross-directory, so the Vercel function bundles cleanly
                        without reaching outside web/api/
    models.py           Pydantic response models (snake_case fields)
    queries.py            SQL strings / small query functions, grouped by endpoint
    requirements.txt       fastapi, uvicorn, psycopg2-binary, python-dotenv, pydantic
                            (deliberately no pandas/numpy — keeps cold starts light; all
                            aggregation is plain Python/SQL, not DataFrames)
    test_api.py              pytest + FastAPI's in-process TestClient
  vercel.json           + rewrites for /api/*
```

## Endpoints

| Endpoint | Source | Notes |
|---|---|---|
| `GET /api/localities` | `current_locality_scores` view ⋈ `localities` | Full current dataset, ~900 rows, no pagination at this size |
| `GET /api/belts` | same base query, grouped in Python (no pandas) | belt_id/city groups where belt_size ≥ 3: size, avg_icp, go_count, confirmed_count, members (≤12) |
| `GET /api/competitor/history?locality_id=&platform=` | `shelf_snapshots` ⋈ `scrape_runs` | Raw rows over time; both params optional filters. Ordered oldest→newest by `scrape_runs.started_at`, matching the "price-over-time" chart use case from the shared spec's frontend section |
| `GET /api/competitor/summary` | `shelf_snapshots` restricted to the latest `scrape_run_id` per platform | Per locality × platform: n_competitor_brands, competitor_avg_price, goat_present — using the already-computed `is_goat` column (Sprint 2), no text-matching re-derivation needed the way `enrich_competitor_data.py` does it |
| `GET /api/annotations?locality_id=` / `POST /api/annotations` | `locality_annotations` | `locality_id` is an optional filter on GET (omitted = all annotations, newest first); POST always inserts (history log) |
| `GET /api/meta/freshness` | `MAX(triggered_at)` from `pipeline_runs`; `MAX(finished_at)` per platform from `scrape_runs` | "Data as of X" indicator |

`color` (hex per `gtm_action`) is **not** computed server-side — stays a pure client-side lookup via a
ported `contract.js` in Sprint 4, per the shared spec's "port contract.js verbatim" decision. The API only
ever returns the raw `gtm_action` string.

## Error handling

FastAPI defaults, no custom envelope: `HTTPException(404, ...)` for an unknown `locality_id`, automatic 422
from Pydantic validation on bad query params, and a catch-all exception handler that logs the real
traceback server-side (captured in Vercel function logs) but returns a generic
`{"detail": "internal server error"}` to the client — never leaks a stack trace.

## Testing

`cd web/api && python -m pytest -q`, mirroring `scripts/`'s existing `cd scripts && python -m pytest -q`
convention. FastAPI's `TestClient` calls routes in-process against the real Neon DB (via `DATABASE_URL`),
using the `requires_db` skip marker and `TestLocalityXYZ`-prefixed fixtures with explicit cleanup, exactly
as `scripts/test_sync_locality_scores.py` and `scripts/test_sync_shelf_snapshots.py` already do.

## Explicitly out of scope for Sprint 3

- Any frontend change — Sprint 4 consumes this API, not built here.
- Auth, rate limiting — already deferred by the shared spec ("whoever has the link").
- An annotation edit/delete endpoint — `updated_at` exists in the schema but isn't used until that's built.
- A `/api/competitor/summary` price-advantage-vs-GOAT-price metric (`enrich_competitor_data.py`'s
  `price_advantage_blinkit`) — that's Blinkit-specific, GOAT-price-hardcoded logic; the summary endpoint
  stays platform-generic (n_competitor_brands, competitor_avg_price, goat_present) and doesn't port it.
