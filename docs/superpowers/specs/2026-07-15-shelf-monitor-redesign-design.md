# Shelf Monitor Redesign

## Why

The current Shelf Monitor tab (`web/shelf-monitor.js`) renders every `(product, locality)` change from
`/api/shelf/changes` as its own flat row. A single SKU getting delisted across 130 localities produces 130
near-identical lines, interleaved with price changes and new-product alerts in one undifferentiated feed,
with no way to filter by city/locality or select a brand to inspect. It is, in practice, unreadable.

Separately, three of the four shelf-scraper platforms (`blinkit`, `swiggy`, `zepto`) — each sweeping the same
10 competitor brands across up to 500 localities — have never been surfaced in the UI at all; only
`blinkit_goatlife` (GOAT's own rank tracker) is wired up today. Database inspection during design found this
data is rich and directly answers a real question the current tab can't: how does GOAT's shelf presence
compare to named competitors, per platform, per locality.

This document redesigns the tab to fix both problems: group-and-filter the existing weekly-change feed, and
add a new view that surfaces the competitor-sweep data.

## Research findings (informing scope)

Queried the live DB directly (`shelf_snapshots`, `scrape_runs`) rather than assuming from `models.py` alone:

| Platform | Scrape runs | Localities / cities | Rank captured? | Brand(s) searched | Notes |
|---|---|---|---|---|---|
| `blinkit_goatlife` | 2 (Jul 11 → Jul 13) | 500 / 10 | Yes (99.97%) | "Goat Life" only | Only platform with real week-over-week history today |
| `blinkit` | 1 | 500 / 10 | **No** (always null) | 10 competitor brands | GOAT incidentally appears in 767/56,688 rows (1.4%) — organic intrusion signal |
| `swiggy` (Instamart) | 1 | 500 / 10 | **No** | same 10 brands | Uniquely captures a `sponsored` flag. GOAT appears in **0** rows — no organic visibility at all |
| `zepto` | 1 | 259 / 6 | **Yes** (full) | same 10 brands (no " Oats" suffix) | Smaller footprint but only competitor sweep with real rank; also captures `reviews`. GOAT appears in 24/35,708 rows (0.07%) |

Other findings that shape the design:
- The 10 competitor brand names are identical across all three sweep platforms modulo a trailing " Oats"
  suffix (`"Pintola Oats"` vs `"Pintola"`) — trivial to normalize, no fuzzy matching needed.
- Locality sets are clean subsets: `blinkit`'s 500 == `swiggy`'s 500 exactly; `zepto`'s 259 is a full subset
  of both. Same-locality cross-platform comparison is valid everywhere zepto has data.
- `blinkit`, `swiggy`, `zepto` each have exactly one scrape run, all from the same day (Jul 11) — a snapshot,
  not a trend. `/api/shelf/changes` already short-circuits to `status: "insufficient_history"` for them
  (`web/api/index.py:111-116`) and returns no row data in that case — there is currently no endpoint that
  returns *current* (non-diffed) snapshot rows for a platform.
- GOAT's organic-visibility gap across platforms (1.4% / 0% / 0.07%) is itself a decision-relevant finding —
  the design surfaces it as a headline stat rather than something a user has to notice by cross-referencing
  tables.

## Decisions locked in during design

- **Two sub-tabs inside Shelf Monitor**, not one page or a top-level nav tab: **This Week** (default) and
  **Compare Brands**. They serve different jobs (triage vs. exploration) and neither should be diluted by the
  other's controls.
- **This Week stays scoped to `blinkit_goatlife`** — it's the only platform with a real diff. No platform
  selector on this tab; adding one is trivial later (the API already takes `platform` as a query param) but
  would be dead UI today since the other three always return `insufficient_history`.
- **Grouping axis for This Week is (event type, product), not city** — one card per unique change, with a
  "in N localities" count and an expand/collapse list, rather than one section per city. Chosen because the
  primary job is spotting patterns ("is one SKU getting wiped out everywhere"), not "what happened in city X."
  A city/locality filter still narrows results within that grouping.
- **Compare Brands uses a platform selector + single focused view**, not three side-by-side columns. Simpler
  to build and read; the cross-platform gap is instead surfaced via the always-visible headline stat row so
  it isn't lost.
- **New backend endpoint required**: `GET /api/shelf/snapshot?platform=X`, returning the latest run's raw
  rows. This walks back an earlier assumption that the redesign needed no backend changes — that held only
  for `blinkit_goatlife`; the three competitor-sweep platforms have no other way to expose current state,
  since `/api/shelf/changes` deliberately returns nothing but a placeholder narrative when there's no second
  run to diff against.
- **Rank column hides itself per platform**, not shown-as-empty — `blinkit`/`swiggy` never populate rank, so
  the Compare Brands table omits that column entirely when the selected platform doesn't have it, rather than
  rendering a column of dashes.

## Architecture

```
web/
  shelf-monitor.js         This Week + Compare Brands render logic, pure helpers, fetch/filter wiring
  index.html                two new <select> pairs (city/locality on This Week; platform/brand/city/locality
                             on Compare Brands) + sub-tab pill buttons, all inside #shelf-monitor's container
  styles.css                 minor additions: sub-tab pills, group-card expand/collapse, headline-stat row
  tests/shelf-monitor.test.js   new pure-function tests (grouping, brand-name normalization, visibility-rate calc)

  api/
    queries.py               + fetch_current_snapshot(conn, platform) and its SQL string
    index.py                  + GET /api/shelf/snapshot?platform=X route
    test_queries.py            + tests for fetch_current_snapshot
    test_api.py                 + tests for the new route
```

No changes to `models.py` — the new endpoint returns `list[ShelfSnapshot]`, and that model already has every
field needed (`brand_searched`, `rank`, `selling_price`, `mrp`, `discount_pct`, `stock_left`, `rating`,
`reviews`, `sponsored`, `serviceable`, `is_goat`).

## This Week tab

- Fetch unchanged: `/api/shelf/changes?platform=blinkit_goatlife` + `/api/shelf/trends?platform=blinkit_goatlife`.
- New pure function `groupChangesByProduct(changes)` collapses `goat_displaced`, `goat_gone`,
  `rank_intrusions`, `price_changes`, `new_products`, `gone_products` into groups keyed by
  `(eventType, productName)`, each with `{ severity, count, entries: [{city, locality, ...detail}] }`.
  Severity per group reuses the existing critical/warning/info mapping from `renderChangeRows` today.
- Render: one card per group — colored left border (existing `.alert-row` classes), product name, event
  description, `"in N localities"` badge. Groups with `count <= 5` render their entries expanded by default;
  larger groups start collapsed behind a toggle.
- Two `<select>` filters (City, Locality — Locality options scoped to the selected City, same cascading
  pattern as `#f-city`/`#belt-select` on the Map tab) populated from the distinct cities/localities present
  in the fetched `changes` payload. Filtering hides groups with zero matching entries and hides non-matching
  entries within a still-visible group.
- Severity banner, brand defence rate, narrative, conquest breadth section, and the trends table are
  unchanged — those already work and weren't part of the complaint.

## Compare Brands tab

- Controls: **Platform** select (`Blinkit`, `Instamart`, `Zepto` — mapped to `blinkit`/`swiggy`/`zepto`
  query values; `blinkit_goatlife` excluded, it never searches competitor brands), **Brand** select (the 10
  canonical names: Alpino, Cosmix, MuscleBlaze, Pintola, Quaker, Saffola, SuperYou, The Whole Truth, True
  Elements, Yoga Bar), and City/Locality filters matching the This Week pattern.
- **Headline stat row**, always visible regardless of platform/brand selection: `GOAT organic visibility —
  Blinkit 1.4% · Instamart 0% · Zepto 0.07%`.
- **Fetch-once-per-platform, filter client-side thereafter**: `/api/shelf/snapshot?platform=X` is called the
  first time a platform is selected and its full result cached client-side for the session (no `brand`
  filter on the endpoint — it always returns the whole platform snapshot). The headline stat is computed
  from that same cached data (`count(is_goat=true) / count(*)`) the first time each platform's data arrives,
  so it fills in progressively rather than requiring three separate calls up front. Brand/city/locality
  selection then filters the already-fetched dataset in memory with no further network calls. Accepted
  tradeoff: `blinkit`'s snapshot alone is ~56.7k rows in one response (the platform's only run, un-diffed) —
  larger than anything else this app fetches, but a one-time cost per platform per session, not per
  interaction.
