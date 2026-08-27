import asyncio
import csv
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Import local modules
import config_sk
import locations_sk

# Set console output encoding to UTF-8 to prevent print errors
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    scraped_urls = set()
    if os.path.exists(config_sk.OUTPUT_CSV):
        try:
            with open(config_sk.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}")
    return scraped_urls

def is_slovakia_address(address):
    """Verifies if an address is in Slovakia by checking for country name, cities, or postcode patterns."""
    if not address:
        return False
    addr_lower = address.lower()
    if "slovakia" in addr_lower or "slovensko" in addr_lower or "slovenská" in addr_lower or "slovenskej" in addr_lower or "sr" in addr_lower or "slovak republic" in addr_lower:
        return True
    
    # Slovak cities
    sk_cities = [
        "bratislava", "kosice", "košice", "presov", "prešov", "zilina", "žilina", "nitra", 
        "banska bystrica", "banská bystrica", "trnava", "martin", "trencin", "trenčín", 
        "poprad", "prievidza", "zvolen", "povazska bystrica", "považská bystrica", 
        "nove zamky", "nové zámky", "michalovce", "spisska nova ves", "spišská nová ves", 
        "komarno", "komárno", "levice", "humenne", "humenné", "bardejov", "lipy", "ruzomberok", 
        "ružomberok", "piestany", "piešťany", "miasto", "lucenec", "lučenec"
    ]
    if any(city in addr_lower for city in sk_cities):
        return True
        
    # Slovakia zip code check: 3 digits + space/dash + 2 digits (e.g. 811 07)
    if re.search(r'\b\d{3}\s?\d{2}\b', address):
        return True
        
    return False

