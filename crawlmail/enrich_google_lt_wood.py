# -*- coding: utf-8 -*-
"""
GOOGLE & MULTI-ENGINE ENRICHMENT - LITHUANIAN WOOD & FURNITURE (LT_WOOD)
========================================================================
Bộ giải pháp làm giàu Email & Website Doanh Nghiệp Gỗ Litva thông minh:
1. Truy vấn tìm kiếm tự nhiên (Natural Brand Query):
   - Thay vì ép dấu ngoặc kép "" và từ tiếng Anh "website" khiến Google chỉ hiện sàn danh bạ tiếng Anh,
     hệ thống dùng tên thương hiệu tự nhiên + thành phố (VD: "Siguldos baldai Vilnius", "Šiaurės baldai Joniškis").
2. Lọc SERP thông minh qua Tên miền & Từ khóa độc nhất (Distinctive Brand Token):
   - Tự động nhận diện từ khóa độc nhất (VD: 'gintauto', 'siguldos', 'siaures', 'eineros', 'balduera').
   - Nhận diện đúng website dù thẻ <title> chỉ viết "Home" hay "Nestandartiniai baldai".
3. Đối chiếu danh tính trên trang đa chiều:
   - Kiểm tra mã số doanh nghiệp Company_Code (9 chữ số Litva) trên trang chủ và trang Kontaktai.
   - Kiểm tra tên thương hiệu trong Title, Header, Footer bản quyền.
4. Vận hành trực quan (headless=False) & Xử lý Captcha thông minh:
   - Khi Google Search hiện Captcha: Tạm dừng, rung chuông \a, in cảnh báo to rõ.
   - Tự động nhận diện khi người dùng giải xong Captcha trên trình duyệt để tiếp tục cào ngay.
5. Thiết lập độ trễ an toàn tối đa cho mạng VPN (Timeout 40s, delay 2.5-3.0s).
6. Bóc tách Email B2B đa tầng & Chuẩn hóa 20 cột Cold Mail (Rule 1, 2, 3, 5, 10, 12).
"""

import sys
import os
import re
import ssl
import json
import time
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

INPUT_CSV_PATH = ROOT_DIR / "LT_WOOD_GMAP_1ENR.csv"
FALLBACK_INPUT = ROOT_DIR / "LT_WOOD_COMB_0RAW.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_WOOD_GSEA_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_WOOD_GSEA_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_WOOD_GSEA_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_google_lt_wood.json"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "lt_google_profile"

SYNC_GMAP_1ENR = ROOT_DIR / "LT_WOOD_GMAP_1ENR.csv"
SYNC_GMAP_2COL = ROOT_DIR / "LT_WOOD_GMAP_2COL.csv"
SYNC_GMAP_READY = ROOT_DIR / "LT_WOOD_GMAP_ONLY_EMAILS_READY.csv"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

# ----------------------------------------------------------------------
# MẠNG VPN & HEADERS
# ----------------------------------------------------------------------
VPN_PAGE_TIMEOUT = 40000   # 40s cho mạng VPN
VPN_SEARCH_DELAY = 3.0     # 3s sau khi search
VPN_SITE_DELAY = 3.0       # 3s sau khi mở website
VPN_STEP_DELAY = 2.5       # 2.5s giãn cách giữa các công ty

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'lt-LT,lt;q=0.9,en-US;q=0.8,en;q=0.7'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# ----------------------------------------------------------------------
# DANH SÁCH ĐEN LOẠI TRỪ (AGGREGATOR, DIRECTORY, SOCIAL, CASINO)
# ----------------------------------------------------------------------
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'tiktok.com', 'pinterest.com', 'google.com', 'maps.google.com', 'wikipedia.org',
    'yellowpages', 'tripadvisor', 'booking.com', 'yelp.com', 'sentry.io', 'wixpress.com',

    # Sàn danh bạ doanh nghiệp & tuyển dụng Litva
    'rekvizitai.vz.lt', 'rekvizitai.lt', 'info.lt', 'visalietuva.lt', 'imones.lt',
    'statyba.lt', 'cr.lt', 'okredo.com', 'scoris.lt', 'creditinfo.lt',
    'cvbankas.lt', 'cvonline.lt', 'cvmarket.lt', 'lovejob.lt', 'dirbk.lt',
    'registrucentras.lt', 'vmi.lt', 'sodra.lt', '1588.lt', '1551.lt', 'infoplius.lt',
    'imoniugidas.lt', 'imoniubaze.lt', 'verslas.lt', 'spec.lt', 'b2lithuania.com',
    'madeinvilnius.lt', 'delfi.lt', '15min.lt', 'lrytas.lt', 'tv3.lt', 'alfa.lt',
    'versloakcija.lt', 'expo.lt', 'ltkatalogas.lt', 'lamaistas.lt', 'meniu.lt',
    'ringo.lt', 'gargzdai.info', 'mokesciu-sufleris.lt', 'tax.lt', 'fsaskaita.lt',
    'saskaitos.lt', 'balticlei.lt', 'business-baltics.com', 'imoniukatalogai.lt',
    'tinklalapiai.lt', 'rekv.lt', 'proton.me', 'geltoni.lt', 'buhalteredaiva.lt',
    'tobulasbustas.lt', 'baldininkai.org', 'alio.lt', 'skelbiu.lt'
]

