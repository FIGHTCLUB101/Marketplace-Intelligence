import AppState from './state.js';

export function severityFor(changes) {
  if (changes.goat_displaced.length + changes.goat_gone.length > 0) return 'critical';
  if (changes.rank_intrusions.length > 0) return 'warning';
  return 'clear';
}

const SEVERITY_LABEL = { critical: 'GOAT LIFE SHELF DISRUPTED', warning: 'CHANGES DETECTED', clear: 'ALL CLEAR' };

export function formatTrendRows(trends) {
  return trends.series.map((s) => ({
    label: s.product_name,
    isGoat: s.is_goat,
    cells: trends.weeks.map((_, i) => (s.data[i] === null || s.data[i] === undefined ? '—' : s.data[i])),
  }));
}

export function formatBrandDefenceRate(value) {
  return value === null || value === undefined ? 'N/A' : `${value.toFixed(1)}%`;
}

export function normalizeBrandName(name) {
  return name.replace(/\s+Oats$/i, '').trim();
}

export function computeVisibilityRate(rows) {
  if (!rows.length) return null;
  return (100 * rows.filter((r) => r.is_goat).length) / rows.length;
}

const EVENT_META = {
  goat_displaced: { severity: 'critical', label: 'displaced' },
  goat_gone: { severity: 'critical', label: 'no longer listed' },
  rank_intrusions: { severity: 'warning', label: 'intruded' },
  price_changes: { severity: 'warning', label: 'price moved' },
  new_products: { severity: 'info', label: 'appeared' },
  gone_products: { severity: 'info', label: 'no longer listed' },
};

function entryFor(eventType, e) {
  switch (eventType) {
    case 'goat_displaced':
      return { city: e.city, locality: e.locality, product: e.was, detail: e.now };
    case 'goat_gone':
      return { city: e.city, locality: e.locality, product: e.product, detail: `last seen rank ${e.rank}` };
    case 'rank_intrusions':
      return { city: e.city, locality: e.locality, product: e.intruder, detail: `intruded at rank ${e.rank}` };
    case 'price_changes': {
      const dir = e.change < 0 ? '▼' : '▲';
      return {
        city: e.city, locality: e.locality, product: e.product,
        detail: `${dir}₹${Math.abs(e.change).toFixed(0)} (₹${e.old_price} → ₹${e.new_price})`,
      };
    }
    case 'new_products':
      return { city: e.city, locality: e.locality, product: e.product, detail: `appeared at rank ${e.rank}` };
    case 'gone_products':
      return { city: e.city, locality: e.locality, product: e.product, detail: 'no longer listed' };
    default:
      throw new Error(`unknown eventType: ${eventType}`);
  }
}

