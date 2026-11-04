# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU THỰC PHẨM & GIA CẦM LITVA QUA CỔNG INFO.LT
(LITHUANIA FOOD & POULTRY DATA ENRICHMENT VIA INFO.LT)
=============================================================================
Mục tiêu:
Làm giàu dữ liệu CHÍNH XÁC cho 2 tệp Litva hiện có (KHÔNG THÊM CÔNG TY MỚI):
1. Tệp Thịt gà / Gia cầm Litva: LT_POUL_WEBD_2COL.csv (979 công ty)
2. Tệp Thực phẩm Litva        : LT_FOOD_WEBS - CleanData.csv (1.142 công ty)

Quy trình làm giàu 3 tầng:
1. Tra cứu chính xác trên info.lt:
   - Tra theo Mã số doanh nghiệp (IČO / FirmCode) nếu có để khớp 100%.
   - Tra theo Tên doanh nghiệp (Firm / q) kết hợp bộ lọc So khớp nghiêm ngặt (Rule 11).
2. Thu thập dữ liệu từ trang chi tiết info.lt:
   - Giải mã XOR Obfuscation (data-link-ob) lấy email B2B trực tiếp.
   - Bóc tách Giám đốc (Direktorius/Vadovas), SĐT chuẩn hóa (+370...), Website, Địa chỉ, Mã số DN.
3. Quét website tự động (nếu info.lt chưa có mail nhưng có Website):
   - Tự động quét trang chủ và các subpage (/kontaktai, /apie, /karjera...).
   - Bóc tách email B2B và chấm điểm theo score_email_b2b_lt.
4. Bảo vệ dữ liệu & Loại trừ:
   - Giữ nguyên 100% các email đã có sẵn hợp lệ.
   - Loại trừ email nằm trong Mail Tracker và danh sách bounce.
   - Loại trừ danh sách đen cố định (Scandi Standard Baltics, Biliarta, Daigre).
