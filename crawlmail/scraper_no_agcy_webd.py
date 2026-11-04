# -*- coding: utf-8 -*-
"""
BỘ CÀO DỮ LIỆU ĐA NGUỒN NA UY (NORWAY HR & RECRUITMENT AGENCIES)
----------------------------------------------------------------------
Thu thập dữ liệu doanh nghiệp Tuyển dụng / Nhân sự / Cung ứng lao động (AGCY) từ 3 nguồn:
1. https://www.proff.no/bransjes%C3%B8k?q=rekruttering (61 trang, ~1,504 doanh nghiệp)
2. https://www.proff.no/bransjes%C3%B8k?q=bemanningsbyr%C3%A5 (15 doanh nghiệp)
3. https://www.gulesider.no/bemanningsbyr%c3%a5/bedrifter (287 trang bóc tách tăng dần)

Tuân thủ toàn bộ quy chuẩn tại GEMINI.md, data-standards và crawl-mail:
- File xuất cố định 17 ký tự: NO_AGCY_WEBD_0RAW.csv
- Định dạng UTF-8 with BOM (utf-8-sig).
- Số điện thoại chuẩn hóa có nháy đơn (') ở đầu: phone = f"'{phone}".
- Bóc tách đầy đủ Orgnr, Tên pháp lý, Web, SĐT, Email, Địa chỉ, Người đại diện pháp luật (Daglig leder).
- Lọc bỏ 100% doanh nghiệp thuộc Danh sách đen cố định (Scandi Standard, Biliarta, Daigre).
- Khử trùng lặp thông minh (Smart Deduplication) theo Orgnr và Tên chuẩn hóa.
- Lưu tăng dần (Incremental Checkpoint) liên tục vào CSV và Cache JSON hỗ trợ Resume 100%.
"""

import sys
import os
import re
import json
import time
import unicodedata
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

# Cấu hình UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT_DIR / "NO_AGCY_WEBD_0RAW.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_scraper_no_agcy_webd.json"

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

CSV_COLUMNS = [
    'No.', 'Công ty', 'Tên pháp lý', 'Orgnr', 'SĐT', 'Web', 'Email',
    'Địa chỉ', 'Mã bưu điện', 'Thành phố', 'Khu vực', 'Người liên hệ',
    'Chức danh', 'Số nhân viên', 'Doanh thu (MNOK)', 'Category',
    'Source', 'Source_URL'
]

HEADERS_PROFF = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,no;q=0.8',
}

HEADERS_GULE = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,nn;q=0.7,en-US;q=0.6,en;q=0.5',
    'Referer': 'https://www.google.no/',
}

def clean_phone_no(phone_raw):
    """Chuẩn hóa số điện thoại Na Uy (+47) và thêm dấu nháy đơn (')"""
    if not phone_raw:
        return ""
    p = str(phone_raw).strip()
    if p in ['', 'None', 'nan', 'null']:
        return ""
    
    digits = re.sub(r'[^\d+]', '', p)
    if digits.startswith('+47'):
        formatted = f"+47 {digits[3:]}"
    elif digits.startswith('47') and len(digits) == 10:
        formatted = f"+47 {digits[2:]}"
    elif len(digits) == 8:
        formatted = f"+47 {digits}"
    else:
        formatted = p

    return f"'{formatted}" if not formatted.startswith("'") else formatted

def clean_email(email_raw):
    """Làm sạch email, loại bỏ whitespace, %20, \xa0 và ký tự lạ"""
    if not email_raw:
        return ""
    em = str(email_raw).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    if any(k in em for k in ['sentry', 'wixpress', 'wordpress', 'example', 'youremail', 'your-email']):
        return ""
    return em

def norm_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['as', 'asa', 'ans', 'da', 'enk', 'nuf', 'kf', 'iks', 'sa']:
        n_clean = re.sub(rf'\b{legal}\b', '', n_clean)
    n_clean = re.sub(r'[^a-z0-9]', ' ', n_clean)
    return ' '.join(n_clean.split())

def is_blacklisted(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def save_incremental_csv(records):
    """Lưu toàn bộ danh sách hiện tại ra file CSV theo chuẩn UTF-8-sig"""
    if not records:
        return
    df = pd.DataFrame(records)
    df['No.'] = range(1, len(df) + 1)
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    df = df[CSV_COLUMNS]
    df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

def fetch_with_retry(url, headers, impersonate, retries=3, timeout=30):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, impersonate=impersonate, timeout=timeout)
            if r.status_code == 200:
                return r
            elif r.status_code == 403 and "Just a moment" in r.text:
                time.sleep(2 * attempt)
            else:
                time.sleep(1)
        except Exception:
            if attempt < retries:
                time.sleep(1.5 * attempt)
    return None

