# -*- coding: utf-8 -*-
"""
Harvest European Commission TRACES NT - Approved Food Establishments in Latvia
Source: https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/index#!/search?classificationSectionChapter=food&countryCode=LV
Output: csdl_lv_food/database_traces_nt.csv
"""

import sys
import re
import csv
import json
import time
from pathlib import Path
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT_DIR / "csdl_lv_food" / "database_traces_nt.csv"

SECTIONS = [
    ("RPM", "Meat products"),
    ("RM", "Meat of domestic ungulates"),
    ("MM", "Minced meat, meat preparations and MSM"),
    ("PM", "Meat from poultry and lagomorphs"),
    ("GM", "Meat of farmed game"),
    ("FFP", "Fishery products"),
    ("MMP", "Raw milk and dairy products"),
    ("EEP", "Eggs and egg products"),
    ("GEN", "General activity establishment"),
    ("FAT", "Rendered animal fats and greaves"),
    ("GEL", "Gelatine"),
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9,lv;q=0.8'
}

FIELDNAMES = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r"^['\"„“”«»]+|['\"„“”«»]+$", "", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c

def harvest_traces_food():
    print("=" * 70)
    print(" HARVESTING APPROVED FOOD ESTABLISHMENTS FROM EC TRACES NT (LATVIA)")
    print("=" * 70)
    
    results = []
    seen = set()
    total_found = 0
    
    for code, sec_name in SECTIONS:
        url = f"https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/establishments/LV/{code}?max=1000&offset=0&sort=name.value"
        print(f"[*] Querying section [{code}] {sec_name}...", end="", flush=True)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                print(f" Failed (HTTP {r.status_code})")
                continue
                
            data = r.json()
            items = data.get('items', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            print(f" Found {len(items)} establishments.")
            total_found += len(items)
            
            for it in items:
                comp_raw = it.get('operatorName') or ""
                comp = clean_company_name(comp_raw)
                if not comp or len(comp) < 3:
                    continue
                    
                # Extract address
                addr_obj = it.get('address') or {}
                street_obj = addr_obj.get('street') or {}
                street_val = street_obj.get('value') or "" if isinstance(street_obj, dict) else str(street_obj)
                
                city_obj = addr_obj.get('cityReference') or {}
                postcode = city_obj.get('postalCode') or ""
                city_name = city_obj.get('name') or ""
                country_obj = city_obj.get('country') or {}
                country_name = country_obj.get('translation') or "Latvia"
                
                # Filter to only keep Latvia establishments
                if country_name.lower() not in ['latvia', 'latvija', 'lv']:
                    continue
                    
                addr_parts = [p.strip() for p in [street_val, city_name, postcode, country_name] if p and p.strip()]
                full_addr = ", ".join(addr_parts)
                
                key = comp.lower()
                if key in seen:
                    # Append category if new
                    for r_item in results:
                        if r_item['Company'].lower() == key:
                            if sec_name not in r_item['Category']:
                                r_item['Category'] += f", {sec_name}"
                            break
                    continue
                seen.add(key)
                
                results.append({
                    'Company': comp,
                    'Website': "",
                    'Phone': "",
                    'Email': "",
                    'Address': full_addr,
                    'Category': f"Food - {sec_name}",
                    'Source': "TRACES NT (EC)",
                    'Profile_URL': f"https://webgate.ec.europa.eu/tracesnt/directory/listing/establishment/publication/index#!/view/LV/{code}"
                })
        except Exception as e:
            print(f" Error: {e}")
            
    print(f"\n[✔] Total establishments returned by API: {total_found}")
    print(f"[✔] Total unique companies after deduplication: {len(results)}")
    
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
        
    print(f"[✔] Saved to: {OUTPUT_CSV}\n")
    return results

if __name__ == '__main__':
    harvest_traces_food()
