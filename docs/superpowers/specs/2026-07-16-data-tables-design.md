# Data Tables

## Why

Third of four sub-projects decomposed from the broader UI/UX task list. Targets the task list's "Data
views" section: sticky headers, column sorting, a horizontal-scroll fallback, a loading skeleton for the
initial dataset parse, and an empty state for zero-result filters. Builds on sub-project 1's design tokens
and sub-project 2's KPI/insight-card work (both merged).

Verified in the actual code before designing:
- `<table class="lb">` appears in **6 places across 2 files**, not the 5 the original task list implied:
  `renderLeaderboard()`'s table (`views.js`), `renderGems()`'s 4 sub-tables (`views.js`), and
  `renderSequence()`'s wave tables in `sequence.js` — which is dynamic, generating up to 4 wave tables plus
  1 watch-list table *per click* of "Generate," entirely regenerated each time.
- `.view{overflow:auto}` is already the scrolling ancestor for every page these tables live on — `position:
  sticky` needs no markup restructuring to work.
- `web/app.js`'s `applyFilter()` (Map view's city/verdict/serviceability filters) has zero empty-result
  handling today — a combination matching 0 localities just silently renders "0 localities · 0 push-now ·
  0 sample" in the small `#map-stats` bar, with the map itself showing nothing and no explanation why.
- `web/data-localities.js` is a 929KB blocking `<script>` (confirmed via `ls -la`); `#kpi-ribbon` and
  `#ledger` are empty `<div>`s in `index.html` until `app.js`'s `DOMContentLoaded` handler finishes parsing
  it and calls `renderKpis()`/`buildLedger()`.

## Decisions locked in during design

- **Sorting scope: Leaderboard's table + all 4 Gems tables** (confirmed with the user — the larger of two
  options offered). **Launch Roadmap's tables get sticky headers and the scroll wrapper like every other
  `.lb` table, but not sorting** — this wasn't part of what was asked/answered, and its tables are small
  (budget-constrained, typically well under Leaderboard's row counts) and fully regenerate on every
  "Generate" click, which is a meaningfully different interaction pattern than browsing a large static list.
  Treat this as a deliberately drawn boundary, not an oversight, if a future pass wants it.
- **Sub-project 2's top-5 insight cards are untouched by sorting.** They stay fixed top-5-by-ICP-score —
  sorting only ever applies to Leaderboard's table (ranks 6-60).
- **Leaderboard's rank number stays tied to each row's fixed ICP-based identity, not display order.**
  Sorting by a different column reorders rows but does not renumber them — e.g. sorted by City, you might
  see `#23`, `#6`, `#41` in that order. This is intentional: the number is a stable cross-reference back to
  "this locality's ICP rank," not a restated row index, so it stays meaningful regardless of the current
  sort.
- **One shared module, not 5 reimplementations.** `web/sortable-table.js` (new file) provides the
  click-to-sort mechanism once; Leaderboard's table and all 4 Gems tables each supply their own column/
  comparator config and row-template function. This is the textbook case for extraction — the exact same
  interactive behavior needed identically 5 times — not premature abstraction.
- **Horizontal-scroll fallback is a plain wrapper div (`.table-wrap{overflow-x:auto}`), not a
  column-hiding/condensing scheme.** Picking which columns to hide per breakpoint is real per-table design
  work; folding it into the already-planned responsive pass on the Map view (sub-project 4) means doing
  breakpoint design once, consistently, rather than twice.
- **Loading skeleton is one generic shimmering block per empty container, not a pixel-accurate placeholder
  matching every KPI card's exact shape.** The actual gap being closed is "flash of empty boxes," not a
  multi-second wait — a simple, honest loading indicator earns its keep here; hand-crafting 4 KPI-shaped
  skeletons would not.
- **Map empty-state background is solid `var(--paper)`, not a translucent overlay.** A translucent
  `rgba()` value would need a separate light/dark tuple to avoid looking wrong in one theme; a solid paper
  background sidesteps that entirely and fully (intentionally) obscures the markerless map beneath it.

## Sticky headers

```css
.lb thead th{position:sticky;top:0;background:var(--paper);z-index:2}
```
`var(--paper)` (not `--surface`) because every `.lb` table sits directly on the page background inside
`.pad` — there's no intervening card/surface wrapper to match instead.

## Sortable tables

`web/sortable-table.js` (new):

```js
export function wireSortableTable(tableEl, rows, columns, renderRow) {
  let sortKey = null;
  let sortDir = 1; // 1 = ascending, -1 = descending

  const render = () => {
    const col = columns.find((c) => c.key === sortKey);
    const sorted = col ? [...rows].sort((a, b) => sortDir * col.sort(a, b)) : rows;
    tableEl.querySelector('tbody').innerHTML = sorted.map(renderRow).join('');
  };

  tableEl.querySelectorAll('th[data-sort-key]').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.sortKey;
      sortDir = sortKey === key ? -sortDir : 1;
      sortKey = key;
      tableEl.querySelectorAll('th[data-sort-key]').forEach((h) => h.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
      render();
    });
  });

  render();
}
```

Each table's `<th>` gains `data-sort-key="..."` attributes matching a `columns` config passed at call
time — e.g. Leaderboard's table (the fully-specified example; the 4 Gems tables follow the identical
pattern with their own column sets and row templates, left to the plan):

