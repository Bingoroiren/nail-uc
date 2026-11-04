# -*- coding: utf-8 -*-
"""
HARVEST & BUILD DEDICATED DATABASE:
THỰC PHẨM BÁNH KẸO & NƯỚC NGỌT LATVIA (SWEETS, PASTRIES & BEVERAGES)

Sources:
1. Dun & Bradstreet (D&B) - Beverage Manufacturing Latvia (239 companies)
   https://www.dnb.com/business-directory/lv/beverage_manufacturing/companies
2. Kompass - Pastries & Cakes Latvia
   https://www.kompass.com/z/lv/a/pastries-and-cakes/03590/
3. Kompass - Food & Beverages Wholesale Latvia
   https://www.kompass.com/z/lv/a/food-beverages-and-tobacco-wholesale/8125003/

Outputs:
- LV_SWET_WEBD_0RAW.csv & csdl_lv_food/LV_SWET_WEBD_0RAW.csv
- LV_SWET_WEBD_1ENR.csv & csdl_lv_food/LV_SWET_WEBD_1ENR.csv
- LV_SWET_WEBD_2COL.csv & csdl_lv_food/LV_SWET_WEBD_2COL.csv
"""

import sys
import os
import re
import csv
import json
import time
import unicodedata
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CSDL_DIR = ROOT_DIR / "csdl_lv_food"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "lv_bevg_swet_profile"

OUT_0RAW_ROOT = ROOT_DIR / "LV_SWET_WEBD_0RAW.csv"
OUT_0RAW_CSDL = CSDL_DIR / "LV_SWET_WEBD_0RAW.csv"

OUT_1ENR_ROOT = ROOT_DIR / "LV_SWET_WEBD_1ENR.csv"
OUT_1ENR_CSDL = CSDL_DIR / "LV_SWET_WEBD_1ENR.csv"

OUT_2COL_ROOT = ROOT_DIR / "LV_SWET_WEBD_2COL.csv"
OUT_2COL_CSDL = CSDL_DIR / "LV_SWET_WEBD_2COL.csv"

RAW_COLUMNS = ['Company', 'Website', 'Phone', 'Email', 'Address', 'Category', 'Source', 'Profile_URL']

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r"^['\"„“”«»]+|['\"„“”«»]+$", "", c).strip()
    c = re.sub(r"\s+", " ", c)
    return c

def normalize_key(name):
    if not name:
        return ""
    t = unicodedata.normalize('NFKD', str(name)).lower()
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'["\'„“”«»\(\)\[\]]', '', t)
    for lf in ['sia', 'as', 'a/s', 'ik', 'ps', 'ks', 'sabiedriba ar ierobezotu atbildibu', 'akciju sabiedriba']:
        t = re.sub(r'\b' + re.escape(lf) + r'\b', '', t)
    return re.sub(r'\s+', ' ', t).strip(' ,.-')

def clean_phone_lv(p):
    if not p or str(p) == 'nan':
        return ""
    s = str(p).strip().lstrip("'")
    digits = re.sub(r'[^\d+]', '', s)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('371'):
        return f"'+{digits}"
    elif (digits.startswith('6') or digits.startswith('2')) and len(digits) == 8:
        return f"'+371{digits}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"

