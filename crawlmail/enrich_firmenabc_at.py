# -*- coding: utf-8 -*-
"""
FirmenABC.at Detail & Search Enrichment for Austrian Agency Dataset (AT_AGCY_COMB_2COL.csv):
1. Tra cuu truc tiep theo Detail_URL (neu da co link firmenabc.at) hoac Search theo Ten Cong ty.
2. So khop ten thong minh va nghiem ngat (Rule 11: Exact, Token Set, Delimiter, Legal forms Ao).
3. Boc tach Phone (luon co dau nhay don '), Email (mailto:), Website chinh thuc, Dia chi.
4. Neu tim thay Website ma FirmenABC chua co Email: Quet sau Website chinh thuc tim Email B2B
   (Uu tien DOM Menu Priority 10: /karriere, /jobs, /bewerbung, /kontakt, /impressum...).
5. Luu tang dan (Incremental Auto-Save) va Checkpoint JSON (Resume 100%).
6. Luon day 100% cong ty Co Email len dau danh sach CSV.
7. Dau ra:
   - AT_AGCY_COMB_2COL.csv (cap nhat truc tiep)
   - data/AT_AGCY_COMB_2COL.csv (dong bo luu kho)
   - AT_AGCY_GMAP_2COL.csv (chuan dat ten 17 ky tu [CC]_[IND4]_[SRC4]_[STG4].csv)
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import unicodedata
import urllib.parse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MAIN_CSV = str(ROOT_DIR / "AT_AGCY_COMB_2COL.csv")
DATA_DIR_CSV = str(ROOT_DIR / "data" / "AT_AGCY_COMB_2COL.csv")
OUTPUT_17CHAR = str(ROOT_DIR / "AT_AGCY_GMAP_2COL.csv")
BACKUP_CSV = str(ROOT_DIR / "data" / "AT_AGCY_COMB_2COL_pre_fabc_backup.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_firmenabc_at.json")

from crawlmail.enrich_maps_at_agcy import (
    clean_company_name_at,
    is_valid_name_match_at,
    score_email_b2b,
    crawl_website_for_contacts,
    HAS_CURL_CFFI
)

if HAS_CURL_CFFI:
    from curl_cffi.requests import AsyncSession
else:
    import aiohttp

EXCLUDED_DOMAINS = {
    'firmenabc', 'google', 'facebook', 'instagram', 'youtube', 'linkedin',
    'twitter', 'x.com', 'tiktok', 'cookiebot', 'adform', 'apple.com',
    'creditreform', 'tripadvisor', 'yellowpages', 'herold.at', 'wko.at'
}

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

def clean_phone_format(raw_phone):
    if not raw_phone:
        return ""
    p = re.sub(r'tel:', '', str(raw_phone), flags=re.I).strip()
    # Format Austria: ensure single quote
    p_clean = re.sub(r'[^\d+/\s\-()]', '', p).strip()
    if p_clean and not p_clean.startswith("'"):
        p_clean = f"'{p_clean}"
    return p_clean

def clean_email_format(raw_email):
    if not raw_email:
        return ""
    e = re.sub(r'mailto:', '', str(raw_email), flags=re.I).split('?')[0].strip()
    e = urllib.parse.unquote(e).replace('%20', '').strip().lower().rstrip('.,;:')
    if '@' in e and '.' in e.split('@')[-1]:
        return e
    return ""

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def save_csv_and_sync(rows, fieldnames):
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    sorted_rows = with_email + without_email

    for target_path in [MAIN_CSV, DATA_DIR_CSV, OUTPUT_17CHAR]:
        try:
            out_dir = os.path.dirname(os.path.abspath(target_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            temp = target_path + ".tmp"
            with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_rows)
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass
            os.rename(temp, target_path)
        except Exception as e:
            print(f"[!] Canh bao loi luu file {target_path}: {e}")

async def extract_firmenabc_detail(page, url):
    """Bóc tách thông tin liên hệ từ trang chi tiết FirmenABC"""
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"       [-] Loi nap trang detail: {e}")
        return None

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    phone = ""
    email = ""
    website = ""
    address = ""

    # 1. Phone
    tel_a = soup.find("a", href=lambda h: h and h.startswith("tel:"))
    if tel_a:
        phone = clean_phone_format(tel_a.get("href") or tel_a.get_text(strip=True))

    # 2. Email
    mail_a = soup.find("a", href=lambda h: h and h.startswith("mailto:"))
    if mail_a:
        email = clean_email_format(mail_a.get("href") or mail_a.get_text(strip=True))

    # 3. Website
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        txt = a.get_text(strip=True).lower()
        if h.startswith(("http://", "https://")):
            if not any(ex in h.lower() for ex in EXCLUDED_DOMAINS):
                # Verify txt contains domain hints
                if "www." in txt or txt.startswith("http") or txt.endswith((".at", ".com", ".de", ".net", ".eu", ".org")):
                    website = h
                    break
                elif not website and "firmenabc" not in h.lower():
                    website = h

    # 4. Address block
    for div in soup.find_all(["div", "section", "p"]):
        t = div.get_text(" ", strip=True)
        if "T:" in t and ("M:" in t or "W:" in t):
            # Block e.g. Welthandelsplatz 1 1020 Wien T: ...
            addr_part = t.split("T:")[0].strip()
            if addr_part and len(addr_part) > 5:
                address = addr_part
                break

    return {
        "phone": phone,
        "email": email,
        "website": website,
        "address": address,
        "detail_url": url
    }

async def search_firmenabc_for_company(page, company_name, city=""):
    """Tìm kiếm công ty trên FirmenABC qua ô tìm kiếm trang chủ"""
    try:
        # Nếu chưa ở firmenabc.at, điều hướng về trang chủ
        if "firmenabc.at" not in page.url:
            await page.goto("https://www.firmenabc.at/", timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

        search_input = page.locator("input#whatSearchField, input[name*='sword'], input[placeholder*='Firma']")
        if await search_input.count() == 0:
            await page.goto("https://www.firmenabc.at/", timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

        clean_name = re.sub(r'["\'„“”«»]', '', company_name).strip()
        await search_input.first.fill(clean_name)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)

        # Trích xuất danh sách link kết quả tìm kiếm
        results = await page.locator("a[href*='_']").all()
        candidates = []
        for r in results:
            h = await r.get_attribute("href")
            txt = (await r.inner_text()).strip()
            if txt and h and not any(ex in h for ex in ["javascript", "login", "firmen/", "crefo", "ki-check", "com/?"]):
                candidates.append((txt, h))

        if not candidates:
            return None

        # So khớp thông minh & nghiêm ngặt
        for txt, href in candidates:
            matched, mtype = is_valid_name_match_at(clean_name, txt)
            if matched:
                full_url = urllib.parse.urljoin("https://www.firmenabc.at", href)
                print(f"       [Match Found] '{txt}' [{mtype}] -> {full_url}")
                return await extract_firmenabc_detail(page, full_url)

    except Exception as e:
        print(f"       [-] Loi tim kiem FirmenABC: {e}")

    return None

async def main():
    if not os.path.exists(MAIN_CSV):
        print(f"[-] Khong tim thay tep nguon: {MAIN_CSV}")
        return

    # Backup truoc khi xu ly
    import shutil
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(MAIN_CSV, BACKUP_CSV)
        print(f"[*] Da tao backup an toan: {BACKUP_CSV}")

    cache = load_cache()

    with open(MAIN_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        raw_rows = list(reader)

    # Loc bo vinh vien cac cong ty trong Blacklist (Rule 12)
    rows = [r for r in raw_rows if not is_blacklisted_company(r.get('Company', ''))]
    if len(rows) < len(raw_rows):
        print(f"[*] Da tu dong loai bo {len(raw_rows) - len(rows)} cong ty thuoc Blacklist.")

    total_rows = len(rows)
    initial_with_email = len([r for r in rows if r.get('Email', '').strip()])
    missing_email_rows = [r for r in rows if not r.get('Email', '').strip()]

    print("=" * 80)
    print("🚀 BẮT ĐẦU LÀM GIÀU DỮ LIỆU AGENCY ÁO QUA FIRMENABC.AT")
    print(f"📊 Tổng số doanh nghiệp trong file : {total_rows}")
    print(f"✉️ Doanh nghiệp ĐÃ CÓ Email        : {initial_with_email}")
    print(f"🔍 Doanh nghiệp CẦN LÀM GIÀU Email : {len(missing_email_rows)}")
    print(f"💾 File lưu chính                 : {MAIN_CSV}")
    print("=" * 80)

    session = AsyncSession(verify=False) if HAS_CURL_CFFI else aiohttp.ClientSession()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="de-AT",
            geolocation={"latitude": 48.2082, "longitude": 16.3738},
            permissions=["geolocation"]
        )
        page = await context.new_page()

        # Nạp trang chủ FirmenABC để thiết lập session ban đầu
        print("[*] Khoi tao phien duyet tren FirmenABC.at...")
        try:
            await page.goto("https://www.firmenabc.at/", timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # Accept cookies neu co popup
            cookie_btn = page.locator('button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, button:has-text("Alle akzeptieren")')
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        enriched_count = 0
        new_emails_count = 0

        for idx, row in enumerate(rows):
            company = row.get("Company", "").strip()
            city = row.get("City", "").strip()
            curr_email = row.get("Email", "").strip()
            curr_phone = row.get("Phone", "").strip()
            curr_web = row.get("Website", "").strip()
            detail_url = row.get("Detail_URL", "").strip()

            # Chi xu ly cac cong ty DANG THIEU EMAIL (hoac thieu Phone/Web)
            if curr_email and curr_phone and curr_web:
                continue

            print(f"\n[{idx+1}/{total_rows}] [*] Doanh nghiep: '{company}' ({city or 'Austria'})")
            updated = False

            cache_key = f"FABC_{company.upper()}_{city.upper()}"
            fabc_data = cache.get(cache_key)

            if fabc_data is None:
                # 1. Neu Detail_URL da la FirmenABC -> truy cap thang
                if "firmenabc.at" in detail_url and "_" in detail_url:
                    print(f"    [*] Truoc do da co link FirmenABC: {detail_url}")
                    fabc_data = await extract_firmenabc_detail(page, detail_url)
                else:
                    # 2. Neu chua co link FirmenABC -> Tim kiem qua search box
                    print(f"    [*] Tim kiem tren FirmenABC cho: '{company}'...")
                    fabc_data = await search_firmenabc_for_company(page, company, city)

                cache[cache_key] = fabc_data if fabc_data else {"not_found": True}
                save_cache(cache)
                await asyncio.sleep(1.0)
            else:
                if fabc_data.get("not_found"):
                    print(f"    [Cache] FirmenABC khong tim thay.")
                else:
                    print(f"    [Cache] FirmenABC da luu: {fabc_data.get('detail_url')}")

            # Xu ly ket qua bóc tách duoc tu FirmenABC
            if fabc_data and not fabc_data.get("not_found"):
                f_phone = fabc_data.get("phone", "")
                f_email = fabc_data.get("email", "")
                f_web = fabc_data.get("website", "")
                f_addr = fabc_data.get("address", "")
                f_url = fabc_data.get("detail_url", "")

                # Bo sung Phone
                if f_phone and not curr_phone:
                    row["Phone"] = f_phone
                    print(f"       + SĐT moi (FirmenABC)  : {f_phone}")
                    updated = True
                    curr_phone = f_phone

                # Bo sung Website
                if f_web and not curr_web:
                    row["Website"] = f_web
                    print(f"       + Website (FirmenABC)  : {f_web}")
                    updated = True
                    curr_web = f_web

                # Bo sung Address
                if f_addr and not row.get("Address", "").strip():
                    row["Address"] = f_addr
                    print(f"       + Dia chi (FirmenABC)  : {f_addr}")
                    updated = True

                # Bo sung Detail_URL neu hop le
                if f_url and "firmenabc.at" not in detail_url:
                    row["Detail_URL"] = f_url

                # Cap nhat Source
                if "FirmenABC" not in row.get("Source", ""):
                    row["Source"] = (row.get("Source", "").strip() + " + FirmenABC.at").strip(" +")

                # Bo sung Email tu FirmenABC
                if f_email and not curr_email:
                    row["Email"] = f_email
                    row["Lead_Score"] = str(score_email_b2b(f_email, curr_web))
                    row["Verified_Date"] = datetime.now().strftime("%Y-%m")
                    print(f"       ✨ EMAIL MOI (FirmenABC): {f_email} [Score: {row['Lead_Score']}]")
                    updated = True
                    new_emails_count += 1
                    curr_email = f_email

                # Neu FirmenABC co Website ma chua co Email (hoac can quet sau): Quet website
                effective_web = row.get("Website", "").strip()
                if not row.get("Email", "").strip() and effective_web:
                    print(f"    [*] Quet sau Website chinh thuc tim Email B2B: {effective_web}...")
                    found_web_email, fb = await crawl_website_for_contacts(effective_web, session)
                    if found_web_email:
                        row["Email"] = found_web_email
                        row["Lead_Score"] = str(score_email_b2b(found_web_email, effective_web))
                        row["Verified_Date"] = datetime.now().strftime("%Y-%m")
                        print(f"       ✨ EMAIL B2B (Tu Web chinh thuc): {found_web_email} [Score: {row['Lead_Score']}]")
                        updated = True
                        new_emails_count += 1

            if updated:
                enriched_count += 1
                save_csv_and_sync(rows, fieldnames)
            else:
                print(f"    [-] Khong tim thay them thong tin moi.")

            # Checkpoint dinh ky moi 5 cong ty
            if (idx + 1) % 5 == 0:
                save_csv_and_sync(rows, fieldnames)

        await browser.close()

    if not HAS_CURL_CFFI:
        await session.close()

    save_csv_and_sync(rows, fieldnames)
    final_with_email = len([r for r in rows if r.get('Email', '').strip()])

    print("\n" + "=" * 80)
    print("🎉 HOAN TAT LAM GIAU DU LIEU QUA FIRMENABC.AT!")
    print(f"📊 Tong so doanh nghiep da xu ly       : {total_rows}")
    print(f"✨ So cong ty duoc bo sung thong tin   : {enriched_count}")
    print(f"✉️ So EMAIL MOI tim thay               : +{new_emails_count}")
    print(f"📈 TONG CONG TY CO EMAIL HIEN TAI      : {final_with_email} (Tang tu {initial_with_email})")
    print(f"💾 File luu chinh                      : {MAIN_CSV}")
    print(f"💾 File chuan 17 ky tu                 : {OUTPUT_17CHAR}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
