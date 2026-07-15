# Design System Foundation

## Why

This is the first of four sub-projects decomposed from a broader UI/UX task list (design tokens,
KPI/insight cards, data tables, map UX) — the full list spans 8 areas and can't be built or reviewed as
one change. This sub-project is the foundation the other three sit on: consolidating color, fixing the
drift risk that's already real (not hypothetical), and adding dark mode as token infrastructure — before
any of the visual/feature work in the later sub-projects touches these files again.

Verified in the actual code (not assumed from the task list): the same brand colors are hardcoded
independently in four places:
- `web/styles.css`'s `:root` (`--go: #059669`)
- `web/contract.js`'s `GTM_COLORS` (`PUSH-NOW: '#059669'`, `HOLD: '#888780'`, ...) — the tested
  cross-language contract with `scripts/contract.py`
- `web/views.js`'s module-level `VERDICT_BG`/`VERDICT_FG` maps, plus five more raw `#059669`/`#888780`/
  `#2a78d6`/`#d97706`/`#EF9F27` literals scattered through inline `style="..."` attributes
- `web/margin.js`'s `COLOR` map (`GO/CAUTION/STOP`), plus a fifth, previously-untracked red
  (`#f87171`) for the "not viable" contribution figure, and a border using `rgba(255,255,255,.02)`

A fifth, independently-designed copy of the same green/amber/red traffic light already exists in
`web/styles.css`'s `.severity-banner`/`.alert-row` rules (added when Shelf Monitor was built), using yet
different exact shades for the same concept (`.severity-banner.clear` text `#166534` vs. `views.js`'s
GO text `#059669` — both mean "success," neither refers to the other).

## Decisions locked in during design

- **Typography stays IBM Plex Sans/Mono** — out of scope for this pass (explicit decision, not an
  oversight; see brainstorming transcript). Nothing in this spec touches `--sans`/`--mono`.
- **Two-tier status token model**, not a flat one: an *accent* shade (vivid, for icons/dots/borders/chart
  lines) and a *text* shade (darker, WCAG-AA-safe against the paired pastel background) per status, plus
  the background tint itself. This is because the existing code already draws this distinction correctly
  in places (e.g. shelf-monitor's `#166534` text vs. GTM's `#059669` accent are both intentionally
  different weights of "success," not accidental drift) — collapsing to one shade per status would be a
  real regression, not a simplification.
- **`GTM_COLORS` is not touched or merged into the status tokens.** It's categorical (5 distinct GTM
  actions that need mutual visual distinction, not a point on a good→bad scale) and it's the tested
  contract with `contract.py` (`scripts/test_build_locality_data.py::test_contract_js_matches_py`, a
  literal-substring check requiring `GTM_COLORS` to keep holding real hex strings). It stays exactly as
  it is; only a comment is added noting `PUSH-NOW`/`HOLD` intentionally match `--status-success`/
  `--status-neutral`.
- **Consolidation target is `views.js`'s `VERDICT_BG`/`VERDICT_FG`, `margin.js`'s `COLOR`, every raw hex
  literal in both files' inline `style=` attributes, and `styles.css`'s existing severity-banner/alert-row
  rules** — all four rewritten to reference the new shared CSS custom properties instead of independently
  hardcoding shades of the same five concepts (success/warning/critical/neutral/info).
