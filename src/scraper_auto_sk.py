import asyncio
import csv
import os
import random
import re
import sys
import json
import urllib.parse
from playwright.async_api import async_playwright

# Import local modules
import config_auto_sk
import locations_sk

# Set console output encoding to UTF-8 to prevent print errors
if sys.platform.startswith('win'):
    import codecs
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "progress",
    "progress_auto_sk.json"
)

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    scraped_urls = set()
    if os.path.exists(config_auto_sk.OUTPUT_CSV):
        try:
            with open(config_auto_sk.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}", flush=True)
    return scraped_urls

def is_slovakia_address(address):
    """Verifies if an address is in Slovakia."""
    if not address:
        return False
    addr_lower = address.lower()
    if any(k in addr_lower for k in ["slovakia", "slovensko", "slovenská", "slovenskej", "sr", "slovak republic"]):
        return True
    
    # Slovak cities
    sk_cities = [
        "bratislava", "kosice", "košice", "presov", "prešov", "zilina", "žilina", "nitra", 
        "banska bystrica", "banská bystrica", "trnava", "martin", "trencin", "trenčín", 
        "poprad", "prievidza", "zvolen", "povazska bystrica", "považská bystrica", 
        "nove zamky", "nové zámky", "michalovce", "spisska nova ves", "spišská nová ves", 
        "komarno", "komárno", "levice", "humenne", "humenné", "bardejov", "ruzomberok", 
        "ružomberok", "piestany", "piešťany", "lucenec", "lučenec", "cadca", "čadca",
        "hlohovec", "topolcany", "topoľčany", "malacky", "senica", "pezinok"
    ]
    if any(city in addr_lower for city in sk_cities):
        return True
        
    # Slovakia zip code check: 3 digits + space/dash + 2 digits (e.g. 811 07) or 5 digits
    if re.search(r'\b\d{3}\s?\d{2}\b', address) or re.search(r'\b\d{5}\b', address):
        return True
        
    return False

def append_to_csv(row_dict):
    os.makedirs(os.path.dirname(config_auto_sk.OUTPUT_CSV), exist_ok=True)
    file_exists = os.path.isfile(config_auto_sk.OUTPUT_CSV)
    try:
        with open(config_auto_sk.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}", flush=True)

def load_completed_scans():
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    completed = set()
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}", flush=True)
            
    if os.path.exists(config_auto_sk.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...", flush=True)
            completed_list = []
            with open(config_auto_sk.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    kw = row.get('Search_Query', '')
                    raw_kw = ""
                    if kw:
                        for original_kw in config_auto_sk.KEYWORDS:
                            if original_kw in kw:
                                raw_kw = original_kw
                                break
                    if not raw_kw:
                        raw_kw = config_auto_sk.KEYWORDS[0]
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), raw_kw.lower())
                        if pair not in completed:
                            completed.add(pair)
                            completed_list.append([loc_name.strip(), state.strip(), raw_kw])
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
            print(f"[+] Loaded {len(completed)} completed locations from CSV.", flush=True)
        except Exception as e:
            print(f"[-] Error initializing progress: {e}", flush=True)
            
    return completed

def save_completed_scan(loc_name, state, keyword):
    completed_list = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed_list = data.get("completed", [])
        except Exception:
            pass
            
    pair = [loc_name, state, keyword]
    if pair not in completed_list:
        completed_list.append(pair)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Error saving progress: {e}", flush=True)

async def handle_captcha(page):
    current_url = page.url.lower()
    page_content = await page.content()
    if "sorry" in current_url or "captcha" in current_url or "recaptcha" in page_content.lower() or "unusual traffic" in page_content.lower():
        print("\a" * 3)  # Chime
        print("[!] CAPTCHA DETECTED! Please solve it in the browser window...", flush=True)
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha solved! Resuming...", flush=True)
                break

