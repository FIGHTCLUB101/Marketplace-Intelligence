import { colorFor, labelFor } from './contract.js';
import { wireSortableTable } from './sortable-table.js';

const L = window.LOCALITIES || [];

const VERDICT_STATUS = { GO: 'success', 'SAMPLE-FIRST': 'warning', WAIT: 'neutral' };
const verdictBadge = (v) => {
  const status = VERDICT_STATUS[v] || 'neutral';
  return `<span class="badge" style="background:var(--status-${status}-bg);color:var(--status-${status}-text)">${v}</span>`;
};
const gtmDot = (a) => `<span style="color:${colorFor(a)}">●</span> ${labelFor(a)}`;
const inr = (n) => (n ? '₹' + Math.round(+n).toLocaleString('en-IN') : '—');

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

  const restRanked = rest.map((l, i) => ({ ...l, _rank: i + 6 }));

  const goatRank = (l) => {
    if (l.blinkit_goat_present === '' || l.blinkit_goat_present == null) return 0;
    return truthy(l.blinkit_goat_present) ? 2 : 1;
  };

  const renderTableRow = (l) => {
    const a = num(l.price_advantage_blinkit);
    const goatBL = l.blinkit_goat_present !== '' && l.blinkit_goat_present != null
      ? (truthy(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">✓</span>' : '<span style="color:var(--status-neutral)">—</span>')
      : '<span style="color:#ccc">n/a</span>';
    return `<tr>
      <td class="mono">${l._rank}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
      <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td class="mono">${goatBL}</td>
      <td class="mono">${a !== null ? '<span style="color:var(--status-success)">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
  };

  const tableHtml = `
    <div class="table-wrap">
    <table class="lb" id="leaderboard-table"><thead><tr>
      <th>#</th><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th>Verdict</th><th>Serviceability</th>
      <th>Archetype</th><th>Action</th><th data-sort-key="goat">GOAT on BL</th><th data-sort-key="price">Price Adv.</th></tr></thead><tbody></tbody></table>
    </div>`;

  document.getElementById('leaderboard').innerHTML = insightsHtml + tableHtml;

  const columns = [
    { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
    { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
    { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
    { key: 'goat', sort: (a, b) => goatRank(a) - goatRank(b) },
    { key: 'price', sort: (a, b) => (num(a.price_advantage_blinkit) ?? -Infinity) - (num(b.price_advantage_blinkit) ?? -Infinity) },
  ];
  wireSortableTable(document.getElementById('leaderboard-table'), restRanked, columns, renderTableRow);
}

export function renderGems() {
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const t = (v) => v === true || v === 'true' || v === 'True';
  const goatRank = (l) => {
    if (l.blinkit_goat_present === '' || l.blinkit_goat_present == null) return 0;
    return t(l.blinkit_goat_present) ? 2 : 1;
  };
  const pareto = L.filter((l) => t(l.pareto_optimal)).sort((a, b) => +b.icp_score - +a.icp_score);
  const hidden = L.filter((l) => t(l.hidden_gem_v2)).sort((a, b) => +b.icp_score - +a.icp_score);
  const spill  = L.filter((l) => t(l.spillover_gem)).sort((a, b) => +b.icp_score - +a.icp_score);
  const ws     = L.filter((l) => t(l.is_white_space)).sort((a, b) => +b.icp_score - +a.icp_score);

  const tableConfigs = [];

  const table = (title, rows, extraHead, extraCell, extraCol) => {
    const id = `gems-table-${tableConfigs.length}`;
    const columns = [
      { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
      { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
      { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
      { key: 'price', sort: (a, b) => (num(a.res_avg_buy_imputed) ?? -Infinity) - (num(b.res_avg_buy_imputed) ?? -Infinity) },
    ];
    if (extraCol) columns.push(extraCol);
    const renderRow = (l) => `<tr><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td class="mono">${inr(l.res_avg_buy_imputed)}</td>
      ${extraCell(l)}<td>${gtmDot(l.gtm_action)}</td></tr>`;
    const extraHeadKeyed = extraCol ? extraHead.replace('<th>', `<th data-sort-key="${extraCol.key}">`) : extraHead;
    tableConfigs.push({ id, rows: rows.slice(0, 25), columns, renderRow });
    return `
      <h3 class="gh">${title} <span class="k">(${rows.length})</span></h3>
      <div class="table-wrap">
      <table class="lb" id="${id}"><thead><tr><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th data-sort-key="price">Price</th>${extraHeadKeyed}<th>Action</th></tr></thead><tbody></tbody></table>
      </div>`;
  };

  const wsColumns = [
    { key: 'locality', sort: (a, b) => a.AREA.localeCompare(b.AREA) },
    { key: 'city', sort: (a, b) => a.ADDRESS.localeCompare(b.ADDRESS) },
    { key: 'icp', sort: (a, b) => +a.icp_score - +b.icp_score },
    { key: 'goat', sort: (a, b) => goatRank(a) - goatRank(b) },
  ];
  const wsRenderRow = (l) => `<tr>
      <td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td>
      <td>${verdictBadge(l.icp_verdict)}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td>${t(l.blinkit_goat_present) ? '<span style="color:var(--status-success)">Listed ✓</span>' : '<span style="color:var(--status-neutral)">Not yet</span>'}</td>
    </tr>`;
  let wsTable = '';
  if (ws.length) {
    const id = 'gems-white-space';
    tableConfigs.push({ id, rows: ws.slice(0, 30), columns: wsColumns, renderRow: wsRenderRow });
    wsTable = `
      <h3 class="gh">White space — no oats competitors on Blinkit or Zepto <span class="k">(${ws.length})</span></h3>
      <p class="vd">These localities have strong demand signals but zero competitor presence in the oats aisle on either Blinkit or Zepto. First-mover advantage is real here.</p>
      <div class="table-wrap">
      <table class="lb" id="${id}"><thead><tr><th data-sort-key="locality">Locality</th><th data-sort-key="city">City</th><th data-sort-key="icp">ICP</th><th>Verdict</th><th>Action</th><th data-sort-key="goat">GOAT on BL</th></tr></thead><tbody></tbody></table>
      </div>`;
  }

  document.getElementById('gems').innerHTML =
    wsTable +
    table('Pareto-optimal — strong on every dimension', pareto, '<th>Serviceability</th>', (l) => `<td>${l.serviceability_state}</td>`, { key: 'serviceability', sort: (a, b) => a.serviceability_state.localeCompare(b.serviceability_state) }) +
    table('Hidden gems — high ICP, under-priced/under-covered', hidden, '<th>Archetype</th>', (l) => `<td>${l.archetype_ml}</td>`, { key: 'archetype', sort: (a, b) => a.archetype_ml.localeCompare(b.archetype_ml) }) +
    table('Spillover gems — cheaper than graph neighbours', spill, '<th>Nearest store</th>', (l) => `<td class="mono">${l.nearest_known_darkstore_km ? l.nearest_known_darkstore_km + ' km' : '—'}</td>`, { key: 'nearest', sort: (a, b) => (num(a.nearest_known_darkstore_km) ?? Infinity) - (num(b.nearest_known_darkstore_km) ?? Infinity) });

  tableConfigs.forEach(({ id, rows, columns, renderRow }) => {
    wireSortableTable(document.getElementById(id), rows, columns, renderRow);
  });
}

export function renderMethodology() {
  document.getElementById('methodology').innerHTML = `
    <h2 class="vt">Methodology</h2>
    <p class="vd">Each locality carries an <b>ICP score</b> (demand attractiveness: affluence + corporate + youth + access + centrality) and a <b>serviceability state</b> (quick-commerce reach from the Blinkit / Zepto / Instamart darkstore sample). The two combine into a go-to-market <b>action</b>.</p>
    <h3 class="gh">Action matrix</h3>
    <div class="table-wrap">
    <table class="lb"><thead><tr><th></th><th>Confirmed / Likely</th><th>Unknown</th></tr></thead><tbody>
      <tr><td class="mono">GO</td><td><span style="color:${colorFor('PUSH-NOW')}">● Push now</span></td><td><span style="color:${colorFor('D2C / OFFLINE - verify QC')}">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:${colorFor('SAMPLE + QC test')}">● Sample + QC test</span></td><td><span style="color:${colorFor('SAMPLE (D2C / offline)')}">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td><td><span style="color:${colorFor('HOLD')}">● Hold</span></td></tr>
    </tbody></table>
    </div>
    <h3 class="gh">Honesty notes</h3>
    <p class="vd">
      <b>Absence ≠ unserviceable.</b> The darkstore set is a sample, so "Unknown" means we have no confirmed store nearby — never that delivery is impossible.<br>
      <b>Coverage confidence is a proxy</b> (no ground-truth darkstore totals).<br>
      <b>Centroid-precision confirmations are softer</b> than locality-precision ones.<br>
      <b>886 of 1,001 localities are mapped</b> — the 115 without coordinates are excluded from the map (not judged unserviceable).
    </p>`;
}
