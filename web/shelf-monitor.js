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

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function alertRow(cls, html) {
  return `<div class="alert-row ${cls}">${html}</div>`;
}

function renderChangeRows(changes) {
  const rows = [];
  changes.goat_displaced.forEach((e) => rows.push(alertRow('critical',
    `<strong>${e.was}</strong> displaced in ${e.city} (${e.locality}) — ${e.now}`)));
  changes.goat_gone.forEach((e) => rows.push(alertRow('critical',
    `<strong>${e.product}</strong> no longer listed in ${e.city} (${e.locality}) — last seen rank ${e.rank}`)));
  changes.rank_intrusions.forEach((e) => rows.push(alertRow('warning',
    `<strong>${e.intruder}</strong> intruded at rank ${e.rank} in ${e.city} (${e.locality})`)));
  changes.price_changes.forEach((e) => {
    const dir = e.change < 0 ? '▼' : '▲';
    rows.push(alertRow('warning',
      `<strong>${e.product}</strong> ${dir}₹${Math.abs(e.change).toFixed(0)} in ${e.city} (₹${e.old_price} → ₹${e.new_price})`));
  });
  changes.new_products.forEach((e) => rows.push(alertRow('info',
    `<strong>${e.product}</strong> appeared at rank ${e.rank} in ${e.city} (${e.locality})`)));
  changes.gone_products.filter((e) => !e.is_goat).forEach((e) => rows.push(alertRow('info',
    `<strong>${e.product}</strong> no longer listed in ${e.city} (${e.locality})`)));
  return rows.length ? rows.join('') : '<p class="info">No changes detected this week.</p>';
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
    `<tr><td>${r.label}</td>${r.cells.map((c) => `<td class="mono">${c}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="lb">${head}${body}</table>`;
}

async function render() {
  const el = document.getElementById('shelf-monitor');
  el.innerHTML = '<p class="info">Loading…</p>';
  try {
    const [changes, trends] = await Promise.all([
      fetchJson('/api/shelf/changes'),
      fetchJson('/api/shelf/trends'),
    ]);
    if (changes.status === 'insufficient_history') {
      el.innerHTML = `<h2 class="vt">Shelf Monitor</h2><p class="info">${changes.narrative[0]}</p>`;
      return;
    }
    const sev = severityFor(changes);
    el.innerHTML = `
      <h2 class="vt">Shelf Monitor</h2>
      <p class="vd">Week-over-week changes to GOAT Life's Blinkit brand-search shelf, comparing run ${changes.old_run_id} → ${changes.new_run_id}.</p>
      <div class="severity-banner ${sev}">${SEVERITY_LABEL[sev]}</div>
      <div class="stat-label">Brand Defence Rate</div>
      <div class="stat-val">${formatBrandDefenceRate(changes.brand_defence_rate)}</div>
      <div class="narrative">${changes.narrative.join('<br>')}</div>
      ${renderChangeRows(changes)}
      ${renderConquestBreadth(changes.conquest_breadth)}
      <h3 class="gh">Observed Digital Shelf Position</h3>
      <p class="info">We observe the output of Blinkit's ranking algorithm, not its inputs — this is rank as it actually appeared, tracked week over week.</p>
      ${renderTrendsTable(trends)}`;
  } catch (e) {
    console.error('shelf-monitor render failed', e);
    el.innerHTML = '<h2 class="vt">Shelf Monitor</h2><p class="info">Failed to load — check the API is running.</p>';
  }
}

AppState.initShelfMonitor = render;
