import asyncio
import csv
import json
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Import local modules dynamically
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_farm_no
import locations_no

# Set console output encoding to UTF-8
if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
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
    """Loads already scraped business Place IDs from CSV file to avoid duplicate entries."""
    scraped_urls = set()
    if os.path.exists(config_farm_no.OUTPUT_CSV):
        try:
            with open(config_farm_no.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}")
    return scraped_urls

def is_norway_address(address):
    """Verifies if an address is located in Norway (Norge)."""
    if not address:
        return False
    addr_lower = address.lower()
    if "norge" in addr_lower or "norway" in addr_lower or ", no" in addr_lower or " nor" in addr_lower:
        return True
    
    no_states_cities = [
        "oslo", "viken", "innlandet", "vestfold", "telemark", "agder", "rogaland", 
        "vestland", "møre og romsdal", "trøndelag", "nordland", "troms", "finnmark",
        "bergen", "stavanger", "trondheim", "drammen", "fredrikstad", "kristiansand",
        "sandnes", "tromsø", "skien", "ålesund", "larvik", "tønsberg", "hamar", "bodø",
        "haugesund", "molde", "harstad", "horten", "kristiansund", "gjøvik", "elverum"
    ]
    if any(city in addr_lower for city in no_states_cities):
        return True
        
    # Check 4-digit Norwegian postal code format (e.g. 0150, 4005, 5003, 7010)
    if re.search(r'\b\d{4}\b', addr_lower):
        return True
        
    return False

def append_to_csv(row_dict):
    """Appends a single scraped record to the raw CSV file."""
    os.makedirs(os.path.dirname(config_farm_no.OUTPUT_CSV), exist_ok=True)
    file_exists = os.path.isfile(config_farm_no.OUTPUT_CSV)
    try:
        with open(config_farm_no.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

PROGRESS_FILE = config_farm_no.PROGRESS_FILE

def load_completed_scans():
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
            
    if os.path.exists(config_farm_no.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...")
            completed_list = []
            with open(config_farm_no.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    search_query = row.get('Search_Query', '')
                    if loc_name and state:
                        found_kw = ""
                        if search_query:
                            for kw in config_farm_no.KEYWORDS:
                                if kw.lower() in search_query.lower():
                                    found_kw = kw
                                    break
                        if not found_kw:
                            found_kw = config_farm_no.KEYWORDS[0]
                            
                        pair = [loc_name.strip(), state.strip(), found_kw]
                        pair_lower = (loc_name.strip().lower(), state.strip().lower(), found_kw.lower())
                        if pair_lower not in [(x[0].lower(), x[1].lower(), x[2].lower()) for x in completed_list]:
                            completed_list.append(pair)
            
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=2, ensure_ascii=False)
            return set((x[0].lower(), x[1].lower(), x[2].lower()) for x in completed_list)
        except Exception as e:
            print(f"[-] Error parsing CSV for progress: {e}")
            
    return set()

def save_completed_scan(loc_name, state, keyword):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    completed_list = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed_list = data.get("completed", [])
        except Exception:
            completed_list = []
            
    new_item = [loc_name, state, keyword]
    new_item_lower = (loc_name.lower(), state.lower(), keyword.lower())
    if new_item_lower not in [(x[0].lower(), x[1].lower(), x[2].lower()) for x in completed_list]:
        completed_list.append(new_item)
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"completed": completed_list}, f, indent=2, ensure_ascii=False)

def is_category_allowed(category_str):
    """Strictly checks if the category matches allowed Norway farm & aquaculture tags."""
    if not category_str:
        return False
    cat_lower = category_str.lower().strip()
    
    # Check exact or substring match with ALLOWED_CATEGORIES
    for allowed in config_farm_no.ALLOWED_CATEGORIES:
        if allowed in cat_lower or cat_lower in allowed:
            return True
    return False

