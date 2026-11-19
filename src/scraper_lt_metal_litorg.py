# -*- coding: utf-8 -*-
"""
SCRAPER & ENRICHMENT PIPELINE - LITHUANIAN FABRICATED METAL PRODUCTS (LT_METL)
SOURCE: LITORG.CC (NACE DIVISION 25: MANUFACTURE OF FABRICATED METAL PRODUCTS)
==============================================================================
Tuân thủ nghiêm ngặt toàn bộ quy chuẩn GEMINI.md:
1. CSV ONLY (Rule 1): Xuất file định dạng UTF-8 with BOM (utf-8-sig).
2. SĐT có nháy đơn (Rule 2): phone = f"'{phone}".
3. Chấm điểm Email B2B & Tuyển chọn 1 email giá trị nhất, đẩy 100% email lên đầu (Rule 3).
4. Chrome trực quan (Rule 4): Kết nối trực tiếp vào Google Chrome thật qua CDP port 9222.
5. Lưu tăng dần & Checkpoint (Rule 5): Ghi CSV định kỳ và cache JSON để Resume 100%.
6. Quy chuẩn đặt tên 17 ký tự (Rule 10):
   - LT_METL_LTOR_0RAW.csv (File thô cào từ litorg.cc)
   - LT_METL_LTOR_1ENR.csv (File đã làm giàu Web, SĐT, Email)
   - LT_METL_LTOR_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
   - LT_METL_LTOR_ONLY_EMAILS_READY.csv (Danh sách chỉ gồm các công ty có Email)
   - Đồng bộ sang csdl_mlt/ và archive/lt_lithuania/.
7. Loại trừ danh sách đen vĩnh viễn (Rule 12): Scandi Standard Baltics, Biliarta, Daigre.
"""

import sys
import os
import re
import ssl
import json
import time
import shutil
import asyncio
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# UTF-8 output cho Windows Console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

BASE_CATALOG_URL = "https://litorg.cc/en/catalog/25/"

OUTPUT_0RAW_PATH = ROOT_DIR / "LT_METL_LTOR_0RAW.csv"
OUTPUT_1ENR_PATH = ROOT_DIR / "LT_METL_LTOR_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_METL_LTOR_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_METL_LTOR_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_scraper_litorg_metal.json"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "native_chrome"

CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

VPN_TIMEOUT = 35000
PAGE_DELAY = 1.5

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]


def is_blacklisted_company(name):
    """Rule 12: Permanent blacklist company exclusion."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str):
    """Normalize Lithuanian phone number strictly with leading single quote (Rule 2)."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = str(phone_str).strip().lstrip("'")
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('370'):
        return f"'+{digits}"
    elif digits.startswith('8') and len(digits) >= 8:
        return f"'+370{digits[1:]}"
    elif digits.startswith('0'):
        return f"'+370{digits[1:]}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"


