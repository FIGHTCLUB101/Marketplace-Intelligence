# Map View UX

## Why

Fourth and final sub-project decomposed from the broader UI/UX task list. Targets the task list's "Map View UX" section: responsive breakpoints, a marker-clustering audit, and filter placement. Builds on sub-project 1's design tokens, sub-project 2's KPI/insight-card work, and sub-project 3's data-table polish (all merged).

Scoping conversation established: this dashboard is a desktop/laptop-only internal GTM tool (no phone/tablet support needed) — the target range is roughly 1024px–1920px+, e.g. a laptop window split-screen next to a spreadsheet, not a phone in someone's pocket.

Verified live in the browser before designing (not assumed):
- **Zero `@media` breakpoints exist anywhere in the app today.** The Map view's layout (`.map-body{grid-template-columns:212px 1fr}`, `#profile{position:absolute;right:12px;top:12px;width:320px}`) is entirely fixed-width.
- **The profile panel does NOT clip off-screen** at narrow widths — computed bounding-box math at 900px viewport width showed `#profile`'s right edge at x=888, safely inside the 900px viewport. An earlier visual read that suggested clipping was wrong; see next finding for what was actually happening.
- **The profile panel and the map's native zoom controls (`NavigationControl`) overlap at every viewport width, not just narrow ones** — both are anchored to the same `'top-right'` corner. Confirmed via bounding-box intersection at 900px, 1200px, and 1920px alike: `overlap: true` in all cases. This is a real, width-independent bug, not a responsiveness gap.
- **Marker clustering breaks apart abruptly at `clusterMaxZoom:8`.** Tested centered on Bangalore: at zoom 8, dense areas render as a handful of cluster bubbles (e.g. point counts 97, 84, 36, 27); one step past the cutoff at zoom 9, all ~98 of those same localities render as individual, heavily-overlapping raw dots with no visual separation — confirmed via screenshot.
- **No other structural breakage found** across 900px, 1024px, 1200px, and 1920px+ viewports for the KPI ribbon, tabs, or map grid — tested directly, not assumed.

## Decisions locked in during design

- **Zoom controls move to `'bottom-right'`, not a repositioned profile panel.** A one-line `maplibregl.NavigationControl` anchor change fully avoids the collision, matches a common map-UI convention (zoom controls away from contextual detail panels), and requires no changes to `#profile`'s existing CSS.
- **`clusterMaxZoom` raised from `8` to `11`, no other clustering parameters changed.** Verified empirically (not guessed): at zoom 11 centered on Bangalore, dense areas still show legible small cluster bubbles (counts like 2–5) with zero overlap; at zoom 12 (one step past the new cutoff), the ~40 individual dots that emerge have enough geographic spread to render without overlapping. `clusterRadius` (46) is untouched — the reported symptom was specifically the abrupt cliff at the old cutoff, not the clustering density itself.
- **Sidebar width reduced from `212px` to `160px` — verified as the safe floor, not a rounder guess.** Tested 160px: every ledger label (including the longest, "D2C / offline (verify QC)"), all three filter `<select>`s, and the belt selector stayed fully legible with no text clipping, at both 1024px and full-width viewports. Tested 140px: `<select>` text visibly clipped ("All serviceabili▾") and the ledger sidebar gained its own vertical scrollbar — a real regression. 160px is therefore the recommended value, not a compromise.
- **No new `@media` breakpoints.** Since no structural breakage was found in the 1024–1920px+ range beyond the three items above, adding breakpoint machinery would be solving a problem that doesn't exist. If a future redesign needs true responsive behavior (e.g. phone support), that's new scope, not this sub-project.

## Zoom control repositioning

`web/locality-map.js`, inside `initMap()`:
```js
map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
```
(currently `'top-right'`). No CSS changes needed — MapLibre's control positioning classes handle the anchor automatically, and `#profile`'s existing `top:12px;right:12px` positioning is untouched.

## Marker clustering

`web/locality-map.js`, in the `localities` source definition inside `initMap()`:
```js
map.addSource('localities', { type: 'geojson', data: fc(L), cluster: true, clusterRadius: 46, clusterMaxZoom: 11 });
```
(currently `clusterMaxZoom: 8`). This is the only change — `clusterRadius`, the `clusters`/`cluster-count`/`locality-circles` layer definitions, and all paint properties are untouched.

## Sidebar width

`web/styles.css`:
```css
.map-body{flex:1;display:grid;grid-template-columns:160px 1fr;overflow:hidden;min-height:0}
```
(currently `212px 1fr`). No other rule changes — `.ledger`'s own padding/font-sizes and the `<select>` styling are untouched; they were verified to still fit at the new width without modification.

## Testing

- No new pure-function logic is introduced by any of the three changes — this is a control-anchor constant, a clustering config constant, and a CSS grid-column value. No unit tests apply, consistent with this repo's pure-function-only testing convention (there is nothing pure to test here).
- Manual verification (already performed once during design, to be repeated post-implementation): confirm zoom controls render at bottom-right and no longer overlap the profile panel at 900px/1200px/1920px when a locality is selected; confirm clustering holds together with legible, non-overlapping bubbles through zoom 11 and individual dots don't overlap at zoom 12+ in a dense area (e.g. Bangalore); confirm the 160px sidebar shows no clipped text and no unexpected scrollbar across the 1024–1920px+ range; repeat all of the above in dark mode.

## Explicitly out of scope

- Phone/tablet support, touch targets, hamburger navigation — this is a desktop/laptop-only internal tool per the scoping conversation.
- Column-hiding/responsive variants for data tables — already explicitly deferred to this sub-project by sub-project 3's spec, and still out of scope here since it's a data-table concern, not a Map view concern.
- Any redesign of the profile panel's content, the KPI ribbon, or the decision ledger's interaction model — only their fixed pixel widths/positions (where relevant to the three fixes above) are touched.
- Any change to `clusterRadius`, cluster bubble styling (`circle-radius` step function, colors), or the darkstore marker layers (`ds-Blinkit`/`ds-Zepto`/`ds-Swiggy Instamart`) — none of these were implicated in the clustering-pileup finding.
