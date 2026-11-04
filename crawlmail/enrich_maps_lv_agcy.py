# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LATVIA RECRUITMENT & EMPLOYMENT AGENCIES
Target dataset: LV_AGCY_WEBD_2COL.csv & LV_AGCY_WEBD_1ENR.csv

Đặc điểm:
- Tự động lọc các công ty CHƯA CÓ EMAIL để tìm kiếm trên Google Maps & Website.
- So khớp tên nghiêm ngặt (Strict Name Matching) khử các loại hình pháp lý SIA, AS, IK, PS, KS, Pašvaldības aģentūra...
  và các hậu tố phân loại của danh bạ 1188.lv/viss.lv (personāla atlase, darbs ārzemēs...).
- Bóc tách Website, Địa chỉ chuẩn và Số điện thoại (+371...) từ Google Maps.
- Quét Email B2B đa tầng: ưu tiên tối cao email đuôi .lv (+60đ), vakances@, darbs@, karjera@, cv@, atlase@, info@, birojs@...
- Chế độ trực quan Chrome (headless=False) có chuông báo \\a khi gặp Captcha, tự động vượt Cookie Consent.
- Tự động thay thế page.wait_for_timeout bằng asyncio.sleep và tự động khôi phục tab nếu Chrome bị đóng.
- Lưu tăng dần (Incremental Checkpoint) mỗi 5 công ty, đẩy 100% doanh nghiệp có Email lên đầu tệp CSV.

Đầu ra:
1. LV_AGCY_WEBD_2COL.csv (Thư mục gốc - Chuẩn Cold Mail 20 cột, 100% Email lên đầu)
2. LV_AGCY_WEBD_1ENR.csv (Thư mục gốc - Đầy đủ các trường bổ trợ)
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
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV_ROOT = ROOT_DIR / "LV_AGCY_WEBD_2COL.csv"
TARGET_1ENR_ROOT = ROOT_DIR / "LV_AGCY_WEBD_1ENR.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lv_agcy.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "lv_agcy_maps_profile"

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
    '1188.lv', 'viss.lv', 'crediweb.lv', 'crefocert.lv', 'lursoft.lv', 'firmas.lv',
    'ss.lv', 'ss.com', 'visasdarbavietas.lv', 'katalogs.lv',
    'zl.lv', 'zo.lv', 'latvijasbizness.lv', 'pilseta24.lv', 'vietas.lv',
    'wikipedia.org', 'delfi.lv', 'tvnet.lv', 'apollo.lv', 'lsm.lv', 'jauns.lv',
    'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'wix.com', 'wordpress.com',
    'tet.lv', 'maptiler.com', 'openstreetmap.org', 'leafletjs.com', 'schema.org'
]

# Rule #12: Danh sách đen doanh nghiệp cố định
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in ['scandi standard', 'scandi-standard', 'scandi standart', 'biliarta', 'daigre'])

JUNK_EMAIL_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@',
    'info@1188.lv', 'viss@viss.lv', 'info@viss.lv'
]

LV_CITIES = [
    "Rīga", "Riga", "Daugavpils", "Liepāja", "Liepaja", "Jelgava", "Jūrmala", "Jurmala",
    "Ventspils", "Rēzekne", "Rezekne", "Valmiera", "Jēkabpils", "Jekabpils", "Ogre",
    "Salaspils", "Tukums", "Cēsis", "Cesis", "Sigulda", "Olaine", "Kuldīga", "Kuldiga",
    "Saldus", "Talsi", "Dobele", "Krāslava", "Kraslava", "Bauska", "Ludza", "Līvāni", "Livani",
    "Gulbene", "Madona", "Alūksne", "Aluksne", "Aizkraukle", "Balvi", "Limbaži", "Limbazi",
    "Preiļi", "Preili", "Valka", "Smiltene", "Viļāni", "Vilani", "Iecava", "Baloži", "Balozi"
]

GAMBLING_KEYWORDS = [
    'casino', 'kazino', 'ggbet', 'vulkan', 'betting', 'derības', 'poker',
    'slots', 'jackpot', 'roulette', 'bukmeker', 'gambling', 'optibet', 'fenikss'
]

