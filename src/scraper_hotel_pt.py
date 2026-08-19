import asyncio
import csv
import json
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Import local modules
import config_hotel_pt
import locations_pt

# Set console output encoding to UTF-8
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
    """Loads already scraped business URLs (Place IDs) from the CSV file to avoid duplicates."""
    scraped_urls = set()
    if os.path.exists(config_hotel_pt.OUTPUT_CSV):
        try:
            with open(config_hotel_pt.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}")
    return scraped_urls

def is_portugal_address(address):
    """Verifies if an address is in Portugal."""
    if not address:
        return False
    addr_lower = address.lower()
    if "portugal" in addr_lower or ", pt" in addr_lower:
        return True
    
    pt_cities = [
        "lisboa", "lisbon", "porto", "faro", "coimbra", "braga", "funchal", 
        "ponta delgada", "aveiro", "leiria", "setúbal", "setubal", "évora", "evora", 
        "viseu", "viana do castelo", "garda", "bragança", "braganca", "beja", 
        "santarém", "santarem", "portimão", "portimao", "albufeira", "lagos", 
        "cascais", "sintra", "estoril", "vilamoura"
    ]
    if any(city in addr_lower for city in pt_cities):
        return True
        
    if re.search(r'\b\d{4}-\d{3}\b', addr_lower) or re.search(r'\b\d{4}\b', addr_lower):
        return True
        
    return False

def append_to_csv(row_dict):
    """Appends a single scraped record to the output CSV file."""
    file_exists = os.path.isfile(config_hotel_pt.OUTPUT_CSV)
    try:
        with open(config_hotel_pt.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

PROGRESS_FILE = config_hotel_pt.PROGRESS_FILE

def load_completed_scans():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
            
    if os.path.exists(config_hotel_pt.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...")
            completed_list = []
            with open(config_hotel_pt.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), config_hotel_pt.KEYWORDS[0].lower())
                        if pair not in completed_list:
                            completed_list.append(pair)
            
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=2, ensure_ascii=False)
            return set(completed_list)
        except Exception as e:
            print(f"[-] Error parsing CSV for progress: {e}")
            
    return set()

def save_completed_scan(loc_name, state, keyword):
    completed = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed = data.get("completed", [])
        except Exception:
            completed = []
            
    item = [loc_name, state, keyword]
    if item not in completed:
        completed.append(item)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Error saving progress: {e}")

async def handle_captcha(page):
    """Detects if Google CAPTCHA / bot detection page is shown and exits safely."""
    is_captcha = False
    try:
        title = await page.title()
        if "sorry" in title.lower() or "recaptcha" in title.lower() or "captcha" in title.lower():
            is_captcha = True
        elif await page.locator('iframe[src*="recaptcha"]').count() > 0 or await page.locator('div#recaptcha').count() > 0:
            is_captcha = True
    except Exception:
        pass
        
    if is_captcha:
        print("\n" + "="*60)
        print("[!] IP BLOCK / CAPTCHA DETECTED! Google is blocking automated access.")
        print("[!] Stopping the scraper immediately to protect your IP address...")
        print("="*60 + "\n")
        sys.stdout.write('\a')
        sys.stdout.flush()
        sys.exit(1)

async def bypass_consent_screen(page):
    """Automatically clicks Google Maps Consent/Cookie banners if they appear."""
    try:
        consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("Agree"), button:has-text("I agree"), button:has-text("Accept"), button:has-text("Aceitar tudo"), button:has-text("Concordo")')
        if await consent_buttons.count() > 0:
            print("[*] Google Consent / Cookie banner detected. Bypassing...")
            await consent_buttons.first.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def scroll_feed(page, max_scrolls=20):
    """Scrolls down the left results container to load all matching businesses."""
    feed_selector = config_hotel_pt.SELECTORS["results_container"]
    
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
        if "reached the end of the list" in inner_text.lower() or "fim da lista" in inner_text.lower():
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