export function groupChangesByProduct(changes) {
  const eventLists = {
    goat_displaced: changes.goat_displaced,
    goat_gone: changes.goat_gone,
    rank_intrusions: changes.rank_intrusions,
    price_changes: changes.price_changes,
    new_products: changes.new_products,
    gone_products: changes.gone_products.filter((e) => !e.is_goat),
  };
  const groups = new Map();
  Object.entries(eventLists).forEach(([eventType, list]) => {
    list.forEach((e) => {
      const entry = entryFor(eventType, e);
      const key = `${eventType}::${entry.product}`;
      if (!groups.has(key)) {
        groups.set(key, {
          key, eventType, severity: EVENT_META[eventType].severity, label: EVENT_META[eventType].label,
          product: entry.product, entries: [],
        });
      }
      groups.get(key).entries.push({ city: entry.city, locality: entry.locality, detail: entry.detail });
    });
  });
  return [...groups.values()];
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function renderConquestBreadth(breadth) {
  if (!breadth.length) return '';
  const rows = breadth.map((b) =>
    `<div class="alert-row warning"><strong>${b.competitor}</strong> appears in ${b.locality_count} localit${b.locality_count === 1 ? 'y' : 'ies'}</div>`
  ).join('');
  return `<h3 class="gh">Conquest Breadth</h3>${rows}`;
}

function renderTrendsTable(trends) {
  if (!trends.series.length) return '<p class="info">Not enough history yet for a trend table.</p>';
  const rows = formatTrendRows(trends);
  const head = `<tr><th>Product</th>${trends.weeks.map((w) => `<th>${w}</th>`).join('')}</tr>`;
  const body = rows.map((r) =>
    `<tr><td>${r.isGoat ? `<strong>${r.label}</strong>` : r.label}</td>${r.cells.map((c) => `<td class="mono">${c}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="lb">${head}${body}</table>`;
}

function cityLocalityIndex(groups) {
  const byCity = new Map();
  groups.forEach((g) => g.entries.forEach((e) => {
    if (!byCity.has(e.city)) byCity.set(e.city, new Set());
    byCity.get(e.city).add(e.locality);
  }));
  return byCity;
}

function groupCard(g) {
  const collapsed = g.entries.length > 5;
  const entriesHtml = g.entries.map((e) =>
    `<div class="group-entry">${e.city} (${e.locality}) — ${e.detail}</div>`
  ).join('');
  return `
    <div class="alert-row ${g.severity} group-card" data-key="${g.key}">
      <div class="group-head">
        <strong>${g.product}</strong> ${g.label}
        <span class="group-count">in ${g.entries.length} localit${g.entries.length === 1 ? 'y' : 'ies'}</span>
        ${collapsed ? '<button type="button" class="group-toggle">Show</button>' : ''}
      </div>
      <div class="group-entries" ${collapsed ? 'style="display:none"' : ''}>${entriesHtml}</div>
    </div>`;
}

function renderGroupedChanges(groups, cityFilter, localityFilter) {
  const filtered = groups
    .map((g) => ({
      ...g,
      entries: g.entries.filter((e) =>
        (cityFilter === 'all' || e.city === cityFilter) &&
        (localityFilter === 'all' || e.locality === localityFilter)),
    }))
    .filter((g) => g.entries.length > 0);
  if (!filtered.length) return '<p class="info">No changes match this filter.</p>';
  return filtered.map(groupCard).join('');
}

function wireGroupToggles(container) {
  container.querySelectorAll('.group-toggle').forEach((btn) => btn.addEventListener('click', () => {
    const entries = btn.closest('.group-card').querySelector('.group-entries');
    const open = entries.style.display !== 'none';
    entries.style.display = open ? 'none' : 'block';
    btn.textContent = open ? 'Show' : 'Hide';
  }));
}

function fillLocalityOptions(select, byCity, city) {
  const localities = city === 'all'
    ? [...new Set([...byCity.values()].flatMap((s) => [...s]))]
    : [...(byCity.get(city) || [])];
  select.innerHTML = '<option value="all">All localities</option>' +
    localities.sort().map((l) => `<option>${l}</option>`).join('');
}

let activeSubtabId = null;

async function renderThisWeek(el) {
  const myId = 'this-week';
  el.innerHTML = '<p class="info">Loading…</p>';
  try {
    const [changes, trends] = await Promise.all([
      fetchJson('/api/shelf/changes?platform=blinkit_goatlife'),
      fetchJson('/api/shelf/trends?platform=blinkit_goatlife'),
    ]);
    if (activeSubtabId !== myId) return;
    if (changes.status === 'insufficient_history') {
      el.innerHTML = `<p class="info">${changes.narrative[0]}</p>`;
      return;
    }
    const sev = severityFor(changes);
    const groups = groupChangesByProduct(changes);
    const byCity = cityLocalityIndex(groups);
    el.innerHTML = `
      <p class="vd">Week-over-week changes to GOAT Life's Blinkit brand-search shelf, comparing run ${changes.old_run_id} → ${changes.new_run_id}.</p>
      <div class="severity-banner ${sev}">${SEVERITY_LABEL[sev]}</div>
      <div class="stat-label">Brand Defence Rate</div>
      <div class="stat-val">${formatBrandDefenceRate(changes.brand_defence_rate)}</div>
      <div class="narrative">${changes.narrative.join('<br>')}</div>
      <div class="filter-row">
        <div class="field"><label>City</label><select class="f-tw-city"><option value="all">All cities</option>${[...byCity.keys()].sort().map((c) => `<option>${c}</option>`).join('')}</select></div>
        <div class="field"><label>Locality</label><select class="f-tw-locality"></select></div>
      </div>
      <div class="group-list"></div>
      ${renderConquestBreadth(changes.conquest_breadth)}
      <h3 class="gh">Observed Digital Shelf Position</h3>
      <p class="info">We observe the output of Blinkit's ranking algorithm, not its inputs — this is rank as it actually appeared, tracked week over week.</p>
      ${renderTrendsTable(trends)}`;

    const citySel = el.querySelector('.f-tw-city');
    const localitySel = el.querySelector('.f-tw-locality');
    const groupList = el.querySelector('.group-list');
    const rerenderGroups = () => {
      groupList.innerHTML = renderGroupedChanges(groups, citySel.value, localitySel.value);
      wireGroupToggles(groupList);
    };
    fillLocalityOptions(localitySel, byCity, 'all');
    citySel.addEventListener('change', () => { fillLocalityOptions(localitySel, byCity, citySel.value); rerenderGroups(); });
    localitySel.addEventListener('change', rerenderGroups);
    rerenderGroups();
  } catch (e) {
    if (activeSubtabId !== myId) return;
    console.error('shelf-monitor This Week render failed', e);
    el.innerHTML = '<p class="info">Failed to load — check the API is running.</p>';
  }
}

const COMPETITOR_PLATFORMS = [
  { value: 'blinkit', label: 'Blinkit' },
  { value: 'swiggy', label: 'Instamart' },
  { value: 'zepto', label: 'Zepto' },
];
const COMPETITOR_BRANDS = [
  'Alpino', 'Cosmix', 'MuscleBlaze', 'Pintola', 'Quaker', 'Saffola', 'SuperYou',
  'The Whole Truth', 'True Elements', 'Yoga Bar',
];

const compareState = { snapshots: {}, visibilityRates: {} };

async function fetchPlatformSnapshot(platform) {
  if (!compareState.snapshots[platform]) {
    compareState.snapshots[platform] = await fetchJson(`/api/shelf/snapshot?platform=${platform}`);
    compareState.visibilityRates[platform] = computeVisibilityRate(compareState.snapshots[platform]);
  }
  return compareState.snapshots[platform];
}

function headlineStatRow() {
  const stats = COMPETITOR_PLATFORMS.map((p) => {
    const rate = compareState.visibilityRates[p.value];
    const text = rate === null || rate === undefined ? '…' : `${rate.toFixed(1)}%`;
    return `<div class="visibility-stat"><span class="stat-label">${p.label}</span><span class="stat-val">${text}</span></div>`;
  }).join('');
  return `<div class="visibility-row">${stats}</div>`;
}

function compareTableRows(rows, brand, city, locality) {
  const normalized = normalizeBrandName(brand);
  const brandRows = rows.filter((r) => normalizeBrandName(r.brand_searched || '') === normalized);
  const goatLocalities = new Set(
    rows.filter((r) => r.is_goat).map((r) => `${r.city_raw}|||${r.locality_raw}`)
  );
  const filtered = brandRows.filter((r) =>
    (city === 'all' || r.city_raw === city) && (locality === 'all' || r.locality_raw === locality));
  const hasRank = brandRows.some((r) => r.rank !== null && r.rank !== undefined);
  return { filtered, hasRank, goatLocalities };
}

function renderCompareTable(rows, brand, city, locality) {
  const { filtered, hasRank, goatLocalities } = compareTableRows(rows, brand, city, locality);
  if (!filtered.length) return '<p class="info">No data for this brand/filter combination.</p>';
  const head = `<tr><th>City</th><th>Locality</th>${hasRank ? '<th>Rank</th>' : ''}<th>Price</th><th>MRP</th><th>Discount %</th><th>GOAT also here?</th></tr>`;
  const body = filtered.map((r) => {
    const goatHere = goatLocalities.has(`${r.city_raw}|||${r.locality_raw}`) ? 'Yes' : 'No';
    return `<tr><td>${r.city_raw}</td><td>${r.locality_raw}</td>${hasRank ? `<td class="mono">${r.rank ?? '—'}</td>` : ''}<td class="mono">${r.selling_price ?? '—'}</td><td class="mono">${r.mrp ?? '—'}</td><td class="mono">${r.discount_pct ?? '—'}</td><td>${goatHere}</td></tr>`;
  }).join('');
  return `<table class="lb">${head}${body}</table>`;
}

function fillCompareCityLocality(citySel, localitySel, rows, onChange) {
  const byCity = new Map();
  rows.forEach((r) => {
    if (!byCity.has(r.city_raw)) byCity.set(r.city_raw, new Set());
    byCity.get(r.city_raw).add(r.locality_raw);
  });
  citySel.innerHTML = '<option value="all">All cities</option>' +
    [...byCity.keys()].sort().map((c) => `<option>${c}</option>`).join('');
  fillLocalityOptions(localitySel, byCity, 'all');
  citySel.onchange = () => { fillLocalityOptions(localitySel, byCity, citySel.value); onChange(); };
}

async function renderCompareBrands(el) {
  const myId = 'compare';
  el.innerHTML = `
    ${headlineStatRow()}
    <div class="filter-row">
      <div class="field"><label>Platform</label><select class="f-cmp-platform"><option value="">Select a platform</option>${COMPETITOR_PLATFORMS.map((p) => `<option value="${p.value}">${p.label}</option>`).join('')}</select></div>
      <div class="field"><label>Brand</label><select class="f-cmp-brand">${COMPETITOR_BRANDS.map((b) => `<option>${b}</option>`).join('')}</select></div>
      <div class="field"><label>City</label><select class="f-cmp-city"><option value="all">All cities</option></select></div>
      <div class="field"><label>Locality</label><select class="f-cmp-locality"><option value="all">All localities</option></select></div>
    </div>
    <div class="compare-table"><p class="info">Select a platform to see current shelf data.</p></div>`;

  const platformSel = el.querySelector('.f-cmp-platform');
  const brandSel = el.querySelector('.f-cmp-brand');
  const citySel = el.querySelector('.f-cmp-city');
  const localitySel = el.querySelector('.f-cmp-locality');
  const table = el.querySelector('.compare-table');

  const rerenderTable = () => {
    const rows = compareState.snapshots[platformSel.value] || [];
    table.innerHTML = renderCompareTable(rows, brandSel.value, citySel.value, localitySel.value);
  };

  platformSel.addEventListener('change', async () => {
    const platform = platformSel.value;
    if (!platform) {
      table.innerHTML = '<p class="info">Select a platform to see current shelf data.</p>';
      return;
    }
    table.innerHTML = '<p class="info">Loading…</p>';
    try {
      const rows = await fetchPlatformSnapshot(platform);
      if (activeSubtabId !== myId || platformSel.value !== platform) return;
      el.querySelector('.visibility-row').outerHTML = headlineStatRow();
      fillCompareCityLocality(citySel, localitySel, rows, rerenderTable);
    } catch (e) {
      if (activeSubtabId !== myId || platformSel.value !== platform) return;
      console.error('Compare Brands snapshot fetch failed', e);
      table.innerHTML = '<p class="info">Failed to load — check the API is running.</p>';
      return;
    }
    rerenderTable();
  });
  brandSel.addEventListener('change', rerenderTable);
  localitySel.addEventListener('change', rerenderTable);
}

const SUBTABS = [
  { id: 'this-week', label: 'This Week', render: renderThisWeek },
  { id: 'compare', label: 'Compare Brands', render: renderCompareBrands },
];

async function render() {
  const el = document.getElementById('shelf-monitor');
  el.innerHTML = `
    <h2 class="vt">Shelf Monitor</h2>
    <div class="subtabs">${SUBTABS.map((t, i) => `<button type="button" class="subtab${i === 0 ? ' active' : ''}" data-subtab="${t.id}">${t.label}</button>`).join('')}</div>
    <div class="subtab-body"></div>`;
  const body = el.querySelector('.subtab-body');
  const activate = (id) => {
    el.querySelectorAll('.subtab').forEach((b) => b.classList.toggle('active', b.dataset.subtab === id));
    activeSubtabId = id;
    SUBTABS.find((t) => t.id === id).render(body);
  };
  el.querySelectorAll('.subtab').forEach((b) => b.addEventListener('click', () => activate(b.dataset.subtab)));
  activate(SUBTABS[0].id);
}

AppState.initShelfMonitor = render;