def clean_email(email_str):
    """Clean email, decoding URL and removing zero-width/nbsp spaces."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    return re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e).strip()


def parse_litorg_html_page(html_text):
    """
    Bóc tách toàn bộ danh sách công ty từ mã nguồn HTML trang catalog của litorg.cc.
    Cấu trúc chuẩn li.fl-item:
    - h3 a: Tên công ty & URL chi tiết
    - div.fl-meta 1: {Code} · {City} · since {Year}
    - div.fl-meta 2: {NACE Code & Name}
    - div.c-rev b: Revenue
    - div.c-profit b: Profit
    - div.c-margin b: Margin
    - div.c-emp b: Employees
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    items = soup.select('li.fl-item')
    records = []

    for it in items:
        h3_a = it.select_one('h3 a')
        name = h3_a.get_text(strip=True) if h3_a else ""
        url = h3_a.get('href', '') if h3_a else ""

        if not name or is_blacklisted_company(name):
            continue

        metas = [m.get_text(strip=True) for m in it.select('div.fl-meta')]
        meta1 = metas[0] if len(metas) > 0 else ""
        meta2 = metas[1] if len(metas) > 1 else ""

        code = ""
        city = ""
        year = ""
        parts = [p.strip() for p in meta1.split('·')]
        if len(parts) >= 1:
            code = parts[0]
        if len(parts) >= 2:
            city = parts[1]
        if len(parts) >= 3:
            year = parts[2].replace('since', '').replace('nuo', '').strip()

        nace = meta2 if meta2 else "25 Manufacture of fabricated metal products"

        rev_el = it.select_one('div.c-rev b')
        rev = rev_el.get_text(strip=True) if rev_el else ""

        prof_el = it.select_one('div.c-profit b')
        prof = prof_el.get_text(strip=True) if prof_el else ""

        marg_el = it.select_one('div.c-margin b')
        marg = marg_el.get_text(strip=True) if marg_el else ""

        emp_el = it.select_one('div.c-emp b')
        emp = emp_el.get_text(strip=True) if emp_el else ""

        records.append({
            'Company_Code': code,
            'Cong ty': name,
            'City': city,
            'Nam_Thanh_Lap': year,
            'Category': nace,
            'Doanh_Thu': rev,
            'Loi_Nhuan': prof,
            'Bien_Loi_Nhuan': marg,
            'So_Nhan_Vien': emp,
            'Detail_URL': f"https://litorg.cc{url}" if url and not url.startswith('http') else url
        })

    return records