- Main table, populated from the cached platform snapshot filtered by the selected brand (name-normalized)
  and city/locality: columns City, Locality, Rank (omitted entirely for `blinkit`/`swiggy`, which never
  populate it), Price, MRP, Discount %, and a "GOAT also here?" flag — cross-referenced from `is_goat=true`
  rows in the same cached snapshot sharing the same `(city_raw, locality_raw)`.
- Brand name normalization: strip a trailing `" Oats"` suffix when matching `brand_searched` against the
  canonical 10-brand list, so `"Pintola Oats"` (Blinkit/Instamart) and `"Pintola"` (Zepto) both match
  selecting "Pintola". One small pure function, unit-tested.

## Backend: `GET /api/shelf/snapshot`

```python
@app.get("/api/shelf/snapshot", response_model=list[ShelfSnapshot])
def get_shelf_snapshot(platform: str = Query(...)):
    conn = get_connection()
    try:
        newest_id, _ = queries.fetch_latest_two_scrape_run_ids(conn, platform)
        if newest_id is None:
            return []
        return queries.fetch_current_snapshot(conn, newest_id)
    finally:
        conn.close()
```

`fetch_current_snapshot(conn, scrape_run_id)` is a new query selecting the full column set (unlike the
existing `fetch_snapshot_rows`, which only selects the narrow subset `shelf_changes.py`'s diff functions
need) — `shelf_snapshot_id, platform, locality_id, city_raw, locality_raw, brand_searched, rank, product_name,
pack_size, selling_price, mrp, discount_pct, stock_left, rating, reviews, sponsored, serviceable, is_goat,
started_at, finished_at`, i.e. every `ShelfSnapshot` field, ordered by `city_raw, locality_raw`.

