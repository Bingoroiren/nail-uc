# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP NA UY BẰNG GOOGLE MAPS & WEB EMAIL
(GOOGLE MAPS & WEB EMAIL ENRICHMENT - NORWAY AGRICULTURE & FARMING)
=============================================================================
Tuân thủ toàn bộ quy chuẩn tại GEMINI.md, data-standards, crawl-mail và enrich-maps:
1. Smart & Strict Name Matching (NFKD, khử legal forms AS, ANS, DA, ENK, SA..., dấu phân tách, ngoặc chú thích).
2. Chuẩn hóa SĐT có nháy đơn ('): phone = f"'{phone}" (+47 ...).
3. Bóc tách email B2B đa tầng & chấm điểm tối ưu (score_email_b2b_no_farm):
   - Ưu tiên Quản lý / Lãnh đạo / Chủ trang trại (bonde@, eier@, dagligleder@, leder@, adm@) +45
   - Ưu tiên Cổng liên hệ chính thức / Trang trại (post@, kontakt@, firmapost@, info@, kontor@) +40
   - Ưu tiên Tuyển dụng / Nhân sự nông vụ (jobb@, karriere@, hr@, stilling@, arbeid@, sesong@) +50
   - Ưu tiên Bán buôn / Nông sản (salg@, ordre@, butikk@, utsalg@) +35
   - Lọc sạch 100% ký tự lạ (\u00a0, %20, \u200b), loại trừ email rác/template.
   - Chỉ giữ DUY NHẤT 1 email giá trị nhất.
4. Bật trình duyệt trực quan Playwright (headless=False, viewport 1280x800), chuông báo \a khi gặp Captcha.
5. Lưu tăng dần (Incremental Checkpoint) mỗi 5 dòng & Cache JSON để Resume 100%.
6. Danh sách đen vĩnh viễn (Scandi Standard Baltics, Biliarta, Daigre).
7. Tự động đồng bộ sang csdl_mlt/ và archive/no_norway/.
"""

import os
import sys
import re
import ssl
import json
import time
import asyncio
import argparse
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUT_CSV = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
RAW_LOOKUP_CSV = ROOT_DIR / "NO_FARM_COMB_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "NO_FARM_GMAP_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_no_farm.json"
EXCLUDE_BOUNCES_CSV = ROOT_DIR / "archive" / "no_norway" / "NO_AGCY_DA_LOAI_BO_REPLY_BOUNCE.csv"
TRACKER_CSV = ROOT_DIR / "Mail Tracker - mail.csv"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,nn;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Danh bạ, mạng xã hội, cổng thông tin (không lấy làm web công ty)
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'gulesider.no', '1881.no', 'purehelp.no', 'regnskapstall.no', 'firmadatabasen.no',
    'enhetsregisteret.no', 'proffforvalt.no', 'dn.no', 'e24.no',
    'wikipedia.org', 'nav.no', 'arbeidstilsynet.no', 'skatteetaten.no', 'sentry.io',
    'wixpress.com', 'dnb.com', 'zoominfo.com', 'cookiebot.com'
]

# Rule 12: Danh sách đen doanh nghiệp cố định
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

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Tải danh sách email đã bounce hoặc reply để loại trừ
EXCLUDED_EMAILS = set()
for path in [EXCLUDE_BOUNCES_CSV, TRACKER_CSV]:
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

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""

def clean_phone_no(p):
    """Chuẩn hóa số điện thoại Na Uy có nháy đơn (') ở đầu theo Rule 2"""
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    
    if digits.startswith('0047'):
        digits = digits[4:]
    elif digits.startswith('47') and len(digits) >= 10:
        digits = digits[2:]
        
    if len(digits) == 8:
        if digits[0] in ['4', '9']: # Di động Na Uy
            formatted = f"+47 {digits[:3]} {digits[3:5]} {digits[5:]}"
        else: # Cố định Na Uy
            formatted = f"+47 {digits[:2]} {digits[2:4]} {digits[4:6]} {digits[6:]}"
        return f"'{formatted}"
    elif len(digits) > 8:
        return f"'+{digits}"
    else:
        return f"'{s}"

def extract_city_from_address(addr):
    """Tách tên thành phố từ địa chỉ Na Uy (vd: 'Skeimeveien 13, 4560 Vanse' -> 'Vanse')"""
    if not addr or not isinstance(addr, str):
        return ""
    m = re.search(r'\b\d{4}\s+([A-Za-zÆØÅæøåÉéÈè\s\-]+)', addr)
    if m:
        c = m.group(1).strip()
        c = re.sub(r'[,0-9]+$', '', c).strip()
        return c
    parts = addr.split(',')
    if len(parts) > 1:
        return parts[-1].strip()
    return ""

def is_valid_name_match(query_name, candidate_name):
    """Smart & Strict Name Matching cho Na Uy: bỏ loại hình AS, ASA, NUF... và ngoặc chú thích"""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    # Tách phần dịch/chú thích tiếng Anh trong ngoặc (Rule 11)
    q_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(query_name))
    c_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(candidate_name))
    
    q = unicodedata.normalize('NFKD', q_raw).lower()
    q = ''.join(c for c in q if not unicodedata.combining(c))
    c = unicodedata.normalize('NFKD', c_raw).lower()
    c = ''.join(c for c in c if not unicodedata.combining(c))
    
    # Khử loại hình pháp lý Na Uy
    legal_forms = [
        'as', 'asa', 'ans', 'da', 'enk', 'nuf', 'kf', 'iks', 'sa', 'ba',
        'holding', 'group', 'gruppen', 'bedrift', 'gard', 'gardbruk', 'bruk', 'drift'
    ]
    for lf in legal_forms:
        q = re.sub(rf'\b{lf}\b', ' ', q).strip()
        c = re.sub(rf'\b{lf}\b', ' ', c).strip()
        
    q = ' '.join(re.sub(r'[^a-z0-9]', ' ', q).split())
    c = ' '.join(re.sub(r'[^a-z0-9]', ' ', c).split())
    
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    # Khớp chuỗi con nếu độ dài >= 4 ký tự
    if len(q) >= 4 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    # Khớp phần lớn các từ khóa quan trọng (Token overlap >= 70%)
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if len(q_tokens) > 1 and len(q_tokens.intersection(c_tokens)) >= len(q_tokens) * 0.7:
        return True, "TOKEN_MATCH"
        
    return False, "NO_MATCH"