async def bypass_consent_screen(page):
    try:
        consent_buttons = page.locator('button:has-text("Prijať všetko"), button:has-text("I agree"), button:has-text("Accept all"), form:has(button) button:has-text("Prijať")')
        if await consent_buttons.count() > 0:
            await consent_buttons.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def extract_details(page, url, search_query, loc_info):
    name = ""
    try:
        h1 = page.locator(config_auto_sk.SELECTORS["business_name"])
        if await h1.count() > 0:
            name = (await h1.first.inner_text()).strip()
    except Exception:
        pass

    if not name:
        return None

    # Category
    category = ""
    try:
        cat_loc = page.locator(config_auto_sk.SELECTORS["category"])
        if await cat_loc.count() > 0:
            category = (await cat_loc.first.inner_text()).strip()
    except Exception:
        pass

    # Filter categories if ALLOWED_CATEGORIES is set
    if config_auto_sk.ALLOWED_CATEGORIES and category:
        match_cat = any(ac.lower() in category.lower() or category.lower() in ac.lower() for ac in config_auto_sk.ALLOWED_CATEGORIES)
        if not match_cat:
            # Let it pass if category is generic auto/manufacturing
            auto_terms = ["auto", "vozidl", "oprav", "servis", "výrob", "kovo", "hliník", "car", "motor"]
            if not any(t in category.lower() for t in auto_terms):
                print(f"    [-] Skipping non-matching category: {category} ({name})", flush=True)
                return None

    # Address
    address = ""
    try:
        addr_loc = page.locator(config_auto_sk.SELECTORS["address"])
        if await addr_loc.count() > 0:
            address = (await addr_loc.first.inner_text()).strip()
    except Exception:
        pass

    if address and not is_slovakia_address(address):
        print(f"    [-] Skipping out-of-country address: {address} ({name})", flush=True)
        return None

    # Phone - prepend single quote
    phone = ""
    try:
        phone_loc = page.locator(config_auto_sk.SELECTORS["phone"])
        if await phone_loc.count() > 0:
            phone_raw = (await phone_loc.first.inner_text()).strip()
            phone = f"'{phone_raw}" if phone_raw and not phone_raw.startswith("'") else phone_raw
    except Exception:
        pass

    # Website
    website = ""
    try:
        web_loc = page.locator(config_auto_sk.SELECTORS["website"])
        if await web_loc.count() > 0:
            website = (await web_loc.first.get_attribute("href") or "").strip()
    except Exception:
        pass

    # Rating & Reviews
    rating = ""
    reviews_count = ""
    try:
        r_loc = page.locator(config_auto_sk.SELECTORS["rating"])
        if await r_loc.count() > 0:
            rating = (await r_loc.first.inner_text()).strip()
        rev_loc = page.locator(config_auto_sk.SELECTORS["reviews_count"])
        if await rev_loc.count() > 0:
            rev_text = (await rev_loc.first.get_attribute("aria-label") or "").strip()
            m = re.search(r'(\d+)', rev_text.replace(',', '').replace('.', ''))
            if m:
                reviews_count = m.group(1)
    except Exception:
        pass

    # Coordinates from URL
    actual_lat, actual_lng = "", ""
    current_url = page.url
    coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', current_url)
    if coord_match:
        actual_lat, actual_lng = coord_match.group(1), coord_match.group(2)
    else:
        m2 = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
        if m2:
            actual_lat, actual_lng = m2.group(1), m2.group(2)

    # Permanently closed check
    closed_loc = page.locator('span:has-text("Trvalo zatvorené"), span:has-text("Permanently closed")')
    permanently_closed = "Yes" if await closed_loc.count() > 0 else "No"

    return {
        "Name": name,
        "Category": category,
        "Phone": phone,
        "Website": website,
        "Address": address,
        "Rating": rating,
        "Reviews_Count": reviews_count,
        "State": loc_info.get("state", ""),
        "Location_Name": loc_info.get("name", ""),
        "Latitude": actual_lat,
        "Longitude": actual_lng,
        "Search_Query": search_query,
        "URL": current_url,
        "Permanently_Closed": permanently_closed,
    }