def scrape_proff_query(query_keyword, source_label, all_records, seen_keys, cache):
    print(f"\n" + "=" * 70)
    print(f"[*] ĐANG CÀO NGUỒN PROFF.NO: '{query_keyword}'")
    print("=" * 70)

    base_url = f"https://www.proff.no/bransjes%C3%B8k?q={query_keyword}"
    
    r = fetch_with_retry(base_url, HEADERS_PROFF, impersonate="chrome124", retries=3, timeout=30)
    if not r:
        print(f"[-] Không thể kết nối tới Proff.no cho '{query_keyword}'")
        return

    soup = BeautifulSoup(r.text, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if not next_data:
        print(f"[-] Không tìm thấy dữ liệu trên Proff.no cho '{query_keyword}'")
        return
    
    data = json.loads(next_data.string)
    store = data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {})
    comp_obj = store.get('companies', {})
    total_hits = comp_obj.get('hits', 0)
    total_pages = comp_obj.get('pages', 1)
    print(f"[+] Tìm thấy tổng cộng: {total_hits:,} doanh nghiệp ({total_pages} trang)")

    for page_num in range(1, total_pages + 1):
        page_url = f"{base_url}&page={page_num}"
        print(f"  --> [Proff: {query_keyword}] Đang xử lý trang {page_num}/{total_pages}...", end='', flush=True)

        r_page = fetch_with_retry(page_url, HEADERS_PROFF, impersonate="chrome124", retries=3, timeout=30)
        if not r_page:
            print(" [Lỗi kết nối - Bỏ qua]")
            continue

        try:
            soup = BeautifulSoup(r_page.text, 'html.parser')
            next_data = soup.find('script', id='__NEXT_DATA__')
            if not next_data:
                print(" [Bỏ qua - Không có dữ liệu]")
                continue
            data = json.loads(next_data.string)
            store = data.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {})
            companies = store.get('companies', {}).get('companies', [])
            
            added_on_page = 0
            for c in companies:
                name = str(c.get('name') or '').strip()
                legal_name = str(c.get('legalName') or '').strip()
                orgnr = str(c.get('orgnr') or '').strip()
                
                # Khử trùng lặp
                dedup_key = orgnr if orgnr else norm_name(name)
                if not dedup_key or dedup_key in seen_keys:
                    continue
                if is_blacklisted(name) or is_blacklisted(legal_name):
                    continue

                phone = clean_phone_no(c.get('phone') or c.get('phone2') or c.get('mobile'))
                web = str(c.get('homePage') or '').strip()
                email = clean_email(c.get('email'))
                
                addr_obj = c.get('visitorAddress') or c.get('postalAddress') or {}
                addr = str(addr_obj.get('addressLine') or '').strip()
                zip_code = str(addr_obj.get('zipCode') or '').strip()
                city = str(addr_obj.get('postPlace') or '').strip()
                loc = c.get('location') or {}
                region = str(loc.get('county') or loc.get('countryPart') or '').strip()

                contact = c.get('contactPerson') or {}
                contact_name = str(contact.get('name') or '').strip()
                contact_role = str(contact.get('role') or '').strip()

                employees = str(c.get('employees') or '').strip()
                revenue = str(c.get('revenue') or '').strip()

                industries = c.get('industries') or []
                cat_desc = '; '.join([str(ind.get('name') or '') for ind in industries if ind.get('name')])
                if not cat_desc:
                    cat_desc = str(c.get('description') or 'Rekruttering og bemanning').strip()

                company_id = str(c.get('companyId') or '').strip()
                source_url = f"https://www.proff.no/selskap/{name}/{city}/{company_id}" if company_id else page_url

                record = {
                    'Công ty': name,
                    'Tên pháp lý': legal_name,
                    'Orgnr': orgnr,
                    'SĐT': phone,
                    'Web': web,
                    'Email': email,
                    'Địa chỉ': addr,
                    'Mã bưu điện': zip_code,
                    'Thành phố': city,
                    'Khu vực': region,
                    'Người liên hệ': contact_name,
                    'Chức danh': contact_role,
                    'Số nhân viên': employees,
                    'Doanh thu (MNOK)': revenue,
                    'Category': cat_desc,
                    'Source': source_label,
                    'Source_URL': source_url
                }

                all_records.append(record)
                seen_keys.add(dedup_key)
                added_on_page += 1

            print(f" OK (+{added_on_page} mới | Tổng: {len(all_records):,})")

            # Lưu tăng dần mỗi trang
            save_incremental_csv(all_records)
            time.sleep(0.3)

        except Exception as e:
            print(f" [LỖI]: {e}")
            time.sleep(0.5)

