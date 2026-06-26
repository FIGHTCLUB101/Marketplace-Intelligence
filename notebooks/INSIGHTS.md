# GOAT Life — Locality ML Insights
_Generated from 1001 localities across 10 cities (magicbricks ML pipeline, notebooks 01-07)._

## Top 15 ICP localities (demand-context attractiveness)
| AREA | ADDRESS | icp_score | icp_verdict | archetype_ml |
| --- | --- | --- | --- | --- |
| Sushant Lok, Gurgaon | Gurugram | 88.5 | GO | Amenity-rich · Metro |
| Saket, New Delhi | New Delhi | 88.0 | GO | Amenity-rich · Metro |
| Sector 43, Gurgaon | Gurugram | 87.0 | GO | Well-connected |
| Phase 2 DLF, Gurgaon | Gurugram | 84.9 | GO | Amenity-rich · Metro |
| Powai, Mumbai | Mumbai | 84.1 | GO | Full-infra · Metro |
| Banjara Hills, Hyderabad | Hyderabad | 84.0 | GO | Healthcare-rich · Full-infra |
| Sector 47, Gurgaon | Gurugram | 83.8 | GO | Well-connected |
| Andheri West, Mumbai | Mumbai | 83.6 | GO | Premium · Metro |
| Baner, Pune | Pune | 83.0 | GO | Premium · Metro |
| Vile Parle West, Mumbai | Mumbai | 82.7 | GO | Premium · Metro |
| Sector 53, Gurgaon | Gurugram | 82.5 | GO | Well-connected |
| Alipore, Kolkata | Kolkata | 82.3 | GO | Employer-dense · Metro |
| Koramangala, Bangalore | Bangalore | 82.0 | GO | Full-infra · Metro |
| Lajpat Nagar 3, New Delhi | New Delhi | 81.5 | GO | Amenity-rich · Metro |
| Mogappair, Chennai | Chennai | 81.2 | GO | Metro |

## Hidden gems (70) — attractive but under-priced / under-covered
| AREA | ADDRESS | icp_score | res_avg_buy_imputed | price_is_imputed |
| --- | --- | --- | --- | --- |
| Mogappair, Chennai | Chennai | 81.2 | 15774.0 | True |
| Block B Sushant Lok Phase 1, Gurgaon | Gurugram | 79.9 | 20761.0 | True |
| Ballygunge, Kolkata | Kolkata | 76.7 | 10600.0 | False |
| JP Nagar, Bangalore | Bangalore | 76.1 | 9850.0 | False |
| Chakala, Mumbai | Mumbai | 75.1 | 24140.0 | True |
| Part 2 Sector 15, Gurgaon | Gurugram | 74.9 | 33802.0 | True |
| Miyapur, Hyderabad | Hyderabad | 74.2 | 7600.0 | False |
| Sector 11, Chandigarh | Chandigarh | 73.6 | 22281.0 | True |
| Sector 4, Gurgaon | Gurugram | 73.1 | 20040.0 | True |
| New Rajendra Nagar, New Delhi | New Delhi | 73.1 | 20732.0 | True |
| Sector 15, Chandigarh | Chandigarh | 72.3 | 19372.0 | True |
| Ramapuram, Chennai | Chennai | 72.3 | 10550.0 | False |

## Spillover gems (38) - cheaper than graph neighbours (spatial arbitrage)
| AREA | ADDRESS | price_gap_pct | res_avg_buy | neighbor_avg_price |
| --- | --- | --- | --- | --- |
| Banaswadi, Bangalore | Bangalore | 0.42 | 9650.0 | 16500.0 |
| Ramapuram, Chennai | Chennai | 0.38 | 10550.0 | 17000.0 |
| Kalkaji, New Delhi | New Delhi | 0.36 | 16150.0 | 25400.0 |
| Tollygunge, Kolkata | Kolkata | 0.36 | 6450.0 | 10050.0 |
| Garia, Kolkata | Kolkata | 0.36 | 4650.0 | 7233.0 |
| Ardee City, Gurgaon | Gurugram | 0.33 | 10650.0 | 15990.0 |
| Phase 1 DLF, Gurgaon | Gurugram | 0.33 | 17050.0 | 25575.0 |
| Sector 56, Gurgaon | Gurugram | 0.33 | 12450.0 | 18600.0 |
| Sector 55, Gurgaon | Gurugram | 0.32 | 12650.0 | 18600.0 |
| Mehrauli Gurgaon Road, Gurgaon | Gurugram | 0.32 | 17500.0 | 25575.0 |

## Top affluence drivers (SHAP, from NB06)
| Feature | Mean abs(SHAP) |
| --- | --- |
| neighbor_avg_price | 4463.3 |
| city_target_enc | 2241.2 |
| primary_sector_score | 400.7 |
| emb_pc5 | 333.9 |
| dist_to_city_centroid_km | 316.8 |
| amenity_diversity | 312.2 |
| sector_retail_and_commercial | 311.7 |
| emb_pc16 | 271.9 |
| emb_pc6 | 266.3 |
| emb_pc17 | 264.2 |

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
