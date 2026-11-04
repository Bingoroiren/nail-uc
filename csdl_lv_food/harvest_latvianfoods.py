# -*- coding: utf-8 -*-
"""
Harvest Latvian Foods Cluster Members (Latvijas Pārtikas Klasteris)
Source: https://latvianfoods.eu/en/our-members.html
Output: csdl_lv_food/database_latvianfoods.csv
"""

import sys
import re
import csv
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT_DIR / "csdl_lv_food" / "database_latvianfoods.csv"

URL = "https://latvianfoods.eu/en/our-members.html"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

FIELDNAMES = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).replace('\n', ' ').replace('\r', ' ')
    c = re.sub(r'\s+', ' ', c).strip()
    return c

def harvest_latvianfoods():
    print("=" * 70)
    print(" HARVESTING LATVIAN FOODS CLUSTER MEMBERS (latvianfoods.eu)")
    print(f" Source URL: {URL}")
    print("=" * 70)
    
    r = requests.get(URL, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        print(f"[ERROR] Failed to fetch {URL}, status: {r.status_code}")
        return []
        
    soup = BeautifulSoup(r.text, 'html.parser')
    cards = soup.select('.el-item')
    print(f"[*] Found {len(cards)} member cards.")
    
    results = []
    seen = set()
    
    for c in cards:
        # Title/Company name
        title_el = c.select_one('.el-title')
        if not title_el:
            continue
            
        raw_name = title_el.get_text(separator=' ').strip()
        comp_name = clean_company_name(raw_name)
        if not comp_name or len(comp_name) < 3:
            continue
            
        # Website
        web = ""
        link_el = c if c.name == 'a' else c.find('a', href=True)
        if link_el and link_el.has_attr('href'):
            h = link_el['href'].strip()
            if h.startswith('http') and not any(bad in h for bad in ['latvianfoods.eu', 'facebook.com']):
                web = h
                
        key = comp_name.lower()
        if key in seen:
            continue
        seen.add(key)
        
        results.append({
            'Company': comp_name,
            'Website': web,
            'Phone': "",
            'Email': "",
            'Address': "Latvia",
            'Category': "Food cluster member",
            'Source': "latvianfoods.eu",
            'Profile_URL': URL
        })
        
    print(f"[✔] Extracted {len(results)} companies from latvianfoods.eu.")
    
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
        
    print(f"[✔] Saved to: {OUTPUT_CSV}\n")
    return results

if __name__ == '__main__':
    harvest_latvianfoods()
