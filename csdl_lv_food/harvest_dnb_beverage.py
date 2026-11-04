# -*- coding: utf-8 -*-
"""
Harvest Dun & Bradstreet (D&B) - Beverage Manufacturing Latvia
Source: https://www.dnb.com/business-directory/lv/beverage_manufacturing/companies
Output: csdl_lv_food/database_dnb_beverage.csv
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
OUTPUT_CSV = ROOT_DIR / "csdl_lv_food" / "database_dnb_beverage.csv"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "dnb_lv_profile"

BASE_URL = "https://www.dnb.com/business-directory/lv/beverage_manufacturing/companies"
FIELDNAMES = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r"^['\"„“”«»]+|['\"„“”«»]+$", "", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c

def harvest_dnb_beverage(headless=False):
    print("=" * 70)
    print(" HARVESTING DUN & BRADSTREET (D&B) - BEVERAGE MANUFACTURING (LATVIA)")
    print(f" Source URL: {BASE_URL}")
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

        print(f"[*] Navigating to: {BASE_URL}")
        page.goto(BASE_URL, timeout=60000)

        # Handle Cloudflare check if present
        print("[*] Checking Cloudflare / page loading (waiting up to 60s)...")
        for wait_sec in range(60):
            title = page.title()
            if "Just a moment" in title or "Attention Required" in title or "Cloudflare" in title:
                if wait_sec == 0:
                    print("\n\a" + "!" * 70)
                    print("[!] CLOUDFLARE DETECTED: Vui lòng click xác thực Cloudflare trên cửa sổ Chrome nếu cần.")
                    print("!" * 70 + "\n")
                time.sleep(2)
            else:
                break

        page_num = 1
        while True:
            time.sleep(3)
            # Extract companies via JS on DOM
            items_data = page.evaluate("""
            () => {
                const res = [];
                const links = document.querySelectorAll('a[href*="/company-information/"], a[href*="/company-profiles/"], a[href*="/business-directory/company"]');
                for (const a of links) {
                    const name = a.innerText.trim();
                    const href = a.href || '';
                    if (!name || name.length < 3) continue;
                    const row = a.closest('tr') || a.parentElement.parentElement || a.parentElement;
                    const text = row ? (row.innerText || '') : '';
                    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                    let location = '';
                    for (const l of lines) {
                        if (l !== name && (l.includes('Latvia') || l.includes('Riga') || l.includes('Rīga') || l.includes(','))) {
                            location = l;
                            break;
                        }
                    }
                    if (!location && lines.length > 1) location = lines[1];
                    res.push({ name, href, location });
                }
                return res;
            }
            """)

            print(f"  Page {page_num}: Found {len(items_data)} items on DOM.")
            new_on_page = 0
            for item in items_data:
                comp_raw = item.get('name') or ""
                comp = clean_company_name(comp_raw)
                if not comp or len(comp) < 3:
                    continue

                location = item.get('location') or ""
                # Filter to only keep Latvia companies if location has country info
                if location and any(c in location.lower() for c in ['lithuania', 'estonia', 'russia', 'poland', 'belarus', 'germany', 'france', 'united kingdom', 'usa']):
                    continue

                key = comp.lower()
                if key in seen:
                    continue
                seen.add(key)
                new_on_page += 1

                addr = location if location else "Latvia"
                if "latvia" not in addr.lower() and "rīga" not in addr.lower() and "riga" not in addr.lower():
                    addr = f"{addr}, Latvia"

                results.append({
                    'Company': comp,
                    'Website': "",
                    'Phone': "",
                    'Email': "",
                    'Address': addr,
                    'Category': "Beverage manufacturing",
                    'Source': "dnb.com",
                    'Profile_URL': item.get('href') or BASE_URL
                })

            print(f"    -> Added {new_on_page} new companies. Total collected: {len(results)}")

            # Check next page
            next_btn = page.query_selector('a[aria-label="Next"], a:has-text("Next"), button[aria-label="Next"], .pagination-next a')
            if next_btn and next_btn.is_visible() and not next_btn.get_attribute('disabled'):
                print("  [*] Clicking Next page...")
                next_btn.click()
                page_num += 1
                time.sleep(3)
            else:
                break

        browser.close()

    print(f"\n[✔] Total companies extracted from D&B: {len(results)}")
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"[✔] Saved to: {OUTPUT_CSV}\n")
    return results

if __name__ == '__main__':
    harvest_dnb_beverage()
