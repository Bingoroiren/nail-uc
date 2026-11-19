# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU PAGESJAUNES PARIS (PHÁP) - NATIVE GOOGLE CHROME CDP
=======================================================================
Kế thừa cơ chế vượt Cloudflare Turnstile từ bộ cào Rekvizitai Litva (harvest_rekvizitai_wood.py):
1. Khởi chạy Google Chrome THẬT 100% của Windows qua subprocess.Popen (Native Chrome).
2. Tự động nhận diện & click Cloudflare Turnstile trong frame (lưu cookie vĩnh viễn vào profile).
3. Hỗ trợ đầy đủ phân trang cho cả 2 danh mục:
   - Danh mục 1: Recrutement international (Paris 75000)
   - Danh mục 2: Agences d'intérim (Paris 75000 - Cào toàn bộ các trang phân trang 1..N)
4. Tự động click "Afficher le numéro" để bóc tách 100% Số điện thoại ('+33...) và Website.
5. Nếu thẻ danh sách chưa có SĐT/Website, tự động quét bổ sung từ trang chi tiết Fiche Pro.
6. Lưu tăng dần từng dòng (mode='a', flush=True) vào file duy nhất: FR_AGCY_PJAU_0RAW.csv
"""

import sys
import os
import re
import csv
import json
import time
import socket
import asyncio
import subprocess
import unicodedata
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

# Rule 10: Tên file cố định 17 ký tự
OUTPUT_CSV = ROOT_DIR / "FR_AGCY_PJAU_0RAW.csv"
NATIVE_CHROME_PROFILE = Path.home() / ".gemini" / "antigravity" / "chrome_pj_native"

TARGET_LISTS = [
    {
        "category": "Recrutement international",
        "base_url": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=Recrutement+international&ou=Paris+%2875000%29&univers=pagesjaunes&idOu=",
        "page_url_template": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=Recrutement+international&ou=Paris+%2875000%29&page={page}",
        "max_pages": 10
    },
    {
        "category": "Agences d'intérim",
        "base_url": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=agences%20d%20interim&ou=Paris%20%2875000%29&idOu=L07505600&page=1&contexte=CDyI98hN/MJ6b3/P9OwrGnflmj0om2e6TKLxy8bWq8SbT4q6rbRhvECOrsEsMzCxjERSMQmS%2BLKj9gyyqTksIuTqV86RMIcFNsYme2oL5uQ%3D&quoiQuiInterprete=agences%20d%20interim",
        "page_url_template": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=agences%20d%20interim&ou=Paris%20%2875000%29&idOu=L07505600&page={page}&quoiQuiInterprete=agences%20d%20interim",
        "max_pages": 40
    }
]

# Rule 12: Danh sách đen cố định
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

def format_french_phone(phone_raw):
    if not phone_raw:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone_raw).strip())
    if clean.startswith("0") and len(clean) == 10:
        clean = "+33" + clean[1:]
    elif clean.startswith("0033"):
        clean = "+33" + clean[4:]
    elif clean.startswith("33") and len(clean) == 11:
        clean = "+" + clean
    return f"'{clean}" if clean and not clean.startswith("'") else clean

def load_existing_records():
    records = {}
    if OUTPUT_CSV.exists():
        try:
            with open(OUTPUT_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    name = r.get("Name", "").strip().lower()
                    pj_url = r.get("PagesJaunes_URL", "").strip()
                    key = pj_url if pj_url else name
                    if key:
                        records[key] = r
        except Exception as e:
            print(f"[!] Warning load existing CSV: {e}")
    return records

def launch_native_google_chrome(port=9222):
    """Khởi chạy trình duyệt Google Chrome THẬT 100% từ Windows (kế thừa từ harvest_rekvizitai_wood.py)"""
    NATIVE_CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.8):
            print(f"[*] Phát hiện Google Chrome thật đang chạy sẵn trên cổng {port}. Kết nối ngay...")
            return None
    except Exception:
        pass

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe")
    ]
    chrome_exe = next((p for p in chrome_paths if os.path.exists(p)), None)
    if not chrome_exe:
        raise RuntimeError("Không tìm thấy chrome.exe trên máy tính! Vui lòng kiểm tra lại Google Chrome.")

    print(f"\n[*] Đang khởi chạy Google Chrome THẬT 100% từ hệ điều hành Windows:")
    print(f"    Exe    : {chrome_exe}")
    print(f"    Profile: {NATIVE_CHROME_PROFILE}")
    print(f"    Port   : {port}")

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={NATIVE_CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=fr-FR",
        "--start-maximized"
    ]
    proc = subprocess.Popen(cmd)
    time.sleep(3.0)
    return proc

async def handle_cookie_consent(page):
    try:
        cookie_selectors = [
            "#didomi-notice-agree-button",
            "button:has-text('Accepter & Fermer')",
            "button:has-text('Continuer sans accepter')",
            "button:has-text('Tout accepter')",
            "button:has-text('Accepter tout')",
            "#didomi-notice-learn-more-button"
        ]
        for sel in cookie_selectors:
            btn = page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                print(f"[+] Bấm chấp nhận Cookie Didomi...")
                await btn.first.click()
                await asyncio.sleep(1.5)
                return True
    except Exception:
        pass
    return False

async def wait_for_human_verification(page):
    """Theo dõi và tự động click checkbox Cloudflare Turnstile trong frame nếu có"""
    alert_printed = False
    for sec in range(1, 150):
        try:
            if page.is_closed():
                return False
            title = (await page.title() or "").lower()
            content = (await page.content()).lower()

            for f in page.frames:
                try:
                    if "cloudflare" in f.url or "challenge" in f.url:
                        chk = await f.query_selector("input[type='checkbox'], .cb-lb, #challenge-stage")
                        if chk:
                            print("[*] Phát hiện ô checkbox Turnstile, đang tự động click...")
                            await chk.click()
                            await asyncio.sleep(1.5)
                except Exception:
                    pass

            is_cf = (
                "just a moment" in title
                or "un instant" in title
                or "sécurité" in content
                or "challenge" in content
                or "challenges.cloudflare.com" in content
            )
            has_content = (
                await page.query_selector("article.bi-bloc, .bi-bloc, .bi, .bi-listing-item, [id^='bi-']") is not None
                or "trouvez plus que" not in title and "rechercher" in content
            )

            if has_content and not is_cf:
                return True

            if not alert_printed:
                sys.stdout.write('\a\a\a')
                sys.stdout.flush()
                print("\n" + "=" * 80)
                print("🚨 [XÁC THỰC CLOUDFLARE TRÊN GOOGLE CHROME THẬT]")
                print("👉 Vui lòng click vào ô 'Verify you are human' nếu xuất hiện trên cửa sổ Chrome.")
                print("=" * 80 + "\n")
                alert_printed = True

            await asyncio.sleep(2.0)
        except Exception:
            await asyncio.sleep(2.0)

    return False

def extract_phone_from_text_or_node(card_soup):
    # 1. Check href="tel:..."
    tel_a = card_soup.select_one("a[href^='tel:']")
    if tel_a and tel_a.get("href"):
        clean_p = re.sub(r"^tel:\s*", "", tel_a["href"], flags=re.I).strip()
        formatted = format_french_phone(clean_p)
        if formatted:
            return formatted
            
    # 2. Check specific phone classes
    for sel in [".bi-contact-tel", "span[itemprop='telephone']", ".coord-numero", ".bi-fantomas-tel", "[data-pj-analytics*='telephone']"]:
        el = card_soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            m = re.search(r'\b(0[1-9](?:[\s.-]?\d{2}){4}|\+33\s?[1-9](?:[\s.-]?\d{2}){4})\b', txt)
            if m:
                return format_french_phone(m.group(1))

    # 3. Regex over the whole card text
    card_text = card_soup.get_text(" ", strip=True)
    m = re.search(r'\b(0[1-9](?:[\s.-]?\d{2}){4}|\+33\s?[1-9](?:[\s.-]?\d{2}){4})\b', card_text)
    if m:
        return format_french_phone(m.group(1))

    return ""

def extract_website_from_card(card_soup):
    for a in card_soup.select("a[href]"):
        href = a.get("href", "")
        if "urldirecte=" in href:
            m = re.search(r'urldirecte=([^&]+)', href)
            if m:
                u = urllib.parse.unquote(m.group(1))
                if u.startswith("http"):
                    return u
        if "/pj_redirect" in href or "pagesjaunes.fr/redirect" in href:
            m = re.search(r'[?&]url=([^&]+)', href)
            if m:
                u = urllib.parse.unquote(m.group(1))
                if u.startswith("http"):
                    return u
        if href.startswith("http") and not any(d in href for d in ["pagesjaunes.fr", "solocal.com", "google.com", "facebook.com", "instagram.com"]):
            return href

    for a in card_soup.select("[data-pj-analytics*='site_internet'], [data-pj-analytics*='web']"):
        href = a.get("href", "")
        if href.startswith("http") and "pagesjaunes.fr" not in href:
            return href

    return ""

async def extract_cards_from_page(page, source_category, records_dict, writer, f_out):
    # Click hiển thị số điện thoại cho toàn bộ thẻ trên trang
    try:
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, a'));
            for (const b of btns) {
                const txt = (b.innerText || '').toLowerCase();
                if (txt.includes('afficher le numéro') || txt.includes('afficher le n°') || txt.includes('numéro')) {
                    try { b.click(); } catch(e) {}
                }
            }
        }""")
        await asyncio.sleep(1.0)
    except Exception:
        pass

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    cards = soup.select("article.bi-bloc, li.bi-bloc, .bi-bloc, article.bi, .bi-listing-item, [id^='bi-']")
    if not cards:
        cards = soup.select("[data-pj-analytics]")
        
    extracted_count = 0
    updated_count = 0
    
    for card in cards:
        name_el = card.select_one(".denomination-links, .company-name, h3, .giz-__title, a.bi-denomination")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 2 or is_blacklisted_company(name):
            continue
            
        act_el = card.select_one(".activite, .bi-activity, .bi-activite, .bi-tag")
        activity = act_el.get_text(strip=True) if act_el else source_category
        
        addr_el = card.select_one(".adresse-bloc, .bi-address, .address, .bi-adresse")
        address = addr_el.get_text(" ", strip=True) if addr_el else ""
        postal_code = ""
        pc_match = re.search(r"\b(75\d{3}|92\d{3}|93\d{3}|94\d{3})\b", address)
        if pc_match:
            postal_code = pc_match.group(1)
            
        phone = extract_phone_from_text_or_node(card)
        website = extract_website_from_card(card)
                
        pj_link = ""
        if name_el and name_el.name == "a" and name_el.get("href"):
            h = name_el.get("href")
            pj_link = "https://www.pagesjaunes.fr" + h if not h.startswith("http") else h
            
        key = pj_link if pj_link else name.lower().strip()
        
        if key not in records_dict:
            rec = {
                "Name": name,
                "Activity": activity,
                "Address": address,
                "Postal_Code": postal_code,
                "City": "Paris",
                "Country": "France",
                "Phone": phone,
                "Website": website,
                "PagesJaunes_URL": pj_link,
                "Category_Source": source_category
            }
            records_dict[key] = rec
            writer.writerow(rec)
            f_out.flush()
            extracted_count += 1
            print(f"      [+] {name[:30]:<30} | {phone:<15} | {website[:25]}")
        else:
            # Cập nhật thêm nếu trước đó bị thiếu SĐT hoặc Website
            existing = records_dict[key]
            changed = False
            if not existing.get("Phone") and phone:
                existing["Phone"] = phone
                changed = True
            if not existing.get("Website") and website:
                existing["Website"] = website
                changed = True
            if changed:
                updated_count += 1
                print(f"      [*] Cập nhật SĐT/Web: {name[:30]} -> {phone} | {website[:25]}")
            
    return extracted_count, updated_count

