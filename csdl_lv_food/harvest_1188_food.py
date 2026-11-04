# -*- coding: utf-8 -*-
"""
Harvest Food Processing, Meat & Seafood Catalogs from 1188.lv
Catalogs:
1. Gaļas pārstrādes uzņēmumi (2020)
2. Gaļas izstrādājumi (2030)
3. Kautuves (3520)
4. Zivis, jūras veltes (7018)
5. Zivju pārstrādes uzņēmumi (6580)
6. Zivsaimniecība (6650)
Output: csdl_lv_food/database_1188_food.csv
"""

import sys
import re
import csv
import time
import urllib.parse
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT_DIR / "csdl_lv_food" / "database_1188_food.csv"

CATEGORIES = [
    ("Gaļas pārstrādes uzņēmumi", "https://www.1188.lv/katalogs/galas-parstrades-uznemumi-2020"),
    ("Gaļas izstrādājumi", "https://www.1188.lv/katalogs/galas-izstradajumi-2030"),
    ("Kautuves", "https://www.1188.lv/katalogs/kautuves-3520"),
    ("Zivis, jūras veltes", "https://www.1188.lv/katalogs/zivis-juras-veltes-7018"),
    ("Zivju pārstrādes uzņēmumi", "https://www.1188.lv/katalogs/zivju-parstrades-uznemumi-6580"),
    ("Zivsaimniecība", "https://www.1188.lv/katalogs/zivsaimnieciba-6650"),
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'lv,en-US;q=0.7,en;q=0.3'
}

JUNK_DOMAINS = {
    '1188.lv', 'viss.lv', 'crediweb.lv', 'lursoft.lv', 'facebook.com',
    'instagram.com', 'linkedin.com', 'twitter.com', 'youtube.com'
}

FIELDNAMES = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r'^[\"\'„“\s]+|[\"\'”\s]+$', '', c)
    c = re.sub(r'\s*\d+\s*$', '', c)
    return c.strip()

def clean_phone(phone_str):
    if not phone_str or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip().lstrip("'")
    p = re.sub(r'^(?:Tel|T\.|Tālr\.|Tālrunis)[:\s]*', '', p, flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('371'):
        return f"'+{digits}"
    elif (digits.startswith('6') or digits.startswith('2')) and len(digits) == 8:
        return f"'+371{digits}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"

def clean_email(email_str):
    if not email_str:
        return ""
    e = email_str.lower().strip().replace('%20', '').strip('.,;:()[]"\'')
    e = re.sub(r'^(?:e-mail\.|email\.|mailto:)', '', e)
    if '@' not in e or len(e) < 6:
        return ""
    if any(e.startswith(j) for j in ['info@1188.lv', 'viss@viss.lv', 'sentry@', 'noreply@']):
        return ""
    return e

def harvest_1188_food():
    print("=" * 70)
    print(" HARVESTING FOOD & SEAFOOD CATALOGS FROM 1188.LV")
    print("=" * 70)
    
    session = requests.Session()
    results = []
    seen = set()
    
    for cat_name, base_url in CATEGORIES:
        print(f"\n[*] Scanning Category: {cat_name} ({base_url})...")
        page_num = 1
        cat_count = 0
        
        while True:
            url = f"{base_url}?page={page_num}"
            try:
                r = session.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                cards = soup.select('.company')
                if not cards:
                    break
                    
                print(f"  Page {page_num}: Found {len(cards)} listings.", flush=True)
                for c in cards:
                    name_a = c.find('a', class_='name')
                    if not name_a:
                        continue
                    comp_name = clean_company_name(name_a.get_text(strip=True))
                    profile_url = name_a.get('href', '').strip()
                    if not profile_url:
                        continue
                        
                    phone = ""
                    email = ""
                    website = ""
                    address = ""
                    
                    try:
                        time.sleep(0.15)
                        r_det = session.get(profile_url, headers=HEADERS, timeout=12)
                        if r_det.status_code == 200:
                            s_det = BeautifulSoup(r_det.text, 'html.parser')
                            name_span = s_det.select_one('h1 span.name')
                            if name_span:
                                comp_name = clean_company_name(name_span.get_text(strip=True))
                                
                            tel_a = s_det.find('a', href=lambda h: h and h.startswith('tel:'))
                            if tel_a:
                                phone = clean_phone(tel_a['href'].replace('tel:', '').strip())
                                
                            mail_a = s_det.find('a', href=lambda h: h and h.startswith('mailto:'))
                            if mail_a:
                                email = clean_email(mail_a['href'].replace('mailto:', '').split('?')[0].strip())
                                
                            info_box = s_det.find(class_='company-info')
                            if info_box:
                                for a in info_box.find_all('a', href=True):
                                    h = a['href'].strip()
                                    if 'utm_medium=homepage' in h or 'utm_medium=screenshot' in h:
                                        p = urllib.parse.urlparse(h)
                                        website = f"{p.scheme}://{p.netloc}"
                                        break
                                if not website:
                                    for a in info_box.find_all('a', href=True):
                                        h = a['href'].strip()
                                        if h.startswith('http') and not any(ign in h.lower() for ign in JUNK_DOMAINS):
                                            p = urllib.parse.urlparse(h)
                                            website = f"{p.scheme}://{p.netloc}"
                                            break
                                            
                            addr_box = s_det.find(class_='address') or s_det.find(class_='company-address')
                            if addr_box:
                                address = addr_box.get_text(separator=', ', strip=True)
                    except Exception:
                        pass
                        
                    key = comp_name.lower()
                    if key in seen:
                        # Append category
                        for r_item in results:
                            if r_item['Company'].lower() == key and cat_name not in r_item['Category']:
                                r_item['Category'] += f", {cat_name}"
                                break
                        continue
                    seen.add(key)
                    cat_count += 1
                    
                    results.append({
                        'Company': comp_name,
                        'Website': website,
                        'Phone': phone,
                        'Email': email,
                        'Address': address or "Latvia",
                        'Category': f"Food - {cat_name}",
                        'Source': "1188.lv",
                        'Profile_URL': profile_url
                    })
                page_num += 1
            except Exception as e:
                print(f"  [!] Error on page {page_num}: {e}")
                break
                
        print(f"  --> Extracted {cat_count} new companies from {cat_name}.")
        
    print(f"\n[✔] Total unique companies from 1188.lv: {len(results)}")
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
        
    print(f"[✔] Saved to: {OUTPUT_CSV}\n")
    return results

if __name__ == '__main__':
    harvest_1188_food()
