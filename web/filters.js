// MapLibre filter-expression builder for the locality layer.
export function buildFilter({ city, verdict, serviceability, gtm }) {
  const e = ['all'];
  if (city && city !== 'all') e.push(['==', ['get', 'ADDRESS'], city]);
  if (verdict && verdict !== 'all') e.push(['==', ['get', 'icp_verdict'], verdict]);
  if (serviceability && serviceability !== 'all') e.push(['==', ['get', 'serviceability_state'], serviceability]);
  if (gtm && gtm.size) e.push(['in', ['get', 'gtm_action'], ['literal', [...gtm]]]);
  return e.length > 1 ? e : null;
}
