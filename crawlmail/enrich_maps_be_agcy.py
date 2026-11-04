# -*- coding: utf-8 -*-
"""
GOOGLE MAPS & WEB EMAIL ENRICHMENT - BELGIUM HR & RECRUITMENT AGENCIES
Input Dataset: BE_AGCY_COMB_0RAW.csv (Merged Federgon & KBO Enterprises)
Output Datasets:
1. BE_AGCY_GMAP_1ENR.csv (Full database with enriched Maps, Phone, Web & Email)
2. BE_AGCY_GMAP_2COL.csv (Cold Mail 20-column format, 100% companies with email pushed to top)

Tuân thủ toàn bộ quy chuẩn tại GEMINI.md, data-standards, crawl-mail và enrich-maps:
1. BỎ QUA 100% DOANH NGHIỆP ĐÃ CÓ EMAIL: Tuyệt đối không cào lại các công ty đã có email. Chỉ cào mới cho các công ty chưa có email.
2. Smart & Strict Name Matching (Exact, Delimiters, Substring, NFKD accents, strip Belgian legal forms NV, BV, BVBA, SRL, SA...).
3. Số điện thoại chuẩn hóa có nháy đơn (') ở đầu: phone = f"'{phone}".
4. Chấm điểm email B2B (score_email_b2b) tối ưu cho Manpower Agency tại Bỉ:
   - Ưu tiên Nhân sự / Việc làm (jobs@, recruitment@, recrutement@, career@, hr@, rh@, emploi@, sollicitatie@, cv@) +50
   - Ưu tiên Ban Giám Đốc / Lãnh đạo (ceo@, director@, directeur@, directie@, manager@, bestuur@) +45
   - Ưu tiên Cổng liên hệ chính thức (info@, contact@, office@, welcome@, agence@) +40
   - Ưu tiên trùng domain website (+50đ), ưu tiên tên miền .be (+25đ)
   - Lọc bỏ 100% mail rác/template (youremail@, gebruiker@domein.com, example@, sentry, wix...).
   - Chỉ giữ DUY NHẤT 1 email giá trị nhất.
5. Bật trình duyệt trực quan Playwright (headless=False, viewport 1280x800) kèm chuông báo \\a khi gặp Captcha.
6. Lưu tăng dần (Incremental Checkpoint) mỗi 5 dòng & Checkpoint JSON để Resume 100%.
7. Danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre).
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

DEFAULT_INPUT_CSV = ROOT_DIR / "BE_AGCY_COMB_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "BE_AGCY_GMAP_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "BE_AGCY_GMAP_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_agcy.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'nl-BE,nl;q=0.9,fr-BE;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Blacklist danh bạ, mạng xã hội, cổng thông tin (không lấy làm web công ty)
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'goudengids.be', 'pagesdor.be', 'trendstop.knack.be', 'infobel.com', 'kompass.com',
    'staatsbladmonitor.be', 'ejustice.just.fgov.be', 'kbopub.economie.fgov.be',
    'wikipedia.org', 'vdab.be', 'actiris.brussels', 'leforem.be', 'sentry.io',
    'wixpress.com', 'dnb.com', 'zoominfo.com', 'talentbusinesspartners.com', 'federgon.be',
    'apd-gba.be', 'kinamo.be', 'cookiebot.com'
]

# Rule #12: Danh sách đen doanh nghiệp cố định
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

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""

def clean_phone(p):
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip()
    return s if s.startswith("'") else f"'{s}"

def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching: exact, brackets, delimiters, or long substring"""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(query_name))
    c_raw = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(candidate_name))
    
    q = unicodedata.normalize('NFKD', q_raw).lower()
    q = ''.join(c for c in q if not unicodedata.combining(c))
    c = unicodedata.normalize('NFKD', c_raw).lower()
    c = ''.join(c for c in c if not unicodedata.combining(c))
    
    # Strip Belgian legal forms
    legal_forms = [
        'nv', 'bvba', 'bv', 'sprl', 'srl', 'sa', 'scrl', 'cvba', 'vof', 'snc',
        'commv', 'scs', 'gmbh', 'se', 'asbl', 'vzw', 'ebvba', 'holding', 'group'
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
        
    # Check substring match
    if len(q) >= 4 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    # Check token overlap
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if len(q_tokens) > 1 and len(q_tokens.intersection(c_tokens)) >= len(q_tokens) * 0.7:
        return True, "TOKEN_MATCH"
        
    return False, "NO_MATCH"

def clean_email(email):
    """
    Làm sạch email triệt để theo quy chuẩn bắt buộc data-standards & GEMINI.md:
    - unquote URL encoding (%20...)
    - Xóa sạch \u00a0, \xa0, &nbsp;, %20, \u200b, \ufeff, \u202f, \u3000, zero-width space
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

def score_email_b2b(email, domain=""):
    """Chấm điểm email B2B cho Manpower Agency theo chuẩn GEMINI.md & data-standards"""
    e = clean_email(email)
    if not e:
        return -1
    
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
        
    # Loại bỏ mail template rác / web developer demo (Anh, Pháp, Hà Lan, Bỉ)
    junk_domains = [
        'sentry', 'wixpress', 'wix.com', 'example.com', 'exemple.com', 'domain.com',
        'domaine.com', 'email.com', 'address.com', 'test.com', 'voorbeeld.nl', 'voorbeeld.be',
        'apd-gba.be', 'kinamo.be', 'cookiebot.com', 'squarespace.com', 'wordpress.com',
        'domein.com', 'uwbedrijf.be', 'jouwbedrijf.be'
    ]
    if any(bad in d for bad in junk_domains):
        return -1
        
    junk_users = [
        'sentry', 'youremail', 'your-email', 'yourname', 'votre.email', 'votre-email',
        'votrenom', 'sample', 'no-reply', 'donotreply', 'someone', 'john.doe',
        'privacy', 'gdpr', 'abuse', 'postmaster', 'user', 'name', 'uw-email', 'uwnaam',
        'gebruiker'
    ]
    if any(bad in u for bad in junk_users):
        return -1
    if u in ['mail', 'email'] and (d in ['email.com', 'address.com', 'domein.com'] or u == d.split('.')[0]):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.be'):
        score += 25

    # Ưu tiên số 1: Tuyển dụng / Nhân sự / Việc làm (+50đ)
    if u in ['jobs', 'recruitment', 'recrutement', 'career', 'careers', 'carriere', 'carrieres', 'hr', 'rh', 'emploi', 'emplois', 'sollicitatie', 'selectie', 'candidature', 'cv', 'work', 'talent']:
        score += 50
    # Ưu tiên số 2: Ban Giám Đốc / Lãnh đạo (+45đ)
    elif u in ['ceo', 'director', 'directeur', 'directie', 'manager', 'bestuur', 'sales', 'commercial', 'managing']:
        score += 45
    # Ưu tiên số 3: Cổng liên hệ chính thức / Thông tin (+40đ)
    elif u in ['info', 'contact', 'office', 'welcome', 'reception', 'recepcia', 'accueil', 'agence', 'agency', 'kantoor', 'admin']:
        score += 40
    # Email cá nhân đích danh (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # Email kỹ thuật / hỗ trợ chung (+5đ)
    elif u in ['support', 'helpdesk', 'servis', 'facturatie', 'facturation']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    best = max(valid, key=lambda e: score_email_b2b(e, domain))
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
        with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""

DOMAIN_EMAIL_CACHE = {}

def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor per Skill crawl-mail"""
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith('http'):
        web_url = f"https://{web_url}"
    web_url = web_url.rstrip('/')
    if any(bad in web_url.lower() for bad in BLACKLIST_DOMAINS):
        return ""
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    
    # Check in-memory domain cache first
    if root in DOMAIN_EMAIL_CACHE:
        return DOMAIN_EMAIL_CACHE[root]
        
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
    if not home_html:
        return ""
        
    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
        ce = clean_email(m)
        if ce and '@' in ce:
            found.add(ce)
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
        dec = clean_email(decode_cf(cf))
        if dec and '@' in dec:
            found.add(dec)
    for em in EMAIL_REGEX.findall(home_html):
        ce = clean_email(em)
        if ce and score_email_b2b(ce, root) > 0:
            found.add(ce)
            
    best_home = select_best_email(found, root)
    if best_home and score_email_b2b(best_home, root) >= 75:
        DOMAIN_EMAIL_CACHE[root] = best_home
        return best_home

    # 2. Extract real DOM contact links
    try:
        soup = BeautifulSoup(home_html, 'html.parser')
        dom_contact_links = []
        contact_keywords = [
            'contact', 'contacteer', 'over-ons', 'overons', 'wie-zijn-we',
            'vacatures', 'jobs', 'werken-bij', 'team', 'locaties', 'kantoren',
            'contactez-nous', 'a-propos', 'qui-sommes-nous', 'emplois',
            'recrutement', 'carrieres', 'offres-d-emploi', 'equipe', 'agences',
            'about-us', 'careers', 'about'
        ]
        for a in soup.find_all('a', href=True):
            h = a['href'].lower()
            txt = a.get_text().lower()
            if any(k in h or k in txt for k in contact_keywords):
                full = urllib.parse.urljoin(web_url, a['href'])
                if full not in dom_contact_links and '#' not in a['href'] and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                    dom_contact_links.append(full)
                    
        for cl in dom_contact_links[:5]:
            chtml = fetch_html_stealth(cl)
            if not chtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                ce = clean_email(m)
                if ce and '@' in ce:
                    found.add(ce)
            for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                dec = clean_email(decode_cf(cf))
                if dec and '@' in dec:
                    found.add(dec)
            for em in EMAIL_REGEX.findall(chtml):
                ce = clean_email(em)
                if ce and score_email_b2b(ce, root) > 0:
                    found.add(ce)
            if found and any(score_email_b2b(e, root) >= 60 for e in found):
                break
    except Exception:
        pass

    # 3. Fallback Guess Paths
    if not found:
        guess_paths = [
            f"{root}/nl/contact", f"{root}/fr/contact", f"{root}/contact",
            f"{root}/nl/over-ons", f"{root}/fr/a-propos", f"{root}/jobs"
        ]
        for gp in guess_paths:
            ghtml = fetch_html_stealth(gp)
            if not ghtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                ce = clean_email(m)
                if ce and '@' in ce:
                    found.add(ce)
            for em in EMAIL_REGEX.findall(ghtml):
                ce = clean_email(em)
                if ce and score_email_b2b(ce, root) > 0:
                    found.add(ce)
            if found:
                break

    best_em = select_best_email(found, root)
    DOMAIN_EMAIL_CACHE[root] = best_em
    return best_em

def save_and_reorder_files(df_full, output_1enr, output_2col):
    """
    Lưu 2 file chuẩn hóa:
    - 1ENR: CSDL đầy đủ tất cả cột.
    - 2COL: Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu danh sách!
    """
    df = df_full.copy()
    
    if 'Phone' in df.columns:
        df['Phone'] = df['Phone'].apply(clean_phone)
    if 'SĐT' in df.columns:
        df['SĐT'] = df['SĐT'].apply(clean_phone)
    if 'Email' in df.columns:
        df['Email'] = df['Email'].apply(clean_email)

    em_col = 'Email'
    has_em = df[df[em_col].notna() & (df[em_col].astype(str).str.strip() != '') & (df[em_col].astype(str).str.strip() != 'nan')].copy()
    # Khử trùng lặp Email: Mỗi email chỉ gán cho 1 doanh nghiệp duy nhất trong tệp Cold Mail
    has_em = has_em.drop_duplicates(subset=[em_col], keep='first')
    
    no_em = df[df[em_col].isna() | (df[em_col].astype(str).str.strip() == '') | (df[em_col].astype(str).str.strip() == 'nan')].copy()
    cname_col = 'Company_Name' if 'Company_Name' in df.columns else 'Công ty'
    has_names = set(has_em[cname_col].str.strip().str.lower())
    no_em = no_em[~no_em[cname_col].str.strip().str.lower().isin(has_names)]
    
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

    # 3. Tạo file 2COL (Chuẩn 20 cột Cold Mail)
    col20_rows = []
    for idx, row in df_sorted.iterrows():
        cname = str(row.get('Company_Name', '') or row.get('Công ty', '')).strip()
        phone = clean_phone(row.get('Phone', '') or row.get('SĐT', ''))
        web = str(row.get('Website', '') or row.get('Liên Hệ', '')).strip()
        email = clean_email(row.get('Email', ''))
        addr = str(row.get('Address', '') or row.get('Địa chỉ', '')).strip()
        city = str(row.get('City', '') or row.get('Thành phố', '')).strip()
        full_addr = f"{addr}, {city}".strip(', ') if city and city not in addr else addr

        r20 = {
            'No.': idx + 1,
            'Công ty': cname,
            'Chức danh': 'Director / Zaakvoerder / Gérant',
            'Người liên hệ': str(row.get('Người liên hệ', '')).strip(),
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': 'Uitzendbureau / Agence de recrutement (Belgium)'
        }
        col20_rows.append(r20)

    df_2col = pd.DataFrame(col20_rows, columns=COL_20_HEADERS)
    df_2col.to_csv(output_2col, index=False, encoding='utf-8-sig')
    return len(has_em)

async def run_enrichment(input_csv, headless=False, limit=0):
    print("=" * 80)
    print(" GOOGLE MAPS & WEB EMAIL ENRICHMENT - BELGIUM HR & RECRUITMENT AGENCIES")
    print("=" * 80)
    print(f"[*] Input File   : {input_csv}")
    print(f"[*] Output 1ENR  : {OUTPUT_1ENR_CSV}")
    print(f"[*] Output 2COL  : {OUTPUT_2COL_CSV}")
    print(f"[*] Cache JSON   : {CACHE_PATH}")
    print(f"[*] Trình duyệt  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False - Quan sát tiến độ)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(input_csv):
        print(f"[ERROR] Không tìm thấy file: '{input_csv}'")
        return

    df = pd.read_csv(input_csv, encoding='utf-8-sig', dtype=str).fillna('')
    
    name_col = 'Company_Name' if 'Company_Name' in df.columns else 'Công ty'
    city_col = 'City' if 'City' in df.columns else 'Thành phố'
    web_col = 'Website' if 'Website' in df.columns else 'Liên Hệ'
    phone_col = 'Phone' if 'Phone' in df.columns else 'SĐT'
    email_col = 'Email'

    if email_col not in df.columns:
        df[email_col] = ''
    if 'Google_Maps_URL' not in df.columns:
        df['Google_Maps_URL'] = ''

    # Đọc cache nếu có
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp cache: {len(cache)} bản ghi đã được xử lý từ trước.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # Đưa các bản ghi đã có email sẵn vào cache để BỎ QUA NGAY LẬP TỨC
    pre_existing_count = 0
    for idx, row in df.iterrows():
        comp = str(row[name_col]).strip()
        em = clean_email(row[email_col])
        wb = str(row[web_col]).strip()
        ph = clean_phone(row[phone_col])
        c_key = comp.lower()
        if comp and em and em != 'nan' and c_key not in cache:
            cache[c_key] = {
                'Web': wb,
                'Email': em,
                'Phone': ph
            }
            pre_existing_count += 1

    # LỌC DUY NHẤT CÁC CÔNG TY CHƯA CÓ EMAIL ĐỂ CÀO MỚI!
    # TUYỆT ĐỐI BỎ QUA 100% CÁC CÔNG TY ĐÃ CÓ EMAIL!
    indices_to_enrich = []
    for idx, row in df.iterrows():
        comp = str(row[name_col]).strip()
        if not comp or is_blacklisted_company(comp):
            continue
        em = clean_email(row[email_col])
        c_key = comp.lower()
        
        # Nếu dòng đã có email hoặc cache đã có email -> BỎ QUA HOÀN TOÀN!
        if em or (c_key in cache and cache[c_key].get('Email')):
            # Đồng bộ email từ cache vào dataframe nếu df chưa có
            if not em and c_key in cache and cache[c_key].get('Email'):
                df.at[idx, email_col] = cache[c_key]['Email']
            continue
        indices_to_enrich.append(idx)

    total_need = len(indices_to_enrich)
    total_to_process = total_need if limit == 0 else min(limit, total_need)
    print(f"[*] Tổng doanh nghiệp trong tệp : {len(df)}")
    print(f"[*] Đã có sẵn Email (BỎ QUA 100%): {len(df) - total_need}")
    print(f"[*] Số công ty CHƯA CÓ EMAIL CẦN CÀO MỚI: {total_need}")
    if limit > 0:
        print(f"[*] Chế độ giới hạn (--limit {limit}): Sẽ cào mới {total_to_process} công ty.\n")
    else:
        print(f"[*] Sẽ cào mới toàn bộ {total_to_process} công ty.\n")

    if total_to_process == 0:
        print("[*] 100% công ty đã có email hoặc đã quét xong! Đang lưu chuẩn hóa...")
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
            locale="nl-BE"
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
            city = str(df.at[idx, city_col]).strip() if city_col in df.columns and pd.notna(df.at[idx, city_col]) else ""
            current_web = str(df.at[idx, web_col]).strip()
            current_email = clean_email(df.at[idx, email_col])
            current_phone = clean_phone(df.at[idx, phone_col])
            cache_key = comp.lower()

            # Nếu website là thư bạ rác -> Xóa để Google Maps tìm web thật
            if current_web and any(bad in current_web.lower() for bad in BLACKLIST_DOMAINS):
                current_web = ""
                df.at[idx, web_col] = ""

            # Kiểm tra cache
            if cache_key in cache:
                c_item = cache[cache_key]
                if c_item.get('Email') and not current_email:
                    df.at[idx, email_col] = c_item['Email']
                if c_item.get('Web') and not current_web:
                    df.at[idx, web_col] = c_item['Web']
                if c_item.get('Phone') and not current_phone:
                    df.at[idx, phone_col] = c_item['Phone']

                current_web = str(df.at[idx, web_col]).strip()
                current_email = clean_email(df.at[idx, email_col])
                current_phone = clean_phone(df.at[idx, phone_col])

                # Nếu cache đã có email -> Bỏ qua ngay lập tức!
                if current_email:
                    processed += 1
                    print(f"[{processed:04d}/{total_to_process}] {comp[:32]:<32} | Cache Hit: {current_email}")
                    continue

            # Bước 1: Nếu đã có Web nhưng chưa có Email -> Quét trực tiếp website trước!
            if current_web and not current_email:
                em_found = crawl_site_for_emails(current_web)
                if em_found:
                    df.at[idx, email_col] = em_found
                    current_email = em_found
                    new_emails += 1
                    print(f"[{processed+1:04d}/{total_to_process}] {comp[:32]:<32} | [WEB DIRECT] -> Email: {em_found}")

            # Bước 2: NẾU VẪN CHƯA CÓ EMAIL -> MỚI TÌM KIẾM GOOGLE MAPS!
            matched = False
            gmap_web = None
            gmap_phone = None
            gmap_url = None

            if not current_email:
                q_term = f"{comp} {city} Belgium".strip() if city else f"{comp} Belgium".strip()
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                    await asyncio.sleep(1.8)

                    # Kiểm tra Captcha
                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\n\\a[CẢNH BÁO] Phát hiện Captcha trên Google Maps! Vui lòng bấm xác minh trên cửa sổ Chrome...\n")
                        await asyncio.sleep(10)

                    # 1. Danh sách kết quả (Multiple places)
                    items = await page.query_selector_all('a[href*="/maps/place/"]')
                    if items:
                        for item in items[:4]:
                            aria_label = await item.get_attribute('aria-label') or ""
                            is_ok, reason = is_valid_name_match(comp, aria_label)
                            if is_ok:
                                await item.click()
                                await asyncio.sleep(2.0)
                                matched = True
                                gmap_url = page.url
                                break
                    else:
                        # 2. Trang chi tiết địa điểm trực tiếp (Direct place panel)
                        title_elem = await page.query_selector('h1.DUwDvf')
                        if title_elem:
                            t_text = await title_elem.inner_text()
                            is_ok, reason = is_valid_name_match(comp, t_text)
                            matched = is_ok
                            gmap_url = page.url

                    if matched:
                        # Lấy website
                        web_btn = await page.query_selector('a[data-item-id="authority"]')
                        if web_btn:
                            cand_web = await web_btn.get_attribute('href')
                            if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                                gmap_web = cand_web

                        # Lấy số điện thoại
                        phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                        if phone_btn:
                            p_attr = await phone_btn.get_attribute('data-item-id')
                            if p_attr and 'phone:tel:' in p_attr:
                                cand_phone = p_attr.replace('phone:tel:', '').strip()
                                gmap_phone = clean_phone(cand_phone)
                except Exception:
                    try:
                        if page.is_closed():
                            page = await context.new_page()
                    except Exception:
                        pass

                # Cập nhật thông tin từ Maps
                if gmap_web and not current_web:
                    df.at[idx, web_col] = gmap_web
                    current_web = gmap_web
                    new_webs += 1
                if gmap_phone and not current_phone:
                    df.at[idx, phone_col] = gmap_phone
                    current_phone = gmap_phone
                    new_phones += 1
                if gmap_url:
                    df.at[idx, 'Google_Maps_URL'] = gmap_url

                # Bước 3: Nếu vừa tìm thấy Web mới từ Maps -> Quét email ngay!
                if gmap_web and not current_email:
                    em_found = crawl_site_for_emails(gmap_web)
                    if em_found:
                        df.at[idx, email_col] = em_found
                        current_email = em_found
                        new_emails += 1

            # Lưu vào cache bộ nhớ
            cache[cache_key] = {
                'Web': current_web,
                'Email': current_email,
                'Phone': current_phone,
                'Maps_URL': str(df.at[idx, 'Google_Maps_URL']).strip()
            }

            processed += 1
            status_tag = f"Maps:{'✓' if matched else '✗'} | Web:{'✓' if current_web else '✗'} | Email:{current_email if current_email else '✗'}"
            print(f"[{processed:04d}/{total_to_process}] {comp[:32]:<32} | {status_tag}")

            # Lưu tăng dần mỗi 5 công ty (Incremental Checkpoint)
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                emails_count = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)
                print(f"--- [CHECKPOINT] Đã lưu tăng dần: {processed} công ty. Có Email: {emails_count} | Mới: +{new_emails} mail, +{new_webs} web, +{new_phones} phone ---")

        # Lưu lần cuối khi hoàn tất
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        total_emails = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)

        print("\n" + "=" * 80)
        print(" HOÀN THÀNH LÀM GIÀU DỮ LIỆU BẰNG GOOGLE MAPS & WEB EMAIL!")
        print("=" * 80)
        print(f"[*] Tổng doanh nghiệp đã xử lý trong lượt: {processed}")
        print(f"[*] Tổng doanh nghiệp có Email: {total_emails}")
        print(f"[*] File kết quả 1ENR          : {OUTPUT_1ENR_CSV}")
        print(f"[*] File Cold Mail 2COL        : {OUTPUT_2COL_CSV} (100% email đã đẩy lên đầu!)")
        print("=" * 80)

        await browser.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Belgium HR Agencies via Google Maps & Web Email")
    parser.add_argument('--input', default=str(DEFAULT_INPUT_CSV), help="Đường dẫn file CSV đầu vào")
    parser.add_argument('--headless', action='store_true', help="Chạy ngầm không mở cửa sổ Chrome")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty cần xử lý (0 = tất cả)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(input_csv=args.input, headless=args.headless, limit=args.limit))