async def scrape_location_keyword(page, location, keyword, scraped_urls, completed_scans):
    loc_name = location["name"]
    state = location["state"]
    lat = location["lat"]
    lng = location["lng"]
    zoom = location.get("zoom", 11)
    
    scan_key = (loc_name.lower(), state.lower(), keyword.lower())
    if scan_key in completed_scans:
        print(f"[*] Skipping completed scan: '{keyword}' in {loc_name}, {state}")
        return
        
    search_query = f"{keyword} in {loc_name}, {state}, Norway"
    encoded_query = urllib.parse.quote(search_query)
    
    # Norwegian map URL with zoom level=11 or 10
    url = f"https://www.google.com/maps/search/{encoded_query}/@{lat},{lng},{zoom}z?hl=no"
    
    print(f"\n==================================================")
    print(f"[*] Searching: '{keyword}' in {loc_name}, {state}")
    print(f"[*] URL: {url}")
    print(f"==================================================")
    
    try:
        await page.goto(url, timeout=config_farm_no.TIMEOUT)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"[-] Failed to load search page: {e}")
        save_completed_scan(loc_name, state, keyword)
        completed_scans.add(scan_key)
        return
        
    # Handle Cookie Consent modal if present
    try:
        consent_btn = page.locator('form[action*="consent"] button, button[aria-label*="Godta alle"], button[aria-label*="Accept all"]')
        if await consent_btn.count() > 0:
            await consent_btn.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    results_container = page.locator(config_farm_no.SELECTORS["results_container"])
    try:
        await results_container.wait_for(state="visible", timeout=10000)
    except Exception:
        print(f"[-] No results container found for {search_query}")
        save_completed_scan(loc_name, state, keyword)
        completed_scans.add(scan_key)
        return

    # Scroll results panel to load all listings
    print("[*] Scrolling search results panel...")
    previous_height = 0
    same_height_count = 0
    max_scrolls = 20
    
    for _ in range(max_scrolls):
        try:
            await results_container.evaluate('el => el.scrollTop = el.scrollHeight')
            await page.wait_for_timeout(1500)
            
            end_elem = page.locator('span.Hv2fv, div.PbV75e')
            if await end_elem.count() > 0:
                break
                
            current_height = await results_container.evaluate('el => el.scrollHeight')
            if current_height == previous_height:
                same_height_count += 1
                if same_height_count >= 3:
                    break
            else:
                same_height_count = 0
            previous_height = current_height
        except Exception:
            break

    links = await page.locator(config_farm_no.SELECTORS["listing_link"]).all()
    print(f"[+] Found {len(links)} potential listings.")
    
    extracted_count = 0
    for i, link in enumerate(links):
        try:
            href = await link.get_attribute("href")
            place_id = extract_place_id(href)
            
            if place_id and place_id in scraped_urls:
                continue
                
            await link.click()
            await page.wait_for_timeout(random.uniform(1500, 2500))
            
            # Extract details
            name_elem = page.locator(config_farm_no.SELECTORS["business_name"])
            if await name_elem.count() == 0:
                continue
            biz_name = (await name_elem.first.inner_text()).strip()
            
            # Category extraction
            cat_elem = page.locator(config_farm_no.SELECTORS["category"])
            category = ""
            if await cat_elem.count() > 0:
                category = (await cat_elem.first.inner_text()).replace('·', '').strip()
                
            # STRICT CATEGORY FILTERING
            if not is_category_allowed(category):
                print(f"  [-] Skipping '{biz_name}': Category '{category}' NOT in allowed Norway farm tags.")
                if place_id:
                    scraped_urls.add(place_id)
                continue

            # Address extraction
            addr_elem = page.locator(config_farm_no.SELECTORS["address"])
            address = ""
            if await addr_elem.count() > 0:
                address = (await addr_elem.first.inner_text()).strip()
                
            # Norway Address Validation
            if address and not is_norway_address(address):
                print(f"  [-] Skipping '{biz_name}': Address '{address}' is not in Norway.")
                if place_id:
                    scraped_urls.add(place_id)
                continue

            # Phone extraction
            phone_elem = page.locator(config_farm_no.SELECTORS["phone"])
            phone = ""
            if await phone_elem.count() > 0:
                phone = (await phone_elem.first.inner_text()).strip()

            # Website extraction
            web_elem = page.locator(config_farm_no.SELECTORS["website"])
            website = ""
            if await web_elem.count() > 0:
                website = await web_elem.first.get_attribute("href")

            # Rating & Reviews
            rating_elem = page.locator(config_farm_no.SELECTORS["rating"])
            rating = ""
            if await rating_elem.count() > 0:
                rating = (await rating_elem.first.inner_text()).strip()

            reviews_elem = page.locator(config_farm_no.SELECTORS["reviews_count"])
            reviews_count = ""
            if await reviews_elem.count() > 0:
                reviews_raw = await reviews_elem.first.inner_text()
                match = re.search(r'\d[\d,\.]*', reviews_raw)
                if match:
                    reviews_count = match.group(0).replace(',', '').replace('.', '')

            row = {
                "Location_Name": loc_name,
                "State": state,
                "Business_Name": biz_name,
                "Category": category,
                "Rating": rating,
                "Reviews_Count": reviews_count,
                "Address": address,
                "Phone": phone,
                "Website": website if website else "",
                "URL": href if href else "",
                "Search_Query": search_query
            }
            
            append_to_csv(row)
            extracted_count += 1
            if place_id:
                scraped_urls.add(place_id)
                
            print(f"  [+] Saved [{extracted_count}]: '{biz_name}' ({category}) | Phone: {phone} | Web: {website}")
            
        except Exception as e:
            print(f"  [-] Error extracting listing {i+1}: {e}")
            continue

    save_completed_scan(loc_name, state, keyword)
    completed_scans.add(scan_key)
    print(f"[*] Completed search for '{keyword}' in {loc_name}. Extracted {extracted_count} valid farm/aquaculture listings.")

async def main():
    scraped_urls = get_scraped_urls()
    completed_scans = load_completed_scans()
    
    print(f"[*] Initialized Norway Farm & Aquaculture Scraper.")
    print(f"[*] Loaded {len(scraped_urls)} existing Place IDs.")
    print(f"[*] Loaded {len(completed_scans)} completed scan pairs.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config_farm_no.HEADLESS,
            slow_mo=config_farm_no.SLOW_MO
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="no-NO",
            timezone_id="Europe/Oslo"
        )
        page = await context.new_page()

        for location in locations_no.LOCATIONS:
            for keyword in config_farm_no.KEYWORDS:
                await scrape_location_keyword(page, location, keyword, scraped_urls, completed_scans)
                await asyncio.sleep(random.uniform(config_farm_no.MIN_DELAY, config_farm_no.MAX_DELAY))

        await browser.close()
        print("\n==================================================")
        print("[SUCCESS] Norway Farm Scraper session completed.")
        print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
