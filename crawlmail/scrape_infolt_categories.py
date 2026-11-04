# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU INFO.LT (LITHUANIA B2B DIRECTORY)
=====================================================
Mục tiêu cào 2 danh mục độc lập thành 2 file riêng biệt:
1. Environmental management, greenery planting:
   https://www.info.lt/en/rubrika/Environmental-management-greenery-planting/100209479
   -> Xuất file: LT_ENVI_INLT_0RAW.csv và LT_ENVI_INLT_2COL.csv (Chuẩn 17 ký tự)
2. Welding, equipment:
   https://www.info.lt/en/rubrika/Welding-equipment/100209653
   -> Xuất file: LT_WELD_INLT_0RAW.csv và LT_WELD_INLT_2COL.csv (Chuẩn 17 ký tự)

Đặc tính kỹ thuật tuân thủ nghiêm ngặt GEMINI.md:
- Bóc tách đầy đủ chi tiết: Tên pháp lý, Mã doanh nghiệp (Company code), Mã PVM (VAT),
  Người đại diện/Giám đốc (Direktorius), SĐT có nháy đơn ('+370...), Website, Địa chỉ,
  Thành phố, Mã bưu điện, Số nhân sự, Lương bình quân (Average wage), Danh mục ngành nghề.
- Giải mã thuật toán XOR Obfuscation (data-link-ob / data-text-ob) bóc tách email thật 100%.
- Chấm điểm email B2B (score_email_b2b_lt), chỉ giữ 1 email giá trị nhất cho file Cold Mail.
- Đẩy 100% doanh nghiệp có Email lên các dòng đầu tiên (dòng 1..N).
- Kiểm tra danh sách đen vĩnh viễn (Scandi Standard Baltics, Biliarta, Daigre).
- Lưu tăng dần (Incremental Checkpoint) và Cache JSON độc lập từng danh mục để Resume 100%.
- Tự động đồng bộ sang csdl_mlt/ và archive/lt_lithuania/.
"""

import os
import sys
import re
import csv
import json
import time
import base64
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
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

# Cấu hình danh mục cào
CATEGORIES = {
    'weld': {
        'name': 'Welding, equipment',
        'code': 'WELD',
        'cat_id': '100209653',
        'url': 'https://www.info.lt/en/rubrika/Welding-equipment/100209653',
        'raw_csv': ROOT_DIR / "LT_WELD_INLT_0RAW.csv",
        'col2_csv': ROOT_DIR / "LT_WELD_INLT_2COL.csv",
        'cache_file': ROOT_DIR / "crawlmail" / "cache_infolt_weld.json",
        'archive_dir': ROOT_DIR / "archive" / "lt_lithuania"
    },
    'envi': {
        'name': 'Environmental management, greenery planting',
        'code': 'ENVI',
        'cat_id': '100209479',
        'url': 'https://www.info.lt/en/rubrika/Environmental-management-greenery-planting/100209479',
        'raw_csv': ROOT_DIR / "LT_ENVI_INLT_0RAW.csv",
        'col2_csv': ROOT_DIR / "LT_ENVI_INLT_2COL.csv",
        'cache_file': ROOT_DIR / "crawlmail" / "cache_infolt_envi.json",
        'archive_dir': ROOT_DIR / "archive" / "lt_lithuania"
    }
}

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

    if digits.startswith('370') and len(digits) == 11:
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

def fetch_page_html(url, retries=3):
    """Tải HTML trang với curl_cffi impersonate chrome120 (chống chặn 100%)"""
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate='chrome120', timeout=12)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 404:
                return None
        except Exception:
            time.sleep(1.0)
    return None

def parse_company_detail(detail_url, main_category_name=""):
    """Bóc tách thông tin chi tiết đầy đủ của một công ty trên info.lt"""
    html = fetch_page_html(detail_url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    comp_name = h1.text.strip() if h1 else ''
    if not comp_name:
        return None

    # Lấy địa chỉ từ thẻ liền sau H1
    raw_addr = ''
    if h1:
        for sib in h1.next_siblings:
            if getattr(sib, 'name', None) and sib.text.strip():
                raw_addr = sib.text.strip().splitlines()[0].strip()
                break

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
        'Tag_Chinh': main_category_name,
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

    # 1. Quét toàn bộ thẻ data-link-ob (Email đã mã hóa XOR)
    for em_tag in soup.find_all(attrs={'data-link-ob': True}):
        decoded = decode_info_lt_ob(em_tag['data-link-ob']).replace('mailto:', '').strip().lower()
        if decoded and '@' in decoded:
            found_emails.append(decoded)

    # 2. Duyệt các hàng thuộc tính (div.row)
    for row in soup.find_all('div', class_='row'):
        c4 = row.find('div', class_='col-xs-4')
        c8 = row.find('div', class_='col-xs-8')
        if not c4 or not c8:
            continue
        label = c4.text.strip().lower()
        val = ' '.join(c8.stripped_strings)

        if 'company code' in label or 'įmonės kodas' in label:
            data['Company_Code'] = val
        elif 'vat code' in label or 'pvm' in label:
            data['VAT_Code'] = val
        elif any(k in label for k in ['direktor', 'vadov', 'manager', 'prezident', 'savinink']):
            data['Chuc danh'] = c4.text.strip()
            data['Nguoi quan ly'] = val
        elif 'employees' in label or 'darbuotoj' in label:
            data['So nhan vien'] = val
        elif 'date of registration' in label or 'registravimo data' in label:
            data['Nam thanh lap'] = val
        elif 'wage' in label or 'atlyginimas' in label:
            data['Average_Wage'] = val
        elif 'website' in label or 'tinklapis' in label:
            a_tag = c8.find('a', href=True)
            if a_tag and a_tag['href'].startswith('http'):
                data['Website'] = a_tag['href'].strip()
            elif val and not val.lower().startswith('www.facebook'):
                data['Website'] = val if val.startswith('http') else f"https://{val}"
        elif 'phone' in label or 'telefonas' in label:
            # Chỉ lấy nếu là số điện thoại thực tế
            if any(c.isdigit() for c in val):
                m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|8\s*\d+[\d\s]*)', val)
                if m_ph:
                    found_phones.append(m_ph.group(1).strip())

    # Quét thêm số điện thoại trên toàn bộ trang nếu chưa có
    if not found_phones:
        for t_node in soup.find_all(string=re.compile(r'\(\+370\)|\+370')):
            m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*)', str(t_node))
            if m_ph:
                found_phones.append(m_ph.group(1).strip())

    data['SDT'] = clean_phone_lt(found_phones[0]) if found_phones else ''
    
    # Chọn email tối ưu nhất
    domain = urllib.parse.urlparse(data['Website']).netloc if data['Website'] else ''
    data['Email'] = select_best_email(found_emails, domain)

    # 3. Lấy toàn bộ danh mục hoạt động (All_Tags)
    cats = [a.text.strip() for a in soup.find_all('a', href=lambda h: h and '/en/rubrika/' in h) if a.text.strip() != 'List of companies']
    data['All_Tags'] = ' | '.join(list(dict.fromkeys(cats)))

    return data

def save_category_files(cache_data, raw_csv_path, col2_csv_path, archive_dir, main_cat_name):
    """
    Lưu dữ liệu tăng dần và phân loại:
    - 100% doanh nghiệp có Email được đẩy lên đầu (Dòng 1..N)
    - Đồng bộ tự động sang csdl_mlt/ và archive/lt_lithuania/
    """
    all_records = list(cache_data.values())
    
    # Loại trừ danh sách đen cố định (Rule 12)
    valid_records = [r for r in all_records if not is_blacklisted_company(r.get('Cong ty', ''))]

    with_email = [r for r in valid_records if r.get('Email') and '@' in r.get('Email')]
    without_email = [r for r in valid_records if not r.get('Email') or '@' not in r.get('Email')]

    sorted_raw = with_email + without_email
    for i, r in enumerate(sorted_raw, start=1):
        r['No.'] = str(i)

    # 1. Ghi file RAW 20 cột (UTF-8 with BOM)
    raw_csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted_raw, columns=COLUMNS_RAW).to_csv(raw_csv_path, index=False, encoding='utf-8-sig')

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
            'Category': main_cat_name
        }
        col20_rows.append(row_20)

    col2_csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(col20_rows, columns=COLUMNS_20).to_csv(col2_csv_path, index=False, encoding='utf-8-sig')

    # 3. Đồng bộ vào csdl_mlt và archive
    csdl_path = ROOT_DIR / "csdl_mlt" / col2_csv_path.name
    archive_col2_path = archive_dir / col2_csv_path.name
    archive_raw_path = archive_dir / raw_csv_path.name

    csdl_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(col20_rows, columns=COLUMNS_20).to_csv(csdl_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(col20_rows, columns=COLUMNS_20).to_csv(archive_col2_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(sorted_raw, columns=COLUMNS_RAW).to_csv(archive_raw_path, index=False, encoding='utf-8-sig')

    return len(with_email), len(valid_records)

def scrape_category(cat_key, limit=0):
    cfg = CATEGORIES[cat_key]
    print("\n" + "=" * 80)
    print(f" KHỞI CHẠY CÀO DANH MỤC: {cfg['name'].upper()}")
    print(f" URL danh mục: {cfg['url']}")
    print(f" File RAW    : {cfg['raw_csv'].name}")
    print(f" File Cold   : {cfg['col2_csv'].name}")
    print("=" * 80)

    # Nạp cache checkpoint JSON nếu có để Resume 100%
    cache = {}
    if cfg['cache_file'].exists():
        try:
            with open(cfg['cache_file'], 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp checkpoint cache: {len(cache):,} doanh nghiệp đã xử lý từ trước.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # 1. Thu thập toàn bộ URL doanh nghiệp qua phân trang
    print("[*] Đang quét phân trang danh mục...")
    first_html = fetch_page_html(cfg['url'])
    if not first_html:
        print("[!] Không thể truy cập trang danh mục đầu tiên!")
        return

    first_soup = BeautifulSoup(first_html, 'html.parser')
    m_count = re.search(r'Results\s+(\d+)', first_html)
    total_found_str = m_count.group(1) if m_count else "Chưa rõ"
    print(f"[*] Tổng số doanh nghiệp công bố trên info.lt: {total_found_str}")

    offsets = [0]
    for a in first_soup.find_all('a', href=True):
        m_off = re.search(r'/(\d+)-20$', a['href'])
        if m_off:
            offsets.append(int(m_off.group(1)))
    max_offset = max(offsets) if offsets else 0
    all_offsets = list(range(0, max_offset + 1, 20))
    print(f"[*] Tìm thấy {len(all_offsets)} trang (Max offset: {max_offset}).")

    firm_urls = []
    seen_urls = set()

    for off in all_offsets:
        p_url = cfg['url'] if off == 0 else f"{cfg['url']}/{off}-20"
        p_html = fetch_page_html(p_url)
        if not p_html:
            continue
        p_soup = BeautifulSoup(p_html, 'html.parser')
        page_firms = []
        for a in p_soup.find_all('a', href=True):
            href = a['href']
            if '/en/imones/' in href:
                clean_u = href.split('?')[0].split('#')[0]
                if clean_u not in seen_urls:
                    seen_urls.add(clean_u)
                    firm_urls.append(clean_u)
                    page_firms.append(clean_u)
        print(f"  -> Offset {off:>4}/{max_offset}: Thu thập được {len(page_firms)} công ty mới (Lũy kế: {len(firm_urls)})")
        time.sleep(0.15)

    print(f"\n[*] TỔNG CỘNG THU THẬP ĐƯỢC {len(firm_urls):,} DOANH NGHIỆP DUY NHẤT TRONG DANH MỤC.")

    # 2. Truy cập từng trang chi tiết để bóc tách thông tin
    to_process = firm_urls if limit == 0 else firm_urls[:limit]
    print(f"[*] Bắt đầu truy cập chi tiết {len(to_process):,} doanh nghiệp...\n")

    processed = 0
    for idx, f_url in enumerate(to_process, start=1):
        # Nếu đã có trong cache và có email -> Bỏ qua
        if f_url in cache:
            processed += 1
            if processed % 20 == 0:
                print(f"[{processed:04d}/{len(to_process)}] Đã xử lý (từ cache)...")
            continue

        c_data = parse_company_detail(f_url, cfg['name'])
        if not c_data:
            continue

        cache[f_url] = c_data
        processed += 1

        em_log = f"Email: {c_data['Email']}" if c_data['Email'] else "Chưa có email"
        ph_log = f"SĐT: {c_data['SDT']}" if c_data['SDT'] else "Chưa có SĐT"
        wb_log = f"Web: {c_data['Website'][:22]}" if c_data['Website'] else "Chưa có Web"
        mgr_log = f"GĐ: {c_data['Nguoi quan ly'][:18]}" if c_data['Nguoi quan ly'] else "GĐ: -"
        print(f"[{processed:04d}/{len(to_process)}] {c_data['Cong ty'][:28]:<28} | {em_log:<32} | {ph_log:<18} | {mgr_log}")

        # Tự động lưu tăng dần sau mỗi 5 công ty (Rule 5)
        if processed % 5 == 0:
            with open(cfg['cache_file'], 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cur_em, cur_tot = save_category_files(cache, cfg['raw_csv'], cfg['col2_csv'], cfg['archive_dir'], cfg['name'])
            print(f"  >>> [AUTO-SAVE] Checkpoint: {cur_tot} công ty ({cur_em} có Email B2B được đẩy lên đầu).")

        time.sleep(0.2)

    # Lưu lần cuối
    with open(cfg['cache_file'], 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    final_em, final_tot = save_category_files(cache, cfg['raw_csv'], cfg['col2_csv'], cfg['archive_dir'], cfg['name'])

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT CÀO DANH MỤC: {cfg['name'].upper()}!")
    print(f" - Tổng doanh nghiệp thu thập           : {final_tot:,}")
    print(f" - Doanh nghiệp CÓ EMAIL B2B (Dòng 1..N): {final_em:,}")
    print(f" - Doanh nghiệp chưa có email           : {final_tot - final_em:,}")
    print(f" - File RAW 20 cột đã xuất              : {cfg['raw_csv'].name}")
    print(f" - File Cold Mail 20 cột đã xuất        : {cfg['col2_csv'].name}")
    print(f" - Tệp Cache lưu trữ checkpoint         : {cfg['cache_file'].name}")
    print(f" - Đồng bộ sang csdl_mlt & archive      : THÀNH CÔNG")
    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Scraper info.lt for Lithuania B2B Directory")
    parser.add_argument('--cat', choices=['weld', 'envi', 'all'], default='all', help="Danh mục cần cào (weld, envi, all)")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty cào để test (0 = toàn bộ)")
    args = parser.parse_args()

    if args.cat in ['weld', 'all']:
        scrape_category('weld', limit=args.limit)
    if args.cat in ['envi', 'all']:
        scrape_category('envi', limit=args.limit)

if __name__ == '__main__':
    main()
