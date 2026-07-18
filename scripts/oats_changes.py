"""Price/availability change-detection for the oats competitor scrapers
(blinkit/swiggy/zepto oats), which capture per-brand-search competitor
listings rather than category shelf rank. Unlike shelf_changes.py's
detect_changes() (rank 1-4 GOAT shelf-position semantics), this operates on
whatever these three platforms actually capture: price, stock/availability,
and new/delisted SKUs. Pure functions only — no DB import here.

Blinkit oats and Swiggy oats capture no rank at all; Zepto oats has a Rank
column but it's rank within one brand's search results, not a category-wide
shelf position -- none of that is comparable to blinkit_goatlife's rank, so
this module never looks at "rank".
"""
from shelf_changes import normalize_product_identity


_OUT_OF_STOCK_MARKERS = ("sold out", "out of stock")


def _stock_state(stock_left):
    if stock_left is None:
        return None
    s = str(stock_left).strip()
    if not s or s.lower() == "nan":
        return None
    lowered = s.lower()
    return "out" if any(marker in lowered for marker in _OUT_OF_STOCK_MARKERS) else "in"


def build_oats_snapshot(rows):
    """rows: list of dicts with city_raw, locality_raw, brand_searched,
    product_name, selling_price, stock_left, is_goat (shelf_snapshots
    columns). Returns {(city, locality, brand_searched, normalized_identity):
    {"price": float | None, "stock_left": str | None, "display_name": str,
    "is_goat": bool}}."""
    snap = {}
    for r in rows:
        if r["product_name"] is None:
            continue
        identity = normalize_product_identity(r["product_name"])
        key = (r["city_raw"], r["locality_raw"], r["brand_searched"], identity)
        price = float(r["selling_price"]) if r["selling_price"] is not None else None
        snap[key] = {
            "price": price,
            "stock_left": r.get("stock_left"),
            "display_name": r["product_name"],
            "is_goat": bool(r.get("is_goat")),
        }
    return snap


def detect_price_availability_changes(rows_new, rows_old, price_threshold_inr=20, price_threshold_pct=15):
    snap_new = build_oats_snapshot(rows_new)
    snap_old = build_oats_snapshot(rows_old)

    new_products, gone_products = [], []
    price_changes, stock_changes = [], []

    for key in set(snap_new) | set(snap_old):
        city, locality, brand_searched, _identity = key
        new_entry, old_entry = snap_new.get(key), snap_old.get(key)
        is_goat = (new_entry or old_entry)["is_goat"]

        if new_entry and not old_entry:
            new_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                  "product": new_entry["display_name"], "is_goat": is_goat})
            continue

        if old_entry and not new_entry:
            gone_products.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                   "product": old_entry["display_name"], "is_goat": is_goat})
            continue

        # Only compare prices/stock when the raw listing name (pack size
        # included) is actually unchanged -- see shelf_changes.py's identical
        # guard for why (confirmed real false-positive pattern there).
        if new_entry["display_name"] != old_entry["display_name"]:
            continue

        new_price, old_price = new_entry["price"], old_entry["price"]
        if new_price is not None and old_price is not None and new_price > 0 and old_price > 0:
            change_abs = abs(new_price - old_price)
            change_pct = (change_abs / old_price * 100) if old_price else 0
            if change_abs >= price_threshold_inr or change_pct >= price_threshold_pct:
                price_changes.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                       "product": new_entry["display_name"], "old_price": old_price,
                                       "new_price": new_price, "change": new_price - old_price,
                                       "is_goat": is_goat})

        old_state = _stock_state(old_entry["stock_left"])
        new_state = _stock_state(new_entry["stock_left"])
        if old_state is not None and new_state is not None and old_state != new_state:
            stock_changes.append({"city": city, "locality": locality, "brand_searched": brand_searched,
                                   "product": new_entry["display_name"], "old_stock": old_entry["stock_left"],
                                   "new_stock": new_entry["stock_left"], "is_goat": is_goat})

    return {
        "new_products": new_products, "gone_products": gone_products,
        "price_changes": price_changes, "stock_changes": stock_changes,
    }