# Rule 12: Danh sách đen doanh nghiệp vĩnh viễn
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

GAMBLING_KEYWORDS = [
    'casino', 'kazino', 'ggbet', 'vulkan', 'betting', 'lažybos', 'lazybos',
    'poker', 'slots', 'jackpot', 'roulette', 'bukmeker', 'gambling', 'guarana.lt'
]

JUNK_EMAIL_DOMAINS = set(BLACKLIST_DOMAINS) | {
    'example.com', 'domain.com', 'yourdomain.com', 'yourcompany.com',
    'company.com', 'website.com', 'site.com', 'pavyzdys.lt', 'imone.lt', 'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'hostmaster', 'postmaster', 'root', 'dataprivacy', 'datenschutz'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname', 'username', 'user', 'name',
    'sample', 'demo', 'test', 'testing', 'placeholder', 'someone', 'nobody',
    'john.doe', 'johndoe', 'jane.doe', 'janedoe', 'jusu', 'tavo', 'vardas', 'pavarde'
}

LT_PRIORITY_KEYWORDS = [
    'kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai',
    'susisiekite', 'administracija', 'prekyba', 'pardavimai', 'gamyba',
    'contact', 'contacts', 'about', 'career', 'careers', 'jobs', 'team'
]

LT_GUESS_SUBPATHS = [
    '/kontaktai', '/kontaktai/', '/kontaktai.html', '/kontaktai.php',
    '/apie-mus', '/apie-mus/', '/apie-mus.html',
    '/karjera', '/karjera/', '/darbas',
    '/rekvizitai', '/susisiekite',
    '/contact', '/contacts', '/contact-us', '/about', '/about-us'
]

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]


# ----------------------------------------------------------------------
# CHUẨN HÓA VĂN BẢN & SO KHỚP TÊN THÔNG MINH
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    """Rule 12: Permanent blacklist company exclusion."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str):
    """Normalize Lithuanian phone number strictly with leading single quote (Rule 2)."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = str(phone_str).strip().lstrip("'")
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


