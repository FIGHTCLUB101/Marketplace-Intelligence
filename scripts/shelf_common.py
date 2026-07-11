"""Shared helpers for turning scraped/computed data into DB-ready values.

compute_loc_key mirrors the join logic enrich_competitor_data.py already uses,
tightened to a city+area composite key (every scraper already records City
separately, so this needs no new data) to avoid collisions between
same-named localities in different cities.
"""
import re


def compute_loc_key(city, area) -> str:
    return f"{str(city).strip().lower()}|{str(area).strip().lower()}"


def is_goat_brand(product_name) -> bool:
    return "goat life" in str(product_name).lower()


def to_float(value):
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in ("", "n/a", "nan", "none"):
        return None
    nums = re.findall(r"\d+\.?\d*", s.replace(",", ""))
    if not nums:
        return None
    return float(nums[-1])


def to_int(value):
    f = to_float(value)
    return int(f) if f is not None else None


def to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None
