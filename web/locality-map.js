import { colorFor, labelFor } from './contract.js';

const L = window.LOCALITIES || [];
let map;

const truthy = (v) => v === true || v === 'true' || v === 'True';

function localityFeatures() {
  return {
    type: 'FeatureCollection',
    features: L.map((l, i) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [+l.lng, +l.lat] },
      properties: {
        _i: i, color: l.color, icp_score: +l.icp_score, ADDRESS: l.ADDRESS,
        icp_verdict: l.icp_verdict, serviceability_state: l.serviceability_state,
        gtm_action: l.gtm_action, belt_id: l.belt_id,
      },
    })),
  };
}

export function initMap() {
  map = new maplibregl.Map({
    container: 'map-container', style: 'https://tiles.openfreemap.org/styles/dark',
    center: [78.9629, 20.5937], zoom: 4.4, minZoom: 3, maxZoom: 16,
  });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');

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
        paint: { 'circle-radius': 2, 'circle-color': c, 'circle-opacity': 0.32 },
      }));
    } catch (e) { console.warn('darkstores load failed', e); }

    map.addSource('localities', { type: 'geojson', data: localityFeatures() });
    map.addLayer({
      id: 'locality-circles', type: 'circle', source: 'localities',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['get', 'icp_score'], 0, 4, 100, 11],
        'circle-color': ['get', 'color'],
        'circle-stroke-width': 1.2, 'circle-stroke-color': '#ffffff', 'circle-opacity': 0.9,
      },
    });
    map.on('click', 'locality-circles', (e) => showProfile(L[e.features[0].properties._i]));
    map.on('mouseenter', 'locality-circles', () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', 'locality-circles', () => (map.getCanvas().style.cursor = ''));
  });
}

export function resizeMap() { if (map) setTimeout(() => map.resize(), 80); }
export function setMapFilter(expr) { if (map && map.getLayer('locality-circles')) map.setFilter('locality-circles', expr); }

export function highlightBelt(beltId) {
  if (beltId === 'all') { setMapFilter(null); return; }
  const id = +beltId;
  setMapFilter(['==', ['get', 'belt_id'], id]);
  const m = L.filter((l) => +l.belt_id === id);
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
  panel.innerHTML = `
    <div class="p-head">
      <div><div class="p-area">${p.AREA}</div><div class="p-sub">${p.ADDRESS} · PIN ${p.PINCODE || '—'}</div></div>
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
    <div class="pills">
      ${gem(truthy(p.pareto_optimal), 'Pareto-optimal', '#E6F1FB', '#185FA5')}
      ${gem(truthy(p.hidden_gem_v2), 'Hidden gem', '#FAEEDA', '#854F0B')}
      ${gem(truthy(p.spillover_gem), 'Spillover gem', '#EAF3DE', '#3B6D11')}
    </div>`;
  panel.classList.add('open');
  if (map && p.lat) map.easeTo({ center: [+p.lng, +p.lat], zoom: 11, duration: 600 });
}
