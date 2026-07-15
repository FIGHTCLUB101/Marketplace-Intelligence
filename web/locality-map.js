import { colorFor, labelFor } from './contract.js';

const L = window.LOCALITIES || [];
L.forEach((l, i) => (l._idx = i));
let map;
const truthy = (v) => v === true || v === 'true' || v === 'True';

function fc(records) {
  return {
    type: 'FeatureCollection',
    features: records.map((l) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [+l.lng, +l.lat] },
      properties: { _i: l._idx, color: l.color, icp_score: +l.icp_score },
    })),
  };
}

// Filtering updates the SOURCE data (not a layer filter) so cluster counts recompute correctly.
export function setLocalityData(records) {
  const s = map && map.getSource('localities');
  if (s) s.setData(fc(records));
}

export function initMap() {
  map = new maplibregl.Map({
    container: 'map-container', style: 'https://tiles.openfreemap.org/styles/dark',
    center: [78.9629, 20.5937], zoom: 4.4, minZoom: 3, maxZoom: 16,
  });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  window._map = map;

  map.on('load', async () => {
    try {
      const ds = (await (await fetch('darkstores.json')).json()).markers || [];
      const DSC = { 'Blinkit': '#f59e0b', 'Zepto': '#a855f7', 'Swiggy Instamart': '#f97316' };
      map.addSource('darkstores', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: ds
          .filter((m) => m.lat != null)
          .map((m) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [m.lng, m.lat] }, properties: { brand: m.brand } })) },
      });
      Object.entries(DSC).forEach(([b, c]) => map.addLayer({
        id: 'ds-' + b, type: 'circle', source: 'darkstores', filter: ['==', ['get', 'brand'], b],
        paint: { 'circle-radius': 2, 'circle-color': c, 'circle-opacity': 0.30 },
      }));
    } catch (e) { console.warn('darkstores load failed', e); }

    // Localities, clustered: neutral count bubbles at macro zoom -> status-colored dots at city zoom.
    map.addSource('localities', { type: 'geojson', data: fc(L), cluster: true, clusterRadius: 46, clusterMaxZoom: 8 });
    map.addLayer({
      id: 'clusters', type: 'circle', source: 'localities', filter: ['has', 'point_count'],
      paint: {
        'circle-color': '#FFFFFF', 'circle-opacity': 0.92,
        'circle-stroke-color': '#888780', 'circle-stroke-width': 1.5,
        'circle-radius': ['step', ['get', 'point_count'], 13, 10, 18, 50, 24],
      },
    });
    map.addLayer({
      id: 'cluster-count', type: 'symbol', source: 'localities', filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Regular'], 'text-size': 12 },
      paint: { 'text-color': '#1A1A1A' },
    });
    map.addLayer({
      id: 'locality-circles', type: 'circle', source: 'localities', filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['get', 'icp_score'], 0, 4, 100, 11],
        'circle-color': ['get', 'color'], 'circle-stroke-width': 1.2, 'circle-stroke-color': '#ffffff', 'circle-opacity': 0.9,
      },
    });

    map.on('click', 'clusters', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ['clusters'] })[0];
      map.getSource('localities').getClusterExpansionZoom(f.properties.cluster_id, (err, z) => {
        if (!err) map.easeTo({ center: f.geometry.coordinates, zoom: z, duration: 500 });
      });
    });
    map.on('click', 'locality-circles', (e) => showProfile(L[e.features[0].properties._i]));
    ['clusters', 'locality-circles'].forEach((ly) => {
      map.on('mouseenter', ly, () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', ly, () => (map.getCanvas().style.cursor = ''));
    });
  });
}

export function resizeMap() { if (map) setTimeout(() => map.resize(), 80); }

export function highlightBelt(beltId) {
  if (beltId === 'all') { setLocalityData(L); return; }
  const id = +beltId;
  const m = L.filter((l) => +l.belt_id === id);
  setLocalityData(m);
  if (!m.length || !map) return;
  const lngs = m.map((l) => +l.lng), lats = m.map((l) => +l.lat);
  map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
    { padding: 70, maxZoom: 13, duration: 600 });
}