async def enrich_missing_details(page, records_dict):
    """Bước bổ sung: Quét trang chi tiết (/pros/...) cho các công ty chưa lấy được SĐT trên danh sách"""
    missing = [r for r in records_dict.values() if not r.get("Phone") and r.get("PagesJaunes_URL")]
    if not missing:
        return
        
    print("\n" + "=" * 80)
    print(f"🔍 [QUÉT TRANG CHI TIẾT] Đang bổ sung SĐT cho {len(missing)} công ty chưa có SĐT...")
    print("=" * 80)
    
    enriched = 0
    for idx, rec in enumerate(missing, 1):
        url = rec["PagesJaunes_URL"]
        name = rec["Name"]
        try:
            print(f"  [{idx:02d}/{len(missing):02d}] {name[:30]:<30} ...", end=" ", flush=True)
            await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(0.8)
            
            # Click nút hiện SĐT trên trang chi tiết
            try:
                btn = page.locator("button:has-text('Afficher le numéro'), a:has-text('Afficher le numéro')").first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.3)
            except Exception:
                pass
                
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            phone = extract_phone_from_text_or_node(soup)
            website = extract_website_from_card(soup)
            
            if phone and not rec.get("Phone"):
                rec["Phone"] = phone
                enriched += 1
            if website and not rec.get("Website"):
                rec["Website"] = website
                
            print(f"-> {rec.get('Phone', 'Chưa có')} | {rec.get('Website', '')[:25]}")
        except Exception as e:
            print(f"-> Lỗi: {e}")
            
    print(f"[+] Hoàn thành quét trang chi tiết: Đã bổ sung SĐT cho {enriched} doanh nghiệp.")

