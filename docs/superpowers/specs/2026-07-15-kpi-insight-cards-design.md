# KPI Ribbon + Insight Cards

## Why

Second of four sub-projects decomposed from the broader UI/UX task list (see
`docs/superpowers/specs/2026-07-15-design-system-foundation-design.md` for sub-project 1, already merged).
This one targets the task list's "Redesign KPI ribbon and Decision Ledger with explicit F-pattern
hierarchy" and "Reframe Leaderboard/Gems rows toward insight card framing" items, closest to the
reference images (Dcluttr-style stat cards, recommendation-panel framing).

Verified in the actual code before designing (not assumed):
- The KPI ribbon (`web/app.js`'s `renderKpis()`) already renders its 4 stats in the *correct* priority
  order (Localities analysed → Push-now → Untapped markets → Confirmed%) — the gap isn't ordering, it's
  that `styles.css`'s `.kpi` rule gives all 4 cards identical visual weight (`font-size:22px` for every
  `.kn`), so the intended hierarchy never actually reads as one.
- A real, blocking constraint found during research (see spec conversation): the reference images'
  signature stat-card element — a sparkline/delta showing movement vs. a prior period — **cannot be built
  with real data**. The Map/KPI/Leaderboard/Gems views run entirely off `web/data-localities.js`, a static
  bundle rebuilt by `scripts/build_locality_data.py` from a single parquet snapshot; they never call the
  Postgres API at all. Even on the DB side, `pipeline_runs` has only 3 genuine full-dataset runs, all
  within ~16 hours on 2026-07-11/12 — not a real week-over-week story. Trend lines are explicitly out of
  scope for this sub-project (see Decisions below) rather than faked.
- `web/views.js`'s `renderGems()` already renders 4 separately-headed sub-tables (White space,
  Pareto-optimal, Hidden gems, Spillover gems) — deliberately left out of insight-card conversion this
  pass (see Decisions).
- A family of near-duplicate hardcoded "light hover tint" hex values exists across exactly the components
  this sub-project touches: `.lrow:hover{background:#F4F2EB}` (Decision Ledger) and
  `.lb tr:hover td{background:#F7F5EF}` (Leaderboard's table, used by the rows this sub-project leaves
  untouched below the new insight cards). A third, `#F1EFE8` (`.tab.active`/`.dd-item:hover`), belongs to
  topbar/nav chrome — out of scope, already flagged as a follow-up in sub-project 1's final review.

## Decisions locked in during design

- **No trend lines / sparklines in this pass.** Confirmed with the user after the data-gap finding above.
  Stat cards get the reference images' *structural* language (label, big number, colored status) without
  the delta-vs-prior-period element. Revisit once the Map view is wired to the Postgres API — not part of
  this sub-project or its immediate successors.
- **KPI hierarchy: Localities Analysed leads** (confirmed with the user; current visual order is already
  correct, this sub-project makes the hierarchy actually visible). It becomes a larger "primary" card;
  Push-now/Untapped/Confirmed% become a secondary row — smaller, grouped, still fully legible.
- **Insight cards apply only to Leaderboard's top 5 rows** (by ICP score, the table's existing sort).
  Rows 6-60 stay in the existing `<table class="lb">`, renumbered starting at 6. Gems is **not** touched
  in this pass — its 4 sub-tables are already segmented by category with their own headings, and
  converting all of them to cards would roughly double this sub-project's scope for a less clear payoff
  than Leaderboard's single ranked list. A future pass can revisit Gems once Leaderboard's pattern is
  proven.
- **Insight cards lead with `gtm_action`, not `icp_verdict`.** "Lead with the recommended action" means
  the actual GTM action (`PUSH-NOW`, `SAMPLE + QC test`, etc.) — literally the row's "Action" column
  today — not the ICP verdict (`GO`/`SAMPLE-FIRST`/`WAIT`), which is an intermediate score feeding into
  that action. The card's leading element reuses `contract.js`'s existing `colorFor()`/`labelFor()`
  (categorical, already canonical) via the same dot-glyph pattern `gtmDot()` already uses elsewhere —
  no new color mapping needed, and it keeps the categorical GTM system cleanly distinct from the
  ordinal status-token system, matching sub-project 1's established "keep two color sources distinct"
  principle.
