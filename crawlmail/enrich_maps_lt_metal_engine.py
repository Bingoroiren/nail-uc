# -*- coding: utf-8 -*-
"""
EMAIL ENRICHMENT & COLD MAIL FORMATTER - LITHUANIAN METAL ENTERPRISES (LT_METL_GMAP)
====================================================================================
Input:  LT_METL_GMAP_0RAW.csv
Output: LT_METL_GMAP_1ENR.csv + LT_METL_GMAP_2COL.csv + LT_METL_GMAP_ONLY_EMAILS_READY.csv
Rules:  GEMINI.md (Rule 1, 2, 3, 5, 7, 10, 11, 12)
"""

import os
import sys
import re
import ssl
import json
import time
import shutil
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

# Ensure UTF-8 console output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV_PATH = ROOT_DIR / "LT_METL_GMAP_0RAW.csv"
OUTPUT_1ENR_PATH = ROOT_DIR / "LT_METL_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_METL_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_METL_GMAP_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_metal_gmap.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_lt(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Litva có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ""
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith('370'):
        pass
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370') and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"

def clean_email(email_str):
    """Rule 3: Làm sạch triệt để ký tự lạ, %20, \\u00a0, zero-width space"""
    if not email_str or not isinstance(email_str, str):
        return ""
    em = urllib.parse.unquote(str(email_str).strip().lower())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        em = em.replace(bad, '')
    if em.startswith('20') and '@' in em and not em.startswith('202'):
        em = em[2:]
    em = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', em)
    return em.strip()

def decode_cloudflare_email(cf_hex):
    """Giải mã email bảo vệ bởi Cloudflare email-protection"""
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return clean_email(email)
    except Exception:
        return ""

def score_email_b2b_lt(email, domain=""):
    """Rule 3: Chấm điểm email B2B cho thị trường Kim loại Litva"""
    e = clean_email(email)
    if not e or '@' not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1

    bad_domains = ['example.com', 'domain.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
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
        score += 35

    # Ưu tiên nhân sự / tuyển dụng
    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    # Ưu tiên ban giám đốc / lãnh đạo
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'gamyba']:
        score += 45
    # Cổng liên hệ chính thức B2B
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
    # Bộ phận kinh doanh / bán hàng
    elif u in ['komercija', 'pardavimai', 'uzsakymai', 'sales', 'prekyba']:
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'inbox.lt', 'one.lt']:
        score += 10
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))

# SSL Context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'lt,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

def fetch_html(url, timeout=7):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return None

def crawl_website_for_email(site_url):
    """Bóc tách email đa tầng từ website doanh nghiệp kim loại Litva"""
    if not site_url or not isinstance(site_url, str):
        return ""
    u_str = site_url.strip()
    if not u_str.startswith('http'):
        u_str = 'http://' + u_str

    try:
        parsed = urllib.parse.urlparse(u_str)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        netloc = parsed.netloc
    except Exception:
        return ""

    # Bỏ qua các mạng xã hội và danh bạ trung gian
    if any(k in netloc.lower() for k in ['facebook.com', 'instagram.com', 'linkedin.com', 'google.com', 'yellowpages', 'rekvizitai']):
        return ""

    found_emails = set()

    def parse_page(html):
        if not html:
            return
        soup = BeautifulSoup(html, 'html.parser')
        
        # Cloudflare decoded emails
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if '/cdn-cgi/l/email-protection#' in href:
                cf_hex = href.split('#')[-1]
                dec = decode_cloudflare_email(cf_hex)
                if dec:
                    found_emails.add(dec)
            elif href.startswith('mailto:'):
                dec = clean_email(href.replace('mailto:', ''))
                if dec:
                    found_emails.add(dec)
                    
        # Regex emails trong HTML
        for em in EMAIL_REGEX.findall(html):
            clean_em = clean_email(em)
            if clean_em:
                found_emails.add(clean_em)

    # 1. Quét trang chủ
    home_html = fetch_html(u_str)
    if home_html:
        parse_page(home_html)
        best = select_best_email(found_emails, netloc)
        if best and score_email_b2b_lt(best, netloc) >= 50:
            return best

    # 2. Quét các subpaths tiếng Litva trọng điểm
    sub_paths = [
        '/kontaktai', '/kontaktai.html', '/apie-mus', '/apie',
        '/rekvizitai', '/karjera', '/darbas', '/contacts'
    ]

    internal_links = set()
    if home_html:
        soup_h = BeautifulSoup(home_html, 'html.parser')
        for a in soup_h.find_all('a', href=True):
            href = a['href'].strip()
            for sp in sub_paths:
                if sp in href.lower():
                    full_u = urllib.parse.urljoin(base_domain, href)
                    if full_u.startswith(base_domain):
                        internal_links.add(full_u)

    targets = list(internal_links)[:4] if internal_links else [f"{base_domain.rstrip('/')}{sp}" for sp in sub_paths[:3]]

    for sub_u in targets:
        sub_html = fetch_html(sub_u)
        if sub_html:
            parse_page(sub_html)
            best = select_best_email(found_emails, netloc)
            if best and score_email_b2b_lt(best, netloc) >= 50:
                return best

    return select_best_email(found_emails, netloc)