async def harvest_all_pages(page, writer, f_out, records_dict):
    total_added = 0
    
    for target in TARGET_LISTS:
        cat_name = target["category"]
        base_url = target["base_url"]
        url_template = target["page_url_template"]
        max_page = target["max_pages"]
        
        print("\n" + "=" * 80)
        print(f"📂 [DANH MỤC] {cat_name.upper()} (Tối đa {max_page} trang)")
        print(f"   URL Khởi đầu: {base_url}")
        print("=" * 80)
        
        await page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
        await wait_for_human_verification(page)
        await handle_cookie_consent(page)
        await asyncio.sleep(2.0)
        
        current_page = 1
        consecutive_zero = 0
        
        while current_page <= max_page:
            print(f"\n  📄 [Trang {current_page:02d}/{max_page:02d}] Đang bóc tách thẻ doanh nghiệp...")
            await handle_cookie_consent(page)
            
            # Cuộn trang từ từ xuống cuối để kích hoạt toàn bộ lazy DOM
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 900)")
                await asyncio.sleep(0.5)
                
            added, updated = await extract_cards_from_page(page, cat_name, records_dict, writer, f_out)
            total_added += added
            print(f"  --> Trang {current_page:02d}: +{added} mới (Cập nhật: {updated}) | Tổng cộng: {len(records_dict)} cty.")
            
            if added == 0 and updated == 0:
                consecutive_zero += 1
                if consecutive_zero >= 2:
                    print(f"  [*] Đã hết kết quả mới ở trang {current_page}. Chuyển danh mục tiếp theo.")
                    break
            else:
                consecutive_zero = 0
                
            # Phân trang: Ưu tiên click nút Next trên DOM, nếu không thấy thì dùng URL template
            next_page_num = current_page + 1
            has_next = False
            
            # Cuộn hẳn xuống đáy trang để lộ thanh phân trang
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.0)
            
            next_selectors = [
                f"a[href*='page={next_page_num}']",
                "a.pagination-suivante",
                "a[title*='suivante']",
                "a[title*='Suivante']",
                "a[id*='pagination-next']",
                "a.next",
                "button:has-text('Suivant')"
            ]
            
            for sel in next_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        print(f"  [>] Bấm lật trang DOM: {sel}...")
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        await asyncio.sleep(3.5)
                        has_next = True
                        current_page = next_page_num
                        break
                except Exception:
                    pass
                    
            if not has_next:
                # Fallback: Chuyển trang trực tiếp bằng URL param
                next_url = url_template.format(page=next_page_num)
                print(f"  [>] Chuyển trang tự động bằng URL: Trang {next_page_num}...")
                try:
                    await page.goto(next_url, wait_until='domcontentloaded', timeout=45000)
                    await asyncio.sleep(3.0)
                    
                    # Kiểm tra xem có kết quả không
                    cnt = await page.locator("article.bi-bloc, .bi-bloc, .bi, .bi-listing-item").count()
                    if cnt == 0:
                        print(f"  [*] Trang {next_page_num} không còn kết quả nào. Đã đến trang cuối cùng!")
                        break
                    has_next = True
                    current_page = next_page_num
                except Exception as e:
                    print(f"  [!] Lỗi chuyển trang URL: {e}")
                    break
                    
    # Sau khi duyệt hết danh mục, quét trang chi tiết nếu còn cty thiếu SĐT
    await enrich_missing_details(page, records_dict)
    
    return total_added