5. Lưu tăng dần (Incremental Auto-Save) sau mỗi 5 công ty & Checkpoint JSON để Resume 100%.
6. Đẩy 100% công ty có Email lên các dòng đầu tiên (dòng 1..N).
"""

import os
import sys
import re
import json
import time
import base64
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
import curl_cffi.requests as requests

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# Cấu hình 2 tập dữ liệu
DATASETS = {
    'poul': {
        'name': 'Gia cầm Litva (Poultry)',
        'input_2col': ROOT_DIR / "LT_POUL_WEBD_2COL.csv",
        'raw_lookup': ROOT_DIR / "LT_POUL_WEBD_0RAW.csv",
        'output_1enr': ROOT_DIR / "LT_POUL_WEBD_1ENR.csv",
        'output_2col': ROOT_DIR / "LT_POUL_WEBD_2COL.csv",
        'cache_file': ROOT_DIR / "crawlmail" / "cache_enrich_infolt_lt_poul.json",
        'archive_dir': ROOT_DIR / "archive" / "lt_lithuania",
        'default_cat': 'Poultry and Meat Processing (Lithuania)'
    },
    'food': {
        'name': 'Thực phẩm Litva (Food)',
        'input_2col': ROOT_DIR / "LT_FOOD_WEBS - CleanData.csv",
        'raw_lookup': ROOT_DIR / "archive" / "lt_lithuania" / "LT_FOOD_WEBD_0RAW.csv",
        'output_1enr': ROOT_DIR / "LT_FOOD_WEBD_1ENR.csv",
        'output_2col': ROOT_DIR / "LT_FOOD_WEBD_2COL.csv",
        'sync_cleandata': ROOT_DIR / "LT_FOOD_WEBS - CleanData.csv",
        'cache_file': ROOT_DIR / "crawlmail" / "cache_enrich_infolt_lt_food.json",
        'archive_dir': ROOT_DIR / "archive" / "lt_lithuania",
        'default_cat': 'Food & Meat Industry (Lithuania)'
    }
}

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

COLUMNS_RAW = [
    'No.', 'Company_Code', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'VAT_Code', 'Nguoi quan ly', 'Chuc danh',
    'Average_Wage', 'So nhan vien', 'Nam thanh lap', 'InfoLT_URL'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')

# Danh sách đen cố định (Rule 12)
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

# Tải danh sách email đã bounce / reply để loại trừ
EXCLUDED_EMAILS = set()
for path in [
    ROOT_DIR / "Mail Tracker - mail.csv",
    ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_DA_LOAI_BO_REPLY_BOUNCE.csv",
    ROOT_DIR / "archive" / "lt_lithuania" / "LT_FOOD_DA_LOAI_BO_REPLY_BOUNCE.csv"
]:
    if path.exists():
        try:
            df_ex = pd.read_csv(path, encoding='utf-8-sig', dtype=str).fillna('')
            for col in ['Email', 'email', 'Mail', 'mail']:
                if col in df_ex.columns:
                    for em in df_ex[col]:
                        clean_em = str(em).strip().lower()
                        if clean_em and '@' in clean_em:
                            EXCLUDED_EMAILS.add(clean_em)
        except Exception:
            pass

print(f"[*] Đã nạp danh sách loại trừ Mail Tracker & Bounce: {len(EXCLUDED_EMAILS):,} email.")

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
    """Chuẩn hóa số điện thoại Litva có nháy đơn (') ở đầu theo Rule 2"""
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

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    em = em.lower()

    # Cắt các đuôi website hoặc SĐT bị dính liền vào email trên website lỗi (VD: info@domain.ltwww.domain.lt hoặc info@domain.lt+370...)
    em = re.sub(r'(\.[a-z]{2,6})www\..*$', r'\1', em, flags=re.I)
    em = re.sub(r'(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$', r'\1', em, flags=re.I)

    if not re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@', 'your@', 'yourcompany']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'email', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    return em

def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email B2B cho thị trường Litva theo Rule 3"""
    e = clean_email(email)
    if not e or '@' not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1

    if e in EXCLUDED_EMAILS:
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

    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'prezidentas']:
        score += 45
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
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

def is_valid_name_match(csv_name, infolt_name):
    """So khớp tên nghiêm ngặt & thông minh theo Rule 11"""
    if not csv_name or not infolt_name:
        return False
    
    # Bỏ chú thích tiếng Anh trong ngoặc
    q_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(csv_name))
    c_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(infolt_name))
    
    q = unicodedata.normalize('NFKD', q_raw).lower()
    q = ''.join(c for c in q if not unicodedata.combining(c))
    c = unicodedata.normalize('NFKD', c_raw).lower()
    c = ''.join(c for c in c if not unicodedata.combining(c))
    
    # Khử loại hình doanh nghiệp Litva
    legal_forms = ['uab', 'mb', 'ab', 'ii', 'vsi', 'tub', 'kub', 'filialas', 'parduotuve', 'centras', 'prekyba']
    for lf in legal_forms:
        q = re.sub(rf'\b{lf}\b', ' ', q).strip()
        c = re.sub(rf'\b{lf}\b', ' ', c).strip()
        
    q = ' '.join(re.sub(r'[^a-z0-9]', ' ', q).split())
    c = ' '.join(re.sub(r'[^a-z0-9]', ' ', c).split())
    
    if not q or not c:
        return False
    if q == c:
        return True
    if len(q) >= 4 and (q in c or c in q):
        return True
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if len(q_tokens) > 1 and len(q_tokens.intersection(c_tokens)) >= len(q_tokens) * 0.7:
        return True
    return False

import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'lt,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

def fetch_html_stealth(url, retries=2):
    """Fetch HTML với curl_cffi chrome120 hoặc urllib fallback (timeout 5s)"""
    for _ in range(retries):
        try:
            r = requests.get(url, impersonate='chrome120', timeout=6, verify=False)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception:
            pass
        time.sleep(0.3)
    return None

def crawl_site_for_emails(site_url):
    """Quét trang web trang chủ và các subpage Litva (/kontaktai, /apie...)"""
    if not site_url or not isinstance(site_url, str):
        return ""
    u_str = site_url.strip()
    if not u_str.startswith('http'):
        u_str = 'http://' + u_str
    
    try:
        domain_parsed = urllib.parse.urlparse(u_str)
        base_domain = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
    except Exception:
        return ""

    html = fetch_html_stealth(u_str)
    if not html:
        return ""

    found_emails = set()

    def parse_page_emails(page_html):
        soup = BeautifulSoup(page_html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if href.startswith('mailto:'):
                em = clean_email(href)
                if em:
                    found_emails.add(em)
            elif '@' in href and not any(href.lower().endswith(ext) for ext in INVALID_EXTS):
                em = clean_email(href)
                if em:
                    found_emails.add(em)
        for em in EMAIL_REGEX.findall(page_html):
            clean_em = clean_email(em)
            if clean_em:
                found_emails.add(clean_em)

    parse_page_emails(html)
    best = select_best_email(found_emails, domain_parsed.netloc)
    if best and score_email_b2b_lt(best, domain_parsed.netloc) >= 50:
        return best

    sub_paths = [
        '/kontaktai', '/kontaktai.html', '/apie-mus', '/apie',
        '/rekvizitai', '/karjera', '/darbas', '/contacts'
    ]
    soup_home = BeautifulSoup(html, 'html.parser')
    internal_links = set()
    for a in soup_home.find_all('a', href=True):
        href = a['href'].strip()
        for sp in sub_paths:
            if sp in href.lower():
                full_url = urllib.parse.urljoin(base_domain, href)
                if full_url.startswith(base_domain):
                    internal_links.add(full_url)

    target_links = list(internal_links)[:4] if internal_links else [f"{base_domain.rstrip('/')}{sp}" for sp in sub_paths[:3]]

    for sub_url in target_links:
        sub_html = fetch_html_stealth(sub_url)
        if sub_html:
            parse_page_emails(sub_html)
            best = select_best_email(found_emails, domain_parsed.netloc)
            if best and score_email_b2b_lt(best, domain_parsed.netloc) >= 50:
                return best

    return select_best_email(found_emails, domain_parsed.netloc)

def search_and_parse_infolt(comp_name, comp_code=""):
    """
    Tìm kiếm và bóc tách dữ liệu công ty trên info.lt
    Ưu tiên 1: Tra theo Mã số doanh nghiệp (FirmCode)
    Ưu tiên 2: Tra theo Tên doanh nghiệp (q / Firm)
    """
    detail_url = None
    target_comp = None

    # 1. Tra cứu theo mã số doanh nghiệp (nếu có IČO / Company Code)
    if comp_code and len(str(comp_code).strip()) in [7, 8, 9]:
        c_code = str(comp_code).strip()
        search_u = f"https://www.info.lt/en?action=ieskoti&page=imones&view=detali&FirmCode={c_code}"
        html = fetch_html_stealth(search_u)
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for h2 in soup.find_all('h2', class_='pavadinimas_paprastas'):
                a = h2.find('a', href=True)
                if a:
                    detail_url = a['href']
                    target_comp = a.text.strip()
                    break

    # 2. Tra cứu theo tên doanh nghiệp nếu chưa tìm thấy theo mã số
    if not detail_url and comp_name:
        clean_q = re.sub(r'\([^\)]*\)|\[[^\]]*\]', '', comp_name).strip()
        clean_q = re.sub(r'\b(UAB|MB|AB|IĮ|VšĮ|TŪB)\b', '', clean_q, flags=re.I).strip(' ,-"\'')
        if clean_q:
            search_u = f"https://www.info.lt/en?action=ieskoti&page=imones&view=greita&q={urllib.parse.quote_plus(clean_q)}"
            html = fetch_html_stealth(search_u)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for h2 in soup.find_all('h2', class_='pavadinimas_paprastas'):
                    a = h2.find('a', href=True)
                    if a:
                        cand_name = a.text.strip()
                        if is_valid_name_match(comp_name, cand_name):
                            detail_url = a['href']
                            target_comp = cand_name
                            break

    if not detail_url:
        return None

    # 3. Truy cập trang chi tiết công ty trên info.lt
    det_html = fetch_html_stealth(detail_url)
    if not det_html:
        return None

    soup = BeautifulSoup(det_html, 'html.parser')
    h1 = soup.find('h1')
    c_name = h1.text.strip() if h1 else (target_comp or comp_name)

    # Địa chỉ
    raw_addr = ''
    if h1:
        for sib in h1.next_siblings:
            if getattr(sib, 'name', None) and sib.text.strip():
                raw_addr = sib.text.strip().splitlines()[0].strip()
                break

    data = {
        'Cong ty': c_name,
        'Company_Code': '',
        'VAT_Code': '',
        'Leader_Role': '',
        'Leader_Name': '',
        'SDT': '',
        'Email': '',
        'Website': '',
        'Dia chi': raw_addr,
        'Thanh pho': '',
        'Ma buu dien': '',
        'Employees': '',
        'Average_Wage': '',
        'Reg_Date': '',
        'Categories': '',
        'InfoLT_URL': detail_url
    }

    found_emails = []
    found_phones = []

    # Giải mã email XOR
    for em_tag in soup.find_all(attrs={'data-link-ob': True}):
        decoded = decode_info_lt_ob(em_tag['data-link-ob']).replace('mailto:', '').strip().lower()
        if decoded and '@' in decoded:
            found_emails.append(decoded)

    # Duyệt các hàng thuộc tính (div.row)
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
            data['Leader_Role'] = c4.text.strip()
            data['Leader_Name'] = val
        elif 'employees' in label or 'darbuotoj' in label:
            data['Employees'] = val
        elif 'date of registration' in label or 'registravimo data' in label:
            data['Reg_Date'] = val
        elif 'wage' in label or 'atlyginimas' in label:
            data['Average_Wage'] = val
        elif 'website' in label or 'tinklapis' in label:
            a_tag = c8.find('a', href=True)
            if a_tag and a_tag['href'].startswith('http'):
                data['Website'] = a_tag['href'].strip()
            elif val and not val.lower().startswith('www.facebook'):
                data['Website'] = val if val.startswith('http') else f"https://{val}"
        elif 'phone' in label or 'telefonas' in label:
            if any(c.isdigit() for c in val):
                m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|8\s*\d+[\d\s]*)', val)
                if m_ph:
                    found_phones.append(m_ph.group(1).strip())

    if not found_phones:
        for t_node in soup.find_all(string=re.compile(r'\(\+370\)|\+370')):
            m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*)', str(t_node))
            if m_ph:
                found_phones.append(m_ph.group(1).strip())

    data['SDT'] = clean_phone_lt(found_phones[0]) if found_phones else ''
    domain = urllib.parse.urlparse(data['Website']).netloc if data['Website'] else ''
    data['Email'] = select_best_email(found_emails, domain)

    # Nếu info.lt chưa có mail mà có Website -> Quét thẳng website để bắt email
    if not data['Email'] and data['Website']:
        web_email = crawl_site_for_emails(data['Website'])
        if web_email:
            data['Email'] = web_email

    return data

def save_enriched_dataset(df_current, cfg):
    """
    Lưu tăng dần file Cold Mail và RAW:
    - 100% doanh nghiệp có email được đẩy lên đầu (dòng 1..N)
    - Đồng bộ tự động sang csdl_mlt/ và archive/lt_lithuania/
    """
    has_em = df_current[df_current['Email'].str.contains('@', na=False)].copy()
    no_em = df_current[~df_current['Email'].str.contains('@', na=False)].copy()
    
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    
    # 1. Xuất file Cold Mail 20 cột
    cfg['output_2col'].parent.mkdir(parents=True, exist_ok=True)
    df_sorted.to_csv(cfg['output_2col'], index=False, encoding='utf-8-sig')

    if 'sync_cleandata' in cfg and cfg['sync_cleandata'].exists():
        df_sorted.to_csv(cfg['sync_cleandata'], index=False, encoding='utf-8-sig')

    # 2. Xuất file 1ENR
    df_sorted.to_csv(cfg['output_1enr'], index=False, encoding='utf-8-sig')

    # 3. Đồng bộ vào csdl_mlt và archive
    csdl_path = ROOT_DIR / "csdl_mlt" / cfg['output_2col'].name
    archive_col2_path = cfg['archive_dir'] / cfg['output_2col'].name
    archive_1enr_path = cfg['archive_dir'] / cfg['output_1enr'].name

    csdl_path.parent.mkdir(parents=True, exist_ok=True)
    cfg['archive_dir'].mkdir(parents=True, exist_ok=True)

    df_sorted.to_csv(csdl_path, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(archive_col2_path, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(archive_1enr_path, index=False, encoding='utf-8-sig')

    return len(has_em)

def run_enrich_dataset(dataset_key, limit=0):
    cfg = DATASETS[dataset_key]
    print("\n" + "=" * 80)
    print(f" LÀM GIÀU DỮ LIỆU BẰNG CỔNG INFO.LT: {cfg['name'].upper()}")
    print(f" File dữ liệu đích: {cfg['input_2col'].name}")
    print("=" * 80)

    if not cfg['input_2col'].exists():
        print(f"[!] Lỗi: Không tìm thấy file {cfg['input_2col']}!")
        return

    df = pd.read_csv(cfg['input_2col'], encoding='utf-8-sig', dtype=str).fillna('')

    # Đọc IČO từ file RAW phụ nếu có
    ico_lookup = {}
    if cfg['raw_lookup'].exists():
        try:
            df_r = pd.read_csv(cfg['raw_lookup'], encoding='utf-8-sig', dtype=str).fillna('')
            ico_col = 'IČO' if 'IČO' in df_r.columns else ('Company_Code' if 'Company_Code' in df_r.columns else '')
            name_col = 'Công ty' if 'Công ty' in df_r.columns else 'Cong ty'
            if ico_col and name_col:
                for _, r in df_r.iterrows():
                    c_n = str(r[name_col]).strip().lower()
                    c_i = str(r[ico_col]).strip()
                    if c_n and c_i:
                        ico_lookup[c_n] = c_i
            print(f"[*] Nạp từ điển IČO/Company Code: {len(ico_lookup):,} mã doanh nghiệp.")
        except Exception as e:
            print(f"[!] Warning reading raw lookup: {e}")

    # Đọc cache checkpoint JSON
    cache = {}
    if cfg['cache_file'].exists():
        try:
            with open(cfg['cache_file'], 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp checkpoint cache: {len(cache):,} công ty đã xử lý từ trước.")
        except Exception as e:
            print(f"[!] Warning reading cache: {e}")

    # Xác định các công ty cần làm giàu (ưu tiên công ty CHƯA CÓ EMAIL)
    indices_to_enrich = []
    for idx, row in df.iterrows():
        comp = str(row['Công ty']).strip()
        if not comp or is_blacklisted_company(comp):
            continue
        em = clean_email(row['Email'])
        c_key = comp.lower()
        # Nếu chưa có email hoặc trong cache đã tìm thấy email mới
        if not em or (c_key in cache and cache[c_key].get('Email')):
            indices_to_enrich.append(idx)

    total_need = len(indices_to_enrich)
    to_process = indices_to_enrich if limit == 0 else indices_to_enrich[:limit]

    print(f"[*] Tổng doanh nghiệp trong file : {len(df):,}")
    print(f"[*] Doanh nghiệp đã có Email B2B : {len(df) - total_need:,}")
    print(f"[*] Doanh nghiệp cần làm giàu    : {total_need:,}")
    print(f"[*] Sẽ xử lý trong đợt này       : {len(to_process):,}\n")

    new_emails = 0
    new_leaders = 0
    new_webs = 0
    new_phones = 0
    processed = 0

    for idx in to_process:
        comp = str(df.at[idx, 'Công ty']).strip()
        current_email = clean_email(df.at[idx, 'Email'])
        current_phone = clean_phone_lt(df.at[idx, 'SĐT'])
        current_web = str(df.at[idx, 'Liên Hệ']).strip()
        current_leader = str(df.at[idx, 'Người liên hệ']).strip()
        current_role = str(df.at[idx, 'Chức danh']).strip()
        current_addr = str(df.at[idx, 'Địa chỉ']).strip()

        c_key = comp.lower()
        c_ico = ico_lookup.get(c_key, '')

        # Kiểm tra cache
        if c_key in cache:
            item = cache[c_key]
            if item.get('Email') and not current_email:
                df.at[idx, 'Email'] = item['Email']
                df.at[idx, 'Check gửi'] = 'Chưa gửi'
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{item['Email']}"
            if item.get('Leader') and not current_leader:
                df.at[idx, 'Người liên hệ'] = item['Leader']
            if item.get('Role') and not current_role:
                df.at[idx, 'Chức danh'] = item['Role']
            if item.get('Web') and not current_web:
                df.at[idx, 'Liên Hệ'] = item['Web']
            if item.get('Phone') and not current_phone:
                df.at[idx, 'SĐT'] = item['Phone']
            if item.get('Address') and not current_addr:
                df.at[idx, 'Địa chỉ'] = item['Address']

            processed += 1
            if processed % 15 == 0:
                print(f"[{processed:04d}/{len(to_process)}] Đã xử lý (cache hit)...")
            continue

        # Tìm kiếm trên info.lt
        match_data = search_and_parse_infolt(comp, c_ico)

        cache_entry = {
            'Matched': False,
            'Email': '',
            'Phone': '',
            'Web': '',
            'Leader': '',
            'Role': '',
            'Address': '',
            'Company_Code': ''
        }

        if match_data:
            cache_entry['Matched'] = True
            cache_entry['Company_Code'] = match_data.get('Company_Code', '')
            
            # Cập nhật email nếu chưa có
            found_em = match_data.get('Email', '')
            if found_em and not current_email:
                df.at[idx, 'Email'] = found_em
                df.at[idx, 'Check gửi'] = 'Chưa gửi'
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{found_em}"
                cache_entry['Email'] = found_em
                new_emails += 1

            # Cập nhật lãnh đạo nếu chưa có
            f_leader = match_data.get('Leader_Name', '')
            f_role = match_data.get('Leader_Role', '')
            if f_leader and not current_leader:
                df.at[idx, 'Người liên hệ'] = f_leader
                cache_entry['Leader'] = f_leader
                new_leaders += 1
            if f_role and not current_role:
                df.at[idx, 'Chức danh'] = f_role
                cache_entry['Role'] = f_role

            # Cập nhật website
            f_web = match_data.get('Website', '')
            if f_web and not current_web:
                df.at[idx, 'Liên Hệ'] = f_web
                cache_entry['Web'] = f_web
                new_webs += 1

            # Cập nhật số điện thoại
            f_phone = match_data.get('SDT', '')
            if f_phone and not current_phone:
                df.at[idx, 'SĐT'] = f_phone
                cache_entry['Phone'] = f_phone
                new_phones += 1

            # Cập nhật địa chỉ nếu thiếu
            f_addr = match_data.get('Dia chi', '')
            if f_addr and not current_addr:
                df.at[idx, 'Địa chỉ'] = f_addr
                cache_entry['Address'] = f_addr

            cache[c_key] = cache_entry
            processed += 1

            log_em = f"Email: {found_em}" if found_em else "Chưa có email"
            log_ldr = f"GĐ: {f_leader[:16]}" if f_leader else "GĐ: -"
            log_web = f"Web: {f_web[:20]}" if f_web else "Web: -"
            print(f"[{processed:04d}/{len(to_process)}] {comp[:28]:<28} | MATCH info.lt | {log_em:<28} | {log_ldr:<22} | {log_web}")

        else:
            cache[c_key] = cache_entry
            processed += 1
            print(f"[{processed:04d}/{len(to_process)}] {comp[:28]:<28} | NOT FOUND on info.lt")

        # Lưu tăng dần sau mỗi 5 công ty (Rule 5)
        if processed % 5 == 0:
            with open(cfg['cache_file'], 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cur_em = save_enriched_dataset(df, cfg)
            print(f"  >>> [AUTO-SAVE] Đã cập nhật tệp: {cur_em} doanh nghiệp có email được đẩy lên đầu.")

        time.sleep(0.2)

    # Lưu lần cuối
    with open(cfg['cache_file'], 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    final_em = save_enriched_dataset(df, cfg)

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT LÀM GIÀU CHO: {cfg['name'].upper()}!")
    print(f" - Tổng công ty đã xử lý trong đợt này : {processed:,}")
    print(f" - Email B2B mới tìm thấy             : +{new_emails:,}")
    print(f" - Giám đốc/Lãnh đạo mới bổ sung       : +{new_leaders:,}")
    print(f" - Website mới bổ sung                 : +{new_webs:,}")
    print(f" - SĐT mới bổ sung                     : +{new_phones:,}")
    print(f" - TỔNG DOANH NGHIỆP CÓ EMAIL TRONG FILE: {final_em:,}")
    print(f" - File Cold Mail đã cập nhật          : {cfg['output_2col'].name}")
    print(f" - Tệp Checkpoint Cache                : {cfg['cache_file'].name}")
    print(f" - Đồng bộ sang csdl_mlt & archive     : THÀNH CÔNG")
    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Enrich Lithuania Food and Poultry Data via info.lt")
    parser.add_argument('--target', choices=['food', 'poul', 'all'], default='all', help="Tập dữ liệu cần làm giàu (food, poul, all)")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty xử lý để test (0 = toàn bộ)")
    args = parser.parse_args()

    if args.target in ['poul', 'all']:
        run_enrich_dataset('poul', limit=args.limit)
    if args.target in ['food', 'all']:
        run_enrich_dataset('food', limit=args.limit)

if __name__ == '__main__':
    main()
