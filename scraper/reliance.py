import sys
try:
    import setuptools._distutils
    import setuptools._distutils.version
    sys.modules['distutils'] = setuptools._distutils
    sys.modules['distutils.version'] = setuptools._distutils.version
except ImportError:
    pass

import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
from bs4 import BeautifulSoup
import time
import re
import pandas as pd
import random
import os
import winsound
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def create_driver():
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=149)
    driver.maximize_window()
    return driver

def fetch_reliance_stores():
    city_urls = [
        ("Gurugram", "https://stores.reliancesmartbazaar.com/location/haryana/gurgaon"),
        ("New Delhi", "https://stores.reliancesmartbazaar.com/location/delhi/new-delhi"),
        ("Pune", "https://stores.reliancesmartbazaar.com/location/maharashtra/pune"),
        ("Mumbai", "https://stores.reliancesmartbazaar.com/location/maharashtra/mumbai"),
        ("Bangalore", "https://stores.reliancesmartbazaar.com/location/karnataka/bangalore"),
        ("Hyderabad", "https://stores.reliancesmartbazaar.com/location/telangana/hyderabad"),
        ("Chennai", "https://stores.reliancesmartbazaar.com/location/tamil-nadu/chennai"),
        ("Kolkata", "https://stores.reliancesmartbazaar.com/location/west-bengal/kolkata"),
        ("Chandigarh", "https://stores.reliancesmartbazaar.com/location/chandigarh/chandigarh"),
        ("Lucknow", "https://stores.reliancesmartbazaar.com/location/uttar-pradesh/lucknow")
    ]

    driver = create_driver()
    results = []
    out_path = str(ROOT / "data" / "reliance_smart_bazaar_stores.xlsx")

    if os.path.exists(out_path):
        try:
            df_exist = pd.read_excel(out_path)
            results = df_exist.to_dict('records')
            print(f"Loaded {len(results)} existing records.", flush=True)
        except Exception:
            pass

    for city, base_url in city_urls:
        print(f"Starting scraping for city: {city}", flush=True)
        for page in range(1, 51): # Check up to 50 pages per city
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}?page={page}"

            success = False
            retries = 3
            while retries > 0 and not success:
                try:
                    driver.get(url)
                    time.sleep(random.uniform(2.5, 4.0))

                    wait_time = 0
                    while True:
                        html = driver.page_source
                        soup = BeautifulSoup(html, 'html.parser')

                        # Look for store elements or "403 Forbidden"
                        if "403 Forbidden" in html or "You don't have permission" in html or "Cloudflare" in html or "Attention Required" in html:
                            if wait_time == 0:
                                print(f"CAPTCHA detected on {city} page {page}. Please solve it in the browser window!", flush=True)
                                winsound.Beep(1000, 1000)
                                winsound.Beep(1000, 1000)

                            time.sleep(3)
                            wait_time += 3
                            if wait_time > 120:
                                print("Waited 2 minutes for CAPTCHA. Skipping...", flush=True)
                                break
                        else:
                            break # Block bypassed or no block!

                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    store_boxes = soup.find_all('div', class_='store-info-box')

                    found_on_page = 0
                    for box in store_boxes:
                        name_el = box.find('li', class_='outlet-name')
                        address_el = box.find('li', class_='outlet-address')

                        if name_el and address_el:
                            name_text = name_el.text.strip()
                            addr_text = address_el.find('div', class_='info-text')
                            if addr_text:
                                raw_addr = addr_text.get_text(separator=' ', strip=True)
                                # Clean up the address a bit
                                clean_addr = re.sub(r'\s+', ' ', raw_addr)

                                pincode = ''
                                match = re.search(r'\b\d{6}\b', clean_addr)
                                if match:
                                    pincode = match.group(0)

                                if not any(r['Store Name'] == name_text and r['Address'] == clean_addr for r in results):
                                    results.append({
                                        'City': city,
                                        'Store Name': name_text,
                                        'Address': clean_addr,
                                        'Pincode': pincode
                                    })
                                found_on_page += 1

                    print(f"City: {city}, Page: {page}, Found: {found_on_page}", flush=True)

                    if found_on_page > 0:
                        df = pd.DataFrame(results)
                        df.drop_duplicates(subset=['Store Name', 'Address'], inplace=True)
                        df.to_excel(out_path, index=False)

                    if found_on_page == 0:
                        print(f"No more stores found on page {page} for {city}. Ending pagination.", flush=True)
                        success = True
                        break

                    success = True

                except WebDriverException as e:
                    print(f"Browser crashed. Restarting... Error: {e}", flush=True)
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = create_driver()
                    retries -= 1
                    time.sleep(3)
                except Exception as e:
                    print(f"Error: {e}", flush=True)
                    retries -= 1
                    time.sleep(3)

            if not success or found_on_page == 0:
                break

    print(f"Total Reliance Smart Bazaar stores scraped: {len(results)}", flush=True)
    try:
        driver.quit()
    except:
        pass
    print("DONE! File saved to:", out_path)

if __name__ == '__main__':
    fetch_reliance_stores()
