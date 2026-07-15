# Map View UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the map's zoom-control/profile-panel collision, stop marker clustering from dumping overlapping raw dots into view, and reclaim map space by narrowing the fixed-width sidebar — three small, independently verified config changes.

**Architecture:** No new files, no new logic. Three one-line configuration changes across two existing files: two in `web/locality-map.js` (a MapLibre control anchor, a clustering threshold) and one in `web/styles.css` (a CSS grid column width).

**Tech Stack:** Vanilla JS, plain CSS, MapLibre GL JS — no build step, no new runtime dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-map-view-ux-design.md` — read it if anything below is ambiguous.
- Target viewport range: ~1024px–1920px+ desktop/laptop. No phone/tablet support, no new `@media` breakpoints — none are needed per the spec's live-tested findings.
- `clusterRadius` (46), the `clusters`/`cluster-count`/`locality-circles` layer definitions, all paint properties, and the darkstore marker layers (`ds-Blinkit`/`ds-Zepto`/`ds-Swiggy Instamart`) are untouched — only `clusterMaxZoom`'s value changes.
- `#profile`'s own CSS (`position:absolute;right:12px;top:12px;width:320px`) is untouched — the zoom-control collision is fixed by moving the control, not the panel.
- `.ledger`'s padding/font-sizes and the `<select>` styling are untouched — only `.map-body`'s grid-column width changes.

---

### Task 1: `locality-map.js` — zoom control position + clustering threshold

**Files:**
- Modify: `web/locality-map.js`

**Interfaces:** None — both changes are MapLibre configuration values with no consumers elsewhere in the codebase.

- [ ] **Step 1: Move the zoom controls to bottom-right**

In `web/locality-map.js`, inside `initMap()`, change:
```js
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
```
to:
```js
  map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
```

- [ ] **Step 2: Raise the clustering cutoff**

In `web/locality-map.js`, inside `initMap()`'s `map.on('load', ...)` handler, change:
```js
    map.addSource('localities', { type: 'geojson', data: fc(L), cluster: true, clusterRadius: 46, clusterMaxZoom: 8 });
```
to:
```js
    map.addSource('localities', { type: 'geojson', data: fc(L), cluster: true, clusterRadius: 46, clusterMaxZoom: 11 });
```

- [ ] **Step 3: Visually verify**

Using a local dev server, open the Map view. Click any locality to open the profile panel and confirm the zoom controls (+/−) now render at the bottom-right corner of the map, no longer overlapping the profile panel — check this at both a narrow (~1024px) and full-width browser window. Then verify clustering: zoom into a dense area (e.g. Bangalore, roughly `[77.5946, 12.9716]`) and confirm cluster bubbles with legible counts persist through zoom level 11 with no overlapping raw dots, and that individual dots at zoom 12+ render with visible separation, not stacked on top of each other.

- [ ] **Step 4: Commit**

```bash
git add web/locality-map.js
git commit -m "fix: move zoom controls to bottom-right, raise cluster cutoff to zoom 11

Zoom controls previously overlapped the profile panel at every viewport
width (both anchored to top-right). Clustering previously broke apart
abruptly at zoom 8, dumping 90+ overlapping individual dots into dense
areas before they had visual room to separate."
```

---

### Task 2: `styles.css` — narrower map sidebar

**Files:**
- Modify: `web/styles.css`

**Interfaces:** None — a single CSS custom value with no JS consumers.

- [ ] **Step 1: Narrow the sidebar column**

In `web/styles.css`, change:
```css
.map-body{flex:1;display:grid;grid-template-columns:212px 1fr;overflow:hidden;min-height:0}
```
to:
```css
.map-body{flex:1;display:grid;grid-template-columns:160px 1fr;overflow:hidden;min-height:0}
```

- [ ] **Step 2: Visually verify**

Using a local dev server, open the Map view at both a narrow (~1024px) and full-width browser window. Confirm every decision-ledger row's label and count are fully visible with no clipping (including the longest label, "D2C / offline (verify QC)"), all three filter `<select>`s ("All cities" / "All verdicts" / "All serviceability") show their full text with no truncation, and the belt selector's text isn't cut off. Confirm the sidebar does not gain its own scrollbar at either width — if it does, the reduction went too far and needs investigation before proceeding, since the spec's own testing found 160px is the safe floor (140px was confirmed too narrow).

- [ ] **Step 3: Commit**

```bash
git add web/styles.css
git commit -m "fix: narrow map sidebar from 212px to 160px, reclaiming map space

Verified 160px keeps every ledger label, filter dropdown, and the belt
selector fully legible with no clipping or new scrollbar, at both 1024px
and full-width viewports; 140px was tested and found too narrow."
```

---

### Task 3: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full frontend test suite**

Run: `node --test web/tests/frontend.test.js web/tests/sequence.test.js web/tests/margin.test.js web/tests/shelf-monitor.test.js web/tests/sortable-table.test.js`
Expected: all pass. (No new tests are introduced by this sub-project — the three changes are configuration values with nothing pure to unit-test, consistent with this repo's testing convention.)

- [ ] **Step 2: Manual end-to-end walkthrough, light and dark, across the target viewport range**

With a local dev server: at 1024px, 1200px, and full-width (1920px+), open the Map view, click a locality to open the profile panel, and confirm the zoom controls stay clear of it at every width. Zoom into at least one other dense area besides Bangalore (e.g. Mumbai or Delhi) and confirm clustering holds together with no overlapping dots through zoom 11, splitting cleanly by zoom 12. Exercise the city/verdict/serviceability filters and the belt selector to confirm the narrower sidebar doesn't clip any dropdown option text when opened. Click through every other view (Leaderboard, Untapped Markets, Launch Roadmap, Margin Calculator, Shelf Monitor, Method) to confirm no regression and no console errors from either change. Repeat the whole pass in dark mode.

- [ ] **Step 3: Commit (only if fixes were needed)**

If the walkthrough surfaced any bugs, fix them, re-run the affected step, then:
```bash
git add -A
git commit -m "fix: address issues found in map-view-ux regression pass"
```
If no fixes were needed, skip this step — nothing to commit.
