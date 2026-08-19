import asyncio
import csv
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Import local modules
import config_farm_nz
import locations_nz

# Set console output encoding to UTF-8 to prevent print errors with Vietnamese or special chars
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def extract_place_id(url):
    if not url:
        return ""
    # Match hex Place ID pair in the URL, e.g. 1s0x6d0983123d4a394f:0xe33631cb235db916
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    """Loads already scraped business URLs (Place IDs) from the CSV file to avoid duplicates."""
    scraped_urls = set()
    if os.path.exists(config_farm_nz.OUTPUT_CSV):
        try:
            with open(config_farm_nz.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}")
    return scraped_urls

def is_new_zealand_address(address):
    """Verifies if an address is in New Zealand by checking for country name, key regions or postcode patterns."""
    if not address:
        return False
    addr_lower = address.lower()
    if "new zealand" in addr_lower or " nz" in addr_lower or addr_lower.endswith("nz"):
        return True
    # Common cities and regions in NZ
    nz_places = ["auckland", "wellington", "christchurch", "hamilton", "tauranga", "dunedin", "palmerston north", "napier", "nelson", "rotorua", "whangarei", "invercargill", "new plymouth", "kapiti", "gisborne", "blenheim", "timaru", "taupo", "oamaru"]
    if any(place in addr_lower for place in nz_places):
        return True
    # Check for 4-digit postcodes without "australia"
    if re.search(r'\b\d{4}\b', addr_lower) and "australia" not in addr_lower:
        return True
    return False

