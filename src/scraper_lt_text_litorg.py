# -*- coding: utf-8 -*-
"""
SCRAPER PIPELINE - LITHUANIAN TEXTILES & APPAREL ENTERPRISES (LT_TEXT)
SOURCE: LITORG.CC (NACE 13: TEXTILES & NACE 14: WEARING APPAREL)
======================================================================
Strictly follows GEMINI.md workspace rules:
1. CSV ONLY (Rule 1): UTF-8 with BOM (utf-8-sig).
2. Phone formatting (Rule 2): phone strictly prefixed with `'`.
3. B2B Email selection & sorting (Rule 3): 100% email rows pushed to top.
4. Incremental auto-save & checkpoint (Rule 5): cache JSON for 100% resume capability.
5. 17-character fixed filename convention (Rule 10):
   - LT_TEXT_LTOR_0RAW.csv (Raw scraped dataset from litorg.cc)
   - LT_TEXT_LTOR_2COL.csv (Standard 20-column Cold Mail format)
   - Synchronized to csdl_mlt/ and archive/lt_lithuania/.
6. Permanent blacklist exclusion (Rule 12): Scandi Standard Baltics, Biliarta, Daigre.
"""

import sys
import os
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
import ssl
import unicodedata
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

# Ensure UTF-8 output for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

CATALOG_SOURCES = [
    {
        'id': '13',
        'name': 'Manufacture of textiles',
        'base_url': 'https://litorg.cc/en/catalog/13/',
        'max_pages': 11
    },
    {
        'id': '14',
        'name': 'Manufacture of wearing apparel',
        'base_url': 'https://litorg.cc/en/catalog/14/',
        'max_pages': 19
    }
]

OUTPUT_0RAW_PATH = ROOT_DIR / "LT_TEXT_LTOR_0RAW.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_TEXT_LTOR_2COL.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_scraper_litorg_text.json"

CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

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
    """Clean email, decoding URL and removing zero-width/nbsp spaces (Rule 3)."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    return re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e).strip()

def parse_litorg_html_page(html_text, catalog_id, catalog_name):
    """
    Extract all company cards from litorg.cc catalog page (li.fl-item).
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

        nace = meta2 if meta2 else f"NACE {catalog_id} {catalog_name}"

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
            'Catalog_ID': catalog_id,
            'Catalog_Name': catalog_name,
            'Doanh_Thu': rev,
            'Loi_Nhuan': prof,
            'Bien_Loi_Nhuan': marg,
            'So_Nhan_Vien': emp,
            'Detail_URL': f"https://litorg.cc{url}" if url and not url.startswith('http') else url,
            'SDT': '',
            'Website': '',
            'Email': '',
            'Dia chi': f"{city}, Lithuania" if city else "Lithuania"
        })

    return records

def export_and_sync_all_files(all_records):
    """
    Exports:
    1. LT_TEXT_LTOR_0RAW.csv (Raw dataset)
    2. LT_TEXT_LTOR_2COL.csv (Cold Mail 20 columns)
    Syncs to csdl_mlt/ and archive/lt_lithuania/.
    """
    df = pd.DataFrame(all_records)
    if 'Cong ty' in df.columns:
        df = df[~df['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    # Clean fields
    for col in ['SDT', 'Website', 'Email', 'Dia chi']:
        if col not in df.columns:
            df[col] = ''

    df['SDT'] = df['SDT'].apply(clean_phone_lt)
    df['Email'] = df['Email'].apply(clean_email)
    df['No.'] = range(1, len(df) + 1)

    raw_cols = ['No.', 'Company_Code', 'Cong ty', 'City', 'Nam_Thanh_Lap', 'Category',
                'Catalog_ID', 'Catalog_Name', 'Doanh_Thu', 'Loi_Nhuan', 'Bien_Loi_Nhuan',
                'So_Nhan_Vien', 'Detail_URL', 'SDT', 'Website', 'Email', 'Dia chi']
    df_raw = df[[c for c in raw_cols if c in df.columns]]
    df_raw.to_csv(OUTPUT_0RAW_PATH, index=False, encoding='utf-8-sig')

    # Sort: companies with email on top (Rule 3)
    has_em = df[df['Email'] != ''].copy()
    no_em = df[df['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi quan ly', '')).strip()
        title = 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('City', '')).strip()
        addr_val = str(r.get('Dia chi', '')).strip()
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"

        cat_val = str(r.get('Category', '')).strip()

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val if web_val else r.get('Detail_URL', ''),
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': addr_val,
            'Lương': r.get('Doanh_Thu', ''),
            'Ngày đăng': r.get('Nam_Thanh_Lap', ''),
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

    # Sync to archive & csdl_mlt
    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_0RAW_PATH, extra_dir / OUTPUT_0RAW_PATH.name)
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
        except Exception:
            pass

    return len(df_raw), len(has_em)