Reuses `fetch_latest_two_scrape_run_ids` (already exists) purely for its `newest_id` — the second-newest is
discarded since this endpoint is not a diff.

## Testing

- Backend: `cd web/api && python -m pytest -q`, following the exact `requires_db` +
  `TestLocalityXYZ`/`test_platform_xyz`-prefixed fixture convention already used throughout `test_api.py` and
  `test_queries.py` (see e.g. `test_api.py:119` for the shape of a scrape-run + snapshot-row fixture). New
  tests: `fetch_current_snapshot` returns full rows for a seeded run; `GET /api/shelf/snapshot` returns `[]`
  for a platform with zero runs and the expected rows for one with data.
- Frontend: `node --test web/tests/shelf-monitor.test.js` (existing convention). New tests for
  `groupChangesByProduct` (grouping + severity + count correctness), the brand-name-normalization helper, and
  the GOAT-visibility-rate calculation — all pure functions, no DOM/network involved, matching how
  `severityFor`/`formatTrendRows`/`formatBrandDefenceRate` are tested today.

## Explicitly out of scope

- A true locality × brand matrix endpoint (rows = localities, columns = brands, cells = rank) — considered
  and declined during design in favor of the platform-selector + single-view approach, which needs no new
  query beyond the flat snapshot endpoint above.
- Extending `/api/shelf/changes`'s week-over-week diff to `blinkit`/`swiggy`/`zepto` — not possible until each
  has a second scrape run; this spec only adds a *current-state* view for them, not a trend.
- A platform selector on the This Week tab — the API already supports it via the existing `platform` query
  param, so adding one later is a small, isolated change, not a reason to build it now against platforms that
  would only ever show "insufficient history."
- Any change to `sync_shelf_snapshots.py` or the scraper pipelines themselves.