def parse_portugal_address(address):
    if not address:
        return None, None, None
    addr = re.sub(r',\s*Portugal\s*$', '', address, flags=re.IGNORECASE).strip()
    
    postcode_match = re.search(r'\b\d{4}-\d{3}\b', addr)
    if postcode_match:
        postcode = postcode_match.group(0)
        remaining = addr[:postcode_match.start()].strip().rstrip(',')
        parts = [p.strip() for p in remaining.split(',')]
        suburb = parts[-1] if parts else ""
        return suburb, "PT", postcode
        
    parts = [p.strip() for p in addr.split(',')]
    if len(parts) >= 2:
        return parts[-2], "PT", ""
    elif len(parts) == 1:
        return parts[0], "PT", ""
    return None, None, None

async def extract_details(page, url, search_query, loc_info):
    """Extracts business details from the detail panel on the page."""
    sel = config_hotel_pt.SELECTORS
    
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
            address = addr_label.replace("Address:", "").replace("Endereço:", "").strip()
        else:
            address = await addr_loc.first.inner_text()
            address = address.strip()
            
    if not is_portugal_address(address):
        print(f"    [-] Skipping: Address '{address}' is not in Portugal.")
        return None
        
    actual_lat, actual_lng = loc_info["lat"], loc_info["lng"]
    coords = extract_coords_from_url(url)
    if coords:
        actual_lat, actual_lng = coords
        if not (32.0 < actual_lat < 43.0) or not (-32.0 < actual_lng < -6.0):
            print(f"    [-] Skipping: Coordinates ({actual_lat}, {actual_lng}) are outside Portugal.")
            return None
            
    actual_suburb, actual_state, postcode = parse_portugal_address(address)
    if not actual_state:
        actual_suburb = loc_info["name"]
        actual_state = "PT"
        
    rating = ""
    reviews_count = ""
    rating_loc = page.locator('div.F7nice')
    if await rating_loc.count() > 0:
        span_rating = rating_loc.first.locator('span[aria-hidden="true"]')
        if await span_rating.count() > 0:
            rating = await span_rating.first.inner_text()
            rating = rating.strip()
            
        span_reviews = rating_loc.first.locator('span[aria-label*="classificação"], span[aria-label*="avaliação"], span[aria-label*="review"]')
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
        closed_loc = page.locator('span:has-text("Permanently closed"), span:has-text("Fechado permanentemente")')
        if await closed_loc.count() > 0:
            permanently_closed = "Yes"
    except Exception:
        pass

    # Extract Category Tag with a wait loop to prevent race conditions
    category = ""
    try:
        category_loc = page.locator(sel["category"])
        for _ in range(15):
            count = await category_loc.count()
            if count > 0:
                for i in range(count):
                    txt = await category_loc.nth(i).inner_text()
                    txt_clean = txt.strip().replace("·", "").strip()
                    if txt_clean and txt_clean not in ["", "·"]:
                        category = txt_clean
                        break
                if category:
                    break
            await page.wait_for_timeout(200)
    except Exception:
        pass

    # Strict filter: category must match one of the allowed hotel tags
    if category:
        cat_lower = category.lower().strip()
        if not any(tag in cat_lower for tag in config_hotel_pt.ALLOWED_CATEGORIES):
            print(f"    [-] Skipping: Category '{category}' is not in allowed hotel tags.")
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
    """Executes search for a specific keyword at a specific coordinate location."""
    search_query = f"{keyword} in {loc_info['name']}, Portugal"
    print(f"\n[+] Searching: '{search_query}'")
    
    query_encoded = urllib.parse.quote_plus(keyword)
    zoom = loc_info.get("zoom", 11)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{zoom}z?hl=pt"
    
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception as geo_err:
        print(f"[*] Warning: Could not set geolocation context: {geo_err}")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"[*] Navigating to search URL (Attempt {attempt}/{max_retries})...")
            await page.goto(search_url, timeout=config_hotel_pt.TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"[-] Navigation failed to search URL after {max_retries} attempts: {e}")
                return False
            else:
                print(f"[!] Timeout/error navigating, retrying in 5 seconds... ({e})")
                await asyncio.sleep(5.0)
        
    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url
    
    if "/maps/place/" in current_url:
        print("[*] Redirected directly to place details view.")
        current_place_id = extract_place_id(current_url)
        if current_place_id not in scraped_urls:
            record = await extract_details(page, current_url, search_query, loc_info)
            if record:
                append_to_csv(record)
                scraped_urls.add(current_place_id)
                print(f"    -> SAVED: {record['Name']} | Tag: {record['Category']} | Phone: {record['Phone']} | Web: {record['Website']}")
        return True

    link_selector = config_hotel_pt.SELECTORS["listing_link"]
    listings_count = await page.locator(link_selector).count()
    
    if listings_count > 0:
        first_item = page.locator(link_selector).first
        try:
            expected_name = await first_item.get_attribute("aria-label")
            await first_item.scroll_into_view_if_needed()
            await first_item.click()
            
            for _ in range(15):
                h1_locator = page.locator(config_hotel_pt.SELECTORS["business_name"])
                if await h1_locator.count() > 0:
                    current_name = await h1_locator.first.inner_text()
                    current_name = current_name.strip()
                    if expected_name and (expected_name.lower() in current_name.lower() or current_name.lower() in expected_name.lower()):
                        break
                await page.wait_for_timeout(200)
                
            addr_loc = page.locator(config_hotel_pt.SELECTORS["address"])
            address = ""
            if await addr_loc.count() > 0:
                addr_label = await addr_loc.first.get_attribute("aria-label")
                address = addr_label.replace("Address:", "").replace("Endereço:", "").strip() if addr_label else await addr_loc.first.inner_text()
                address = address.strip()
                
            if address and not is_portugal_address(address):
                print(f"[-] First listing is outside Portugal ('{address}'). Skipping location.")
                return True
        except Exception as check_err:
            print(f"[-] Error checking geofence on first listing: {check_err}")

    await scroll_feed(page)
    
    listings_count = await page.locator(link_selector).count()
    print(f"[*] Found {listings_count} listings in search results.")
    
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
                        h1_locator = page.locator(config_hotel_pt.SELECTORS["business_name"])
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
                        print("      [-] Details card did not match. Skipping.")
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
                print(f"    -> SAVED: {record['Name']} | Tag: {record['Category']} | Phone: {record['Phone']} | Web: {record['Website']}")
            else:
                print("    [-] Failed to parse details card or tag filtered out.")
        except Exception as parse_err:
            print(f"    [-] Exception during detail extraction: {parse_err}")
                
        await asyncio.sleep(random.uniform(config_hotel_pt.MIN_DELAY, config_hotel_pt.MAX_DELAY))

    if count_saved > 0:
        print(f"[+] Finished scan for query: Saved {count_saved} new entries.")
    return True