def clean_email(email_str):
    """Decode and scrub zero-width spaces, %20, and phone labels from email text."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    for bad_char in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad_char, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def decode_cf(cf_hex):
    """Decode Cloudflare XOR data-cfemail."""
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def normalize_text(text):
    """Khử dấu Unicode NFKD bản địa Litva đưa về chữ thường ASCII."""
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    t = ''.join(c for c in n if not unicodedata.combining(c))
    t = re.sub(r'["\'„“”«»]', '', t).strip()
    return t


def clean_company_name(name):
    """Bóc tách tên cốt lõi, loại bỏ legal forms Litva."""
    if not name:
        return ""
    t = normalize_text(name)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    legal_forms = [
        'uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove',
        'viesoji istaiga', 'individuali imone', 'zemes ukio bendrove',
        'uab', 'mb', 'ab', 'vsi', 'ii', 'zub', 'kb', 'filialas', 'skyrius',
        'imone', 'bendra imone', 'kooperatyvas'
    ]
    for lf in legal_forms:
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return t


def get_core_tokens(name):
    """
    Trích xuất:
    1. tokens: toàn bộ từ tố trong tên công ty.
    2. distinctive: từ khóa nhận diện độc nhất (loại bỏ từ phổ thông như baldu, baldai, gamyba).
    """
    clean = clean_company_name(name)
    tokens = [t for t in re.split(r'[^a-z0-9]', clean) if t and len(t) >= 2]
    generic_words = {'baldu', 'baldai', 'gamyba', 'prekyba', 'paslaugos', 'meistrai', 'studija', 'namai', 'centras'}
    distinctive = [t for t in tokens if t not in generic_words]
    return tokens, distinctive


def is_valid_website_domain(url):
    """Kiểm tra domain hợp lệ và không nằm trong danh sách đen / cờ bạc."""
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


def is_valid_serp_candidate(company_name, result_title, result_url, result_snippet=""):
    """
    Lọc kết quả SERP thông minh:
    1. Loại trừ 100% sàn danh bạ, mạng xã hội.
    2. ƯU TIÊN SỐ 1: Tên miền chứa từ khóa nhận diện độc nhất của công ty (VD: 'bestbaldai', 'siguldosbaldai').
    3. Tiêu đề chứa tên công ty và tuân thủ quy tắc phân cách (-, |, /, :, ,).
    """
    if not is_valid_website_domain(result_url):
        return False, "INVALID_OR_BLACKLISTED_DOMAIN"

    parsed = urllib.parse.urlparse(result_url)
    domain = parsed.netloc.lower().replace('www.', '')
    dom_main = re.sub(r'[^a-z0-9]', '', domain.split('.')[0])

    tokens, distinctive = get_core_tokens(company_name)
    full_compact = ''.join(tokens)
    norm_title = normalize_text(result_title)

    # Tiêu chuẩn 1: Khớp Tên Miền Thông Minh (Domain Affinity)
    # Nếu tên miền là 'siguldosbaldai' và công ty có từ 'siguldos' -> KHỚP 100%!
    if full_compact and (full_compact in dom_main or dom_main in full_compact):
        return True, "DOMAIN_FULL_MATCH"

    if distinctive:
        # Nếu từ khóa độc nhất (VD: 'siguldos', 'gintauto', 'eineros', 'siaures') nằm trong domain
        if any(len(d) >= 3 and d in dom_main for d in distinctive):
            return True, f"DOMAIN_DISTINCTIVE_MATCH ({distinctive[0]} in {dom_main})"

    # Tiêu chuẩn 2: Khớp Tiêu Đề Kết Quả (Title Match)
    clean_q = clean_company_name(company_name)
    if clean_q and clean_q in norm_title:
        title_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', norm_title).strip()
        if clean_q == norm_title or clean_q == title_nobrackets:
            return True, "EXACT_TITLE"
        parts = [normalize_text(p).strip() for p in re.split(r'[-–—|/:,•·]', norm_title) if p.strip()]
        if any(clean_q == p or p.startswith(clean_q) or p.endswith(clean_q) for p in parts):
            return True, "DELIMITER_MATCH"

    # Tiêu chuẩn 3: Snippet chứa tên công ty và domain có đuôi .lt
    if domain.endswith('.lt') and distinctive:
        if any(d in norm_title for d in distinctive):
            return True, "DISTINCTIVE_TITLE_LT"

    return False, "NO_MATCH"


def verify_website_identity(company_name, company_code, page_title, page_text, page_url):
    """
    Đối chiếu danh tính trang web chống nhầm công ty:
    1. Mã số doanh nghiệp 9 chữ số Litva (Company_Code) xuất hiện trên web -> 100% Khớp!
    2. Tên miền chứa từ khóa nhận diện độc nhất của công ty.
    3. Tên công ty / thương hiệu xuất hiện trong Title hoặc Footer.
    """
    tokens, distinctive = get_core_tokens(company_name)
    parsed = urllib.parse.urlparse(page_url)
    domain = parsed.netloc.lower().replace('www.', '')
    dom_main = re.sub(r'[^a-z0-9]', '', domain.split('.')[0])

    norm_title = normalize_text(page_title)
    norm_text = normalize_text(page_text[:20000]) # 20k ký tự đầu
    norm_footer = normalize_text(page_text[-6000:]) # 6k ký tự cuối

    # 1. Mã số công ty xuất hiện trên web (Footer, Rekvizitai, Kontaktai)
    clean_code = re.sub(r'\D', '', str(company_code)) if company_code else ""
    if clean_code and len(clean_code) >= 7 and clean_code in page_text:
        return True, f"COMPANY_CODE_MATCH ({clean_code})"

    # 2. Tên miền khớp từ khóa độc nhất của công ty
    full_compact = ''.join(tokens)
    if full_compact and (full_compact == dom_main or full_compact in dom_main):
        if not any(park in norm_title for park in ['domain for sale', 'pirkti domena', 'parked', 'under construction']):
            return True, f"DOMAIN_FULL_MATCH ('{dom_main}')"

    if distinctive and any(len(d) >= 3 and d == dom_main or d in dom_main for d in distinctive):
        if not any(park in norm_title for park in ['domain for sale', 'pirkti domena', 'parked', 'under construction']):
            return True, f"DOMAIN_DISTINCTIVE_MATCH ('{distinctive[0]}' in '{dom_main}')"

    # 3. Tên thương hiệu xuất hiện trong Title hoặc Footer
    clean_q = clean_company_name(company_name)
    if clean_q and (clean_q in norm_title or clean_q in norm_footer):
        return True, f"BRAND_NAME_IN_TITLE_OR_FOOTER ('{clean_q}')"

    # 4. Từ khóa độc nhất xuất hiện kết hợp với 'baldai' trong Title/Footer
    if distinctive:
        for d in distinctive:
            if len(d) >= 3 and d in norm_title:
                return True, f"DISTINCTIVE_WORD_IN_TITLE ('{d}')"

    return False, "NO_IDENTITY_MATCH"


# ----------------------------------------------------------------------
# CHẤM ĐIỂM EMAIL B2B (RULE 3)
# ----------------------------------------------------------------------
def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email tối ưu cho B2B Môi giới việc làm / Doanh nghiệp Gỗ Litva."""
    if not email or not isinstance(email, str):
        return -1
    e = clean_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if any(bad in d for bad in BLACKLIST_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'sample', 'placeholder', 'jusu', 'tavo']):
        return -1
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 35

    # Priority 1: HR / Tuyển dụng (+50)
    if any(k in u for k in ['karjera', 'darbas', 'personalas', 'hr', 'jobs', 'recruitment', 'career', 'careers', 'talent']):
        score += 50
    # Priority 2: Ban Giám Đốc / Chủ sở hữu (+45)
    elif any(k in u for k in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'savininkas', 'prekyba', 'pardavimai', 'gamyba']):
        score += 45
    # Priority 3: Cổng liên hệ chính thức (+40)
    elif any(k in u for k in ['info', 'kontaktai', 'office', 'biuras', 'sekretoriatas', 'administracija', 'bendras', 'pastas']):
        score += 40
    # Named employee on official domain (+25)
    elif '.' in u and score >= 60:
        score += 25
    # Free webmail (+10)
    elif d in ['gmail.com', 'inbox.lt', 'one.lt', 'zebra.lt']:
        score += 10
    # Technical (+5)
    elif any(k in u for k in ['support', 'admin', 'buhalterija', 'it', 'servisas']):
        score += 5

    return score


