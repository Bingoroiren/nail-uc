# -*- coding: utf-8 -*-
"""
TRÌNH CÀO TRỰC TIẾP PAGESJAUNES PHÁP (PAGESJAUNES.FR) - BẢN STEALTH CHỐNG DETECT
================================================================================
Target: 
1. Recrutement international (Paris 75000)
2. Agences d'interim (Paris 75000)
Gộp chung vào 1 file duy nhất: FR_AGCY_PJAU_0RAW.csv
Quy chuẩn: GEMINI.md (Rule 1, 2, 4, 5, 8, 10, 11, 12)
"""

import os
import sys
import re
import csv
import json
import time
import asyncio
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

OUTPUT_CSV = ROOT_DIR / "FR_AGCY_PJAU_0RAW.csv"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "pagesjaunes_profile"

TARGET_LISTS = [
    {
        "category": "Recrutement international",
        "url": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=Recrutement+international&ou=Paris+%2875000%29&univers=pagesjaunes&idOu="
    },
    {
        "category": "Agences d'intérim",
        "url": "https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=agences%20d%20interim&ou=Paris%20%2875000%29&idOu=L07505600&page=1&contexte=CDyI98hN/MJ6b3/P9OwrGnflmj0om2e6TKLxy8bWq8SbT4q6rbRhvECOrsEsMzCxjERSMQmS%2BLKj9gyyqTksIuTqV86RMIcFNsYme2oL5uQ%3D&quoiQuiInterprete=agences%20d%20interim"
    }
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def check_current_network():
    try:
        req = urllib.request.Request("https://ipinfo.io/json", headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            country = data.get("country", "")
            ip = data.get("ip", "")
            org = data.get("org", "")
            return country, ip, org
    except Exception:
        return "UNKNOWN", "", ""

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def format_french_phone(phone_raw):
    if not phone_raw:
        return ""
    clean = re.sub(r"[^\d+]", "", phone_raw.strip())
    if clean.startswith("0") and len(clean) == 10:
        clean = "+33" + clean[1:]
    elif clean.startswith("0033"):
        clean = "+33" + clean[4:]
    return f"'{clean}" if clean and not clean.startswith("'") else clean

def load_seen_companies():
    seen = set()
    if OUTPUT_CSV.exists():
        try:
            with open(OUTPUT_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    name = r.get("Name", "").strip().lower()
                    phone = r.get("Phone", "").strip()
                    if name:
                        seen.add((name, phone))
        except Exception as e:
            print(f"[!] Warning load existing CSV: {e}")
    return seen

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
                print(f"[+] Bấm nút đồng ý Cookie: {sel}")
                await btn.first.click()
                await asyncio.sleep(2)
                return True
    except Exception:
        pass
    return False

async def wait_for_challenge_resolution(page):
    """Theo dõi và cảnh báo nếu gặp trang kiểm tra bảo mật của PagesJaunes"""
    for sec in range(1, 300):
        try:
            content = (await page.content()).lower()
            title = (await page.title() or "").lower()
            h1 = (await page.locator("h1").first.inner_text()).lower() if await page.locator("h1").count() > 0 else ""
            
            is_sec = "sécurité" in content or "challenge" in content or "just a moment" in title or "un instant" in title or "sécurité" in h1
            
            if not is_sec and "rechercher" in content or "trouvez plus que" not in title or await page.locator("article.bi-bloc, .bi-bloc, .bi").count() > 0:
                print(f"✅ ĐÃ VÀO ĐƯỢC TRANG KẾT QUẢ PAGESJAUNES! (Title: {await page.title()})")
                return True
                
            if sec == 1 or sec % 8 == 0:
                sys.stdout.write('\a\a\a')
                sys.stdout.flush()
                print(f"\n🚨 [{sec}s] BẢO MẬT CLOUDFLARE TURNSTILE ĐANG BẬT")
                print("👉 Vui lòng nhìn vào cửa sổ Google Chrome vừa mở.")
                print("👉 Nhấp vào ô 'Verify you are human' (hoặc hoàn thành xác thực).")
                print("💡 MẸO: Nếu bị hỏi lặp lại liên tục, hãy mở Proton VPN chuyển sang vị trí FRANCE (PHÁP) hoặc TẮT VPN.")
                sys.stdout.flush()
                
            await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(2)
            
    print("[!] Hết thời gian chờ xác thực bảo mật (5 phút).")
    return False

async def extract_cards_from_page(page, source_category, seen_companies, writer, f_out):
    try:
        show_phone_btns = page.locator("button:has-text('Afficher le numéro'), a:has-text('Afficher le numéro')")
        cnt = await show_phone_btns.count()
        if cnt > 0:
            for b_idx in range(min(cnt, 20)):
                try:
                    btn = show_phone_btns.nth(b_idx)
                    if await btn.is_visible():
                        await btn.click(timeout=1000)
                        await asyncio.sleep(0.2)
                except Exception:
                    pass
    except Exception:
        pass

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")
    
    cards = soup.select("article.bi-bloc, li.bi-bloc, .bi-bloc, article.bi, .bi-listing-item, [id^='bi-']")
    if not cards:
        cards = soup.select("[data-pj-analytics]")
        
    extracted_count = 0
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
            
        phone_el = card.select_one(".bi-contact-tel, span[itemprop='telephone'], .coord-numero, [data-pj-analytics*='telephone']")
        phone = ""
        if phone_el:
            phone_text = phone_el.get_text(strip=True)
            phone = format_french_phone(phone_text)
            
        web_el = card.select_one("a[data-pj-analytics*='site_internet'], .bi-site-web a, a.bi-links, a[href^='http']:not([href*='pagesjaunes.fr'])")
        website = ""
        if web_el and web_el.get("href"):
            w_href = web_el.get("href")
            if "urldirecte=" in w_href:
                m = re.search(r"urldirecte=([^&]+)", w_href)
                if m:
                    website = urllib.parse.unquote(m.group(1))
            elif not "pagesjaunes.fr" in w_href:
                website = w_href
                
        pj_link = ""
        if name_el and name_el.name == "a" and name_el.get("href"):
            h = name_el.get("href")
            pj_link = "https://www.pagesjaunes.fr" + h if not h.startswith("http") else h
            
        key = (name.lower().strip(), phone)
        if key not in seen_companies:
            seen_companies.add(key)
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
            writer.writerow(rec)
            f_out.flush()
            extracted_count += 1
            print(f"      [+] {name} | {phone} | {website[:30]}")
            
    return extracted_count

async def main():
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    seen_companies = load_seen_companies()
    
    country, ip, org = check_current_network()
    
    print("=" * 75)
    print("🇫🇷  BỘ CÀO DANH BẠ DOANH NGHIỆP PAGESJAUNES PARIS (PHÁP) - STEALTH")
    print(f"    - IP Hiện Tại: {ip} | Quốc Gia: {country} | Nhà Mạng: {org}")
    if country != "FR":
        print(f"    ⚠️  LƯU Ý QUAN TRỌNG: Bạn đang dùng IP ngoài nước Pháp ({country}).")
        print("       Nếu gặp lỗi lặp verify liên tục do Cloudflare, hãy mở Proton VPN")
        print("       chuyển sang server FRANCE (Pháp) hoặc tắt VPN!")
    print(f"    - Tệp xuất dữ liệu: {OUTPUT_CSV.name}")
    print(f"    - Đã có sẵn trước đó: {len(seen_companies)} doanh nghiệp")
    print("=" * 75 + "\n")
    sys.stdout.flush()

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

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ],
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris"
        )
        
        # Tiêm mã Stealth để xóa hoàn toàn dấu vết navigator.webdriver
        await context.add_init_script("""
            delete Object.getPrototypeOf(navigator).webdriver;
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['fr-FR', 'fr', 'en-US', 'en']
            });
        """)
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        total_new = 0
        for target in TARGET_LISTS:
            cat_name = target["category"]
            start_url = target["url"]
            print(f"\n===========================================================================")
            print(f"📂 [DANH MỤC] {cat_name.upper()}")
            print(f"   URL: {start_url}")
            print(f"===========================================================================")
            
            try:
                await page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"[!] Warning khi mở URL: {e}")
                
            passed = await wait_for_challenge_resolution(page)
            if not passed:
                print(f"[!] Bỏ qua danh mục {cat_name} do không vượt qua bảo mật.")
                continue
                
            await handle_cookie_consent(page)
            await asyncio.sleep(3)
            
            page_num = 1
            max_pages = 25
            while page_num <= max_pages:
                print(f"\n  📄 [Trang {page_num}] Đang bóc tách danh sách...")
                await handle_cookie_consent(page)
                
                for _ in range(4):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(0.8)
                    
                added = await extract_cards_from_page(page, cat_name, seen_companies, writer, f_out)
                total_new += added
                print(f"  --> Trang {page_num}: Bóc tách thêm {added} công ty mới (Tổng cộng: {len(seen_companies)} cty).")
                
                next_selectors = [
                    "a[id*='pagination-next']",
                    "a.pagination-next",
                    "a:has-text('Suivant')",
                    "a:has-text('Page suivante')",
                    "a[title*='suivante']",
                    "button:has-text('Suivant')"
                ]
                
                has_next = False
                for n_sel in next_selectors:
                    btn = page.locator(n_sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        print(f"  [>] Bấm chuyển trang qua: {n_sel}...")
                        try:
                            await btn.first.click()
                            await asyncio.sleep(4)
                            has_next = True
                            page_num += 1
                            break
                        except Exception as e:
                            print(f"[!] Lỗi click next: {e}")
                            
                if not has_next:
                    print(f"  [*] Đã hết các trang trong danh mục {cat_name}.")
                    break
                    
        f_out.close()
        await context.close()
        
    print("\n" + "=" * 75)
    print(f"🎉 HOÀN THÀNH CÀO PAGESJAUNES PARIS!")
    print(f"   - Tổng số doanh nghiệp mới thu thập được: {total_new}")
    print(f"   - Tệp CSV đã lưu: {OUTPUT_CSV.name}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
