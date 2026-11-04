# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU AGENCY NA UY (PROFF DIRECT TURBO 10 LUỒNG)
----------------------------------------------------------------------
Tối ưu hóa tốc độ tối đa theo cấu trúc Proff.no:
1. BÓC TÁCH TRỰC TIẾP HỒ SƠ PROFF.NO (SIÊU TỐC ~0.3s/công ty):
   - Truy vấn trực tiếp `https://www.proff.no/selskap/-/-/-/{orgnr}`
   - Bóc tách toàn bộ dữ liệu có sẵn ngay trên Proff:
     * Email doanh nghiệp (c.get('email') -> ví dụ: hei@humano.no)
     * Email nhân sự cấp cao / Partners (c.get('contactPersons') -> ví dụ: vivian@humano.no, sindre@humano.no)
     * Website chính thức (c.get('homePage') -> ví dụ: https://humano.no/)
     * Số điện thoại (c.get('phone') -> ví dụ: 944 23 194)
     * Người đại diện pháp luật (Daglig leder / CEO / Partner)
     * Địa chỉ trụ sở (visitorAddress / postalAddress)
2. TÌM KIẾM ORGNR NHANH TRÊN PROFF CHO CÁC DOANH NGHIỆP TỪ GULESIDER:
   - Tra cứu trực tiếp trên Proff search Store để lấy Orgnr và trang hồ sơ.
3. QUÉT NHANH TRANG CHỦ WEBSITE (NẾU PROFF CÓ WEB NHƯNG CHƯA CÓ EMAIL):
   - Chỉ quét nhanh trang chủ và /kontakt với timeout ngắn (2.5s), không treo tiến trình.
4. LOẠI BỎ HOÀN TOÀN DUCKDUCKGO ĐỂ TRÁNH NGHẼN MẠNG VÀ CHẬM TIẾN ĐỘ.
5. LƯU TĂNG DẦN LIÊN TỤC VÀO NO_AGCY_WEBD_1ENR.CSV VÀ NO_AGCY_WEBD_2COL.CSV:
   - Đẩy 100% doanh nghiệp có Email lên đầu tệp Cold Mail 20 cột chuẩn UTF-8-sig.
"""

import sys
import os
import re
import json
import time
import threading
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "NO_AGCY_WEBD_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "NO_AGCY_WEBD_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "NO_AGCY_WEBD_2COL.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_no_agcy_webd.json"

MAX_WORKERS = 10

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'nb-NO,no;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

lock = threading.RLock()

def clean_phone_no(phone_raw):
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
    if not email_raw:
        return ""
    em = str(email_raw).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    
    if any(em.startswith(b) for b in bad_prefixes):
        return ""
    if any(em.endswith(b) for b in bad_domains):
        return ""
    if any(k in em for k in ['sentry', 'wix', 'wordpress', 'no-reply', 'donotreply', 'privacy', 'gdpr']):
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

def score_email_no(email, domain):
    score = 0
    em = email.lower()
    prefix = em.split('@')[0]
    em_dom = em.split('@')[1] if '@' in em else ''
    
    if domain and domain.lower() in em_dom:
        score += 50
    if em_dom.endswith('.no'):
        score += 25
        
    if any(k in prefix for k in ['rekruttering', 'bemanning', 'karriere', 'stilling', 'hr', 'jobb', 'recruitment', 'praca', 'nabor']):
        score += 50
    elif any(k in prefix for k in ['dagligleder', 'leder', 'ceo', 'director', 'manager', 'partner', 'sjef']):
        score += 45
    elif any(k in prefix for k in ['post', 'kontakt', 'firmapost', 'office', 'info', 'support', 'hei', 'velkommen']):
        score += 40
    elif '.' in prefix or '_' in prefix:
        score += 25
    elif any(k in em_dom for k in ['gmail.com', 'online.no']):
        score += 10
        
    return score

def fetch_proff_detail(orgnr):
    """Truy vấn trực tiếp trang hồ sơ Proff.no qua Orgnr (Chính xác 100%)"""
    digits = re.sub(r'\D', '', str(orgnr))
    if not digits:
        return None
    url = f"https://www.proff.no/selskap/-/-/-/{digits}"
    try:
        r = requests.get(url, headers=HEADERS, impersonate="chrome124", allow_redirects=True, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            s = soup.find('script', id='__NEXT_DATA__')
            if s:
                d = json.loads(s.string)
                return d.get('props', {}).get('pageProps', {}).get('company', {})
    except Exception:
        pass
    return None

def search_proff_orgnr(name, city=''):
    """Tìm nhanh Orgnr trên Proff.no nếu dòng dữ liệu ban đầu thiếu Orgnr"""
    q = f"{name} {city}".strip()
    url = f"https://www.proff.no/bransjes%C3%B8k?q={urllib.parse.quote(q)}"
    try:
        r = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            s = soup.find('script', id='__NEXT_DATA__')
            if s:
                d = json.loads(s.string)
                comps = d.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {}).get('companies', {}).get('companies', [])
                if comps:
                    return str(comps[0].get('orgnr') or '').strip()
    except Exception:
        pass
    return None

def quick_crawl_site_emails(website_url):
    """Quét nhanh trang chủ và trang /kontakt của Website với timeout 2.5s"""
    if not website_url:
        return ""
    if not website_url.startswith('http'):
        website_url = 'https://' + website_url
        
    parsed = urllib.parse.urlparse(website_url)
    base_domain = parsed.netloc.lower()
    if base_domain.startswith('www.'):
        base_domain = base_domain[4:]
        
    found_emails = set()
    
    for sp in ['', '/kontakt', '/kontakt-oss']:
        page_url = f"{parsed.scheme}://{parsed.netloc}{sp}"
        try:
            r = requests.get(page_url, headers=HEADERS, impersonate="chrome124", timeout=2.5)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    if a['href'].startswith('mailto:'):
                        raw_em = a['href'].replace('mailto:', '').split('?')[0].strip()
                        c_em = clean_email(raw_em)
                        if c_em:
                            found_emails.add(c_em)
                            
                matches = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.text)
                for m in matches:
                    c_em = clean_email(m)
                    if c_em:
                        found_emails.add(c_em)
        except Exception:
            pass
            
        if found_emails:
            break
            
    if not found_emails:
        return ""
        
    scored = sorted([(em, score_email_no(em, base_domain)) for em in found_emails], key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored else ""

def save_outputs(df_full):
    """Lưu đồng thời file đầy đủ và file Cold Mail 20 cột (Email trên đầu)"""
    with lock:
        df_full.to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')

        has_em_rows = []
        no_em_rows = []

        for idx, r in df_full.iterrows():
            comp = r.get('Công ty', '').strip()
            phone = clean_phone_no(r.get('SĐT', ''))
            em = clean_email(r.get('Email', ''))
            web = r.get('Web', '').strip()
            addr = r.get('Địa chỉ', '').strip()
            city = r.get('Thành phố', '').strip()
            leader = r.get('Người liên hệ', '').strip()
            role = r.get('Chức danh', '').strip()
            cat = r.get('Category', '').strip()

            full_addr = f"{addr}, {city}".strip(', ') if city and city not in addr else addr

            row_dict = {
                'No.': '',
                'Công ty': comp,
                'Chức danh': role,
                'Người liên hệ': leader,
                'SĐT': phone,
                'Liên Hệ': web,
                'Email': em,
                'Liên Hệ mail': '',
                'Địa chỉ': full_addr,
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': 'Da_Gui_Truoc' if em else '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': '',
                'Lần Follow-up': '0' if em else '',
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': cat if cat else 'Rekruttering og bemanning'
            }

            if em:
                has_em_rows.append(row_dict)
            else:
                no_em_rows.append(row_dict)

        all_sorted = has_em_rows + no_em_rows
        for idx_num, item in enumerate(all_sorted, 1):
            item['No.'] = str(idx_num)

        df_2col = pd.DataFrame(all_sorted, columns=COLUMNS_20)
        df_2col.to_csv(OUTPUT_2COL_CSV, index=False, encoding='utf-8-sig')

def process_single_company(row_info, cache, stats, df_full, total):
    idx, comp, orgnr, city, curr_web, curr_em, curr_phone, curr_leader, curr_role = row_info

    if is_blacklisted(comp):
        return

    cache_key = orgnr if orgnr else norm_name(comp)

    # 1. Kiểm tra cache
    with lock:
        if cache_key in cache:
            c_data = cache[cache_key]
            if c_data.get('Email'):
                df_full.at[idx, 'Email'] = c_data['Email']
                if c_data.get('Web') and not curr_web:
                    df_full.at[idx, 'Web'] = c_data['Web']
                if c_data.get('SĐT') and not curr_phone:
                    df_full.at[idx, 'SĐT'] = c_data['SĐT']
                if c_data.get('Leader') and not curr_leader:
                    df_full.at[idx, 'Người liên hệ'] = c_data['Leader']
                if c_data.get('Role') and not curr_role:
                    df_full.at[idx, 'Chức danh'] = c_data['Role']

                stats['processed'] += 1
                print(f"[{stats['processed']:04d}/{total}] {comp[:28]:<28} | Cache Hit: {c_data['Email']}", flush=True)
                return

    # 2. BƯỚC 1: TRA CỨU HỒ SƠ PROFF.NO TRỰC TIẾP
    proff_company = None
    if orgnr:
        proff_company = fetch_proff_detail(orgnr)
    else:
        found_orgnr = search_proff_orgnr(comp, city)
        if found_orgnr:
            orgnr = found_orgnr
            with lock:
                df_full.at[idx, 'Orgnr'] = orgnr
            proff_company = fetch_proff_detail(orgnr)

    # Bóc tách thông tin từ hồ sơ Proff
    if proff_company:
        p_email = clean_email(proff_company.get('email'))
        
        # Nếu chưa có email công ty, bóc tách email từ danh sách contactPersons (Key Persons)
        if not p_email:
            cp_list = proff_company.get('contactPersons') or []
            cp_emails = [clean_email(p.get('email')) for p in cp_list if clean_email(p.get('email'))]
            if cp_emails:
                p_email = cp_emails[0]

        p_web = str(proff_company.get('homePage') or '').strip()
        p_phone = proff_company.get('phone') or proff_company.get('legalPhone') or proff_company.get('phone2') or proff_company.get('mobile')
        
        contact_obj = proff_company.get('contactPerson') or {}
        if isinstance(contact_obj, dict):
            p_leader = str(contact_obj.get('name') or '').strip()
            p_role = str(contact_obj.get('role') or '').strip()
        else:
            p_leader = ''
            p_role = ''

        addr_obj = proff_company.get('visitorAddress') or proff_company.get('postalAddress') or {}
        p_addr = str(addr_obj.get('addressLine') or '').strip() if isinstance(addr_obj, dict) else ''

        if p_email and not curr_em:
            curr_em = p_email
            with lock:
                stats['proff_emails'] += 1

        if p_web and not curr_web:
            curr_web = p_web
            with lock:
                stats['proff_webs'] += 1

        if p_phone and not curr_phone:
            curr_phone = clean_phone_no(p_phone)
            with lock:
                df_full.at[idx, 'SĐT'] = curr_phone

        if p_leader and not curr_leader:
            curr_leader = p_leader
            curr_role = p_role if p_role else 'Daglig leder'
            with lock:
                df_full.at[idx, 'Người liên hệ'] = curr_leader
                df_full.at[idx, 'Chức danh'] = curr_role

        if p_addr and not df_full.at[idx, 'Địa chỉ']:
            with lock:
                df_full.at[idx, 'Địa chỉ'] = p_addr

    # 3. BƯỚC 2: QUÉT NHANH WEBSITE (NẾU ĐÃ CÓ WEB NHƯNG PROFF CHƯA CÓ EMAIL)
    if curr_web and not curr_em:
        found_em = quick_crawl_site_emails(curr_web)
        if found_em:
            curr_em = found_em
            with lock:
                stats['site_emails'] += 1

    # Cập nhật kết quả an toàn trong Lock
    with lock:
        df_full.at[idx, 'Web'] = curr_web
        df_full.at[idx, 'Email'] = curr_em
        cache[cache_key] = {
            'Company': comp,
            'Orgnr': orgnr,
            'Web': curr_web,
            'Email': curr_em,
            'SĐT': curr_phone,
            'Leader': curr_leader,
            'Role': curr_role
        }
        stats['processed'] += 1
        p_count = stats['processed']
        
        status_src = 'Proff' if (proff_company and curr_em) else ('Web' if curr_em else '-')
        status_str = f"Web: {'✓' if curr_web else '✗'} | Email: {curr_em if curr_em else '✗'} ({status_src})"
        print(f"[{p_count:04d}/{total}] {comp[:28]:<28} | {status_str}", flush=True)

        # Lưu tăng dần mỗi 10 công ty
        if p_count % 10 == 0:
            save_outputs(df_full)
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

def main():
    print("=" * 80)
    print(f" HỆ THỐNG LÀM GIÀU DỮ LIỆU AGENCY NA UY (PROFF DIRECT TURBO {MAX_WORKERS} WORKERS)")
    print(f" Bóc tách trực tiếp Proff.no Detail + Quick Site Check")
    print(f" Input : {INPUT_CSV.name}")
    print(f" Output 1ENR: {OUTPUT_1ENR_CSV.name}")
    print(f" Output 2COL: {OUTPUT_2COL_CSV.name} (Cold Mail Ready - 100% Email On Top)")
    print("=" * 80)

    if not INPUT_CSV.exists():
        print(f"[-] Không tìm thấy file input: {INPUT_CSV}")
        return

    df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total = len(df)
    print(f"[*] Tổng số doanh nghiệp cần làm giàu: {total:,}")

    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            cached_emails = sum(1 for v in cache.values() if v.get('Email'))
            print(f"[+] Đã nạp cache: {len(cache):,} mục ({cached_emails:,} có Email sẵn).")
        except Exception:
            cache = {}

    stats = {
        'processed': 0,
        'proff_emails': 0,
        'proff_webs': 0,
        'site_emails': 0
    }

    # Chuẩn bị danh sách tham số công việc
    tasks_args = []
    for idx, r in df.iterrows():
        comp = r.get('Công ty', '').strip()
        orgnr = r.get('Orgnr', '').strip()
        city = r.get('Thành phố', '').strip()
        curr_web = r.get('Web', '').strip()
        curr_em = r.get('Email', '').strip()
        curr_phone = clean_phone_no(r.get('SĐT', ''))
        curr_leader = r.get('Người liên hệ', '').strip()
        curr_role = r.get('Chức danh', '').strip()
        tasks_args.append((idx, comp, orgnr, city, curr_web, curr_em, curr_phone, curr_leader, curr_role))

    print(f"[*] Khởi động {MAX_WORKERS} luồng bóc tách song song...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_single_company, arg, cache, stats, df, total) for arg in tasks_args]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    # Lưu lần cuối
    save_outputs(df)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total_with_email = (df['Email'] != '').sum()
    total_with_web = (df['Web'] != '').sum()

    print("\n" + "=" * 80)
    print(" HOÀN TẤT LÀM GIÀU DỮ LIỆU AGENCY NA UY THÀNH CÔNG!")
    print(f" [*] Email trực tiếp từ Proff.no    : +{stats['proff_emails']:,}")
    print(f" [*] Email bóc tách từ Website      : +{stats['site_emails']:,}")
    print(f" [*] Website mới từ Proff.no        : +{stats['proff_webs']:,}")
    print(f" [*] TỔNG SỐ EMAIL B2B ĐẠT ĐƯỢC     : {total_with_email:,} / {total:,}")
    print(f" [*] TỔNG SỐ WEBSITE ĐẠT ĐƯỢC      : {total_with_web:,} / {total:,}")
    print(f" [*] File kết quả đầy đủ            : {OUTPUT_1ENR_CSV.name}")
    print(f" [*] File Cold Mail chuẩn 20 cột   : {OUTPUT_2COL_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()