def select_best_email(emails, domain=""):
    """Chọn 1 email B2B duy nhất có điểm số cao nhất."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


# ----------------------------------------------------------------------
# XỬ LÝ CAPTCHA & ĐỘ TRỄ MẠNG VPN TRÊN CHROME TRỰC QUAN
# ----------------------------------------------------------------------
async def check_and_handle_captcha(page):
    """
    Phát hiện Captcha Google Search & tạm dừng an toàn để người dùng xử lý trực quan.
    """
    is_captcha = False
    cur_url = page.url.lower()
    
    if "google.com/sorry" in cur_url or "captcha" in cur_url:
        is_captcha = True
    else:
        try:
            p_title = (await page.title() or "").lower()
            if "sorry" in p_title or "unusual traffic" in p_title or "recaptcha" in p_title:
                is_captcha = True
            elif await page.query_selector("iframe[src*='recaptcha'], form#captcha-form, div#recaptcha"):
                is_captcha = True
        except Exception:
            pass

    if not is_captcha:
        return False

    # Phát chuông cảnh báo âm thanh
    sys.stdout.write('\a\a\a')
    sys.stdout.flush()

    print("\n" + "=" * 80)
    print("🚨 [CẢNH BÁO] PHÁT HIỆN CAPTCHA GOOGLE SEARCH!")
    print("   Trình duyệt Chrome đang được mở trực quan để bạn thao tác.")
    print("   👉 Vui lòng nhìn màn hình Chrome, bấm tích giải Captcha (Verify you are human / reCAPTCHA).")
    print("   ⏱️  Hệ thống đang tạm dừng và TỰ ĐỘNG THEO DÕI:")
    print("      Ngay khi bạn giải xong và Google tải lại trang kết quả tìm kiếm,")
    print("      tiến trình sẽ TỰ ĐỘNG nhận diện và tiếp tục cào ngay lập tức!")
    print("=" * 80 + "\n")

    # Vòng lặp chờ giải Captcha (tự động phát hiện khi URL thoát khỏi /sorry)
    while True:
        await asyncio.sleep(2.5)
        try:
            check_url = page.url.lower()
            if "google.com/sorry" not in check_url and "captcha" not in check_url:
                check_title = (await page.title() or "").lower()
                if "sorry" not in check_title and "unusual traffic" not in check_title:
                    print("✅ [THÀNH CÔNG] Đã phát hiện Captcha được giải xong! Đang tiếp tục cào...\n")
                    await asyncio.sleep(VPN_SEARCH_DELAY)
                    return True
        except Exception:
            pass


# ----------------------------------------------------------------------
# QUÉT EMAIL ĐA TẦNG TRÊN WEBSITE ĐÃ ĐƯỢC XÁC THỰC
# ----------------------------------------------------------------------
async def crawl_verified_website_for_emails(page, web_url):
    """
    Mở website công ty trực quan trên Chrome để quét Email B2B đa tầng:
    DOM thẻ <a>, Cloudflare XOR, subpaths liên hệ.
    """
    if not is_valid_website_domain(web_url):
        return ""
    if not web_url.startswith('http'):
        web_url = 'https://' + web_url

    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found_emails = set()

    try:
        await page.goto(web_url, wait_until='domcontentloaded', timeout=VPN_PAGE_TIMEOUT)
        await asyncio.sleep(VPN_SITE_DELAY)

        html = await page.content()

        # 1. Bóc tách mailto:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
            clean_m = clean_email(m)
            if '@' in clean_m:
                found_emails.add(clean_m)

        # 2. Bóc tách Cloudflare XOR
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
            dec = clean_email(decode_cf(cf))
            if '@' in dec:
                found_emails.add(dec)

        # 3. Regex trên text
        for em in EMAIL_REGEX.findall(html):
            clean_em = clean_email(em)
            if score_email_b2b_lt(clean_em, root) > 0:
                found_emails.add(clean_em)

        # Nếu đã có email điểm cao (>= 80đ) ngay trang chủ thì lấy luôn
        best_home = select_best_email(found_emails, root)
        if best_home and score_email_b2b_lt(best_home, root) >= 80:
            return best_home

        # 4. Tìm các link liên hệ trên menu DOM trang chủ (Priority 10)
        dom_contact_links = []
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href'].lower()
            txt = a.get_text().lower()
            if any(k in h or k in txt for k in LT_PRIORITY_KEYWORDS):
                full = urllib.parse.urljoin(web_url, a['href'])
                if root in full and full not in dom_contact_links and '#' not in a['href']:
                    if not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)

        # Duyệt tối đa 4 subpages liên hệ
        for cl in dom_contact_links[:4]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=VPN_PAGE_TIMEOUT)
                await asyncio.sleep(2.0)
                sub_html = await page.content()
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                    clean_m = clean_email(m)
                    if '@' in clean_m:
                        found_emails.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', sub_html):
                    dec = clean_email(decode_cf(cf))
                    if '@' in dec:
                        found_emails.add(dec)
                for em in EMAIL_REGEX.findall(sub_html):
                    clean_em = clean_email(em)
                    if score_email_b2b_lt(clean_em, root) > 0:
                        found_emails.add(clean_em)
                if found_emails and any(score_email_b2b_lt(e, root) >= 70 for e in found_emails):
                    break
            except Exception:
                pass

        # 5. Fallback Guess subpaths nếu vẫn chưa có
        if not found_emails:
            for gp in LT_GUESS_SUBPATHS[:4]:
                guess_url = urllib.parse.urljoin(root, gp)
                try:
                    await page.goto(guess_url, wait_until='domcontentloaded', timeout=20000)
                    await asyncio.sleep(1.5)
                    g_html = await page.content()
                    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', g_html, re.I):
                        clean_m = clean_email(m)
                        if '@' in clean_m:
                            found_emails.add(clean_m)
                    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', g_html):
                        dec = clean_email(decode_cf(cf))
                        if '@' in dec:
                            found_emails.add(dec)
                    for em in EMAIL_REGEX.findall(g_html):
                        clean_em = clean_email(em)
                        if score_email_b2b_lt(clean_em, root) > 0:
                            found_emails.add(clean_em)
                    if found_emails:
                        break
                except Exception:
                    pass

    except Exception:
        pass

    return select_best_email(found_emails, root)


# ----------------------------------------------------------------------
# XUẤT ĐỊNH DẠNG CHUẨN COLD MAIL 20 CỘT & ĐỒNG BỘ
# ----------------------------------------------------------------------
def export_and_sync_all_files(df):
    """
    Lưu và xuất đầy đủ:
    1. LT_WOOD_GSEA_1ENR.csv
    2. LT_WOOD_GSEA_2COL.csv (đẩy 100% email lên đầu)
    3. LT_WOOD_GSEA_ONLY_EMAILS_READY.csv
    Đồng bộ sang csdl_mlt và archive/lt_lithuania.
    """
    import shutil

    df_out = df.copy()
    if 'Cong ty' in df_out.columns:
        df_out = df_out[~df_out['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['SDT'] = df_out['SDT'].apply(clean_phone_lt)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # 1. Tách email lên đầu (Rule 3)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Ghi 1ENR
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(SYNC_GMAP_1ENR, index=False, encoding='utf-8-sig')

    # 2. Ghi 2COL Cold Mail 20 cột
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi quan ly', '')).strip()
        title = str(r.get('Chuc danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('Thanh pho', '')).strip()
        addr_val = str(r.get('Dia chi', '')).strip()
        full_addr = f"{addr_val}, {city_val}".strip(', ') if city_val else addr_val

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': full_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': r.get('Nam thanh lap', ''),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Baldų gamyba / Medienos apdirbimas')
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')
    df_2col.to_csv(SYNC_GMAP_2COL, index=False, encoding='utf-8-sig')

    # 3. Ghi file CHỈ CÓ EMAIL sẵn sàng gửi
    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')
    df_ready.to_csv(SYNC_GMAP_READY, index=False, encoding='utf-8-sig')

    # 4. Đồng bộ sang csdl_mlt và archive/lt_lithuania
    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_dir / OUTPUT_READY_PATH.name)
            shutil.copy2(SYNC_GMAP_2COL, extra_dir / SYNC_GMAP_2COL.name)
        except Exception:
            pass

    return len(has_em)


# ----------------------------------------------------------------------
# TIẾN TRÌNH LÀM GIÀU CHÍNH (GOOGLE SEARCH ENGINE)
# ----------------------------------------------------------------------
async def run_google_enrichment(headless=False, limit=None, start_idx=0):
    print("=" * 80)
    print("🌲  LÀM GIÀU EMAIL DOANH NGHIỆP GỖ LITVA QUA GOOGLE SEARCH (KỊCH BẢN TỰ NHIÊN)")
    print(f"    - Tệp dữ liệu vào       : {INPUT_CSV_PATH.name}")
    print(f"    - Tệp Master 1ENR       : {OUTPUT_1ENR_PATH.name}")
    print(f"    - Tệp Cold Mail 20 cột  : {OUTPUT_2COL_PATH.name}")
    print(f"    - Tệp CHỈ CÓ EMAIL      : {OUTPUT_READY_PATH.name}")
    print(f"    - Checkpoint Cache      : {CACHE_PATH.name}")
    print(f"    - Chế độ Chrome         : TRỰC QUAN (headless={headless}, VPN delays enabled)")
    if limit:
        print(f"    - Giới hạn xử lý        : {limit} công ty")
    print("=" * 80 + "\n")

    target_path = INPUT_CSV_PATH if INPUT_CSV_PATH.exists() else FALLBACK_INPUT
    if not target_path.exists():
        print(f"[!] Lỗi: Không tìm thấy tệp dữ liệu vào tại {target_path}!")
        return

    df = pd.read_csv(target_path, encoding='utf-8-sig', dtype=str).fillna('')
    for col in ['Website', 'Email', 'SDT']:
        if col not in df.columns:
            df[col] = ''

    # Đọc Cache nếu có
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} bản ghi từ checkpoint cache.")
        except Exception as e:
            print(f"[!] Không đọc được cache: {e}")

    # Lọc danh sách công ty cần tra cứu (chưa có Email)
    pending_indices = []
    for idx, row in df.iterrows():
        em = clean_email(str(row['Email']).strip())
        if not em:
            pending_indices.append(idx)

    if start_idx > 0:
        pending_indices = [i for i in pending_indices if i >= start_idx]
    if limit:
        pending_indices = pending_indices[:limit]

    print(f"[*] Tổng số công ty: {len(df):,} | Đã có Email: {len(df) - len(pending_indices):,} | Cần tra cứu Google: {len(pending_indices):,}\n")

    if not pending_indices:
        print("[+] Toàn bộ công ty đều đã có Email B2B!")
        export_and_sync_all_files(df)
        return

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=headless,
            channel="chrome",  # Sử dụng Google Chrome thật
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--start-maximized'
            ],
            no_viewport=True,
            locale='lt-LT',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])

        processed = 0
        newly_found = 0

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('Thanh pho', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            current_web = str(row.get('Website', '')).strip()

            clean_name = clean_company_name(comp)
            tokens, distinctive = get_core_tokens(comp)
            cache_key = code if code else f"{normalize_text(comp)}::{normalize_text(city)}"

            processed += 1

            # 1. Kiểm tra cache trước
            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, 'Email'] = c['Email']
                if c.get('Website') and not df.at[idx, 'Website']:
                    df.at[idx, 'Website'] = c['Website']
                if c.get('SDT') and not df.at[idx, 'SDT']:
                    df.at[idx, 'SDT'] = c['SDT']
                if c.get('Email'):
                    print(f"[{processed}/{len(pending_indices)}] [CACHE] {comp} -> {c['Email']}")
                    continue

            # 2. Xử lý website có sẵn trước (nếu là website hợp lệ chưa quét mail)
            if is_valid_website_domain(current_web):
                web_url = current_web
                found_email = await crawl_verified_website_for_emails(page, web_url)
                if found_email:
                    df.at[idx, 'Email'] = found_email
                    newly_found += 1
                    print(f"[{processed}/{len(pending_indices)}] [+] ĐÃ CÓ WEB -> EMAIL: {comp} -> {found_email} ({web_url})")
                    cache[cache_key] = {'Website': web_url, 'Email': found_email, 'SDT': df.at[idx, 'SDT']}
                    continue

            # 3. Kịch bản tìm kiếm tự nhiên thông minh:
            # Truy vấn 1: Tên sạch + Thành phố (ví dụ: "Siguldos baldai Vilnius")
            # Truy vấn 2: Từ khóa nhận diện độc nhất + "baldai" (ví dụ: "Siguldos baldai")
            query_1 = f"{clean_name} {city}".strip()
            queries = [query_1]
            if distinctive:
                brand_q = f"{distinctive[0]} baldai"
                if brand_q != clean_name:
                    queries.append(brand_q)

            serp_candidates = []

            for s_q in queries:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(s_q)}&hl=lt"
                print(f"[{processed}/{len(pending_indices)}] 🔍 Google: {s_q}")

                try:
                    await page.goto(search_url, wait_until='domcontentloaded', timeout=VPN_PAGE_TIMEOUT)
                    await asyncio.sleep(VPN_SEARCH_DELAY)

                    # Kiểm tra và xử lý Captcha
                    await check_and_handle_captcha(page)

                    # Kiểm tra nút Website / Svetainė trong Google Knowledge Panel bên phải
                    kp_btn = await page.query_selector('a[aria-label*="svetain"], a[aria-label*="Website"], a.ab_button[href^="http"], a[data-pcu^="http"]')
                    if kp_btn:
                        kp_href = await kp_btn.get_attribute('href')
                        if is_valid_website_domain(kp_href):
                            serp_candidates.append({
                                'title': comp,
                                'url': kp_href,
                                'reason': 'GOOGLE_KNOWLEDGE_PANEL'
                            })

                    # Thu thập kết quả tìm kiếm tự nhiên
                    h3_elements = await page.query_selector_all('h3')
                    for h3 in h3_elements[:10]:
                        try:
                            title_text = (await h3.inner_text()).strip()
                            parent_a = await h3.evaluate_handle('el => el.closest("a")')
                            if parent_a:
                                href = await parent_a.get_attribute('href')
                                if href and href.startswith('http') and not any(bad in href for bad in ['google.com', 'webcache.google']):
                                    snip_text = ""
                                    container = await h3.evaluate_handle('el => el.closest("div.g, div.MjjYud, div.tF2Cpc, div[data-sokoban-container]")')
                                    if container:
                                        snip_el = await container.query_selector('div.VwiC3b, div[data-sncf="1"], span')
                                        if snip_el:
                                            snip_text = (await snip_el.inner_text()).strip()

                                    is_cand, cand_reason = is_valid_serp_candidate(comp, title_text, href, snip_text)
                                    if is_cand and not any(c['url'] == href for c in serp_candidates):
                                        serp_candidates.append({
                                            'title': title_text,
                                            'url': href,
                                            'reason': cand_reason
                                        })
                        except Exception:
                            continue

                except Exception as e:
                    print(f"    [!] Lỗi tìm kiếm: {e}")

                if serp_candidates:
                    break

            # 4. Truy cập vào website ứng viên & Đối chiếu tên công ty
            verified_web = ""
            verified_email = ""

            for cand in serp_candidates[:3]:
                cand_url = cand['url']
                cand_reason = cand['reason']

                try:
                    await page.goto(cand_url, wait_until='domcontentloaded', timeout=VPN_PAGE_TIMEOUT)
                    await asyncio.sleep(VPN_SITE_DELAY)

                    page_title = (await page.title() or "").strip()
                    page_text = (await page.inner_text('body') or "").strip()

                    # Đối chiếu danh tính công ty chặt chẽ
                    is_verified, v_reason = verify_website_identity(comp, code, page_title, page_text, cand_url)

                    if is_verified:
                        verified_web = cand_url
                        print(f"    [MATCHED & VERIFIED] {comp} -> {cand_url} [{v_reason}]")
                        
                        # Bóc tách Email B2B đa tầng
                        verified_email = await crawl_verified_website_for_emails(page, cand_url)
                        break
                    else:
                        print(f"    [REJECT] {cand_url} không trùng khớp tên/mã ({v_reason})")

                except Exception:
                    pass

            # Cập nhật kết quả
            if verified_web and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = verified_web

            if verified_email:
                df.at[idx, 'Email'] = verified_email
                newly_found += 1
                print(f"    🎯 [+] TÌM THẤY EMAIL MỚI: {comp} -> {verified_email}")
            elif verified_web:
                print(f"    🌐 [~] ĐÃ XÁC THỰC WEB (Chưa có mail trực tiếp): {comp} -> {verified_web}")
            else:
                print(f"    [-] KHÔNG TÌM THẤY WEB HỢP LỆ: {comp}")

            # Lưu vào Cache
            cache[cache_key] = {
                'Website': verified_web if verified_web else df.at[idx, 'Website'],
                'Email': verified_email if verified_email else df.at[idx, 'Email'],
                'SDT': df.at[idx, 'SDT']
            }

            # Lưu checkpoint mỗi 5 công ty (Rule 5)
            if processed % 5 == 0:
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_emails = export_and_sync_all_files(df)
                print(f"    [*] Đã lưu Checkpoint ({processed}/{len(pending_indices)} | Tổng email: {cur_emails:,} | +{newly_found} mới)")

            # Giãn cách VPN tránh spam Google
            await asyncio.sleep(VPN_STEP_DELAY)

        # Lưu lần cuối
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        total_valid_emails = export_and_sync_all_files(df)

        print("\n" + "=" * 80)
        print("🏆 HOÀN THÀNH TIẾN TRÌNH LÀM GIÀU EMAIL GOOGLE SEARCH (GỖ LITVA)!")
        print(f"   - Tổng số doanh nghiệp trong danh sách : {len(df):,}")
        print(f"   - Doanh nghiệp có EMAIL hợp lệ        : {total_valid_emails:,} ({total_valid_emails*100/len(df):.1f}%)")
        print(f"   - Email mới tìm được đợt này          : +{newly_found:,}")
        print("   - Tệp dữ liệu đã xuất:")
        print(f"     1. {OUTPUT_1ENR_PATH.name} (Full dataset master)")
        print(f"     2. {OUTPUT_2COL_PATH.name} (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)")
        print(f"     3. {OUTPUT_READY_PATH.name} (Tệp chỉ có email gửi chiến dịch)")
        print("=" * 80 + "\n")

        await context.close()


def main():
    parser = argparse.ArgumentParser(description="Google Search B2B Email Enrichment for Lithuanian Wood Enterprises")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn (mặc định hiện trình duyệt trực quan)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng công ty cần cào")
    parser.add_argument("--start-idx", type=int, default=0, help="Vị trí bắt đầu trong danh sách pending")
    parser.add_argument("--re-export", action="store_true", help="Chỉ xuất lại file Cold Mail từ 1ENR/Cache mà không chạy cào")
    args = parser.parse_args()

    if args.re_export:
        print("[*] Đang xuất lại các tệp chuẩn Cold Mail...")
        target_path = OUTPUT_1ENR_PATH if OUTPUT_1ENR_PATH.exists() else INPUT_CSV_PATH
        df = pd.read_csv(target_path, encoding='utf-8-sig', dtype=str).fillna('')
        cnt = export_and_sync_all_files(df)
        print(f"[+] Xuất thành công! Tổng số doanh nghiệp có email: {cnt:,} / {len(df):,}")
        return

    asyncio.run(run_google_enrichment(headless=args.headless, limit=args.limit, start_idx=args.start_idx))


if __name__ == '__main__':
    main()
