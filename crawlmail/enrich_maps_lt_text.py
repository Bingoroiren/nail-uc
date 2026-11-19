# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN TEXTILE & APPAREL ENTERPRISES (LT_TEXT)
================================================================================
Mục tiêu: Làm giàu dữ liệu bằng Google Maps cho tệp LT_TEXT_INLT_2COL.csv (1,429 công ty
          dệt may Litva) kết hợp metadata từ LT_TEXT_INLT_1ENR.csv.

Input:  LT_TEXT_INLT_2COL.csv (+ tự động kết hợp LT_TEXT_INLT_1ENR.csv nếu có)
Output:
  - LT_TEXT_GMAP_1ENR.csv (Master dataset đầy đủ sau khi enrich Maps + Web + FB)
  - LT_TEXT_GMAP_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
  - LT_TEXT_GMAP_ONLY_EMAILS_READY.csv (Chỉ chứa các công ty có email sạch)
  - Đồng bộ cập nhật LT_TEXT_INLT_2COL.csv & LT_TEXT_INLT_ONLY_EMAILS_READY.csv
    (Có tạo backup archive/lt_lithuania/LT_TEXT_INLT_2COL_pre_maps_backup.csv lần đầu)
  - Đồng bộ vào csdl_mlt/ và archive/lt_lithuania/

