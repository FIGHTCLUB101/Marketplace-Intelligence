import re

from pipeline.parse import count_named_entities


def parse_physical_infra(text):
    """Derive metro connectivity + airport access minutes from the free-text infra blurb."""
    if not text:
        return {"metro_connected": False, "airport_min": None}
    t = str(text)
    metro = bool(re.search(r"metro", t, re.I))
    air = None
    m = re.search(r"airport.{0,60}?(\d{1,3})\s*[-–]\s*(\d{1,3})\s*minutes", t, re.I)
    if m:
        air = int(m.group(2))
    elif re.search(r"airport", t, re.I):
        mins = [int(x) for x in re.findall(r"(\d{1,3})\s*[-–]?\s*\d{0,3}\s*minutes", t)]
        air = max(mins) if mins else None
    return {"metro_connected": metro, "airport_min": air}


def _entities(text, n=6):
    if not text:
        return []
    parts = [p.strip() for p in str(text).split(",")]
    return [p for p in parts if p and p.upper() != "N/A"][:n]


def activation_venues(loc):
    """Concrete sampling/pop-up venues from transport/shopping/social/tourist columns."""
    out = []
    for name in _entities(loc.get("transport")):
        out.append({"type": "metro", "name": name})
    for name in _entities(loc.get("shopping")):
        out.append({"type": "mall", "name": name})
    for name in _entities(loc.get("social_infra"), 3):
        out.append({"type": "cafe", "name": name})
    for name in _entities(loc.get("tourist")):
        out.append({"type": "tourist", "name": name})
    return out[:8]


def classify_archetype(loc):
    c = loc.get("corporate") or 0
    a = loc.get("affluence") or 0
    y = loc.get("youth") or 0
    intro = (loc.get("intro") or "").lower()
    top = max(c, a, y)
    if top < 35:
        return "Emerging"
    if "commercial" in intro and c >= a:
        return "Corporate Belt"
    if c == top:
        return "Corporate Belt"
    if y == top and y >= 60:
        return "Student Hub"
    if a == top and "residential" in intro:
        return "Premium Residential"
    if a == top:
        return "Premium Residential"
    return "Commercial/Retail"


def health_ecosystem(loc):
    return count_named_entities(loc.get("hospital")) >= 1


def attach_enrichment(localities):
    for l in localities:
        pi = parse_physical_infra(l.get("physical_infra"))
        l["metro_connected"] = pi["metro_connected"]
        l["airport_min"] = pi["airport_min"]
        l["activation"] = activation_venues(l)
        l["archetype"] = classify_archetype(l)
        l["health_ecosystem"] = health_ecosystem(l)
        l["nearby_raw"] = l.get("nearby")
