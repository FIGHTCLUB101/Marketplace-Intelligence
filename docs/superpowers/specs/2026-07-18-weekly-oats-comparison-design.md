# Weekly Oats Competitor Comparison — Design

Date: 2026-07-18
Status: Approved for planning

## Problem

`scripts/run_weekly.py` currently syncs and diffs only `blinkit_goatlife_data.xlsx` (the
GOAT Life shelf-rank monitor) week over week, then emails a report. The three oats
competitor scrapers — `blinkit_oats.py`, `swiggy_oats.py`, `zepto_oats.py` — produce
weekly xlsx snapshots too (`scraper/output/{blinkit,swiggy,zepto}_oats_data.xlsx`), but
nothing compares one week's snapshot to the next for them. Old snapshots just accumulate
untouched (e.g. `scraper/output/backup_2026-07-17/`) with no diffing, alerting, or
history retention.

Goal: extend the weekly orchestrator to also diff the three oats platforms week over
week and fold the result into one combined report.

## Why oats platforms need different diff logic than blinkit_goatlife

`blinkit_goatlife.py` searches a category term and records each product's **shelf rank**
(1-4). `shelf_changes.py`'s `detect_changes()` is built entirely around that: GOAT
displaced from rank 1-4, competitor rank intrusions, etc. `build_shelf_snapshot()`
silently drops any row with `rank=None`.

The oats scrapers work differently: for each city/locality they search **each
competitor brand by name** (Pintola Oats, Yoga Bar Oats, Quaker Oats, ...) and record
whatever comes back for that brand — a competitive pricing/availability scrape, not a
shelf-rank scrape. Confirmed from the actual output columns:

- **Blinkit oats & Swiggy oats: no `Rank` column at all.**
- **Zepto oats has a `Rank` column**, but it's rank *within that one brand's search
  results*, not a category-wide shelf position — a different meaning than
  `blinkit_goatlife`'s rank.

Reusing `detect_changes()` unmodified against oats data would silently produce nothing
(every row dropped for `rank=None`) or compare rank values that don't mean what
`blinkit_goatlife`'s do. So oats platforms get their own diff function, scoped to what
they actually capture: price, discount, stock/availability, and new/delisted SKUs.

## Decisions

1. **Comparison scope for oats platforms**: price changes, stock/availability changes,
   and new/discontinued SKUs — no rank-based logic. (Rejected: extending the scrapers to
   capture shelf rank — out of scope, touches the scraper layer, not the weekly report.)
2. **Report structure**: one combined weekly email covering all 4 platforms
   (`blinkit_goatlife` + 3 oats), with a section per platform, rather than 4 separate
   emails.
