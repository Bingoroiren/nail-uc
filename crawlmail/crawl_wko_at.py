#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crawl Austrian Chamber of Commerce: firmen.wko.at
Reusing proven techniques from Canada folder with Playwright Stealth, 
dynamic paths, checklist tracking, and incremental auto-save checkpoints.
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
from playwright_stealth import stealth_async

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

RAW_CSV = OUTPUT_RAW_DIR / "AT_AGCY_WKOP_0RAW.csv"
RAW_JSON = OUTPUT_RAW_DIR / "AT_AGCY_WKOP_0RAW.json"
CHECKLIST_FILE = OUTPUT_RAW_DIR / "checklist_at_agcy.json"

TARGET_URLS = [
    {
        "id": "wko_vermittlung_tirol",
        "url": "https://firmen.wko.at/vermittlung/tirol/",
        "region": "Tirol",
        "keyword": "vermittlung"
    },
    {
        "id": "wko_personaldienstleister_at",
        "url": "https://firmen.wko.at/personaldienstleister/",
        "region": "Österreich",
        "keyword": "personaldienstleister"
    }
]

# Timeouts & settings
TIMEOUT_PAGE_LOAD = 60000
TIMEOUT_LOAD_MORE = 20000
DELAY_BETWEEN_CLICKS = 1.5
MAX_RETRY_NO_INCREASE = 3

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

async def extract_wko_companies(page, target_info):
    """Trích xuất nhanh các thẻ công ty WKO bằng JavaScript trên DOM hiện tại"""
    companies = await page.evaluate("""(args) => {
        const [source, region, category] = args;
        const results = [];
        const baseUrl = "https://firmen.wko.at";
        const articles = document.querySelectorAll('article.search-result-article');
        
        for (const article of articles) {
            const titleLink = article.querySelector('a.title-link');
            let name = "";
            let detailUrl = "";
            if (titleLink) {
                const h3 = titleLink.querySelector('h3');
                name = h3 ? h3.innerText.trim() : titleLink.innerText.trim();
                const href = titleLink.getAttribute('href') || '';
                detailUrl = href.startsWith('/') ? baseUrl + href : href;
            }

            const titleDetails = article.querySelector('.title-details');
            const industry = titleDetails ? titleDetails.innerText.trim() : category;

            const phoneEl = article.querySelector('a[itemprop="telephone"], a[href^="tel:"]');
            let phone = "";
            if (phoneEl) {
                phone = phoneEl.innerText.trim().replace(/\\s+/g, '');
                if (!phone) {
                    phone = (phoneEl.getAttribute('href') || '').replace('tel:', '').trim();
                }
            }

            const emailEl = article.querySelector('a[itemprop="email"], a[href^="mailto:"]');
            let email = "";
            if (emailEl) {
                email = emailEl.innerText.trim();
                if (!email) {
                    const href = emailEl.getAttribute('href') || '';
                    email = href.replace('mailto:', '').split('?')[0].trim();
                }
            }

            const webEl = article.querySelector('a[itemprop="url"]');
            const website = webEl ? (webEl.getAttribute('href') || '').trim() : '';

            const placeEl = article.querySelector('.address .place');
            let place = placeEl ? placeEl.innerText.trim() : '';
            let postalCode = '';
            let city = '';
            if (place) {
                const match = place.match(/^(\\d{4})\\s+(.+)$/);
                if (match) {
                    postalCode = match[1];
                    city = match[2].trim();
                }
            }

            const streetEl = article.querySelector('.address .street');
            let street = streetEl ? streetEl.innerText.trim() : '';

            if (name && name.length > 1) {
                results.push({
                    source: "WKO Firmen A-Z",
                    region: region,
                    category: industry,
                    name: name,
                    street: street,
                    postal_code: postalCode,
                    city: city,
                    phone: phone,
                    email: email,
                    website: website,
                    detail_url: detailUrl
                });
            }
        }
        return results;
    }""", ["WKO Firmen A-Z", target_info["region"], target_info["keyword"]])
    
    return companies

