"""Shelf change-detection, ported from the antigravity repo's
shelf_monitor.py (detect_changes/build_shelf_snapshot/generate_narrative_summary,
96 tests) to operate on Postgres shelf_snapshots rows (list[dict], the shape
RealDictCursor returns) instead of pandas DataFrames.

Pure functions only — no DB import here. is_goat is now a precomputed
boolean column (set by the scraper's is_goat_brand() at scrape time), which
replaces the original's runtime case-insensitive keyword matching.

ICP-weighted narrative prioritization and historical_recurrence (both real
features of the original) are deferred to Sprint 5 — there is currently
only one scrape_run per platform in the database, so there is no history to
weight yet.
"""
import re

PLACEHOLDER_NAMES = ("N/A", "Not Available", "Location Error")

# Confirmed real-world case (2026-07-13 production data, run 7 vs run 168):
# Blinkit's own listing for the exact same physical SKU sometimes carries a
# "- Pack of N" or "- Combo [of N]" suffix and sometimes doesn't, between
# scrapes -- with no suffix normalization, ~half of all "gone"/"new"/
# "displaced" events on real data were this single false-positive pattern.
_VARIANT_SUFFIX_RE = re.compile(r"\s*-\s*(pack of \d+|combo(?:\s+of\s+\d+)?)\s*$", re.IGNORECASE)


def normalize_product_identity(name):
    """Strips known pack-size/bundle-variant suffixes so the same physical
    product scraped with a different suffix on different weeks is still
    recognized as the same product for identity matching. Matching-key use
    only — the raw scraped name is preserved separately as "display_name"
    for anything shown to a human."""
    return _VARIANT_SUFFIX_RE.sub("", name).strip()


def build_shelf_snapshot(rows):
    """rows: list of dicts with city_raw, locality_raw, product_name, rank,
    selling_price (shelf_snapshots columns). Returns
    {(city, locality, normalized_product_identity): {"rank": int,
    "price": float | None, "display_name": str}}. display_name is the raw
    scraped product_name, preserved for display even though the key is
    normalized. Rows with rank=None (Not Serviceable / Location Error
    placeholders) are skipped — matches the original's numeric-rank-only
    filter."""
    snap = {}
    for r in rows:
        if r["rank"] is None:
            continue
        identity = normalize_product_identity(r["product_name"])
        key = (r["city_raw"], r["locality_raw"], identity)
        price = float(r["selling_price"]) if r["selling_price"] is not None else None
        snap[key] = {"rank": r["rank"], "price": price, "display_name": r["product_name"]}
    return snap


def not_serviceable_localities(rows):
    """Returns {(city, locality)} for rows the scraper marked Not Serviceable."""
    return {(r["city_raw"], r["locality_raw"]) for r in rows if r["product_name"] == "Not Serviceable"}


def _is_goat_lookup(rows_new, rows_old):
    lookup = {}
    for r in rows_new + rows_old:
        if r["rank"] is not None:
            identity = normalize_product_identity(r["product_name"])
            lookup[(r["city_raw"], r["locality_raw"], identity)] = r["is_goat"]
    return lookup