```js
const columns = [
  { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
  { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
  { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
  { key: 'price', sort: (a, b) => (num(a.price_advantage_blinkit) ?? -Infinity) - (num(b.price_advantage_blinkit) ?? -Infinity) },
];
```
(`num()` already exists as a local helper in `renderLeaderboard()`; nulls sort last on ascending, matching
how a user would expect "no data" to rank behind real values rather than sorting arbitrarily.)

CSS:
```css
.lb th[data-sort-key]{cursor:pointer;user-select:none}
.lb th[data-sort-key]:hover{color:var(--ink)}
.lb th.sorted-asc::after{content:' \25B2';font-size:9px}
.lb th.sorted-desc::after{content:' \25BC';font-size:9px}
```

## Horizontal-scroll fallback

Every `<table class="lb">...</table>` occurrence (6 call sites across `views.js`/`sequence.js`) gets wrapped
in `<div class="table-wrap">...</div>`:
```css
.table-wrap{overflow-x:auto}
```

## Loading skeleton

`index.html`'s `#kpi-ribbon`/`#ledger` get pre-populated placeholder markup instead of being empty; `app.js`'s
existing `renderKpis()`/`buildLedger()` naturally replace it via their existing `innerHTML = ...` writes —
no new JS logic needed, only the initial HTML and a CSS animation:

```css
.skeleton{background:linear-gradient(90deg, var(--line) 25%, var(--surface) 50%, var(--line) 75%);
  background-size:200% 100%;animation:skeleton-pulse 1.5s ease-in-out infinite;border-radius:var(--radius)}
.skeleton-kpi{height:64px;margin:11px 22px}
.skeleton-ledger{height:220px;margin:4px 0}
@keyframes skeleton-pulse{0%{background-position:200% 0}100%{background-position:-200% 0}}
```
The existing global `@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none
!important}}` rule already disables this animation for reduced-motion users — it degrades to a static gray
block, which still communicates "loading" via shape, not motion. No additional accessibility work needed.

## Map empty state

New element inside `.map-wrap` (already `position:relative`, the correct anchor):
```html
<div id="map-empty" class="map-empty">
  <p>No localities match these filters.</p>
  <button id="map-empty-clear" type="button">Clear filters</button>
</div>
```
```css
.map-empty{display:none;position:absolute;inset:0;align-items:center;justify-content:center;
  flex-direction:column;gap:10px;background:var(--paper);z-index:4;text-align:center}
.map-empty.show{display:flex}
```
`applyFilter()` toggles `.show` based on `vis.length === 0`. The "Clear filters" button resets `sel.city`/
`sel.verdict`/`sel.serviceability` to `'all'`, resets the three `<select>` elements' displayed values to
match, and re-runs `applyFilter()` — giving the empty state an actual way out, per the "empty state as an
invitation to act" principle, not just an explanation.

## Testing

- New pure-function coverage for `wireSortableTable`'s sort-toggle state machine (click same column twice
  → direction flips; click a different column → direction resets to ascending) — this is genuine new logic,
  unlike sub-project 2's trivial slice-based splitting, and it's shared across 5 call sites, making a
  regression here higher-blast-radius than a one-off. Exact test shape left to the plan.
- No test needed for the loading skeleton or empty-state CSS — pure presentation, verified manually.
- Manual verification: scroll each of the 6 long tables and confirm headers stick; click through sortable
  columns on Leaderboard and each Gems table in both directions; resize the viewport narrow and confirm
  tables scroll horizontally instead of overflowing the page; throttle/observe the initial page load for
  the skeleton flash; set the Map filters to an impossible combination (e.g. a city with no `GO` verdicts)
  and confirm the empty state appears and "Clear filters" recovers correctly; repeat all of the above in
  dark mode.

## Explicitly out of scope

- Column-hiding/condensing responsive table variants — folded into sub-project 4's Map-view responsive work
  instead of being designed twice.
- Sorting on Launch Roadmap's tables (locked decision, see above).
- Any change to `renderLeaderboard()`'s top-5 insight cards (sub-project 2, already shipped) — sorting
  never touches them.
- Marker clustering, filter-panel placement, or any other item from sub-project 4's scope.
