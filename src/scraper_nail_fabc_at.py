# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU FIRMENABC CHO TIỆM NAIL ÁO (AT_NAIL_FABC)
=============================================================================
Nguồn: https://www.firmenabc.at/
Ngành: Nagelstudio / Nageldesign (412 tiệm)
Công nghệ: Playwright Chromium (headless=False) xử lý Cookiebot & bóc tách trang chi tiết
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import unicodedata
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

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
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_RAW_CSV = DATA_DIR / "AT_NAIL_FABC_0RAW.csv"
OUTPUT_RAW_JSON = DATA_DIR / "AT_NAIL_FABC_0RAW.json"
CHECKLIST_FILE = ROOT_DIR / "progress" / "progress_nail_fabc_at.json"
CHECKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)

ROOT_RAW_CSV = ROOT_DIR / "AT_NAIL_FABC_0RAW.csv"

# URL gốc được cung cấp chính xác bởi người dùng
BASE_SEARCH_URL = "https://www.firmenabc.at/suche/ergebnisse?tx_indexedsearch_pi2%5Bsearch%5D%5Bsword%5D=Nagelstudio+%2F+Nageldesign&tx_indexedsearch_pi2%5Bsearch%5D%5BwhatId%5D=5933&tx_indexedsearch_pi2%5Bsearch%5D%5BwhatIndustry%5D=1&tx_indexedsearch_pi2%5Bsearch%5D%5Bwhere%5D=&tx_indexedsearch_pi2%5Bsearch%5D%5BwhereId%5D=&tx_indexedsearch_pi2%5Bsearch%5D%5BwhereRegion%5D=0&tx_indexedsearch_pi2%5Baction%5D=search&tx_indexedsearch_pi2%5Bsearch%5D%5BsearchMode%5D=&cHash=0a9ce70f741885651ffd976dcd4f18db"

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

def load_checkpoint():
    if CHECKLIST_FILE.exists():
        try:
            with open(CHECKLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"visited_detail_urls": [], "stage": "COLLECT_CARDS"}