export function showProfile(p) {
  const panel = document.getElementById('profile');
  const c = colorFor(p.gtm_action);
  const price = p.res_avg_buy_imputed
    ? '₹' + Math.round(+p.res_avg_buy_imputed).toLocaleString('en-IN') + '/sqft' + (truthy(p.price_is_imputed) ? ' ·est' : '')
    : '—';
  const row = (k, v, mono) => `<div class="pr"><span class="k">${k}</span><span class="v${mono ? ' mono' : ''}">${v}</span></div>`;
  const gem = (on, t, bg, fg) => on ? `<span class="pill" style="background:${bg};color:${fg}">${t}</span>` : '';
  const brands = (p.n_brands_confirmed || 0) + '/3' + (p.brands_confirmed_list ? ' · ' + p.brands_confirmed_list : '');

  const num = (v) => (v !== '' && v != null) ? +v : null;
  const blComp = num(p.blinkit_n_competitor_brands);
  const blAvg  = num(p.blinkit_competitor_avg_price);
  const blAdv  = num(p.price_advantage_blinkit);
  const ztComp = num(p.zepto_n_competitor_brands);
  const compSection = blComp !== null ? `
    <div class="p-sep"></div>
    <div class="p-section-head">Competitive position · Oats aisle</div>
    <div class="p-grid">
      ${row('GOAT on Blinkit', truthy(p.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>')}
      ${blAvg !== null ? row('Competitor avg price', '₹' + Math.round(blAvg), true) : ''}
      ${blAdv !== null ? row('GOAT price advantage', '<span style="color:var(--status-success)">+₹' + Math.round(blAdv) + ' cheaper</span>') : ''}
      ${truthy(p.is_white_space) ? '<div class="pr"><span class="pill" style="background:var(--status-success-bg);color:var(--status-success-text);font-size:11px">White space — no competitors on BL or Zepto</span></div>' : ''}
    </div>` : '';

  panel.innerHTML = `
    <div class="p-head">
      <div><div class="p-area">${p.AREA.split(',')[0].trim()}</div><div class="p-sub">${p.ADDRESS} · PIN ${p.PINCODE || '—'}</div></div>
      <button class="p-x" onclick="document.getElementById('profile').classList.remove('open')">×</button>
    </div>
    <div class="gtm-status" style="color:${c}">● ${labelFor(p.gtm_action)}</div>
    <div class="p-icp">
      <div><span class="k">ICP</span><div class="big">${Math.round(+p.icp_score)}</div></div>
      <div><span class="k">Serviceability</span><div class="v mono">${p.serviceability_state} · ${p.serviceability_confidence}</div></div>
    </div>
    <div class="p-grid">
      ${row('Verdict', p.icp_verdict)}
      ${row('Archetype', p.archetype_ml)}
      ${row('Lifecycle', p.lifecycle || '—')}
      ${row('Brands confirmed', brands)}
      ${row('Nearest store', p.nearest_known_darkstore_km ? p.nearest_known_darkstore_km + ' km' : '—', true)}
      ${row('Price', price, true)}
      ${row('Employer quality', p.employer_quality != null && p.employer_quality !== '' ? Math.round(+p.employer_quality) : '—', true)}
      ${row('Metro', truthy(p.is_metro_connected) ? 'Yes' : 'No')}
    </div>
    ${compSection}
    <div class="pills">
      ${gem(truthy(p.pareto_optimal), 'Pareto-optimal', '#E6F1FB', '#185FA5')}
      ${gem(truthy(p.hidden_gem_v2), 'Hidden gem', '#FAEEDA', '#854F0B')}
      ${gem(truthy(p.spillover_gem), 'Spillover gem', '#EAF3DE', '#3B6D11')}
    </div>`;
  panel.classList.add('open');
  if (map && p.lat) map.easeTo({ center: [+p.lng, +p.lat], zoom: 11, duration: 600 });
}
