# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU INFO.LT - NGÀNH GỖ VÀ NỘI THẤT LITVA (LT_WOOD_INLT)
======================================================================
Mục tiêu cào hợp nhất 2 danh mục thành 1 file duy nhất:
1. Baldų gamyba (Sản xuất nội thất): https://www.info.lt/paieska/Bald%C5%B3+gamyba
2. Medienos apdirbimas (Chế biến gỗ & Lâm sản): https://www.info.lt/paieska/Medienos+apdirbimas
-> Hợp nhất khử trùng lặp: ~3,106 doanh nghiệp duy nhất!

Đầu ra chuẩn 17 ký tự (Rule 10):
- LT_WOOD_INLT_0RAW.csv: Dữ liệu bóc tách thô chi tiết 20 cột
- LT_WOOD_INLT_2COL.csv: File chuẩn Cold Mail 20 cột (Đẩy 100% có email lên đầu)
- LT_WOOD_INLT_ONLY_EMAILS_READY.csv: File rút gọn chỉ gồm các cty có Email B2B

Đặc tính kỹ thuật tuân thủ nghiêm ngặt GEMINI.md:
- Bóc tách chi tiết từng thẻ công ty (detail card): Tên pháp lý, Mã DN (Company Code),
  Mã PVM (VAT), Giám đốc/Người đại diện (Direktorius), SĐT có nháy đơn ('+370...),
  Website, Địa chỉ chi tiết, Mã bưu điện, Thành phố, Số nhân viên, Lương bình quân.
- Giải mã thuật toán XOR Obfuscation (data-link-ob) bóc tách email thật 100%.
- Chấm điểm email B2B (score_email_b2b_lt), chỉ giữ lại DUY NHẤT 1 email giá trị nhất.
- Đẩy 100% doanh nghiệp có email lên dòng đầu tiên (dòng 1..N).
- Kiểm tra danh sách đen vĩnh viễn (Scandi Standard Baltics, Biliarta, Daigre).
- Cơ chế Rotating Proxy Pool tiền kiểm định (Pre-validated) tốc độ cao chống Cloudflare 429.
- Checkpoint tự động sau mỗi 10 doanh nghiệp để Resume 100% không mất dữ liệu.
- Đồng bộ tự động sang csdl_mlt/ và archive/lt_lithuania/.
"""

import os
import sys
import re
import csv
import json
import time
import random
import base64
import argparse
import threading
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pandas as pd
import curl_cffi.requests as requests

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV_PATH = ROOT_DIR / "LT_WOOD_INLT_0RAW.csv"
COL2_CSV_PATH = ROOT_DIR / "LT_WOOD_INLT_2COL.csv"
READY_CSV_PATH = ROOT_DIR / "LT_WOOD_INLT_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_infolt_wood.json"
URLS_FILE = ROOT_DIR / "crawlmail" / "urls_infolt_wood.json"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

COLUMNS_RAW = [
    'No.', 'Company_Code', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'VAT_Code', 'Nguoi quan ly', 'Chuc danh',
    'Average_Wage', 'So nhan vien', 'Nam thanh lap', 'InfoLT_URL'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule 12: Danh sách đen vĩnh viễn
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

class PreValidatedProxyPool:
    """Quản lý danh sách proxy ĐÃ ĐƯỢC KIỂM ĐỊNH thành công trên info.lt"""
    def __init__(self):
        self.live_proxies = []
        self.lock = threading.Lock()
        self.is_refreshing = False

    def validate_one(self, p):
        try:
            r = requests.get('https://www.info.lt', proxies={'http': f'http://{p}', 'https': f'http://{p}'}, impersonate='chrome120', timeout=3.5)
            if r.status_code == 200 and len(r.text) > 1000:
                return p
        except Exception:
            pass
        return None

    def refresh(self):
        with self.lock:
            if self.is_refreshing:
                return
            self.is_refreshing = True

        try:
            url = 'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3500&country=all&ssl=yes&anonymity=elite'
            r = requests.get(url, timeout=5)
            raw = [l.strip() for l in r.text.splitlines() if l.strip()]
            candidates = raw[:80]
            print(f"[*] Đang kiểm định {len(candidates)} proxy khả dụng...")
            valid = []
            with ThreadPoolExecutor(max_workers=20) as ex:
                for res in ex.map(self.validate_one, candidates):
                    if res:
                        valid.append(res)
            with self.lock:
                self.live_proxies = valid
            print(f"[*] Đã xác thực thành công {len(valid)} proxy phản hồi nhanh trên info.lt!")
        except Exception as e:
            print(f"[!] Lỗi nạp proxy: {e}")
        finally:
            with self.lock:
                self.is_refreshing = False

    def get_proxy(self):
        with self.lock:
            if len(self.live_proxies) < 4 and not self.is_refreshing:
                threading.Thread(target=self.refresh, daemon=True).start()
            if self.live_proxies:
                return random.choice(self.live_proxies)
        return None

    def remove_proxy(self, p):
        with self.lock:
            if p in self.live_proxies:
                self.live_proxies.remove(p)

PROXY_POOL = PreValidatedProxyPool()

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def decode_info_lt_ob(encoded_str):
    """Giải mã chuỗi Base64 + XOR Obfuscation của info.lt để lấy Email/Phone thật"""
    if not encoded_str:
        return ""
    try:
        raw = base64.b64decode(encoded_str).decode('utf-8').split(',')
        key = int(raw[0])
        decoded = ''.join(chr(int(x) ^ key) for x in raw[1:])
        return decoded.replace('mailto:', '').strip()
    except Exception:
        return ""

def clean_phone_lt(raw_phone):
    """Chuẩn hóa số điện thoại Litva theo chuẩn Rule 2: có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('370'):
        pass
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370'):
        if len(digits) == 11:
            if digits[3] == '6':
                formatted = f"+370 {digits[3:6]} {digits[6:]}"
            elif digits[3] == '5':
                formatted = f"+370 {digits[3]} {digits[4:7]} {digits[7:]}"
            else:
                formatted = f"+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
            return f"'{formatted}"
    return f"'+{digits}"

def parse_lt_address(addr):
    """Tách chi tiết đường phố, mã bưu điện 5 số và thành phố Litva"""
    if not addr:
        return '', '', ''
    s = addr.strip()
    m_zip = re.search(r'\b(\d{5})\b', s)
    zipcode = m_zip.group(1) if m_zip else ''
    city = ''
    street = s
    if zipcode:
        parts = s.split(zipcode)
        street = parts[0].strip().rstrip(',')
        city = parts[1].strip().lstrip(',').strip()
    else:
        parts = s.split(',')
        if len(parts) > 1:
            city = parts[-1].strip()
            street = ', '.join(parts[:-1]).strip()
    return street, zipcode, city

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    return em.lower()

def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email B2B cho thị trường Litva theo Rule 3"""
    e = clean_email(email)
    if not e or '@' not in e:
        return -1
    u, d = e.split('@', 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1
    bad_domains = ['example.com', 'domain.com', 'sentry.io', 'wixpress.com', 'test.com']
    if any(b in d for b in bad_domains):
        return -1
    bad_users = ['youremail', 'your-email', 'someone', 'john.doe', 'no-reply', 'donotreply', 'privacy', 'gdpr']
    if any(b in u for b in bad_users):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 25

    # Ưu tiên số 1: Tuyển dụng / Nhân sự Litva (+50đ)
    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    # Ưu tiên số 2: Giám đốc / Lãnh đạo điều hành (+45đ)
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'prezidentas']:
        score += 45
    # Ưu tiên số 3: Cổng liên hệ chính thức (+40đ)
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
    # Ưu tiên số 4: Kinh doanh / Bán hàng (+35đ)
    elif u in ['komercija', 'pardavimai', 'uzsakymai', 'sales', 'prekyba']:
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    elif u in ['buhalterija', 'saskaitos', 'faktura', 'it', 'servisas']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))

def fetch_page_html(url, retries=6):
    """Tải HTML trang với curl_cffi kết hợp Proxy Pool đã kiểm định chống 429"""
    for attempt in range(retries):
        p = PROXY_POOL.get_proxy()
        if not p:
            time.sleep(0.5)
            continue
        try:
            px_dict = {'http': f'http://{p}', 'https': f'http://{p}'}
            r = requests.get(url, proxies=px_dict, impersonate='chrome120', timeout=5.0)
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
            elif r.status_code == 404:
                return None
            elif r.status_code == 429:
                PROXY_POOL.remove_proxy(p)
        except Exception:
            PROXY_POOL.remove_proxy(p)

    return None

def parse_company_detail(detail_url, category_name=""):
    """Bóc tách thông tin chi tiết đầy đủ của một công ty trên info.lt"""
    html = fetch_page_html(detail_url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    comp_name = h1.text.strip() if h1 else ''
    if not comp_name:
        return None

    raw_addr = ''
    if h1:
        parent_strings = [s.strip() for s in h1.parent.stripped_strings if s.strip() != comp_name]
        if parent_strings:
            raw_addr = parent_strings[0]

    street, zipcode, city = parse_lt_address(raw_addr)

    data = {
        'Company_Code': '',
        'Cong ty': comp_name,
        'Ten phap ly': comp_name,
        'SDT': '',
        'Email': '',
        'Website': '',
        'Dia chi': street or raw_addr,
        'Ma buu dien': zipcode,
        'Khu vuc': '',
        'Thanh pho': city,
        'Tag_Chinh': category_name,
        'All_Tags': '',
        'VAT_Code': '',
        'Nguoi quan ly': '',
        'Chuc danh': '',
        'Average_Wage': '',
        'So nhan vien': '',
        'Nam thanh lap': '',
        'InfoLT_URL': detail_url
    }

    found_emails = []
    found_phones = []

    for em_tag in soup.find_all(attrs={'data-link-ob': True}):
        decoded = decode_info_lt_ob(em_tag['data-link-ob']).replace('mailto:', '').strip().lower()
        if decoded and '@' in decoded:
            found_emails.append(decoded)

    for row in soup.find_all('div', class_='row'):
        c4 = row.find('div', class_='col-xs-4')
        c8 = row.find('div', class_='col-xs-8')
        if not c4 or not c8:
            continue
        label = c4.text.strip().lower()
        val = ' '.join(c8.stripped_strings)

        if 'company code' in label or 'įmonės kodas' in label or 'imones kodas' in label:
            data['Company_Code'] = val
        elif 'vat code' in label or 'pvm' in label:
            data['VAT_Code'] = val
        elif any(k in label for k in ['direktor', 'vadov', 'manager', 'prezident', 'savinink']):
            data['Chuc danh'] = c4.text.strip()
            data['Nguoi quan ly'] = val
        elif 'employees' in label or 'darbuotoj' in label:
            data['So nhan vien'] = val
        elif 'date of registration' in label or 'registravimo data' in label or 'registracijos data' in label:
            data['Nam thanh lap'] = val
        elif 'wage' in label or 'atlyginimas' in label:
            data['Average_Wage'] = val
        elif 'website' in label or 'tinklalapis' in label or 'tinklapis' in label:
            a_tag = c8.find('a', href=True)
            if a_tag and a_tag['href'].startswith('http'):
                data['Website'] = a_tag['href'].strip()
            elif val and not val.lower().startswith('facebook') and not val.lower().startswith('puslapis'):
                data['Website'] = val if val.startswith('http') else f"https://{val}"
        elif 'phone' in label or 'telefonas' in label:
            if any(c.isdigit() for c in val):
                m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|\(0\s*\d+\)\s*\d+|0\s*\d+[\d\s]*|8\s*\d+[\d\s]*)', val)
                if m_ph:
                    found_phones.append(m_ph.group(1).strip())

    if not found_phones:
        for t_node in soup.find_all(string=re.compile(r'\(\+370\)|\+370|\(0\s*\d+\)')):
            m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|\(0\s*\d+\)\s*\d+[\d\s]*)', str(t_node))
            if m_ph:
                found_phones.append(m_ph.group(1).strip())

    data['SDT'] = clean_phone_lt(found_phones[0]) if found_phones else ''

    domain = urllib.parse.urlparse(data['Website']).netloc if data['Website'] else ''
    data['Email'] = select_best_email(found_emails, domain)

    cats = [a.text.strip() for a in soup.find_all('a', href=lambda h: h and '/rubrika/' in h) if a.text.strip() not in ['Įmonių sąrašas', 'List of companies']]
    data['All_Tags'] = ' | '.join(list(dict.fromkeys(cats)))

    return data

def save_wood_files(cache_data):
    """
    Lưu dữ liệu tăng dần và phân loại:
    - 100% doanh nghiệp có Email được đẩy lên đầu (Dòng 1..N)
    - Tạo đồng thời 3 file: 0RAW, 2COL và ONLY_EMAILS_READY
    - Đồng bộ tự động sang csdl_mlt/ và archive/lt_lithuania/
    """
    all_records = list(cache_data.values())

    valid_records = [r for r in all_records if not is_blacklisted_company(r.get('Cong ty', ''))]

    with_email = [r for r in valid_records if r.get('Email') and '@' in r.get('Email')]
    without_email = [r for r in valid_records if not r.get('Email') or '@' not in r.get('Email')]

    sorted_raw = with_email + without_email
    for i, r in enumerate(sorted_raw, start=1):
        r['No.'] = str(i)

    # 1. Ghi file RAW 20 cột (UTF-8 with BOM)
    RAW_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted_raw, columns=COLUMNS_RAW).to_csv(RAW_CSV_PATH, index=False, encoding='utf-8-sig')

    # 2. Ghi file Cold Mail 20 cột (UTF-8 with BOM)
    col20_rows = []
    for r in sorted_raw:
        c_name = r.get('Cong ty', '')
        c_role = r.get('Chuc danh', '') or 'Direktorius / Vadovas'
        c_leader = r.get('Nguoi quan ly', '')
        c_phone = r.get('SDT', '')
        c_email = r.get('Email', '')
        c_web = r.get('Website', '')
        c_addr = r.get('Dia chi', '')
        c_city = r.get('Thanh pho', '')
        full_addr = f"{c_addr}, {c_city}".strip(', ') if c_city and c_city not in c_addr else c_addr

        row_20 = {
            'No.': r.get('No.', ''),
            'Công ty': c_name,
            'Chức danh': c_role,
            'Người liên hệ': c_leader,
            'SĐT': c_phone,
            'Liên Hệ': c_web,
            'Email': c_email,
            'Liên Hệ mail': f"mailto:{c_email}" if c_email else '',
            'Địa chỉ': full_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if c_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Gỗ & Nội thất')
        }
        col20_rows.append(row_20)

    COL2_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_col2 = pd.DataFrame(col20_rows, columns=COLUMNS_20)
    df_col2.to_csv(COL2_CSV_PATH, index=False, encoding='utf-8-sig')

    # 3. Ghi file ONLY_EMAILS_READY (Chỉ các cty có Email)
    df_ready = df_col2[df_col2['Email'].str.contains('@', na=False)].copy()
    for i, _ in enumerate(df_ready.index, start=1):
        df_ready.iloc[i-1, df_ready.columns.get_loc('No.')] = str(i)
    df_ready.to_csv(READY_CSV_PATH, index=False, encoding='utf-8-sig')

    # 4. Đồng bộ vào csdl_mlt và archive/lt_lithuania
    CSDL_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    df_col2.to_csv(CSDL_DIR / COL2_CSV_PATH.name, index=False, encoding='utf-8-sig')
    df_col2.to_csv(ARCHIVE_DIR / COL2_CSV_PATH.name, index=False, encoding='utf-8-sig')
    pd.DataFrame(sorted_raw, columns=COLUMNS_RAW).to_csv(ARCHIVE_DIR / RAW_CSV_PATH.name, index=False, encoding='utf-8-sig')
    df_ready.to_csv(ARCHIVE_DIR / READY_CSV_PATH.name, index=False, encoding='utf-8-sig')

    return len(with_email), len(valid_records)

def main():
    parser = argparse.ArgumentParser(description="Scraper info.lt Wood & Furniture Lithuania (LT_WOOD_INLT)")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty để test nhanh (0 = toàn bộ)")
    parser.add_argument('--workers', type=int, default=8, help="Số luồng cào song song (mặc định 8)")
    args = parser.parse_args()

    print("=" * 80)
    print(" HỆ THỐNG CÀO INFO.LT - NGÀNH GỖ VÀ NỘI THẤT LITVA (LT_WOOD_INLT)")
    print(f" Output RAW : {RAW_CSV_PATH.name}")
    print(f" Output Cold: {COL2_CSV_PATH.name}")
    print(f" Output Read: {READY_CSV_PATH.name}")
    print(f" Checkpoint : {CACHE_FILE.name}")
    print(f" Workers    : {args.workers}")
    print("=" * 80)

    # 1. Nạp cache checkpoint JSON
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp checkpoint cache: {len(cache):,} công ty đã cào từ trước.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # 2. Khởi tạo Proxy Pool đã tiền kiểm định
    PROXY_POOL.refresh()

    # 3. Lấy danh sách URL công ty
    if URLS_FILE.exists():
        with open(URLS_FILE, 'r', encoding='utf-8') as f:
            all_urls = json.load(f)
        print(f"[*] Nạp sẵn {len(all_urls):,} link công ty từ {URLS_FILE.name}.")
    else:
        print("[!] Không tìm thấy urls_infolt_wood.json, thoát.")
        return

    urls_to_scrape = all_urls
    if args.limit > 0:
        urls_to_scrape = urls_to_scrape[:args.limit]
        print(f"[*] Giới hạn kiểm tra: {len(urls_to_scrape)} công ty.")

    # 4. Lọc danh sách cần cào (chưa có trong cache)
    pending_urls = [u for u in urls_to_scrape if u not in cache]
    print(f"[*] Đã có sẵn trong cache: {len(urls_to_scrape) - len(pending_urls):,} công ty.")
    print(f"[*] Cần cào mới chi tiết  : {len(pending_urls):,} công ty.")

    if cache:
        cur_em, cur_tot = save_wood_files(cache)
        print(f"[*] Đã đồng bộ CSV từ cache: {cur_tot:,} công ty ({cur_em:,} có email).")

    if not pending_urls:
        print("\n[*] Toàn bộ doanh nghiệp đã được cào và lưu trữ đầy đủ trong cache!")
    else:
        print(f"\n[*] Bắt đầu cào song song với {args.workers} luồng (kèm Pre-Validated Proxy Pool)...")
        t_start = time.time()
        completed_count = 0
        batch_count = 0

        def scrape_single(u):
            return u, parse_company_detail(u, "Gỗ & Nội thất")

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_url = {executor.submit(scrape_single, u): u for u in pending_urls}
            for future in as_completed(future_to_url):
                u, c_data = future.result()
                completed_count += 1
                batch_count += 1

                if c_data:
                    cache[u] = c_data
                    em_log = f"Mail: {c_data['Email']}" if c_data['Email'] else "Chưa có mail"
                    ph_log = f"SĐT: {c_data['SDT']}" if c_data['SDT'] else "Chưa có SĐT"
                    mgr_log = f"GĐ: {c_data['Nguoi quan ly'][:18]}" if c_data['Nguoi quan ly'] else "GĐ: -"
                    print(f"[{completed_count:04d}/{len(pending_urls)}] {c_data['Cong ty'][:26]:<26} | {em_log:<30} | {ph_log:<18} | {mgr_log}")
                else:
                    print(f"[{completed_count:04d}/{len(pending_urls)}] Không lấy được dữ liệu: {u}")

                if batch_count >= 10:
                    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(cache, f, ensure_ascii=False, indent=2)
                    cur_em, cur_tot = save_wood_files(cache)
                    batch_count = 0
                    print(f"  >>> [AUTO-SAVE] Checkpoint: {cur_tot:,} công ty ({cur_em:,} có Email B2B).")

        t_end = time.time()
        print(f"\n[*] Thời gian cào hoàn tất: {t_end - t_start:.2f} giây.")

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    final_em, final_tot = save_wood_files(cache)

    print("\n" + "=" * 80)
    print(" BÁO CÁO KẾT QUẢ CÀO INFO.LT - GỖ VÀ NỘI THẤT LITVA (LT_WOOD_INLT)")
    print(f" - Tổng số doanh nghiệp hợp nhất        : {final_tot:,}")
    print(f" - Doanh nghiệp CÓ EMAIL B2B (Dòng 1..N): {final_em:,} ({(final_em/final_tot*100) if final_tot else 0:.1f}%)")
    print(f" - Doanh nghiệp chưa có email           : {final_tot - final_em:,}")
    print(f" - File RAW 20 cột đã xuất              : {RAW_CSV_PATH.name}")
    print(f" - File Cold Mail 20 cột (Đẩy mail đầu) : {COL2_CSV_PATH.name}")
    print(f" - File Ready to Send (Chỉ có Email)    : {READY_CSV_PATH.name}")
    print(f" - Cache Checkpoint phục hồi 100%       : {CACHE_FILE.name}")
    print(f" - Đồng bộ csdl_mlt & archive           : THÀNH CÔNG")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()