def append_to_csv(row_dict):
    """Appends a single scraped record to the output CSV file."""
    file_exists = os.path.isfile(config_farm_nz.OUTPUT_CSV)
    try:
        with open(config_farm_nz.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

import json

PROGRESS_FILE = os.path.join(os.path.dirname(config_farm_nz.OUTPUT_CSV), "scraping_progress_farm_nz.json")

def load_completed_scans():
    completed = set()
    # 1. Try to load from progress.json
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
            
    # 2. If progress file does not exist, initialize it from existing CSV entries
    if os.path.exists(config_farm_nz.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...")
            completed_list = []
            with open(config_farm_nz.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), config_farm_nz.KEYWORDS[0].lower())
                        if pair not in completed:
                            completed.add(pair)
                            completed_list.append([loc_name.strip(), state.strip(), config_farm_nz.KEYWORDS[0]])
            # Write to progress.json
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
            print(f"[+] Loaded {len(completed)} completed locations from CSV and initialized progress file.")
        except Exception as e:
            print(f"[-] Error initializing progress from CSV: {e}")
            
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
            
    # Add new combination if not already present
    pair = [loc_name, state, keyword]
    if pair not in completed_list:
        completed_list.append(pair)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Error saving progress file: {e}")

async def handle_captcha(page):
    """Checks for Google CAPTCHA or unusual traffic warnings and exits the program immediately if blocked."""
    is_captcha = False
    
    # Check common CAPTCHA indications
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
        
        # Ring terminal bell to notify user
        sys.stdout.write('\a')
        sys.stdout.flush()
        
        # Exit the program immediately to stop scraping
        sys.exit(1)

async def bypass_consent_screen(page):
    """Automatically clicks Google Maps Consent/Cookie banners if they appear."""
    try:
        consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("Agree"), button:has-text("I agree"), button:has-text("Accept"), button:has-text("Accept details")')
        if await consent_buttons.count() > 0:
            print("[*] Google Consent / Cookie banner detected. Bypassing...")
            await consent_buttons.first.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
    except Exception as e:
        pass

async def scroll_feed(page, max_scrolls=20):
    """Scrolls down the left results container to load all matching businesses."""
    feed_selector = config_farm_nz.SELECTORS["results_container"]
    
    # Wait to see if results container appears
    try:
        await page.wait_for_selector(feed_selector, timeout=8000)
    except Exception as e:
        return
        
    feed = page.locator(feed_selector)
    if await feed.count() == 0:
        return
        
    print("[*] Scrolling the results panel to load listings...")
    
    scrolls = 0
    last_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
    
    while scrolls < max_scrolls:
        # Scroll container to the bottom
        await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
        
        # Sleep to let results load
        await page.wait_for_timeout(random.uniform(400, 800))
        
        # Check if we hit the end-of-list message
        inner_text = await feed.inner_text()
        if "You've reached the end of the list." in inner_text:
            print("[*] Reached the end of the results list.")
            break
            
        new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
        if new_height == last_height:
            # Double check with a longer delay
            await page.wait_for_timeout(500)
            await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
            new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
            if new_height == last_height:
                break
                
        last_height = new_height
        scrolls += 1

def extract_coords_from_url(url):
    """Parses actual coordinates from a Google Maps place URL."""
    if not url:
        return None
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

def parse_new_zealand_address(address):
    """Extracts suburb/city and postcode from a standard New Zealand address."""
    if not address:
        return None, None, None
    # Remove country suffix
    addr = re.sub(r',\s*New Zealand\s*$', '', address, flags=re.IGNORECASE).strip()
    addr = re.sub(r'\s*NZ\s*$', '', addr, flags=re.IGNORECASE).strip()
    
    # Look for 4-digit postcode at the end
    postcode_match = re.search(r'\b(\d{4})$', addr)
    if postcode_match:
        postcode = postcode_match.group(1)
        remaining = addr[:postcode_match.start()].strip().rstrip(',')
        parts = [p.strip() for p in remaining.split(',')]
        
        # The last part before postcode is usually the city/suburb
        suburb = parts[-1] if parts else ""
        return suburb, "NZ", postcode
        
    # Fallback if no postcode found
    parts = [p.strip() for p in addr.split(',')]
    if len(parts) >= 2:
        return parts[-2], "NZ", ""
    elif len(parts) == 1:
        return parts[0], "NZ", ""
    return None, None, None

async def extract_details(page, url, search_query, loc_info):
    """Extracts business details from the detail panel on the page."""
    # Retrieve configuration selectors
    sel = config_farm_nz.SELECTORS
    
    # Extract Business Name
    name = ""
    name_loc = page.locator(sel["business_name"])
    if await name_loc.count() > 0:
        name = await name_loc.first.inner_text()
        name = name.strip()
        
    # If Name is empty, skip extraction (not a valid details panel)
    if not name:
        return None
        
    # Extract Website Link
    website = ""
    web_loc = page.locator(sel["website"])
    if await web_loc.count() > 0:
        website = await web_loc.first.get_attribute("href")
        if website:
            website = website.strip()
            
    # Extract Phone Number
    phone = ""
    phone_loc = page.locator(sel["phone"])
    if await phone_loc.count() > 0:
        phone_attr = await phone_loc.first.get_attribute("data-item-id")
        if phone_attr:
            phone = phone_attr.replace("phone:tel:", "").strip()
            
    # Extract Address
    address = ""
    addr_loc = page.locator(sel["address"])
    if await addr_loc.count() > 0:
        addr_label = await addr_loc.first.get_attribute("aria-label")
        if addr_label:
            address = addr_label.replace("Address:", "").strip()
        else:
            address = await addr_loc.first.inner_text()
            address = address.strip()
            
    # Validate Address is in New Zealand
    if not is_new_zealand_address(address):
        print(f"    [-] Skipping: Address '{address}' is not in New Zealand.")
        return None
        
    # Extract Coordinates and check bounds
    actual_lat, actual_lng = loc_info["lat"], loc_info["lng"]
    coords = extract_coords_from_url(url)
    if coords:
        actual_lat, actual_lng = coords
        # NZ Bounding box coordinates
        if not (-48.0 < actual_lat < -33.0) or not (165.0 < actual_lng < 179.5):
            print(f"    [-] Skipping: Coordinates ({actual_lat}, {actual_lng}) are outside New Zealand.")
            return None
            
    # Parse Suburb and State
    actual_suburb, actual_state, postcode = parse_new_zealand_address(address)
    if not actual_state:
        actual_suburb = loc_info["name"]
        actual_state = "NZ"
        
    # Extract Rating & Reviews
    rating = ""
    reviews_count = ""
    rating_loc = page.locator('div.F7nice')
    if await rating_loc.count() > 0:
        # Rating text (e.g. 4.8)
        span_rating = rating_loc.first.locator('span[aria-hidden="true"]')
        if await span_rating.count() > 0:
            rating = await span_rating.first.inner_text()
            rating = rating.strip()
            
        # Review count text (e.g. 15 reviews)
        span_reviews = rating_loc.first.locator('span[aria-label*="reviews"]')
        if await span_reviews.count() > 0:
            reviews_text = await span_reviews.first.get_attribute("aria-label")
            if reviews_text:
                match = re.search(r'\d+', reviews_text.replace(",", ""))
                if match:
                    reviews_count = match.group()
            else:
                reviews_text = await span_reviews.first.inner_text()
                match = re.search(r'\d+', reviews_text.replace(",", ""))
                if match:
                    reviews_count = match.group()
                    
    # Check if Permanently Closed
    permanently_closed = "No"
    try:
        closed_loc = page.locator('span:has-text("Permanently closed"), span:has-text("Đóng cửa vĩnh viễn")')
        if await closed_loc.count() > 0:
            permanently_closed = "Yes"
    except Exception:
        pass

    # Extract Category
    category = ""
    try:
        category_loc = page.locator(sel["category"])
        if await category_loc.count() > 0:
            category = await category_loc.first.inner_text()
            category = category.strip()
    except Exception:
        pass

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
    search_query = f"{keyword} in {loc_info['name']}, New Zealand"
    print(f"\n[+] Searching: '{search_query}'")
    
    # Construct coordinate search URL
    query_encoded = urllib.parse.quote_plus(keyword)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{loc_info['zoom']}z?hl=en"
    
    # Set context geolocation to prevent Google Maps from defaulting back to Vietnam/runner location
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception as geo_err:
        print(f"[*] Warning: Could not set geolocation context: {geo_err}")

    # Navigate with retry logic
    max_retries = 3
    navigated = False
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f"[*] Navigating to search URL (Attempt {attempt}/{max_retries})...")
            await page.goto(search_url, timeout=config_farm_nz.TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000) # Allow initial rendering
            navigated = True
            break
        except Exception as e:
            if attempt == max_retries:
                print(f"[-] Navigation failed to search URL after {max_retries} attempts: {e}")
                return
            else:
                print(f"[!] Timeout/error navigating, retrying in 5 seconds... ({e})")
                await asyncio.sleep(5.0)
        
    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url
    # Check if Google redirected directly to a single business page instead of a list
    if "/maps/place/" in current_url:
        print("[*] Redirected directly to place details view.")
        current_place_id = extract_place_id(current_url)
        if current_place_id not in scraped_urls:
            record = await extract_details(page, current_url, search_query, loc_info)
            if record:
                append_to_csv(record)
                scraped_urls.add(current_place_id)
                print(f"    -> SAVED: {record['Name']} | Phone: {record['Phone']} | Web: {record['Website']}")
        return

    # Find all listing links
    link_selector = config_farm_nz.SELECTORS["listing_link"]
    listings_count = await page.locator(link_selector).count()
    
    # Check if the first result is in NZ before scrolling (fail fast if fallback)
    if listings_count > 0:
        first_item = page.locator(link_selector).first
        try:
            expected_name = await first_item.get_attribute("aria-label")
            await first_item.scroll_into_view_if_needed()
            await first_item.click()
            
            # Wait for detail card to update
            name_matched = False
            for _ in range(15): # Try for 3 seconds (15 * 200ms)
                h1_locator = page.locator(config_farm_nz.SELECTORS["business_name"])
                if await h1_locator.count() > 0:
                    current_name = await h1_locator.first.inner_text()
                    current_name = current_name.strip()
                    if expected_name and (expected_name.lower() in current_name.lower() or current_name.lower() in expected_name.lower()):
                        name_matched = True
                        break
                await page.wait_for_timeout(200)
                
            # Extract address and verify
            addr_loc = page.locator(config_farm_nz.SELECTORS["address"])
            address = ""
            if await addr_loc.count() > 0:
                addr_label = await addr_loc.first.get_attribute("aria-label")
                address = addr_label.replace("Address:", "").strip() if addr_label else await addr_loc.first.inner_text()
                address = address.strip()
                
            if address:
                if not is_new_zealand_address(address):
                    print(f"[-] First listing is outside New Zealand ('{address}'). Skipping location.")
                    return
            else:
                print("    [*] First listing address was empty (load timeout). Proceeding to scroll results...")
        except Exception as check_err:
            print(f"[-] Error checking geofence on first listing: {check_err}")

    # Scroll the results list.
    await scroll_feed(page)
    
    # Find all listing links
    link_selector = config_farm_nz.SELECTORS["listing_link"]
    listings_count = await page.locator(link_selector).count()
    print(f"[*] Found {listings_count} listings in search results.")
    
    # Extract all URL links first
    urls = []
    for i in range(listings_count):
        try:
            href = await page.locator(link_selector).nth(i).get_attribute("href")
            if href:
                urls.append(href)
        except Exception as e:
            pass
            
    # Remove duplicate URLs from the current search viewport
    urls = list(dict.fromkeys(urls))
    
    # Scrape detail for each listing URL
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
                    for _ in range(15): # Try for 3 seconds (15 * 200ms)
                        h1_locator = page.locator(config_farm_nz.SELECTORS["business_name"])
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
                        print("      [-] Details card did not match. Will fallback to direct page navigation.")
                else:
                    await page.wait_for_timeout(2000)
                    clicked = True
                    
                await handle_captcha(page)
        except Exception as click_err:
            pass
            
        if not clicked:
            continue

        # Extract details from the page
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
            print(f"    [-] Exception during detail extraction: {parse_err}")
                
        # Random sleep to avoid rapid clicks
        await asyncio.sleep(random.uniform(config_farm_nz.MIN_DELAY, config_farm_nz.MAX_DELAY))

    if count_saved > 0:
        print(f"[+] Finished scan for query: Saved {count_saved} new entries.")

