# -*- coding: utf-8 -*-
"""
Harvest Lithuania Fisheries and Fish Products from Rekvizitai.vz.lt via Persistent Chrome Context
Target: https://rekvizitai.vz.lt/imones/zuvininkyste_zuvies_produktai/1/

Fixes:
- Uses launch_persistent_context with user_data_dir to preserve Cloudflare clearance cookies (no repeat challenges).
- Removes navigator.webdriver flag.
- Waits patiently until Cloudflare challenge is passed.
- Paginates via DOM link clicks to avoid triggering Turnstile on page.goto.

Outputs: csdl_mlt/rekvizitai_database.csv
"""

import sys
import os
import re
import csv
import time
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

OUT_DIR = os.path.join(os.path.dirname(__file__))
OUT_CSV = os.path.join(OUT_DIR, "rekvizitai_database.csv")
USER_DATA_DIR = os.path.join(OUT_DIR, "chrome_rekvizitai_profile")

BASE_URL = "https://rekvizitai.vz.lt/imones/zuvininkyste_zuvies_produktai/1/?scrollTo=searchForm&name=&company_code=&search_word=&industry=100152496&search_terms=&location=&catUrlKey=zuvininkyste_zuvies_produktai&resetFilter=0&order=1&redirected=1"

HEADERS = [
    "Công ty",
    "IČO",
    "SĐT",
    "Web",
    "Email",
    "Địa chỉ",
    "Thành phố",
    "Category",
    "Source",
    "Source_URL",
]


def clean_phone(raw):
    if not raw:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip())
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and len(p) == 10:
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    return f"'{p}" if not p.startswith("'") else p


async def wait_for_cloudflare(page):
    """Wait until Cloudflare challenge is resolved by user or automatically"""
    while True:
        try:
            title = await page.title()
            content = await page.content()
            
            # Check if still on Cloudflare challenge
            is_cf = (
                "Just a moment" in title 
                or "Luktelėkite" in title 
                or "DDoS protection" in content 
                or "cf-turnstile" in content
                or "challenges.cloudflare.com" in content
            )
            
            # Check if we have actual Rekvizitai content
            has_rekv = (
                "rekvizitai" in title.lower() 
                or await page.query_selector(".company-title, .company, a[href*='/imone/']") is not None
            )
            
            if has_rekv and not ("Just a moment" in title or "Luktelėkite" in title):
                return True
                
            print("\a[*] Dang cho xac thuc Cloudflare tren cua so trinh duyet... (Vui long tich o xac nhan neu co)")
            
            # Try to auto-click turnstile checkbox in frames if present
            for f in page.frames:
                try:
                    if "cloudflare" in f.url or "challenge" in f.url:
                        chk = await f.query_selector("input[type='checkbox'], .cb-lb, #challenge-stage")
                        if chk:
                            await chk.click()
                except Exception:
                    pass
                    
            await page.wait_for_timeout(2500)
        except Exception:
            await page.wait_for_timeout(2000)


