# -*- coding: utf-8 -*-
"""
Harvest Kompass Latvia Food & Beverages Categories
Sources:
1. https://vn.kompass.com/z/lv/a/food/03/
2. https://www.kompass.com/z/lv/a/pastries-and-cakes/03590/
3. https://www.kompass.com/z/lv/a/food-beverages-and-tobacco-wholesale/8125003/
Output: csdl_lv_food/database_kompass_food.csv
"""

import sys
import re
import csv
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT_DIR / "csdl_lv_food" / "database_kompass_food.csv"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "kompass_lv_profile"

URLS = [
    ("Food & Beverages", "https://www.kompass.com/z/lv/a/food/03/"),
    ("Pastries & Cakes", "https://www.kompass.com/z/lv/a/pastries-and-cakes/03590/"),
    ("Food & Beverages Wholesale", "https://www.kompass.com/z/lv/a/food-beverages-and-tobacco-wholesale/8125003/"),
]

FIELDNAMES = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r"^['\"„“”«»]+|['\"„“”«»]+$", "", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c

def harvest_kompass_food(headless=False):
    print("=" * 70)
    print(" HARVESTING KOMPASS LATVIA FOOD & BEVERAGES DIRECTORIES")
    print("=" * 70)

    results = []
    seen = set()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled', '--start-maximized']
        )
        page = browser.new_page() if not browser.pages else browser.pages[0]

        for cat_name, base_url in URLS:
            print(f"\n[*] Navigating to Category: {cat_name} ({base_url})")
            page.goto(base_url, timeout=60000)

            # Wait for user if DataDome or Cloudflare appears
            for wait_sec in range(60):
                title = page.title()
                html = page.content()
                if "DataDome" in html or "captcha-delivery" in html or "Just a moment" in title:
                    if wait_sec == 0:
                        print("\n\a" + "!" * 70)
                        print("[!] CAPTCHA / DATADOME DETECTED trên Kompass.")
                        print("Vui lòng giải captcha trên cửa sổ Chrome. Hệ thống đang chờ...")
                        print("!" * 70 + "\n")
                    time.sleep(2)
                else:
                    break

            page_num = 1
            cat_count = 0
            while True:
                time.sleep(2.5)
                # Bóc tách danh sách công ty qua DOM
                items = page.evaluate("""
                () => {
                    const res = [];
                    // Kompass company link usually has /c/ in href
                    const links = document.querySelectorAll('a[href*="/c/"]');
                    for (const a of links) {
                        const name = a.innerText.trim();
                        const href = a.href || '';
                        if (!name || name.length < 3) continue;
                        if (name.toLowerCase().includes('kompass') || name.toLowerCase().includes('contact')) continue;
                        
                        // Extract parent container text for address/location
                        const card = a.closest('.product-item') || a.closest('.searchResultItem') || a.closest('div[class*="item"]') || a.parentElement.parentElement;
                        let location = '';
                        if (card) {
                            const text = card.innerText || '';
                            const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                            for (const l of lines) {
                                if (l !== name && (l.includes('Latvia') || l.includes('Riga') || l.includes('Rīga') || l.includes('LV-'))) {
                                    location = l;
                                    break;
                                }
                            }
                        }
                        res.push({ name, href, location });
                    }
                    return res;
                }
                """)

                print(f"  Page {page_num}: Found {len(items)} listings.")
                new_on_page = 0
                for item in items:
                    comp = clean_company_name(item.get('name') or "")
                    if not comp or len(comp) < 3:
                        continue

                    location = item.get('location') or ""
                    # Ensure only Latvia companies
                    if location and any(c in location.lower() for c in ['lithuania', 'estonia', 'russia', 'poland', 'belarus', 'germany', 'france', 'united kingdom', 'usa', 'italy']):
                        continue

                    key = comp.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    new_on_page += 1
                    cat_count += 1

                    addr = location if location else "Latvia"
                    results.append({
                        'Company': comp,
                        'Website': "",
                        'Phone': "",
                        'Email': "",
                        'Address': addr,
                        'Category': f"Food - {cat_name}",
                        'Source': "Kompass",
                        'Profile_URL': item.get('href') or base_url
                    })

                print(f"    -> Added +{new_on_page} new companies from page {page_num}.")

                # Check Next page button
                next_btn = page.query_selector('a.pagination-next, a[rel="next"], a:has-text("Next"), li.next a, a[title="Next page"]')
                if next_btn and next_btn.is_visible() and new_on_page > 0:
                    print("  [*] Navigating to next page...")
                    next_btn.click()
                    page_num += 1
                else:
                    break

            print(f"  --> Extracted {cat_count} total companies from {cat_name}.")

        browser.close()

    print(f"\n[✔] Total companies extracted from Kompass: {len(results)}")
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"[✔] Saved to: {OUTPUT_CSV}\n")
    return results

if __name__ == '__main__':
    harvest_kompass_food()