# ----------------------------------------------------------------------
# CHUẨN HÓA SỐ ĐIỆN THOẠI & ĐỊA ĐIỂM
# ----------------------------------------------------------------------
def clean_phone_lv(phone_str):
    """Chuẩn hóa SĐT Latvia: luôn có nháy đơn ' và đầu số quốc tế +371."""
    if not phone_str or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip().lstrip("'")
    p = re.sub(r'^(?:Tel|T\.|Tālr\.|Tālrunis)[:\s]*', '', p, flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('371'):
        return f"'+{digits}"
    elif (digits.startswith('6') or digits.startswith('2')) and len(digits) == 8:
        return f"'+371{digits}"
    elif digits.startswith('0'):
        return f"'+371{digits[1:]}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"

def extract_city_lv(comp_name, addr):
    """Trích xuất thành phố từ tên công ty (ưu tiên nhánh/filiāle) hoặc địa chỉ."""
    c_name = str(comp_name or "")
    # 1. Kiểm tra nhánh trực tiếp trong tên công ty
    for city in LV_CITIES:
        if re.search(rf"\b{re.escape(city)}(?:s|es|ā|ē|as|ie|iem)?\b", c_name, re.IGNORECASE):
            return city
            
    # 2. Kiểm tra trong địa chỉ
    if addr and isinstance(addr, str):
        # Trích xuất mã bưu chính LV-XXXX
        m_post = re.search(r"LV-\d{4}\s+([A-Za-zĀ-ž]+)", addr)
        if m_post:
            c = m_post.group(1).strip()
            if c:
                return c
        for city in LV_CITIES:
            if re.search(rf"\b{re.escape(city)}\b", addr, re.IGNORECASE):
                return city
    return ""

def is_valid_website(url):
    """Kiểm tra website hợp lệ và không nằm trong danh sách đen hoặc cờ bạc."""
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
        if any(g in domain for g in GAMBLING_KEYWORDS):
            return False
        return True
    except Exception:
        return False

# ----------------------------------------------------------------------
# SO KHỚP TÊN DOANH NGHIỆP THÔNG MINH & NGHIÊM NGẶT (LATVIA)
# ----------------------------------------------------------------------
def strip_accents(s):
    n = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in n if not unicodedata.combining(c))

