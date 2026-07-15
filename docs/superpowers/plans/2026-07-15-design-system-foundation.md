# Design System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate four independently-hardcoded copies of the same status colors (`styles.css`, `contract.js`'s categorical colors aside, `views.js`, `margin.js`, and the shelf-monitor severity CSS) into one set of CSS custom properties, and add a working dark mode on top of that same token set.

**Architecture:** Extend `styles.css`'s existing `:root` with a semantic status-token layer (4 statuses × 3 shades: accent/text/bg) plus a `[data-theme="dark"]` override block. Every JS file that currently hardcodes one of these hex values switches to `var(--status-*)` in its generated `style="..."` strings — the same pattern `margin.js` already uses once for `var(--go)`, generalized. A small button in the topbar flips `data-theme` and persists the choice to `localStorage`.

**Tech Stack:** Plain CSS custom properties, vanilla JS template strings — no build step, no CSS-in-JS, no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-design-system-foundation-design.md` — read it if anything below is ambiguous.
- `contract.js`'s `GTM_COLORS` values and structure do not change — it's the tested cross-language contract with `scripts/contract.py` (`scripts/test_build_locality_data.py::test_contract_js_matches_py`, a literal-substring check). Only a comment is added.
- Typography (`--sans`, `--mono`) is untouched — locked decision from brainstorming, not this plan's concern.
- **Deviation from the spec, caught during planning — only 4 status tokens (success/warning/critical/neutral), not 5.** The spec listed a 5th, `--status-info` (blue, `#2a78d6`), but tracing every actual call site during planning found it has zero consumers: the one place that color appears (`views.js`'s Methodology action-matrix table) turns out to literally display a GTM action's own color and correctly becomes `colorFor('D2C / OFFLINE - verify QC')` (Task 2), not a generic status token. Per YAGNI, this token isn't created. Every other token/file in this plan matches the spec.
- **`web/sequence.js` is explicitly untouched by this plan**, despite being named in the original (pre-spec) task list. Verified during planning: its inline `style="..."` usages are layout-only (`display`, `gap`, `width`, `padding`) and its one color usage already calls `colorFor()` and `var(--goat)`/`var(--line)`/`var(--mono)` — it has no hardcoded-hex duplication bug. Nothing to fix here.
- **This consolidation changes a handful of exact pixel values** (converging near-duplicate shades that drifted independently) — full list below so no task or review treats these as mistakes:
  | Where | Old | New | Why |
  |---|---|---|---|
  | Verdict badge `GO` background | `#E6F4EE` | `#EAF7F0` (`--status-success-bg`) | converges on the value shelf-monitor's severity banner already uses |
  | Verdict badge `GO` text | `#059669` | `#166534` (`--status-success-text`) | was using the accent shade for text; two-tier model puts text on the darker, already-established WCAG shade |
  | Verdict badge `SAMPLE-FIRST` text | `#B45309` | `#92400E` (`--status-warning-text`) | same convergence, warning axis |
  | `blinkit_goat_present`/`is_white_space` "absent" gray (`views.js` ×2, `locality-map.js` ×1) | `#888780` | `#6B6B66` (`--status-neutral`, = existing `--muted`) | was GTM's HOLD-specific gray; these usages are generic "absent" indicators, not GTM state, so the general muted gray is the more correct semantic fit |
  | White-space pill background (`locality-map.js`) | `#E6F4EE` | `#EAF7F0` (`--status-success-bg`) | same as verdict badge GO background, second occurrence |
  | Margin verdict card background | `rgba(255,255,255,.02)` | `var(--surface)` (solid) | the original was a near-invisible overlay tint, almost certainly an unintentional near-no-op; solid surface color is what every other card in the app already uses |
  | Margin "not viable" contribution text | `#f87171` | `#991B1B` (`--status-critical`) | normalizes to the same accent tier the adjacent "viable" case already used (`var(--go)`) — the original lighter red had no corresponding light-tier for green, i.e. it wasn't a deliberate two-tier choice |
  All GTM-categorical colors (`colorFor()` output) and the Methodology table are pixel-identical before/after — only the values above visibly shift.