def save_checkpoint(data):
    try:
        with open(CHECKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Lỗi lưu checkpoint: {e}")

def load_existing_results():
    if OUTPUT_RAW_JSON.exists():
        try:
            with open(OUTPUT_RAW_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_results(results):
    if not results:
        return
    valid_results = [r for r in results if not is_blacklisted(r.get("name", ""))]

    with open(OUTPUT_RAW_JSON, 'w', encoding='utf-8') as f:
        json.dump(valid_results, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "source", "category", "name", "street", "postal_code",
        "city", "phone", "email", "website", "detail_url"
    ]
    for path in [OUTPUT_RAW_CSV, ROOT_RAW_CSV]:
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in valid_results:
                    row = {k: r.get(k, "") for k in fieldnames}
                    row["phone"] = clean_phone(row.get("phone", ""))
                    row["email"] = clean_email(row.get("email", ""))
                    writer.writerow(row)
        except PermissionError:
            print(f"  [!] File {path.name} đang mở, sẽ cập nhật ở lần sau.")
        except Exception as e:
            print(f"[-] Lỗi ghi file {path.name}: {e}")

async def handle_cookiebot(page):
    try:
        btn = page.locator("#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll")
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(1500)
    except Exception:
        pass

async def scrape_fabc():
    print("=" * 80)
    print("🇦🇹  HỆ THỐNG CÀO TIỆM NAIL FIRMENABC (FIRMENABC.AT)")
    print(f"    - URL Gốc      : {BASE_SEARCH_URL}")
    print(f"    - Chế độ xem  : Trực quan (headless=False - Rule 4)")
    print(f"    - File kết quả : {OUTPUT_RAW_CSV.name}")
    print("=" * 80)

    checkpoint = load_checkpoint()
    existing_results = load_existing_results()
    results_map = { r.get("detail_url"): r for r in existing_results if r.get("detail_url") }
    visited_urls = set(checkpoint.get("visited_detail_urls", []))

    print(f"[*] Đã nạp {len(existing_results):,} tiệm nail sẵn có từ checkpoint.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=30)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        page = await context.new_page()
        await stealth_async(page)

        # ---------------- GIAI ĐOẠN 1: THU THẬP TẤT CẢ DANH SÁCH THẺ (PAGES 1..9) ----------------
        print("\n[*] GIAI ĐOẠN 1: Thu thập danh sách thẻ qua tất cả các trang...")
        await page.goto(BASE_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        await handle_cookiebot(page)

        current_page_idx = 1
        while True:
            print(f"  👉 Đang quét trang danh sách {current_page_idx}...", end="", flush=True)
            await page.wait_for_timeout(1000)

            # Bóc tách 50 thẻ trên trang
            cards = await page.evaluate("""() => {
                const h3List = document.querySelectorAll('h3[id^="company-"]');
                const list = [];
                for (const h3 of h3List) {
                    const name = h3.innerText.trim();
                    const aLink = h3.querySelector('a');
                    const detailUrl = aLink ? aLink.href : '';
                    let card = h3.closest('div.bg-gray, div[class*="border"], div[class*="min-h"]') || h3.parentElement.parentElement;
                    let text = card ? card.innerText : '';
                    list.push({name, detailUrl, textSnippet: text});
                }
                return list;
            }""")

            added_cards = 0
            for c in cards:
                d_url = c.get("detailUrl")
                if not d_url:
                    continue
                if d_url not in results_map:
                    # Trích xuất địa chỉ sơ bộ từ textSnippet
                    text = c.get("textSnippet", "")
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    street = ""
                    postal_code = ""
                    city = ""
                    for line in lines:
                        plz_m = re.search(r'\b(\d{4})\s+([A-Za-zÄÖÜäöüß\s\-]+)', line)
                        if plz_m:
                            postal_code = plz_m.group(1).strip()
                            city = plz_m.group(2).strip()
                        elif any(s in line.lower() for s in ['straße', 'str.', 'weg', 'gasse', 'platz', 'dorf']) and not street:
                            street = line

                    results_map[d_url] = {
                        "source": "FirmenABC",
                        "category": "Nagelstudio / Nageldesign",
                        "name": c.get("name", "").strip(),
                        "street": street,
                        "postal_code": postal_code,
                        "city": city,
                        "phone": "",
                        "email": "",
                        "website": "",
                        "detail_url": d_url
                    }
                    added_cards += 1

            print(f" -> Lấy được {len(cards)} thẻ (+{added_cards} mới | Tổng: {len(results_map)}).")

            # Tìm nút 'Nächste Seite' hoặc trang tiếp theo
            next_btn = page.locator("a:has-text('Nächste Seite'), a[aria-label='Nächste Seite']")
            if await next_btn.count() > 0 and await next_btn.first.is_visible():
                await next_btn.first.click()
                current_page_idx += 1
                await page.wait_for_timeout(2000)
                await handle_cookiebot(page)
            else:
                print("✅ Đã duyệt hết tất cả các trang danh sách FirmenABC!")
                break

        # Lưu danh sách thẻ thô
        save_results(list(results_map.values()))

        # ---------------- GIAI ĐOẠN 2: BÓC TÁCH CHI TIẾT (SĐT, EMAIL, WEBSITE) ----------------
        print(f"\n[*] GIAI ĐOẠN 2: Quét chi tiết từng cơ sở để lấy Email, SĐT, Website...")
        to_enrich = [item for item in results_map.values() if item["detail_url"] not in visited_urls]
        print(f"[*] Số cơ sở cần cào chi tiết: {len(to_enrich):,} / {len(results_map):,}")

        emails_found_count = sum(1 for item in results_map.values() if item.get("email"))
        processed_step = 0

        for item in to_enrich:
            d_url = item["detail_url"]
            name = item["name"]

            try:
                await page.goto(d_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(800)
                await handle_cookiebot(page)

                detail_data = await page.evaluate("""() => {
                    const tel = (document.querySelector('a[href^="tel:"]')?.href || '').replace('tel:', '').trim();
                    const mail = (document.querySelector('a[href^="mailto:"]')?.href || '').replace('mailto:', '').split('?')[0].trim();
                    const web = (document.querySelector('a[href^="http"]:not([href*="firmenabc"])')?.href || '').trim();

                    // Đọc địa chỉ chính xác nếu trang danh sách chưa có
                    const text = document.body.innerText;
                    return { tel, mail, web, fullText: text.substring(0, 800) };
                }""")

                if detail_data.get("tel"):
                    item["phone"] = clean_phone(detail_data["tel"])
                if detail_data.get("mail"):
                    item["email"] = clean_email(detail_data["mail"])
                    emails_found_count += 1
                if detail_data.get("web"):
                    item["website"] = detail_data["web"]

                log_mail = f"✨ {item['email']}" if item["email"] else "Không có mail"
                log_tel = item["phone"] if item["phone"] else "-"
                print(f"[{processed_step+1:03d}/{len(to_enrich):03d}] {name[:25]:<25} | {log_mail:<30} | {log_tel}", flush=True)

            except Exception as e:
                print(f"  [-] Lỗi tải {d_url}: {e}")

            visited_urls.add(d_url)
            checkpoint["visited_detail_urls"] = list(visited_urls)
            processed_step += 1

            # Auto-save Checkpoint mỗi 10 cơ sở
            if processed_step % 10 == 0:
                save_checkpoint(checkpoint)
                save_results(list(results_map.values()))
                print(f"  💾 [Auto-Save Checkpoint] Đã lưu {len(results_map)} cơ sở ({emails_found_count} có email).")

            await page.wait_for_timeout(300)

        save_checkpoint(checkpoint)
        save_results(list(results_map.values()))
        await browser.close()

    total_with_email = sum(1 for item in results_map.values() if item.get("email"))
    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CÀO TOÀN DIỆN FIRMENABC NƯỚC ÁO:")
    print(f"   - Tổng số tiệm nail thu thập được : {len(results_map):,} tiệm")
    print(f"   - TỔNG SỐ TIỆM CÓ EMAIL XÁC THỰC  : {total_with_email:,} tiệm")
    print(f"   - File kết quả thô                 : {OUTPUT_RAW_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(scrape_fabc())

