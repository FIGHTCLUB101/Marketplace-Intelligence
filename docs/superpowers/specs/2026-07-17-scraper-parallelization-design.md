# Scraper Parallelization — Design

## Problem

`blinkit_oats.py` and `zepto_oats.py` each take ~14-15 hours to scrape 500
localities sequentially (one Chrome window, one locality at a time, 10 brand
searches per locality). That's the whole loop: `driver.get()` a locality,
search 10 brands, save, move to the next of 500.

## Goal

Cut that runtime by running each scraper as multiple parallel workers, each
covering a slice of the 500 localities, while:
- Not overwhelming the machine (4 cores / 8 threads, **7.7GB RAM total**,
  observed as low as 0.6GB free with prior Chrome processes still lingering)
- Producing a single combined output file at the same path the rest of the
  pipeline already reads from (`scraper/output/blinkit_oats_data.xlsx` /
  `scraper/output/zepto_oats_data.xlsx`)
- Surviving individual worker crashes without losing progress or taking
  other workers down with it (explicit requirement)

## Scope

- **In scope:** `blinkit_oats.py`, `zepto_oats.py`.
- **Out of scope:** `swiggy_oats.py` (currently running fine, similar
  pace, not part of this change), `blinkit_goatlife.py` (not requested).
- **Worker count:** 3 workers per scraper (6 Chrome windows total if both
  scrapers are run in parallel with each other — see Usage Patterns below).

## Why not Colab / cloud GPU

Considered and rejected. Scraping is I/O-bound, not compute-bound, so a GPU
gives no benefit. More importantly, Colab runs on Google Cloud IP ranges,
and Blinkit/Zepto's anti-bot systems specifically flag datacenter IPs
harder than residential ones (`_reliability.py`'s own block markers already
include `"awswafintegration"`) — running from Colab would likely trigger
*more* CAPTCHAs and blocks, not fewer. It also has no way to interactively
solve a CAPTCHA (the scraper's block-handling depends on a real visible
window you can click into), and free-tier sessions disconnect on idle
(~90 min) or after ~12h, which doesn't comfortably cover this job. Local
parallelism, bounded by available RAM, is the right lever here.

## Architecture

```
                    ┌─────────────────────────┐
                    │   parallel_runner.py      │
                    │   (per scraper, e.g.       │
                    │   `blinkit_oats --workers 3`)│
                    └───────────┬───────────────┘
                                │ builds full 500-locality list
                                │ (same logic scraper already has)
                                │ splits round-robin into 3 shards
                                │ staggers launch ~20s apart
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
       Worker 0 (Chrome#1) Worker 1 (Chrome#2) Worker 2 (Chrome#3)
       shard0.xlsx          shard1.xlsx          shard2.xlsx
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ▼
                    every 5 min + on completion:
                    merge_shards() → sort by canonical
                    (city, locality-price-rank, brand) order
                                ▼
                  scraper/output/blinkit_oats_data.xlsx
                  (same path the rest of the pipeline already reads)
```

## Components

### 1. Worker scraper scripts (minimal changes)

`blinkit_oats.py` and `zepto_oats.py` gain two optional CLI args:
- `--shard-index N`
- `--num-shards K`

Default (`--num-shards 1`, or omitted): behaves exactly as today — full
500-locality run, output to the normal path. This is unchanged and stays
the supported "just run it normally" path.

When `--num-shards > 1`: the locality list is sliced round-robin
(`localities[shard_index::num_shards]`), and `OUTPUT_FILE` is redirected to
`scraper/output/_shards/{scraper_name}_shard{N}.xlsx`.

**Nothing else changes** — interstitial dismissal, the location-bar reopen
fix, per-locality retry/dead-session recovery, the brand-search
wait-for-cards-or-no-results logic — all untouched. Each worker is just
today's `main()` loop, scoped to fewer localities.

### 2. `parallel_runner.py` (new, generic — works for either scraper)

```
python parallel_runner.py blinkit_oats --workers 3
python parallel_runner.py zepto_oats --workers 3
```

