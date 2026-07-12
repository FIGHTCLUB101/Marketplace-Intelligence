import sys
try:
    import setuptools._distutils
    import setuptools._distutils.version
    sys.modules['distutils'] = setuptools._distutils
    sys.modules['distutils.version'] = setuptools._distutils.version
except ImportError:
    pass

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import time
import pandas as pd
import random
import os
import winsound
import re
from bs4 import BeautifulSoup
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def create_driver():
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=149)
    driver.maximize_window()
    return driver

def check_captcha(driver, city, wait_time=0):
    while True:
        html = driver.page_source.lower()
        if "access denied" in html or "captcha" in html or "attention required" in html or "are you human" in html:
            if wait_time == 0:
                print(f"CAPTCHA/Block detected on {city}. Please solve it in the browser window!", flush=True)
                winsound.Beep(1000, 1000)
                winsound.Beep(1000, 1000)
            time.sleep(3)
            wait_time += 3
            if wait_time > 180:
                print("Waited 3 minutes for CAPTCHA. Skipping...", flush=True)
                break
        else:
            break

def fetch_magicbricks():
    cities = [
        "mumbai", "bangalore", "hyderabad", "kolkata", "lucknow"
    ]

    driver = create_driver()
    results = []
    out_path = str(ROOT / "data" / "magicbricks_combined.xlsx")

    if os.path.exists(out_path):
        try:
            df_exist = pd.read_excel(out_path)
            results = df_exist.to_dict('records')
            print(f"Loaded {len(results)} existing records.", flush=True)
        except Exception:
            pass

    processed_urls = set([r.get("URL") for r in results if r.get("URL")])

    for city in cities:
        print(f"Starting scraping for city: {city}", flush=True)
        city_url_name = city.capitalize()
        if city == "gurugram":
            city_url_name = "Gurgaon"
        elif city == "new-delhi":
            city_url_name = "New-Delhi"

        localities_url = f"https://www.magicbricks.com/localities-in-{city_url_name}"

        try:
            driver.get(localities_url)
            time.sleep(3)
            check_captcha(driver, city)

            # --- STEP 1: Try scrolling first (works for Gurugram, New Delhi, Pune, etc.) ---
            last_count = 0
            retries = 0
            while retries < 5:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                driver.execute_script("window.scrollBy(0, -300);")
                time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

                elements = driver.find_elements(By.XPATH, "//a[contains(@href, '-Overview')]")

                if len(elements) > 300:
                    break

                if len(elements) == last_count:
                    retries += 1
                else:
                    retries = 0
                    last_count = len(elements)

            # Collect all Overview links from the current page
            def collect_overview_links(drv):
                links = []
                for el in drv.find_elements(By.TAG_NAME, "a"):
                    try:
                        href = el.get_attribute("href")
                        if href and "-Overview" in href:
                            links.append(href)
                    except:
                        pass
                return links

            all_overview_urls = collect_overview_links(driver)

            # Deduplicate while preserving order
            unique_urls = []
            seen = set()
            for url in all_overview_urls:
                if url not in seen:
                    unique_urls.append(url)
                    seen.add(url)

            # --- STEP 2: If scrolling didn't find enough, use PAGINATION ---
            # Some cities (Mumbai, Bangalore, Hyderabad, Kolkata, Lucknow) use paginated pages
            # with 20 localities per page. We need to click through pages to get 100.
            if len(unique_urls) < 100:
                print(f"  Scrolling found only {len(unique_urls)} localities. Checking pagination...", flush=True)

                # Pages are 1-indexed on Magicbricks: ?page=1, ?page=2, etc.
                # Page 1 is the default page we already loaded. We need pages 2-5 for the next 80.
                for page_num in range(2, 8):  # Try up to page 7 to be safe
                    if len(unique_urls) >= 100:
                        break

                    page_url = f"{localities_url}?page={page_num}"
                    print(f"  Loading page {page_num}: {page_url}", flush=True)

                    try:
                        driver.get(page_url)
                        time.sleep(2)
                        check_captcha(driver, city)

                        # Scroll to load all content on this page
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)

                        page_links = collect_overview_links(driver)
                        new_count = 0
                        for url in page_links:
                            if url not in seen:
                                unique_urls.append(url)
                                seen.add(url)
                                new_count += 1

                        print(f"  Page {page_num}: found {new_count} new localities (total: {len(unique_urls)})", flush=True)

                        if new_count == 0:
                            print(f"  No new localities on page {page_num}, stopping pagination.", flush=True)
                            break
                    except Exception as e:
                        print(f"  Error loading page {page_num}: {e}", flush=True)
                        break

            # Strictly limit to the Top 100
            overview_urls = unique_urls[:100]
            print(f"Slicing the Top {len(overview_urls)} localities for {city}")

            for url in overview_urls:
                if url in processed_urls:
                    continue

                print(f"Scraping locality: {url}")
                driver.get(url)
                time.sleep(random.uniform(2.5, 4.0))
                check_captcha(driver, city)

                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)

                try:
                    read_more_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'Read more') or contains(text(), 'Read More')]")
                    for btn in read_more_btns:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                except:
                    pass

                try:
                    more_btns = driver.find_elements(By.XPATH, "//*[contains(text(), ' more')]")
                    for btn in more_btns:
                        if "+" in btn.text:
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(0.5)
                except:
                    pass

                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                area_name = url.split('/')[-1].replace('-in-', ', ').replace('-Overview', '').replace('-', ' ')

                data = {
                    "URL": url,
                    "AREA": area_name,
                    "ADDRESS": city.replace('-', ' ').title(),
                    "PINCODE": "N/A",
                    "price range(for residential, office space, shop)": "N/A",
                    "Physical infrastructure": "N/A",
                    "Locality introduction and neighbourhood": "N/A",
                    "Social & retail infra": "N/A",
                    "Nearby employment hubs": "N/A",
                    "Educational Institute": "N/A",
                    "Transportation Hub": "N/A",
                    "Shopping Centre": "N/A",
                    "Hospital": "N/A",
                    "Nearby Localities": "N/A",
                    "Tourist Spot": "N/A",
                    "Commercial Hub": "N/A"
                }

                match = re.search(r'\b\d{6}\b', soup.get_text())
                if match:
                    data["PINCODE"] = match.group(0)

                price_block = soup.find('div', class_=re.compile(r'pricerangeblocks', re.I))
                if price_block:
                    prices = []
                    for card in price_block.find_all('div', class_=re.compile(r'pricerangeblocks__card', re.I)):
                        title = card.find('div', class_=re.compile(r'card__title', re.I))
                        if title:
                            title_text = title.get_text(strip=True)
                            card_prices = []
                            for p in card.find_all('div', class_=re.compile(r'card__price', re.I)):
                                text = p.get_text(separator=' ', strip=True).replace('\u20b9', 'Rs.')
                                # Clean up double spaces
                                text = re.sub(r'\s+', ' ', text)
                                card_prices.append(text)
                            if card_prices:
                                prices.append(f"{title_text}: " + " | ".join(card_prices))
                    if prices:
                        data["price range(for residential, office space, shop)"] = " || ".join(prices)

                def get_text_after_header(header_name):
                    text_node = soup.find(string=re.compile(r'^\s*' + header_name, re.I))
                    if text_node:
                        parent = text_node.parent
                        sibling = parent.find_next_sibling()
                        if sibling:
                            return sibling.get_text(separator=' ', strip=True)
                        try:
                            return parent.parent.find_next_sibling().get_text(separator=' ', strip=True)
                        except:
                            pass
                    return "N/A"

                data["Locality introduction and neighbourhood"] = get_text_after_header("Locality introduction and neighbourhood")
                data["Physical infrastructure"] = get_text_after_header("Physical infrastructure")
                data["Social & retail infra"] = get_text_after_header("Social & retail infra")
                data["Nearby employment hubs"] = get_text_after_header("Nearby employment hubs")

                def extract_neighbourhood_list(category):
                    text_node = soup.find(string=re.compile(r'^\s*' + category, re.I))
                    if text_node:
                        # Look for the outer card__inner container (NOT card__head which also matches 'card')
                        container = text_node.find_parent('div', class_=re.compile(r'card__inner', re.I))
                        if not container:
                            container = text_node.find_parent('div', class_=re.compile(r'card__body', re.I))
                        if not container:
                            container = text_node.parent.parent.parent

                        if container:
                            items = []
                            for item in container.find_all('div', class_=re.compile(r'body__item', re.I)):
                                text = item.get_text(strip=True)
                                if text and text.lower() != category.lower() and 'more' not in text.lower() and len(text) > 3:
                                    items.append(text)

                            if items:
                                seen = set()
                                unique_items = [x for x in items if not (x in seen or seen.add(x))]
                                return ", ".join(unique_items)
                    return "N/A"

                data["Educational Institute"] = extract_neighbourhood_list("Educational Institute")
                data["Transportation Hub"] = extract_neighbourhood_list("Transportation Hub")
                data["Shopping Centre"] = extract_neighbourhood_list("Shopping Centre")
                data["Hospital"] = extract_neighbourhood_list("Hospital")
                data["Nearby Localities"] = extract_neighbourhood_list("Nearby Localities")
                data["Tourist Spot"] = extract_neighbourhood_list("Tourist Spot")
                data["Commercial Hub"] = extract_neighbourhood_list("Commercial Hub")

                results.append(data)
                processed_urls.add(url)

                print("\n" + "="*60)
                print(f"✓ SUCCESSFULLY EXTRACTED: {data['AREA']}")
                print(f"  Prices:  {data['price range(for residential, office space, shop)'][:80]}...")
                print(f"  Schools: {data['Educational Institute'][:80]}...")
                print(f"  Hospitals: {data['Hospital'][:80]}...")
                print("="*60 + "\n", flush=True)

                df = pd.DataFrame(results)
                columns_order = [
                    "AREA", "ADDRESS", "PINCODE", "price range(for residential, office space, shop)",
                    "Physical infrastructure", "Locality introduction and neighbourhood",
                    "Social & retail infra", "Nearby employment hubs",
                    "Educational Institute", "Transportation Hub", "Shopping Centre",
                    "Hospital", "Nearby Localities", "Tourist Spot", "Commercial Hub"
                ]
                df = df[[c for c in columns_order if c in df.columns] + [c for c in df.columns if c not in columns_order]]

                try:
                    df.to_excel(out_path, index=False)
                except PermissionError:
                    print(f"\n⚠️ WARNING: Please close the Excel file! Cannot save {data['AREA']} because Excel is locking the file. It will be saved when you close Excel and the next locality is extracted.\n", flush=True)

        except WebDriverException as e:
            print(f"Browser crashed. Restarting... Error: {e}", flush=True)
            try:
                driver.quit()
            except:
                pass
            driver = create_driver()
            time.sleep(3)
        except Exception as e:
            print(f"Error processing {city}: {e}", flush=True)

    print(f"Total Magicbricks localities scraped: {len(results)}", flush=True)
    try:
        driver.quit()
    except:
        pass
    print("DONE! File saved to:", out_path)

if __name__ == '__main__':
    fetch_magicbricks()
