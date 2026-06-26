import { initMap, resizeMap, setMapFilter, highlightBelt } from './locality-map.js';
import { buildFilter } from './filters.js';
import { colorFor, labelFor, GTM_ACTIONS } from './contract.js';
import { renderLeaderboard, renderGems, renderMethodology } from './views.js';
import { renderSequence } from './sequence.js';
import AppState from './state.js';
import './margin.js';

const L = window.LOCALITIES || [];
const BELTS = window.BELTS || [];
const activeGtm = new Set();          // empty = all actions shown
const sel = { city: 'all', verdict: 'all', serviceability: 'all' };

const matches = (l) =>
  (sel.city === 'all' || l.ADDRESS === sel.city) &&
  (sel.verdict === 'all' || l.icp_verdict === sel.verdict) &&
  (sel.serviceability === 'all' || l.serviceability_state === sel.serviceability) &&
  (activeGtm.size === 0 || activeGtm.has(l.gtm_action));

function applyFilter() {
  setMapFilter(buildFilter({ ...sel, gtm: activeGtm.size ? activeGtm : null }));
  const vis = L.filter(matches);
  const push = vis.filter((l) => l.gtm_action === 'PUSH-NOW').length;
  const samp = vis.filter((l) => l.gtm_action.startsWith('SAMPLE')).length;
  document.getElementById('map-stats').innerHTML =
    `<b>${vis.length}</b> localities · <b>${push}</b> push-now · <b>${samp}</b> sample`;
}

function buildLedger() {
  const counts = {};
  L.forEach((l) => (counts[l.gtm_action] = (counts[l.gtm_action] || 0) + 1));
  const el = document.getElementById('ledger');
  el.innerHTML = GTM_ACTIONS.map((a) =>
    `<div class="lrow" data-gtm="${a}"><span class="dot" style="background:${colorFor(a)}"></span>${labelFor(a)}<span class="lc">${counts[a] || 0}</span></div>`
  ).join('');
  el.querySelectorAll('.lrow').forEach((row) => row.addEventListener('click', () => {
    const a = row.dataset.gtm;
    if (activeGtm.has(a)) activeGtm.delete(a); else activeGtm.add(a);
    el.querySelectorAll('.lrow').forEach((r) =>
      r.classList.toggle('off', activeGtm.size > 0 && !activeGtm.has(r.dataset.gtm)));
    applyFilter();
  }));
}

document.addEventListener('DOMContentLoaded', () => {
  // city filter options
  const fc = document.getElementById('f-city');
  [...new Set(L.map((l) => l.ADDRESS))].sort().forEach((c) => {
    const o = document.createElement('option'); o.value = o.textContent = c; fc.appendChild(o);
  });
  // belt options
  const bsel = document.getElementById('belt-select');
  BELTS.forEach((b) => {
    const o = document.createElement('option');
    o.value = b.belt_id;
    o.textContent = `${b.ADDRESS} · ${b.size} localities · ICP ${b.avg_icp}`;
    bsel.appendChild(o);
  });

  buildLedger();
  initMap();
  AppState.initMargin && AppState.initMargin();
  renderMethodology();

  document.getElementById('f-city').addEventListener('change', (e) => { sel.city = e.target.value; applyFilter(); });
  document.getElementById('f-verdict').addEventListener('change', (e) => { sel.verdict = e.target.value; applyFilter(); });
  document.getElementById('f-svc').addEventListener('change', (e) => { sel.serviceability = e.target.value; applyFilter(); });
  bsel.addEventListener('change', (e) => highlightBelt(e.target.value));

  const rendered = {};
  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => {
    const v = tab.dataset.view;
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.view').forEach((s) => s.classList.toggle('active', s.id === v + '-view'));
    if (v === 'map') resizeMap();
    if (v === 'leaderboard' && !rendered.lb) { renderLeaderboard(); rendered.lb = 1; }
    if (v === 'gems' && !rendered.gems) { renderGems(); rendered.gems = 1; }
    if (v === 'sequence' && !rendered.seq) { renderSequence(); rendered.seq = 1; }
  }));

  setTimeout(applyFilter, 300);
});
