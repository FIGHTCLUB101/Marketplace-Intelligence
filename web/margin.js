import AppState from './state.js';

export function calcEconomics({mrp, grossMarginPercent, brandDiscountPercent=0,
  commissionRate=0.179, fulfilmentFee=50, logisticsRate=0.10, returnsRate=0.025,
  monthlyAdBudget=250000, monthlyOrders=3000}){
  const effSP = mrp * (1 - brandDiscountPercent/100);
  const cogs = mrp * (1 - grossMarginPercent/100);
  const logistics = mrp * logisticsRate;
  const returns = mrp * returnsRate;
  const adPerOrder = monthlyOrders > 0 ? monthlyAdBudget / monthlyOrders : 0;
  const netRealization = effSP * (1 - commissionRate) - fulfilmentFee;
  const netContribution = netRealization - cogs - logistics - returns - adPerOrder;
  return {
    netRealization: Math.round(netRealization*100)/100,
    netContribution: Math.round(netContribution*100)/100,
    netContributionPercent: Math.round(netContribution/mrp*1000)/10,
    isViable: netContribution > 0,
  };
}

// QCompass getViabilityVerdict thresholds (exact)
export function getVerdict({grossMarginPercent, netRealization, monthlyAdBudget}){
  if (grossMarginPercent < 50 || netRealization < 150 || monthlyAdBudget < 100000) return 'STOP';
  if (grossMarginPercent >= 65 && netRealization >= 250 && monthlyAdBudget >= 200000) return 'GO';
  return 'CAUTION';
}

const COLOR = { GO:'#059669', CAUTION:'#d97706', STOP:'#991B1B' };

function field(label,id,val){
  return `<div class="field"><label for="${id}">${label}</label>
    <input id="${id}" type="number" value="${val}"></div>`;
}
function num(id){ return parseFloat(document.getElementById(id).value) || 0; }

function update(){
  const mrp=num('m-mrp'), gm=num('m-gm');
  const r = calcEconomics({ mrp, grossMarginPercent:gm, brandDiscountPercent:num('m-disc'),
    commissionRate:num('m-comm')/100, fulfilmentFee:num('m-ful'),
    monthlyAdBudget:num('m-ad'), monthlyOrders:num('m-ord') });
  const v = getVerdict({ grossMarginPercent:gm, netRealization:r.netRealization, monthlyAdBudget:num('m-ad') });
  document.getElementById('m-out').innerHTML = `
    <div style="border:2px solid ${COLOR[v]};border-radius:var(--radius);padding:1rem;background:rgba(255,255,255,.02)">
      <span class="verdict-badge" style="background:${COLOR[v]};color:#fff">${v}</span>
      <div style="display:flex;gap:2rem;margin-top:.75rem;flex-wrap:wrap">
        <div><div class="stat-label">Net realization</div><div class="stat-val">₹${r.netRealization}</div></div>
        <div><div class="stat-label">Net contribution / order</div><div class="stat-val" style="color:${r.isViable?'var(--go)':'#f87171'}">₹${r.netContribution}</div></div>
        <div><div class="stat-label">Contribution %</div><div class="stat-val">${r.netContributionPercent}%</div></div>
      </div>
      <p class="info" style="margin-top:.75rem">Net realization = selling price × (1 − commission) − fulfilment. Contribution subtracts COGS, logistics (10%), returns (2.5%), ad/order. Thresholds: QCompass GO/CAUTION/STOP.</p>
    </div>`;
}

function render(){
  const el = document.getElementById('margin');
  el.innerHTML = `
    <h2 style="font-size:1.1rem;margin-bottom:.25rem">Margin Reality — GOAT Life on Blinkit</h2>
    <p class="info" style="margin-bottom:1rem">Pre-filled with GOAT Life's real Blinkit economics (₹119 MRP, ₹99 selling, 57% gross margin). Edit any field.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;max-width:760px">
      ${field('MRP (₹)','m-mrp',119)}
      ${field('Gross margin (%)','m-gm',57)}
      ${field('Brand discount (%)','m-disc',16)}
      ${field('Commission (%)','m-comm',17.9)}
      ${field('Fulfilment fee (₹)','m-ful',50)}
      ${field('Monthly ad budget (₹)','m-ad',250000)}
      ${field('Monthly orders','m-ord',3000)}
    </div>
    <div id="m-out" style="margin-top:1.25rem;max-width:760px"></div>`;
  el.querySelectorAll('input').forEach(i=>i.addEventListener('input', update));
  update();
}
AppState.initMargin = render;