---

### Task 1: `styles.css` — status token system + dark mode

**Files:**
- Modify: `web/styles.css`

**Interfaces:**
- Produces: CSS custom properties `--status-success`, `--status-success-text`, `--status-success-bg` (and the same three suffixes for `warning`, `critical`, `neutral`) — consumed by Tasks 2 and 3. Produces `.theme-toggle`, `.margin-verdict` (+ `.go`/`.caution`/`.stop` modifiers), `.verdict-badge.go`/`.caution`/`.stop` classes — consumed by Task 3 (`.margin-verdict`, `.verdict-badge.*`) and Task 4 (`.theme-toggle`).

- [ ] **Step 1: Add the status tokens and dark-mode override block**

In `web/styles.css`, replace the `:root{...}` block (lines 1-5) with:

```css
:root{
  --paper:#FAFAF7; --surface:#FFFFFF; --ink:#1A1A1A; --muted:#6B6B66; --line:#E6E4DD; --goat:#E8A317;
  --sans:'IBM Plex Sans',system-ui,sans-serif; --mono:'IBM Plex Mono',ui-monospace,monospace;
  --radius:8px; --go:#059669;
  --status-success:#059669; --status-success-text:#166534; --status-success-bg:#EAF7F0;
  --status-warning:#d97706; --status-warning-text:#92400E; --status-warning-bg:#FEF6E7;
  --status-critical:#991B1B; --status-critical-text:#991B1B; --status-critical-bg:#FDEDEC;
  --status-neutral:#6B6B66; --status-neutral-text:#6B6B66; --status-neutral-bg:#F0EFEA;
}
:root[data-theme="dark"]{
  --paper:#15161A; --surface:#1D1F26; --ink:#EDEBE4; --muted:#8B8A85; --line:#33353E;
  --status-success-bg:#0F2A20; --status-warning-bg:#2E2311; --status-critical-bg:#341413; --status-neutral-bg:#25262B;
  --status-success-text:#6EE7B7; --status-warning-text:#FBBF24; --status-critical-text:#F87171; --status-neutral-text:#A8A7A2;
}
```

- [ ] **Step 2: Rewrite the severity-banner and alert-row rules to use the new tokens**

Replace these six lines (currently near the end of the file, right after `.narrative{...}`):

```css
.severity-banner.critical{background:#FDEDEC;color:#991B1B}
.severity-banner.warning{background:#FEF6E7;color:#92400E}
.severity-banner.clear{background:#EAF7F0;color:#166534}
.alert-row.critical{border-left-color:#991B1B}
.alert-row.warning{border-left-color:#d97706}
```

with:

```css
.severity-banner.critical{background:var(--status-critical-bg);color:var(--status-critical-text)}
.severity-banner.warning{background:var(--status-warning-bg);color:var(--status-warning-text)}
.severity-banner.clear{background:var(--status-success-bg);color:var(--status-success-text)}
.alert-row.critical{border-left-color:var(--status-critical)}
.alert-row.warning{border-left-color:var(--status-warning)}
```

(`.alert-row.info{border-left-color:var(--goat)}` is unchanged — it already used a token, and it's intentionally the brand accent, not a status color; leave it exactly as-is, don't touch that line.)

- [ ] **Step 3: Add `.theme-toggle` and the margin-verdict/verdict-badge modifier classes**

Add to the end of `web/styles.css`:

```css

.theme-toggle{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:none;border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer}
.theme-toggle:hover{color:var(--ink);border-color:var(--muted)}

.margin-verdict{border:2px solid var(--line);border-radius:var(--radius);padding:1rem;background:var(--surface)}
.margin-verdict.go{border-color:var(--status-success)}
.margin-verdict.caution{border-color:var(--status-warning)}
.margin-verdict.stop{border-color:var(--status-critical)}
.verdict-badge.go{background:var(--status-success);color:#fff}
.verdict-badge.caution{background:var(--status-warning);color:#fff}
.verdict-badge.stop{background:var(--status-critical);color:#fff}
```

