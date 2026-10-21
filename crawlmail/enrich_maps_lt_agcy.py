# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN RECRUITMENT & EMPLOYMENT AGENCIES
Target dataset: LT_AGCY_REKV_2COL.csv (Rekvizitai Lithuania Manpower Agencies)

Đặc điểm:
- Tự động lọc các công ty CHƯA CÓ EMAIL để tìm kiếm trên Google Maps & Website.
- So khớp tên nghiêm ngặt (Strict Name Matching) khử các loại hình pháp lý UAB, MB, VšĮ...
- Bóc tách Website và Số điện thoại (+370...) từ Google Maps.
- Quét Email B2B đa tầng: ưu tiên tối cao email đuôi .lt (+60đ), darbas@, karjera@, cv@, hr@, vadovas@, info@...
- Chế độ trực quan Chrome (headless=False) có chuông báo \a khi gặp Captcha, tự động vượt Cookie Consent.
- Thay thế hoàn toàn page.wait_for_timeout bằng asyncio.sleep và tự động khôi phục tab nếu Chrome bị đóng.
- Lưu tăng dần (Incremental Checkpoint) mỗi 5 công ty, đẩy 100% doanh nghiệp có Email lên đầu tệp CSV.

Đầu ra:
1. LT_AGCY_REKV_2COL.csv (Thư mục gốc)
2. csdl_mlt/LT_AGCY_REKV_2COL.csv
3. csdl_mlt/LT_AGCY_REKV_1ENR.csv
"""

import sys
import os
import re
import ssl
import json
import time
import asyncio
import argparse
import urllib.parse
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV_ROOT = ROOT_DIR / "LT_AGCY_REKV_2COL.csv"
TARGET_CSV_CSDL = ROOT_DIR / "csdl_mlt" / "LT_AGCY_REKV_2COL.csv"
TARGET_1ENR_CSDL = ROOT_DIR / "csdl_mlt" / "LT_AGCY_REKV_1ENR.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_agcy.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "lt_agcy_maps_profile"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Blacklist danh bạ, mạng xã hội, cổng thông tin (không lấy làm web công ty)
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'statyba.lt', 'info.lt', 'visalietuva.lt', 'imones.lt', 'rekvizitai.vz.lt', 'rekvizitai.lt',
    'b2lithuania.com', 'cvbankas.lt', 'cvonline.lt', 'wikipedia.org', 'delfi.lt', '15min.lt', 'lrt.lt',
    'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'scoris.lt', 'infoin.lt', 'cr.lt',
    'creditinfo.lt', 'verslas.lt', 'madeinvilnius.lt', 'lrytas.lt', 'alfa.lt', 'tv3.lt',
    'registrucentras.lt', 'vmi.lt', 'sodra.lt', '1551.lt', 'tax.lt', 'buhalteredaiva.lt',
    'geltoni.lt', 'fsaskaita.lt', 'jars.lt', 'spec.lt', 'saskaitos.lt', 'balticlei.lt',
    'infoplius.lt', 'business-baltics.com', 'imoniukatalogai.lt', '1588.lt',
    'imoniugidas.lt', 'imoniubaze.lt', 'versloakcija.lt', 'expo.lt', 'ltkatalogas.lt',
    'cvmarket.lt', 'rekv.lt', 'proton.me', 'lovejob.lt', 'tinklalapiai.lt'
]

# Danh sách công ty loại trừ khỏi danh sách kết nối / tuyển dụng
EXCLUDED_COMPANIES = [
    'biliarta'
]

JUNK_EMAIL_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@'
]

LT_CITIES = [
    "Vilnius", "Kaunas", "Klaipėda", "Šiauliai", "Panevėžys", "Alytus",
    "Marijampolė", "Mažeikiai", "Jonava", "Utena", "Kėdainiai", "Telšiai",
    "Visaginas", "Tauragė", "Ukmergė", "Plungė", "Šilutė", "Kretinga",
    "Radviliškis", "Druskininkai", "Palanga", "Gargždai", "Rokiškis",
    "Biržai", "Elektrėnai", "Garliava", "Jurbarkas", "Vilkaviškis",
    "Raseiniai", "Anykščiai", "Lentvaris", "Grigiškės", "Prienai",
    "Joniškis", "Kelmė", "Varėna", "Kaišiadorys", "Pasvalys", "Kupiškis",
    "Zarasai", "Skuodas", "Kazlų Rūda", "Širvintos", "Molėtai", "Šakiai",
    "Šalčininkai", "Ignalina", "Kybartai", "Pabradė", "Neringa", "Nida"
]

# ----------------------------------------------------------------------
# CHUẨN HÓA SỐ ĐIỆN THOẠI & ĐỊA ĐIỂM
# ----------------------------------------------------------------------
def clean_phone_lt(phone_str):
    """Chuẩn hóa SĐT Lithuania: luôn có nháy đơn và đầu số quốc tế +370."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = phone_str.strip().lstrip("'")
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

