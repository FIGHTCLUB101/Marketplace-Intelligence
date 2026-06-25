import re

import openpyxl


def parse_price_to_midpoint(price_str):
    """Return midpoint of the Residential Buy ₹/sqft range, or None."""
    if not price_str:
        return None
    m = re.search(r"Residential:\s*Buy\s*Rs\.?\s*([\d,]+)\s*-\s*Rs\.?\s*([\d,]+)", str(price_str))
    if not m:
        return None
    low = float(m.group(1).replace(",", ""))
    high = float(m.group(2).replace(",", ""))
    return (low + high) / 2


def count_named_entities(text):
    """Count comma-separated named entities, ignoring blanks and 'N/A'."""
    if not text:
        return 0
    parts = [p.strip() for p in str(text).split(",")]
    return len([p for p in parts if p and p.upper() != "N/A"])


def _rows(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    data = list(ws.iter_rows(values_only=True))
    wb.close()
    return data[1:]  # drop header


def load_localities(path):
    """Magicbricks columns:
    0 AREA, 1 ADDRESS(city), 2 PINCODE, 3 price, 4 physical infra, 5 intro,
    6 social infra, 7 employment, 8 education, 9 transport, 10 shopping,
    11 hospital, 12 nearby, 13 tourist, 14 commercial hub, 15 url
    """
    out = []
    for r in _rows(path):
        out.append({
            "area": r[0], "city": r[1], "pincode": r[2],
            "price_mid": parse_price_to_midpoint(r[3]),
            "employment_count": count_named_entities(r[7]),
            "education_count": count_named_entities(r[8]),
            "employment_raw": r[7], "education_raw": r[8], "commercial_raw": r[14],
            "physical_infra": r[4], "intro": r[5], "social_infra": r[6],
            "transport": r[9], "shopping": r[10], "hospital": r[11],
            "nearby": r[12], "tourist": r[13], "url": r[15],
        })
    return out


def load_gyms(path):
    return [{"city": r[0], "name": r[1], "addr": str(r[2] or "")} for r in _rows(path)]


def load_stores(path):
    return [{"city": r[0], "name": r[1], "addr": r[2], "pincode": r[3]} for r in _rows(path)]