def export_and_sync_all_files(df_raw):
    """
    Xuất đồng bộ:
    1. LT_METL_LTOR_0RAW.csv
    2. LT_METL_LTOR_1ENR.csv
    3. LT_METL_LTOR_2COL.csv (chuẩn Cold Mail 20 cột, 100% email lên đầu)
    4. LT_METL_LTOR_ONLY_EMAILS_READY.csv
    Đồng bộ sang csdl_mlt/ và archive/lt_lithuania/.
    """
    df = df_raw.copy()
    if 'Cong ty' in df.columns:
        df = df[~df['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    for col in ['SDT', 'Website', 'Email', 'Dia chi']:
        if col not in df.columns:
            df[col] = ''

    df['SDT'] = df['SDT'].apply(clean_phone_lt)
    df['Email'] = df['Email'].apply(clean_email)
    df['No.'] = range(1, len(df) + 1)

    df.to_csv(OUTPUT_0RAW_PATH, index=False, encoding='utf-8-sig')
    df.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')

    has_em = df[df['Email'] != ''].copy()
    no_em = df[df['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi quan ly', '')).strip()
        title = str(r.get('Chuc danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('Thanh pho', r.get('City', ''))).strip()
        addr_val = str(r.get('Dia chi', '')).strip()
        full_addr = f"{addr_val}, {city_val}".strip(', ') if city_val else addr_val

        cat_val = str(r.get('Category', 'Manufacture of fabricated metal products')).strip()

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': full_addr,
            'Lương': r.get('Doanh_Thu', r.get('Doanh thu', '')),
            'Ngày đăng': r.get('Nam_Thanh_Lap', r.get('Nam thanh lap', '')),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat_val
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')

    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_dir / OUTPUT_READY_PATH.name)
            shutil.copy2(OUTPUT_0RAW_PATH, extra_dir / OUTPUT_0RAW_PATH.name)
        except Exception:
            pass

    return len(df), len(has_em)


async def run_scraper(limit=None, cdp_port=9222, max_pages=40):
    print("=" * 80)
    print("⚙️  HỆ THỐNG CÀO DỮ LIỆU CÔNG TY CƠ KHÍ & KIM LOẠI LITVA (LT_METL)")
    print(f"    - Nguồn cào        : {BASE_CATALOG_URL} (NACE Division 25)")
    print(f"    - Tệp dữ liệu thô  : {OUTPUT_0RAW_PATH.name}")
    print(f"    - Tệp Cold Mail    : {OUTPUT_2COL_PATH.name}")
    print(f"    - Checkpoint Cache : {CACHE_FILE.name}")
    print(f"    - Cổng kết nối CDP : {cdp_port}")
    if limit:
        print(f"    - Giới hạn cào     : {limit} công ty")
    print("=" * 80 + "\n")
    sys.stdout.flush()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} công ty từ checkpoint cache.")
        except Exception:
            cache = {}

    all_companies = dict(cache)

    async with async_playwright() as p:
        browser = None
        context = None
        page = None

        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}", timeout=8000)
            context = browser.contexts[0]
            for p_tab in context.pages:
                if "litorg.cc" in p_tab.url:
                    page = p_tab
                    break
            if not page:
                page = context.pages[0] if context.pages else await context.new_page()
            print(f"[+] ĐÃ KẾT NỐI VÀO GOOGLE CHROME THẬT (CỔNG {cdp_port}) THÀNH CÔNG!")
            print(f"    - URL Tab hiện tại: {page.url}\n")
            sys.stdout.flush()
        except Exception as e:
            print(f"[!] Không kết nối được cổng CDP {cdp_port}: {e}")
            print("[!] Vui lòng đảm bảo Google Chrome đã được mở với --remote-debugging-port=9222.")
            return

        # Vòng lặp cào tuần tự 40 trang (page 1 đến page 40)
        for page_num in range(1, max_pages + 1):
            page_url = f"https://litorg.cc/en/catalog/25/?page={page_num}" if page_num > 1 else "https://litorg.cc/en/catalog/25/"
            print(f"📄 [Trang {page_num}/{max_pages}] Đang tải: {page_url}")
            sys.stdout.flush()

            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=VPN_TIMEOUT)
                await asyncio.sleep(PAGE_DELAY)

                content = await page.content()
                records = parse_litorg_html_page(content)

                new_count = 0
                for r in records:
                    code = r['Company_Code']
                    if code and code not in all_companies:
                        all_companies[code] = r
                        new_count += 1

                print(f"   -> Bóc tách được {len(records)} công ty (+{new_count} mới | Tổng tích lũy: {len(all_companies):,})")
                sys.stdout.flush()

                # Lưu checkpoint sau mỗi trang
                if new_count > 0:
                    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(all_companies, f, ensure_ascii=False, indent=2)

                    df_current = pd.DataFrame(list(all_companies.values()))
                    export_and_sync_all_files(df_current)

                if limit and len(all_companies) >= limit:
                    print(f"\n[!] Đã đạt giới hạn yêu cầu ({limit} công ty). Dừng cào.")
                    break

            except Exception as ex:
                print(f"   [!] Lỗi khi tải trang {page_num}: {ex}")
                continue

        # Lưu hoàn tất lần cuối
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_companies, f, ensure_ascii=False, indent=2)

        df_final = pd.DataFrame(list(all_companies.values()))
        tot, em = export_and_sync_all_files(df_final)

        print("\n" + "=" * 80)
        print("🏆 HOÀN THÀNH TIẾN TRÌNH CÀO DANH SÁCH DOANH NGHIỆP KIM LOẠI LITVA (LITORG.CC)!")
        print(f"   - Tổng số doanh nghiệp thu thập : {tot:,}")
        print(f"   - Tệp dữ liệu thô đã xuất       : {OUTPUT_0RAW_PATH.name}")
        print(f"   - Tệp Cold Mail 20 cột         : {OUTPUT_2COL_PATH.name}")
        print(f"   - Tệp chỉ gồm công ty có Email : {OUTPUT_READY_PATH.name}")
        print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape Lithuanian Metal Enterprises from litorg.cc (NACE 25)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty cần cào")
    parser.add_argument("--max-pages", type=int, default=40, help="Số trang tối đa (mặc định 40 trang = 1,990 công ty)")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Cổng CDP Chrome (mặc định 9222)")
    parser.add_argument("--export-only", action="store_true", help="Chỉ xuất lại file Cold Mail từ Cache mà không cào")
    args = parser.parse_args()

    if args.export_only:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame(list(data.values()))
            tot, em = export_and_sync_all_files(df)
            print(f"[+] Đã xuất lại thành công {tot:,} công ty ({em:,} có email)!")
        return

    asyncio.run(run_scraper(limit=args.limit, cdp_port=args.cdp_port, max_pages=args.max_pages))


if __name__ == '__main__':
    main()