def append_to_csv(row_dict):
    file_exists = os.path.isfile(config_sk.OUTPUT_CSV)
    try:
        with open(config_sk.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

import json

PROGRESS_FILE = os.path.join(os.path.dirname(config_sk.OUTPUT_CSV), "scraping_progress_sk.json")

def load_completed_scans():
    completed = set()
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
            
    if os.path.exists(config_sk.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...")
            completed_list = []
            with open(config_sk.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    kw = row.get('Search_Query', '')
                    raw_kw = ""
                    if kw:
                        for original_kw in config_sk.KEYWORDS:
                            if original_kw in kw:
                                raw_kw = original_kw
                                break
                    if not raw_kw:
                        raw_kw = config_sk.KEYWORDS[0]
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), raw_kw.lower())
                        if pair not in completed:
                            completed.add(pair)
                            completed_list.append([loc_name.strip(), state.strip(), raw_kw])
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
            print(f"[+] Loaded {len(completed)} completed locations from CSV.")
        except Exception as e:
            print(f"[-] Error initializing progress: {e}")
            
    return completed

def save_completed_scan(loc_name, state, keyword):
    completed_list = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed_list = data.get("completed", [])
        except:
            pass
            
    pair = [loc_name, state, keyword]
    if pair not in completed_list:
        completed_list.append(pair)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Error saving progress: {e}")

async def handle_captcha(page):
    is_captcha = False
    title = await page.title()
    page_content = await page.content()
    
    if (
        "unusual traffic" in title.lower() or 
        "captcha" in title.lower() or
        await page.locator("iframe[src*='recaptcha']").count() > 0 or 
        await page.locator("#captcha-form").count() > 0 or
        "systems have detected unusual traffic" in page_content
    ):
        is_captcha = True
        
    if is_captcha:
        print("\n" + "="*60)
        print("[!] IP BLOCK / CAPTCHA DETECTED! Google is blocking automated access.")
        print("[!] Stopping the scraper immediately to protect your IP address...")
        print("[!] You should rotate your VPN location before restarting the scraper.")
        print("="*60 + "\n")
        sys.stdout.write('\a')
        sys.stdout.flush()
        sys.exit(1)

async def bypass_consent_screen(page):
    try:
        consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("Agree"), button:has-text("I agree"), button:has-text("Accept"), button:has-text("Súhlasím"), button:has-text("Prijať všetko"), button:has-text("Prijať")')
        if await consent_buttons.count() > 0:
            print("[*] Google Consent / Cookie banner detected. Bypassing...")
            await consent_buttons.first.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def scroll_feed(page, max_scrolls=20):
    feed_selector = config_sk.SELECTORS["results_container"]
    try:
        await page.wait_for_selector(feed_selector, timeout=8000)
    except Exception:
        return
        
    feed = page.locator(feed_selector)
    if await feed.count() == 0:
        return
        
    print("[*] Scrolling the results panel to load listings...")
    scrolls = 0
    last_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
    
    while scrolls < max_scrolls:
        await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
        await page.wait_for_timeout(random.uniform(400, 800))
        
        inner_text = await feed.inner_text()
        if any(x in inner_text.lower() for x in ["reached the end of the list", "koniec zoznamu", "dosiahli ste koniec", "žiadne ďalšie výsledky"]):
            print("[*] Reached the end of the results list.")
            break
            
        new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
        if new_height == last_height:
            await page.wait_for_timeout(500)
            await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
            new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
            if new_height == last_height:
                break
                
        last_height = new_height
        scrolls += 1

def extract_coords_from_url(url):
    if not url:
        return None
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

def parse_slovakia_address(address):
    if not address:
        return None, None, None
        
    addr = address.replace("Slovakia", "").replace("slovakia", "").replace("Slovensko", "").replace("slovensko", "").strip()
    
    postcode = ""
    postcode_match = re.search(r'\b\d{3}\s?\d{2}\b', address)
    if postcode_match:
        postcode = postcode_match.group(0)
    else:
        postcode_match = re.search(r'\b\d{5}\b', address)
        if postcode_match:
            postcode = postcode_match.group(0)
            
    city = ""
    regions = ["Bratislava", "Košice", "Prešov", "Žilina", "Nitra", "Banská Bystrica", "Trnava", "Trenčín"]
    for r in regions:
        if r.lower() in address.lower():
            city = r
            break
            
    state = city if city else "Slovakia"
    suburb = city if city else "SK"
    
    return suburb, state, postcode

async def extract_details(page, url, search_query, loc_info):
    sel = config_sk.SELECTORS
    
    name = ""
    name_loc = page.locator(sel["business_name"])
    if await name_loc.count() > 0:
        name = await name_loc.first.inner_text()
        name = name.strip()
        
    if not name:
        return None
        
    website = ""
    web_loc = page.locator(sel["website"])
    if await web_loc.count() > 0:
        website = await web_loc.first.get_attribute("href")
        if website:
            website = website.strip()
            
    phone = ""
    phone_loc = page.locator(sel["phone"])
    if await phone_loc.count() > 0:
        phone_attr = await phone_loc.first.get_attribute("data-item-id")
        if phone_attr:
            phone = phone_attr.replace("phone:tel:", "").strip()
            
    address = ""
    addr_loc = page.locator(sel["address"])
    if await addr_loc.count() > 0:
        addr_label = await addr_loc.first.get_attribute("aria-label")
        if addr_label:
            address = addr_label
            for prefix in ["Address:", "Adresa:", "Adrese:", "地址:", "地址："]:
                address = address.replace(prefix, "")
            address = address.strip()
        else:
            address = await addr_loc.first.inner_text()
            address = address.strip()
            
    if not is_slovakia_address(address):
        print(f"    [-] Skipping: Address '{address}' is not in Slovakia.")
        return None
        
    actual_lat, actual_lng = loc_info["lat"], loc_info["lng"]
    coords = extract_coords_from_url(url)
    if coords:
        actual_lat, actual_lng = coords
        # Slovakia bounding box check
        if not (47.5 < actual_lat < 50.0) or not (16.5 < actual_lng < 23.0):
            print(f"    [-] Skipping: Coordinates ({actual_lat}, {actual_lng}) are outside Slovakia.")
            return None
            
    actual_suburb, actual_state, postcode = parse_slovakia_address(address)
    if not actual_state:
        actual_suburb = loc_info["name"]
        actual_state = "Slovakia"
        
    rating = ""
    reviews_count = ""
    rating_loc = page.locator('div.F7nice')
    if await rating_loc.count() > 0:
        span_rating = rating_loc.first.locator('span[aria-hidden="true"]')
        if await span_rating.count() > 0:
            rating = await span_rating.first.inner_text()
            rating = rating.strip()
            
        span_reviews = rating_loc.first.locator('span[aria-label*="recenzie"], span[aria-label*="recenzií"], span[aria-label*="review"], span[aria-label*="reviews"]')
        if await span_reviews.count() > 0:
            reviews_text = await span_reviews.first.get_attribute("aria-label")
            if reviews_text:
                match = re.search(r'\d+', reviews_text.replace(" ", "").replace(",", ""))
                if match:
                    reviews_count = match.group()
            else:
                reviews_text = await span_reviews.first.inner_text()
                match = re.search(r'\d+', reviews_text.replace(" ", "").replace(",", ""))
                if match:
                    reviews_count = match.group()
                    
    permanently_closed = "No"
    try:
        closed_loc = page.locator('span:has-text("Permanently closed"), span:has-text("Trvalo zatvorené")')
        if await closed_loc.count() > 0:
            permanently_closed = "Yes"
    except Exception:
        pass

    category = ""
    try:
        category_loc = page.locator(sel["category"])
        if await category_loc.count() > 0:
            category = await category_loc.first.inner_text()
            category = category.strip()
    except Exception:
        pass
        
    ALLOWED_CATEGORIES = set(config_sk.ALLOWED_CATEGORIES)
    if not category or category.strip() not in ALLOWED_CATEGORIES:
        print(f"    [-] Skipping: Category '{category}' is not in Slovakia recruitment tags.")
        return None

    record = {
        "Name": name,
        "Website": website,
        "Phone": phone,
        "Address": address,
        "Rating": rating,
        "Reviews_Count": reviews_count,
        "State": actual_state,
        "Location_Name": actual_suburb,
        "Latitude": actual_lat,
        "Longitude": actual_lng,
        "Search_Query": search_query,
        "URL": url,
        "Permanently_Closed": permanently_closed,
        "Category": category,
    }
    return record

async def process_search(page, keyword, loc_info, scraped_urls):
    search_query = f"{keyword} in {loc_info['name']}, Slovakia"
    print(f"\n[+] Searching: '{search_query}'")
    
    query_encoded = urllib.parse.quote_plus(keyword)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{loc_info['zoom']}z?hl=sk"
    
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception as geo_err:
        print(f"[*] Warning: Geolocation error: {geo_err}")

    max_retries = 3
    navigated = False
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"[*] Navigating (Attempt {attempt}/{max_retries})...")
            await page.goto(search_url, timeout=config_sk.TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            navigated = True
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"[-] Navigation failed: {e}")
                return
            else:
                print(f"[!] Timeout, retrying in 5s... ({e})")
                await asyncio.sleep(5.0)
        
    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url
    
    if "/maps/place/" in current_url:
        print("[*] Redirected to place details.")
        current_place_id = extract_place_id(current_url)
        if current_place_id not in scraped_urls:
            record = await extract_details(page, current_url, search_query, loc_info)
            if record:
                append_to_csv(record)
                scraped_urls.add(current_place_id)
                print(f"    -> SAVED: {record['Name']} | Phone: {record['Phone']} | Web: {record['Website']}")
        return

    link_selector = config_sk.SELECTORS["listing_link"]
    listings_count = await page.locator(link_selector).count()
    
    if listings_count > 0:
        first_item = page.locator(link_selector).first
        try:
            expected_name = await first_item.get_attribute("aria-label")
            await first_item.scroll_into_view_if_needed()
            await first_item.click()
            
            name_matched = False
            for _ in range(15):
                h1_locator = page.locator(config_sk.SELECTORS["business_name"])
                if await h1_locator.count() > 0:
                    current_name = await h1_locator.first.inner_text()
                    current_name = current_name.strip()
                    if expected_name and (expected_name.lower() in current_name.lower() or current_name.lower() in expected_name.lower()):
                        name_matched = True
                        break
                await page.wait_for_timeout(200)
                
            addr_loc = page.locator(config_sk.SELECTORS["address"])
            address = ""
            if await addr_loc.count() > 0:
                addr_label = await addr_loc.first.get_attribute("aria-label")
                address = addr_label
                for prefix in ["Address:", "Adresa:", "Adrese:", "地址:", "地址："]:
                    address = address.replace(prefix, "")
                address = address.strip()
            else:
                address = await addr_loc.first.inner_text()
                address = address.strip()
                
            if address:
                if not is_slovakia_address(address):
                    print(f"[-] First listing is outside Slovakia ('{address}'). Skipping location.")
                    return
            else:
                print("    [*] First address empty. Scrolling feed...")
        except Exception as check_err:
            print(f"[-] Geofence check failed: {check_err}")

    await scroll_feed(page)
    listings_count = await page.locator(link_selector).count()
    print(f"[*] Found {listings_count} listings in results.")
    
    urls = []
    for i in range(listings_count):
        try:
            href = await page.locator(link_selector).nth(i).get_attribute("href")
            if href:
                urls.append(href)
        except Exception:
            pass
            
    urls = list(dict.fromkeys(urls))
    
    count_saved = 0
    for index, url in enumerate(urls):
        if extract_place_id(url) in scraped_urls:
            continue
            
        print(f"[{index + 1}/{len(urls)}] Extracting detail...")
        
        clicked = False
        try:
            item_locator = page.locator(f'a.hfpxzc[href="{url}"]')
            if await item_locator.count() > 0:
                expected_name = await item_locator.first.get_attribute("aria-label")
                if expected_name:
                    expected_name = expected_name.strip()
                    
                await item_locator.first.scroll_into_view_if_needed()
                await item_locator.first.click()
                
                if expected_name:
                    name_matched = False
                    for _ in range(15):
                        h1_locator = page.locator(config_sk.SELECTORS["business_name"])
                        if await h1_locator.count() > 0:
                            current_name = await h1_locator.first.inner_text()
                            current_name = current_name.strip()
                            if expected_name.lower() in current_name.lower() or current_name.lower() in expected_name.lower():
                                name_matched = True
                                break
                        await page.wait_for_timeout(200)
                    
                    if name_matched:
                        clicked = True
                    else:
                        print("      [-] Details card did not match. Fallback to navigation.")
                else:
                    await page.wait_for_timeout(2000)
                    clicked = True
                    
                await handle_captcha(page)
        except Exception:
            pass
            
        if not clicked:
            continue

        try:
            record = await extract_details(page, url, search_query, loc_info)
            if record:
                append_to_csv(record)
                scraped_urls.add(extract_place_id(url))
                count_saved += 1
                print(f"    -> SAVED: {record['Name']} | Phone: {record['Phone']} | Web: {record['Website']}")
            else:
                print("    [-] Failed to parse details card.")
        except Exception as parse_err:
            print(f"    [-] Exception during extraction: {parse_err}")
                
        await asyncio.sleep(random.uniform(config_sk.MIN_DELAY, config_sk.MAX_DELAY))

    if count_saved > 0:
        print(f"[+] Finished scan: Saved {count_saved} new entries.")

