"""Pack-size-aware price normalization for the competitor overlay
(enrich_competitor_data.py). Comparing raw selling prices across products of
very different pack sizes (a 25g sachet vs. a 1kg bag) isn't a fair
comparison — everything here converts to Rs./100g first, the standard
unit-price basis, so a competitor average and GOAT's own price are actually
comparable regardless of what pack sizes either happens to sell.

Split into its own importable module (rather than living directly in
enrich_competitor_data.py) because that script has no __main__ guard and
runs its full pipeline at import time — see test_build_locality_data.py's
subprocess-based pattern for the same reason. Pure functions live here so
they can be unit-tested directly.
"""
import re

import pandas as pd

_UNIT_RE = r"(kgs?|kilograms?|gms?|grams?|g)"
_WEIGHT_RE = re.compile(rf"(\d+\.?\d*)\s*{_UNIT_RE}", re.IGNORECASE)
_UNIT_TO_GRAMS = {
    "kg": 1000, "kgs": 1000, "kilogram": 1000, "kilograms": 1000,
    "g": 1, "gm": 1, "gms": 1, "gram": 1, "grams": 1,
}


def _unit_grams(value, unit):
    return value * _UNIT_TO_GRAMS[unit.lower()]


def parse_pack_size_grams(s):
    """Parses a pack-size string into total grams. Handles the formats seen
    across Blinkit/Swiggy/Zepto exports:
      - plain: "400 g", "225g", "1 kg", "2.5 kg"
      - parenthesized: "1 pack (400 g)", "1 pc (1 kg)"
      - multiplication: "500 g X 3", "38 g X 4", "2 x 35 g" (inside parens)
      - combo/addition: "1 kg + 300 g", "400+60 g" (trailing number borrows
        the unit of a later term when it has none of its own)
    Returns None if the string doesn't contain a recognizable weight —
    excluded from any average rather than silently guessed wrong.
    """
    if pd.isna(s):
        return None
    text = str(s).strip()
    if not text:
        return None

    paren = re.search(r"\(([^)]+)\)", text)
    inner = paren.group(1) if paren else text

    # "<count> x <num> <unit>", e.g. "2 x 35 g"
    m = re.search(rf"(\d+\.?\d*)\s*[xX]\s*(\d+\.?\d*)\s*{_UNIT_RE}", inner, re.IGNORECASE)
    if m:
        count, value, unit = float(m.group(1)), float(m.group(2)), m.group(3)
        return count * _unit_grams(value, unit)

    # "<num> <unit> X <count>", e.g. "500 g X 3"
    m = re.search(rf"(\d+\.?\d*)\s*{_UNIT_RE}\s*[xX]\s*(\d+\.?\d*)", inner, re.IGNORECASE)
    if m:
        value, unit, count = float(m.group(1)), m.group(2), float(m.group(3))
        return _unit_grams(value, unit) * count

    # combo/addition, e.g. "1 kg + 300 g" or "400+60 g"
    if "+" in inner:
        parts = [p.strip() for p in inner.split("+")]
        shared_unit = next(
            (u.group(1) for u in (re.search(_UNIT_RE, p, re.IGNORECASE) for p in parts) if u),
            None,
        )
        total, found_any = 0.0, False
        for p in parts:
            num_m = re.search(r"(\d+\.?\d*)", p)
            if not num_m:
                continue
            unit_m = re.search(_UNIT_RE, p, re.IGNORECASE)
            unit = unit_m.group(1) if unit_m else shared_unit
            if unit is None:
                continue
            total += _unit_grams(float(num_m.group(1)), unit)
            found_any = True
        if found_any:
            return total

    # plain "<num> <unit>", e.g. "400 g", "225g", "1 kg"
    m = _WEIGHT_RE.search(inner)
    if m:
        return _unit_grams(float(m.group(1)), m.group(2))

    return None


def price_per_100g(price, pack_size_grams):
    """Rs./100g unit price. None if price or weight is missing/zero."""
    if price is None or pd.isna(price):
        return None
    if pack_size_grams is None or pd.isna(pack_size_grams) or pack_size_grams == 0:
        return None
    return price / pack_size_grams * 100


def goat_price_per_100g(df):
    """Average GOAT Life price-per-100g across a platform's own listings.
    GOAT sells more than one pack size (75g and 60g SKUs both appear in
    Blinkit data), so this is computed from GOAT's actual rows rather than a
    fixed reference price. df must have "is_goat" and "price_per_100g"
    columns. None if there are no GOAT rows with a computable rate."""
    vals = df.loc[df["is_goat"], "price_per_100g"].dropna()
    return round(float(vals.mean()), 1) if len(vals) > 0 else None
