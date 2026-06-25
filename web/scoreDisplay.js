export function verdictColor(verdict){
  return verdict === 'GO' ? '#059669' : verdict === 'SAMPLE-FIRST' ? '#d97706' : '#52525b';
}

function bar(label, val){
  const v = val == null ? 0 : val;
  const txt = val == null ? 'n/a' : Math.round(val);
  return `<div class="score-row"><div class="score-meta"><span>${label}</span><span>${txt}</span></div>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${v}%"></div></div></div>`;
}

function serviceabilityLine(loc){
  if (loc.qc_serviceable === undefined) return '';
  const brands = loc.nearest_by_brand || {};
  const detail = Object.entries(brands).sort((a,b)=>a[1]-b[1])
    .map(([b,km])=>`${b} ${km}km`).slice(0,3).join(' · ');
  if (loc.qc_serviceable){
    return `<div class="insp-section"><div class="insp-label">Serviceability</div>
      <span class="verdict-badge verdict-GO">QC-ready</span>
      <p class="info" style="margin-top:.3rem">Nearest darkstores: ${detail || 'within 3.5 km'}</p></div>`;
  }
  return `<div class="insp-section"><div class="insp-label">Serviceability</div>
    <span class="verdict-badge verdict-WAIT">D2C / offline-only</span>
    <p class="info" style="margin-top:.3rem">No darkstore within 3.5 km${loc.nearest_darkstore_km!=null?` (nearest ${loc.nearest_darkstore_km}km)`:''}.</p></div>`;
}

function activationLine(loc){
  if (!loc.activation || !loc.activation.length) return '';
  const chips = loc.activation.map(v=>`<span class="chip ${v.type}">${v.name}</span>`).join('');
  return `<div class="insp-section"><div class="insp-label">Activation Playbook</div>${chips}</div>`;
}

function adjacencyLine(loc){
  if (!loc.nearby_raw || loc.nearby_raw === 'N/A') return '';
  return `<div class="insp-section"><div class="insp-label">Adjacent localities (attack the belt)</div>
    <p class="info">${loc.nearby_raw}</p></div>`;
}

export function inspectorHTML(loc){
  const archetype = loc.archetype ? `<span class="chip" style="background:rgba(245,166,35,.15);color:var(--goat-gold)">${loc.archetype}</span>` : '';
  const health = loc.health_ecosystem ? `<span class="chip" style="background:rgba(5,150,105,.15);color:#34d399">Health ecosystem</span>` : '';
  const source = loc.url ? `<div class="insp-section"><a href="${loc.url}" target="_blank" rel="noopener" class="info">Source: Magicbricks ↗</a></div>` : '';
  return `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem">
      <h3 style="font-size:.95rem">${loc.area}</h3>
      <span class="verdict-badge verdict-${loc.verdict}">${loc.verdict}</span>
    </div>
    <p class="info">${loc.city}${loc.partial_data ? ' · partial data' : ''} ${archetype} ${health}</p>
    <div style="font-size:2rem;font-weight:700;color:var(--goat-gold);margin:.5rem 0">${loc.goat_fit}<span style="font-size:.8rem;color:var(--text3)">/100 GOAT-Fit</span></div>
    <div class="info" style="margin-bottom:.5rem">Recommended channel: <strong style="color:var(--text)">${loc.channel}</strong></div>
    ${bar('Affluence', loc.affluence)}
    ${bar('Fitness density', loc.fitness)}
    ${bar('Corporate density', loc.corporate)}
    ${bar('Youth density', loc.youth)}
    ${serviceabilityLine(loc)}
    ${activationLine(loc)}
    ${adjacencyLine(loc)}
    ${source}
  `;
}