Tuân thủ toàn diện quy chuẩn GEMINI.md & Skills (enrich-maps, crawl-mail, data-standards):
- Rule 1 : CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2 : SĐT luôn có nháy đơn ('+370...)
- Rule 3 : B2B Email Scoring giữ DUY NHẤT 1 email giá trị nhất, đẩy 100% email lên đầu
- Rule 4 : Trình duyệt trực quan (headless=False), viewport >= 1280x800, báo chuông Captcha
- Rule 5 : Incremental Auto-Save mỗi 5 công ty + Checkpoint JSON Resume 100%
- Rule 8 : Launcher .bat thuần ASCII, không dấu tiếng Việt, không dùng & trần
- Rule 10: Quy chuẩn đặt tên 17 ký tự (LT_TEXT_GMAP_1ENR / LT_TEXT_GMAP_2COL)
- Rule 11: So khớp tên thông minh & nghiêm ngặt (NFKD, bỏ ngoặc, bỏ legal forms Litva)
- Rule 12: Loại trừ danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre)
"""

import sys
import os
import re
import ssl
import html as html_lib
import json
import time
import shutil
import asyncio
import argparse
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# UTF-8 output cho Windows Console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_2COL_PATH = ROOT_DIR / "LT_TEXT_INLT_2COL.csv"
INPUT_1ENR_PATH = ROOT_DIR / "LT_TEXT_INLT_1ENR.csv"
BACKUP_2COL_PATH = ROOT_DIR / "archive" / "lt_lithuania" / "LT_TEXT_INLT_2COL_pre_maps_backup.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_TEXT_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_TEXT_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_TEXT_GMAP_ONLY_EMAILS_READY.csv"

SYNC_INLT_2COL_PATH = ROOT_DIR / "LT_TEXT_INLT_2COL.csv"
SYNC_INLT_READY_PATH = ROOT_DIR / "LT_TEXT_INLT_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_text.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

MAPS_TIMEOUT = 25000
DELAY_AFTER_SEARCH = 2.0
DELAY_AFTER_CLICK = 2.0

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule 12: Permanent company blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

# Domain mạng xã hội, sàn danh bạ, cơ quan nhà nước (tuyệt đối không nhận làm Website chính thức)
BLACKLIST_DOMAINS = [
    'facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'twitter.com', 'x.com', 'tiktok.com', 'pinterest.com', 'google.com',
    'maps.google.com', 'goo.gl', 'wikipedia.org', 'yellowpages', 'tripadvisor',
    'booking.com', 'yelp.com', 'sentry.io', 'wix.com', 'wixpress.com',
    'rekvizitai.vz.lt', 'rekvizitai.lt', 'rekv.lt', 'info.lt', 'visalietuva.lt',
    'imones.lt', 'statyba.lt', 'cr.lt', 'okredo.com', 'scoris.lt',
    'creditinfo.lt', 'cvbankas.lt', 'cvonline.lt', 'cvmarket.lt', 'dirbk.lt',
    'registrucentras.lt', 'vmi.lt', 'sodra.lt', '1588.lt', '1551.lt',
    'infoplius.lt', 'imoniugidas.lt', 'imoniubaze.lt', 'imoniukatalogai.lt',
    'verslas.lt', 'spec.lt', 'litorg.cc', 'delfi.lt', '15min.lt', 'lrytas.lt',
    'tv3.lt', 'alfa.lt', 'lrt.lt', 'b2lithuania.com', 'geltoni.lt', 'tax.lt',
    'balticlei.lt', 'business-baltics.com', 'ltkatalogas.lt', 'expo.lt',
    'lovejob.lt', 'tinklalapiai.lt', 'trustpilot.com', 'schema.org'
]

SUBSTRING_BLACKLIST_BRANDS = ['yellowpages', 'tripadvisor', 'booking.com', 'yelp.com']

GAMBLING_KEYWORDS = [
    'casino', 'kazino', 'ggbet', 'vulkan', 'betting', 'lazybos',
    'poker', 'slots', 'jackpot', 'roulette', 'bukmeker', 'gambling'
]

JUNK_EMAIL_DOMAINS = set(BLACKLIST_DOMAINS) | {
    'wordpress.com', 'squarespace.com', 'weebly.com', 'godaddy.com',
    'example.com', 'example.org', 'domain.com', 'yourdomain.com',
    'yourcompany.com', 'company.com', 'website.com', 'site.com',
    'placeholder.com', 'templatemonster.com', 'themeforest.net',
    'bootstrapmade.com', 'pavyzdys.lt', 'imone.lt', 'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies',
    'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon',
    'test', 'example', 'hostmaster', 'postmaster', 'root', 'dataprivacy',
    'datenschutz'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname', 'username', 'user', 'name',
    'sample', 'demo', 'testing', 'placeholder', 'someone', 'nobody',
    'john.doe', 'johndoe', 'jane.doe', 'janedoe', 'first.last',
    'jusu', 'tavo', 'vardas', 'pavarde'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
OBFUSCATED_EMAIL_REGEX = re.compile(
    r'\b([A-Za-z0-9._%+-]{1,64})\s*(?:\[at\]|\(at\)|\{at\}|\bat\b)\s*([A-Za-z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\{dot\}|\.)\s*([A-Za-z]{2,10})\b',
    re.I
)
INVALID_EXTS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js',
    '.pdf', '.woff', '.woff2', '.ico', '.mp4', '.avi', '.zip', '.rar'
)

# Priority 10 & Priority 5 từ khóa menu bản địa Litva + Quốc tế (Skill crawl-mail)
LT_CONTACT_KEYWORDS_P10 = [
    'kontaktai', 'kontakt', 'susisiekite', 'susisiekti', 'contact', 'contacts',
    'contact-us', 'get-in-touch', 'reach-us', 'rekvizitai'
]
LT_SECONDARY_KEYWORDS_P5 = [
    'apie', 'apie-mus', 'karjera', 'darbas', 'administracija', 'prekyba',
    'pardavimai', 'gamyba', 'siuvimas', 'siuvykla', 'about', 'about-us',
    'career', 'careers', 'jobs', 'team', 'company'
]

# Priority 2 fallback guess subpaths (chỉ chạy khi DOM link chưa ra email)
LT_GUESS_SUBPATHS = [
    '/kontaktai', '/kontaktai/', '/kontaktai.html', '/kontaktai.php',
    '/susisiekite', '/rekvizitai', '/apie-mus', '/apie-mus.html',
    '/karjera', '/darbas', '/contact', '/contact.html', '/contact-us',
    '/about', '/about-us'
]


# ----------------------------------------------------------------------
# HÀM CHUẨN HÓA, BLACKLIST & SO KHỚP TÊN (RULE 2, 3, 11, 12)
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Litva có nháy đơn (') ở đầu"""
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
    elif digits.startswith('0') and len(digits) in (9, 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370') and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"


def clean_email(email_str):
    """Rule 3: Làm sạch triệt để %20, \\u00a0, zero-width space, hậu tố tel/mob dính"""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = html_lib.unescape(urllib.parse.unquote(str(email_str).strip()))
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        e = e.replace(bad, '')
    e = re.sub(r'^(?:mailto:\s*|u00[0-9a-f]{2})+', '', e, flags=re.I)
    e = re.sub(r'\s+', '', e)
    e = e.strip(" .,;:\"'<>[](){}\\/").lower()
    e = re.sub(r'^(?:u00[0-9a-f]{2})+', '', e)
    if re.match(r'^20[a-zA-Z][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e) and not e.startswith('202'):
        e = e[2:]
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and '@' in e:
            tld = e.split('@')[-1].split('.')[-1]
            if len(tld) > 5:
                e = e[:-len(suffix)]
    return e.strip()


def decode_cf_hex(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join(chr(int(cf_hex[i:i + 2], 16) ^ r) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


def normalize_text(text):
    """Khử dấu Unicode NFKD đa quốc gia và loại bỏ ngoặc kép trang trí"""
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    t = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'["\'„“”«»`´]', '', t).strip()


def clean_company_name_lt(name):
    """Bóc tách ngoặc dịch/chú thích + legal forms Litva + cắt sạch dấu câu đầu/cuối"""
    if not name:
        return ""
    t = normalize_text(name)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    legal_forms = [
        'uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove',
        'individuali imone', 'viesoji istaiga', 'zemes ukio bendrove',
        'bendra imone', 'uab', 'mb', 'ab', 'ii', 'vsi', 'tub', 'kub',
        'zub', 'kb', 'filialas', 'skyrius', 'kooperatyvas'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
    return re.sub(r'\s+', ' ', t).strip(' ,.-:;|/')


def is_valid_name_match_lt(query_name, candidate_name):
    """
    So khớp tên thông minh & nghiêm ngặt (Rule 11 & Skill enrich-maps Section 2.A):
    - Cho phép khớp chính xác sau khử dấu + bóc legal forms Litva
    - Cho phép tách ngoặc chú thích (...) / [...]
    - Cho phép tách cụm ngăn cách chuẩn (-, –, —, |, /, :, ,)
    - Từ chối nghiêm ngặt nếu bị chèn từ lạ vào giữa hoặc tên không tương xứng
    """
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_raw_norm = normalize_text(query_name)
    c_raw_norm = normalize_text(candidate_name)

    q_clean = clean_company_name_lt(query_name)
    c_clean = clean_company_name_lt(candidate_name)
    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    q_alnum = re.sub(r'[^a-z0-9]', '', q_clean)
    c_alnum = re.sub(r'[^a-z0-9]', '', c_clean)

    # 1. Exact match (cả có hoặc không có dấu câu)
    if q_clean == c_clean or (q_alnum and q_alnum == c_alnum):
        return True, "EXACT"

    # 2. Bóc ngoặc trực tiếp trên chuỗi gốc đã bỏ legal forms
    c_nobrack = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw_norm).strip()
    c_nobrack_clean = clean_company_name_lt(c_nobrack)
    c_nobrack_alnum = re.sub(r'[^a-z0-9]', '', c_nobrack_clean)
    if q_clean == c_nobrack_clean or (q_alnum and q_alnum == c_nobrack_alnum):
        return True, "BRACKET_MATCH"

    # 3. Phân tách theo dấu ngăn cách chuẩn (-, –, —, |, /, :, ,)
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw_norm) if p.strip()]
    for part in parts:
        p_clean = clean_company_name_lt(part)
        p_alnum = re.sub(r'[^a-z0-9]', '', p_clean)
        if p_clean and (q_clean == p_clean or (q_alnum and q_alnum == p_alnum)):
            return True, "DELIMITER_MATCH"

    return False, "NO_MATCH"


def is_valid_website(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.replace('www.', '').lower().split(':')[0]
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        if any(domain == bad or domain.endswith('.' + bad) for bad in BLACKLIST_DOMAINS):
            return False
        if any(sb in domain for sb in SUBSTRING_BLACKLIST_BRANDS):
            return False
        if any(g in domain for g in GAMBLING_KEYWORDS):
            return False
        return True
    except Exception:
        return False


def is_facebook_url(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not ('facebook.com/' in u or 'fb.com/' in u):
        return False
    bad_fb = [
        '/sharer', '/share', '/plugins/', '/tr?', '/dialog/', '/groups/',
        '/events/', '/watch/', '/marketplace/', '/login', '/policies/',
        '/privacy', '/help/', '/ads/', 'l.facebook.com'
    ]
    if any(b in u for b in bad_fb):
        return False
    parsed = urllib.parse.urlparse(u if u.startswith('http') else 'https://' + u)
    path = parsed.path.strip('/')
    return bool(path) and len(path) >= 2


def score_email_b2b_lt(email, domain=""):
    """Rule 3: Chấm điểm email B2B tối ưu cho thị trường Dệt may Litva"""
    if not email or not isinstance(email, str):
        return -1
    e = clean_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)

    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if any(d == bad or d.endswith('.' + bad) for bad in BLACKLIST_DOMAINS):
        return -1
    if any(sb in d for sb in SUBSTRING_BLACKLIST_BRANDS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'sample', 'placeholder', 'jusu', 'tavo']):
        return -1
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if u in ['mail', 'email'] and d in ['mail.lt', 'email.com', 'mail.com', 'email.lt', 'domain.com']:
        return -1

    score = 10
    clean_d = ""
    if domain:
        d_tmp = domain.strip().lower()
        if '://' in d_tmp:
            d_tmp = urllib.parse.urlparse(d_tmp).netloc
        clean_d = d_tmp.replace('www.', '').split(':')[0].split('/')[0]
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 35

    # Ưu tiên số 1: Bộ phận Nhân sự / Tuyển dụng (+50đ)
    if any(k in u for k in ['karjera', 'darbas', 'personalas', 'personalo', 'atranka', 'cv', 'hr', 'jobs', 'recruitment', 'career', 'talent']):
        score += 50
    # Ưu tiên số 2: Ban Giám Đốc / Quản lý / Sản xuất dệt may (+45đ)
    elif any(k in u for k in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'savininkas', 'pardavimai', 'prekyba', 'gamyba', 'siuvimas', 'tekstile']):
        score += 45
    # Ưu tiên số 3: Cổng liên hệ chính thức (+40đ)
    elif any(k in u for k in ['info', 'kontaktai', 'kontakt', 'office', 'biuras', 'administracija', 'sekretoriatas', 'bendras', 'pastas', 'mail']):
        score += 40
    # Tên nhân viên đích danh theo domain công ty (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # Webmail miễn phí Litva/quốc tế (+10đ)
    elif d in ['gmail.com', 'inbox.lt', 'one.lt', 'zebra.lt', 'yahoo.com', 'outlook.com']:
        score += 10
    # Kỹ thuật / Hỗ trợ / Kế toán (+5đ)
    elif any(k in u for k in ['support', 'admin', 'buhalterija', 'servisas', 'fakturos']):
        score += 5

    return score


