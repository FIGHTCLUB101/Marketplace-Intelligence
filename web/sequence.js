// Attack-sequence engine — city + platform + budget -> wave-by-wave activation plan.
import { costFor, labelFor, colorFor } from './contract.js';

const L = (typeof window !== 'undefined' && window.LOCALITIES) || [];
const truthy = (v) => v === true || v === 'true' || v === 'True';
const avg = (a) => (a.length ? Math.round(a.reduce((s, l) => s + +l.icp_score, 0) / a.length) : 0);

export const WAVE_LABELS = {
  1: 'Wave 1 · Confirmed GO, established — highest conviction',
  2: 'Wave 2 · Confirmed GO, emerging — capture early',
  3: 'Wave 3 · Likely GO — expand, lower confidence',
  4: 'Wave 4 · Confirmed SAMPLE-FIRST, established — test adjacent demand',
};

// First matching wave wins (1-4 are activation; 5 = watch list).
export function assignWave(l) {
  const v = l.icp_verdict, s = l.serviceability_state, lc = l.lifecycle;
  if (v === 'GO' && s === 'Confirmed' && lc === 'established') return 1;
  if (v === 'GO' && s === 'Confirmed' && (lc === 'emerging' || lc === 'nascent')) return 2;
  if (v === 'GO' && s === 'Likely') return 3;
  if (v === 'SAMPLE-FIRST' && s === 'Confirmed' && lc === 'established') return 4;
  if (truthy(l.hidden_gem_v2) || truthy(l.spillover_gem)) return 5;
  return 0;
}

export function buildSequence(localities, { city, platform, budget }) {
  let pool = localities.filter((l) => l.ADDRESS === city);
  if (platform && platform !== 'all') pool = pool.filter((l) => truthy(l[platform + '_confirmed']));
  const waves = {};
  let remaining = budget;
  for (const w of [1, 2, 3, 4]) {
    const cand = pool.filter((l) => assignWave(l) === w).sort((a, b) => +b.icp_score - +a.icp_score);
    if (!cand.length) continue;
    const affordable = []; let cost = 0;
    for (const l of cand) {
      const c = costFor(l.archetype_ml);
      if (cost + c <= remaining) { affordable.push({ ...l, _cost: c }); cost += c; }
    }
    waves[w] = { candidates: cand, affordable, cost, avg: avg(cand) };
    remaining -= cost;
  }
  const watch = pool.filter((l) => assignWave(l) === 5).sort((a, b) => +b.icp_score - +a.icp_score);
  return { city, platform, budget, spent: budget - remaining, waves, watch };
}

// --- UI ---
export function renderSequence() {
  const cities = [...new Set(L.map((l) => l.ADDRESS))].sort();
  const el = document.getElementById('sequence');
  el.innerHTML = `
    <h2 class="vt">Attack sequence</h2>
    <p class="vd">Pick a city, platform and monthly budget. The engine sequences localities into activation
      waves by demand × serviceability × lifecycle, and fits them to budget (costs grounded in GOAT Life's disclosed spend).</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px">
      <select id="sq-city">${cities.map((c) => `<option>${c}</option>`).join('')}</select>
      <select id="sq-platform"><option value="all">All platforms</option><option value="blinkit">Blinkit</option><option value="swiggy">Swiggy</option><option value="zepto">Zepto</option></select>
      <input id="sq-budget" type="number" value="500000" style="width:170px;padding:6px 8px;font-family:var(--mono);border:1px solid var(--line);border-radius:6px">
      <button id="sq-go" class="tab active" style="background:var(--goat);color:#fff">Generate</button>
    </div>
    <div id="seq-out"></div>`;
  const go = () => {
    const plan = buildSequence(L, {
      city: el.querySelector('#sq-city').value,
      platform: el.querySelector('#sq-platform').value,
      budget: parseInt(el.querySelector('#sq-budget').value, 10) || 0,
    });
    el.querySelector('#seq-out').innerHTML = renderPlan(plan);
  };
  el.querySelector('#sq-go').addEventListener('click', go);
  go();
}

function renderPlan(plan) {
  const inr = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  let html = `<p class="vd" style="margin-top:14px"><b>${plan.city}</b> · ${plan.platform} · budget ${inr(plan.budget)} · allocated <b>${inr(plan.spent)}</b></p>`;
  for (const w of [1, 2, 3, 4]) {
    const wd = plan.waves[w];
    if (!wd) continue;
    html += `<h3 class="gh">${WAVE_LABELS[w]}</h3>
      <p class="k" style="margin-bottom:6px">${wd.affordable.length} funded of ${wd.candidates.length} · ${inr(wd.cost)} · avg ICP ${wd.avg}</p>
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Archetype</th><th>Brands</th><th>Cost</th></tr></thead><tbody>
      ${wd.affordable.map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td>${l.archetype_ml}</td><td class="mono">${l.n_brands_confirmed}/3</td><td class="mono">${inr(l._cost)}</td></tr>`).join('')}
      </tbody></table>`;
  }
  if (plan.watch.length) {
    html += `<h3 class="gh">Watch list · hidden & spillover gems <span class="k">(${plan.watch.length})</span></h3>
      <table class="lb"><thead><tr><th>Locality</th><th>ICP</th><th>Action</th></tr></thead><tbody>
      ${plan.watch.slice(0, 10).map((l) => `<tr><td>${l.AREA}</td><td class="mono">${Math.round(+l.icp_score)}</td><td><span style="color:${colorFor(l.gtm_action)}">●</span> ${labelFor(l.gtm_action)}</td></tr>`).join('')}
      </tbody></table>`;
  }
  return html;
}
