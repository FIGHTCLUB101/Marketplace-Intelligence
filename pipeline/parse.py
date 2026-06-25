import re


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
