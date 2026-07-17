"""
Blinkit Goat Life Brand Scraper
Scrapes Goat Life product availability, pricing, and ratings across
Top 50 localities (by residential property price = spending power)
in each of the 10 cities.

Output: scraper/output/blinkit_goatlife_data.xlsx
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from _reliability import (
    IncrementalWorkbook, defeat_visibility_throttling, dismiss_blinkit_interstitials,
    is_dead_session_error, jittered_sleep, keep_window_unminimized,
    should_restart_driver, wait_for_manual_unblock,
)

# ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
MAGICBRICKS_FILE = ROOT / "data" / "magicbricks_combined.xlsx"
OUTPUT_FILE      = ROOT / "scraper" / "output" / "blinkit_goatlife_data.xlsx"
TOP_N            = 50

BRAND = "Goat Life"

COLUMNS = ["City", "Locality", "Search Term", "Rank", "Product Name",
           "Pack Size", "Selling Price", "MRP", "Discount %", "Stock Left",
           "Rating", "Sponsored", "Serviceable"]

# ─────────────────────────────────────────────
def extract_buy_price(price_str):
    if pd.isna(price_str) or str(price_str).strip() in ('N/A','nan',''): return 0
    m = re.search(r'Buy Rs\.\s*([\d,]+)\s*-\s*Rs\.\s*([\d,]+)', str(price_str))
    if m:
        return (int(m.group(1).replace(',','')) + int(m.group(2).replace(',',''))) / 2
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

# ─────────────────────────────────────────────
def set_location(driver, locality, city):
    search_query = f"{locality}, {city}"
    print(f"  📍 Setting location → {search_query}", flush=True)

    for attempt in range(3):
        try:
            driver.get("https://blinkit.com/")
            time.sleep(5)
            if not wait_for_manual_unblock(driver, beep):
                print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

            dismiss_blinkit_interstitials(driver)

            input_box = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='search delivery location']"))
            )

            driver.execute_script("""
                arguments[0].value = '';
                arguments[0].focus();
            """, input_box)
            time.sleep(0.5)

            actions = ActionChains(driver)
            actions.click(input_box)
            actions.send_keys(search_query)
            actions.perform()
            time.sleep(3.5)

            suggestion_clicked = False
            suggestion_text = "None found"

            modal_xpaths = [
                "//div[contains(@class,'LocationDropDown')]",
                "//div[contains(@class,'location__shake-container')]",
                "//div[contains(@class,'LocationModal')]",
            ]

            modal = None
            for mx in modal_xpaths:
                try:
                    modal = driver.find_element(By.XPATH, mx)
                    if modal: break
                except: pass

            if modal:
                child_divs = modal.find_elements(By.XPATH, ".//div")
                location_divs = []
                for d in child_divs:
                    try:
                        if not d.is_displayed(): continue
                        text = d.text.strip()
                        if (len(text) > 5 and
                            any(kw in text for kw in [city, 'India', 'Maharashtra', 'Delhi',
                                                       'Karnataka', 'Punjab', 'Uttar Pradesh',
                                                       'Haryana', 'Tamil Nadu', 'West Bengal',
                                                       'Telangana', locality[:5]]) and
                            'Please provide' not in text and
                            'Detect my location' not in text and
                            'search delivery' not in text.lower()):
                            location_divs.append((d, text))
                    except: pass

                if location_divs:
                    first_div, first_text = location_divs[0]
                    suggestion_text = first_text.split('\n')[0][:60]
                    driver.execute_script("arguments[0].click();", first_div)
                    suggestion_clicked = True

            if not suggestion_clicked:
                try:
                    time.sleep(1)
                    candidates = driver.find_elements(By.XPATH,
                        f"//*[contains(text(),'{locality[:8]}') and not(contains(@class,'Footer')) and not(contains(@class,'Input'))]")
                    visible = [c for c in candidates if c.is_displayed() and c.text.strip() and
                               len(c.text.strip()) > 10]
                    if visible:
                        suggestion_text = visible[0].text.split('\n')[0][:60]
                        driver.execute_script("arguments[0].click();", visible[0])
                        suggestion_clicked = True
                except: pass

            if not suggestion_clicked:
                input_box = driver.find_element(By.XPATH, "//input[@placeholder='search delivery location']")
                input_box.send_keys(Keys.RETURN)
                suggestion_text = "(pressed Enter)"

            print(f"  ✅ Selected: {suggestion_text}", flush=True)
            time.sleep(4)
            return True

        except Exception as e:
            if is_dead_session_error(e):
                raise  # let the outer loop restart the driver and retry the locality
            print(f"  ❌ Attempt {attempt+1}: {str(e)[:100]}", flush=True)
            time.sleep(3)

    return False

# ─────────────────────────────────────────────
def is_serviceable(driver):
    pt = driver.page_source.lower()
    return not any(p in pt for p in [
        "we don't deliver here", "not serviceable", "outside our delivery",
        "not available in your area", "coming soon to your area"
    ])

def has_sponsored_badge(img_srcs):
    """True if any image src matches Blinkit's sponsored/"Ad" badge asset.
    Blinkit renders that badge as an absolutely-positioned image overlay
    (assets/ui/ad_without_bg.png) that sits outside the card's text flow --
    it never appears in .text/innerText, so text-based parsing can't see
    it. Verified against a live blinkit.com search results page
    (2026-07-16): the badge image was present on a sponsored card and
    absent on every plain organic card checked."""
    return any("assets/ui/ad" in src for src in img_srcs if src)

# ─────────────────────────────────────────────
def scrape_brand(driver, brand, locality, city):
    products = []
    try:
        driver.get(f"https://blinkit.com/s/?q={brand.replace(' ','%20')}")
        time.sleep(3)
        if not wait_for_manual_unblock(driver, beep):
            print("  ⚠️  Still blocked after waiting — continuing anyway.", flush=True)

        def _cards_or_no_results(d):
            no_results = any(x in d.page_source.lower() for x in
                              ["no products", "0 results", "couldn't find", "no result"])
            has_cards = bool(d.find_elements(By.XPATH, "//div[text()='ADD' or text()='Add']"))
            return no_results or has_cards

        # The product grid renders async after the search XHR completes -- a
        # fixed sleep here (the old approach) raced that render and, whenever
        # it lost, silently recorded "0 cards" for a brand that was actually
        # present (confirmed live in blinkit_oats.py: same brand flipped
        # between 0 and 36 cards across adjacent, back-to-back localities
        # with nothing else different). Poll instead of guessing a fixed delay.
        try:
            WebDriverWait(driver, 10).until(_cards_or_no_results)
        except Exception:
            pass

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

        # The scroll can lazy-load additional cards past what was already
        # rendered -- give that a shorter second chance rather than assuming
        # the pre-scroll count is final.
        try:
            WebDriverWait(driver, 4).until(
                lambda d: len(d.find_elements(By.XPATH, "//div[text()='ADD' or text()='Add']")) > 0
            )
        except Exception:
            pass

        page_lower = driver.page_source.lower()
        if any(x in page_lower for x in ["no products","0 results","couldn't find","no result"]):
            print(f"    ⚪ No results for '{brand}'", flush=True)
            return products

        cards = []
        try:
            add_buttons = driver.find_elements(By.XPATH, "//div[text()='ADD' or text()='Add']")
            for btn in add_buttons:
                try:
                    parent = btn.find_element(By.XPATH, "./../../..")
                    if '₹' in parent.text:
                        cards.append(parent)
                except: pass
        except: pass

        print(f"    🔍 '{brand}': {len(cards)} card(s) found on page", flush=True)

        for rank, card in enumerate(cards[:15], 1):
            try:
                ct = card.text
                if not ct or len(ct) < 5: continue

                lines = [l.strip() for l in ct.split('\n') if l.strip() and len(l.strip()) > 3]
                name = lines[0] if lines else "Unknown"

                # No keyword filtering - capturing first 15 results regardless of brand
                pack_size = "N/A"
                m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g\b|ml|L\b|gm)\b', ct, re.I)
                if m: pack_size = f"{m.group(1)} {m.group(2)}"

                prices = sorted(set([int(x.replace(',','')) for x in re.findall(r'₹\s*(\d+(?:,\d+)?)', ct)]))
                sp = mrp = disc = "N/A"
                if len(prices) >= 2:
                    sp, mrp = f"₹{prices[0]}", f"₹{prices[-1]}"
                    d = round((1 - prices[0]/prices[-1])*100) if prices[-1] > 0 else 0
                    disc = f"{d}%"
                elif prices: sp = mrp = f"₹{prices[0]}"
                dm = re.search(r'(\d+)%\s*OFF', ct, re.I)
                if dm: disc = f"{dm.group(1)}%"

                stock = "N/A"
                sm = re.search(r'(\d+)\s+left|only\s+(\d+)', ct, re.I)
                if sm: stock = f"{(sm.group(1) or sm.group(2))} left"
                elif "out of stock" in ct.lower(): stock = "Out of Stock"

                rating = "N/A"
                rm = re.search(r'(\d\.\d)\s*\(', ct)
                if rm and 1.0 <= float(rm.group(1)) <= 5.0: rating = rm.group(1)

                img_srcs = [img.get_attribute("src") for img in card.find_elements(By.TAG_NAME, "img")]
                sponsored = "True" if has_sponsored_badge(img_srcs) else "False"

                products.append({
                    "City": city, "Locality": locality, "Search Term": brand, "Rank": rank,
                    "Product Name": name, "Pack Size": pack_size,
                    "Selling Price": sp, "MRP": mrp, "Discount %": disc,
                    "Stock Left": stock, "Rating": rating, "Sponsored": sponsored, "Serviceable": "Yes",
                })
                print(f"    ✅ [Rank {rank}] {name[:31]:<31} {pack_size:<8} {sp} (MRP:{mrp})", flush=True)

            except: pass

    except Exception as e:
        if is_dead_session_error(e):
            raise  # let the outer loop restart the driver and retry the locality
        print(f"    ❌ Error: {str(e)[:80]}", flush=True)
    return products

# ─────────────────────────────────────────────
def not_available_row(city, locality, reason="Not Available"):
    return {
        "City": city, "Locality": locality, "Search Term": BRAND, "Rank": "N/A",
        "Product Name": reason, "Pack Size": "N/A", "Selling Price": "N/A",
        "MRP": "N/A", "Discount %": "N/A", "Stock Left": "N/A", "Rating": "N/A",
        "Sponsored": "N/A", "Serviceable": "Yes" if reason == "Not Available" else "No",
    }

# ─────────────────────────────────────────────
def main():
    print("="*65, flush=True)
    print("  BLINKIT — GOAT LIFE SCRAPER", flush=True)
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

    print(f"\n📋 Localities: {len(target_localities)} | Brand: {BRAND} | Est. searches: {len(target_localities)}", flush=True)

    wb = IncrementalWorkbook(OUTPUT_FILE, columns=COLUMNS)
    done_keys = wb.done_keys(["City", "Locality"])
    if done_keys:
        print(f"📂 Resuming — {len(done_keys)} localities already saved.", flush=True)

    driver = create_driver()
    total = len(target_localities)
    i = 0
    retries = 0

    try:
        while i < total:
            loc = target_localities[i]
            locality, city, price = loc['locality'], loc['city'], loc['price']

            if f"{city}|{locality}" in done_keys:
                print(f"\n⏭️  [{i+1}/{total}] SKIP {locality}, {city} (already done)", flush=True)
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
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                elif not is_serviceable(driver):
                    print(f"  🚫 NOT SERVICEABLE in {locality}, {city}", flush=True)
                    wb.append_row(not_available_row(city, locality, "Not Serviceable"))
                else:
                    print(f"\n  🛒 Searching: {BRAND}", flush=True)
                    prods = scrape_brand(driver, BRAND, locality, city)
                    if not prods:
                        wb.append_row(not_available_row(city, locality))
                    else:
                        for p in prods: wb.append_row(p)

                done_keys.add(f"{city}|{locality}")
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
                    continue  # retry same i
                elif is_dead_session_error(e):
                    print(f"\n⚠️  {locality}, {city} failed after {retries} restarts — marking error and moving on.", flush=True)
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                    done_keys.add(f"{city}|{locality}")
                    wb.save()
                    i += 1
                    retries = 0
                else:
                    print(f"\n❌ Unexpected error on {locality}, {city}: {str(e)[:100]}", flush=True)
                    wb.append_row(not_available_row(city, locality, "Location Error"))
                    done_keys.add(f"{city}|{locality}")
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
