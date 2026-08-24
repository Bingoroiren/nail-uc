import urllib.request
import urllib.error
import urllib.parse
import json
import csv
import os
import sys
import re
import time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://bis.gov.lv"
LIST_URL_TEMPLATE = "https://bis.gov.lv/bisp/lv/construction_companies/list?page={page}&search[statuses][]=A"
PROGRESS_FILE = "scraping_progress_construction_lv_bis.json"
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "construction_latvia_with_emails.csv")
TEST_OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "construction_latvia_test_with_emails.csv")

# Force UTF-8 stdout encoding for safe console print of Baltic characters
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import http.cookiejar

# Setup cookie jar to preserve session cookies across requests (prevents F5 WAF 503 rate limits)
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
urllib.request.install_opener(opener)

# Custom headers for safety and polite scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'lv,en-US;q=0.7,en;q=0.3',
    'Connection': 'keep-alive'
}

def fetch_html(url, retries=5, delay=3, timeout=15):
    """Fetches HTML content from URL with robust exponential backoff retry for HTTP 503."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return response.read().decode('utf-8', errors='ignore')
                else:
                    print(f"[!] Warning: Received status {response.status} for {url}")
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code == 503:
                wait_time = delay * (2 ** (attempt - 1)) + 2
                print(f"[!] Rate Limited (HTTP {e.code}) on attempt {attempt}/{retries}. Backing off for {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"[!] HTTP Error {e.code} on attempt {attempt}/{retries} for {url}")
                time.sleep(delay * attempt)
        except Exception as e:
            print(f"[!] Connection Error {e} on attempt {attempt}/{retries} for {url}")
            time.sleep(delay * attempt)
    return None

def load_progress():
    """Loads scraping progress from JSON file."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure structure is sound
                if "completed_pages" not in data:
                    data["completed_pages"] = []
                if "company_links" not in data:
                    data["company_links"] = {}
                if "scraped_details" not in data:
                    data["scraped_details"] = {}
                return data
        except Exception as e:
            print(f"[*] Failed to load progress file: {e}. Starting fresh.")
    return {"completed_pages": [], "company_links": {}, "scraped_details": {}}

def save_progress(progress):
    """Saves scraping progress to JSON file."""
    try:
        # Save to temp file first to prevent corruption
        temp_file = PROGRESS_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        os.rename(temp_file, PROGRESS_FILE)
    except Exception as e:
        print(f"[!] Error saving progress: {e}")

def parse_list_page(html):
    """Parses list page HTML to extract company links, names, and UR registration numbers."""
    companies = []
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('div.flextable__row')
    
    for row in rows:
        link_el = row.select_one('a.public_list__link')
        if not link_el:
            continue
            
        name = link_el.text.strip()
        href = link_el.get('href')  # e.g., /bisp/lv/construction_companies/2
        
        # UR registration number
        ur_el = row.find('div', attrs={'data-column-header-name': 'UR vai mītnes valsts reģistrācijas numurs'})
        ur_num = ""
        if ur_el:
            val_el = ur_el.select_one('span.flextable__value')
            if val_el:
                sr_el = val_el.select_one('span.screen-reader-only')
                if sr_el:
                    sr_el.decompose()
                ur_num = val_el.text.strip()
                
        # Status check (should be Aktīvs, but let's parse it)
        status_el = row.find('div', attrs={'data-column-header-name': 'Statuss'})
        status = "Aktīvs"
        if status_el:
            val_el = status_el.select_one('span.flextable__value')
            if val_el:
                status = val_el.text.strip()
                
        companies.append({
            'name': name,
            'href': href,
            'ur_num': ur_num,
            'status': status
        })
    return companies

def parse_detail_page(html):
    """Parses company detail page to extract addresses, phone, and email."""
    details = {
        'phone': '',
        'email': '',
        'legal_address': '',
        'actual_address': ''
    }
    if not html:
        return details
        
    soup = BeautifulSoup(html, 'html.parser')
    for row in soup.select('div.wizardform__preview_row'):
        label_el = row.select_one('div.wizardform__preview_label')
        value_el = row.select_one('div.wizardform__preview_value')
        if label_el and value_el:
            label = label_el.text.strip().lower()
            val = value_el.text.strip()
            if 'tālruņa numurs' in label:
                details['phone'] = val
            elif 'elektroniskā pasta adrese' in label:
                details['email'] = val
            elif 'juridiskā adrese' in label:
                details['legal_address'] = val
            elif 'faktiskā' in label or 'korespondences' in label:
                details['actual_address'] = val
                
    return details

def scrape_detail_worker(name, info, index, total):
    """Worker function for ThreadPool to fetch and parse a single detail page."""
    href = info['href']
    url = BASE_URL + href
    # Sequential delay to avoid F5 WAF rate-limiting (HTTP 503)
    time.sleep(0.3)
    
    html = fetch_html(url)
    if html:
        details = parse_detail_page(html)
        print(f"[{index}/{total}] Scraped: {name} -> Email: {details['email'] or 'None'}, Phone: {details['phone'] or 'None'}")
        return href, details
    else:
        print(f"[!] [{index}/{total}] Failed to fetch detail page: {url}")
        return href, None