def clean_email(email):
    """
    Làm sạch email triệt để theo quy chuẩn bắt buộc data-standards & GEMINI.md:
    - unquote URL encoding (%20...)
    - Xóa sạch \u00a0, \xa0, &nbsp;, %20, \u200b, \ufeff, zero-width space
    - Xóa tiền tố mailto:, khoảng trắng thừa
    - Cắt dấu câu thừa viền
    - Xử lý tiền tố 20 do decode sót
    """
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

def score_email_b2b_no_farm(email, domain=""):
    """Chấm điểm email B2B ngành Nông nghiệp Na Uy theo chuẩn GEMINI.md & data-standards"""
    e = clean_email(email)
    if not e:
        return -1
    
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1

    if e in EXCLUDED_EMAILS:
        return -1
        
    # Loại bỏ mail template rác / theme demo
    junk_domains = [
        'sentry', 'wixpress', 'wix.com', 'example.com', 'eksempel.no', 'domain.com',
        'domene.no', 'email.com', 'epost.no', 'address.com', 'test.com',
        'cookiebot.com', 'squarespace.com', 'wordpress.com'
    ]
    if any(bad in d for bad in junk_domains):
        return -1
        
    junk_users = [
        'sentry', 'youremail', 'your-email', 'yourname', 'din', 'dinepost', 'din-epost',
        'ditt', 'dittnavn', 'ditt-navn', 'navn', 'fornavn', 'etternavn', 'eksempel',
        'sample', 'no-reply', 'donotreply', 'someone', 'john.doe', 'bruker', 'kunde',
        'privacy', 'gdpr', 'personvern', 'abuse', 'postmaster', 'user', 'name'
    ]
    if any(bad in u for bad in junk_users):
        return -1
    if u in ['mail', 'email', 'epost'] and (d in ['email.com', 'epost.no', 'address.com'] or u == d.split('.')[0]):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.no'):
        score += 25

    # Ưu tiên số 1: Tuyển dụng / Lao động nông nghiệp / Nông vụ (+50đ)
    if u in ['jobb', 'jobber', 'karriere', 'hr', 'rekruttering', 'stilling', 'stillinger', 'arbeid', 'sesong', 'recruitment', 'career']:
        score += 50
    # Ưu tiên số 2: Chủ trang trại / Ban Giám Đốc / Lãnh đạo (+45đ)
    elif u in ['bonde', 'gardbruker', 'eier', 'dagligleder', 'leder', 'ceo', 'director', 'partner', 'styre', 'adm', 'sjef', 'manager']:
        score += 45
    # Ưu tiên số 3: Cổng liên hệ chính thức trang trại (+40đ)
    elif u in ['post', 'kontakt', 'firmapost', 'kontor', 'gard', 'info', 'hei', 'hallo', 'kundeservice', 'sentralbord', 'office']:
        score += 40
    # Ưu tiên số 4: Bán buôn / Đơn hàng nông sản (+35đ)
    elif u in ['salg', 'ordre', 'butikk', 'utsalg', 'marked', 'sales']:
        score += 35
    # Email đích danh cá nhân trên domain (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # Email kỹ thuật / sửa chữa máy / kế toán (+5đ)
    elif u in ['drift', 'verksted', 'servis', 'faktura', 'regnskap']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_no_farm(e, domain) > 0]
    if not valid:
        return ""
    best = max(valid, key=lambda e: score_email_b2b_no_farm(e, domain))
    return clean_email(best)

