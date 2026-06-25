import AppState from './state.js';
import { verdictColor } from './scoreDisplay.js';

function renderLeaderboard(data){
  const rows = [...data.localities].sort((a,b)=>b.goat_fit-a.goat_fit).slice(0,50);
  document.getElementById('leaderboard').innerHTML = `
    <table class="lb"><thead><tr>
      <th>#</th><th>Locality</th><th>City</th><th>GOAT-Fit</th><th>Verdict</th><th>Archetype</th><th>Channel</th><th>QC</th>
    </tr></thead><tbody>
    ${rows.map((l,i)=>`<tr class="${l.partial_data?'partial':''}">
      <td>${i+1}</td><td>${l.area}</td><td>${l.city}</td>
      <td style="color:var(--goat-gold);font-weight:600">${l.goat_fit}</td>
      <td><span class="verdict-badge verdict-${l.verdict}">${l.verdict}</span></td>
      <td>${l.archetype||'—'}</td><td>${l.channel}</td>
      <td>${l.qc_serviceable?'✓':'—'}</td></tr>`).join('')}
    </tbody></table>`;
}

function renderWhitespace(data){
  const pts = data.localities.filter(l => l.affluence != null);
  const ds = pts.map(l => ({ x:l.goat_fit, y:l.affluence, r:Math.max(4,(l.fitness||0)/8), loc:l }));
  new Chart(document.getElementById('whitespaceChart').getContext('2d'), {
    type:'bubble',
    data:{ datasets:[{ data:ds,
      backgroundColor: pts.map(l=>verdictColor(l.verdict)+'b3'),
      borderColor: pts.map(l=>verdictColor(l.verdict)) }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:(c)=>{
        const l=c.raw.loc; return [`${l.area} (${l.city})`,
          `GOAT-Fit ${l.goat_fit} · Affluence ${Math.round(l.affluence)}`,
          l.has_store?'Has Reliance store':'No modern retail',
          l.qc_serviceable?'QC-ready':'D2C/offline-only', l.channel]; } } } },
      scales:{
        x:{ title:{display:true,text:'GOAT-Fit Score',color:'#a1a1aa'}, grid:{color:'rgba(255,255,255,.05)'}, ticks:{color:'#a1a1aa'} },
        y:{ title:{display:true,text:'Affluence percentile',color:'#a1a1aa'}, grid:{color:'rgba(255,255,255,.05)'}, ticks:{color:'#a1a1aa'} } } }
  });
}

function renderGyms(data, markers){
  const fitByPin = {};
  data.localities.forEach(l=>{ if(l.pincode!=null){ const p=String(l.pincode).trim();
    fitByPin[p]=Math.max(fitByPin[p]||0, l.goat_fit); } });
  const ranked = markers.gyms
    .map(g=>({...g, fit: fitByPin[String(g.pincode).trim()] ?? null}))
    .filter(g=>g.fit!=null)
    .sort((a,b)=>b.fit-a.fit).slice(0,60);
  document.getElementById('gyms').innerHTML = `
    <p class="info" style="margin-bottom:.75rem">Top gyms ranked by the GOAT-Fit of their locality pincode — sampling/partnership priority.</p>
    <table class="lb"><thead><tr><th>#</th><th>Gym</th><th>City</th><th>Area GOAT-Fit</th></tr></thead><tbody>
    ${ranked.map((g,i)=>`<tr><td>${i+1}</td><td>${g.name}</td><td>${g.city}</td>
      <td style="color:var(--goat-gold);font-weight:600">${g.fit}</td></tr>`).join('')}
    </tbody></table>`;
}

AppState.renderLeaderboard = renderLeaderboard;
AppState.renderWhitespace = renderWhitespace;
AppState.renderGyms = renderGyms;