def detect_changes(rows_new, rows_old, drop_calendar=None, price_threshold_inr=20, price_threshold_pct=15):
    snap_new = build_shelf_snapshot(rows_new)
    snap_old = build_shelf_snapshot(rows_old)
    is_goat_of = _is_goat_lookup(rows_new, rows_old)
    ns_new = not_serviceable_localities(rows_new)
    drop_calendar = drop_calendar or set()

    goat_displaced, goat_recovered = [], []
    new_products, gone_products = [], []
    rank_intrusions, rank_moved = [], []
    price_changes = []

    for key in set(snap_new) | set(snap_old):
        city, locality, name = key
        if (city, locality) in ns_new:
            continue
        new_entry, old_entry = snap_new.get(key), snap_old.get(key)
        new_rank = new_entry["rank"] if new_entry else None
        old_rank = old_entry["rank"] if old_entry else None
        new_price = new_entry["price"] if new_entry else None
        old_price = old_entry["price"] if old_entry else None
        is_goat = is_goat_of.get(key, False)
        is_placeholder = name in PLACEHOLDER_NAMES
        # Display names: prefer the current (new) raw scraped name when
        # present, falling back to the old one -- "name" (the dict key) is
        # the normalized identity and must never be shown to a human.
        new_display = new_entry["display_name"] if new_entry else None
        old_display = old_entry["display_name"] if old_entry else None
        current_display = new_display or old_display

        if new_entry and not old_entry and not is_placeholder:
            new_products.append({"city": city, "locality": locality, "rank": new_rank, "product": new_display})

        if old_entry and not new_entry and not is_placeholder:
            if not (is_goat and name in drop_calendar):
                gone_products.append({"city": city, "locality": locality, "rank": old_rank,
                                       "product": old_display, "is_goat": is_goat})

        if new_entry and old_entry and new_rank != old_rank and not is_placeholder:
            rank_moved.append({"city": city, "locality": locality, "product": current_display,
                                "old_rank": old_rank, "new_rank": new_rank, "is_goat": is_goat})

        if not is_placeholder and is_goat and old_entry and old_rank in (1, 2, 3, 4):
            if not new_entry or new_rank not in (1, 2, 3, 4):
                if name not in drop_calendar:
                    now_label = f"Still listed, now rank {new_rank}" if new_entry else "MISSING"
                    goat_displaced.append({"city": city, "locality": locality, "rank": old_rank,
                                            "was": old_display, "now": now_label})

        if not is_placeholder and is_goat and new_entry and new_rank in (1, 2, 3, 4):
            if not old_entry or old_rank not in (1, 2, 3, 4):
                goat_recovered.append({"city": city, "locality": locality, "rank": new_rank, "product": new_display})

        if not is_placeholder and not is_goat and new_entry and new_rank in (1, 2, 3, 4):
            if not old_entry or old_rank not in (1, 2, 3, 4):
                rank_intrusions.append({"city": city, "locality": locality, "rank": new_rank, "intruder": new_display})

        # Only compare prices when the raw listing name (pack size included)
        # is actually unchanged -- comparing a single-pack price to the same
        # product's "- Pack of N" price is comparing different quantities,
        # not a real per-unit price movement (confirmed real 2026-07-13
        # production artifact: this produced a spurious ~496-locality spike).
        if new_price and old_price and not is_placeholder and new_display == old_display:
            change_abs = abs(new_price - old_price)
            change_pct = (change_abs / old_price * 100) if old_price else 0
            if change_abs >= price_threshold_inr or change_pct >= price_threshold_pct:
                price_changes.append({"city": city, "locality": locality, "product": current_display,
                                       "old_price": old_price, "new_price": new_price,
                                       "change": new_price - old_price})

    return {
        "goat_displaced": goat_displaced, "goat_recovered": goat_recovered,
        "new_products": new_products, "gone_products": gone_products,
        "rank_intrusions": rank_intrusions, "rank_moved": rank_moved,
        "price_changes": price_changes,
    }


def goat_gone_unique(changes):
    """GOAT gone_products entries not already represented in goat_displaced
    (which covers rank 1-4 SKUs that vanished — same event, don't double-count).
    Keyed by the full (city, locality, product) identity, not name alone — the
    same SKU can independently vanish in one locality while being separately
    displaced in another, and both are real, distinct events."""
    displaced_keys = {(e["city"], e["locality"], e["was"]) for e in changes["goat_displaced"]}
    return [g for g in changes["gone_products"]
            if g["is_goat"] and (g["city"], g["locality"], g["product"]) not in displaced_keys]


def generate_narrative_summary(changes):
    """Returns 1-2 plain-language sentences. Lead sentence is whichever
    threat's product name recurs most often this week (frequency-only —
    ICP-weighted prioritization is Sprint 5). A "threat" is a rank
    disruption, a competitor intrusion, or a GOAT SKU vanishing entirely
    (goat_gone_unique avoids double-counting a rank-1-4 SKU that appears in
    both goat_displaced and gone_products for the same real event)."""
    threats = list(changes["goat_displaced"]) + list(changes["rank_intrusions"]) + list(goat_gone_unique(changes))

    if not threats:
        return ["GOAT Life holds ranks 1-4 across all monitored localities. "
                "No competitor has moved into your shelf space this week."]

    def product_name_of(entry):
        return entry.get("was") or entry.get("intruder") or entry.get("product") or ""

    name_counts = {}
    for e in threats:
        name_counts[product_name_of(e)] = name_counts.get(product_name_of(e), 0) + 1

    lead = max(threats, key=lambda e: name_counts[product_name_of(e)])
    product, city = product_name_of(lead), lead["city"]
    if "intruder" in lead:
        sentence = f"{product[:40]} intruded into GOAT Life's shelf space in {city} this week."
    elif "was" in lead:
        sentence = f"GOAT Life lost shelf position for {product[:40]} in {city} this week."
    else:
        sentence = f"GOAT Life's {product[:40]} disappeared from the shelf in {city} this week."
    sentences = [sentence]

    other_count = len(threats) - name_counts[product_name_of(lead)]
    if other_count > 0:
        sentences.append(f"{other_count} other change{'s' if other_count != 1 else ''} detected this week.")

    return sentences
