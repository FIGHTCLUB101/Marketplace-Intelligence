import AppState from './state.js';

function renderMethodology(data){
  const w = data.meta.weights, g = data.meta.geocode_coverage, ds = data.meta.darkstores;
  document.getElementById('methodology').innerHTML = `
    <h2 style="font-size:1.1rem;margin-bottom:.75rem">Methodology & Data Transparency</h2>
    <p class="info">GOAT-Fit Score (0–100) per locality — weighted composite of percentile-ranked sub-scores:</p>
    <ul style="margin:.5rem 0 1rem 1.2rem;font-size:.85rem;color:var(--text2)">
      <li>Affluence (residential ₹/sqft) — weight ${w.affluence}</li>
      <li>Fitness density (gyms in pincode) — weight ${w.fitness}</li>
      <li>Corporate density (employment hubs + commercial hub) — weight ${w.corporate}</li>
      <li>Youth density (educational institutes) — weight ${w.youth}</li>
    </ul>
    <p class="info">Missing sub-scores (e.g. localities without price data) are excluded and their weight redistributed; such localities are flagged <span class="partial">partial data</span>. No values are imputed.</p>
    <p class="info" style="margin-top:.75rem">Verdict bands: GO ≥ 70 · SAMPLE-FIRST 45–69 · WAIT &lt; 45. Serviceability tag = a Blinkit/Zepto/Instamart darkstore within 3.5 km (haversine).</p>
    <p class="info" style="margin-top:.75rem">Every other Magicbricks column has a job: Physical infrastructure → connectivity; Transport/Shopping/Social/Tourist → Activation Playbook; Locality intro → archetype + blurb; Hospital → health-ecosystem flag; Nearby Localities → adjacency; URL → source link.</p>
    <p class="info" style="margin-top:.75rem"><strong style="color:var(--text)">Geocoding (offline, pincode-centroid via pgeocode):</strong>
      localities ${g.magicbricks_hit}/${g.magicbricks_total}, gyms ${g.gyms_hit}/${g.gyms_total}, stores ${g.stores_hit}/${g.stores_total}.
      Darkstores: Blinkit ${ds.Blinkit}, Zepto ${ds.Zepto}, Instamart ${ds['Swiggy Instamart']}.
      Pincode-centroid means localities sharing a pincode share a point — directional, not survey-grade.</p>
    <p class="info" style="margin-top:.75rem">Sources: Magicbricks (localities), JustDial (gyms), Reliance Smart Bazaar store locator, darkstore v1 scrape (darkstores). Margin engine ports QCompass (Morgan Stanley Q3 FY26 Blinkit 17.9% commission). Generated ${data.meta.generated}.</p>`;
}
AppState.renderMethodology = renderMethodology;
