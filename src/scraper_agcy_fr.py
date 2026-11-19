# -*- coding: utf-8 -*-
"""
GOOGLE MAPS SCRAPER - FRANCE RECRUITMENT & INTERIM AGENCIES (FR_AGCY_GMAP)
=============================================================================
Target:   Paris & Île-de-France International Recruitment & Temp/Interim Agencies
Output:   FR_AGCY_GMAP_0RAW.csv
Rules:    GEMINI.md (Rule 1, 2, 4, 5, 8, 10, 11, 12)
"""

import os
import sys
import re
import csv
import json
import random
import asyncio
import unicodedata
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config_agcy_fr as config
import locations_fr

PROGRESS_FILE = Path(config.PROGRESS_FILE)

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def extract_place_id(url):
    if not url:
        return ""
    m = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if m:
        return m.group(1).lower()
    return url.split('?')[0].lower()

def is_france_address(address):
    if not address:
        return False
    addr_lower = address.lower()
    if any(k in addr_lower for k in ["france", "paris", "750", "92", "93", "94", "île-de-france", "ile-de-france"]):
        return True
    return bool(re.search(r'\b(75\d{3}|92\d{3}|93\d{3}|94\d{3})\b', address))

def clean_french_phone(phone):
    if not phone:
        return ""
    p = str(phone).strip()
    p = re.sub(r'^(tel|phone|téléphone|tél|t)\s*[:.]?\s*', '', p, flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', p)
    if digits.startswith('0') and len(digits) == 10:
        digits = '+33' + digits[1:]
    elif digits.startswith('0033'):
        digits = '+33' + digits[4:]
    # Rule 2: Single quote prefix
    return f"'{digits}" if digits and not digits.startswith("'") else digits

def clean_website(url):
    if not url:
        return ""
    u = url.strip()
    if any(d in u.lower() for d in ["google.com", "gstatic.com", "facebook.com", "instagram.com", "linkedin.com"]):
        return ""
    return u

def load_progress():
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_queries": [], "seen_place_ids": []}

def save_progress(progress):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def load_existing_place_ids(csv_path):
    seen = set()
    p = Path(csv_path)
    if p.exists():
        try:
            with open(p, 'r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    place_id = row.get('Place_ID') or extract_place_id(row.get('Google_Maps_URL', ''))
                    if place_id:
                        seen.add(place_id.lower())
                    name = row.get('Name', '').strip().lower()
                    phone = row.get('Phone', '').strip()
                    if name and phone:
                        seen.add(f"{name}|{phone}")
        except Exception as e:
            print(f"[!] Warning reading existing CSV: {e}")
    return seen

async def handle_consent(page):
    try:
        consent_selectors = [
            "button:has-text('Tout accepter')",
            "button:has-text('Accept all')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Priнять все')",
            "form[action*='consent'] button"
        ]
        for sel in consent_selectors:
            btn = page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                print("[+] Đã tự động chấp nhận Google Consent!")
                await asyncio.sleep(2)
                return True
    except Exception:
        pass
    return False

async def scrape_france_agencies():
    output_path = Path(config.OUTPUT_CSV)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    seen_ids = load_existing_place_ids(output_path)
    progress = load_progress()
    for pid in progress.get("seen_place_ids", []):
        seen_ids.add(pid.lower())
        
    completed_queries = set(progress.get("completed_queries", []))
    
    fieldnames = [
        "Name", "Category", "Address", "Postal_Code", "City", "Country", 
        "Phone", "Website", "Rating", "Review_Count", "Google_Maps_URL", "Place_ID", "Search_Keyword", "Search_Location"
    ]
    
    if not output_path.exists() or output_path.stat().st_size == 0:
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
    user_data_dir = SRC_DIR.parent / "chrome_user_data" / "gmap_fr_agcy_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("🚀  KHỞI ĐỘNG BỘ CÀO GOOGLE MAPS TUYỂN DỤNG & INTERIM PHÁP (FR_AGCY_GMAP)")
    print(f"    - Tệp đầu ra: {config.OUTPUT_CSV}")
    print(f"    - Đã thu thập trước đó: {len(seen_ids)} doanh nghiệp")
    print("=" * 70)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1366, "height": 850},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Test navigation & handle consent
        await page.goto("https://www.google.com/maps?hl=fr", timeout=30000)
        await asyncio.sleep(2)
        await handle_consent(page)
        
        for loc in locations_fr.LOCATIONS:
            loc_name = loc["name"]
            for kw in config.KEYWORDS:
                query = f"{kw} in {loc_name}, France"
                query_key = f"{loc_name}::{kw}"
                if query_key in completed_queries:
                    continue
                    
                print(f"\n🔍 [TÌM KIẾM] {query}")
                search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=fr"
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3)
                    await handle_consent(page)
                except Exception as e:
                    print(f"[!] Lỗi truy cập: {e}")
                    continue
                    
                # Scroll loop
                feed = page.locator("div[role='feed']")
                if await feed.count() > 0:
                    for _ in range(6):
                        await feed.evaluate("el => el.scrollBy(0, 1000)")
                        await asyncio.sleep(1.5)
                        
                # Extract listing links
                cards = page.locator("a[href*='/maps/place/']")
                count = await cards.count()
                print(f"    - Tìm thấy {count} thẻ kết quả.")
                
                urls_to_visit = []
                for i in range(count):
                    try:
                        href = await cards.nth(i).get_attribute("href")
                        if href and "/maps/place/" in href:
                            pid = extract_place_id(href)
                            if pid and pid not in seen_ids:
                                urls_to_visit.append(href)
                                seen_ids.add(pid)
                    except Exception:
                        pass
                        
                print(f"    - Cần bóc tách chi tiết: {len(urls_to_visit)} địa điểm mới.")
                new_records = []
                for u in urls_to_visit:
                    try:
                        await page.goto(u, wait_until="domcontentloaded", timeout=25000)
                        await asyncio.sleep(1.5)
                        
                        # Name
                        name_el = page.locator("h1.DUwDvf").first
                        name = (await name_el.inner_text()).strip() if await name_el.count() > 0 else ""
                        if not name or is_blacklisted_company(name):
                            continue
                            
                        # Category
                        cat_el = page.locator("button.DkEaL").first
                        category = (await cat_el.inner_text()).strip() if await cat_el.count() > 0 else ""
                        
                        # Category filter check
                        if config.ALLOWED_CATEGORIES:
                            cat_match = any(c.lower() in category.lower() for c in config.ALLOWED_CATEGORIES)
                            # Nếu category trống hoặc không khớp, kiểm tra thêm trong tên
                            if not cat_match and not any(k.lower() in name.lower() for k in ["recrutement", "interim", "intérim", "rh", "travail"]):
                                continue
                                
                        # Address
                        addr_el = page.locator("button[data-item-id*='address'] div.fontBodyMedium").first
                        address = (await addr_el.inner_text()).strip() if await addr_el.count() > 0 else ""
                        
                        postal_code = ""
                        pc_m = re.search(r'\b(75\d{3}|92\d{3}|93\d{3}|94\d{3})\b', address)
                        if pc_m:
                            postal_code = pc_m.group(1)
                            
                        # Phone
                        phone_el = page.locator("button[data-item-id*='phone:tel:'] div.fontBodyMedium").first
                        phone_raw = (await phone_el.inner_text()).strip() if await phone_el.count() > 0 else ""
                        phone = clean_french_phone(phone_raw)
                        
                        # Website
                        web_el = page.locator("a[data-item-id='authority']").first
                        website_raw = (await web_el.get_attribute("href")).strip() if await web_el.count() > 0 else ""
                        website = clean_website(website_raw)
                        
                        # Rating & Reviews
                        rating = ""
                        reviews = ""
                        r_el = page.locator("div.F7nice span[aria-hidden='true']").first
                        if await r_el.count() > 0:
                            rating = (await r_el.inner_text()).strip().replace(',', '.')
                        rev_el = page.locator("div.F7nice span:has-text('(')").first
                        if await rev_el.count() > 0:
                            rev_text = (await rev_el.inner_text()).strip()
                            rev_m = re.search(r'[\d\s]+', rev_text)
                            if rev_m:
                                reviews = rev_m.group(0).replace(' ', '')
                                
                        place_id = extract_place_id(page.url) or extract_place_id(u)
                        
                        rec = {
                            "Name": name,
                            "Category": category,
                            "Address": address,
                            "Postal_Code": postal_code,
                            "City": "Paris",
                            "Country": "France",
                            "Phone": phone,
                            "Website": website,
                            "Rating": rating,
                            "Review_Count": reviews,
                            "Google_Maps_URL": page.url,
                            "Place_ID": place_id,
                            "Search_Keyword": kw,
                            "Search_Location": loc_name
                        }
                        new_records.append(rec)
                        print(f"      [+] {name} | Cat: {category} | Phone: {phone} | Web: {website[:30]}")
                        
                        # Save incrementally (Rule 5)
                        with open(output_path, 'a', encoding='utf-8-sig', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writerow(rec)
                            f.flush()
                            
                    except Exception as e:
                        print(f"      [!] Lỗi bóc tách card: {e}")
                        
                completed_queries.add(query_key)
                progress["completed_queries"] = list(completed_queries)
                progress["seen_place_ids"] = list(seen_ids)
                save_progress(progress)
                print(f"    --> Đã lưu tích lũy {len(new_records)} doanh nghiệp từ query này.")
                
        await context.close()
        print("\n🎉 Hoàn thành cào Google Maps Tuyển Dụng & Interim Pháp!")

if __name__ == "__main__":
    asyncio.run(scrape_france_agencies())

