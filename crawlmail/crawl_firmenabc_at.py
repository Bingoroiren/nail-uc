#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crawl Austrian Employment & Staffing Agencies from FirmenABC.at
Dynamic paths, Playwright DOM parsing, pagination checklist, incremental checkpointing.
"""

import os
import sys
import json
import re
import time
import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

# Base directory relative to this script
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_RAW_DIR = BASE_DIR / "data"
OUTPUT_RAW_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = OUTPUT_RAW_DIR / "AT_AGCY_FABC_0RAW.csv"
RAW_JSON = OUTPUT_RAW_DIR / "AT_AGCY_FABC_0RAW.json"
CHECKLIST_FILE = OUTPUT_RAW_DIR / "checklist_at_agcy.json"

TARGET_URLS = [
    {
        "id": "fabc_noe_bereitstellung",
        "url": "https://www.firmenabc.at/firmen/noe/personalbereitstellung-personalleasing-personalueberlassung_CKx",
        "region": "Niederösterreich",
        "category": "Personalbereitstellung / Personalleasing"
    },
    {
        "id": "fabc_graz_bereitstellung",
        "url": "https://www.firmenabc.at/firmen/graz-stadt_Ld/personalbereitstellung-personalleasing-personalueberlassung_CKx",
        "region": "Graz-Stadt",
        "category": "Personalbereitstellung / Personalleasing"
    },
    {
        "id": "fabc_stmk_bereitstellung",
        "url": "https://www.firmenabc.at/firmen/stmk/personalbereitstellung-personalleasing-personalueberlassung_CKx",
        "region": "Steiermark",
        "category": "Personalbereitstellung / Personalleasing"
    }
]

def load_checklist():
    if CHECKLIST_FILE.exists():
        try:
            with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_checklist(checklist):
    try:
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(checklist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving checklist: {e}")

def load_existing_results():
    if RAW_JSON.exists():
        try:
            with open(RAW_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_results(results):
    if not results:
        return
    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Save CSV with BOM
    fieldnames = [
        "source", "region", "category", "name", "street", "postal_code",
        "city", "phone", "email", "website", "detail_url"
    ]
    import csv
    with open(RAW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k, "") for k in fieldnames}
            phone = str(row["phone"]).strip()
            if phone and not phone.startswith("'"):
                row["phone"] = f"'{phone}"
            writer.writerow(row)

def parse_firmenabc_page(html, target_info):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    
    # Check max page from pagination
    pages = [1]
    for a in soup.find_all("a"):
        h = a.get("href", "")
        m = re.search(r"_CKx/(\d+)", h)
        if m:
            pages.append(int(m.group(1)))
    total_pages = max(pages) if pages else 1
    
    # Each company listing in FirmenABC has an h3 containing link with slug_ID
    for h3 in soup.find_all("h3"):
        a_link = h3.find("a")
        if not a_link:
            a_link = h3.find_parent("a")
            
        name = h3.get_text(strip=True)
        if not name or len(name) < 2 or "Erhöhen Sie" in name or "Auswahl" in name:
            continue
            
        href = a_link.get("href", "").strip() if a_link else ""
        if not href or href.startswith("#"):
            continue
            
        detail_url = f"https://www.firmenabc.at{href}" if href.startswith("/") else href
        
        # Look for address text in sibling / parent elements
        # Usually card container has street and '8054 Seiersberg-Pirka'
        parent_card = h3.find_parent("div")
        card_text = parent_card.get_text("\n", strip=True) if parent_card else ""
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]
        
        street = ""
        postal_code = ""
        city = ""
        
        # Match PLZ: 4 digits followed by city
        for line in lines:
            m = re.match(r"^(\d{4})\s+(.+)$", line)
            if m:
                postal_code = m.group(1).strip()
                city = m.group(2).strip()
                break
                
        # Street is usually preceding PLZ line
        if postal_code:
            for idx, line in enumerate(lines):
                if postal_code in line and idx > 0:
                    prev = lines[idx - 1]
                    if prev != name and len(prev) > 3:
                        street = prev
                    break
                    
        results.append({
            "source": "FirmenABC.at",
            "region": target_info["region"],
            "category": target_info["category"],
            "name": name,
            "street": street,
            "postal_code": postal_code,
            "city": city,
            "phone": "",
            "email": "",
            "website": "",
            "detail_url": detail_url
        })
        
    return results, total_pages

async def crawl_firmenabc():
    checklist = load_checklist()
    existing_results = load_existing_results()
    seen_keys = { (r["name"].lower().strip(), r.get("detail_url", "").lower().strip()) for r in existing_results }
    all_results = list(existing_results)

    print("\n" + "=" * 75)
    print("🚀 BẮT ĐẦU CÀO FIRMENABC.AT (AUSTRIA AGENCY)")
    print(f"📁 Dữ liệu lưu tại: {RAW_CSV}")
    print(f"📋 Checklist file: {CHECKLIST_FILE}")
    print("=" * 75)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()

        for t_idx, target in enumerate(TARGET_URLS, 1):
            t_id = target["id"]
            base_url = target["url"]

            if t_id not in checklist:
                checklist[t_id] = {
                    "portal": "FirmenABC",
                    "region": target["region"],
                    "category": target["category"],
                    "base_url": base_url,
                    "total_pages": None,
                    "scraped_pages": [],
                    "status": "PENDING",
                    "items_count": 0
                }
                save_checklist(checklist)

            entry = checklist[t_id]
            if entry.get("status") == "COMPLETED":
                print(f"[{t_idx}/{len(TARGET_URLS)}] ⏭️ Bỏ qua {t_id} (Đã hoàn thành trước đó với {entry.get('items_count', 0)} mục)")
                continue

            print(f"\n[{t_idx}/{len(TARGET_URLS)}] 🔍 Đang xử lý: FirmenABC [{target['region'].upper()}]")
            print(f"🔗 Base URL: {base_url}")

            page_num = 1
            total_pages = entry.get("total_pages") or 1

            while page_num <= total_pages:
                if page_num in entry.get("scraped_pages", []):
                    print(f"  ⏭️ Trang {page_num} đã cào -> Bỏ qua")
                    page_num += 1
                    continue

                page_url = base_url if page_num == 1 else f"{base_url}/{page_num}"
                print(f"  📄 Đang tải trang {page_num}/{total_pages}: {page_url} ...")

                try:
                    resp = await page.goto(page_url, wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(2000)

                    # Chấp nhận cookie banner nếu có
                    await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button, a'));
                        for (const btn of buttons) {
                            const txt = (btn.innerText || '').toLowerCase().trim();
                            if (txt.includes('alle akzeptieren') || txt.includes('akzeptieren') || txt.includes('zustimmen') || txt.includes('verstanden')) {
                                btn.click();
                                break;
                            }
                        }
                    }""")

                    html = await page.content()
                    items, detected_total = parse_firmenabc_page(html, target)

                    if detected_total > total_pages:
                        total_pages = detected_total
                        entry["total_pages"] = total_pages

                    new_items = 0
                    for it in items:
                        key = (it["name"].lower().strip(), it["detail_url"].lower().strip())
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_results.append(it)
                            new_items += 1

                    entry["scraped_pages"].append(page_num)
                    entry["items_count"] = entry.get("items_count", 0) + new_items
                    save_checklist(checklist)
                    save_results(all_results)

                    print(f"  ✅ Trang {page_num}/{total_pages}: Trích xuất được {len(items)} cty (+{new_items} mới) | Tổng: {len(all_results)}")

                except Exception as e:
                    print(f"  ❌ Lỗi khi tải trang {page_num}: {e}")
                    await asyncio.sleep(2)

                page_num += 1
                await asyncio.sleep(1.2)

            entry["status"] = "COMPLETED"
            save_checklist(checklist)
            print(f"🎉 Hoàn thành mục {t_id}! Tổng công ty hiện có: {len(all_results)}")

        await browser.close()

    print("\n" + "=" * 75)
    print(f"🏁 ĐÃ HOÀN TẤT TOÀN BỘ FIRMENABC.AT!")
    print(f"📊 Tổng cộng: {len(all_results)} công ty")
    print(f"💾 File kết quả: {RAW_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(crawl_firmenabc())