- **No build step exists in this repo** (plain `<script>` tags, no bundler) — CSS custom properties
  referenced from JS-generated `style="color:var(--status-success)"` strings is how consolidation actually
  happens (this pattern already exists once, in `margin.js:47`'s `var(--go)` — this spec generalizes it,
  doesn't invent it).
- **Dark mode is `[data-theme="dark"]`-attribute-driven**, one override block in `styles.css`, not a
  second stylesheet or a JS-computed palette. Light "paper" theme stays the default (unchanged
  `:root`); dark values only apply when the attribute is present.
- **A visible toggle ships in this sub-project**, not deferred to the nav-redesign sub-project — a dark
  theme with no way to activate it is dead code. Minimal: one button in `.topbar`, styled to match the
  existing `.tab` typographic language (uppercase IBM Plex Mono label), not an icon/emoji (nothing else in
  the app's chrome uses emoji). Preference persists via `localStorage`.

## Token values

Added to `styles.css`'s `:root` (existing 10 variables — `--paper`, `--surface`, `--ink`, `--muted`,
`--line`, `--goat`, `--sans`, `--mono`, `--radius`, `--go` — are unchanged):

```css
--status-success:      #059669;  --status-success-text: #166534;  --status-success-bg: #EAF7F0;
--status-warning:      #d97706;  --status-warning-text: #92400E;  --status-warning-bg: #FEF6E7;
--status-critical:     #991B1B;  --status-critical-text:#991B1B;  --status-critical-bg: #FDEDEC;
--status-neutral:      #6B6B66;  --status-neutral-text: #6B6B66;  --status-neutral-bg: #F0EFEA;
--status-info:         #2a78d6;  --status-info-text:    #1e40af;  --status-info-bg:    #EAF1FC;
```

Note `--status-neutral`/`--status-neutral-text` both equal `--muted` (`#6B6B66`) and
`--status-success`/`--status-success-text` differ (`#059669` vs `#166534`) — intentional, not
inconsistent; see the two-tier decision above.

`[data-theme="dark"]` override block (new — first dark-mode rule in the codebase):

```css
:root[data-theme="dark"]{
  --paper:#15161A; --surface:#1D1F26; --ink:#EDEBE4; --muted:#8B8A85; --line:#33353E;
  --status-success-bg:#0F2A20; --status-warning-bg:#2E2311; --status-critical-bg:#341413;
  --status-neutral-bg:#25262B; --status-info-bg:#152437;
  --status-success-text:#6EE7B7; --status-warning-text:#FBBF24; --status-critical-text:#F87171;
  --status-neutral-text:#A8A7A2; --status-info-text:#60A5FA;
}
```
The five `-text` shades **are** overridden in dark mode (caught in self-review — they were chosen for
WCAG-AA contrast against *light* pastel backgrounds; reused as-is against the new dark tinted backgrounds,
contrast would fail, e.g. `#991B1B` critical-text on `#341413` critical-bg-dark is dark-on-dark). The dark
`--status-critical-text` (`#F87171`) happens to be the exact value `margin.js` already hardcodes ad-hoc for
its "not viable" contribution figure — one more small piece of existing drift this consolidation catches.
`--goat`, `--go`, `--radius`, and the five *accent* `--status-*` (non-text, non-bg) values are left
unoverridden — used only for icons/dots/borders at 3:1 contrast requirements (not 4.5:1 text), they're
already vivid enough to read on the dark surface, and keeping them fixed is the continuity anchor between
themes.

## File-by-file changes

- **`web/styles.css`**: add the 15 status custom properties + dark override block (above) to `:root`;
  rewrite `.severity-banner.critical/.warning/.clear` and `.alert-row.critical/.warning/.info` to
  reference `var(--status-*)` instead of their own literal hex; add `.theme-toggle` button styling
  (matches `.tab`).
- **`web/views.js`**: two different color sources currently look similar but are semantically distinct —
  keeping them distinct in the rewrite matters (caught in self-review; an earlier draft of this spec
  conflated them):
  - `verdictBadge()` (ICP verdict `GO`/`SAMPLE-FIRST`/`WAIT`) and the generic present/absent indicators
    (`blinkit_goat_present` ✓/— at lines 23/60, `price_advantage_blinkit`'s `+₹` at line 31) are genuine
    severity/status signals with no GTM meaning — these become `var(--status-success)`/
    `var(--status-warning)`/`var(--status-neutral)` and their `-bg`/`-text` pairs. `VERDICT_BG`/
    `VERDICT_FG` module consts are deleted.
  - `renderMethodology()`'s action-matrix table (lines 77-79) literally *displays* the 5 GTM action
    colors as a legend (`Push now`, `D2C / offline (verify QC)`, `Sample + QC test`,
    `Sample (D2C / offline)`, `Hold`) — these six hardcoded hex literals (`#059669`, `#2a78d6`,
    `#d97706`, `#EF9F27`, `#888780` ×2) are replaced with `colorFor('PUSH-NOW')`,
    `colorFor('D2C / OFFLINE - verify QC')`, etc. — `contract.js`'s existing canonical function,
    already imported at the top of this file — not status tokens. (`#EF9F27` in particular has no
    status-token equivalent; it's a GTM-only color and was never part of the 5-status palette.)
  - `gtmDot()` already calls `colorFor(a)` — unchanged, already correct.
- **`web/margin.js`**: delete the `COLOR` map; `update()`'s verdict border/badge reference
  `var(--status-success)`/`var(--status-warning)`/`var(--status-critical)`; the `#f87171` "not viable"
  color becomes `var(--status-critical)`; the `rgba(255,255,255,.02)` card background becomes a real
  `.margin-verdict` CSS class (moved out of the inline `style=`) using `var(--surface)`.
- **`web/contract.js`**: no functional change — one comment added above `GTM_COLORS` noting the
  intentional match with the new status tokens (see Decisions above).
- **`web/index.html`**: add `<button class="theme-toggle" id="theme-toggle">Dark</button>` to `.topbar`,
  after `.tabs`.
- **`web/app.js`**: on `DOMContentLoaded`, read `localStorage.getItem('theme')`; if `'dark'`, set
  `document.documentElement.dataset.theme = 'dark'` and the toggle's label to `Light`. Click handler
  flips `document.documentElement.dataset.theme` between `'dark'`/unset, updates the button label, and
  writes the choice to `localStorage`.

## Testing

- `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v` — must
  still pass unmodified (proves `GTM_COLORS` wasn't touched in a way that breaks the contract).
- No new frontend pure-function tests — this sub-project is CSS custom-property + markup wiring, not new
  logic. Verification is manual: toggle dark mode and click through every existing view (Map, Leaderboard,
  Untapped Markets, Launch Roadmap, Margin Calculator, Shelf Monitor's both sub-tabs, Method), confirming
  no color regression in either theme and that the toggle's choice persists across a reload.

## Explicitly out of scope

- Typography (locked decision, see above).
- Any change to `GTM_COLORS`' values, the 5 GTM action colors, or `contract.py`.
- KPI ribbon, Decision Ledger, Leaderboard/Gems insight-card framing, table sorting/sticky headers, map
  UX — all three later sub-projects, unaffected by this one beyond inheriting the new tokens.
- A system-preference (`prefers-color-scheme`) auto-detect for dark mode — manual toggle only, per the
  locked decision that light stays the default regardless of OS theme.
- Command palette, conversational/chat surface, external alerting, mobile breakpoints — separate,
  much larger initiatives from the original task list, not part of any of the 4 sequenced sub-projects
  agreed so far.