async def harvest_rekvizitai():
    print("=" * 70)
    print(" HARVESTING REKVIZITAI.VZ.LT (Fisheries and Fish Products)")
    print(f" Output File: {OUT_CSV}")
    print(f" Profile Directory: {USER_DATA_DIR}")
    print("=" * 70)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    seen_companies = set()
    rows = []

    # Resume from existing if present
    if os.path.exists(OUT_CSV):
        try:
            with open(OUT_CSV, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    key = r.get("Công ty", "").strip().lower()
                    if key:
                        seen_companies.add(key)
                        rows.append(r)
            print(f"[*] Resumed: loaded {len(seen_companies)} existing records from CSV.")
        except Exception as e:
            print(f"[!] Warning reading existing CSV: {e}")

    async with async_playwright() as p:
        # Launch persistent context to save cookies, session tokens and TLS fingerprint
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="lt-LT"
        )
        
        # Anti-detection script
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("\n[+] Dang ket noi den trang chu Rekvizitai...")
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"[!] Warning during navigation: {e}")
            
        print("[+] Dang kiem tra xac thuc Cloudflare...")
        await wait_for_cloudflare(page)
        print("[V] Da vuot qua Cloudflare thanh cong! Bat dau boc tach du lieu...")
        
        current_page = 1
        max_page = 10
        
        while current_page <= max_page:
            print(f"\n[+] Dang xu ly trang {current_page}...")
            await page.wait_for_timeout(2000)
            
            # Check if challenged again
            title = await page.title()
            if "Just a moment" in title or "Luktelėkite" in title:
                await wait_for_cloudflare(page)
                
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Detect max page
            pag_links = soup.select(".pages a, .pagination a, a[href*='/zuvininkyste_zuvies_produktai/']")
            for pl in pag_links:
                href = pl.get("href", "")
                m = re.search(r"/zuvininkyste_zuvies_produktai/(\d+)/", href)
                if m:
                    pg_num = int(m.group(1))
                    if pg_num > max_page:
                        max_page = pg_num
                        
            # Company cards
            comp_links = soup.select(".company-title, a.companyName, .firm-item a.title, .company .name a, a[href*='/imone/']")
            valid_cards = []
            seen_page_hrefs = set()
            
            for ct in comp_links:
                href = ct.get("href", "")
                txt = ct.get_text(strip=True)
                if "/imone/" in href and txt and len(txt) > 2 and href not in seen_page_hrefs:
                    seen_page_hrefs.add(href)
                    parent = ct.find_parent("div", class_=lambda c: c and any(k in c for k in ["company", "item", "row", "firm"]))
                    if not parent:
                        parent = ct.find_parent("tr") or ct.find_parent("div")
                    valid_cards.append((txt, href, parent))
                    
            if not valid_cards:
                print(f"    [!] Khong tim thay the cong ty tren trang {current_page}. Dung lai.")
                break
                
            new_in_page = 0
            for comp_name, detail_href, parent in valid_cards:
                key = comp_name.lower()
                if key in seen_companies:
                    continue
                    
                full_url = detail_href if detail_href.startswith("http") else f"https://rekvizitai.vz.lt{detail_href}"
                card_txt = parent.get_text(" | ", strip=True) if parent else ""
                
                # Company Code
                ico = ""
                m_ico = re.search(r"kodas\s*[:\s]*(\d{7,10})", card_txt, re.IGNORECASE)
                if not m_ico:
                    m_ico = re.search(r"\b(\d{9})\b", card_txt)
                if m_ico:
                    ico = m_ico.group(1)
                    
                # Phone
                phone = ""
                m_phone = re.search(r"(?:Tel\.?|Mob\.?)\s*([0-9\s()+-]+)", card_txt)
                if m_phone:
                    phone = clean_phone(m_phone.group(1))
                    
                # Address
                addr = ""
                parts = [p.strip() for p in card_txt.split("|") if p.strip()]
                for p in parts:
                    if any(k in p.lower() for k in [" g.", " al.", " pl.", " k.", " m.", " r."]):
                        addr = p
                        break
                        
                record = {
                    "Công ty": comp_name,
                    "IČO": ico,
                    "SĐT": phone,
                    "Web": "",
                    "Email": "",
                    "Địa chỉ": addr,
                    "Thành phố": "",
                    "Category": "Žuvininkystė, žuvies produktai (Fisheries & Fish products)",
                    "Source": "rekvizitai.vz.lt",
                    "Source_URL": full_url,
                }
                
                seen_companies.add(key)
                rows.append(record)
                new_in_page += 1
                
            print(f"    [+] Trang {current_page}/{max_page}: +{new_in_page} cong ty (Luy ke: {len(rows)})")
            
            # Incremental auto-save
            with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()
                writer.writerows(rows)
                
            if current_page >= max_page:
                break
                
            # Navigate to next page: prefer clicking DOM link to preserve Cloudflare clearance
            next_page_num = current_page + 1
            next_link = await page.query_selector(f"a[href*='/zuvininkyste_zuvies_produktai/{next_page_num}/']")
            if next_link:
                try:
                    await next_link.click()
                    await page.wait_for_timeout(3000)
                except Exception:
                    next_url = f"https://rekvizitai.vz.lt/imones/zuvininkyste_zuvies_produktai/{next_page_num}/"
                    await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
            else:
                next_url = f"https://rekvizitai.vz.lt/imones/zuvininkyste_zuvies_produktai/{next_page_num}/"
                await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
                
            current_page += 1
            
        await context.close()
        
    print(f"\n[V] Hoan tat cao Rekvizitai! Tong cong: {len(rows):,} doanh nghiep da luu vao {OUT_CSV}")


if __name__ == "__main__":
    asyncio.run(harvest_rekvizitai())