def scrape_dnb_beverage(page):
    print("\n" + "=" * 70)
    print(" [1/2] CÀO DUN & BRADSTREET (D&B) - BEVERAGE MANUFACTURING (LATVIA)")
    print("=" * 70)

    base_url = "https://www.dnb.com/business-directory/lv/beverage_manufacturing/companies"
    dnb_results = []
    seen = set()

    for page_num in range(1, 6):
        url = f"{base_url}?page={page_num}"
        print(f"[*] Đang tải trang {page_num}/5: {url}")
        try:
            page.goto(url, timeout=45000)
            time.sleep(2.0)

            # Kiểm tra Cloudflare
            for wait_sec in range(30):
                title = page.title()
                if "Just a moment" in title or "Attention Required" in title or "Cloudflare" in title:
                    if wait_sec == 0:
                        print("\n\a" + "!" * 70)
                        print("[!] CLOUDFLARE DETECTED trên D&B: Vui lòng click xác thực trên cửa sổ Chrome nếu có...")
                        print("!" * 70)
                    time.sleep(2)
                else:
                    break

            # Đóng cookie banner nếu xuất hiện
            try:
                cookie_btn = page.query_selector('button#onetrust-accept-btn-handler, button:has-text("Agree & Proceed"), button:has-text("Accept All")')
                if cookie_btn and cookie_btn.is_visible():
                    cookie_btn.click()
                    time.sleep(1.0)
            except Exception:
                pass

            time.sleep(2.0)

            # Trích xuất dữ liệu qua DOM
            items = page.evaluate("""
            () => {
                const res = [];
                const links = document.querySelectorAll('a.companyName, a[href*="/company-information/"], a[href*="/company-profiles/"], a[href*="/business-directory/company"]');
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

            print(f"  -> Trang {page_num}: Phát hiện {len(items)} doanh nghiệp.")
            added_page = 0
            for it in items:
                comp = clean_company_name(it.get('name', ''))
                if not comp or len(comp) < 3 or is_blacklisted_company(comp):
                    continue

                loc = it.get('location', '')
                # Lọc quốc gia khác
                if loc and any(bad in loc.lower() for bad in ['estonia', 'lithuania', 'russia', 'poland', 'belarus', 'germany', 'sweden']):
                    continue

                k = normalize_key(comp)
                if k in seen:
                    continue
                seen.add(k)
                added_page += 1

                addr = loc if loc else "Latvia"
                if "latvia" not in addr.lower() and "riga" not in addr.lower() and "rīga" not in addr.lower():
                    addr = f"{addr}, Latvia"

                dnb_results.append({
                    'Company': comp,
                    'Website': "",
                    'Phone': "",
                    'Email': "",
                    'Address': addr,
                    'Category': "Nước ngọt / Đồ uống (Beverage Manufacturing)",
                    'Source': "dnb.com",
                    'Profile_URL': it.get('href') or url
                })

            print(f"     [+] Đã thêm +{added_page} công ty mới. Lũy kế D&B: {len(dnb_results)}.")
        except Exception as e:
            print(f"[-] Lỗi tải trang {page_num}: {e}")

    print(f"[✔] Tổng cộng bóc tách từ D&B: {len(dnb_results)} doanh nghiệp sản xuất đồ uống/nước ngọt.")
    return dnb_results

def scrape_kompass_pastries(page):
    print("\n" + "=" * 70)
    print(" [2/2] CÀO KOMPASS - BÁNH KẸO, BÁNH NGỌT & BÁN BUÔN THỰC PHẨM (LATVIA)")
    print("=" * 70)

    kompass_categories = [
        ("Bánh ngọt / Bánh kẹo (Pastries & Cakes)", "https://www.kompass.com/z/lv/a/pastries-and-cakes/03590/"),
        ("Bán buôn Thực phẩm & Đồ uống (Food & Beverage Wholesale)", "https://www.kompass.com/z/lv/a/food-beverages-and-tobacco-wholesale/8125003/"),
        ("Thực phẩm tổng hợp (Food & Agro)", "https://www.kompass.com/z/lv/a/food/03/")
    ]

    kompass_results = []
    seen = set()

    for cat_name, base_url in kompass_categories:
        print(f"\n[*] Đang điều hướng chuyên mục: {cat_name}")
        print(f"    URL: {base_url}")
        try:
            page.goto(base_url, timeout=45000)
            time.sleep(2.0)

            # Kiểm tra DataDome / Captcha
            for wait_sec in range(30):
                title = page.title()
                html = page.content()
                if "DataDome" in html or "captcha-delivery" in html or "Just a moment" in title:
                    if wait_sec == 0:
                        print("\n\a" + "!" * 70)
                        print("[!] CAPTCHA / DATADOME DETECTED trên Kompass: Vui lòng giải captcha trên cửa sổ Chrome nếu có...")
                        print("!" * 70)
                    time.sleep(2)
                else:
                    break

            # Đóng banner cookie
            try:
                cookie_btn = page.query_selector('button#onetrust-accept-btn-handler, button:has-text("Accept"), button:has-text("Pieņemt")')
                if cookie_btn and cookie_btn.is_visible():
                    cookie_btn.click()
                    time.sleep(1.0)
            except Exception:
                pass

            page_num = 1
            cat_count = 0
            while page_num <= 5:
                time.sleep(2.5)
                # Bóc tách DOM các thẻ công ty
                items = page.evaluate("""
                () => {
                    const res = [];
                    const links = document.querySelectorAll('a[href*="/c/"], a.product-list-item-title, h2.product-list-item-title a');
                    for (const a of links) {
                        const name = a.innerText.trim();
                        const href = a.href || '';
                        if (!name || name.length < 3) continue;
                        if (name.toLowerCase().includes('kompass') || name.toLowerCase().includes('contact')) continue;
                        
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

                print(f"  Trang {page_num}: Tìm thấy {len(items)} thẻ công ty.")
                new_on_page = 0
                for it in items:
                    comp = clean_company_name(it.get('name', ''))
                    if not comp or len(comp) < 3 or is_blacklisted_company(comp):
                        continue

                    loc = it.get('location', '')
                    if loc and any(bad in loc.lower() for bad in ['estonia', 'lithuania', 'russia', 'poland', 'belarus', 'germany']):
                        continue

                    k = normalize_key(comp)
                    if k in seen:
                        continue
                    seen.add(k)
                    new_on_page += 1
                    cat_count += 1

                    addr = loc if loc else "Latvia"
                    kompass_results.append({
                        'Company': comp,
                        'Website': "",
                        'Phone': "",
                        'Email': "",
                        'Address': addr,
                        'Category': f"{cat_name}",
                        'Source': "Kompass",
                        'Profile_URL': it.get('href') or base_url
                    })

                print(f"    -> Thêm +{new_on_page} công ty mới từ trang {page_num}.")

                # Kiểm tra nút chuyển trang
                next_btn = page.query_selector('a.pagination-next, a[rel="next"], a:has-text("Next"), li.next a, a[title="Next page"]')
                if next_btn and next_btn.is_visible() and new_on_page > 0:
                    print("  [*] Nhấn chuyển sang trang kế tiếp...")
                    next_btn.click()
                    page_num += 1
                else:
                    break

            print(f"  --> Hoàn tất {cat_name}: {cat_count} doanh nghiệp.")
        except Exception as e:
            print(f"[-] Lỗi cào chuyên mục {cat_name}: {e}")

    print(f"[✔] Tổng cộng bóc tách từ Kompass: {len(kompass_results)} doanh nghiệp.")
    return kompass_results

def main():
    print("=" * 80)
    print(" HỆ THỐNG CÀO DỮ LIỆU THỰC PHẨM BÁNH KẸO & NƯỚC NGỌT LATVIA")
    print(" Nguồn: Dun & Bradstreet (Đồ uống) + Kompass (Bánh kẹo & Bán buôn)")
    print("=" * 80)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    CSDL_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled', '--start-maximized']
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        # 1. Cào D&B Beverage
        dnb_records = scrape_dnb_beverage(page)

        # 2. Cào Kompass Pastries & Wholesale
        kompass_records = scrape_kompass_pastries(page)

        browser.close()

    # 3. Hợp nhất và khử trùng lặp
    all_raw = []
    seen_master = set()
    master_dict = {}

    for r in dnb_records + kompass_records:
        comp = r['Company']
        k = normalize_key(comp)
        if not k:
            continue

        if k in master_dict:
            # Gộp nguồn và chuyên mục nếu trùng
            existing = master_dict[k]
            if r['Source'] not in existing['Source']:
                existing['Source'] += f" + {r['Source']}"
            if r['Category'] not in existing['Category']:
                existing['Category'] += f", {r['Category']}"
        else:
            master_dict[k] = r

    final_unique = list(master_dict.values())
    print("\n" + "=" * 80)
    print(f" HOÀN TẤT THU THẬP VÀ KHỬ TRÙNG LẶP!")
    print(f" [*] Dun & Bradstreet (Đồ uống) : {len(dnb_records)} công ty")
    print(f" [*] Kompass (Bánh kẹo / buôn)   : {len(kompass_records)} công ty")
    print(f" [*] Tổng số công ty duy nhất   : {len(final_unique):,} công ty")
    print("=" * 80 + "\n")

    # 4. Xuất file 0RAW
    for out_path in [OUT_0RAW_ROOT, OUT_0RAW_CSDL]:
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
            writer.writeheader()
            writer.writerows(final_unique)
        print(f"[+] Đã lưu file thô 0RAW: {out_path}")

    # 5. Xuất file 1ENR
    for out_path in [OUT_1ENR_ROOT, OUT_1ENR_CSDL]:
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
            writer.writeheader()
            writer.writerows(final_unique)
        print(f"[+] Đã lưu file 1ENR: {out_path}")

    # 6. Xuất file 2COL (Chuẩn Cold Mail 20 cột)
    coldmail_rows = []
    for idx, r in enumerate(final_unique, 1):
        c_dict = {col: '' for col in COLUMNS_20}
        c_dict['No.'] = str(idx)
        c_dict['Công ty'] = r['Company']
        c_dict['SĐT'] = clean_phone_lv(r.get('Phone', ''))
        c_dict['Liên Hệ'] = r.get('Website', '')
        c_dict['Email'] = r.get('Email', '')
        c_dict['Liên Hệ mail'] = f"mailto:{r['Email']}" if r.get('Email') else ""
        c_dict['Địa chỉ'] = r.get('Address', 'Latvia')
        c_dict['Check gửi'] = 'OK' if r.get('Email') else ''
        c_dict['Category'] = r.get('Category', 'Thực phẩm Bánh kẹo & Nước ngọt')
        coldmail_rows.append(c_dict)

    for out_path in [OUT_2COL_ROOT, OUT_2COL_CSDL]:
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
            writer.writeheader()
            writer.writerows(coldmail_rows)
        print(f"[+] Đã lưu file chuẩn Cold Mail 2COL: {out_path}")

    print("\n[✔] TẤT CẢ CÁC TỆP ĐÃ ĐƯỢC XUẤT RA FILE RIÊNG BIỆT CHO BÁNH KẸO & NƯỚC NGỌT LATVIA!")

if __name__ == '__main__':
    main()
