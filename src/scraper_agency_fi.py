import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup

# Import local modules dynamically
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config_agency_fi

# Set console output encoding to UTF-8
if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def fetch_member_list():
    """Fetches the official HELA member directory HTML and parses all company names and website URLs."""
    url = config_agency_fi.SOURCE_URL
    print(f"[*] Fetching HELA Finland Agency Directory from: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"[-] Failed to fetch directory page: {e}")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    
    # Locate member content blocks
    agency_list = []
    seen_websites = set()
    
    # Find all <a> tags within the entry-content container
    content_div = soup.find('div', class_='entry-content')
    if not content_div:
        content_div = soup

    links = content_div.find_all('a', href=True)
    
    for a in links:
        href = a['href'].strip()
        name = a.get_text(strip=True)
        
        # Skip internal menu links, empty text, or non-company links
        if not href or not name or len(name) < 2:
            continue
            
        if any(skip_term in href for skip_term in ['henkilostoala.fi', 'wp-content', 'javascript:', 'mailto:', '#', 'facebook.com', 'twitter.com', 'linkedin.com']):
            continue
            
        # Ensure valid URL format
        if not href.startswith(('http://', 'https://')):
            href = 'http://' + href

        clean_url = href.split('?')[0].rstrip('/')
        if clean_url.lower() in seen_websites:
            continue
            
        seen_websites.add(clean_url.lower())
        
        agency_list.append({
            "Business_Name": name,
            "Category": config_agency_fi.DEFAULT_CATEGORY_FI,
            "Address": "Phần Lan (Finland)",
            "Phone": "",
            "Website": href,
            "URL": href,
            "Search_Query": f"HELA Member Directory - {name}"
        })

    return agency_list

def save_to_csv(agencies, test_mode=False):
    os.makedirs(os.path.dirname(config_agency_fi.OUTPUT_CSV), exist_ok=True)
    
    if test_mode:
        agencies = agencies[:10]
        print(f"[!] TEST MODE ACTIVE: Limiting output to top {len(agencies)} records.")

    fieldnames = [
        "Business_Name", "Category", "Address", "Phone", "Website", "URL", "Search_Query"
    ]
    
    try:
        with open(config_agency_fi.OUTPUT_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(agencies)
        print(f"[+] Successfully saved {len(agencies)} Finland recruitment agencies to: {config_agency_fi.OUTPUT_CSV}")
    except Exception as e:
        print(f"[-] Error writing raw CSV: {e}")

def main():
    test_mode = "--test" in sys.argv
    print("==================================================")
    print("[*] Initialized Finland Recruitment Agency Directory Scraper (HELA).")
    print("==================================================")
    
    agencies = fetch_member_list()
    print(f"[+] Extracted total {len(agencies)} member agencies from Henkilöstöala HELA.")
    
    save_to_csv(agencies, test_mode=test_mode)
    
    print("\n==================================================")
    print("[SUCCESS] Finland Agency Directory Scraping Completed.")
    print("==================================================")

if __name__ == "__main__":
    main()
