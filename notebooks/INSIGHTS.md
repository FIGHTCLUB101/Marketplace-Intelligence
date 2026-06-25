# GOAT Life — Locality ML Insights
_Generated from 1001 localities across 10 cities (magicbricks ML pipeline, notebooks 01-07)._

## Top 15 ICP localities (demand-context attractiveness)
| AREA | ADDRESS | icp_score | icp_verdict | archetype_ml |
| --- | --- | --- | --- | --- |
| Koramangala, Bangalore | Bangalore | 89.8 | GO | Full-infra · Metro |
| Vile Parle West, Mumbai | Mumbai | 88.7 | GO | Premium · Metro |
| Shivaji Park, Mumbai | Mumbai | 87.5 | GO | Premium · Metro |
| Kurla West, Mumbai | Mumbai | 87.0 | GO | Premium · Metro |
| Bandra East, Mumbai | Mumbai | 86.4 | GO | Premium · Metro |
| Sushant Lok, Gurgaon | Gurugram | 85.8 | GO | Amenity-rich · Metro |
| Saket, New Delhi | New Delhi | 85.7 | GO | Amenity-rich · Metro |
| Chakala, Mumbai | Mumbai | 85.6 | GO | Premium · Metro |
| Versova Andheri West, Mumbai | Mumbai | 84.7 | GO | Premium · Metro |
| East Patel Nagar, New Delhi | New Delhi | 84.0 | GO | Employer-dense |
| Vikhroli West, Mumbai | Mumbai | 83.6 | GO | Premium · Metro |
| Lower Parel, Mumbai | Mumbai | 83.2 | GO | Premium · Metro |
| Banjara Hills, Hyderabad | Hyderabad | 83.1 | GO | Healthcare-rich · Full-infra |
| Andheri West, Mumbai | Mumbai | 82.5 | GO | Premium · Metro |
| Safdarjung Development Area, New Delhi | New Delhi | 81.9 | GO | Amenity-rich · Metro |

## Hidden gems (67) — attractive but under-priced / under-covered
| AREA | ADDRESS | icp_score | res_avg_buy_imputed | price_is_imputed |
| --- | --- | --- | --- | --- |
| Chakala, Mumbai | Mumbai | 85.6 | 35720.0 | True |
| East Patel Nagar, New Delhi | New Delhi | 84.0 | 26820.0 | True |
| New Rajendra Nagar, New Delhi | New Delhi | 79.5 | 25746.0 | True |
| JP Nagar, Bangalore | Bangalore | 78.8 | 9850.0 | False |
| Sector 38, Gurgaon | Gurugram | 77.9 | 21477.0 | True |
| Sector 39, Gurgaon | Gurugram | 77.8 | 20587.0 | True |
| Mogappair, Chennai | Chennai | 77.1 | 12088.0 | True |
| Ballygunge, Kolkata | Kolkata | 76.8 | 10600.0 | False |
| Block B Sushant Lok Phase 1, Gurgaon | Gurugram | 76.7 | 18688.0 | True |
| Old Rajinder Nagar, New Delhi | New Delhi | 75.0 | 19752.0 | True |
| Sushant Lok 2 Sector 57, Gurgaon | Gurugram | 74.7 | 28550.0 | True |
| Mahipalpur, New Delhi | New Delhi | 74.7 | 28494.0 | True |

## Data-driven archetypes (NB05)
| archetype | n |
| --- | --- |
| Premium | 197 |
| Metro | 100 |
| Well-connected | 99 |
| Average / Mixed | 97 |
| Full-infra · Metro | 95 |
| Amenity-rich · Metro | 92 |
| Healthcare-rich · Full-infra | 85 |
| Employer-dense · Metro | 84 |
| Premium · Metro | 84 |
| Employer-dense | 68 |

## Largest belts (NB04 — contiguous groups to attack together)
| belt_id | city | size |
| --- | --- | --- |
| 120 | Gurugram | 60 |
| 59 | Chandigarh | 59 |
| 88 | Chennai | 33 |
| 368 | Pune | 32 |
| 380 | Pune | 26 |
| 193 | Kolkata | 22 |
| 191 | Kolkata | 21 |
| 126 | Gurugram | 18 |

## Method & caveats
- ICP = 0.30 affluence + 0.30 corporate + 0.10 youth + 0.15 access + 0.15 centrality (percentile-ranked). Magicbricks-side only.
- Prices for ~45% of localities are **model-imputed** (LightGBM, CV R2 0.52, beats city-mean) and flagged `price_is_imputed` — treat as directional.
- Production GOAT-Fit additionally layers gym-fitness density + darkstore serviceability (not in these notebooks).