async def process_search(page, keyword, loc_info, scraped_urls):
    search_query = f"{keyword} in {loc_info['name']}, Slovakia"
    print(f"\n[+] Searching: '{search_query}'", flush=True)
    
    query_encoded = urllib.parse.quote_plus(keyword)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{loc_info['zoom']}z?hl=sk"
    
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception:
        pass

    for attempt in range(1, 4):
        try:
            await page.goto(search_url, timeout=config_auto_sk.TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            break
        except Exception as e:
            if attempt == 3:
                print(f"[-] Navigation failed: {e}", flush=True)
                return
            await asyncio.sleep(4.0)

    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url

    # Check if redirected directly to single place
    if "/maps/place/" in current_url:
        pid = extract_place_id(current_url)
        if pid not in scraped_urls:
            rec = await extract_details(page, current_url, search_query, loc_info)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                print(f"    -> SAVED: {rec['Name']} | Tel: {rec['Phone']} | Web: {rec['Website']}", flush=True)
        return

    # Check listings in feed
    feed_selector = config_auto_sk.SELECTORS["results_container"]
    link_selector = config_auto_sk.SELECTORS["listing_link"]

    try:
        await page.wait_for_selector(feed_selector, timeout=7000)
    except Exception:
        print("    [*] No results feed container found.", flush=True)
        return

    feed = page.locator(feed_selector).first

    # Scroll feed to load items
    seen_hrefs = set()
    no_new_counter = 0

    while True:
        links = await page.locator(link_selector).all()
        current_hrefs = []
        for l in links:
            href = await l.get_attribute("href")
            if href:
                current_hrefs.append(href)

        new_found = [h for h in current_hrefs if h not in seen_hrefs]
        for h in new_found:
            seen_hrefs.add(h)

        # Check end of list indicator
        end_text = page.locator('span:has-text("Dosiahli ste koniec zoznamu"), span:has-text("You\'ve reached the end of the list")')
        if await end_text.count() > 0:
            break

        if not new_found:
            no_new_counter += 1
            if no_new_counter >= 5:
                break
        else:
            no_new_counter = 0

        # Scroll down
        try:
            await feed.evaluate('el => el.scrollBy(0, 1000)')
            await page.wait_for_timeout(1000)
        except Exception:
            break

    print(f"    [*] Found {len(seen_hrefs)} total listing links in feed.", flush=True)

    # Process each listing link
    for idx, href in enumerate(seen_hrefs):
        pid = extract_place_id(href)
        if pid in scraped_urls:
            continue

        try:
            await page.goto(href, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            await handle_captcha(page)

            rec = await extract_details(page, href, search_query, loc_info)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                print(f"    [{idx+1}/{len(seen_hrefs)}] SAVED: {rec['Name']} | Phone: {rec['Phone']} | Web: {rec['Website']}", flush=True)
        except Exception as e:
            continue

async def main():
    os.makedirs(os.path.dirname(config_auto_sk.OUTPUT_CSV), exist_ok=True)
    scraped_urls = get_scraped_urls()
    completed_scans = load_completed_scans()

    print("=" * 70, flush=True)
    print("SLOVAKIA AUTOMOTIVE & ALUMINUM FACTORIES GOOGLE MAPS SCRAPER", flush=True)
    print(f"Output CSV : {config_auto_sk.OUTPUT_CSV}", flush=True)
    print(f"Existing records : {len(scraped_urls)} unique places", flush=True)
    print(f"Completed scans  : {len(completed_scans)} pairs", flush=True)
    print("=" * 70, flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config_auto_sk.HEADLESS,
            slow_mo=config_auto_sk.SLOW_MO,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="sk-SK",
            permissions=["geolocation"]
        )
        page = await context.new_page()

        total_locations = len(locations_sk.LOCATIONS)
        for loc_idx, loc in enumerate(locations_sk.LOCATIONS):
            loc_name = loc['name']
            state = loc['state']

            for kw in config_auto_sk.KEYWORDS:
                scan_key = (loc_name.lower(), state.lower(), kw.lower())
                if scan_key in completed_scans:
                    continue

                print(f"\n[LOC {loc_idx+1}/{total_locations}] Region: {state} | City: {loc_name} | Keyword: '{kw}'", flush=True)
                await process_search(page, kw, loc, scraped_urls)
                save_completed_scan(loc_name, state, kw)
                completed_scans.add(scan_key)

                delay = random.uniform(config_auto_sk.MIN_DELAY, config_auto_sk.MAX_DELAY)
                await asyncio.sleep(delay)

        await browser.close()

    print("\n" + "=" * 70, flush=True)
    print(f"[SUCCESS] Scraping completed! Output saved to: {config_auto_sk.OUTPUT_CSV}", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