async def main():
    print("=" * 80)
    print("🇫🇷  HỆ THỐNG CÀO DỮ LIỆU PAGESJAUNES PARIS (PHÁP) - NATIVE GOOGLE CHROME")
    print("    CHẾ ĐỘ GOOGLE CHROME THẬT 100% (CDP PORT 9222 - KẾ THỪA REKVIZITAI LITVA)")
    print(f"    Tệp đầu ra: {OUTPUT_CSV.name}")
    print("=" * 80)
    
    records_dict = load_existing_records()
    print(f"[*] Đã nạp từ tệp CSV có sẵn: {len(records_dict)} doanh nghiệp.")
    
    fieldnames = [
        "Name", "Activity", "Address", "Postal_Code", "City", "Country",
        "Phone", "Website", "PagesJaunes_URL", "Category_Source"
    ]
    
    file_exists = OUTPUT_CSV.exists() and OUTPUT_CSV.stat().st_size > 0
    f_out = open(OUTPUT_CSV, "a" if file_exists else "w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()
        f_out.flush()

    chrome_proc = launch_native_google_chrome(port=9222)

    try:
        async with async_playwright() as p:
            print("[*] Đang kết nối tới Google Chrome thật qua cổng 9222...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            total_crawled = await harvest_all_pages(page, writer, f_out, records_dict)
            print(f"\n🎉 THU THẬP THÀNH CÔNG TỔNG CỘNG: {total_crawled} DOANH NGHIỆP MỚI!")

            await browser.close()
    finally:
        f_out.close()
        
        # Ghi đè lại toàn bộ file CSV để cập nhật các SĐT/Web vừa được bổ sung
        if records_dict:
            with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(records_dict.values())
                
        if chrome_proc:
            try:
                chrome_proc.terminate()
            except Exception:
                pass

    print("\n" + "=" * 80)
    print(f"✅ HOÀN TẤT! Toàn bộ 2 danh mục đã lưu trọn vẹn vào: {OUTPUT_CSV.name}")
    print(f"   Tổng số doanh nghiệp trong tệp: {len(records_dict)}")
    with_phone = sum(1 for r in records_dict.values() if r.get("Phone"))
    with_web = sum(1 for r in records_dict.values() if r.get("Website"))
    print(f"   - Có Số điện thoại : {with_phone} ({with_phone*100/len(records_dict):.1f}%)")
    print(f"   - Có Website link  : {with_web} ({with_web*100/len(records_dict):.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
