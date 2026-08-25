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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_factory_ie
import locations_ie

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
    if os.path.exists(config_factory_ie.OUTPUT_CSV):
        try:
            with open(config_factory_ie.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Error loading existing CSV records: {e}")
    return scraped_urls

def is_ireland_address(address):
    """Verifies if an address is in Ireland."""
    if not address:
        return False
    addr_lower = address.lower()
    if "ireland" in addr_lower or ", ie" in addr_lower or "co. " in addr_lower or "county " in addr_lower:
        return True
    
    ie_counties_cities = [
        "dublin", "cork", "galway", "limerick", "waterford", "kilkenny", "killarney", 
        "wexford", "sligo", "donegal", "athlone", "dundalk", "drogheda", "bray", 
        "tralee", "ennis", "castlebar", "westport", "letterkenny", "mallow", "tullamore", 
        "navan", "carlow", "clonmel", "mullingar", "naas", "cobh", "kinsale", "roscommon",
        "leinster", "munster", "connacht", "ulster", "monaghan", "cavan", "eircode"
    ]
    if any(city in addr_lower for city in ie_counties_cities):
        return True
        
    if re.search(r'\b[a-z0-9]{3}\s?[a-z0-9]{4}\b', addr_lower):
        return True
        
    return False

def append_to_csv(row_dict):
    """Appends a single scraped record to the output CSV file."""
    file_exists = os.path.isfile(config_factory_ie.OUTPUT_CSV)
    try:
        with open(config_factory_ie.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

PROGRESS_FILE = config_factory_ie.PROGRESS_FILE

def load_completed_scans():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
            
    if os.path.exists(config_factory_ie.OUTPUT_CSV):
        try:
            print("[*] Progress file not found. Initializing from existing CSV data...")
            completed_list = []
            with open(config_factory_ie.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), config_factory_ie.KEYWORDS[0].lower())
                        if pair not in completed_list:
                            completed_list.append(pair)
            save_completed_scans(set(completed_list))
            return set(completed_list)
        except Exception as e:
            print(f"[-] Error initializing progress file from CSV: {e}")
            
    return set()

def save_completed_scans(completed_set):
    try:
        data = {"completed": list(completed_set)}
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Error saving progress file: {e}")

async def handle_cookie_consent(page):
    try:
        consent_button = await page.query_selector('form[action*="consent"] button, button[aria-label*="Accept all"], button[aria-label*="Chấp nhận tất cả"]')
        if consent_button:
            await consent_button.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def scroll_feed(page, results_selector):
    feed = await page.query_selector(results_selector)
    if not feed:
        return 0
        
    prev_height = 0
    same_count = 0
    
    for _ in range(25):
        await page.evaluate('(element) => element.scrollTop = element.scrollHeight', feed)
        await page.wait_for_timeout(random.randint(600, 1000))
        
        end_text = await page.content()
        if "You've reached the end of the list" in end_text or "Đã tới cuối danh sách" in end_text:
            break
            
        curr_height = await page.evaluate('(element) => element.scrollHeight', feed)
        if curr_height == prev_height:
            same_count += 1
            if same_count >= 3:
                break
        else:
            same_count = 0
            prev_height = curr_height

async def scrape_location_keyword(context, location, keyword, scraped_urls, completed_scans):
    loc_key = (location["name"].strip().lower(), location["state"].strip().lower(), keyword.strip().lower())
    if loc_key in completed_scans:
        print(f"[*] Skipping {location['name']} ({location['state']}) for '{keyword}' - already completed.")
        return 0

    page = await context.new_page()
    page.set_default_timeout(config_factory_ie.TIMEOUT)
    
    query = f"{keyword} in {location['name']}, {location['state']}, Ireland"
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/maps/search/{encoded_query}/@{location['lat']},{location['lng']},{location['zoom']}z?hl=en"
    
    print(f"\n[+] Searching: '{query}' ({location['name']}, {location['state']}) [Zoom: {location['zoom']}]")
    
    scraped_in_this_session = 0
    
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await handle_cookie_consent(page)
        
        try:
            await page.wait_for_selector(config_factory_ie.SELECTORS["results_container"], timeout=8000)
        except Exception:
            if await page.query_selector(config_factory_ie.SELECTORS["business_name"]):
                pass
            else:
                print(f"[-] No results container found for {query}.")
                completed_scans.add(loc_key)
                save_completed_scans(completed_scans)
                await page.close()
                return 0

        # Scroll to load all feed listings
        await scroll_feed(page, config_factory_ie.SELECTORS["results_container"])
        
        # Collect listing links
        links = await page.query_selector_all(config_factory_ie.SELECTORS["listing_link"])
        listing_urls = []
        for link in links:
            href = await link.get_attribute("href")
            if href:
                place_id = extract_place_id(href)
                if place_id and place_id not in scraped_urls:
                    listing_urls.append(href)
                    
        print(f"[+] Found {len(listing_urls)} new listings to extract in {location['name']}.")

        for i, listing_url in enumerate(listing_urls, 1):
            place_id = extract_place_id(listing_url)
            if place_id in scraped_urls:
                continue
                
            try:
                await page.goto(listing_url, wait_until="domcontentloaded")
                await page.wait_for_selector(config_factory_ie.SELECTORS["business_name"], timeout=5000)
                
                # Extract Name
                name_elem = await page.query_selector(config_factory_ie.SELECTORS["business_name"])
                name = await name_elem.inner_text() if name_elem else ""
                
                # Permanently Closed check
                perm_closed = "No"
                closed_elem = await page.query_selector('span.pk475, span:has-text("Permanently closed"), span:has-text("Đóng cửa vĩnh viễn")')
                if closed_elem:
                    perm_closed = "Yes"
                
                # Extract Category
                category = ""
                cat_elems = await page.query_selector_all(config_factory_ie.SELECTORS["category"])
                for cat_elem in cat_elems:
                    text = await cat_elem.inner_text()
                    text_clean = text.strip().replace("·", "").replace("•", "").strip()
                    if text_clean and not text_clean.startswith("$$") and not text_clean.startswith("€") and not re.search(r'\d', text_clean):
                        category = text_clean
                        break
                        
                # Extract Address
                address = ""
                addr_elem = await page.query_selector(config_factory_ie.SELECTORS["phone"] + ' ~ div, button[data-item-id^="address"]')
                if addr_elem:
                    address = await addr_elem.inner_text()
                    
                # Verify address is in Ireland
                if address and not is_ireland_address(address):
                    print(f"    [-] Skipping non-Ireland address: {name} ({address})")
                    scraped_urls.add(place_id)
                    continue

                # Extract Website
                website = ""
                web_elem = await page.query_selector(config_factory_ie.SELECTORS["website"])
                if web_elem:
                    website = await web_elem.get_attribute("href") or ""
                    
                # Extract Phone
                phone = ""
                phone_elem = await page.query_selector(config_factory_ie.SELECTORS["phone"])
                if phone_elem:
                    phone_aria = await phone_elem.get_attribute("aria-label") or ""
                    phone_text = await phone_elem.inner_text() or ""
                    phone = phone_aria.replace("Phone:", "").replace("Điện thoại:", "").strip() if phone_aria else phone_text.strip()

                # Extract Rating & Reviews
                rating = ""
                rating_elem = await page.query_selector(config_factory_ie.SELECTORS["rating"])
                if rating_elem:
                    rating = await rating_elem.inner_text()
                    
                reviews_count = ""
                rev_elem = await page.query_selector(config_factory_ie.SELECTORS["reviews_count"])
                if rev_elem:
                    rev_aria = await rev_elem.get_attribute("aria-label") or ""
                    rev_match = re.search(r'([\d,]+)', rev_aria)
                    if rev_match:
                        reviews_count = rev_match.group(1).replace(",", "")
                        
                data_row = {
                    "Name": name,
                    "Category": category,
                    "Address": address,
                    "Phone": f"'{phone}" if phone else "",
                    "Website": website,
                    "Rating": rating,
                    "Reviews_Count": reviews_count,
                    "State": location["state"],
                    "Location_Name": location["name"],
                    "URL": listing_url,
                    "Permanently_Closed": perm_closed
                }

                append_to_csv(data_row)
                scraped_urls.add(place_id)
                scraped_in_this_session += 1
                print(f"    [{i}/{len(listing_urls)}] Scraped: {name} | Category: {category} | Web: {'Yes' if website else 'No'}")
                
            except Exception as e:
                print(f"    [-] Error extracting listing {listing_url}: {e}")
                scraped_urls.add(place_id)
                
            await asyncio.sleep(random.uniform(config_factory_ie.MIN_DELAY, config_factory_ie.MAX_DELAY))

        completed_scans.add(loc_key)
        save_completed_scans(completed_scans)

    except Exception as e:
        print(f"[-] Error searching query '{query}': {e}")
    finally:
        await page.close()
        
    return scraped_in_this_session

async def main():
    print("==================================================================")
    print("  IRELAND FACTORIES & ELECTRONICS/SEMICONDUCTOR MAPS SCRAPER     ")
    print("==================================================================")
    
    locations = locations_ie.get_locations()
    keywords = config_factory_ie.KEYWORDS
    
    scraped_urls = get_scraped_urls()
    completed_scans = load_completed_scans()
    
    print(f"[*] Total location grid points: {len(locations)}")
    print(f"[*] Total search keywords: {len(keywords)}")
    print(f"[*] Loaded {len(scraped_urls)} existing business Place IDs from CSV.")
    print(f"[*] Loaded {len(completed_scans)} completed (location, keyword) scans.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config_factory_ie.HEADLESS, slow_mo=config_factory_ie.SLOW_MO)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        total_scraped = 0
        for kw in keywords:
            print(f"\n==========================================")
            print(f"  PROCESSING KEYWORD: '{kw}'")
            print(f"==========================================")
            for loc in locations:
                count = await scrape_location_keyword(context, loc, kw, scraped_urls, completed_scans)
                total_scraped += count
                
        await context.close()
        await browser.close()
        
    print(f"\n[SUCCESS] Scraping completed! Total new listings scraped: {total_scraped}")

if __name__ == "__main__":
    asyncio.run(main())