async def main():
    print("="*60)
    print("      NEW ZEALAND NAIL SALON GOOGLE MAPS SCRAPER")
    print("="*60)
    
    # Load previously scraped URLs
    scraped_urls = get_scraped_urls()
    print(f"[+] Loaded {len(scraped_urls)} existing entries from CSV.")
    
    # Load completed scans (to skip them instantly)
    completed_scans = load_completed_scans()
    
    # Retrieve locations and keywords
    locs = locations_nz.get_locations()
    keywords = config_farm_nz.KEYWORDS
    
    print(f"[+] Total target locations: {len(locs)}")
    print(f"[+] Search keywords: {keywords}")
    print(f"[+] Output CSV path: {config_farm_nz.OUTPUT_CSV}\n")
    
    async with async_playwright() as p:
        # We can specify channel="chrome" or "msedge" to launch the system's real browser
        # which has standard profiles/locales and is less likely to trigger IP redirects than headless/bare Chromium.
        browser = None
        for channel in ["chrome", "msedge", None]:
            try:
                chan_str = f"channel '{channel}'" if channel else "default Chromium"
                print(f"[*] Attempting to launch browser with {chan_str}...")
                launch_args = {
                    "headless": config_farm_nz.HEADLESS,
                    "slow_mo": config_farm_nz.SLOW_MO,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--lang=en-US,en"
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
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            geolocation={"latitude": -36.85, "longitude": 174.76},  # Default to Auckland, NZ coordinates
            permissions=["geolocation"]
        )
        
        page = await context.new_page()
        
        total_scans = len(locs) * len(keywords)
        scan_index = 0
        
        try:
            for loc in locs:
                for kw in keywords:
                    scan_index += 1
                    
                    # Skip if already completed in previous run
                    scan_key = (loc['name'].lower(), loc['state'].lower(), kw.lower())
                    if scan_key in completed_scans:
                        continue
                        
                    print(f"\n[Progress: {scan_index}/{total_scans}] Location: {loc['name']} | Keyword: '{kw}'")
                    success = await process_search(page, kw, loc, scraped_urls)
                    
                    # Mark completed and save to progress file only if search succeeded (did not return False)
                    if success is not False:
                        save_completed_scan(loc['name'], loc['state'], kw)
                    
                    # Random delay between search query shifts
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
            
    print(f"\n[+] Scraping session complete! Total unique entries now in CSV: {len(get_scraped_urls())}")
    print(f"[+] Results saved to: {config_farm_nz.OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main())