Responsibilities:
- Build the canonical locality list once (imported from the target
  scraper's own list-building function, so there's one source of truth).
- Launch `workers` subprocesses via `subprocess.Popen`, each running
  `python {scraper}.py --shard-index i --num-shards {workers}`, staggered
  ~20s apart.
- Poll each subprocess. If one exits before completing its shard (crash),
  relaunch it (same shard index), capped at 5 restarts per worker with a
  short backoff. After 5 failed restarts for a given worker, stop retrying
  it and print a clear warning — don't crash-loop silently forever.
- Before each launch/restart, check free system RAM; if below a threshold
  (~1GB), pause and warn rather than piling on another Chrome instance.
- Every 5 minutes, and once more after all workers finish, call
  `merge_shards()`.

### 3. `_merge.py` (new, shared)

`merge_shards(shard_paths, output_path, columns, locality_rank_fn)`:
1. Read each shard `.xlsx` (skip any that don't exist yet — a worker may
   not have saved its first row yet).
2. Concatenate all rows.
3. Sort by `(locality_rank_fn(city, locality), brand_index)` — the same
   order the sequential scraper already produces, so the combined file
   reads identically to today's output regardless of which worker produced
   which row or in what order they finished.
4. Write to a temp file, then atomically replace the real output path. If
   the target file is open elsewhere (e.g. in Excel) and locked, catch the
   `PermissionError` and skip this cycle — retry on the next one instead of
   crashing the supervisor.

### 4. Fail-safe mechanisms (explicit requirement)

- **Process isolation**: workers are separate OS processes; one Chrome/
  driver crash can't take another worker down.
- **Auto-restart with cap**: dead workers are relaunched automatically
  (max 5 attempts, backoff between), resuming from their own shard's
  `done_keys` (unchanged `IncrementalWorkbook` resume behavior, just now
  scoped per shard).
- **Staggered startup**: ~20s between worker launches, avoiding a
  simultaneous memory spike from 3 Chrome instances starting at once.
- **Lighter per-instance memory**: parallel-mode workers add
  `--blink-settings=imagesEnabled=false` to `create_driver()` — product
  image *bytes* aren't needed (sponsored-badge detection only reads the
  `src` attribute text), cutting real memory/bandwidth per Chrome instance.
- **RAM pre-check**: supervisor checks free memory before each
  launch/restart and pauses with a warning if too low.
- **Safe merge writes**: temp-file + atomic rename, tolerant of the output
  file being open elsewhere.

## Usage patterns

Both are supported without any extra code — it's just which command(s) you
run:
- **One scraper at a time (default/recommended for this machine):** run
  Blinkit's 3-worker set, let it finish, then run Zepto's. 3 Chrome windows
  at a time.
- **Both at once:** run both `parallel_runner.py` invocations in separate
  terminals if you have RAM to spare. 6 Chrome windows total.

## Testing

- Round-robin sharding function: full coverage (every locality assigned to
  exactly one shard, no gaps or duplicates) across various locality-count /
  shard-count combinations.
- `merge_shards()`: correct sort order, no row loss or duplication, against
  small fixture shard files; behavior when a shard file is missing or
  empty; behavior when the output path is locked (simulated
  `PermissionError`).
- Restart/backoff counter logic: mocked subprocess, no real Chrome/driver
  involved.
- Existing scraper test suites (`test_blinkit_oats.py`, `test_zepto_oats.py`,
  `test_reliability.py`) are unaffected since the scraping logic itself
  doesn't change — they should continue to pass unmodified.

## Out of scope / explicitly not doing

- No headless mode (breaks the window-visibility requirement the scraper
  was already hardened around, and headless is more block-prone anyway).
- No cloud/Colab execution (see "Why not Colab" above).
- No change to `swiggy_oats.py` or `blinkit_goatlife.py`.
- No change to the final output file's path, columns, or schema — anything
  downstream (pipeline, dashboards) keeps reading the same file the same
  way.