async def main():
    print("="*60)
    print("      SLOVAKIA RECRUITMENT AGENCY GOOGLE MAPS SCRAPER")
    print("="*60)
    
    scraped_urls = get_scraped_urls()
    print(f"[+] Loaded {len(scraped_urls)} existing entries from CSV.")
    
    completed_scans = load_completed_scans()
    
    locs = locations_sk.get_locations()
    keywords = config_sk.KEYWORDS
    
    print(f"[+] Total target locations: {len(locs)}")
    print(f"[+] Search keywords: {keywords}")
    print(f"[+] Output CSV path: {config_sk.OUTPUT_CSV}\n")
    
    async with async_playwright() as p:
        browser = None
        for channel in ["chrome", "msedge", None]:
            try:
                chan_str = f"channel '{channel}'" if channel else "default Chromium"
                print(f"[*] Attempting to launch browser with {chan_str}...")
                launch_args = {
                    "headless": config_sk.HEADLESS,
                    "slow_mo": config_sk.SLOW_MO,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--lang=sk,en"
                    ]
                }
                if channel:
                     launch_args["channel"] = channel
                browser = await p.chromium.launch(**launch_args)
                print(f"[+] Launched browser using {chan_str}!")
                break
            except Exception as e:
                print(f"[-] Failed with channel '{channel}': {e}")
                
        if not browser:
            print("[!] Could not launch browser. Exiting.")
            return
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="sk",
            viewport={"width": 1280, "height": 800},
            geolocation={"latitude": 48.1485, "longitude": 17.1077},  # Bratislava
            permissions=["geolocation"]
        )
        
        page = await context.new_page()
        
        total_scans = len(locs) * len(keywords)
        scan_index = 0
        
        try:
            for loc in locs:
                for kw in keywords:
                    scan_index += 1
                    
                    scan_key = (loc['name'].lower(), loc['state'].lower(), kw.lower())
                    if scan_key in completed_scans:
                        continue
                        
                    print(f"\n[Progress: {scan_index}/{total_scans}] Location: {loc['name']} | Keyword: '{kw}'")
                    success = await process_search(page, kw, loc, scraped_urls)
                    
                    if success is not False:
                        save_completed_scan(loc['name'], loc['state'], kw)
                    
                    await asyncio.sleep(random.uniform(3.0, 7.0))
                    
        except KeyboardInterrupt:
            print("\n[-] Scraping manually interrupted by user.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[-] Unexpected runtime error: {e}")
            sys.exit(1)
        finally:
            print("\n[*] Closing browser...")
            await context.close()
            await browser.close()
            
    print(f"\n[+] Scraping session complete! Total entries in CSV: {len(get_scraped_urls())}")
    print(f"[+] Results saved to: {config_sk.OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main())