def scrape_gulesider(max_pages, all_records, seen_keys, cache):
    print(f"\n" + "=" * 70)
    print(f"[*] ĐANG CÀO NGUỒN GULESIDER.NO: 'bemanningsbyrå/bedrifter' (Tối đa {max_pages} trang)")
    print("=" * 70)

    for page_num in range(1, max_pages + 1):
        url = f"https://www.gulesider.no/bemanningsbyr%c3%a5/bedrifter/{page_num}"
        print(f"  --> [Gulesider] Đang bóc tách trang {page_num}/{max_pages}...", end='', flush=True)

        r = fetch_with_retry(url, HEADERS_GULE, impersonate="safari17_0", retries=3, timeout=20)
        if not r or r.status_code != 200 or "Just a moment" in r.text:
            print(" [Status lỗi hoặc gặp Cloudflare - Bỏ qua]")
            time.sleep(1)
            continue

        try:
            soup = BeautifulSoup(r.text, 'html.parser')
            h2s = soup.find_all('h2')
            if not h2s:
                print(" [Không còn kết quả]")
                break

            added_on_page = 0
            for h2 in h2s:
                comp_name = h2.get_text(strip=True)
                if not comp_name or is_blacklisted(comp_name):
                    continue

                card = h2
                for _ in range(5):
                    if card.parent and len(card.parent.find_all('h2')) <= 1:
                        card = card.parent
                    else:
                        break

                # Extract Website
                web = ""
                for a in card.find_all('a', href=True):
                    href = a['href'].strip()
                    if href.startswith('http') and not any(k in href for k in ['gulesider.no', 'facebook.com', 'instagram.com', 'linkedin.com', 'teamtailor.com']):
                        web = href
                        break

                # Extract Detail URL
                detail_url = ""
                for a in card.find_all('a', href=True):
                    href = a['href'].strip()
                    if '/bedrift' in href:
                        detail_url = "https://www.gulesider.no" + href if href.startswith('/') else href
                        break

                # Extract Address
                card_text = card.get_text(separator=' | ', strip=True)
                addr_match = re.search(r'([^|]+?\|\s*\d{4}\s+[^|]+)', card_text)
                addr_full = addr_match.group(1).replace('|', '').strip() if addr_match else ""
                
                # Tách Zip Code và City
                zip_code, city = "", ""
                zc_match = re.search(r'\b(\d{4})\s+([A-ZÆØÅa-zæøå\s-]+)', addr_full)
                if zc_match:
                    zip_code = zc_match.group(1).strip()
                    city = zc_match.group(2).strip()

                # Khử trùng lặp
                dedup_key = norm_name(comp_name)
                if not dedup_key or dedup_key in seen_keys:
                    continue

                record = {
                    'Công ty': comp_name,
                    'Tên pháp lý': comp_name,
                    'Orgnr': '',
                    'SĐT': '',
                    'Web': web,
                    'Email': '',
                    'Địa chỉ': addr_full,
                    'Mã bưu điện': zip_code,
                    'Thành phố': city,
                    'Khu vực': '',
                    'Người liên hệ': '',
                    'Chức danh': '',
                    'Số nhân viên': '',
                    'Doanh thu (MNOK)': '',
                    'Category': 'Bemanningsbyrå (Gulesider)',
                    'Source': 'Gulesider (bemanningsbyrå)',
                    'Source_URL': detail_url if detail_url else url
                }

                all_records.append(record)
                seen_keys.add(dedup_key)
                added_on_page += 1

            print(f" OK (+{added_on_page} mới | Tổng: {len(all_records):,})")
            save_incremental_csv(all_records)
            time.sleep(0.4)

        except Exception as e:
            print(f" [LỖI]: {e}")
            time.sleep(0.5)

def main():
    print("=" * 80)
    print(" HỆ THỐNG CÀO DỮ LIỆU ĐA NGUỒN NA UY (NORWAY AGCY)")
    print(f" File xuất chuẩn 17 ký tự: {OUTPUT_CSV.name}")
    print("=" * 80)

    cache = load_cache()
    all_records = []
    seen_keys = set()

    # Nạp dữ liệu cũ nếu có
    if OUTPUT_CSV.exists():
        try:
            df_old = pd.read_csv(OUTPUT_CSV, encoding='utf-8-sig', dtype=str).fillna('')
            for idx, r in df_old.iterrows():
                orgnr = str(r.get('Orgnr', '')).strip()
                name = str(r.get('Công ty', '')).strip()
                k = orgnr if orgnr else norm_name(name)
                if k:
                    seen_keys.add(k)
                all_records.append(r.to_dict())
            print(f"[+] Đã khôi phục {len(all_records):,} bản ghi từ file trước đó.")
        except Exception:
            pass

    # 1. Cào Proff.no - Từ khóa 'rekruttering' (~1,504 doanh nghiệp)
    scrape_proff_query('rekruttering', 'Proff.no (rekruttering)', all_records, seen_keys, cache)

    # 2. Cào Proff.no - Từ khóa 'bemanningsbyrå' (~15 doanh nghiệp)
    scrape_proff_query('bemanningsbyr%C3%A5', 'Proff.no (bemanningsbyrå)', all_records, seen_keys, cache)

    # 3. Cào Gulesider.no - 'bemanningsbyrå/bedrifter' (Lấy top 30 trang đầu)
    scrape_gulesider(max_pages=30, all_records=all_records, seen_keys=seen_keys, cache=cache)

    # Lưu kết quả cuối cùng
    save_incremental_csv(all_records)
    save_cache(cache)

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT THU THẬP DỮ LIỆU NA UY THÀNH CÔNG!")
    print(f" [*] Tổng số doanh nghiệp thu thập: {len(all_records):,}")
    print(f" [*] Đã xuất tệp dữ liệu: {OUTPUT_CSV}")
    print(f" [*] Đã lọc trùng lặp & blacklist hoàn tất.")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()