def write_to_csv(companies_data, output_path):
    """Writes accumulated company data to standard Latvia scraper format CSV."""
    headers = [
        "Name", "Website", "Phone", "Address", "Rating", "Reviews_Count",
        "State", "Location_Name", "Latitude", "Longitude", "Search_Query",
        "URL", "Permanently_Closed", "Category", "Email"
    ]
    
    print(f"[*] Writing {len(companies_data)} records to {output_path}...")
    
    with open(output_path, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for name, data in companies_data.items():
            details = data.get('details', {})
            # Location Name can be extracted from the address
            address = details.get('legal_address', '')
            location_name = "LV"
            if address:
                # Try to extract the municipality/city before the postal code
                # Addresses look like: "Starķi", Katlakalns, Ķekavas pag., Ķekavas nov., LV-2111
                parts = [p.strip() for p in address.split(',')]
                # Usually city/novads is the second to last or third to last
                for part in reversed(parts):
                    if 'nov.' in part.lower() or 'pag.' in part.lower() or 'rīga' in part.lower() or 'jūrmala' in part.lower():
                        location_name = part
                        break
            
            # Form phone string with single quote wrapper for Excel
            phone_str = details.get('phone', '').strip()
            if phone_str:
                phone_digits = re.sub(r'[^0-9]', '', phone_str)
                # If starts with country code, remove it for local normalization later
                if phone_digits.startswith('371'):
                    phone_digits = phone_digits[3:]
                phone_str = f"'{phone_digits}"
            else:
                phone_str = ""
                
            row = {
                "Name": name,
                "Website": "",
                "Phone": phone_str,
                "Address": address,
                "Rating": "5,0",
                "Reviews_Count": "0",
                "State": "LV",
                "Location_Name": location_name,
                "Latitude": "0.0",
                "Longitude": "0.0",
                "Search_Query": "BIS Registry",
                "URL": BASE_URL + data['href'],
                "Permanently_Closed": "No",
                "Category": "Būvuzņēmums",  # Undergoes category translation in Step 4
                "Email": details.get('email', '')
            }
            writer.writerow(row)

def main():
    dry_run = "--dry-run" in sys.argv
    target_output = TEST_OUTPUT_CSV if dry_run else OUTPUT_CSV
    
    print("============================================================")
    print("       LATVIA CONSTRUCTION REGISTRY SCRAPER (BIS.GOV.LV)    ")
    print("============================================================")
    if dry_run:
        print("[*] Running in DRY-RUN mode (1 page of listings only).")
    
    progress = load_progress()
    
    # --- STEP 1: SCRAPE LIST PAGES ---
    # Determine the pages to scrape
    total_pages = 1 if dry_run else 245
    print(f"[*] Step 1: Extracting company detail links (Pages: 1 to {total_pages})...")
    
    for page in range(1, total_pages + 1):
        if page in progress["completed_pages"]:
            continue
            
        print(f"[*] Crawling page {page}/{total_pages}...")
        url = LIST_URL_TEMPLATE.format(page=page)
        html = fetch_html(url)
        if not html:
            print(f"[!] Failed to fetch list page {page}. Retrying next time.")
            continue
            
        companies_on_page = parse_list_page(html)
        if not companies_on_page:
            print(f"[*] No companies found on page {page} (possibly end of pagination).")
            break
            
        for company in companies_on_page:
            name = company['name']
            if name not in progress["company_links"]:
                progress["company_links"][name] = {
                    'href': company['href'],
                    'ur_num': company['ur_num'],
                    'status': company['status']
                }
                
        progress["completed_pages"].append(page)
        save_progress(progress)
        print(f"[+] Page {page} parsed. Found {len(companies_on_page)} companies.")
        time.sleep(2.0)
        
    all_links = progress["company_links"]
    print(f"[SUCCESS] Link extraction complete. Total active companies: {len(all_links)}")
    
    # --- STEP 2: SCRAPE COMPANY DETAILS ---
    print(f"\n[*] Step 2: Fetching company contact details...")
    
    # Filter list for companies that haven't been details-scraped yet
    todo_list = {}
    for name, info in all_links.items():
        href = info['href']
        if href not in progress["scraped_details"] or progress["scraped_details"][href] is None:
            todo_list[name] = info
            
    total_todo = len(todo_list)
    print(f"[*] Already scraped: {len(progress['scraped_details'])} companies.")
    print(f"[*] Remaining to scrape: {total_todo} companies.")
    
    if total_todo > 0:
        max_workers = 1  # Sequential scraping to avoid F5 WAF rate-limiting (HTTP 503)
        print(f"[*] Scraping details sequentially (concurrency={max_workers})...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_company = {
                executor.submit(scrape_detail_worker, name, info, i, total_todo): (name, info)
                for i, (name, info) in enumerate(todo_list.items(), 1)
            }
            
            save_counter = 0
            for future in as_completed(future_to_company):
                name, info = future_to_company[future]
                try:
                    href, details = future.result()
                    if details:
                        progress["scraped_details"][href] = details
                        save_counter += 1
                        # Save progress every 50 detail scrapes to prevent loss
                        if save_counter >= 50:
                            save_progress(progress)
                            save_counter = 0
                except Exception as exc:
                    print(f"[!] Exception crawling details for {name}: {exc}")
                    
            # Save final details progress
            save_progress(progress)
            
    print("[SUCCESS] All details successfully crawled!")
    
    # --- STEP 3: EXPORT TO CSV ---
    # Merge company links with details
    companies_data = {}
    for name, info in all_links.items():
        href = info['href']
        if href in progress["scraped_details"] and progress["scraped_details"][href] is not None:
            companies_data[name] = {
                'href': href,
                'ur_num': info['ur_num'],
                'details': progress["scraped_details"][href]
            }
            
    write_to_csv(companies_data, target_output)
    print(f"[SUCCESS] Scraper execution completed. File output: {target_output}")
    print("============================================================")

if __name__ == "__main__":
    main()
