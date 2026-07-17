"""
Swiggy Instamart Oats Brand Scraper
Scrapes oats brand availability, pricing, ratings, protein info, and
sponsored tags across Top 50 localities (by residential property price =
spending power) in each of the 10 cities. Searches 10 competitor brands
per locality.

Output: scraper/output/swiggy_oats_data.xlsx
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import os, re, time, winsound
from pathlib import Path

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, is_dead_session_error,
    jittered_sleep, keep_window_unminimized, should_restart_driver,
    wait_for_manual_unblock,
)

# ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"
OUTPUT_FILE      = ROOT / "scraper" / "output" / "swiggy_oats_data.xlsx"
TOP_N            = 50

BRANDS = [
    "Pintola Oats", "Yoga Bar Oats", "Quaker Oats", "MuscleBlaze Oats",
    "Alpino Oats", "True Elements Oats", "Saffola Oats", "Cosmix Oats",
    "SuperYou Oats", "The Whole Truth Oats",
]

COLUMNS = ["City", "Locality", "Brand Searched", "Product Name", "Protein Info",
           "Sponsored", "Pack Size", "Selling Price", "MRP", "Discount %",
           "Stock Left", "Rating", "Serviceable"]

# ─────────────────────────────────────────────
def extract_buy_price(price_str):
    if pd.isna(price_str) or str(price_str).strip() in ('N/A','nan',''): return 0
    m = re.search(r'Buy Rs\.\s*([\d,]+)\s*-\s*Rs\.\s*([\d,]+)', str(price_str))
    if m: return (int(m.group(1).replace(',','')) + int(m.group(2).replace(',',''))) / 2
    return 0

def beep():
    for _ in range(2):
        winsound.Beep(1000, 500)
        time.sleep(0.3)

def create_driver():
    opts = uc.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-IN")
    # Chrome throttles JS timers/rendering on minimized (occluded) windows,
    # which breaks this scraper's fixed time.sleep() waits (the page hasn't
    # actually finished loading yet when Selenium resumes) -- these three
    # flags keep the renderer running at full speed regardless of window
    # visibility, so the browser window can be minimized while this runs.
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    # The three flags above cover generic Chromium background-tab/renderer
    # throttling, but Windows has its own, separate mechanism -- "Native
    # Window Occlusion" -- that watches window state at the OS level and
    # throttles Chrome when the window is minimized, independent of the
    # above. Confirmed live: minimizing the window broke scraping even with
    # the other three flags in place.
    opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
    # version_main=150 pinned explicitly -- undetected_chromedriver's own
    # auto-detect (the previous approach here) resolved to ChromeDriver 151
    # against an actually-installed Chrome 150.0.7871.115, failing with
    # "session not created". Bump this to match Chrome's major version
    # (see chrome://settings/help) whenever Chrome auto-updates past it.
    driver = uc.Chrome(options=opts, version_main=150)
    defeat_visibility_throttling(driver)
    keep_window_unminimized(driver)
    return driver

def get_visible_input(driver):
    inputs = driver.find_elements(By.TAG_NAME, "input")
    for inp in inputs:
        if inp.is_displayed(): return inp
    return None

def click_element(driver, el):
    try: el.click()
    except:
        try: ActionChains(driver).move_to_element(el).click().perform()
        except: driver.execute_script("arguments[0].click();", el)

# ─────────────────────────────────────────────
def set_location(driver, locality, city):
    search_query = f"{locality}, {city}"
    short_query = locality.split()[0].lower()
    print(f"  📍 Setting location → {search_query}", flush=True)

    for attempt in range(3):
        try:
            driver.delete_all_cookies()
            driver.get("https://www.swiggy.com/instamart")
            time.sleep(4)
            if not wait_for_manual_unblock(driver, beep):
                print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

            input_el = get_visible_input(driver)

            if not input_el:
                try:
                    fake_inputs = driver.find_elements(By.XPATH, "//div[contains(text(), 'Search for an area or address')]")
                    for f in fake_inputs:
                        if f.is_displayed():
                            click_element(driver, f)
                            time.sleep(2)
                            break
                except: pass

                time.sleep(1)
                input_el = get_visible_input(driver)
                if not input_el:
                    loc_btns = driver.find_elements(By.XPATH, "//div[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'select your location') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'setup your precise')]")
                    for b in loc_btns:
                        if b.is_displayed():
                            click_element(driver, b)
                            time.sleep(2)
                            break

                time.sleep(1)
                input_el = get_visible_input(driver)

            if not input_el:
                print(f"  ❌ Attempt {attempt+1}: Could not find actual location input.", flush=True)
                continue

            driver.execute_script("arguments[0].value = ''; arguments[0].focus();", input_el)
            time.sleep(0.5)
            actions = ActionChains(driver)
            actions.click(input_el)
            actions.send_keys(search_query)
            actions.perform()
            time.sleep(4)

            suggestion_clicked = False
            suggestion_text = "None found"

            xpath = f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{short_query}')] | //div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{short_query}') and @role='button']"
            suggestions = driver.find_elements(By.XPATH, xpath)

            if not suggestions:
                xpath2 = f"//div[contains(@class, 'container') or contains(@class, 'list')]//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{short_query}')]"
                suggestions = driver.find_elements(By.XPATH, xpath2)

            for s in suggestions:
                if s.is_displayed() and len(s.text) > 3:
                    try:
                        suggestion_text = s.text.replace('\n', ' ')[:60]
                        click_element(driver, s)
                        suggestion_clicked = True
                        break
                    except: pass

            if not suggestion_clicked:
                try:
                    input_el.send_keys(Keys.RETURN)
                    suggestion_clicked = True
                    suggestion_text = "(Pressed Enter)"
                except: pass

            if suggestion_clicked:
                print(f"  ✅ Selected: {suggestion_text}", flush=True)
                time.sleep(5)
                return True

        except Exception as e:
            if is_dead_session_error(e):
                raise  # let the outer loop restart the driver and retry the locality
            print(f"  ❌ Attempt {attempt+1}: {str(e)[:100]}", flush=True)
            time.sleep(3)

    return False

# ─────────────────────────────────────────────
def parse_card_block(ct):
    lines = [l.strip() for l in ct.split('\n') if l.strip()]

    clean_lines = []
    is_sponsored = "False"
    for l in lines:
        lu = l.upper()
        if "SPONSORED" in lu or lu == "AD" or "UPGRADE" in lu:
            is_sponsored = "True"
        if lu in ["AD", "UPGRADE", "SPONSORED", "ADD", "CUSTOMISABLE"] or "MINS" in lu or "DELIVERY" in lu:
            continue
        clean_lines.append(l)

    parsed_prods = []
    curr_prod = None

    for l in clean_lines:
        lu = l.upper()

        is_pack_size = bool(re.match(r'^\d+(\.\d+)?\s*(kg|g|ml|l|gm)$', l, re.I))
        is_discount  = bool(re.search(r'\d+%\s*OFF', l, re.I))
        is_price     = bool(re.match(r'^₹?\s*\d+(?:,\d+)?$', l))
        is_stock     = bool(re.search(r'SOLD OUT|OUT OF STOCK|CURRENTLY UNAVAILABLE|\d+\s+LEFT|ONLY\s+\d+', lu))
        is_protein   = bool(re.search(r'protein[\s:]+[\d.]+g?\s+per\s*100g', l, re.I))
        is_rating    = bool(re.match(r'^\d\.\d$', l))

        is_name = not (is_pack_size or is_discount or is_price or is_stock or is_protein or is_rating)

        if not is_name and curr_prod is None:
            continue

        if is_name:
            if curr_prod: parsed_prods.append(curr_prod)
            curr_prod = {
                "name": l, "pack_size": "N/A", "protein_info": "N/A", "stock": "In Stock",
                "prices": [], "discount": "N/A", "sponsored": is_sponsored, "rating": "N/A"
            }
        elif curr_prod:
            if is_pack_size: curr_prod["pack_size"] = l
            elif is_protein: curr_prod["protein_info"] = l
            elif is_stock:   curr_prod["stock"] = l
            elif is_discount:curr_prod["discount"] = l
            elif is_rating:  curr_prod["rating"] = l
            elif is_price:   curr_prod["prices"].append(int(l.replace('₹','').replace(',','').strip()))

    if curr_prod: parsed_prods.append(curr_prod)

    for p in parsed_prods:
        p["prices"] = sorted(set(p["prices"]))
        if len(p["prices"]) >= 2:
            p["sp"] = f"₹{p['prices'][0]}"
            p["mrp"] = f"₹{p['prices'][-1]}"
            p["discount"] = f"{round((1 - p['prices'][0]/p['prices'][-1])*100)}%"
        elif p["prices"]:
            p["sp"] = p["mrp"] = f"₹{p['prices'][0]}"
        else:
            p["sp"] = p["mrp"] = "N/A"

    return parsed_prods

def is_oats_product(name):
    """True if the product name indicates an actual oats product. Even with
    "Oats" in the search query, these platforms can still surface non-oats
    products from a matched brand (confirmed on Blinkit: "Pintola oats"
    returned "Pintola All Natural Crunchy Peanut Butter") -- this scraper is
    oats-category data only, so those get dropped regardless of brand."""
    return "oat" in name.lower()

# ─────────────────────────────────────────────
def scrape_brand(driver, brand, locality, city):
    products = []
    try:
        driver.get(f"https://www.swiggy.com/instamart/search?custom_back=true&query={brand.replace(' ','%20')}")
        time.sleep(4)
        if not wait_for_manual_unblock(driver, beep):
            print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1)

        page_lower = driver.page_source.lower()
        if "something went wrong" in page_lower or "no results" in page_lower:
            print(f"    ⚪ No results or error for '{brand}'", flush=True)
            return products

        cards = []
        try:
            bases = driver.find_elements(By.XPATH, "//*[starts-with(@data-testid, 'item-collection-card')]")
            for base in bases:
                try:
                    curr = base
                    for _ in range(3):
                        curr = curr.find_element(By.XPATH, "..")
                    if curr not in cards: cards.append(curr)
                except: pass
        except: pass

        print(f"    🔍 '{brand}': {len(cards)} card block(s) found on page", flush=True)

        variants_added = 0

        for card in cards:
            if variants_added >= 15: break

            try:
                ct = card.text
                if not ct or len(ct) < 5: continue

                parsed_prods = parse_card_block(ct)

                for p in parsed_prods:
                    if variants_added >= 15: break
                    if not is_oats_product(p['name']): continue

                    products.append({
                        "City": city, "Locality": locality, "Brand Searched": brand,
                        "Product Name": p['name'], "Protein Info": p['protein_info'], "Sponsored": p['sponsored'],
                        "Pack Size": p['pack_size'], "Selling Price": p['sp'], "MRP": p['mrp'], "Discount %": p['discount'],
                        "Stock Left": p['stock'], "Rating": p['rating'], "Serviceable": "Yes",
                    })

                    sponsored_marker = "[SPONS]" if p['sponsored'] == "True" else ""
                    print(f"    ✅ {p['name'][:25]:<25} {sponsored_marker:<10} {p['sp']} (MRP:{p['mrp']})", flush=True)
                    variants_added += 1
            except: pass

        if variants_added == 0:
            print(f"    ⚪ No matching variants found for '{brand}'", flush=True)

    except Exception as e:
        if is_dead_session_error(e):
            raise  # let the outer loop restart the driver and retry the locality
        print(f"    ❌ Error: {str(e)[:80]}", flush=True)
    return products

# ─────────────────────────────────────────────
def not_available_row(city, locality, brand, reason="Not Available"):
    return {
        "City": city, "Locality": locality, "Brand Searched": brand,
        "Product Name": reason, "Protein Info": "N/A", "Sponsored": "N/A",
        "Pack Size": "N/A", "Selling Price": "N/A", "MRP": "N/A", "Discount %": "N/A",
        "Stock Left": "N/A", "Rating": "N/A", "Serviceable": "Yes" if reason == "Not Available" else "No",
    }

# ─────────────────────────────────────────────
def main():
    print("="*65, flush=True)
    print("  SWIGGY INSTAMART OATS SCRAPER — Starting", flush=True)
    print("  If CAPTCHA appears, solve it in the browser!", flush=True)
    print("="*65, flush=True)

    df_mb = pd.read_excel(MAGICBRICKS_FILE)
    df_mb['avg_buy_price'] = df_mb['price range(for residential, office space, shop)'].apply(extract_buy_price)

    target_localities = []
    for city in df_mb['ADDRESS'].unique():
        city_df = df_mb[df_mb['ADDRESS'] == city].copy()
        top = city_df[city_df['avg_buy_price'] > 0].nlargest(TOP_N, 'avg_buy_price')
        if len(top) < TOP_N:
            pad = city_df[city_df['avg_buy_price'] == 0].head(TOP_N - len(top))
            top = pd.concat([top, pad])
        for _, row in top.iterrows():
            area = str(row['AREA']).split(',')[0].strip()
            target_localities.append({'locality': area, 'city': city, 'price': row['avg_buy_price']})

    print(f"\n📋 Localities: {len(target_localities)} | Brands: {len(BRANDS)} | Est. searches: {len(target_localities)*len(BRANDS)}", flush=True)

    wb = IncrementalWorkbook(OUTPUT_FILE, columns=COLUMNS)
    done_keys = wb.done_keys(["City", "Locality", "Brand Searched"])
    if done_keys:
        print(f"📂 Resuming — {len(done_keys)} (locality, brand) pairs already saved.", flush=True)

    driver = create_driver()
    total = len(target_localities)
    i = 0
    retries = 0

    try:
        while i < total:
            loc = target_localities[i]
            locality, city, price = loc['locality'], loc['city'], loc['price']

            brands_todo = [b for b in BRANDS if f"{city}|{locality}|{b}" not in done_keys]
            if not brands_todo:
                print(f"\n⏭️  [{i+1}/{total}] SKIP {locality}, {city} (all done)", flush=True)
                i += 1
                continue

            if retries == 0 and should_restart_driver(i, restart_every=25):
                print(f"\n🔄 Restarting browser at locality {i+1} to keep memory healthy...", flush=True)
                try: driver.quit()
                except: pass
                driver = create_driver()

            print(f"\n{'='*65}", flush=True)
            print(f"[{i+1}/{total}] {locality}, {city}  (Rs.{price:,.0f}/sqft)", flush=True)
            print(f"{'='*65}", flush=True)

            try:
                ok = set_location(driver, locality, city)
                if not ok:
                    for b in brands_todo:
                        wb.append_row(not_available_row(city, locality, b, "Location Error"))
                        done_keys.add(f"{city}|{locality}|{b}")
                else:
                    for brand in brands_todo:
                        print(f"\n  🛒 Searching: {brand}", flush=True)
                        prods = scrape_brand(driver, brand, locality, city)
                        if not prods:
                            wb.append_row(not_available_row(city, locality, brand))
                        else:
                            for p in prods: wb.append_row(p)
                        done_keys.add(f"{city}|{locality}|{brand}")

                wb.save()
                print(f"\n  💾 Saved (locality {i+1}/{total})", flush=True)
                i += 1
                retries = 0

            except Exception as e:
                if is_dead_session_error(e) and retries < 2:
                    retries += 1
                    print(f"\n🔁 Browser session died ({str(e)[:60]}) — restarting and retrying "
                          f"{locality}, {city} (attempt {retries+1})...", flush=True)
                    try: driver.quit()
                    except: pass
                    driver = create_driver()
                    continue  # retry same i (including any brands within it not yet done)
                elif is_dead_session_error(e):
                    print(f"\n⚠️  {locality}, {city} failed after {retries} restarts — marking error and moving on.", flush=True)
                    remaining = [b for b in brands_todo if f"{city}|{locality}|{b}" not in done_keys]
                    for b in remaining:
                        wb.append_row(not_available_row(city, locality, b, "Location Error"))
                        done_keys.add(f"{city}|{locality}|{b}")
                    wb.save()
                    i += 1
                    retries = 0
                else:
                    print(f"\n❌ Unexpected error on {locality}, {city}: {str(e)[:100]}", flush=True)
                    remaining = [b for b in brands_todo if f"{city}|{locality}|{b}" not in done_keys]
                    for b in remaining:
                        wb.append_row(not_available_row(city, locality, b, "Location Error"))
                        done_keys.add(f"{city}|{locality}|{b}")
                    wb.save()
                    i += 1
                    retries = 0

            jittered_sleep(1.0, jitter_s=1.5)

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user.", flush=True)
    finally:
        wb.save()
        print(f"\n✅ Final save → {OUTPUT_FILE}", flush=True)
        try: driver.quit()
        except: pass

    print("\n" + "="*65, flush=True)
    print("  SCRAPING COMPLETE!", flush=True)
    print("="*65, flush=True)

if __name__ == "__main__":
    main()
