# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU WKO FIRMEN A-Z TOÀN BỘ 9 BANG NƯỚC ÁO
Chuyên ngành: Nagelstudio (Tiệm Nail)
Nguồn: https://firmen.wko.at/nagelstudio/
Kế thừa & tối ưu kỹ thuật từ D:/glc/canada/scrape_wko_all_states.py và crawlmail/crawl_wko_at.py
"""

import os
import sys
import json
import re
import time
import asyncio
import unicodedata
from pathlib import Path
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

_old_print = print
def print(*args, **kwargs):
    kwargs['flush'] = True
    _old_print(*args, **kwargs)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PROGRESS_DIR = ROOT_DIR / "progress"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)

# File chuẩn 17 ký tự (Rule 10)
OUTPUT_RAW_CSV = DATA_DIR / "AT_NAIL_WKOP_0RAW.csv"
OUTPUT_RAW_JSON = DATA_DIR / "AT_NAIL_WKOP_0RAW.json"
CHECKLIST_FILE = PROGRESS_DIR / "progress_nail_wko_at.json"

ROOT_RAW_CSV = ROOT_DIR / "AT_NAIL_WKOP_0RAW.csv"

# 9 Bang của Áo (Bundesländer)
STATES = [
    {"name": "Burgenland", "slug": "burgenland"},
    {"name": "Kärnten", "slug": "k%c3%a4rnten"},
    {"name": "Niederösterreich", "slug": "nieder%c3%b6sterreich"},
    {"name": "Oberösterreich", "slug": "ober%c3%b6sterreich"},
    {"name": "Salzburg", "slug": "salzburg"},
    {"name": "Steiermark", "slug": "steiermark"},
    {"name": "Tirol", "slug": "tirol"},
    {"name": "Vorarlberg", "slug": "vorarlberg"},
    {"name": "Wien", "slug": "wien"}
]

TIMEOUT_PAGE_LOAD = 60000
TIMEOUT_LOAD_MORE = 15000
DELAY_BETWEEN_CLICKS = 1.2
MAX_RETRY_NO_INCREASE = 3

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigrė'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = email.strip()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()
    if re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return em
    return ""

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
        print(f"[-] Lỗi lưu checklist: {e}")

def load_existing_results():
    if OUTPUT_RAW_JSON.exists():
        try:
            with open(OUTPUT_RAW_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_results(results):
    if not results:
        return
    
    # Lọc blacklist (Rule 12)
    valid_results = [r for r in results if not is_blacklisted(r.get("name", ""))]

    with open(OUTPUT_RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(valid_results, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "source", "state", "category", "name", "street", "postal_code",
        "city", "phone", "email", "website", "detail_url"
    ]
    import csv
    for path in [OUTPUT_RAW_CSV, ROOT_RAW_CSV]:
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in valid_results:
                    row = {k: r.get(k, "") for k in fieldnames}
                    row["phone"] = clean_phone(row.get("phone", ""))
                    row["email"] = clean_email(row.get("email", ""))
                    writer.writerow(row)
        except PermissionError:
            print(f"[!] Cảnh báo: File {path.name} đang mở bởi ứng dụng khác.")
        except Exception as e:
            print(f"[-] Lỗi ghi file {path.name}: {e}")

async def extract_wko_companies(page, state_name):
    """Trích xuất toàn bộ thẻ công ty trên DOM hiện tại"""
    companies = await page.evaluate("""(args) => {
        const [source, state, category] = args;
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
            let place = placeEl ? placeEl.innerText.replace(/\\u00a0/g, ' ').trim() : '';
            let postalCode = '';
            let city = '';
            if (place) {
                const match = place.match(/^(\\d{4})\\s+(.+)$/);
                if (match) {
                    postalCode = match[1];
                    city = match[2].trim();
                } else {
                    city = place;
                }
            }

            const streetEl = article.querySelector('.address .street');
            let street = streetEl ? streetEl.innerText.replace(/\\u00a0/g, ' ').trim() : '';

            if (name && name.length > 1) {
                results.push({
                    source: "WKO Firmen A-Z",
                    state: state,
                    category: industry || "Nagelstudio",
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
    }""", ["WKO Firmen A-Z", state_name, "Nagelstudio"])
    
    return companies

async def crawl_state(page, state_info, all_results, seen_keys, checklist):
    state_name = state_info["name"]
    state_slug = state_info["slug"]
    state_id = f"wko_nail_{state_name.lower()}"

    target_url = f"https://firmen.wko.at/nagelstudio/{state_slug}/"

    if state_id not in checklist:
        checklist[state_id] = {
            "portal": "WKO Firmen A-Z",
            "state": state_name,
            "keyword": "nagelstudio",
            "url": target_url,
            "clicks_count": 0,
            "status": "PENDING",
            "items_count": 0
        }
        save_checklist(checklist)

    entry = checklist[state_id]
    if entry.get("status") == "COMPLETED":
        print(f"⏭️ Bỏ qua [{state_name}] (Đã hoàn tất trước đó với {entry.get('items_count', 0)} tiệm)")
        return

    print("\n" + "=" * 75)
    print(f"🏛️ ĐANG CÀO WKO: BANG [{state_name.upper()}] - TỪ KHÓA [NAGELSTUDIO]")
    print(f"🔗 URL: {target_url}")
    print("=" * 75)

    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"⚠️ Lỗi tải trang ban đầu {target_url}: {e}")
        return

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
            print(f"✅ Nút 'Mehr laden' không còn hiển thị -> Đã tải hết tiệm nail tại {state_name}!")
            break

        current_count = await page.evaluate("() => document.querySelectorAll('article.search-result-article').length")

        # Cuộn tới nút
        await page.evaluate("""() => {
            const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton') || 
                        document.querySelector('input[value="Mehr laden"], .btn-load-more');
            if (btn) btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }""")
        await page.wait_for_timeout(250)

        # Bấm nút
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
            print(f"  👉 [{state_name}] [Lần {click_count:02d}] Bấm 'Mehr laden' | Hiện có: {new_count:4d} tiệm (+{new_count - current_count})")
        except Exception:
            consecutive_no_increase += 1
            print(f"  ⏳ [Chờ WKO phản hồi] Thử lại ({consecutive_no_increase}/{MAX_RETRY_NO_INCREASE})...")
            if consecutive_no_increase >= MAX_RETRY_NO_INCREASE:
                print(f"  ⏹️ Đã thử {MAX_RETRY_NO_INCREASE} lần không tăng thêm -> Kết thúc tải cho {state_name}.")
                break

        # Checkpoint tự động mỗi 5 lần bấm
        if click_count % 5 == 0 and click_count > 0:
            temp_items = await extract_wko_companies(page, state_name)
            for item in temp_items:
                k = (item["name"].lower().strip(), item["detail_url"].lower().strip())
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_results.append(item)
            save_results(all_results)
            entry["items_count"] = len(temp_items)
            save_checklist(checklist)
            print(f"  💾 [Auto-Save Checkpoint] Đã lưu {len(all_results):,} tiệm nail tích lũy.")

        await page.wait_for_timeout(int(DELAY_BETWEEN_CLICKS * 1000))

    # Trích xuất toàn bộ kết quả của bang
    final_items = await extract_wko_companies(page, state_name)
    added_new = 0
    for item in final_items:
        k = (item["name"].lower().strip(), item["detail_url"].lower().strip())
        if k not in seen_keys:
            seen_keys.add(k)
            all_results.append(item)
            added_new += 1

    entry["status"] = "COMPLETED"
    entry["items_count"] = len(final_items)
    save_checklist(checklist)
    save_results(all_results)
    
    with_em = sum(1 for item in final_items if clean_email(item.get("email", "")))
    print(f"🎉 Hoàn thành bang {state_name}! Thu được {len(final_items)} tiệm nail (+{added_new} mới, {with_em} có sẵn email trực tiếp).")
    print(f"📊 Tổng số tiệm nail tích lũy toàn quốc: {len(all_results):,} tiệm.")

async def main():
    print("=" * 80)
    print("🇦🇹  HỆ THỐNG CÀO TIỆM NAIL WKO TOÀN BỘ 9 BANG NƯỚC ÁO (FIRMEN.WKO.AT)")
    print(f"    - URL Gốc      : https://firmen.wko.at/nagelstudio/")
    print(f"    - Chế độ xem  : Trực quan (headless=False - Rule 4)")
    print(f"    - File kết quả : {OUTPUT_RAW_CSV.name}")
    print(f"    - Checkpoint   : {CHECKLIST_FILE.name}")
    print("=" * 80)

    checklist = load_checklist()
    existing_results = load_existing_results()
    seen_keys = { (r["name"].lower().strip(), r.get("detail_url", "").lower().strip()) for r in existing_results }
    all_results = list(existing_results)

    if existing_results:
        print(f"📂 Đã nạp lại {len(all_results):,} tiệm nail sẵn có từ checkpoint trước.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()

        for idx, state_info in enumerate(STATES, 1):
            print(f"\n>>>>>> BANG [{idx}/{len(STATES)}]: {state_info['name'].upper()} <<<<<<")
            await crawl_state(page, state_info, all_results, seen_keys, checklist)
            await page.wait_for_timeout(1500)

        save_results(all_results)
        await page.wait_for_timeout(2000)
        await browser.close()

    total_emails = sum(1 for r in all_results if clean_email(r.get("email", "")))
    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CÀO WKO TOÀN BỘ 9 BANG NƯỚC ÁO:")
    print(f"   - Tổng số tiệm nail sạch trích xuất : {len(all_results):,} tiệm")
    print(f"   - Số tiệm CÓ SẴN EMAIL TRỰC TIẾP   : {total_emails:,} tiệm")
    print(f"   - File kết quả thô                  : {OUTPUT_RAW_CSV}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())