- **The three-way `#F1EFE8`/`#F4F2EB`/`#F7F5EF` hover-tint duplication is only partially addressed.**
  `#F4F2EB` (Decision Ledger) and `#F7F5EF` (Leaderboard table) are consolidated into one new token,
  `--hover-bg: #F4F2EB` (light — the ledger's existing value, kept as canonical) /
  `--hover-bg: #2A2C33` in the `[data-theme="dark"]` block (a step lighter than `--surface`'s `#1D1F26`,
  enough to read as a hover highlight against the dark card/row background). `#F1EFE8`
  (`.tab.active`/`.dd-item:hover`, topbar chrome) is deliberately left alone — out of scope, same
  boundary already drawn in sub-project 1.
- **No new icon library or icon font.** The app has no icon system today (its only "icons" are the
  existing ●/✓/— glyphs already used by `gtmDot()` and the indicator spans). This sub-project continues
  that restrained, text/mono-driven visual language rather than introducing a dependency for one section.

## KPI ribbon

`renderKpis()` output restructures from 4 flat `.kpi` divs into a primary card + a secondary group:

```html
<div class="kpi primary">
  <div class="kn">1,001<span class="ks">886 mapped</span></div>
  <div class="kl">Localities analysed</div>
</div>
<div class="kpi-secondary">
  <div class="kpi"><div class="kn" style="color:var(--status-success)">97</div><div class="kl">Ready to launch · push-now</div></div>
  <div class="kpi"><div class="kn">145</div><div class="kl">Untapped markets</div></div>
  <div class="kpi"><div class="kn">89%</div><div class="kl">Quick-commerce confirmed</div></div>
</div>
```

`.kpi-ribbon` stays the outer flex container (two children now: `.kpi.primary` and `.kpi-secondary`).
`.kpi.primary`'s `.kn` renders larger (34px vs. the existing 22px) and the card gets a `border-left:3px
solid var(--goat)` accent — reusing the existing brand-accent token as the "this is the flagship stat"
signal, the same left-border-accent pattern `.alert-row`/`.group-card` already establish elsewhere in the
app, not a new visual device. `.kpi-secondary` is an inner flex row for the 3 remaining stats, each
slightly smaller (`.kn` at 18px) than today's 22px — legible, clearly secondary, not cramped.

## Decision Ledger

No structural change — stays the existing dot + label + count list (it doubles as the map's filter
control; forcing it into card format would fight that role, and it's already close to the reference
images' "Top cities" list pattern). Scope is: apply the new `--hover-bg` token to `.lrow:hover` (replacing
`#F4F2EB`) for dark-mode consistency with the rest of this pass's work.

## Leaderboard insight cards

`renderLeaderboard()` splits its sorted 60 rows into `top5` (cards) and the remaining 55 (table,
renumbered from 6). Each card:

```html
<div class="insight-card">
  <div class="insight-head">
    <span class="insight-rank">#1</span>
    <span class="insight-action" style="color:${colorFor(gtm_action)}">● ${labelFor(gtm_action)}</span>
    <span class="insight-icp">ICP <b>92</b></span>
  </div>
  <div class="insight-locality">Koramangala <span class="insight-city">· Bangalore</span></div>
  <div class="insight-meta">Confirmed serviceability · Premium · Metro</div>
  <div class="insight-meta">GOAT on Blinkit <span style="color:var(--status-success)">✓</span> · <span style="color:var(--status-success)">+₹18</span> price advantage</div>
</div>
```

The two `.insight-meta` lines reuse the exact same data/fields/status-token colors the existing table
already shows for these rows (`serviceability_state`, `archetype_ml`, `blinkit_goat_present`,
`price_advantage_blinkit`) — no new data, just a restructured presentation leading with the action instead
of burying it in a table column. `.lb tr:hover td` gets the same `--hover-bg` token swap as the ledger.

**Null handling matches the existing table exactly, not fabricated for the card layout.** Today's table
already handles two fields as sometimes-absent: `price_advantage_blinkit` (shown as `'—'` when `null`,
already gated by `a !== null` in the current code) and `blinkit_goat_present` (three states — `true`,
`false`, or `'' `/`null` meaning "n/a," already handled by the current ternary chain). The insight card's
second `.insight-meta` line reuses that same three-way logic — if both fields are absent for a top-5 row,
that line is omitted entirely rather than rendering an empty/dash-filled line.

## Testing

No new frontend pure-function tests — this sub-project is markup/CSS restructuring of existing render
functions with no new data logic (the row-splitting `slice(0,5)`/`slice(5)` is the only new "logic," and
it's trivial enough that a unit test would just restate the slice itself). Verification is manual: load
the Map view and confirm the KPI hierarchy reads correctly at a glance in both themes; open Leaderboard
and confirm the top 5 render as cards (correct action/ICP/locality/metadata per row, matching what the
table used to show for those same 5 localities) and rows 6-60 render in the table starting at rank 6;
confirm Decision Ledger's hover state and Leaderboard's table-row hover state both look correct in dark
mode (previously they'd have been the old unthemed hex).

## Explicitly out of scope

- Trend lines / sparklines (locked decision, see above — real architectural gap, not a "later polish" item).
- Gems (`renderGems()`) — all 4 sub-tables stay plain tables, no insight-card conversion.
- `.tab.active`/`.dd-item:hover`'s `#F1EFE8` — topbar/nav chrome, a different sub-project.
- Any icon library/font addition.
- Sticky table headers, column sorting, loading skeletons, empty states — sub-project 3 (data tables).
- Map view responsive/clustering/filter-placement work — sub-project 4.