async def crawl_wko():
    checklist = load_checklist()
    existing_results = load_existing_results()
    seen_keys = { (r["name"].lower().strip(), r.get("detail_url", "").lower().strip()) for r in existing_results }
    all_results = list(existing_results)

    print("\n" + "=" * 75)
    print("🚀 BẮT ĐẦU CÀO WKO (AUSTRIAN CHAMBER OF COMMERCE)")
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
        await stealth_async(page)

        for t_idx, target in enumerate(TARGET_URLS, 1):
            t_id = target["id"]
            target_url = target["url"]

            if t_id not in checklist:
                checklist[t_id] = {
                    "portal": "WKO",
                    "region": target["region"],
                    "keyword": target["keyword"],
                    "base_url": target_url,
                    "clicks_count": 0,
                    "status": "PENDING",
                    "items_count": 0
                }
                save_checklist(checklist)

            entry = checklist[t_id]
            if entry.get("status") == "COMPLETED":
                print(f"[{t_idx}/{len(TARGET_URLS)}] ⏭️ Bỏ qua {t_id} (Đã hoàn thành trước đó với {entry.get('items_count', 0)} mục)")
                continue

            print(f"\n[{t_idx}/{len(TARGET_URLS)}] 🔍 Đang xử lý: WKO [{target['keyword'].upper()}] - [{target['region'].upper()}]")
            print(f"🔗 Target URL: {target_url}")

            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
                await page.wait_for_timeout(2500)
            except Exception as e:
                print(f"⚠️ Lỗi tải trang ban đầu {target_url}: {e}")
                continue

            # Chấp nhận cookie banner
            await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, a'));
                for (const btn of buttons) {
                    const txt = (btn.innerText || '').toLowerCase().trim();
                    if (txt.includes('alle akzeptieren') || txt.includes('akzeptieren') || txt.includes('zustimmen')) {
                        btn.click();
                        break;
                    }
                }
            }""")
            await page.wait_for_timeout(1000)

            click_count = entry.get("clicks_count", 0)
            consecutive_no_increase = 0

            while True:
                # Kiểm tra nút 'Mehr laden'
                load_more_exists = await page.evaluate("""() => {
                    const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton') || 
                                document.querySelector('input[value="Mehr laden"], .btn-load-more');
                    if (!btn) return false;
                    const style = window.getComputedStyle(btn);
                    return style && style.display !== 'none' && style.visibility !== 'hidden';
                }""")

                if not load_more_exists:
                    print(f"✅ Nút 'Mehr laden' không còn hiển thị -> Đã tải hết kết quả cho {t_id}!")
                    break

                current_count = await page.evaluate("() => document.querySelectorAll('article.search-result-article').length")

                # Cuộn màn hình tới nút để quan sát
                await page.evaluate("""() => {
                    const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton') || 
                                document.querySelector('input[value="Mehr laden"], .btn-load-more');
                    if (btn) btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }""")
                await page.wait_for_timeout(300)

                # Bấm nút 'Mehr laden'
                await page.evaluate("""() => {
                    const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton') || 
                                document.querySelector('input[value="Mehr laden"], .btn-load-more');
                    if (btn) btn.click();
                }""")

                try:
                    await page.wait_for_function(
                        f"document.querySelectorAll('article.search-result-article').length > {current_count}",
                        timeout=TIMEOUT_LOAD_MORE
                    )
                    new_count = await page.evaluate("() => document.querySelectorAll('article.search-result-article').length")
                    click_count += 1
                    consecutive_no_increase = 0
                    entry["clicks_count"] = click_count
                    if click_count % 5 == 0:
                        print(f"  👉 [Lần {click_count:02d}] Bấm 'Mehr laden' | Hiện có: {new_count} cty (+{new_count - current_count})")
                except Exception:
                    consecutive_no_increase += 1
                    print(f"  ⏳ [Chờ mạng WKO] Thử lại ({consecutive_no_increase}/{MAX_RETRY_NO_INCREASE})...")
                    if consecutive_no_increase >= MAX_RETRY_NO_INCREASE:
                        print(f"  ⏹️ Đã thử {MAX_RETRY_NO_INCREASE} lần không tăng thêm -> Kết thúc tải cho {t_id}.")
                        break

                # Auto-save Checkpoint mỗi 10 lần bấm
                if click_count % 10 == 0 and click_count > 0:
                    temp_items = await extract_wko_companies(page, target)
                    for item in temp_items:
                        k = (item["name"].lower().strip(), item["detail_url"].lower().strip())
                        if k not in seen_keys:
                            seen_keys.add(k)
                            all_results.append(item)
                    save_results(all_results)
                    entry["items_count"] = len(temp_items)
                    save_checklist(checklist)

                await page.wait_for_timeout(int(DELAY_BETWEEN_CLICKS * 1000))

            # Trích xuất toàn bộ kết quả sau khi tải xong
            final_items = await extract_wko_companies(page, target)
            new_added = 0
            for item in final_items:
                k = (item["name"].lower().strip(), item["detail_url"].lower().strip())
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_results.append(item)
                    new_added += 1

            entry["status"] = "COMPLETED"
            entry["items_count"] = len(final_items)
            save_checklist(checklist)
            save_results(all_results)
            print(f"🎉 Hoàn thành mục {t_id}! Thu thập được {len(final_items)} cty (+{new_added} mới) | Tổng: {len(all_results)}")

        await browser.close()

    print("\n" + "=" * 75)
    print(f"🏁 ĐÃ HOÀN TẤT TOÀN BỘ WKO!")
    print(f"📊 Tổng cộng: {len(all_results)} công ty")
    print(f"💾 File kết quả: {RAW_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(crawl_wko())