async def main():
    print("="*60)
    print("      PORTUGAL HOTEL & ACCOMMODATION GOOGLE MAPS SCRAPER")
    print("="*60)
    
    scraped_urls = get_scraped_urls()
    print(f"[+] Loaded {len(scraped_urls)} existing entries from CSV.")
    
    completed_scans = load_completed_scans()
    
    locs = locations_pt.get_locations()
    keywords = config_hotel_pt.KEYWORDS
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        locs = locs[:3]
        print(f"[TEST MODE] Running on first {len(locs)} locations only.")
        
    print(f"[+] Total target locations: {len(locs)}")
    print(f"[+] Search keywords: {keywords}")
    print(f"[+] Output CSV path: {config_hotel_pt.OUTPUT_CSV}\n")
    
    async with async_playwright() as p:
        browser = None
        for channel in ["chrome", "msedge", None]:
            try:
                chan_str = f"channel '{channel}'" if channel else "default Chromium"
                print(f"[*] Attempting to launch browser with {chan_str}...")
                launch_args = {
                    "headless": config_hotel_pt.HEADLESS,
                    "slow_mo": config_hotel_pt.SLOW_MO,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--lang=pt-PT,pt"
                    ]
                }
                if channel:
                    launch_args["channel"] = channel
                browser = await p.chromium.launch(**launch_args)
                print(f"[+] Successfully launched browser using {chan_str}!")
                break
            except Exception as e:
                print(f"[-] Failed to launch with channel '{channel}': {e}")
                
        if not browser:
            print("[!] Could not launch any browser. Exiting.")
            return
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="pt-PT",
            viewport={"width": 1280, "height": 800},
            geolocation={"latitude": 38.7223, "longitude": -9.1393}, # Lisbon coordinates
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
                    
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                    
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
            
    print(f"\n[+] Scraping session complete! Total unique entries in CSV: {len(get_scraped_urls())}")
    print(f"[+] Results saved to: {config_hotel_pt.OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main())
