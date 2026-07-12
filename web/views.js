import { colorFor, labelFor } from './contract.js';

const L = window.LOCALITIES || [];

const VERDICT_BG = { GO: '#E6F4EE', 'SAMPLE-FIRST': '#FAF0DF', WAIT: '#F0EFEA' };
const VERDICT_FG = { GO: '#059669', 'SAMPLE-FIRST': '#B45309', WAIT: '#6B6B66' };
const verdictBadge = (v) =>
  `<span class="badge" style="background:${VERDICT_BG[v] || '#F0EFEA'};color:${VERDICT_FG[v] || '#6B6B66'}">${v}</span>`;
const gtmDot = (a) => `<span style="color:${colorFor(a)}">●</span> ${labelFor(a)}`;
const inr = (n) => (n ? '₹' + Math.round(+n).toLocaleString('en-IN') : '—');

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
        ? (truthy(l.blinkit_goat_present) ? '<span style="color:#059669">✓</span>' : '<span style="color:#888780">—</span>')
        : '<span style="color:#ccc">n/a</span>';
      return `<tr>
        <td class="mono">${i + 1}</td><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
        <td class="mono">${Math.round(+l.icp_score)}</td><td>${verdictBadge(l.icp_verdict)}</td>
        <td>${l.serviceability_state}</td><td>${l.archetype_ml}</td>
        <td>${gtmDot(l.gtm_action)}</td>
        <td class="mono">${goatBL}</td>
        <td class="mono">${a !== null ? '<span style="color:#059669">+₹' + Math.round(a) + '</span>' : '—'}</td></tr>`;
    }).join('')}
    </tbody></table>`;
}

export function renderGems() {
  const table = (title, rows, extraHead, extraCell) => `
    <h3 class="gh">${title} <span class="k">(${rows.length})</span></h3>
    <table class="lb"><thead><tr><th>Locality</th><th>City</th><th>ICP</th><th>Price</th>${extraHead}<th>Action</th></tr></thead><tbody>
    ${rows.slice(0, 25).map((l) => `<tr><td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td><td class="mono">${inr(l.res_avg_buy_imputed)}</td>
      ${extraCell(l)}<td>${gtmDot(l.gtm_action)}</td></tr>`).join('')}
    </tbody></table>`;
  const t = (v) => v === true || v === 'true' || v === 'True';
  const num = (v) => (v !== '' && v != null) ? +v : null;
  const pareto = L.filter((l) => t(l.pareto_optimal)).sort((a, b) => +b.icp_score - +a.icp_score);
  const hidden = L.filter((l) => t(l.hidden_gem_v2)).sort((a, b) => +b.icp_score - +a.icp_score);
  const spill  = L.filter((l) => t(l.spillover_gem)).sort((a, b) => +b.icp_score - +a.icp_score);
  const ws     = L.filter((l) => t(l.is_white_space)).sort((a, b) => +b.icp_score - +a.icp_score);

  const wsTable = ws.length ? `
    <h3 class="gh">White space — no oats competitors on Blinkit or Zepto <span class="k">(${ws.length})</span></h3>
    <p class="vd">These localities have strong demand signals but zero competitor presence in the oats aisle on either Blinkit or Zepto. First-mover advantage is real here.</p>
    <table class="lb"><thead><tr><th>Locality</th><th>City</th><th>ICP</th><th>Verdict</th><th>Action</th><th>GOAT on BL</th></tr></thead><tbody>
    ${ws.slice(0, 30).map((l) => `<tr>
      <td>${l.AREA.split(',')[0].trim()}</td><td>${l.ADDRESS}</td>
      <td class="mono">${Math.round(+l.icp_score)}</td>
      <td>${verdictBadge(l.icp_verdict)}</td>
      <td>${gtmDot(l.gtm_action)}</td>
      <td>${t(l.blinkit_goat_present) ? '<span style="color:#059669">Listed ✓</span>' : '<span style="color:#888780">Not yet</span>'}</td>
    </tr>`).join('')}
    </tbody></table>` : '';

  document.getElementById('gems').innerHTML =
    wsTable +
    table('Pareto-optimal — strong on every dimension', pareto, '<th>Serviceability</th>', (l) => `<td>${l.serviceability_state}</td>`) +
    table('Hidden gems — high ICP, under-priced/under-covered', hidden, '<th>Archetype</th>', (l) => `<td>${l.archetype_ml}</td>`) +
    table('Spillover gems — cheaper than graph neighbours', spill, '<th>Nearest store</th>', (l) => `<td class="mono">${l.nearest_known_darkstore_km ? l.nearest_known_darkstore_km + ' km' : '—'}</td>`);
}

export function renderMethodology() {
  document.getElementById('methodology').innerHTML = `
    <h2 class="vt">Methodology</h2>
    <p class="vd">Each locality carries an <b>ICP score</b> (demand attractiveness: affluence + corporate + youth + access + centrality) and a <b>serviceability state</b> (quick-commerce reach from the Blinkit / Zepto / Instamart darkstore sample). The two combine into a go-to-market <b>action</b>.</p>
    <h3 class="gh">Action matrix</h3>
    <table class="lb"><thead><tr><th></th><th>Confirmed / Likely</th><th>Unknown</th></tr></thead><tbody>
      <tr><td class="mono">GO</td><td><span style="color:#059669">● Push now</span></td><td><span style="color:#2a78d6">● D2C / offline (verify QC)</span></td></tr>
      <tr><td class="mono">SAMPLE-FIRST</td><td><span style="color:#d97706">● Sample + QC test</span></td><td><span style="color:#EF9F27">● Sample (D2C / offline)</span></td></tr>
      <tr><td class="mono">WAIT</td><td><span style="color:#888780">● Hold</span></td><td><span style="color:#888780">● Hold</span></td></tr>
    </tbody></table>
    <h3 class="gh">Honesty notes</h3>
    <p class="vd">
      <b>Absence ≠ unserviceable.</b> The darkstore set is a sample, so "Unknown" means we have no confirmed store nearby — never that delivery is impossible.<br>
      <b>Coverage confidence is a proxy</b> (no ground-truth darkstore totals).<br>
      <b>Centroid-precision confirmations are softer</b> than locality-precision ones.<br>
      <b>886 of 1,001 localities are mapped</b> — the 115 without coordinates are excluded from the map (not judged unserviceable).
    </p>`;
}
