"""SQL query functions for the API layer. Each fetch_* function takes an
open psycopg2 connection and returns plain dicts (via RealDictCursor)."""
from psycopg2.extras import RealDictCursor

LOCALITIES_SQL = """
    SELECT
        l.locality_id, l.loc_key, l.area, l.city, l.pincode, l.lat, l.lng,
        l.belt_id, l.belt_size,
        cs.as_of, cs.icp_score, cs.icp_verdict, cs.gtm_action,
        cs.serviceability_state, cs.serviceability_confidence, cs.archetype_ml,
        cs.lifecycle, cs.n_brands_confirmed, cs.brands_confirmed_list,
        cs.nearest_known_darkstore_km, cs.blinkit_confirmed, cs.swiggy_confirmed,
        cs.zepto_confirmed, cs.res_avg_buy_imputed, cs.price_is_imputed,
        cs.employer_quality, cs.primary_sector, cs.is_metro_connected,
        cs.pareto_optimal, cs.hidden_gem_v2, cs.spillover_gem
    FROM localities l
    JOIN current_locality_scores cs ON cs.locality_id = l.locality_id
    ORDER BY l.locality_id
"""


def fetch_localities(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(LOCALITIES_SQL)
        return cur.fetchall()


def compute_belts(locality_rows):
    """Group locality rows (as returned by fetch_localities) into belts of
    size >= 3, matching scripts/build_locality_data.py's pandas groupby."""
    groups = {}
    for r in locality_rows:
        if not r["belt_id"] or not r["belt_size"] or r["belt_size"] < 3:
            continue
        key = (r["belt_id"], r["city"])
        groups.setdefault(key, []).append(r)

    belts = []
    for (belt_id, city), members in groups.items():
        icp_scores = [m["icp_score"] for m in members if m["icp_score"] is not None]
        belts.append({
            "belt_id": belt_id,
            "city": city,
            "size": members[0]["belt_size"],
            "avg_icp": round(sum(icp_scores) / len(icp_scores), 1) if icp_scores else None,
            "go_count": sum(1 for m in members if m["icp_verdict"] == "GO"),
            "confirmed_count": sum(1 for m in members if m["serviceability_state"] == "Confirmed"),
            "members": [m["area"] for m in members[:12]],
        })
    belts.sort(key=lambda b: b["size"], reverse=True)
    return belts