def select_best_email(emails, domain=""):
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


def extract_emails_from_html(raw_html):
    """Bóc tách đa nguồn: Cloudflare XOR, mailto:, HTML entities, obfuscated, regex"""
    found = set()
    if not raw_html:
        return found

    decoded_html = html_lib.unescape(urllib.parse.unquote(raw_html))

    # 1. Cloudflare XOR data-cfemail & /cdn-cgi/l/email-protection#...
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', raw_html):
        dec = clean_email(decode_cf_hex(cf))
        if '@' in dec:
            found.add(dec)
    for cf in re.findall(r'/cdn-cgi/l/email-protection#([a-fA-F0-9]+)', raw_html):
        dec = clean_email(decode_cf_hex(cf))
        if '@' in dec:
            found.add(dec)

    # 2. mailto:
    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', raw_html, re.I):
        cm = clean_email(m)
        if '@' in cm:
            found.add(cm)

    # 3. Standard regex trên cả raw và decoded HTML
    for em in EMAIL_REGEX.findall(decoded_html):
        cm = clean_email(em)
        if '@' in cm:
            found.add(cm)

    # 4. Obfuscated [at] / (at) / [dot]
    for u, dom, tld in OBFUSCATED_EMAIL_REGEX.findall(decoded_html):
        cm = clean_email(f"{u}@{dom}.{tld}")
        if '@' in cm:
            found.add(cm)

    return found


def extract_facebook_links(raw_html, base_url):
    fb_links = []
    if not raw_html:
        return fb_links
    try:
        soup = BeautifulSoup(raw_html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = urllib.parse.urljoin(base_url, a['href'].strip())
            if is_facebook_url(href) and href not in fb_links:
                fb_links.append(href.split('?')[0])
    except Exception:
        pass
    return fb_links


def extract_city_from_address(addr):
    """Tách thành phố Litva gọn gàng từ chuỗi địa chỉ đầy đủ"""
    if not addr:
        return ""
    s = str(addr).strip()
    s = re.sub(r',?\s*Lithuania$', '', s, flags=re.I).strip()
    if ',' in s:
        last_part = s.split(',')[-1].strip()
    else:
        last_part = s
    last_part = re.sub(r'\b\d{4,5}\b', '', last_part).strip()
    last_part = re.sub(r'\(.*?\)', '', last_part).strip(' ,.-')
    return last_part


# ----------------------------------------------------------------------
# QUÉT WEBSITE & FACEBOOK FANPAGE (PRIORITY 10 DOM-FIRST + FALLBACK)
# ----------------------------------------------------------------------
def fetch_html_fast(url, timeout=4.5):
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=timeout, verify=False)
        if r.status_code == 200:
            return r.text
        elif r.status_code in (403, 404, 410, 500, 502, 503):
            return ""
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""


async def fetch_html_playwright(pw_page, url, timeout=15000):
    if not pw_page:
        return ""
    try:
        await pw_page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        await asyncio.sleep(1.5)
        return await pw_page.content()
    except Exception:
        return ""


