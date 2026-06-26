# Future improvements — only when the data supports them

Two UX/modeling ideas were reviewed and **deliberately deferred** because our current data can't honestly
support them. Documented here so they aren't re-proposed without the prerequisites.

## 1. Isochrone serviceability (instead of Haversine radius)
**Idea:** replace the straight-line darkstore radius with 10-minute drive-time polygons (Mapbox Isochrone /
OSRM) + point-in-polygon, accounting for roads, rivers, one-ways, and rush-hour shrink.

**Why deferred — it would be false precision on our data:**
- The darkstore set is a **partial sample**. Exact polygons around incomplete stores produce precise-looking
  but incomplete coverage; the asymmetric *"absence ≠ unserviceable"* rule (NB08) is the honest model.
- Many locality coordinates are still **pincode-centroids (±~4 km)**. Point-in-polygon with a fuzzy point is
  moot — input error dwarfs the polygon precision.
- Mapbox Isochrone is paid/rate-limited; 4,081 stores = many calls. Dynamic rush-hour isochrones are a
  dispatch-ops concern, not a strategic-shortlisting one.

**Prerequisite to revisit:** near-complete darkstore coverage **and** locality-precise coordinates.

## 2. Margin calculator as a map-recoloring drawer
**Idea:** make Unit Economics a slide-out drawer whose sliders recolor the map (localities turn red/green).

**Why deferred — it doesn't fit the data model:** the margin calc is GOAT's **own** unit economics
(MRP/COGS/commission), **not a per-locality variable**. Map colors come from ICP × serviceability, not margin.
Wiring sliders to map color would imply a spatial relationship that doesn't exist. Would require modeling
per-locality economics first.

## Shipped instead (2026-06-27)
KPI ribbon ("first 5 seconds"), clearer tab labels (Launch Roadmap / Unit Economics / Untapped Markets),
and zoom-aware clustering (neutral count bubbles at country zoom → status dots at city zoom) — all of which
the current data fully supports.