- [ ] **Step 4: Visually verify no regression in light mode**

Using a local dev server serving `web/` (e.g. `python -m http.server` from `web/`, or the project's existing dev setup), open the dashboard and check Shelf Monitor's "This Week" tab: the severity banner and any critical/warning alert-row cards must look pixel-identical to before this change (all the Step 2 values are unchanged numerically, only re-expressed as `var(...)`). If anything shifted, the token values were transcribed wrong — fix before proceeding.

- [ ] **Step 5: Commit**

```bash
git add web/styles.css
git commit -m "feat: add status-color design tokens and dark-mode override block"
```

---

### Task 2: `views.js` + `locality-map.js` — consolidate indicator/badge colors

**Files:**
- Modify: `web/views.js`
- Modify: `web/locality-map.js`

**Interfaces:**
- Consumes: the `--status-*` tokens from Task 1, and `colorFor()` (already imported in `views.js` from `./contract.js`, unchanged).

- [ ] **Step 1: Rewrite `verdictBadge` in `web/views.js`**

Replace:

```js
const VERDICT_BG = { GO: '#E6F4EE', 'SAMPLE-FIRST': '#FAF0DF', WAIT: '#F0EFEA' };
const VERDICT_FG = { GO: '#059669', 'SAMPLE-FIRST': '#B45309', WAIT: '#6B6B66' };
const verdictBadge = (v) =>
  `<span class="badge" style="background:${VERDICT_BG[v] || '#F0EFEA'};color:${VERDICT_FG[v] || '#6B6B66'}">${v}</span>`;
```

with:

```js
const VERDICT_STATUS = { GO: 'success', 'SAMPLE-FIRST': 'warning', WAIT: 'neutral' };
const verdictBadge = (v) => {
  const status = VERDICT_STATUS[v] || 'neutral';
  return `<span class="badge" style="background:var(--status-${status}-bg);color:var(--status-${status}-text)">${v}</span>`;
};
```

- [ ] **Step 2: Replace the three hardcoded-hex indicator spans in `web/views.js`**

In `renderLeaderboard()`, replace:
```js
      const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:#059669">✓</span>' : '<span style="color:#888780">—</span>')
        : '<span style="color:#ccc">n/a</span>';
```
with:
```js
      const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
        : '<span style="color:#ccc">n/a</span>';
```
(The `'n/a'` case's `#ccc` is unrelated to the status palette — a distinct "no data" gray, not "neutral status" — leave it as a literal, don't fold it into `--status-neutral`.)

Still in `renderLeaderboard()`, replace:
```js
        <td class="mono">${a !== null ? '<span style="color:#059669">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
```
with:
```js
        <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
```

In `renderGems()`'s `wsTable` template, replace:
```js
      <td>${t(l.blinkit_goat_present) ? '<span style="color:#059669">Listed ✓</span>' : '<span style="color:#888780">Not yet</span>'}</td>
```
with:
```js
      <td>${t(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>'}</td>
```

- [ ] **Step 3: Rewrite the Methodology action-matrix table to use `colorFor()` instead of raw hex**

In `renderMethodology()`, replace:
```js
      <tr><td class="mono">GO</td><td><span style="color:#059669">● Push now</span></td><td><span style="color:#2a78d6">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:#d97706">● Sample + QC test</span></td><td><span style="color:#EF9F27">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:#888780">● Hold</span></td><td><span style="color:#888780">● Hold</span></td></tr>
```
with:
```js
      <tr><td class="mono">GO</td><td><span style="color:${colorFor('PUSH-NOW')}">● Push now</span></td><td><span style="color:${colorFor('D2C / OFFLINE - verify QC')}">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:${colorFor('SAMPLE + QC test')}">● Sample + QC test</span></td><td><span style="color:${colorFor('SAMPLE (D2C / offline)')}">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td></tr>
```
(`colorFor` is already imported at the top of this file: `import { colorFor, labelFor } from './contract.js';` — no import change needed. This step produces pixel-identical output to before; it's a maintainability-only fix, not a value change.)

- [ ] **Step 4: Replace the three hardcoded-hex usages in `web/locality-map.js`**

Around line 118-121 (inside the function building the map profile panel's competitive-position section), replace:
```js
      ${row('GOAT on Blinkit', truthy(p.blinkit_goat_present) ? '<span style="color:#059669">Listed ✓</span>' : '<span style="color:#888780">Not yet</span>')}
      ${blAvg !== null ? row('Competitor avg price', '₹' + Math.round(blAvg), true) : ''}
      ${blAdv !== null ? row('GOAT price advantage', '<span style="color:#059669">+₹' + Math.round(blAdv) + ' cheaper</span>') : ''}
      ${truthy(p.is_white_space) ? '<div class="pr"><span class="pill" style="background:#E6F4EE;color:#059669;font-size:11px">White space — no competitors on BL or Zepto</span></div>' : ''}
```
with:
```js
      ${row('GOAT on Blinkit', truthy(p.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>')}
      ${blAvg !== null ? row('Competitor avg price', '₹' + Math.round(blAvg), true) : ''}
      ${blAdv !== null ? row('GOAT price advantage', '<span style="color:var(--status-success)">+₹' + Math.round(blAdv) + ' cheaper</span>') : ''}
      ${truthy(p.is_white_space) ? '<div class="pr"><span class="pill" style="background:var(--status-success-bg);color:var(--status-success);font-size:11px">White space — no competitors on BL or Zepto</span></div>' : ''}
```

- [ ] **Step 5: Visually verify**

With a local dev server, click through Leaderboard, Untapped Markets, Method, and the Map view's profile panel (click any locality with `blinkit_goat_present` data to see the competitive-position section). Confirm: verdict badges show a slightly darker green/amber text than before (expected, per the Global Constraints value-change table) and the Methodology table's colored dots look identical to before (expected — that one's pixel-for-pixel unchanged).

- [ ] **Step 6: Commit**

```bash
git add web/views.js web/locality-map.js
git commit -m "feat: consolidate hardcoded status colors in views.js and locality-map.js onto shared tokens"
```

---

### Task 3: `margin.js` — remove the `COLOR` map, use shared tokens and classes

**Files:**
- Modify: `web/margin.js`

**Interfaces:**
- Consumes: `--status-success`/`--status-warning`/`--status-critical` tokens and `.margin-verdict`/`.verdict-badge` modifier classes from Task 1.

- [ ] **Step 1: Delete the `COLOR` map and switch to CSS classes**

In `web/margin.js`, delete this line entirely:
```js
const COLOR = { GO:'#059669', CAUTION:'#d97706', STOP:'#991B1B' };
```
and add this one in its place:
```js
const VERDICT_CLASS = { GO: 'go', CAUTION: 'caution', STOP: 'stop' };
```

- [ ] **Step 2: Rewrite `update()`'s output template**

Replace:
```js
function update(){
  const mrp=num('m-mrp'), gm=num('m-gm');
  const r = calcEconomics({ mrp, grossMarginPercent:gm, brandDiscountPercent:num('m-disc'),
    commissionRate:num('m-comm')/100, fulfilmentFee:num('m-ful'),
    monthlyAdBudget:num('m-ad'), monthlyOrders:num('m-ord') });
  const v = getVerdict({ grossMarginPercent:gm, netRealization:r.netRealization, monthlyAdBudget:num('m-ad') });
  document.getElementById('m-out').innerHTML = `
    <div style="border:2px solid ${COLOR[v]};border-radius:var(--radius);padding:1rem;background:rgba(255,255,255,.02)">
      <span class="verdict-badge" style="background:${COLOR[v]};color:#fff">${v}</span>
      <div style="display:flex;gap:2rem;margin-top:.75rem;flex-wrap:wrap">
        <div><div class="stat-label">Net realization</div><div class="stat-val">₹${r.netRealization}</div></div>
        <div><div class="stat-label">Net contribution / order</div><div class="stat-val" style="color:${r.isViable?'var(--go)':'#f87171'}">₹${r.netContribution}</div></div>
        <div><div class="stat-label">Contribution %</div><div class="stat-val">${r.netContributionPercent}%</div></div>
      </div>
      <p class="info" style="margin-top:.75rem">Net realization = selling price × (1 − commission) − fulfilment. Contribution subtracts COGS, logistics (10%), returns (2.5%), ad/order. Thresholds: QCompass GO/CAUTION/STOP.</p>
    </div>`;
}
```
with:
```js
function update(){
  const mrp=num('m-mrp'), gm=num('m-gm');
  const r = calcEconomics({ mrp, grossMarginPercent:gm, brandDiscountPercent:num('m-disc'),
    commissionRate:num('m-comm')/100, fulfilmentFee:num('m-ful'),
    monthlyAdBudget:num('m-ad'), monthlyOrders:num('m-ord') });
  const v = getVerdict({ grossMarginPercent:gm, netRealization:r.netRealization, monthlyAdBudget:num('m-ad') });
  const vClass = VERDICT_CLASS[v];
  document.getElementById('m-out').innerHTML = `
    <div class="margin-verdict ${vClass}">
      <span class="verdict-badge ${vClass}">${v}</span>
      <div style="display:flex;gap:2rem;margin-top:.75rem;flex-wrap:wrap">
        <div><div class="stat-label">Net realization</div><div class="stat-val">₹${r.netRealization}</div></div>
        <div><div class="stat-label">Net contribution / order</div><div class="stat-val" style="color:${r.isViable ? 'var(--status-success)' : 'var(--status-critical)'}">₹${r.netContribution}</div></div>
        <div><div class="stat-label">Contribution %</div><div class="stat-val">${r.netContributionPercent}%</div></div>
      </div>
      <p class="info" style="margin-top:.75rem">Net realization = selling price × (1 − commission) − fulfilment. Contribution subtracts COGS, logistics (10%), returns (2.5%), ad/order. Thresholds: QCompass GO/CAUTION/STOP.</p>
    </div>`;
}
```

- [ ] **Step 3: Visually verify**

With a local dev server, open Margin Calculator (via the `++` dropdown). Confirm the verdict card's border/badge color is correct for all three verdicts — edit the MRP/gross-margin/ad-budget fields to trigger GO, CAUTION, and STOP at least once each (thresholds are in `getVerdict()`: STOP if gross margin < 50 or net realization < 150 or ad budget < 100000; GO if gross margin ≥ 65 and net realization ≥ 250 and ad budget ≥ 200000; else CAUTION). Confirm the card background is now solid white (was a near-invisible tint before — this is an intended, visible change per the Global Constraints table, not a bug).

- [ ] **Step 4: Commit**

```bash
git add web/margin.js
git commit -m "feat: consolidate margin.js verdict colors onto shared status tokens"
```

---

### Task 4: dark-mode toggle wiring + remaining small consolidations

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/contract.js`

**Interfaces:**
- Consumes: `.theme-toggle` class (Task 1), `--status-success` token (Task 1).
- Produces: a working `#theme-toggle` button that flips `document.documentElement.dataset.theme` and persists the choice — this is the only way to actually see Task 1's dark override block, so later manual verification (Task 5) depends on this.

- [ ] **Step 1: Add the toggle button to the topbar**

In `web/index.html`, replace:
```html
      <button class="tab" data-view="sequence">Launch Roadmap</button>
      <button class="tab" data-view="shelf">Shelf Monitor</button>
      <button class="tab" data-view="methodology">Method</button>
    </nav>
  </div>
```
with:
```html
      <button class="tab" data-view="sequence">Launch Roadmap</button>
      <button class="tab" data-view="shelf">Shelf Monitor</button>
      <button class="tab" data-view="methodology">Method</button>
    </nav>
    <button class="theme-toggle" id="theme-toggle">Dark</button>
  </div>
```

- [ ] **Step 2: Wire the toggle in `app.js`**

In `web/app.js`, inside the `document.addEventListener('DOMContentLoaded', () => { ... })` callback, add this as the very first lines of the callback body (before the existing `// city filter options` comment):
```js
  const themeToggle = document.getElementById('theme-toggle');
  const applyTheme = (theme) => {
    if (theme === 'dark') { document.documentElement.dataset.theme = 'dark'; themeToggle.textContent = 'Light'; }
    else { delete document.documentElement.dataset.theme; themeToggle.textContent = 'Dark'; }
  };
  applyTheme(localStorage.getItem('theme') === 'dark' ? 'dark' : 'light');
  themeToggle.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('theme', next);
  });

```

- [ ] **Step 3: Fix the one remaining hardcoded status color in `app.js`**

In `renderKpis()`, replace:
```js
    <div class="kpi"><div class="kn" style="color:#059669">${push}</div><div class="kl">Ready to launch · push-now</div></div>
```
with:
```js
    <div class="kpi"><div class="kn" style="color:var(--status-success)">${push}</div><div class="kl">Ready to launch · push-now</div></div>
```
(Pixel-identical — `--status-success` is `#059669`, the same value. This was found during planning, not listed in the spec's file list, but it's the exact same bug the spec targets.)

- [ ] **Step 4: Add the documentation comment to `contract.js`**

In `web/contract.js`, immediately above `export const GTM_COLORS = {`, add:
```js
// PUSH-NOW and HOLD intentionally match styles.css's --status-success/--status-neutral tokens
// (see docs/superpowers/specs/2026-07-15-design-system-foundation-design.md) — not re-derived from
// them, since this file is also read by Python-side tooling with no CSS access.
```

- [ ] **Step 5: Verify the toggle works**

With a local dev server, click the "Dark" button in the topbar. Confirm: the whole page (background, text, all cards) switches to the dark palette, the button label changes to "Light", and reloading the page keeps dark mode active (persisted via `localStorage`). Click "Light" to switch back, reload, confirm it stays light.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js web/contract.js
git commit -m "feat: add dark-mode toggle and fix remaining hardcoded status color in app.js"
```

---

### Task 5: Full regression pass (light + dark)

**Files:** none (verification only)

- [ ] **Step 1: Run the existing contract test**

Run: `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v`
Expected: PASS (proves `GTM_COLORS` in `contract.js` still contains every required literal hex/action-name pair — Task 4 only added a comment above it, no functional change).

- [ ] **Step 2: Manual walkthrough, light mode**

With a local dev server, starting from a fresh page load (light mode is default), click through every view: Map (including opening a locality profile panel with competitive-position data), the `++` dropdown's Leaderboard/Untapped Markets/Margin Calculator, Launch Roadmap, Shelf Monitor (both This Week and Compare Brands sub-tabs), Method. Confirm no visual regression and no console errors.

- [ ] **Step 3: Manual walkthrough, dark mode**

Click the theme toggle to switch to dark. Repeat the same click-through as Step 2. Confirm: every view is legibly dark-themed (no white-on-white or black-on-black text), status colors (severity banners, verdict badges, margin verdict card, KPI ribbon's push-now number) are all visibly distinct from each other and from the background, and the map's own dark base style (`#0d0f12`, unrelated to this token system) still looks correct alongside the now-dark surrounding chrome.

- [ ] **Step 4: Commit (only if Step 2 or 3 required fixes)**

If the manual walkthrough surfaced any bugs, fix them, re-run the affected step, then:
```bash
git add -A
git commit -m "fix: address issues found in design-system-foundation regression pass"
```
If no fixes were needed, skip this step — nothing to commit.