3. **Architecture**: new pure-function module `scripts/oats_changes.py` (mirrors
   `shelf_changes.py`'s shape) + generalize `run_weekly.py` into a loop over a platform
   table, dispatching to the rank-based or price/availability-based detector per
   platform. (Rejected: bolting a "no-rank" mode onto `detect_changes()` itself — would
   muddy a module whose entire vocabulary, `goat_displaced`/`rank_intrusions`, is
   rank-position-specific and has 96 ported tests riding on current behavior. Rejected:
   a fully separate, independently-scheduled script — doesn't produce the single
   combined email that was asked for.)

## Data layer changes

`scripts/queries_shelf.py`'s `fetch_snapshot_rows()` currently selects only
`city_raw, locality_raw, product_name, rank, selling_price, is_goat`. Widen the SELECT
to also include `brand_searched, stock_left, serviceable` — required for oats
matching/diffing, harmless unused extra columns on the existing `blinkit_goatlife` path.

This change is isolated to `scripts/`: `web/api/queries.py` has its own separate
`fetch_snapshot_rows` (by design — `queries_shelf.py`'s docstring notes `scripts/` and
`web/api/` intentionally don't share code across the Vercel bundle boundary), so
widening the `scripts/` copy cannot affect the web API.

Matching key for oats products (no rank available): `(city_raw, locality_raw,
brand_searched, normalize_product_identity(product_name))`, reusing the existing
pack-size/bundle-suffix normalizer from `shelf_changes.py` — the same "Pack of N" vs.
plain listing false-positive problem applies here too. `brand_searched` is part of the
key because the same product (notably GOAT Life's own, appearing as a conquest signal)
can legitimately appear under multiple competitor brand searches in the same locality;
those must stay distinct entries, not get merged.

## `scripts/oats_changes.py` (new)

One function: `detect_price_availability_changes(rows_new, rows_old,
price_threshold_inr=20, price_threshold_pct=15)` returning:

- `new_products` / `gone_products` — appeared/disappeared for a given
  locality+brand+identity.
- `price_changes` — same ₹20-absolute-or-15%-percent threshold as the existing shelf
  monitor, for consistency. Guards, ported/added from `shelf_changes.py`'s proven
  false-positive fixes:
  - Only compares when the raw `display_name` is identical on both sides (never diff a
    single-pack price against a "Pack of 3" price for the same normalized identity —
    this was a confirmed real bug in `shelf_changes.py`, ~496 false positives from
    exactly this pattern).
  - Skips the comparison when either price is `None` or `≤ 0` (bad-scrape sentinel,
    not a real price).
- `stock_changes` — `stock_left` text flips between "in stock"-like and "sold
  out"-like, evaluated **only** when `stock_left` is non-null/non-empty on *both*
  sides. Classification is a case-insensitive substring check: text containing "sold
  out" or "out of stock" is out-of-stock, anything else non-empty is in-stock. Flagged
  only on an actual state flip (in→out or out→in), not on every non-matching string
  pair. Confirmed from real data this degrades gracefully per platform: Swiggy oats
  populates it usefully (`"In Stock"` / `"SOLD OUT"`), current Blinkit oats data is
  100% blank, Zepto oats doesn't have the column at all (`stock_left: None` in
  `PLATFORM_COLUMNS`) — all three are valid, non-error states.
- Every entry carries `is_goat` through (already computed by the oats scrapers) so the
  email can call out when GOAT Life's own product is the one that changed.

## `run_weekly.py` restructuring

Replace the single hardcoded `SCRAPER_OUTPUT`/`PLATFORM` with a platform table:

```python
PLATFORMS = [
    {"key": "blinkit_goatlife", "label": "GOAT Life Shelf Monitor (Blinkit)",
     "xlsx": SCRAPER_OUT / "blinkit_goatlife_data.xlsx", "mode": "rank"},
    {"key": "blinkit", "label": "Blinkit Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUT / "blinkit_oats_data.xlsx", "mode": "oats"},
    {"key": "swiggy", "label": "Swiggy Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUT / "swiggy_oats_data.xlsx", "mode": "oats"},
    {"key": "zepto", "label": "Zepto Oats — Competitor Pricing",
     "xlsx": SCRAPER_OUT / "zepto_oats_data.xlsx", "mode": "oats"},
]
```

For each platform: sync its xlsx into `shelf_snapshots`, fetch the latest two
`scrape_run_id`s, dispatch to `detect_changes()` (mode=`rank`) or
`detect_price_availability_changes()` (mode=`oats`), and produce one HTML section.
All sections combine into a single email rather than each platform sending its own.

### Per-platform isolation (error handling)

Each platform is wrapped in its own try/except inside the loop so one platform's
problem never blocks the others' reporting:

- **Missing xlsx** (scraper hasn't finished this week) → log warning, section reads
  "no data available", continue.
- **`PermissionError`** (file open in Excel) → same "try again next cycle, not fatal"
  treatment `scraper/_merge.py` already uses for shard files — log warning, skip,
  continue.
- **Sync/DB error for one platform** → log warning, skip, continue.
- **Fewer than 2 `scrape_run`s exist** (already handled today for `blinkit_goatlife`,
  extended per-platform) → section reads "not enough history yet", continue.

The script only exits non-zero if **every** platform failed — partial success (e.g. 3
of 4 platforms reported) is still a successful run and still sends an email.

`--dry-run` extends across the whole loop: all 4 platforms are synced and diffed,
per-platform summaries are logged, and no email is sent.

Each platform's DB sync commits independently inside `sync_shelf_snapshots` (existing
behavior), so a late failure (e.g. the email send itself) never loses already-synced
data — only the report for that run is affected, and it's identical to the "insufficient
history" case: the exact same sync just contributes a real diff next week.

## `alerts.py` restructuring

Move from one monolithic HTML document to composable fragments:

- `build_shelf_section_html(changes, label)` — today's `blinkit_goatlife` content
  (narrative, rank disruptions, gone products, intrusions, price table), extracted from
  the current `build_email_html` body. Content unchanged.
- `build_oats_section_html(changes, label)` — new: tables for new SKUs, delisted SKUs,
  price changes, stock changes. A table is only rendered when its list is non-empty
  (matches the existing pattern already used for `blinkit_goatlife`'s sections).
- `build_combined_email_html(sections)` — new outer wrapper (head/style/header) that
  concatenates section fragments into one document. Top banner severity becomes a
  simple total-change count across *all* platforms (`"14 changes detected"` / `"All
  Clear"`) — a single unified severity scale doesn't make sense across
  rank-disruption and price-change semantics. The total is the sum of every bucket's
  length in every platform's `changes` dict (all of `goat_displaced`,
  `goat_recovered`, `new_products`, `gone_products`, `rank_intrusions`, `rank_moved`,
  `price_changes` for rank mode; all of `new_products`, `gone_products`,
  `price_changes`, `stock_changes` for oats mode) — a plain "how many things changed"
  count, not the narrower "threats only" formula `run_weekly.py` uses today
  internally for its own log line (`goat_displaced` + `rank_intrusions` +
  `goat_gone_unique`). That narrower formula still drives the existing per-run log
  output; it does not drive the new combined subject line.
- `build_email_html()` stays as a thin back-compat wrapper:
  `build_combined_email_html([build_shelf_section_html(...)])`, so existing
  `test_alerts.py` assertions keep working with minimal changes.

Subject line: `f"Weekly Competitive Report — {total} changes detected"` or
`"Weekly Competitive Report — All Clear"`.

## Testing plan

**`scripts/test_oats_changes.py` (new)**, mirroring `test_shelf_changes.py`'s style
(pure functions, `list[dict]` in/out):
- New product appears / existing product disappears.
- Price change over threshold triggers; under threshold does not.
- Pack-size-suffix variant: no false price change, and not counted as new+gone either
  (silently unchanged, matching `shelf_changes.py`'s existing behavior for the same
  case).
- Stock flip (`"In Stock"` → `"SOLD OUT"`) detected; `None`/blank on either side is
  skipped, not an error.
- Same product name under two different `brand_searched` values in the same locality
  stays as distinct entries.
- Price sanity floor: `None` or `≤ 0` price is skipped without raising or false-flagging.
- `is_goat` propagates through every bucket.

**`scripts/test_run_weekly.py` additions:**
- One platform's xlsx missing → other 3 still processed normally, exit 0.
- One platform's xlsx locked (`PermissionError`) → skipped with a warning, others
  unaffected.
- One platform has only 1 `scrape_run` → "not enough history" section, others show
  real diffs.
- `--dry-run` across all 4 platforms → no email sent, all 4 summaries logged.
- All platforms fail → exits non-zero.

**`scripts/test_alerts.py` additions:**
- `build_combined_email_html` with multiple sections concatenates correctly and sums
  the subject-line count across platforms.
- `build_oats_section_html` renders only non-empty tables.
- Existing `build_email_html` back-compat wrapper assertions still pass unchanged.

## Out of scope

- Extending the oats scrapers themselves to capture shelf rank.
- Any scheduling/cron automation — this stays a manually-run script (`python
  run_weekly.py`), matching `blinkit_goatlife`'s existing CAPTCHA-gated, local-only
  constraint.
- ICP-weighted narrative prioritization or `historical_recurrence` weighting for oats
  platforms (already deferred for `blinkit_goatlife` itself, per `shelf_changes.py`'s
  docstring — no reason to build it here first).
