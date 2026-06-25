import re

import pandas as pd
import pgeocode


def extract_pincode(text):
    if not text:
        return None
    m = re.search(r"\b(\d{6})\b", str(text))
    return m.group(1) if m else None


def make_geocoder():
    """Return a cached pincode -> (lat, lng) lookup for India (offline)."""
    nomi = pgeocode.Nominatim("in")
    cache = {}

    def geocode(pin):
        if not pin:
            return None
        pin = re.sub(r"\D", "", str(pin))[:6]
        if len(pin) != 6:
            return None
        if pin in cache:
            return cache[pin]
        r = nomi.query_postal_code(pin)
        res = None if (r is None or pd.isna(r.latitude)) else (
            round(float(r.latitude), 5), round(float(r.longitude), 5)
        )
        cache[pin] = res
        return res

    return geocode


def attach_coords(records, pin_key="pincode", addr_key=None, geocode=None):
    """Mutate records adding lat/lng. Falls back to a pincode parsed from addr_key."""
    if geocode is None:
        geocode = make_geocoder()
    hit = 0
    for rec in records:
        pin = rec.get(pin_key)
        if not pin and addr_key:
            pin = extract_pincode(rec.get(addr_key))
            rec[pin_key] = pin
        res = geocode(pin)
        rec["lat"], rec["lng"] = (res if res else (None, None))
        if res:
            hit += 1
    return {"total": len(records), "hit": hit}