async def crawl_site_and_socials(web_url, existing_fb="", pw_page=None):
    """
    Bóc tách email đa tầng tuân thủ Skill crawl-mail:
    - Tầng 1: Trang chủ + Tối đa 8 trang con bản địa hóa (Priority 10 trên thẻ <a> DOM,
              Priority 2 guess paths chỉ dùng dự phòng). Hỗ trợ Playwright fallback nếu cần.
    - Tầng 2: Tự động gom link Facebook Fanpage & quét trang About Fanpage.
    Trả về: (best_email, fb_url, email_source)
    """
    best_email = ""
    found_emails = set()
    fb_candidates = []
    if existing_fb and is_facebook_url(existing_fb):
        fb_candidates.append(existing_fb)

    root = ""
    if web_url and is_valid_website(web_url):
        if not web_url.startswith('http'):
            web_url = 'https://' + web_url
        parsed = urllib.parse.urlparse(web_url)
        root = f"{parsed.scheme}://{parsed.netloc}"

        home_html = fetch_html_fast(web_url)
        if not home_html and web_url.rstrip('/') != root.rstrip('/'):
            home_html = fetch_html_fast(root)
        if not home_html and pw_page:
            home_html = await fetch_html_playwright(pw_page, web_url)

        if home_html:
            found_emails |= extract_emails_from_html(home_html)
            for fb in extract_facebook_links(home_html, web_url):
                if fb not in fb_candidates:
                    fb_candidates.append(fb)

            best_home = select_best_email(found_emails, root)
            if best_home and score_email_b2b_lt(best_home, root) >= 85:
                return best_home, (fb_candidates[0] if fb_candidates else ""), "Website"

            # Priority 10 & 5: Thu thập link thật trên DOM trang chủ
            prioritized_links = []
            seen_norm = {web_url.rstrip('/'), root.rstrip('/')}
            try:
                soup = BeautifulSoup(home_html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    raw_href = a['href'].strip()
                    if not raw_href or raw_href.startswith('#') or raw_href.lower().startswith(('javascript:', 'tel:', 'mailto:')):
                        continue
                    full_url = urllib.parse.urljoin(web_url, raw_href)
                    norm_url = full_url.split('#')[0].rstrip('/')
                    p_full = urllib.parse.urlparse(norm_url)
                    if parsed.netloc.replace('www.', '') not in p_full.netloc.replace('www.', ''):
                        continue
                    if norm_url in seen_norm or any(norm_url.lower().endswith(ext) for ext in INVALID_EXTS):
                        continue

                    h_low = raw_href.lower()
                    t_low = a.get_text(" ", strip=True).lower()
                    prio = 0
                    if any(k in h_low or k in t_low for k in LT_CONTACT_KEYWORDS_P10):
                        prio = 10
                    elif any(k in h_low or k in t_low for k in LT_SECONDARY_KEYWORDS_P5):
                        prio = 5
                    if prio > 0:
                        seen_norm.add(norm_url)
                        prioritized_links.append((prio, full_url.split('#')[0]))
            except Exception:
                pass

            prioritized_links.sort(key=lambda x: x[0], reverse=True)
            sub_queue = [u for _, u in prioritized_links]

            # Priority 2 fallback guess paths nếu DOM ít link
            for gp in LT_GUESS_SUBPATHS:
                g_url = urllib.parse.urljoin(root, gp)
                norm_g = g_url.rstrip('/')
                if norm_g not in seen_norm:
                    seen_norm.add(norm_g)
                    sub_queue.append(g_url)

            # Duyệt tối đa 8 subpages (Skill crawl-mail)
            for sub_url in sub_queue[:8]:
                sub_html = fetch_html_fast(sub_url, timeout=3.5)
                if not sub_html:
                    continue
                found_emails |= extract_emails_from_html(sub_html)
                for fb in extract_facebook_links(sub_html, sub_url):
                    if fb not in fb_candidates:
                        fb_candidates.append(fb)
                cur_best = select_best_email(found_emails, root)
                if cur_best and score_email_b2b_lt(cur_best, root) >= 60:
                    return cur_best, (fb_candidates[0] if fb_candidates else ""), "Website"

            best_email = select_best_email(found_emails, root)
            if best_email:
                return best_email, (fb_candidates[0] if fb_candidates else ""), "Website"

    # Tầng 2: Fallback Facebook Fanpage nếu Website không có email công khai
    best_fb = fb_candidates[0] if fb_candidates else ""
    if best_fb and not best_email:
        fb_targets = [best_fb.rstrip('/') + '/about', best_fb]
        for fb_url in fb_targets:
            fb_html = fetch_html_fast(fb_url, timeout=4.5)
            if not fb_html and pw_page:
                fb_html = await fetch_html_playwright(pw_page, fb_url, timeout=12000)
            if fb_html:
                fb_emails = extract_emails_from_html(fb_html)
                fb_best = select_best_email(fb_emails, root)
                if fb_best:
                    return fb_best, best_fb, "Facebook"

    return "", best_fb, ""


# ----------------------------------------------------------------------
# NẠP DỮ LIỆU ĐẦU VÀO & ĐỒNG BỘ XUẤT FILE (RULE 1, 3, 10, 12)
# ----------------------------------------------------------------------
def load_source_dataset():
    """
    Nạp dữ liệu ưu tiên Resume từ LT_TEXT_GMAP_1ENR.csv,
    nếu chạy lần đầu sẽ kết hợp trọn vẹn metadata từ LT_TEXT_INLT_1ENR.csv + LT_TEXT_INLT_2COL.csv.
    """
    if OUTPUT_1ENR_PATH.exists():
        print(f"[*] Resume từ file Master GMAP: {OUTPUT_1ENR_PATH.name}")
        df = pd.read_csv(OUTPUT_1ENR_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    elif INPUT_1ENR_PATH.exists():
        print(f"[*] Nạp nguồn Master INLT: {INPUT_1ENR_PATH.name}")
        df = pd.read_csv(INPUT_1ENR_PATH, encoding='utf-8-sig', dtype=str).fillna('')
        if INPUT_2COL_PATH.exists():
            df2 = pd.read_csv(INPUT_2COL_PATH, encoding='utf-8-sig', dtype=str).fillna('')
            map_2col = {}
            for _, r in df2.iterrows():
                k = normalize_text(r.get('Công ty', ''))
                if k:
                    map_2col[k] = r
            for idx, r in df.iterrows():
                k = normalize_text(r.get('Cong ty', ''))
                if k in map_2col:
                    r2 = map_2col[k]
                    em2 = clean_email(r2.get('Email', ''))
                    if em2 and not clean_email(r.get('Email', '')):
                        df.at[idx, 'Email'] = em2
                    sdt2 = clean_phone_lt(r2.get('SĐT', ''))
                    if sdt2 and not clean_phone_lt(r.get('SDT', '')):
                        df.at[idx, 'SDT'] = sdt2
                    web2 = str(r2.get('Liên Hệ', '')).strip()
                    if is_valid_website(web2) and not is_valid_website(r.get('Website', '')):
                        df.at[idx, 'Website'] = web2
                    elif is_facebook_url(web2) and not str(r.get('Facebook_URL', '')).strip():
                        df.at[idx, 'Facebook_URL'] = web2
    elif INPUT_2COL_PATH.exists():
        print(f"[*] Nạp trực tiếp từ Cold Mail 2COL: {INPUT_2COL_PATH.name}")
        df2 = pd.read_csv(INPUT_2COL_PATH, encoding='utf-8-sig', dtype=str).fillna('')
        rows = []
        for idx, r in df2.iterrows():
            lh = str(r.get('Liên Hệ', '')).strip()
            web_val = lh if is_valid_website(lh) else ""
            fb_val = lh if is_facebook_url(lh) else ""
            detail_val = lh if 'litorg.cc' in lh.lower() else ""
            addr_val = str(r.get('Địa chỉ', '')).strip()
            rows.append({
                'No.': r.get('No.', str(idx + 1)),
                'Company_Code': '',
                'Cong ty': str(r.get('Công ty', '')).strip(),
                'City': extract_city_from_address(addr_val),
                'Nam_Thanh_Lap': str(r.get('Ngày đăng', '')).strip(),
                'Category': str(r.get('Category', '')).strip(),
                'Doanh_Thu': str(r.get('Lương', '')).strip(),
                'Detail_URL': detail_val,
                'SDT': str(r.get('SĐT', '')).strip(),
                'Website': web_val,
                'Facebook_URL': fb_val,
                'Email': str(r.get('Email', '')).strip(),
                'Dia chi': addr_val,
                'Nguoi_Quan_Ly': str(r.get('Người liên hệ', '')).strip(),
                'Chuc_Danh': str(r.get('Chức danh', '')).strip(),
                'Dia_Chi': addr_val
            })
        df = pd.DataFrame(rows)
    else:
        return None

    # Chuẩn hóa đầy đủ các cột cần thiết
    for col in ['Website', 'Email', 'SDT', 'Dia chi', 'Dia_Chi', 'City', 'Nguoi_Quan_Ly', 'Chuc_Danh', 'Detail_URL', 'Facebook_URL', 'Email_Source']:
        if col not in df.columns:
            df[col] = ''

    # Thu thập Facebook Fanpage URL từ Website trước khi lọc sạch Website
    for idx, r in df.iterrows():
        raw_w = str(r.get('Website', '')).strip()
        if raw_w and is_facebook_url(raw_w) and not str(r.get('Facebook_URL', '')).strip():
            df.at[idx, 'Facebook_URL'] = raw_w
        if 'Liên Hệ' in df.columns:
            raw_lh = str(r.get('Liên Hệ', '')).strip()
            if raw_lh and is_facebook_url(raw_lh) and not str(df.at[idx, 'Facebook_URL']).strip():
                df.at[idx, 'Facebook_URL'] = raw_lh

    # Đảm bảo Website không chứa link rác như litorg.cc hoặc MXH
    df['Website'] = df['Website'].apply(lambda w: w.strip() if is_valid_website(w) else '')
    # Tạo City nếu thiếu
    for idx, r in df.iterrows():
        if not str(r.get('City', '')).strip():
            addr_src = r.get('Dia_Chi', '') or r.get('Dia chi', '')
            df.at[idx, 'City'] = extract_city_from_address(addr_src)

    # Rule 12: Loại bỏ hoàn toàn Hard Blacklist
    if 'Cong ty' in df.columns:
        df = df[~df['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    return df


def export_and_sync_all_files(df):
    """Xuất 1ENR + 2COL + ONLY_EMAILS_READY (đẩy 100% Email lên đầu, SĐT có ', đồng bộ thư mục)"""
    df_out = df.copy()
    if 'Cong ty' in df_out.columns:
        df_out = df_out[~df_out['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['SDT'] = df_out['SDT'].apply(clean_phone_lt)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # Đẩy 100% doanh nghiệp có Email lên đầu (Rule 3)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi_Quan_Ly', '')).strip()
        title = str(r.get('Chuc_Danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        detail_val = str(r.get('Detail_URL', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('City', '')).strip()
        addr_val = str(r.get('Dia_Chi', '')).strip() or str(r.get('Dia chi', '')).strip()
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val if web_val else detail_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else (web_val if web_val else detail_val),
            'Địa chỉ': addr_val,
            'Lương': r.get('Doanh_Thu', ''),
            'Ngày đăng': r.get('Nam_Thanh_Lap', ''),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Category', 'Manufacture of textiles / apparel')
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')

    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready['No.'] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    # Đồng bộ cập nhật tệp gốc LT_TEXT_INLT_2COL.csv & READY (đã tạo backup trước đó)
    df_2col.to_csv(SYNC_INLT_2COL_PATH, index=False, encoding='utf-8-sig')
    df_ready.to_csv(SYNC_INLT_READY_PATH, index=False, encoding='utf-8-sig')

    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_1ENR_PATH, extra_dir / OUTPUT_1ENR_PATH.name)
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_dir / OUTPUT_READY_PATH.name)
            shutil.copy2(SYNC_INLT_2COL_PATH, extra_dir / SYNC_INLT_2COL_PATH.name)
            shutil.copy2(SYNC_INLT_READY_PATH, extra_dir / SYNC_INLT_READY_PATH.name)
        except Exception:
            pass

    return len(has_em)


# ----------------------------------------------------------------------
# TIẾN TRÌNH LÀM GIÀU CHÍNH (PHASE 1 WEBSITE + PHASE 2 GOOGLE MAPS)
# ----------------------------------------------------------------------
async def run_enrichment(headless=False, limit=None, skip_phase1=False, phase1_only=False, force_retry=False):
    df = load_source_dataset()
    if df is None:
        print(f"[!] Không tìm thấy {INPUT_2COL_PATH.name} hoặc {INPUT_1ENR_PATH.name}!")
        return

    # Tạo bản sao lưu an toàn 1 lần trước khi làm giàu Google Maps
    if INPUT_2COL_PATH.exists() and not BACKUP_2COL_PATH.exists():
        BACKUP_2COL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INPUT_2COL_PATH, BACKUP_2COL_PATH)
        print(f"[+] Đã sao lưu bản gốc tại: {BACKUP_2COL_PATH.relative_to(ROOT_DIR)}")

    # Nạp checkpoint cache JSON
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} bản ghi từ cache {CACHE_PATH.name}.")
        except Exception:
            pass

    # Áp dụng kết quả từ cache vào DataFrame ngay lập tức
    for idx, row in df.iterrows():
        comp = str(row['Cong ty']).strip()
        city = str(row.get('City', '')).strip()
        code = str(row.get('Company_Code', '')).strip()
        cache_key = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"
        if cache_key in cache:
            c = cache[cache_key]
            if c.get('Email') and not clean_email(df.at[idx, 'Email']):
                df.at[idx, 'Email'] = clean_email(c['Email'])
            if c.get('Website') and is_valid_website(c['Website']) and not is_valid_website(df.at[idx, 'Website']):
                df.at[idx, 'Website'] = c['Website']
            if c.get('SDT') and not clean_phone_lt(df.at[idx, 'SDT']):
                df.at[idx, 'SDT'] = clean_phone_lt(c['SDT'])
            if c.get('Dia_Chi') and not str(df.at[idx, 'Dia_Chi']).strip():
                df.at[idx, 'Dia_Chi'] = c['Dia_Chi']
            if c.get('Facebook_URL') and not str(df.at[idx, 'Facebook_URL']).strip():
                df.at[idx, 'Facebook_URL'] = c['Facebook_URL']
            if c.get('Email_Source') and not str(df.at[idx, 'Email_Source']).strip():
                df.at[idx, 'Email_Source'] = c['Email_Source']

    # Thống kê
    no_email_indices = [i for i, r in df.iterrows() if not clean_email(r['Email'])]
    no_sdt_only_indices = [i for i, r in df.iterrows() if clean_email(r['Email']) and not clean_phone_lt(r['SDT'])]

    print("=" * 80)
    print("🌟 LÀM GIÀU DỮ LIỆU DỆT MAY LITVA BẰNG GOOGLE MAPS (SKILL ENRICH-MAPS)")
    print(f"   - Tệp nguồn mục tiêu : {INPUT_2COL_PATH.name} ({len(df):,} công ty)")
    print(f"   - Đã có Email        : {len(df) - len(no_email_indices):,}")
    print(f"   - Đang thiếu Email   : {len(no_email_indices):,}")
    print(f"   - Thiếu mỗi SĐT      : {len(no_sdt_only_indices):,}")
    print(f"   - File xuất chuẩn    : {OUTPUT_2COL_PATH.name} & {OUTPUT_READY_PATH.name}")
    print(f"   - Chế độ trình duyệt : {'HEADLESS' if headless else 'TRỰC QUAN (headless=False, 1280x800)'}")
    print("=" * 80 + "\n")

    # ------------------------------------------------------------------
    # PHASE 1: QUÉT SÂU WEBSITE CÓ SẴN NHƯNG CHƯA CÓ EMAIL
    # ------------------------------------------------------------------
    phase1_found = 0
    if not skip_phase1:
        p1_candidates = [
            i for i in no_email_indices
            if is_valid_website(df.at[i, 'Website']) or is_facebook_url(df.at[i, 'Facebook_URL'])
        ]
        if limit:
            p1_candidates = p1_candidates[:limit]

        print("-" * 80)
        print(f"  PHASE 1: Quét sâu {len(p1_candidates)} Website / Fanpage có sẵn (Priority 10 + FB fallback)")
        print("-" * 80)

        for p1_idx, idx in enumerate(p1_candidates, 1):
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('City', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            web_url = str(row.get('Website', '')).strip()
            fb_in = str(row.get('Facebook_URL', '')).strip()
            cache_key = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"

            if not force_retry and cache_key in cache and cache[cache_key].get('phase1_done'):
                continue

            em_found, fb_found, em_src = await crawl_site_and_socials(web_url, existing_fb=fb_in)
            if fb_found and not df.at[idx, 'Facebook_URL']:
                df.at[idx, 'Facebook_URL'] = fb_found

            if em_found:
                df.at[idx, 'Email'] = em_found
                df.at[idx, 'Email_Source'] = em_src
                phase1_found += 1
                print(f"  [{p1_idx}/{len(p1_candidates)}] 🎯 WEB EMAIL ({em_src}): {comp} -> {em_found}")
            else:
                print(f"  [{p1_idx}/{len(p1_candidates)}] [-] Web không có email công khai: {web_url}")

            cache[cache_key] = {
                'Website': web_url,
                'Email': em_found or df.at[idx, 'Email'],
                'SDT': clean_phone_lt(df.at[idx, 'SDT']),
                'Dia_Chi': df.at[idx, 'Dia_Chi'],
                'Facebook_URL': fb_found or df.at[idx, 'Facebook_URL'],
                'Email_Source': em_src or df.at[idx, 'Email_Source'],
                'phase1_done': True
            }

            if p1_idx % 10 == 0:
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        cur_em = export_and_sync_all_files(df)
        print(f"[*] Hoàn thành Phase 1: +{phase1_found} email mới từ Website có sẵn (Tổng Email: {cur_em:,})\n")

        if phase1_only:
            print("[+] Dừng theo chế độ --phase1-only.")
            return

    # ------------------------------------------------------------------
    # PHASE 2: LÀM GIÀU BẰNG GOOGLE MAPS + WEBSITE + FACEBOOK (VISUAL CHROME)
    # ------------------------------------------------------------------
    pending_email = [i for i, r in df.iterrows() if not clean_email(r['Email'])]
    pending_phone = [i for i, r in df.iterrows() if clean_email(r['Email']) and not clean_phone_lt(r['SDT'])]
    all_pending = pending_email + pending_phone

    # Lọc các bản ghi đã chạy Google Maps rồi trong cache (trừ khi --force-retry)
    if not force_retry:
        pending_to_run = []
        for idx in all_pending:
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('City', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            cache_key = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"
            if cache.get(cache_key, {}).get('maps_done'):
                continue
            pending_to_run.append(idx)
    else:
        pending_to_run = all_pending

    if limit:
        pending_to_run = pending_to_run[:limit]

    print("-" * 80)
    print(f"  PHASE 2: Google Maps Enrichment (Visual Chrome) - Cần tra cứu: {len(pending_to_run):,} công ty")
    print("-" * 80)

    if not pending_to_run:
        print("[+] Toàn bộ công ty đều đã hoàn thành tra cứu!")
        export_and_sync_all_files(df)
        return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=headless,
                channel="chrome",
                args=['--start-maximized', '--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
        except Exception:
            browser = await p.chromium.launch(
                headless=headless,
                args=['--start-maximized', '--no-sandbox', '--disable-blink-features=AutomationControlled']
            )

        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='lt-LT',
            user_agent=HEADERS['User-Agent']
        )
        # Bỏ qua Google Consent popup bằng SOCS cookie
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        maps_page = await context.new_page()
        web_page = await context.new_page()

        processed = 0
        newly_found_email = 0
        newly_found_phone = 0
        newly_found_web = 0

        for idx in pending_to_run:
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('City', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            cache_key = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"

            processed += 1
            loc_str = f"{city} Lietuva".strip() if city else "Lietuva"
            search_query = f"{comp} {loc_str}"
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(search_query)}?hl=lt"

            print(f"[{processed}/{len(pending_to_run)}] 📍 Maps: {comp} ({city or 'Lietuva'})")

            found_web = ""
            found_fb = ""
            found_phone = ""
            found_addr = ""
            found_email = ""
            email_src = ""
            matched = False
            match_reason = "NO_MATCH"

            try:
                await maps_page.goto(maps_url, wait_until='domcontentloaded', timeout=MAPS_TIMEOUT)
                await asyncio.sleep(DELAY_AFTER_SEARCH)

                # Tự động xử lý màn hình Google Consent nếu vẫn xuất hiện
                if "consent.google.com" in maps_page.url.lower():
                    c_btn = await maps_page.query_selector(
                        'button:has-text("Priimti visus"), button:has-text("Accept all"), form[action*="consent"] button'
                    )
                    if c_btn:
                        await c_btn.click()
                        await asyncio.sleep(2.5)

                # Kiểm tra Google Captcha (Rule 4: rung chuông \a và chờ xử lý)
                cur_u = maps_page.url.lower()
                page_txt_low = (await maps_page.content()).lower()
                if (
                    "sorry" in cur_u
                    or "captcha" in cur_u
                    or "unusual traffic" in page_txt_low
                    or await maps_page.query_selector("iframe[src*='recaptcha']")
                ):
                    print("\a" * 3)
                    print("\n[!] PHÁT HIỆN CAPTCHA GOOGLE! Vui lòng bấm xác thực trên trình duyệt...")
                    while (
                        "sorry" in maps_page.url.lower()
                        or "captcha" in maps_page.url.lower()
                        or await maps_page.query_selector("iframe[src*='recaptcha']")
                    ):
                        await asyncio.sleep(3)
                    print("[+] Captcha đã xử lý xong! Tiếp tục tra cứu...\n")

                # Trường hợp 1: Maps mở thẳng trang chi tiết địa điểm
                if "/maps/place/" in maps_page.url:
                    h1 = await maps_page.query_selector('h1.DUwDvf')
                    cand_name = (await h1.inner_text()).strip() if h1 else ""
                    matched, match_reason = is_valid_name_match_lt(comp, cand_name)
                else:
                    # Trường hợp 2: Danh sách nhiều kết quả -> kiểm tra từng card với is_valid_name_match_lt
                    cards = await maps_page.query_selector_all('div[role="feed"] a.hfpxzc[href*="/maps/place/"], a.hfpxzc[href*="/maps/place/"]')
                    for card in cards[:5]:
                        cand_name = (await card.get_attribute('aria-label') or "").strip()
                        if not cand_name:
                            cand_name = (await card.inner_text()).strip()
                        ok, reason = is_valid_name_match_lt(comp, cand_name)
                        if ok:
                            matched, match_reason = True, reason
                            await card.click()
                            await asyncio.sleep(DELAY_AFTER_CLICK)
                            break

                # Bóc tách chi tiết khi khớp tên doanh nghiệp
                if matched:
                    # 1. Website hoặc Facebook chính thức trên thẻ Google Maps
                    web_btn = await maps_page.query_selector(
                        'a[data-item-id="authority"], a[aria-label*="Svetain"], a[aria-label*="svetain"], a[aria-label*="Website"]'
                    )
                    if web_btn:
                        w_href = (await web_btn.get_attribute('href') or "").strip()
                        if is_valid_website(w_href):
                            found_web = w_href
                        elif is_facebook_url(w_href):
                            found_fb = w_href

                    # 2. SĐT trên Google Maps
                    phone_btn = await maps_page.query_selector(
                        'button[data-item-id^="phone:"], button[aria-label*="Telefon"], button[aria-label*="Phone"]'
                    )
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id') or ""
                        if p_attr.startswith('phone:tel:'):
                            found_phone = clean_phone_lt(p_attr.replace('phone:tel:', '').strip())
                        else:
                            found_phone = clean_phone_lt(await phone_btn.inner_text())

                    # 3. Địa chỉ trên Google Maps
                    addr_btn = await maps_page.query_selector(
                        'button[data-item-id="address"], button[aria-label*="Adresas"], button[aria-label*="Address"]'
                    )
                    if addr_btn:
                        found_addr = re.sub(r'^(Adresas|Address):\s*', '', (await addr_btn.inner_text()).strip(), flags=re.I).strip()

                    # 4. Quét sâu Website + Facebook tìm Email B2B
                    target_web = found_web or (df.at[idx, 'Website'] if is_valid_website(df.at[idx, 'Website']) else "")
                    target_fb = found_fb or str(df.at[idx, 'Facebook_URL']).strip()
                    if not clean_email(df.at[idx, 'Email']) and (target_web or target_fb):
                        found_email, fb_from_site, email_src = await crawl_site_and_socials(
                            target_web, existing_fb=target_fb, pw_page=web_page
                        )
                        if fb_from_site and not found_fb:
                            found_fb = fb_from_site

                    # Fallback Tầng 3: Bóc email trực tiếp nếu xuất hiện trong panel Maps
                    if not clean_email(df.at[idx, 'Email']) and not found_email:
                        panel_html = await maps_page.content()
                        panel_emails = extract_emails_from_html(panel_html)
                        best_panel_em = select_best_email(panel_emails, target_web)
                        if best_panel_em:
                            found_email = best_panel_em
                            email_src = "GoogleMaps"

            except Exception as e:
                print(f"    [!] Lỗi xử lý Google Maps: {e}")

            # Cập nhật DataFrame
            if found_web and not is_valid_website(df.at[idx, 'Website']):
                df.at[idx, 'Website'] = found_web
                newly_found_web += 1
            if found_fb and not str(df.at[idx, 'Facebook_URL']).strip():
                df.at[idx, 'Facebook_URL'] = found_fb
            if found_phone and not clean_phone_lt(df.at[idx, 'SDT']):
                df.at[idx, 'SDT'] = found_phone
                newly_found_phone += 1
            if found_addr and not str(df.at[idx, 'Dia_Chi']).strip():
                df.at[idx, 'Dia_Chi'] = found_addr
            if found_email and not clean_email(df.at[idx, 'Email']):
                df.at[idx, 'Email'] = found_email
                df.at[idx, 'Email_Source'] = email_src
                newly_found_email += 1

            # In tiến độ
            if found_email:
                print(f"    🎯 [+] EMAIL ({email_src} | {match_reason}): {found_email} | Web: {found_web or df.at[idx, 'Website']} | SĐT: {found_phone or df.at[idx, 'SDT']}")
            elif matched and (found_web or found_phone):
                print(f"    🌐 [~] KHỚP MAPS ({match_reason}): Web: {found_web or '-'} | SĐT: {found_phone or '-'}")
            else:
                print(f"    [-] Không tìm thấy địa điểm khớp chuẩn trên Maps ({match_reason}).")

            # Ghi Cache JSON ngay từng dòng (Rule 5)
            cache[cache_key] = {
                'Website': df.at[idx, 'Website'],
                'Email': df.at[idx, 'Email'],
                'SDT': clean_phone_lt(df.at[idx, 'SDT']),
                'Dia_Chi': df.at[idx, 'Dia_Chi'],
                'Facebook_URL': df.at[idx, 'Facebook_URL'],
                'Email_Source': df.at[idx, 'Email_Source'],
                'phase1_done': True,
                'maps_done': True
            }
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            # Incremental Auto-Save CSV mỗi 5 công ty (Rule 5)
            if processed % 5 == 0:
                cur_em = export_and_sync_all_files(df)
                print(f"    [*] Checkpoint CSV ({processed}/{len(pending_to_run)} | Tổng Email: {cur_em:,} | +{newly_found_email} mail, +{newly_found_phone} SĐT, +{newly_found_web} web)")

            await asyncio.sleep(0.8)

        # Lưu hoàn chỉnh lần cuối
        cur_em = export_and_sync_all_files(df)
        await browser.close()

        print("\n" + "=" * 80)
        print("🏆 HOÀN TẤT LÀM GIÀU DỮ LIỆU DỆT MAY LITVA BẰNG GOOGLE MAPS!")
        print(f"   - Tổng doanh nghiệp sạch    : {len(df):,}")
        print(f"   - Có Email B2B (xếp dòng đầu): {cur_em:,} ({cur_em*100/len(df):.1f}%)")
        print(f"   - Bổ sung mới đợt này        : +{phase1_found + newly_found_email} Email | +{newly_found_phone} SĐT | +{newly_found_web} Website")
        print("   - Tệp đầu ra:")
        print(f"     1. {OUTPUT_1ENR_PATH.name} (Master Dataset)")
        print(f"     2. {OUTPUT_2COL_PATH.name} (Chuẩn Cold Mail 20 cột)")
        print(f"     3. {OUTPUT_READY_PATH.name} (100% Có Email sẵn sàng gửi)")
        print(f"     4. Đồng bộ lại {SYNC_INLT_2COL_PATH.name}, csdl_mlt/ và archive/lt_lithuania/")
        print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Lithuanian Textile Enterprises (LT_TEXT)")
    parser.add_argument("--headless", action="store_true", help="Chạy trình duyệt ẩn (mặc định headless=False)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty xử lý (dùng để test)")
    parser.add_argument("--skip-phase1", action="store_true", help="Bỏ qua Phase 1, đi thẳng vào Google Maps")
    parser.add_argument("--phase1-only", action="store_true", help="Chỉ chạy Phase 1 quét Website có sẵn")
    parser.add_argument("--force-retry", action="store_true", help="Quét lại kể cả các công ty đã có cờ maps_done trong cache")
    parser.add_argument("--re-export", action="store_true", help="Chỉ xuất lại toàn bộ CSV chuẩn từ Cache mà không cào")
    args = parser.parse_args()

    if args.re_export:
        df = load_source_dataset()
        if df is not None:
            if CACHE_PATH.exists():
                with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                for idx, row in df.iterrows():
                    comp = str(row['Cong ty']).strip()
                    city = str(row.get('City', '')).strip()
                    code = str(row.get('Company_Code', '')).strip()
                    k = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"
                    if k in cache:
                        c = cache[k]
                        if c.get('Email') and not clean_email(df.at[idx, 'Email']):
                            df.at[idx, 'Email'] = clean_email(c['Email'])
                        if c.get('Website') and is_valid_website(c['Website']) and not is_valid_website(df.at[idx, 'Website']):
                            df.at[idx, 'Website'] = c['Website']
                        if c.get('SDT') and not clean_phone_lt(df.at[idx, 'SDT']):
                            df.at[idx, 'SDT'] = clean_phone_lt(c['SDT'])
                        if c.get('Dia_Chi') and not str(df.at[idx, 'Dia_Chi']).strip():
                            df.at[idx, 'Dia_Chi'] = c['Dia_Chi']
                        if c.get('Facebook_URL') and not str(df.at[idx, 'Facebook_URL']).strip():
                            df.at[idx, 'Facebook_URL'] = c['Facebook_URL']
                        if c.get('Email_Source') and not str(df.at[idx, 'Email_Source']).strip():
                            df.at[idx, 'Email_Source'] = c['Email_Source']
            cnt = export_and_sync_all_files(df)
            print(f"[+] Đã xuất lại thành công! Tổng doanh nghiệp có Email: {cnt:,} / {len(df):,}")
        return

    asyncio.run(run_enrichment(
        headless=args.headless,
        limit=args.limit,
        skip_phase1=args.skip_phase1,
        phase1_only=args.phase1_only,
        force_retry=args.force_retry
    ))


if __name__ == '__main__':
    main()
