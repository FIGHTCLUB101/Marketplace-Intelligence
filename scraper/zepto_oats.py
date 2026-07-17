"""
Zepto Instamart Oats Brand Scraper
Scrapes competitor oats-brand product availability, pricing, ratings, and
sponsored tags across Top 50 localities (by residential property price =
spending power) in each of the 10 cities. Searches 10 competitor brands
per locality.

Output: scraper/output/zepto_oats_data.xlsx
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import re, time, winsound, urllib.parse
from pathlib import Path

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, is_blocked,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    shard_localities, should_restart_driver, wait_for_manual_unblock,
)

# ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"
OUTPUT_FILE      = ROOT / "scraper" / "output" / "zepto_oats_data.xlsx"

# Brands to search
BRANDS = [
    "Pintola", "Yoga Bar", "Quaker", "MuscleBlaze", "Alpino",
    "True Elements", "Saffola", "Cosmix", "SuperYou", "The Whole Truth"
]

COLUMNS = ["Locality", "Brand Searched", "Rank", "Product Name", "Selling Price",
           "MRP", "Discount", "Pack Size", "Rating", "Reviews", "Sponsored"]

# ─────────────────────────────────────────────
def extract_buy_price(price_str):
    if pd.isna(price_str) or str(price_str).strip() in ('N/A','nan',''): return 0
    m = re.search(r'Buy Rs\.\s*([\d,]+)\s*-\s*Rs\.\s*([\d,]+)', str(price_str))
    if m: return (int(m.group(1).replace(',','')) + int(m.group(2).replace(',',''))) / 2
    return 0

def load_localities(filepath):
    try:
        df_mb = pd.read_excel(filepath)
        df_mb['avg_buy_price'] = df_mb['price range(for residential, office space, shop)'].apply(extract_buy_price)

        target_localities = []
        for city in df_mb['ADDRESS'].unique():
            city_df = df_mb[df_mb['ADDRESS'] == city].copy()
            top = city_df[city_df['avg_buy_price'] > 0].nlargest(50, 'avg_buy_price')
            if len(top) < 50:
                pad = city_df[city_df['avg_buy_price'] == 0].head(50 - len(top))
                top = pd.concat([top, pad])
            for _, row in top.iterrows():
                area = str(row['AREA']).split(',')[0].strip()
                price = row['avg_buy_price']
                price_str = f"Rs.{price:,.0f}/sqft"
                target_localities.append({
                    'loc_str': f"{area}, {city}",
                    'price': price,
                    'price_str': price_str
                })
        return target_localities
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

def make_sort_key_fn(localities):
    """Ranks a merged row the same way the sequential scraper already
    orders its output -- by locality's position in `localities`, then
    brand's position in BRANDS -- so parallel_runner.py's periodic merge
    produces a file that reads identically to a single-worker run,
    regardless of which shard actually scraped which row."""
    locality_rank = {loc['loc_str']: i for i, loc in enumerate(localities)}
    brand_rank = {b: i for i, b in enumerate(BRANDS)}

    def sort_key(row):
        loc_rank = locality_rank.get(row.get('Locality'), len(locality_rank))
        b_rank = brand_rank.get(row.get('Brand Searched'), len(brand_rank))
        return (loc_rank, b_rank)

    return sort_key

def parse_zepto_card(card_text):
    parts = [p.strip() for p in card_text.split('|') if p.strip()]

    is_sponsored = "False"
    if "Ad" in parts or "Sponsored" in parts:
        is_sponsored = "True"

    prices = [p for p in parts if '₹' in p]
    sp, mrp, discount = "N/A", "N/A", "N/A"
    if len(prices) >= 1:
        sp = prices[0].replace('₹', 'Rs.')
    if len(prices) >= 2:
        mrp = prices[1].replace('₹', 'Rs.')
    if len(prices) >= 3:
        discount = prices[2].replace('₹', 'Rs.') + " OFF"

    name_parts = []
    pack_size = "N/A"
    rating = "N/A"
    reviews = "N/A"

    for p in parts:
        if p == 'ADD' or '₹' in p or p == 'OFF' or p == 'Ad' or p == 'Sponsored' or p == 'Bestseller' or p.startswith('Get it for'):
            continue

        if p.startswith('(') and p.endswith(')'):
            reviews = p
            continue

        try:
            val = float(p)
            if '.' in p and val < 6:
                rating = p
                continue
        except ValueError:
            pass

        p_lower = p.lower()
        if ('pack' in p_lower or 'kg' in p_lower or ' g' in p_lower or p_lower.endswith('g') or 'pc' in p_lower) and len(p) < 25 and any(char.isdigit() for char in p):
            if pack_size == "N/A":
                pack_size = p
                continue

        if len(p) > 2:
            name_parts.append(p)

    name = " | ".join(name_parts) if name_parts else "N/A"

    return {
        'name': name.replace('₹', 'Rs.'),
        'sp': sp,
        'mrp': mrp,
        'discount': discount,
        'pack_size': pack_size,
        'rating': rating,
        'reviews': reviews,
        'sponsored': is_sponsored
    }

def has_sponsored_badge(img_srcs):
    """True if any image src matches Zepto's sponsored/"Ad" badge asset.
    Zepto renders that badge as a small image overlay (filename ending in
    "_Ad.png"), not as text, so it never appears in a card's innerText --
    the text-based "Ad"/"Sponsored" check in parse_zepto_card can't see it.
    Verified against a live zepto.com search results page (2026-07-16): the
    badge image was present on a sponsored card and absent on an organic
    card for the same search."""
    return any(src.lower().endswith("_ad.png") for src in img_srcs if src)

def is_oats_product(name):
    """True if the product name indicates an actual oats product. Even with
    "Oats" in the search query, these platforms can still surface non-oats
    products from a matched brand (confirmed on Blinkit: "Pintola oats"
    returned "Pintola All Natural Crunchy Peanut Butter") -- this scraper is
    oats-category data only, so those get dropped regardless of brand."""
    return "oat" in name.lower()

# ─────────────────────────────────────────────
def beep():
    for _ in range(2):
        winsound.Beep(1000, 500)
        time.sleep(0.3)

def create_driver():
    opts = uc.ChromeOptions()
    opts.add_argument('--start-maximized')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    # Chrome throttles JS timers/rendering on minimized (occluded) windows,
    # which breaks this scraper's fixed time.sleep() waits (the page hasn't
    # actually finished loading yet when Selenium resumes) -- these three
    # flags keep the renderer running at full speed regardless of window
    # visibility, so the browser window can be minimized while this runs.
    opts.add_argument('--disable-background-timer-throttling')
    opts.add_argument('--disable-backgrounding-occluded-windows')
    opts.add_argument('--disable-renderer-backgrounding')
    # The three flags above cover generic Chromium background-tab/renderer
    # throttling, but Windows has its own, separate mechanism -- "Native
    # Window Occlusion" -- that watches window state at the OS level and
    # throttles Chrome when the window is minimized, independent of the
    # above. Confirmed live: minimizing the window broke scraping even with
    # the other three flags in place.
    opts.add_argument('--disable-features=CalculateNativeWinOcclusion')
    # version_main=150 pinned explicitly -- undetected_chromedriver's own
    # auto-detect (the previous approach here) resolved to ChromeDriver 151
    # against an actually-installed Chrome 150.0.7871.115, failing with
    # "session not created". Bump this to match Chrome's major version
    # (see chrome://settings/help) whenever Chrome auto-updates past it.
    driver = uc.Chrome(options=opts, version_main=150)
    defeat_visibility_throttling(driver)
    keep_window_unminimized(driver)
    return driver

# ─────────────────────────────────────────────
def set_location(driver, loc_str, wait):
    print(f"  📍 Setting location → {loc_str}", flush=True)

    for attempt in range(3):
        try:
            driver.get('https://www.zeptonow.com/')
            time.sleep(3)
            if not wait_for_manual_unblock(driver, beep):
                print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

            # 1. Click Location
            loc_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Select Location')]/.. | //span[contains(@class, 'cTJX6L')]/..")))
            driver.execute_script("arguments[0].click();", loc_btn)
            time.sleep(2)

            # 2. Enter Location
            loc_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search a new address']")))
            loc_input.clear()
            loc_input.send_keys(loc_str)
            time.sleep(3)

            # 3. Click first autocomplete
            first_result = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'line-clamp-2')]")))
            driver.execute_script("arguments[0].click();", first_result)
            time.sleep(3)

            try:
                confirm_btn = driver.find_element(By.XPATH, "//button[contains(., 'Confirm') or contains(., 'Continue')]")
                driver.execute_script("arguments[0].click();", confirm_btn)
                time.sleep(2)
            except:
                pass

            print(f"  ✅ Selected: (pressed Enter)", flush=True)
            return True

        except Exception as e:
            if is_dead_session_error(e):
                raise  # let the outer loop restart the driver and retry the locality
            print(f"  ❌ Attempt {attempt+1}: {str(e)[:100]}", flush=True)
            time.sleep(3)

    return False

# ─────────────────────────────────────────────
def scrape_brand(driver, brand, loc_str):
    records = []
    try:
        print(f"\n  🛒 Searching: {brand} Oats", flush=True)
        query = urllib.parse.quote(f"{brand} Oats")

        # Zepto occasionally shows a rate-limit-style "Please login to
        # continue searching" wall. Confirmed live: it does NOT clear by
        # waiting on the same page (nothing re-fetches without a new
        # navigation) -- it clears on a subsequent fresh driver.get(), so we
        # retry via re-navigation rather than a long static poll (which is
        # what wait_for_manual_unblock does, built for CAPTCHA that a human
        # solves in place). Bounded at 3 attempts so a permanently-blocked
        # run doesn't spin forever.
        for attempt in range(3):
            driver.get(f"https://www.zeptonow.com/search?query={query}")
            time.sleep(4)
            if not is_blocked(driver):
                break
            print(f"  ⚠️  Blocked (attempt {attempt+1}/3) — retrying with a fresh page load...", flush=True)
            jittered_sleep(3.0, jitter_s=2.0)
        else:
            print("  ⚠️  Still blocked after 3 attempts — skipping this search.", flush=True)

        # Ensure cards load
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)

        cards = driver.find_elements(By.TAG_NAME, "a")
        product_cards = []
        for card in cards:
            text = card.text
            if "ADD" in text and "₹" in text:
                product_cards.append(card)

        print(f"    🔍 '{brand} Oats': {len(product_cards)} card(s) found", flush=True)

        for i, card in enumerate(product_cards[:15]):
            card_text = driver.execute_script("return arguments[0].innerText;", card)
            card_text_clean = " | ".join([x.strip() for x in card_text.split('\n') if x.strip()])

            pdata = parse_zepto_card(card_text_clean)
            if not is_oats_product(pdata['name']):
                continue

            img_srcs = [img.get_attribute("src") for img in card.find_elements(By.TAG_NAME, "img")]
            if has_sponsored_badge(img_srcs):
                pdata['sponsored'] = "True"

            sp_disp = pdata['sp'].replace('Rs.', '₹').replace(' ', '')
            mrp_disp = pdata['mrp'].replace('Rs.', '₹').replace(' ', '')
            print(f"    ✅ {pdata['name'][:36].ljust(36)} {pdata['pack_size'].ljust(8)} {sp_disp.ljust(5)} (MRP:{mrp_disp})", flush=True)

            records.append({
                "Locality": loc_str,
                "Brand Searched": brand,
                "Rank": i + 1,
                "Product Name": pdata['name'],
                "Selling Price": pdata['sp'],
                "MRP": pdata['mrp'],
                "Discount": pdata['discount'],
                "Pack Size": pdata['pack_size'],
                "Rating": pdata['rating'],
                "Reviews": pdata['reviews'],
                "Sponsored": pdata['sponsored']
            })

    except Exception as e:
        if is_dead_session_error(e):
            raise  # let the outer loop restart the driver and retry the locality
        print(f"    ❌ Error: {str(e)[:80]}", flush=True)
    return records

# ─────────────────────────────────────────────
def not_available_row(loc_str, brand, reason="Location Error"):
    return {
        "Locality": loc_str, "Brand Searched": brand, "Rank": "N/A",
        "Product Name": reason, "Selling Price": "N/A", "MRP": "N/A",
        "Discount": "N/A", "Pack Size": "N/A", "Rating": "N/A",
        "Reviews": "N/A", "Sponsored": "N/A",
    }

# ─────────────────────────────────────────────
def scrape_zepto(localities=None, output_file=None):
    print("=================================================================", flush=True)
    print("  ZEPTO INSTAMART OATS SCRAPER - Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("=================================================================\n", flush=True)

    if localities is None:
        localities = load_localities(str(MAGICBRICKS_FILE))
    if output_file is None:
        output_file = OUTPUT_FILE
    if not localities:
        print("No localities found. Exiting.", flush=True)
        return

    print(f"📋 Localities: {len(localities)} | Brands: {len(BRANDS)} | Est. searches: {len(localities)*len(BRANDS)}\n", flush=True)

    wb = IncrementalWorkbook(output_file, columns=COLUMNS)
    done_keys = wb.done_keys(["Locality", "Brand Searched"])
    if done_keys:
        print(f"📂 Resuming — {len(done_keys)} (locality, brand) pairs already saved.", flush=True)

    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    total = len(localities)
    i = 0
    retries = 0

    try:
        while i < total:
            loc_obj = localities[i]
            loc_str = loc_obj['loc_str']
            price_str = loc_obj['price_str']

            brands_todo = [b for b in BRANDS if f"{loc_str}|{b}" not in done_keys]
            if not brands_todo:
                print(f"\n⏭️  [{i+1}/{total}] SKIP {loc_str} (all done)", flush=True)
                i += 1
                continue

            if retries == 0 and should_restart_driver(i, restart_every=25):
                print(f"\n🔄 Restarting browser at locality {i+1} to keep memory healthy...", flush=True)
                try: driver.quit()
                except: pass
                driver = create_driver()
                wait = WebDriverWait(driver, 10)

            print(f"=================================================================", flush=True)
            print(f"[{i+1}/{total}] {loc_str}  ({price_str})", flush=True)
            print(f"=================================================================", flush=True)

            try:
                ok = set_location(driver, loc_str, wait)
                if not ok:
                    for b in brands_todo:
                        wb.append_row(not_available_row(loc_str, b, "Location Error"))
                        done_keys.add(f"{loc_str}|{b}")
                else:
                    for brand in brands_todo:
                        records = scrape_brand(driver, brand, loc_str)
                        if not records:
                            wb.append_row(not_available_row(loc_str, brand, "Not Available"))
                        else:
                            for r in records:
                                wb.append_row(r)
                        done_keys.add(f"{loc_str}|{brand}")

                wb.save()
                print(f"\n  💾 Saved (locality {i+1}/{total})", flush=True)
                i += 1
                retries = 0

            except Exception as e:
                if is_dead_session_error(e) and retries < 2:
                    retries += 1
                    print(f"\n🔁 Browser session died ({str(e)[:60]}) — restarting and retrying "
                          f"{loc_str} (attempt {retries+1})...", flush=True)
                    try: driver.quit()
                    except: pass
                    driver = create_driver()
                    wait = WebDriverWait(driver, 10)
                    continue  # retry same i (including any brands within it not yet done)
                elif is_dead_session_error(e):
                    print(f"\n⚠️  {loc_str} failed after {retries} restarts — marking error and moving on.", flush=True)
                    remaining = [b for b in brands_todo if f"{loc_str}|{b}" not in done_keys]
                    for b in remaining:
                        wb.append_row(not_available_row(loc_str, b, "Location Error"))
                        done_keys.add(f"{loc_str}|{b}")
                    wb.save()
                    i += 1
                    retries = 0
                else:
                    print(f"\n❌ Unexpected error on {loc_str}: {str(e)[:100]}", flush=True)
                    remaining = [b for b in brands_todo if f"{loc_str}|{b}" not in done_keys]
                    for b in remaining:
                        wb.append_row(not_available_row(loc_str, b, "Location Error"))
                        done_keys.add(f"{loc_str}|{b}")
                    wb.save()
                    i += 1
                    retries = 0

            jittered_sleep(1.0, jitter_s=1.5)

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.", flush=True)
    finally:
        wb.save()
        print(f"\n✅ Final save → {output_file}", flush=True)
        try: driver.quit()
        except: pass

    print("\n" + "="*65, flush=True)
    print("  SCRAPING COMPLETE!", flush=True)
    print("="*65, flush=True)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, default=None,
                         help="This worker's shard number (0-based). Required with --num-shards > 1.")
    parser.add_argument("--num-shards", type=int, default=1,
                         help="Total number of shards. Omit (or 1) to scrape all 500 localities normally.")
    args = parser.parse_args()

    if args.num_shards > 1:
        if args.shard_index is None:
            parser.error("--shard-index is required when --num-shards > 1")
        all_localities = load_localities(str(MAGICBRICKS_FILE))
        shard = shard_localities(all_localities, args.shard_index, args.num_shards)
        shard_output = ROOT / "scraper" / "output" / "_shards" / f"zepto_oats_shard{args.shard_index}.xlsx"
        scrape_zepto(localities=shard, output_file=shard_output)
    else:
        scrape_zepto()