def normalize_text_core(text):
    """Khử dấu ngoặc, loại hình pháp lý, chuyển về chữ thường chuẩn hóa không dấu."""
    if not text:
        return ""
    t = re.sub(r'["\'„“”«»]', '', str(text)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    
    # Loại bỏ mô tả đặc trưng của danh bạ
    for desc in [
        r',?\s*personāla atlase.*',
        r',?\s*aktieru un talantu atlase.*',
        r',?\s*darbs ārzemēs.*',
        r',?\s*personāla risinājumu aģentūra.*',
        r',?\s*mācību centrs.*',
        r'\s*-\s*Atrodi piemērotāko.*',
        r'\s*3A princips.*',
        r'\(SPMG\)',
    ]:
        t = re.sub(desc, '', t, flags=re.I).strip()
        
    legal_forms = [
        r'\bsabiedrība ar ierobežotu atbildību\b',
        r'\bakciju sabiedrība\b',
        r'\bindividuālais komersants\b',
        r'\bpašvaldības aģentūra\b',
        r'\bsia\b', r'\bas\b', r'\ba/s\b', r'\bik\b', r'\bps\b', r'\bks\b'
    ]
    for lf in legal_forms:
        t = re.sub(lf, '', t, flags=re.I).strip()
        
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return strip_accents(t)

def clean_company_name_for_search(name):
    """Làm sạch tên công ty để tạo từ khóa tìm kiếm tối ưu trên Google Maps."""
    t = re.sub(r'["\'„“”«»]', '', str(name)).strip()
    for desc in [
        r',?\s*personāla atlase.*',
        r',?\s*aktieru un talantu atlase.*',
        r',?\s*darbs ārzemēs.*',
        r',?\s*personāla risinājumu aģentūra.*',
        r',?\s*mācību centrs.*',
        r'\s*-\s*Atrodi piemērotāko.*',
        r'\s*3A princips.*',
        r'\(SPMG\)',
    ]:
        t = re.sub(desc, '', t, flags=re.I).strip()
    t = re.sub(r'\b(?:SIA|AS|A/S|IK|PS|KS)\b', '', t, flags=re.I).strip(' ,.-')
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
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    for p in parts:
        pn = normalize_text_core(p)
        if pn and (pn == q or (len(q) >= 4 and pn in q) or (len(pn) >= 4 and q in pn)):
            return True, "DELIMITER_MATCH"
            
    # Chuỗi con nếu đủ dài (tối thiểu 4 ký tự)
    if len(q) >= 4 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    # Tập token
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if q_tokens and (q_tokens.issubset(c_tokens) or c_tokens.issubset(q_tokens)):
        return True, "TOKEN_SET_MATCH"
        
    return False, "NO_MATCH"

# ----------------------------------------------------------------------
# BỘ LỌC VÀ CHẤM ĐIỂM EMAIL B2B (MANPOWER AGENCY LATVIA)
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
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf', 'ico']:
        return False
    return True

def score_email_b2b(email, website_domain=""):
    """Chấm điểm email tối ưu cho B2B Manpower Agency (Latvia)."""
    if not is_valid_email(email):
        return 0
    e = email.lower().strip()
    score = 10
    prefix = e.split('@')[0]
    email_domain = e.split('@')[1]
    
    # 1. Trùng domain website (+50đ)
    if website_domain and website_domain in email_domain:
        score += 50
    elif any(email_domain.endswith(free) for free in ['gmail.com', 'yahoo.com', 'inbox.lv', 'apollo.lv', 'tvnet.lv']):
        score += 10
        
    # 2. Ưu tiên ĐẶC BIỆT: Chi nhánh tại Latvia có đuôi .lv (+60đ)
    if email_domain.endswith('.lv'):
        score += 60
        
    # 3. Bộ phận nhân sự / tuyển dụng / việc làm (+50đ)
    if any(k in prefix for k in ['vakances', 'darbs', 'karjera', 'cv', 'atlase', 'personals', 'recruitment', 'jobs', 'praca', 'work', 'hr']):
        score += 50
    # 4. Lãnh đạo / Ban giám đốc (+45đ)
    elif any(k in prefix for k in ['vadiba', 'direktors', 'vaditajs', 'ceo', 'director', 'manager', 'valde', 'board']):
        score += 45
    # 5. Cổng liên hệ chính thức (+40đ)
    elif any(k in prefix for k in ['info', 'birojs', 'kontakt', 'kontakti', 'contact', 'office', 'sekretare', 'pasts']):
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

        # Kiểm tra nếu trang chuyển hướng sang casino / cờ bạc / cá cược
        try:
            p_title = (await page.title() or "").lower()
            if any(g in p_title or g in actual_url.lower() or g in domain for g in GAMBLING_KEYWORDS):
                print(f"  ⚠️ [BỎ QUA WEB ĐÁNH BẠC/CASINO] {web_url} -> '{p_title[:35]}'")
                return ""
        except Exception:
            pass

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
            
        # 2. Tìm các link liên hệ trên menu trang chủ (Latvia & Quốc tế)
        contact_sublinks = []
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            h_low = h.lower()
            txt = a.get_text().lower()
            if any(k in h_low or k in txt for k in [
                'kontakti', 'kontakt', 'par-mums', 'parmums', 'vakances', 'karjera',
                'darbs', 'pakalpojumi', 'kontakts', 'rakstiet-mums', 'contact', 'about', 'team'
            ]):
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
        
    # 3. Thử nhanh các subpath Latvia & Quốc tế chuẩn nếu vẫn chưa có
    if not found_emails:
        candidates = [
            f"{root}/kontakti", f"{root}/kontakti.html", f"{root}/kontakti.php",
            f"{root}/kontakt", f"{root}/contact", f"{root}/contact-us",
            f"{root}/par-mums", f"{root}/par-mums.html", f"{root}/vakances",
            f"{root}/karjera", f"{root}/darbs", f"{root}/about", f"{root}/about-us"
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
# ĐOÁN EMAIL DỰA TRÊN TIỀN TỐ PHỔ BIẾN NHẤT & DOMAIN WEBSITE
# ----------------------------------------------------------------------
def get_clean_domain(url):
    """Trích xuất root domain sạch, loại trừ blacklist mạng xã hội và web cờ bạc."""
    if not is_valid_website(url):
        return None
    try:
        u = str(url).strip().lower()
        if not u.startswith("http"):
            u = "https://" + u
        parsed = urllib.parse.urlparse(u)
        netloc = parsed.netloc.split(':')[0].lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        if any(b in netloc for b in BLACKLIST_DOMAINS):
            return None
        if any(g in netloc for g in GAMBLING_KEYWORDS):
            return None
        parts = netloc.split('.')
        if len(parts) >= 2 and len(parts[-1]) >= 2:
            return netloc
        return None
    except Exception:
        return None

def guess_emails_from_domains(df, force_prefix=None):
    """
    Thực hiện bước đoán mail:
    1. Tổng hợp lượng mail trước @ để chọn ra đầu mail phổ biến nhất.
    2. Đoán ghép với các website chưa có email: <tiền tố>@[domain].
    """
    email_col = 'Email'
    web_col = 'Liên Hệ'
    
    # 1. Thống kê tiền tố trước @
    prefix_counts = {}
    for idx in df.index:
        em = str(df.at[idx, email_col]).strip().lower()
        if em and em != 'nan' and '@' in em and '.' in em:
            pref = em.split('@')[0].strip()
            prefix_counts[pref] = prefix_counts.get(pref, 0) + 1
            
    sorted_prefixes = sorted(prefix_counts.items(), key=lambda x: x[1], reverse=True)
    if force_prefix:
        chosen_prefix = force_prefix.strip().lower()
    else:
        chosen_prefix = sorted_prefixes[0][0] if sorted_prefixes else 'info'
        
    print(f"\n[*] [BƯỚC ĐOÁN EMAIL] Tiền tố phổ biến nhất được chọn: '{chosen_prefix}' ({prefix_counts.get(chosen_prefix, 0)} lần)")
    
    # 2. Đoán ghép
    guessed_count = 0
    df_res = df.copy()
    for idx in df_res.index:
        comp = str(df_res.at[idx, 'Công ty']).strip()
        if is_blacklisted_company(comp):
            continue
        em = str(df_res.at[idx, email_col]).strip()
        if not em or em.lower() == 'nan' or '@' not in em:
            web = df_res.at[idx, web_col]
            domain = get_clean_domain(web)
            if domain:
                guessed_em = f"{chosen_prefix}@{domain}"
                df_res.at[idx, email_col] = guessed_em
                df_res.at[idx, 'Liên Hệ mail'] = f"mailto:{guessed_em}"
                guessed_count += 1
                
    print(f"[*] [BƯỚC ĐOÁN EMAIL] Đã ghép thành công +{guessed_count:,} email mới từ domain website!\n")
    return df_res

# ----------------------------------------------------------------------
# LƯU VÀ ĐỒNG BỘ ĐẦU RA (100% EMAIL LÊN ĐẦU DANH SÁCH)
# ----------------------------------------------------------------------
def save_and_reorder_master(df, df_1enr=None):
    """Lưu và đồng bộ tự động ra cả 2 file: Root 2COL và Root 1ENR."""
    df_out = df.copy()
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_lv)

    # Loại bỏ triệt để các công ty thuộc Permanent Blacklist
    if 'Công ty' in df_out.columns:
        df_out = df_out[
            ~df_out['Công ty'].astype(str).apply(is_blacklisted_company)
        ].reset_index(drop=True)

    # Phân loại có email và không có email (100% Email lên đầu)
    has_em = df_out[df_out['Email'].notna() & (df_out['Email'].astype(str).str.strip() != '') & (df_out['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df_out[df_out['Email'].isna() | (df_out['Email'].astype(str).str.strip() == '') | (df_out['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Đảm bảo đủ các cột chuẩn COLDMAIL_COLUMNS
    for col in COLDMAIL_COLUMNS:
        if col not in df_sorted.columns:
            df_sorted[col] = ''
    df_sorted = df_sorted[COLDMAIL_COLUMNS]

    # 1. Lưu file Root 2COL
    df_sorted.to_csv(TARGET_CSV_ROOT, index=False, encoding='utf-8-sig')

    # 2. Cập nhật và lưu file Root 1ENR
    if TARGET_1ENR_ROOT.exists():
        try:
            df_1 = pd.read_csv(TARGET_1ENR_ROOT, encoding='utf-8-sig', dtype=str).fillna('')
            # Đồng bộ các cột quan trọng theo tên công ty
            enrich_map = {}
            for _, r in df_sorted.iterrows():
                enrich_map[r['Công ty']] = {
                    'SĐT': r['SĐT'],
                    'Liên Hệ': r['Liên Hệ'],
                    'Email': r['Email'],
                    'Liên Hệ mail': r['Liên Hệ mail'],
                    'Địa chỉ': r['Địa chỉ']
                }
            for idx1 in df_1.index:
                c1 = df_1.at[idx1, 'Công ty']
                if c1 in enrich_map:
                    item = enrich_map[c1]
                    for k, v in item.items():
                        if v and k in df_1.columns:
                            df_1.at[idx1, k] = v
            # Loại bỏ blacklist trong 1ENR
            df_1 = df_1[~df_1['Công ty'].astype(str).apply(is_blacklisted_company)].reset_index(drop=True)
            df_1.to_csv(TARGET_1ENR_ROOT, index=False, encoding='utf-8-sig')
        except Exception as e:
            print(f"  [!] Lưu 1ENR error: {e}")

    return len(has_em)

# ----------------------------------------------------------------------
# HÀM CHÍNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS
# ----------------------------------------------------------------------
async def run_enrichment(headless=False, limit=0):
    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU GOOGLE MAPS - MÔI GIỚI LAO ĐỘNG LATVIA")
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
            ~df['Công ty'].astype(str).apply(is_blacklisted_company)
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

    # Lọc danh sách công ty cần xử lý: Chưa có Email
    unprocessed_indices = []
    for idx in df.index:
        comp = str(df.at[idx, 'Công ty']).strip()
        if is_blacklisted_company(comp):
            continue

        c_key = comp.lower()
        if c_key in cache:
            # Áp dụng dữ liệu từ cache nếu có
            cached_item = cache[c_key]
            if cached_item.get('Email'):
                df.at[idx, 'Email'] = cached_item['Email']
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{cached_item['Email']}"
            if cached_item.get('Web') and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = cached_item['Web']
            if cached_item.get('Phone') and not str(df.at[idx, 'SĐT']).strip():
                df.at[idx, 'SĐT'] = clean_phone_lv(cached_item['Phone'])
            if cached_item.get('Address') and not str(df.at[idx, 'Địa chỉ']).strip():
                df.at[idx, 'Địa chỉ'] = cached_item['Address']

        em = str(df.at[idx, 'Email']).strip()
        if em and em != 'nan' and is_valid_email(em):
            continue

        unprocessed_indices.append(idx)

    already_has = sum(1 for idx in df.index if str(df.at[idx, 'Email']).strip() and str(df.at[idx, 'Email']).strip() != 'nan')
    print(f"[*] Tổng số doanh nghiệp trong tệp : {total_companies:,}")
    print(f"[*] Đã có Email xác thực           : {already_has:,} ({already_has/total_companies*100:.1f}%)")
    print(f"[*] Đã kiểm tra & lưu Cache        : {len(cache):,} công ty")
    print(f"[*] CẦN TIẾP TỤC LÀM GIÀU          : {len(unprocessed_indices):,} công ty\n")

    if not unprocessed_indices:
        print("[✔] 100% công ty trong danh sách đã được làm giàu đầy đủ!")
        df = guess_emails_from_domains(df)
        save_and_reorder_master(df)
        return

    target_list = unprocessed_indices if limit == 0 else unprocessed_indices[:limit]

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            locale="lv-LV",
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
            city = extract_city_lv(comp, curr_addr)
            cache_key = comp.lower()

            found_email = ""
            gmap_web = None
            gmap_phone = None
            gmap_addr = None

            print(f"[{processed+1:04d}/{len(target_list):04d}] {comp[:35]:<35} | ", end="", flush=True)

            # BƯỚC 1: Nếu công ty đã có website nhưng chưa quét được mail ở lần cào thô trước
            if curr_web and is_valid_website(curr_web):
                found_email = await crawl_site_for_email(page, curr_web)
                if found_email:
                    print(f"WEB CÓ SẴN: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    new_emails_found += 1

            # BƯỚC 2: Nếu vẫn chưa có Email -> Tìm kiếm trên Google Maps
            if not found_email:
                search_comp = clean_company_name_for_search(comp)
                queries = []
                if city:
                    queries.append(f"{search_comp} {city}")
                    queries.append(f"{search_comp} Latvija")
                    queries.append(f"{search_comp}")
                else:
                    queries.append(f"{search_comp} Latvija")
                    queries.append(f"{search_comp} Riga")
                    queries.append(f"{search_comp}")
                if curr_phone:
                    p_digits = re.sub(r'[^\d]', '', curr_phone)
                    if len(p_digits) >= 8:
                        queries.append(f"{search_comp} {p_digits[-8:]}")

                matched = False
                for q_term in queries:
                    if matched:
                        break
                    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=lv"

                    for attempt in range(2):
                        try:
                            if page.is_closed():
                                page = await browser.new_page()

                            await page.goto(url, wait_until='domcontentloaded', timeout=18000)

                            # Tự động đồng ý Cookie Modal của Google (tiếng Latvia / tiếng Anh)
                            try:
                                consent_btn = await page.query_selector(
                                    'button:has-text("Pieņemt visu"), button:has-text("Piekrītu"), '
                                    'button:has-text("Accept all"), button:has-text("Priimti viską"), '
                                    'button[aria-label*="Accept all"], form[action*="consent"] button'
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
                                if any(no_k in body_txt for no_k in ["Nekas netika atrasts", "Google Maps nevar atrast", "No results found"]):
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

                                # Lấy Địa chỉ chính xác từ Google Maps
                                addr_btn = await page.query_selector('button[data-item-id="address"]')
                                if addr_btn:
                                    cand_addr = await addr_btn.get_attribute('aria-label') or await addr_btn.inner_text()
                                    cand_addr = re.sub(r'^(?:Adrese|Address)[:\s]*', '', cand_addr, flags=re.I).strip()
                                    if cand_addr and len(cand_addr) > 5:
                                        gmap_addr = cand_addr

                                break
                        except Exception as err:
                            if attempt == 0:
                                await asyncio.sleep(2.0)
                                if page.is_closed():
                                    try:
                                        page = await browser.new_page()
                                    except Exception:
                                        pass

                # Cập nhật Website / SĐT / Địa chỉ mới từ Google Maps
                if gmap_web and not curr_web:
                    df.at[idx, 'Liên Hệ'] = gmap_web
                    curr_web = gmap_web
                    new_webs_found += 1

                if gmap_phone and not curr_phone:
                    df.at[idx, 'SĐT'] = clean_phone_lv(gmap_phone)
                    curr_phone = df.at[idx, 'SĐT']
                    new_phones_found += 1

                if gmap_addr and (not curr_addr or curr_addr in ["Tērbatas iela 32, Rīga, LV-1011", "Lazaretes iela 7, Liepāja, LV-3414"]):
                    df.at[idx, 'Địa chỉ'] = gmap_addr
                    curr_addr = gmap_addr

                # Quét Email từ Website vừa tìm được qua Google Maps
                if curr_web and is_valid_website(curr_web):
                    found_email = await crawl_site_for_email(page, curr_web)
                    if found_email:
                        new_emails_found += 1
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    else:
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | (Chưa thấy mail)")
                elif matched and gmap_phone:
                    print(f"GMAP: {clean_phone_lv(gmap_phone):<20} | (Khớp Maps - Có SĐT)")
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
                'Address': curr_addr,
                'Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed += 1

            # Lưu tăng dần định kỳ mỗi 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                curr_total_emails = save_and_reorder_master(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {curr_total_emails:,}/{total_companies:,} công ty có Email được đưa lên đầu file CSV.")

        # Lưu lần cuối khi duyệt hết danh sách
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        # Thực hiện bước đoán email theo tiền tố phổ biến nhất cho các web còn lại
        df = guess_emails_from_domains(df)
        final_emails = save_and_reorder_master(df)

        print("\n" + "=" * 85)
        print(" HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
        print(f" [*] Tổng số công ty          : {total_companies:,}")
        print(f" [*] Đã bóc tách được Email   : {final_emails:,} / {total_companies:,} ({(final_emails/total_companies)*100:.1f}%)")
        print(f" [*] Email mới tìm thấy thêm  : +{new_emails_found:,}")
        print(f" [*] Website mới tìm thấy thêm: +{new_webs_found:,}")
        print(f" [*] SĐT mới tìm thấy thêm    : +{new_phones_found:,}")
        print(f" [*] Đã lưu đồng bộ ra các tệp:")
        print(f"     - {TARGET_CSV_ROOT} (Thư mục gốc - 100% Email lên đầu)")
        print(f"     - {TARGET_1ENR_ROOT}")
        print("=" * 85 + "\n")

        await browser.close()

# ----------------------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Latvia Recruitment Agencies")
    parser.add_argument("--headless", action="store_true", help="Chạy ngầm không mở cửa sổ (mặc định mở trực quan)")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số công ty xử lý (0 = toàn bộ)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless, limit=args.limit))

if __name__ == '__main__':
    main()