def fetch_url(url, retries=3):
    """Fetch URL with retries and SSL context."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                if resp.status == 200:
                    return resp.read().decode('utf-8')
        except Exception as e:
            if attempt == retries:
                print(f"    [!] Error fetching {url}: {e}")
            time.sleep(1.5)
    return None

def main():
    print("=" * 80)
    print("🚀 HỆ THỐNG CÀO DỮ LIỆU DỆT MAY LITVA - NACE 13 & 14 (LITORG.CC)")
    print(f"    - Danh mục 13   : Manufacture of textiles (521 cty, 11 trang)")
    print(f"    - Danh mục 14   : Manufacture of wearing apparel (908 cty, 19 trang)")
    print(f"    - Tệp dữ liệu thô : {OUTPUT_0RAW_PATH.name}")
    print(f"    - Tệp Cold Mail   : {OUTPUT_2COL_PATH.name}")
    print(f"    - Checkpoint Cache: {CACHE_FILE.name}")
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

    total_pages = sum(c['max_pages'] for c in CATALOG_SOURCES)
    current_page_idx = 0

    for cat in CATALOG_SOURCES:
        cat_id = cat['id']
        cat_name = cat['name']
        max_p = cat['max_pages']

        print(f"\n📂 === ĐANG CÀO DANH MỤC {cat_id}: {cat_name.upper()} (TỐI ĐA {max_p} TRANG) ===")
        sys.stdout.flush()

        for p in range(1, max_p + 1):
            current_page_idx += 1
            page_url = f"{cat['base_url']}?page={p}" if p > 1 else cat['base_url']
            print(f"[{current_page_idx}/{total_pages}] Trang {p}/{max_p} [Cat {cat_id}]: {page_url} ...", end=" ", flush=True)

            html = fetch_url(page_url)
            if not html:
                print("❌ THẤT BẠI!")
                continue

            records = parse_litorg_html_page(html, cat_id, cat_name)
            new_added = 0
            for r in records:
                code = r['Company_Code']
                if code and code not in all_companies:
                    all_companies[code] = r
                    new_added += 1
                elif code in all_companies:
                    # Update category info if belongs to both
                    curr_cat = all_companies[code]['Category']
                    if r['Category'] not in curr_cat:
                        all_companies[code]['Category'] = f"{curr_cat}; {r['Category']}"

            print(f"✅ {len(records)} cty (+{new_added} mới | Tích lũy: {len(all_companies):,})")
            sys.stdout.flush()

            # Save checkpoint
            if new_added > 0:
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_companies, f, ensure_ascii=False, indent=2)

                export_and_sync_all_files(list(all_companies.values()))

            time.sleep(0.5)

    # Final export
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, ensure_ascii=False, indent=2)

    total_cnt, has_em = export_and_sync_all_files(list(all_companies.values()))

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH TIẾN TRÌNH CÀO DANH MỤC DỆT MAY LITVA TỪ LITORG.CC!")
    print(f"    - Tổng số doanh nghiệp thu thập : {total_cnt:,}")
    print(f"    - Tệp dữ liệu thô (0RAW)        : {OUTPUT_0RAW_PATH.name}")
    print(f"    - Tệp Cold Mail (2COL)          : {OUTPUT_2COL_PATH.name}")
    print(f"    - Thư mục sao lưu               : csdl_mlt/ & archive/lt_lithuania/")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()

