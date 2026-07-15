# KPI Ribbon + Insight Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the KPI ribbon real visual hierarchy (one primary stat, three secondary), and reframe Leaderboard's top 5 rows as action-led insight cards while rows 6-60 stay in the existing table.

**Architecture:** Pure markup/CSS restructuring of two existing render functions (`web/app.js`'s `renderKpis()`, `web/views.js`'s `renderLeaderboard()`) plus new CSS classes in `web/styles.css`, all built on sub-project 1's token system (`--status-*`, plus one new `--hover-bg` token). No new data, no new endpoints, no new dependencies.

**Tech Stack:** Vanilla JS template strings, plain CSS — matches the rest of the codebase, no build step.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-kpi-insight-cards-design.md` — read it if anything below is ambiguous.
- No trend lines / sparklines — locked decision, real data-architecture gap (see spec's Why section), not part of this plan.
- `renderGems()` in `web/views.js` is not touched by any task in this plan.
- The insight card's leading color comes from `colorFor(l.gtm_action)`/`labelFor(l.gtm_action)` (categorical, `contract.js`) — never from the `--status-*` tokens, which stay reserved for `icp_verdict`/severity contexts. Keeping these two color sources distinct is a carry-over principle from sub-project 1, not new to this plan.
- `.kn`/`.kl` (the KPI number/label classes) are used nowhere in the codebase except the 4 KPI cards (verified via grep) — safe to resize without side effects elsewhere.

---

### Task 1: `styles.css` — hover token, KPI hierarchy, insight-card classes

**Files:**
- Modify: `web/styles.css`

**Interfaces:**
- Produces: `--hover-bg` custom property (light + dark). Produces `.kpi.primary`, `.kpi-secondary` (consumed by Task 2). Produces `.insight-cards`, `.insight-card`, `.insight-head`, `.insight-rank`, `.insight-action`, `.insight-icp`, `.insight-locality`, `.insight-city`, `.insight-meta` (consumed by Task 3).

- [ ] **Step 1: Add the `--hover-bg` token to both the light and dark blocks**

In `web/styles.css`, the `:root{...}` block currently ends with:
```css
  --status-neutral:#6B6B66; --status-neutral-text:#6B6B66; --status-neutral-bg:#F0EFEA;
}
```
Change to:
```css
  --status-neutral:#6B6B66; --status-neutral-text:#6B6B66; --status-neutral-bg:#F0EFEA;
  --hover-bg:#F4F2EB;
}
```
And the `:root[data-theme="dark"]{...}` block currently ends with:
```css
  --status-success-text:#6EE7B7; --status-warning-text:#FBBF24; --status-critical-text:#F87171; --status-neutral-text:#A8A7A2;
}
```
Change to:
```css
  --status-success-text:#6EE7B7; --status-warning-text:#FBBF24; --status-critical-text:#F87171; --status-neutral-text:#A8A7A2;
  --hover-bg:#2A2C33;
}
```

- [ ] **Step 2: Swap the two hardcoded hover hex values to the new token**

Replace:
```css
.lrow:hover{background:#F4F2EB}
```
with:
```css
.lrow:hover{background:var(--hover-bg)}
```
Replace:
```css
.lb tr:hover td{background:#F7F5EF}
```
with:
```css
.lb tr:hover td{background:var(--hover-bg)}
```
(Do not touch `.tab:hover`, `.tab.active`, or `.dd-item:hover` — out of scope, see Global Constraints.)

- [ ] **Step 3: Rewrite the KPI ribbon rules for hierarchy**

Replace:
```css
.kpi-ribbon{display:flex;background:var(--surface);border-bottom:1px solid var(--line);flex-shrink:0}
.kpi{padding:11px 22px;border-right:1px solid var(--line)}
.kn{font-family:var(--mono);font-size:22px;font-weight:600;line-height:1}
.kn .ks{font-size:11px;font-weight:400;color:var(--muted);margin-left:5px}
.kl{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:5px}
```
with:
```css
.kpi-ribbon{display:flex;background:var(--surface);border-bottom:1px solid var(--line);flex-shrink:0}
.kpi{padding:11px 22px;border-right:1px solid var(--line)}
.kpi.primary{padding:14px 26px;border-left:3px solid var(--goat)}
.kpi.primary .kn{font-size:34px}
.kpi-secondary{display:flex;flex:1}
.kn{font-family:var(--mono);font-size:20px;font-weight:600;line-height:1}
.kn .ks{font-size:11px;font-weight:400;color:var(--muted);margin-left:5px}
.kl{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:5px}
```

- [ ] **Step 4: Add the insight-card classes**

Add to the end of `web/styles.css`:
```css

.insight-cards{display:flex;flex-direction:column;gap:8px;margin-bottom:18px}
.insight-card{border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;background:var(--surface)}
.insight-head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.insight-rank{font-family:var(--mono);font-size:11px;color:var(--muted)}
.insight-action{font-family:var(--mono);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.insight-icp{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:auto}
.insight-locality{font-size:15px;font-weight:600;margin-bottom:4px}
.insight-city{font-weight:400;color:var(--muted);font-size:13px}
.insight-meta{font-size:12px;color:var(--muted);margin-top:2px}
```

- [ ] **Step 5: Visually verify no unrelated regression**

Using a local dev server, confirm: Decision Ledger and Leaderboard table row hover states still show a light tint in light mode (visually the same as before — `#F4F2EB`/`#F7F5EF` and the new `--hover-bg:#F4F2EB` are close enough to be indistinguishable at a glance for the ledger, and the table row hover changes from `#F7F5EF` to `#F4F2EB`, a very subtle shift, expected). The KPI ribbon and Leaderboard will look unchanged until Tasks 2-3 add the markup that uses these new classes — that's expected at this point, not a bug.

- [ ] **Step 6: Commit**

```bash
git add web/styles.css
git commit -m "feat: add hover-bg token, KPI hierarchy, and insight-card CSS classes"
```

---

### Task 2: `app.js` — KPI ribbon hierarchy markup

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `.kpi.primary`, `.kpi-secondary` (Task 1).

- [ ] **Step 1: Rewrite `renderKpis()`'s output markup**

Replace:
```js
  document.getElementById('kpi-ribbon').innerHTML = `
    <div class="kpi"><div class="kn">1,001<span class="ks">${mapped} mapped</span></div><div class="kl">Localities analysed</div></div>
    <div class="kpi"><div class="kn" style="color:var(--status-success)">${push}</div><div class="kl">Ready to launch · push-now</div></div>
    <div class="kpi"><div class="kn">${gems}</div><div class="kl">Untapped markets</div></div>
    <div class="kpi"><div class="kn">${conf}%</div><div class="kl">Quick-commerce confirmed</div></div>`;
```
with:
```js
  document.getElementById('kpi-ribbon').innerHTML = `
    <div class="kpi primary">
      <div class="kn">1,001<span class="ks">${mapped} mapped</span></div>
      <div class="kl">Localities analysed</div>
    </div>
    <div class="kpi-secondary">
      <div class="kpi"><div class="kn" style="color:var(--status-success)">${push}</div><div class="kl">Ready to launch · push-now</div></div>
      <div class="kpi"><div class="kn">${gems}</div><div class="kl">Untapped markets</div></div>
      <div class="kpi"><div class="kn">${conf}%</div><div class="kl">Quick-commerce confirmed</div></div>
    </div>`;
```
(Nothing else in `renderKpis()` changes — the `mapped`/`push`/`gems`/`conf` calculations above this template stay exactly as they are.)

- [ ] **Step 2: Visually verify the hierarchy**

Using a local dev server, open the Map view. Confirm: "Localities analysed" is now visually the largest, leftmost stat with a gold left-border accent; the other three stats sit to its right, smaller, in their own row-like group. Push-now's number is still green. Check both light and dark mode.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: give the KPI ribbon real F-pattern visual hierarchy"
```

---

### Task 3: `views.js` — Leaderboard insight cards

**Files:**
- Modify: `web/views.js`

**Interfaces:**
- Consumes: `.insight-cards`, `.insight-card`, `.insight-head`, `.insight-rank`, `.insight-action`, `.insight-icp`, `.insight-locality`, `.insight-city`, `.insight-meta` (Task 1); `colorFor`/`labelFor` (already imported from `./contract.js`).
- Produces: no new exports — `renderLeaderboard()`'s external behavior (called from `app.js`, writes into `#leaderboard`) is unchanged, only its internal output markup changes.

- [ ] **Step 1: Replace `renderLeaderboard()` in full**

Replace the entire function:
```js
export function renderLeaderboard() {
  const rows = [...L].sort((a, b) => +b.icp_score - +a.icp_score).slice(0, 60);
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const truthy = (v) => v === true || v === 'true' || v === 'True';
  document.getElementById('leaderboard').innerHTML = `
    <table class="lb"><thead><tr>
      <th>#</th><th>Locality</th><th>City</th><th>ICP</th><th>Verdict</th><th>Serviceability</th>
      <th>Archetype</th><th>Action</th><th>GOAT on BL</th><th>Price Adv.</th></tr></thead><tbody>
    ${rows.map((l, i) => {
      const a = num(l.price_advantage_blinkit);
      const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
        : '<span style="color:#ccc">n/a</span>';
      return `<tr>
        <td class="mono">${i + 1}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
        <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
        <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
        <td>${gtmDot(l.gtm_action)}</td>
        <td class="mono">${goatBL}</td>
        <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
    }).join('')}
    </tbody></table>`;
}
```
with:
```js
export function renderLeaderboard() {
  const rows = [...L].sort((a, b) => +b.icp_score - +a.icp_score).slice(0, 60);
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const truthy = (v) => v === true || v === 'true' || v === 'True';

  const goatPart = (l) => {
    if (l.blinkit_goat_present === '' || l.blinkit_goat_present == null) return null;
    return `GOAT on Blinkit ${truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>'}`;
  };
  const pricePart = (a) => a !== null ? `<span style="color:var(--status-success)">+₹${Math.round(a)}</span> price advantage` : null;

  const insightCard = (l, rank) => {
    const a = num(l.price_advantage_blinkit);
    const metaParts = [goatPart(l), pricePart(a)].filter(Boolean);
    const metaLine2 = metaParts.length ? `<div class="insight-meta">${metaParts.join(' · ')}</div>` : '';
    return `
      <div class="insight-card">
        <div class="insight-head">
          <span class="insight-rank">#${rank}</span>
          <span class="insight-action" style="color:${colorFor(l.gtm_action)}">● ${labelFor(l.gtm_action)}</span>
          <span class="insight-icp">ICP <b>${Math.round(+l.icp_score)}</b></span>
        </div>
        <div class="insight-locality">${l.AREA.split(',')[0].trim()} <span class="insight-city">· ${l.ADDRESS}</span></div>
        <div class="insight-meta">${l.serviceability_state} · ${l.archetype_ml}</div>
        ${metaLine2}
      </div>`;
  };

  const top5 = rows.slice(0, 5);
  const rest = rows.slice(5);

  const insightsHtml = `<div class="insight-cards">${top5.map((l, i) => insightCard(l, i + 1)).join('')}</div>`;

  const tableHtml = `
    <table class="lb"><thead><tr>
      <th>#</th><th>Locality</th><th>City</th><th>ICP</th><th>Verdict</th><th>Serviceability</th>
      <th>Archetype</th><th>Action</th><th>GOAT on BL</th><th>Price Adv.</th></tr></thead><tbody>
    ${rest.map((l, i) => {
      const a = num(l.price_advantage_blinkit);
      const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
        : '<span style="color:#ccc">n/a</span>';
      return `<tr>
        <td class="mono">${i + 6}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
        <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
        <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
        <td>${gtmDot(l.gtm_action)}</td>
        <td class="mono">${goatBL}</td>
        <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
    }).join('')}
    </tbody></table>`;

  document.getElementById('leaderboard').innerHTML = insightsHtml + tableHtml;
}
```
(`verdictBadge`, `gtmDot`, `colorFor`, `labelFor` are all already defined/imported earlier in this file — no import changes needed. Nothing else in `views.js` — `renderGems()`, `renderMethodology()` — changes.)

- [ ] **Step 2: Visually verify**

Using a local dev server, open Leaderboard (via the `++` dropdown). Confirm:
- Exactly 5 insight cards render above the table, highest ICP score first.
- Each card's action label/color matches what that same locality's "Action" column would have shown in the old table (cross-check against the Map view's decision ledger colors, or against Untapped Markets if the same locality appears there).
- The table below starts at rank **6**, not 1, and has 55 rows.
- A card whose locality has no `price_advantage_blinkit` and no `blinkit_goat_present` data shows only the serviceability/archetype line, with no empty second meta line (find a case where this is true, if the top 5 all happen to have full data, temporarily check further down the sorted list by editing `top5`/`rest` slice indices locally to confirm the omission logic — then revert).
- Check both light and dark mode.

- [ ] **Step 3: Commit**

```bash
git add web/views.js
git commit -m "feat: reframe Leaderboard's top 5 rows as action-led insight cards"
```

---

### Task 4: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the existing test suites**

Run: `cd scripts && python -m pytest test_build_locality_data.py::test_contract_js_matches_py -v` — expected PASS (nothing in this plan touches `contract.js`).
Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/shelf-monitor.test.js` — expected all pass (nothing in this plan touches any tested pure function).

- [ ] **Step 2: Manual end-to-end walkthrough, light and dark**

With a local dev server: load the Map view fresh, confirm the KPI hierarchy; open Leaderboard, confirm the 5 insight cards + 55-row table (starting at #6); toggle dark mode and repeat both checks; hover a Decision Ledger row and a Leaderboard table row in both themes and confirm the hover tint looks correct (not the old unthemed light-mode-only hex). Click through Untapped Markets, Launch Roadmap, Margin Calculator, Shelf Monitor, Method to confirm no regression elsewhere (none of those files were touched, but confirm no console errors from a stale reference).

- [ ] **Step 3: Commit (only if fixes were needed)**

If the walkthrough surfaced any bugs, fix them, re-run the affected step, then:
```bash
git add -A
git commit -m "fix: address issues found in kpi-insight-cards regression pass"
```
If no fixes were needed, skip this step — nothing to commit.