def extract_city(addr):
    """Trích xuất thành phố từ địa chỉ."""
    if not addr or not isinstance(addr, str):
        return ""
    m_post = re.search(r"LT-\d{5}\s+([A-Za-zÀ-ž]+)", addr)
    if m_post:
        c = m_post.group(1).strip()
        if c:
            return c
    for city in LT_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", addr, re.IGNORECASE):
            return city
    return ""

def is_valid_website(url):
    """Kiểm tra website hợp lệ và không nằm trong danh sách đen."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.replace('www.', '').lower()
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        if any(bad in domain for bad in BLACKLIST_DOMAINS):
            return False
        return True
    except Exception:
        return False

# ----------------------------------------------------------------------
# SO KHỚP TÊN DOANH NGHIỆP THÔNG MINH & NGHIÊM NGẶT
# ----------------------------------------------------------------------
def normalize_text_core(text):
    """Khử dấu ngoặc, loại hình pháp lý, chuyển về chữ thường chuẩn hóa."""
    if not text:
        return ""
    t = re.sub(r'["\'„“”«»]', '', str(text)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    
    legal_forms = [
        'uždaroji akcinė bendrovė', 'mažoji bendrija', 'akcinė bendrovė',
        'viešoji įstaiga', 'individuali įmonė', 'žemės ūkio bendrovė',
        'uab', 'mb', 'ab', 'všį', 'iį', 'žūb', 'kb', 'filialas', 'atstovybė'
    ]
    for lf in legal_forms:
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
        
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return t

def is_valid_name_match(query_name, candidate_name):
    """So khớp tên nghiêm ngặt giữa dữ liệu gốc và Google Maps."""
    if not query_name or not candidate_name:
        return False, "EMPTY"
        
    q = normalize_text_core(query_name)
    c = normalize_text_core(candidate_name)
    
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    # Khớp qua ký tự phân tách
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c) if p.strip()]
    if any(p == q for p in parts):
        return True, "DELIMITER_MATCH"
        
    # Chuỗi con nếu đủ dài (tối thiểu 5 ký tự)
    if len(q) >= 5 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    return False, "NO_MATCH"

# ----------------------------------------------------------------------
# BỘ LỌC VÀ CHẤM ĐIỂM EMAIL B2B (MANPOWER AGENCY)
# ----------------------------------------------------------------------
def is_valid_email(email):
    if not email or '@' not in email:
        return False
    e = email.strip().lower()
    if len(e) < 6 or len(e) > 80:
        return False
    if any(jp in e for jp in JUNK_EMAIL_PARTS):
        return False
    if any(bad in e.split('@')[-1] for bad in BLACKLIST_DOMAINS):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', e):
        return False
    ext = e.split('.')[-1]
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf']:
        return False
    return True

def score_email_b2b(email, website_domain=""):
    """Chấm điểm email tối ưu cho B2B Manpower Agency (Lithuania)."""
    if not is_valid_email(email):
        return 0
    e = email.lower().strip()
    score = 10
    prefix = e.split('@')[0]
    email_domain = e.split('@')[1]
    
    # 1. Trùng domain website (+50đ)
    if website_domain and website_domain in email_domain:
        score += 50
    elif any(email_domain.endswith(free) for free in ['gmail.com', 'yahoo.com', 'inbox.lt', 'one.lt']):
        score += 10
        
    # 2. Ưu tiên ĐẶC BIỆT: Chi nhánh tại Lithuania có đuôi .lt (+60đ)
    if email_domain.endswith('.lt'):
        score += 60
        
    # 3. Bộ phận tuyển dụng / nhân sự (+50đ)
    if any(k in prefix for k in ['darbas', 'karjera', 'cv', 'atranka', 'personalo', 'recruitment', 'jobs', 'praca', 'work']):
        score += 50
    # 4. Lãnh đạo / Ban giám đốc (+45đ)
    elif any(k in prefix for k in ['vadov', 'direktor', 'director', 'ceo', 'manager', 'prezident', 'head']):
        score += 45
    # 5. Cổng liên hệ chính thức (+40đ)
    elif any(k in prefix for k in ['info', 'biuras', 'kontakt', 'contact', 'office', 'sekretor', 'bendras']):
        score += 40
    # 6. Email cá nhân theo domain riêng (+25đ)
    elif '.' in prefix or '_' in prefix:
        score += 25
    else:
        score += 15
        
    return score

def decode_cf(email_code):
    """Giải mã Cloudflare Email Protection."""
    try:
        r = int(email_code[:2], 16)
        email = ''.join([chr(int(email_code[i:i+2], 16) ^ r) for i in range(2, len(email_code), 2)])
        return email.strip().lower()
    except Exception:
        return ""

# ----------------------------------------------------------------------
# QUÉT EMAIL TỪ WEBSITE TRỰC QUAN TRÊN TRÌNH DUYỆT CHROME
# ----------------------------------------------------------------------
async def crawl_site_for_email(page, web_url):
    """Mở website công ty trực quan trên Chrome để quét Email B2B."""
    if not is_valid_website(web_url):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith("http"):
        web_url = "https://" + web_url
        
    try:
        parsed_init = urllib.parse.urlparse(web_url)
        initial_domain = parsed_init.netloc.replace('www.', '').lower()
        if not initial_domain or len(initial_domain) < 4:
            return ""
    except Exception:
        return ""
        
    domain = initial_domain
    root = f"{parsed_init.scheme}://{parsed_init.netloc}"
    found_emails = set()
    
    try:
        # 1. Mở trang chủ công ty trực quan trên Chrome
        await page.goto(web_url, wait_until='domcontentloaded', timeout=14000)
        await asyncio.sleep(1.0)
        
        actual_url = page.url or web_url
        parsed_actual = urllib.parse.urlparse(actual_url)
        if parsed_actual.netloc:
            domain = parsed_actual.netloc.replace('www.', '').lower()
            root = f"{parsed_actual.scheme}://{parsed_actual.netloc}"
        
        html = await page.content()
        
        # Bóc tách mailto:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
            clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
            if is_valid_email(clean_m):
                found_emails.add(clean_m)
                
        # Bóc tách Cloudflare
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
            dec = decode_cf(cf)
            if is_valid_email(dec):
                found_emails.add(dec)
                
        # Regex text
        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', html):
            em_low = em.strip().lower()
            if is_valid_email(em_low):
                found_emails.add(em_low)
                
        # Nếu đã có email điểm cao ngay trang chủ (>= 80đ) thì lấy ngay
        if found_emails and any(score_email_b2b(e, domain) >= 80 for e in found_emails):
            return max(found_emails, key=lambda e: score_email_b2b(e, domain))
            
        # 2. Tìm các link liên hệ trên menu trang chủ (khắc phục lệch www/non-www)
        contact_sublinks = []
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            h_low = h.lower()
            txt = a.get_text().lower()
            if any(k in h_low or k in txt for k in ['kontakt', 'contact', 'apie', 'karjer', 'darb', 'about']):
                full = urllib.parse.urljoin(actual_url, h)
                full_lower = full.lower()
                if domain in full_lower and full not in contact_sublinks and '#' not in h:
                    contact_sublinks.append(full)
                    
        contact_sublinks.sort(key=lambda u: 0 if any(k in u.lower() for k in ['contact', 'kontakt']) else 1)
        
        # Mở duyệt sublinks liên hệ trên Chrome (tối đa 4 subpages)
        for cl in contact_sublinks[:4]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=10000)
                await asyncio.sleep(0.8)
                sub_html = await page.content()
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                    clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                    if is_valid_email(clean_m):
                        found_emails.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', sub_html):
                    dec = decode_cf(cf)
                    if is_valid_email(dec):
                        found_emails.add(dec)
                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', sub_html):
                    em_low = em.strip().lower()
                    if is_valid_email(em_low):
                        found_emails.add(em_low)
                if found_emails and any(score_email_b2b(e, domain) >= 70 for e in found_emails):
                    break
            except Exception:
                pass
    except Exception:
        pass
        
    # 3. Thử nhanh các subpath Lithuania & Quốc tế chuẩn nếu vẫn chưa có
    if not found_emails:
        candidates = [
            f"{root}/contact", f"{root}/contact/", f"{root}/contacts", f"{root}/contacts/",
            f"{root}/kontaktai", f"{root}/kontaktai/", f"{root}/kontakt", f"{root}/kontakt/",
            f"{root}/apie-mus", f"{root}/about", f"{root}/about-us"
        ]
        for cu in candidates:
            try:
                await page.goto(cu, wait_until='domcontentloaded', timeout=8000)
                await asyncio.sleep(0.5)
                c_html = await page.content()
                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', c_html):
                    em_low = em.strip().lower()
                    if is_valid_email(em_low):
                        found_emails.add(em_low)
                if found_emails:
                    break
            except Exception:
                pass
                
    if not found_emails:
        return ""
        
    return max(found_emails, key=lambda e: score_email_b2b(e, domain))

# ----------------------------------------------------------------------
# LƯU VÀ ĐỒNG BỘ ĐẦU RA (100% EMAIL LÊN ĐẦU DANH SÁCH)
# ----------------------------------------------------------------------
def save_and_reorder_master(df):
    """Lưu và đồng bộ tự động ra cả 3 file: Root 2COL, CSDL 2COL, CSDL 1ENR."""
    df_out = df.copy()
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_lt)

    # Loại bỏ triệt để các công ty thuộc EXCLUDED_COMPANIES
    if 'Công ty' in df_out.columns:
        df_out = df_out[
            ~df_out['Công ty'].astype(str).str.lower().apply(
                lambda c: any(ex in normalize_text_core(c) or ex in c.lower() for ex in EXCLUDED_COMPANIES)
            )
        ].reset_index(drop=True)

    # Phân loại có email và không có email
    has_em = df_out[df_out['Email'].notna() & (df_out['Email'].astype(str).str.strip() != '') & (df_out['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df_out[df_out['Email'].isna() | (df_out['Email'].astype(str).str.strip() == '') | (df_out['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Đảm bảo đủ các cột chuẩn
    for col in COLDMAIL_COLUMNS:
        if col not in df_sorted.columns:
            df_sorted[col] = ''
    df_sorted = df_sorted[COLDMAIL_COLUMNS]

    # 1. Lưu file Root 2COL
    df_sorted.to_csv(TARGET_CSV_ROOT, index=False, encoding='utf-8-sig')
    # 2. Lưu file CSDL 2COL
    df_sorted.to_csv(TARGET_CSV_CSDL, index=False, encoding='utf-8-sig')
    # 3. Lưu file CSDL 1ENR
    df_sorted.to_csv(TARGET_1ENR_CSDL, index=False, encoding='utf-8-sig')
    return len(has_em)

# ----------------------------------------------------------------------
# HÀM CHÍNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS
# ----------------------------------------------------------------------
async def run_enrichment(headless=False, limit=0):
    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU GOOGLE MAPS - MÔI GIỚI LAO ĐỘNG LITHUANIA")
    print("=" * 85)
    print(f"[*] File mục tiêu chính : {TARGET_CSV_ROOT}")
    print(f"[*] Cache Checkpoint    : {CACHE_PATH}")
    print(f"[*] Trình duyệt Chrome  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False) - Quan sát & Vượt Captcha'}")
    print("=" * 85 + "\n")

    if not TARGET_CSV_ROOT.exists():
        print(f"[ERROR] Không tìm thấy file: {TARGET_CSV_ROOT}")
        return

    df = pd.read_csv(TARGET_CSV_ROOT, encoding='utf-8-sig', dtype=str).fillna('')
    if 'Công ty' in df.columns:
        df = df[
            ~df['Công ty'].astype(str).str.lower().apply(
                lambda c: any(ex in normalize_text_core(c) or ex in c.lower() for ex in EXCLUDED_COMPANIES)
            )
        ].reset_index(drop=True)
    total_companies = len(df)

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache Checkpoint: {len(cache):,} công ty đã kiểm tra từ trước.")
        except Exception:
            pass

    # Lọc danh sách công ty cần xử lý: Chưa có Email VÀ chưa từng xử lý trong Cache
    unprocessed_indices = []
    for idx in df.index:
        em = str(df.at[idx, 'Email']).strip()
        comp = str(df.at[idx, 'Công ty']).strip()
        c_key = comp.lower()
        if em and em != 'nan':
            continue
        if c_key in cache:
            # Áp dụng dữ liệu từ cache nếu có
            cached_item = cache[c_key]
            if cached_item.get('Email'):
                df.at[idx, 'Email'] = cached_item['Email']
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{cached_item['Email']}"
            if cached_item.get('Web') and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = cached_item['Web']
            if cached_item.get('Phone') and not str(df.at[idx, 'SĐT']).strip():
                df.at[idx, 'SĐT'] = cached_item['Phone']
            continue
        unprocessed_indices.append(idx)

    already_has = sum(1 for idx in df.index if str(df.at[idx, 'Email']).strip() and str(df.at[idx, 'Email']).strip() != 'nan')
    print(f"[*] Tổng số doanh nghiệp trong tệp : {total_companies:,}")
    print(f"[*] Đã có Email xác thực           : {already_has:,} ({already_has/total_companies*100:.1f}%)")
    print(f"[*] Đã kiểm tra & lưu Cache        : {len(cache):,} công ty")
    print(f"[*] CẦN LÀM GIÀU GOOGLE MAPS       : {len(unprocessed_indices):,} công ty\n")

    if not unprocessed_indices:
        print("[✔] 100% công ty trong danh sách đã được làm giàu đầy đủ!")
        save_and_reorder_master(df)
        return

    target_list = unprocessed_indices if limit == 0 else unprocessed_indices[:limit]

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            locale="lt-LT",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )

        await browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        await browser.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])

        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed = 0
        new_emails_found = 0
        new_webs_found = 0
        new_phones_found = 0

        for idx in target_list:
            if page.is_closed():
                try:
                    page = await browser.new_page()
                except Exception:
                    pass

            comp = str(df.at[idx, 'Công ty']).strip()
            curr_phone = str(df.at[idx, 'SĐT']).strip()
            curr_web = str(df.at[idx, 'Liên Hệ']).strip()
            curr_addr = str(df.at[idx, 'Địa chỉ']).strip()
            city = extract_city(curr_addr)
            cache_key = comp.lower()

            found_email = ""
            gmap_web = None
            gmap_phone = None

            print(f"[{processed+1:04d}/{len(target_list):04d}] {comp[:35]:<35} | ", end="", flush=True)

            # BƯỚC 1: Nếu công ty đã có website nhưng chưa quét được mail ở lần cào thô trước
            if curr_web and is_valid_website(curr_web):
                found_email = await crawl_site_for_email(page, curr_web)
                if found_email:
                    print(f"WEB HIỆN CÓ: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    new_emails_found += 1

            # BƯỚC 2: Nếu vẫn chưa có Email -> Tìm kiếm trên Google Maps
            if not found_email:
                core_name = normalize_text_core(comp)
                queries = []
                if city:
                    queries.append(f"{core_name} {city} Lietuva")
                queries.append(f"{core_name} Lietuva")
                clean_comp = re.sub(r'["\'„“”«»]', '', comp).strip()
                if len(clean_comp) >= 5 and clean_comp.lower() != core_name:
                    queries.append(f"{clean_comp} Lietuva")

                matched = False
                for q_term in queries[:2]:
                    if matched:
                        break
                    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                    for attempt in range(2):
                        try:
                            if page.is_closed():
                                page = await browser.new_page()

                            await page.goto(url, wait_until='domcontentloaded', timeout=18000)

                            # Tự động đồng ý Cookie Modal của Google
                            try:
                                consent_btn = await page.query_selector(
                                    'button:has-text("Accept all"), button:has-text("Priimti viską"), '
                                    'button:has-text("Sutinku"), button[aria-label*="Accept all"], form[action*="consent"] button'
                                )
                                if consent_btn:
                                    await consent_btn.click()
                                    await asyncio.sleep(1.0)
                            except Exception:
                                pass

                            # Bắt Captcha Google
                            if "google.com/sorry" in page.url or "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                                print("\n\a" + "!" * 80)
                                print("[CẢNH BÁO BOT] PHÁT HIỆN CAPTCHA GOOGLE TRÊN CHROME!")
                                print("Vui lòng giải captcha trên cửa sổ Chrome. Hệ thống kiên nhẫn chờ 120s...")
                                print("!" * 80 + "\n")
                                for wait_s in range(60):
                                    await asyncio.sleep(2.0)
                                    if "google.com/sorry" not in page.url and not await page.query_selector("iframe[src*='recaptcha']"):
                                        print("[+] Captcha đã được xử lý! Tự động quét tiếp...\n")
                                        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                                        await asyncio.sleep(1.5)
                                        break

                            # Chờ Google Maps SPA tải kết quả
                            for _ in range(8):
                                if await page.query_selector('a[href*="/maps/place/"], h1.DUwDvf, div[role="feed"]'):
                                    break
                                body_txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
                                if any(no_k in body_txt for no_k in ["Nenašli sa žiadne výsledky", "Google Maps can't find", "No results found"]):
                                    break
                                await asyncio.sleep(1.0)

                            # 1. Kiểm tra danh sách kết quả (Multiple places)
                            items = await page.query_selector_all('a[href*="/maps/place/"]')
                            if items:
                                for item in items[:4]:
                                    aria_label = await item.get_attribute('aria-label') or ""
                                    is_ok, _ = is_valid_name_match(comp, aria_label)
                                    if is_ok:
                                        await item.click()
                                        try:
                                            await page.wait_for_selector('h1.DUwDvf, a[data-item-id="authority"], button[data-item-id^="phone:"]', timeout=6000)
                                            await asyncio.sleep(1.0)
                                        except Exception:
                                            await asyncio.sleep(1.5)
                                        matched = True
                                        break
                            else:
                                # 2. Kiểm tra trang chi tiết trực tiếp (Single direct place)
                                title_elem = await page.query_selector('h1.DUwDvf')
                                if title_elem:
                                    t_text = await title_elem.inner_text()
                                    is_ok, _ = is_valid_name_match(comp, t_text)
                                    matched = is_ok

                            if matched:
                                # Lấy Website từ Google Maps
                                web_btn = await page.query_selector('a[data-item-id="authority"]')
                                if web_btn:
                                    cand_web = await web_btn.get_attribute('href')
                                    if cand_web and is_valid_website(cand_web):
                                        gmap_web = cand_web

                                # Lấy SĐT từ Google Maps
                                phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                                if phone_btn:
                                    p_attr = await phone_btn.get_attribute('data-item-id')
                                    if p_attr and p_attr.startswith('phone:tel:'):
                                        gmap_phone = p_attr.replace('phone:tel:', '').strip()
                                    else:
                                        p_txt = await phone_btn.inner_text()
                                        if re.search(r'\d{3,}', p_txt):
                                            gmap_phone = p_txt.strip()
                                break
                        except Exception as err:
                            if attempt == 0:
                                await asyncio.sleep(2.0)
                                if page.is_closed():
                                    try:
                                        page = await browser.new_page()
                                    except Exception:
                                        pass

                # Cập nhật Website / SĐT mới từ Google Maps
                if gmap_web and not curr_web:
                    df.at[idx, 'Liên Hệ'] = gmap_web
                    curr_web = gmap_web
                    new_webs_found += 1

                if gmap_phone and not curr_phone:
                    df.at[idx, 'SĐT'] = clean_phone_lt(gmap_phone)
                    curr_phone = df.at[idx, 'SĐT']
                    new_phones_found += 1

                # Quét Email từ Website vừa tìm được qua Google Maps
                if curr_web and is_valid_website(curr_web):
                    found_email = await crawl_site_for_email(page, curr_web)
                    if found_email:
                        new_emails_found += 1
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    else:
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | (Chưa thấy mail)")
                elif matched and gmap_phone:
                    print(f"GMAP: {clean_phone_lt(gmap_phone):<20} | (Khớp Maps - Có SĐT)")
                elif matched:
                    print(f"GMAP | (Khớp địa điểm - Không có web)")
                else:
                    print(f"No match | (Không tìm thấy trên Maps)")

            # Cập nhật kết quả vào DataFrame
            if found_email:
                df.at[idx, 'Email'] = found_email
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{found_email}"

            cache[cache_key] = {
                'Web': curr_web,
                'Email': found_email,
                'Phone': curr_phone,
                'Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed += 1

            # Lưu tăng dần định kỳ mỗi 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                curr_total_emails = save_and_reorder_master(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {curr_total_emails:,}/{total_companies:,} công ty có Email được đưa lên đầu file CSV.")

        # Lưu lần cuối khi hoàn tất
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_emails = save_and_reorder_master(df)

        print("\n" + "=" * 85)
        print(" HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
        print(f" [*] Tổng số công ty          : {total_companies:,}")
        print(f" [*] Đã bóc tách được Email   : {final_emails:,} / {total_companies:,} ({(final_emails/total_companies)*100:.1f}%)")
        print(f" [*] Email mới tìm thấy thêm  : +{new_emails_found:,}")
        print(f" [*] Website mới tìm thấy thêm: +{new_webs_found:,}")
        print(f" [*] SĐT mới tìm thấy thêm    : +{new_phones_found:,}")
        print(f" [*] Đã lưu đồng bộ ra các tệp:")
        print(f"     - {TARGET_CSV_ROOT} (Thư mục gốc)")
        print(f"     - {TARGET_CSV_CSDL}")
        print(f"     - {TARGET_1ENR_CSDL}")
        print("=" * 85 + "\n")

        await browser.close()

# ----------------------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Lithuania Recruitment Agencies")
    parser.add_argument("--headless", action="store_true", help="Chạy ngầm không mở cửa sổ (mặc định mở trực quan)")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số công ty xử lý (0 = toàn bộ)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless, limit=args.limit))

if __name__ == '__main__':
    main()