def fetch_html_stealth(url):
    """Fetch HTML với curl_cffi chrome120 hoặc urllib fallback (timeout 4s)"""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=4, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return ""

def crawl_site_for_emails(site_url):
    """Quét trang web trang chủ và các subpage nông nghiệp Na Uy để tìm email B2B"""
    if not site_url or not isinstance(site_url, str):
        return ""
    u_str = site_url.strip()
    if not u_str.startswith('http'):
        u_str = 'http://' + u_str
    
    domain_parsed = urllib.parse.urlparse(u_str)
    base_domain = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
    
    html = fetch_html_stealth(u_str)
    if not html:
        return ""

    found_emails = set()

    def parse_page_emails(page_html):
        soup = BeautifulSoup(page_html, 'html.parser')
        # 1. Quét thẻ a mailto (Priority cao nhất)
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('mailto:'):
                em = clean_email(href)
                if em:
                    found_emails.add(em)
            if 'data-cfemail' in a.attrs:
                em = clean_email(decode_cf(a['data-cfemail']))
                if em:
                    found_emails.add(em)
        # 2. Quét span/div data-cfemail
        for tag in soup.find_all(attrs={'data-cfemail': True}):
            em = clean_email(decode_cf(tag['data-cfemail']))
            if em:
                found_emails.add(em)
        # 3. Regex trên text
        for em in EMAIL_REGEX.findall(page_html):
            clean_em = clean_email(em)
            if clean_em:
                found_emails.add(clean_em)

    parse_page_emails(html)
    best = select_best_email(found_emails, domain_parsed.netloc)
    if best and score_email_b2b_no_farm(best, domain_parsed.netloc) >= 50:
        return best

    # Quét các subpage bản địa Na Uy (kontakt, om-oss, ansatte, karriere...)
    sub_paths = [
        '/kontakt', '/kontakt-oss', '/kontakt.html', '/kontakt.php',
        '/om-oss', '/om-garden', '/om', '/garden',
        '/ansatte', '/folkene', '/team', '/ansatte.html',
        '/jobb', '/karriere', '/arbeid', '/ledige-stillinger'
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

    target_links = list(internal_links)[:4] if internal_links else [f"{base_domain.rstrip('/')}{sp}" for sp in sub_paths[:4]]

    for sub_url in target_links:
        sub_html = fetch_html_stealth(sub_url)
        if sub_html:
            parse_page_emails(sub_html)
            best = select_best_email(found_emails, domain_parsed.netloc)
            if best and score_email_b2b_no_farm(best, domain_parsed.netloc) >= 60:
                return best

    return select_best_email(found_emails, domain_parsed.netloc)

def save_and_reorder_files(df_current, output_1enr, output_2col):
    """
    Lưu tăng dần và chuẩn hóa:
    - 100% doanh nghiệp có email được đẩy lên các dòng đầu tiên (dòng 1..N)
    - Đồng bộ tự động sang csdl_mlt/ và archive/no_norway/
    """
    has_em = df_current[df_current['Email'].str.contains('@', na=False)].copy()
    no_em = df_current[~df_current['Email'].str.contains('@', na=False)].copy()
    
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    
    # 1. Lưu file 1ENR
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

    # 2. Tạo file 2COL chuẩn Cold Mail 20 cột
    col20_rows = []
    for idx, row in df_sorted.iterrows():
        cname = str(row.get('Công ty', '') or row.get('Company_Name', '')).strip()
        phone = clean_phone_no(row.get('SĐT', '') or row.get('Phone', ''))
        web = str(row.get('Liên Hệ', '') or row.get('Web', '') or row.get('Website', '')).strip()
        email = clean_email(row.get('Email', ''))
        addr = str(row.get('Địa chỉ', '') or row.get('Address', '')).strip()
        category = str(row.get('Category', '') or row.get('Tag_Chinh', '')).strip() or 'Jordbruk'

        existing_check = str(row.get('Check gửi', '')).strip()
        check_gui = existing_check if existing_check else ('Chưa gửi' if email else '')

        r20 = {
            'No.': idx + 1,
            'Công ty': cname,
            'Chức danh': str(row.get('Chức danh', '')).strip() or 'Bonde / Daglig leder / Eier',
            'Người liên hệ': str(row.get('Người liên hệ', '') or row.get('Nguoi quan ly', '')).strip(),
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else '',
            'Địa chỉ': addr,
            'Lương': str(row.get('Lương', '')).strip(),
            'Ngày đăng': str(row.get('Ngày đăng', '')).strip(),
            'Hạn tuyển': str(row.get('Hạn tuyển', '')).strip(),
            'Check gửi': check_gui,
            'Last Subject': str(row.get('Last Subject', '')).strip(),
            'Last Body HTML': str(row.get('Last Body HTML', '')).strip(),
            'Trạng thái Reply': str(row.get('Trạng thái Reply', '')).strip(),
            'Lần Follow-up': str(row.get('Lần Follow-up', '')).strip() or '0',
            'Ngày Follow-up gần nhất': str(row.get('Ngày Follow-up gần nhất', '')).strip(),
            'Mailbox đã dùng': str(row.get('Mailbox đã dùng', '')).strip(),
            'Category': category
        }
        col20_rows.append(r20)

    df_2col = pd.DataFrame(col20_rows, columns=COL_20_HEADERS)
    df_2col.to_csv(output_2col, index=False, encoding='utf-8-sig')

    # Đồng bộ sang csdl_mlt và archive
    csdl_path = ROOT_DIR / "csdl_mlt" / "NO_FARM_COMB_2COL.csv"
    archive_path = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_COMB_2COL.csv"
    csdl_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    df_2col.to_csv(csdl_path, index=False, encoding='utf-8-sig')
    df_2col.to_csv(archive_path, index=False, encoding='utf-8-sig')

    return len(has_em)

async def run_enrichment(input_csv, headless=False, limit=0):
    print("=" * 80)
    print(" GOOGLE MAPS & WEB EMAIL ENRICHMENT - NORWAY AGRICULTURE & FARMING")
    print("=" * 80)
    print(f"[*] File đầu vào (Input)   : {input_csv}")
    print(f"[*] File xuất 1ENR (Output): {OUTPUT_1ENR_CSV}")
    print(f"[*] File Cold Mail 2COL    : {OUTPUT_2COL_CSV}")
    print(f"[*] Tệp Cache Checkpoint   : {CACHE_PATH}")
    print(f"[*] Chế độ Trình duyệt     : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False - Quan sát tiến độ)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(input_csv):
        print(f"[ERROR] Không tìm thấy file: '{input_csv}'")
        return

    df = pd.read_csv(input_csv, encoding='utf-8-sig', dtype=str).fillna('')
    
    name_col = 'Công ty' if 'Công ty' in df.columns else 'Company_Name'
    addr_col = 'Địa chỉ' if 'Địa chỉ' in df.columns else 'Address'
    web_col = 'Liên Hệ' if 'Liên Hệ' in df.columns else ('Web' if 'Web' in df.columns else 'Website')
    phone_col = 'SĐT' if 'SĐT' in df.columns else 'Phone'
    email_col = 'Email'

    if email_col not in df.columns:
        df[email_col] = ''
    if web_col not in df.columns:
        df[web_col] = ''
    if 'Google_Maps_URL' not in df.columns:
        df['Google_Maps_URL'] = ''
    if 'Maps_Status' not in df.columns:
        df['Maps_Status'] = ''

    # Lập chỉ mục phụ từ NO_FARM_COMB_0RAW.csv để lấy chính xác Thành phố & Mã bưu điện
    city_lookup = {}
    if RAW_LOOKUP_CSV.exists():
        try:
            df_raw = pd.read_csv(RAW_LOOKUP_CSV, encoding='utf-8-sig', dtype=str).fillna('')
            for _, r in df_raw.iterrows():
                c_name = r.get('Cong ty', '').strip().lower()
                c_city = r.get('Thanh pho', '').strip()
                c_zip = r.get('Ma buu dien', '').strip()
                if c_name:
                    city_lookup[c_name] = f"{c_zip} {c_city}".strip()
            print(f"[*] Đã nạp từ điển đối chiếu địa phương Proff/Gulesider: {len(city_lookup):,} bản ghi.")
        except Exception as e:
            print(f"[!] Không thể nạp bảng phụ RAW: {e}")

    # Nạp cache nếu có
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp cache: {len(cache):,} bản ghi đã được xử lý từ trước.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # Đồng bộ toàn bộ dữ liệu đã bóc tách từ cache vào DataFrame
    cached_sync_count = 0
    for idx in df.index:
        comp = str(df.at[idx, name_col]).strip()
        c_key = comp.lower()
        if c_key in cache:
            c_item = cache[c_key]
            if c_item.get('Email') and not clean_email(df.at[idx, email_col]):
                df.at[idx, email_col] = c_item['Email']
            if c_item.get('Web') and not str(df.at[idx, web_col]).strip():
                df.at[idx, web_col] = c_item['Web']
            if c_item.get('Phone') and not str(df.at[idx, phone_col]).strip():
                df.at[idx, phone_col] = c_item['Phone']
            if c_item.get('Maps_URL') and not str(df.at[idx, 'Google_Maps_URL']).strip():
                df.at[idx, 'Google_Maps_URL'] = c_item['Maps_URL']
            if c_item.get('Status') and not str(df.at[idx, 'Maps_Status']).strip():
                df.at[idx, 'Maps_Status'] = c_item['Status']
            cached_sync_count += 1
    print(f"[*] Đã đồng bộ dữ liệu của {cached_sync_count:,} bản ghi từ cache vào bảng dữ liệu.")

    # Đưa các bản ghi đã có email sẵn vào cache để BỎ QUA NGAY LẬP TỨC
    pre_existing_count = 0
    for idx, row in df.iterrows():
        comp = str(row[name_col]).strip()
        em = clean_email(row[email_col])
        wb = str(row.get(web_col, '')).strip()
        ph = clean_phone_no(row.get(phone_col, ''))
        c_key = comp.lower()
        if comp and em and em != 'nan' and c_key not in cache:
            cache[c_key] = {
                'Web': wb,
                'Email': em,
                'Phone': ph,
                'Address': str(row.get(addr_col, '')).strip(),
                'Maps_URL': '',
                'Status': 'PRE_EXISTING'
            }
            pre_existing_count += 1
            
    # Lọc danh sách các công ty CẦN LÀM GIÀU (chưa từng được xử lý trong cache và chưa có email)
    indices_to_enrich = []
    for idx in df.index:
        comp = str(df.at[idx, name_col]).strip()
        if not comp or is_blacklisted_company(comp):
            continue
        em = clean_email(df.at[idx, email_col])
        c_key = comp.lower()
        
        # NẾU ĐÃ CÓ EMAIL HOẶC ĐÃ ĐƯỢC XỬ LÝ TRONG CACHE -> BỎ QUA 100%, TUYỆT ĐỐI KHÔNG CÀO LẠI!
        if em or c_key in cache:
            continue
        indices_to_enrich.append(idx)

    total_need = len(indices_to_enrich)
    total_to_process = total_need if limit == 0 else min(limit, total_need)
    print(f"[*] Tổng doanh nghiệp trong tệp: {len(df):,}")
    print(f"[*] Đã hoàn tất từ hôm qua / có sẵn Email (tự động bỏ qua): {len(df) - total_need:,}")
    print(f"[*] Số doanh nghiệp CÒN LẠI cần làm giàu Maps & Web: {total_need:,}")
    if limit > 0:
        print(f"[*] Chế độ giới hạn (--limit {limit}): Sẽ xử lý {total_to_process:,} công ty.\n")
    else:
        print(f"[*] Sẽ xử lý nốt {total_to_process:,} công ty còn lại.\n")

    if total_to_process == 0:
        print("[*] 100% doanh nghiệp đã có email hoặc đã hoàn tất! Đang kiểm tra lưu file chuẩn hóa...")
        save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="nb-NO"
        )
        # Bỏ qua cookie consent Google
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        new_emails = 0
        new_webs = 0
        new_phones = 0

        for idx in indices_to_enrich:
            if processed >= total_to_process:
                break

            comp = str(df.at[idx, name_col]).strip()
            addr = str(df.at[idx, addr_col]).strip() if addr_col in df.columns else ""
            city = extract_city_from_address(addr)
            if not city and comp.lower() in city_lookup:
                city = city_lookup[comp.lower()]

            current_web = str(df.at[idx, web_col]).strip()
            current_email = clean_email(df.at[idx, email_col])
            current_phone = clean_phone_no(df.at[idx, phone_col])
            cache_key = comp.lower()

            # Nếu website là thư bạ/directory rác -> Xóa để Google Maps tìm web thật
            if current_web and any(bad in current_web.lower() for bad in BLACKLIST_DOMAINS):
                current_web = ""
                df.at[idx, web_col] = ""

            # Kiểm tra cache dự phòng
            if cache_key in cache:
                processed += 1
                c_item = cache[cache_key]
                print(f"[{processed:04d}/{total_to_process}] {comp[:32]:<32} | Cache Hit: {c_item.get('Status', 'OK')}")
                continue

            # Bước 1: Nếu đã có Web nhưng chưa có Email -> Quét trực tiếp website trước!
            if current_web and not current_email:
                em_found = crawl_site_for_emails(current_web)
                if em_found:
                    df.at[idx, email_col] = em_found
                    current_email = em_found
                    new_emails += 1
                    print(f"[{processed+1:04d}/{total_to_process}] {comp[:32]:<32} | [WEB DIRECT] -> Email: {em_found}")

            # Bước 2: Tìm kiếm Google Maps nếu chưa có Email hoặc chưa có Web/SĐT
            matched = False
            gmap_web = None
            gmap_phone = None
            gmap_addr = None
            gmap_url = None
            maps_status = "NOT_FOUND"

            if not current_email or not current_web or not current_phone:
                q_term = f"{comp} {city} Norway".strip() if city else f"{comp} Norway".strip()
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                    await asyncio.sleep(1.8)

                    # Kiểm tra Captcha
                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\n\a[CẢNH BÁO] Phát hiện Captcha trên Google Maps! Vui lòng bấm xác minh trên cửa sổ Chrome...\n")
                        await asyncio.sleep(10)

                    # Kiểm tra xem có bị đóng cửa vĩnh viễn không (Stengt for godt)
                    body_text = await page.content()
                    if "stengt for godt" in body_text.lower() or "permanently closed" in body_text.lower():
                        maps_status = "CLOSED"

                    # 1. Danh sách kết quả (Multiple places in sidebar)
                    items = await page.query_selector_all('a[href*="/maps/place/"]')
                    if items:
                        for item in items[:4]:
                            aria_label = await item.get_attribute('aria-label') or ""
                            is_ok, reason = is_valid_name_match(comp, aria_label)
                            if is_ok:
                                await item.click()
                                await asyncio.sleep(2.0)
                                matched = True
                                maps_status = "FOUND"
                                gmap_url = page.url
                                break
                    else:
                        # 2. Trang chi tiết địa điểm trực tiếp (Direct place panel)
                        title_elem = await page.query_selector('h1.DUwDvf')
                        if title_elem:
                            t_text = await title_elem.inner_text()
                            is_ok, reason = is_valid_name_match(comp, t_text)
                            if is_ok:
                                matched = True
                                maps_status = "FOUND"
                                gmap_url = page.url

                    if matched:
                        # Lấy website
                        web_btn = await page.query_selector('a[data-item-id="authority"]')
                        if web_btn:
                            cand_web = await web_btn.get_attribute('href')
                            if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                                gmap_web = cand_web

                        # Lấy số điện thoại
                        phone_btn = await page.query_selector('button[data-item-id*="phone:tel:"]')
                        if phone_btn:
                            p_data = await phone_btn.get_attribute('data-item-id')
                            if p_data:
                                gmap_phone = p_data.split('phone:tel:')[-1]

                        # Lấy địa chỉ chuẩn Maps
                        addr_btn = await page.query_selector('button[data-item-id="address"]')
                        if addr_btn:
                            aria_addr = await addr_btn.get_attribute('aria-label')
                            if aria_addr:
                                gmap_addr = aria_addr.replace('Adresse:', '').replace('Address:', '').strip()

                except Exception as e:
                    maps_status = "ERROR"

            # Cập nhật thông tin tìm được từ Google Maps
            if matched:
                if gmap_url:
                    df.at[idx, 'Google_Maps_URL'] = gmap_url
                if gmap_web and not current_web:
                    df.at[idx, web_col] = gmap_web
                    current_web = gmap_web
                    new_webs += 1
                if gmap_phone and not current_phone:
                    c_phone = clean_phone_no(gmap_phone)
                    df.at[idx, phone_col] = c_phone
                    current_phone = c_phone
                    new_phones += 1
                if gmap_addr and not addr:
                    df.at[idx, addr_col] = gmap_addr

                # Bước 3: Nếu vừa tìm thấy website từ Maps -> Quét tìm Email ngay!
                if current_web and not current_email:
                    em_found = crawl_site_for_emails(current_web)
                    if em_found:
                        df.at[idx, email_col] = em_found
                        current_email = em_found
                        new_emails += 1
                        print(f"[{processed+1:04d}/{total_to_process}] {comp[:32]:<32} | [MAPS -> WEB] -> Email: {em_found}")

            df.at[idx, 'Maps_Status'] = maps_status

            # Lưu vào cache
            cache[cache_key] = {
                'Web': current_web,
                'Email': current_email,
                'Phone': current_phone,
                'Address': str(df.at[idx, addr_col]).strip(),
                'Maps_URL': str(df.at[idx, 'Google_Maps_URL']).strip(),
                'Status': maps_status
            }

            processed += 1
            log_status = f"Maps: {maps_status}"
            if current_email:
                log_status += f" | Email: {current_email}"
            elif current_web:
                log_status += f" | Web: {current_web[:25]}"
            print(f"[{processed:04d}/{total_to_process}] {comp[:32]:<32} | {log_status}")

            # Lưu tăng dần sau mỗi cụm 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_emails = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)
                print(f"  >>> [AUTO-SAVE] Đã lưu tăng dần: {cur_emails} doanh nghiệp có email được đẩy lên đầu.")

        await browser.close()

    # Ghi nhận lần cuối
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
        
    total_with_email = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)

    print("\n" + "=" * 80)
    print(" HOÀN TẤT LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP NA UY BẰNG GOOGLE MAPS!")
    print(f" - Tổng doanh nghiệp đã xử lý trong đợt này : {processed:,}")
    print(f" - Website mới tìm thấy từ Maps             : {new_webs:,}")
    print(f" - SĐT mới bổ sung                          : {new_phones:,}")
    print(f" - Email B2B mới bóc tách thành công        : {new_emails:,}")
    print(f" - TỔNG CỘNG DOANH NGHIỆP CÓ EMAIL B2B (TOP): {total_with_email:,}")
    print(f" - File xuất làm giàu 1ENR                  : {OUTPUT_1ENR_CSV.name}")
    print(f" - File Cold Mail 20 cột (Đẩy mail lên đầu) : {OUTPUT_2COL_CSV.name}")
    print(f" - Đồng bộ tự động sang csdl_mlt & archive  : THÀNH CÔNG")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Google Maps & Web Email Enrichment for Norway Agriculture")
    parser.add_argument('--input', default=str(DEFAULT_INPUT_CSV), help="Tệp CSV đầu vào")
    parser.add_argument('--headless', action='store_true', help="Chạy ẩn trình duyệt Playwright (mặc định là hiển thị trực quan)")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty cần xử lý (0 = toàn bộ)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(input_csv=args.input, headless=args.headless, limit=args.limit))

if __name__ == '__main__':
    main()