def export_and_sync_files(df):
    """Xuất định dạng Master 1ENR và Cold Mail 20 cột, đẩy 100% email lên đầu"""
    df_out = df.copy()
    if 'Name' in df_out.columns:
        df_out = df_out[~df_out['Name'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['Phone'] = df_out['Phone'].apply(clean_phone_lt)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # Đẩy 100% email lên đầu (Rule 3)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Name', '')).strip()
        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('Phone', ''))
        addr_val = str(r.get('Address', '')).strip()
        cat_val = str(r.get('Category', 'Metalo apdirbimas ir gaminiai')).strip()

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': 'Vadovas',
            'Người liên hệ': '',
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': addr_val,
            'Lương': '',
            'Ngày đăng': '',
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

    for extra_d in [CSDL_DIR, ARCHIVE_DIR]:
        extra_d.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_2COL_PATH, extra_d / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_d / OUTPUT_READY_PATH.name)
            shutil.copy2(OUTPUT_1ENR_PATH, extra_d / OUTPUT_1ENR_PATH.name)
        except Exception:
            pass

    return len(has_em)

def run_enrichment():
    print("=" * 80)
    print("🌟 BÓC TÁCH EMAIL & XUẤT COLD MAIL KIM LOẠI LITVA (LT_METL_GMAP)")
    print(f"   - File nguồn thô: {INPUT_CSV_PATH.name}")
    print(f"   - File 1ENR     : {OUTPUT_1ENR_PATH.name}")
    print(f"   - File 2COL     : {OUTPUT_2COL_PATH.name}")
    print(f"   - File READY    : {OUTPUT_READY_PATH.name}")
    print("=" * 80 + "\n")

    if not INPUT_CSV_PATH.exists():
        print(f"[!] Không tìm thấy tệp {INPUT_CSV_PATH.name}. Vui lòng chạy scraper cào Maps trước!")
        return

    df = pd.read_csv(INPUT_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    if 'Email' not in df.columns:
        df['Email'] = ''

    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} bản ghi từ checkpoint cache.")
        except Exception:
            pass

    processed = 0
    newly_found = 0

    for idx, row in df.iterrows():
        comp = str(row['Name']).strip()
        web = str(row.get('Website', '')).strip()
        cache_key = web if web else comp

        processed += 1

        # 1. Kiểm tra cache
        if cache_key in cache:
            c_email = cache[cache_key]
            if c_email:
                df.at[idx, 'Email'] = c_email
            continue

        if not web:
            cache[cache_key] = ""
            continue

        print(f"[{processed}/{len(df)}] 🌐 Quét email: {comp} -> {web}")
        found_em = crawl_website_for_email(web)

        if found_em:
            df.at[idx, 'Email'] = found_em
            cache[cache_key] = found_em
            newly_found += 1
            print(f"    🎯 [+] TÌM THẤY EMAIL: {found_em}")
        else:
            cache[cache_key] = ""
            print("    [-] Không tìm thấy email trên website.")

        # Lưu checkpoint mỗi 10 công ty (Rule 5)
        if processed % 10 == 0:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cur_em = export_and_sync_files(df)
            print(f"    [*] Đã lưu Checkpoint ({processed}/{len(df)} | Tổng Email: {cur_em:,} | +{newly_found} mới)")

        time.sleep(0.3)

    # Lưu lần cuối
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total_em = export_and_sync_files(df)

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH BÓC TÁCH EMAIL & CHUẨN HÓA COLD MAIL KIM LOẠI LITVA!")
    print(f"   - Tổng số doanh nghiệp: {len(df):,}")
    print(f"   - Doanh nghiệp có EMAIL: {total_em:,} ({total_em*100/len(df):.1f}%)")
    print(f"   - Email mới tìm được  : +{newly_found:,}")
    print(f"   - File Cold Mail 20 cột: {OUTPUT_2COL_PATH.name} (Đã đẩy 100% email lên đầu)")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    run_enrichment()

