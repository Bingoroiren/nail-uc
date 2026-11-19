# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU BẰNG GOOGLE MAPS - NÔNG NGHIỆP LITVA (LT_FARM_GMAP)
=============================================================================
Dataset nguồn: LT_FARM_WEBD_0RAW.csv -> LT_FARM_GMAP_1ENR.csv + LT_FARM_GMAP_2COL.csv

Tuân thủ nghiêm ngặt chuẩn mực kỹ thuật Antigravity & GEMINI.md:
- Skill enrich-maps: So khớp tên thông minh & nghiêm ngặt (Smart & Strict Name Matching)
- Skill crawl-mail: Ưu tiên link DOM thực tế (Priority 10), giải mã Cloudflare XOR, lọc %20
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY. Không bao giờ dùng Excel.
- Rule 2: Số điện thoại luôn có nháy đơn (') ở đầu ('+370...).
- Rule 3: Chấm điểm email B2B, giữ duy nhất 1 email tối ưu, ĐẨY 100% CTY CÓ EMAIL LÊN ĐẦU.
- Rule 4: Chế độ trình duyệt trực quan (headless=False, viewport >= 1280x800) để theo dõi và xử lý Captcha.
- Rule 5: Lưu tăng dần (Incremental Auto-Save) và Checkpoint cache JSON (100% Resume).
- Rule 8: File launcher .bat thuần ASCII, không dấu tiếng Việt, không dùng ký tự '&' trần.
- Rule 9: Cung cấp đầy đủ câu lệnh Terminal cho người dùng IDE (PowerShell, CMD, Python).
- Rule 10: Tên file cố định chuẩn 17 ký tự (LT_FARM_GMAP_1ENR.csv / LT_FARM_GMAP_2COL.csv).
- Rule 11: So khớp tên chuẩn hóa NFKD Unicode, loại bỏ pháp nhân, nhận diện ngoặc chú thích.
- Rule 12: Loại trừ 100% danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre).
- Tự động đồng bộ sang csdl_mlt/ và archive/lt_lithuania/.
"""

import sys
import os
import re
import ssl
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

# UTF-8 output cho Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# PATH CONSTANTS
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUT_CSV = ROOT_DIR / "LT_FARM_WEBD_0RAW.csv"
OUTPUT_1ENR_PATH = ROOT_DIR / "LT_FARM_GMAP_1ENR.csv"
OUTPUT_1ENR_CSDL = ROOT_DIR / "csdl_mlt" / "LT_FARM_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_FARM_GMAP_2COL.csv"
OUTPUT_2COL_CSDL = ROOT_DIR / "csdl_mlt" / "LT_FARM_GMAP_2COL.csv"
OUTPUT_2COL_ARCH = ROOT_DIR / "archive" / "lt_lithuania" / "LT_FARM_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_FARM_GMAP_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_farm.json"

# ----------------------------------------------------------------------
# NETWORK & SSL SETUP
# ----------------------------------------------------------------------
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'lt-LT,lt;q=0.9,en-US;q=0.8,en;q=0.7',
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# ----------------------------------------------------------------------
# BLACKLISTS & FILTERING (Rule 12 & Aggregators)
# ----------------------------------------------------------------------
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'statyba.lt', 'info.lt', 'visalietuva.lt', 'imones.lt', 'rekvizitai.vz.lt', 'rekvizitai.lt',
    'b2lithuania.com', 'cvbankas.lt', 'cvonline.lt', 'wikipedia.org', 'delfi.lt', '15min.lt', 'lrt.lt',
    'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'scoris.lt', 'infoin.lt', 'cr.lt',
    'creditinfo.lt', 'verslas.lt', 'madeinvilnius.lt', 'lrytas.lt', 'alfa.lt', 'tv3.lt',
    'registrucentras.lt', 'vmi.lt', 'sodra.lt', '1551.lt', 'tax.lt', 'fermos.lt', 'firmavis.com',
    'geltoni.lt', 'fsaskaita.lt', 'jars.lt', 'spec.lt', 'saskaitos.lt', 'balticlei.lt',
    'infoplius.lt', 'business-baltics.com', 'imoniukatalogai.lt', '1588.lt',
    'imoniugidas.lt', 'imoniubaze.lt', 'versloakcija.lt', 'expo.lt', 'ltkatalogas.lt',
    'cvmarket.lt', 'rekv.lt', 'proton.me', 'lovejob.lt', 'tinklalapiai.lt'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
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
    'john.doe', 'johndoe', 'jane.doe', 'janedoe'
}

LT_PRIORITY_KEYWORDS = [
    'kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai',
    'susisiekite', 'administracija', 'prekyba', 'pardavimai', 'gamyba',
    'contact', 'contacts', 'about', 'career', 'careers', 'jobs', 'team'
]

LT_GUESS_SUBPATHS = [
    '/kontaktai', '/kontaktai/', '/kontaktai.html', '/kontaktai.php',
    '/lt/kontaktai', '/en/contacts',
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
# HELPER FUNCTIONS: NORMALIZATION & STRICT MATCHING (Rule 11 & Rule 12)
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    """Rule 12: Permanent company blacklist exclusion."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def normalize_text_core(text):
    """Khử dấu Unicode NFKD bản địa đa quốc gia (ė->e, ų->u, š->s, ž->z, á->a...)."""
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    legal_forms = [
        'uzdaroji akcine bendrove', 'akcine bendrove', 'zemes ukio kooperatyvas',
        'zemes ukio bendrove', 'valstybes imone', 'private limited liability company',
        'public limited company', 'agricultural company', 'kooperatyvas',
        'uab', 'ab', 'zub', 'vsi', 'mb', 'kb', 'zuk'
    ]
    for term in legal_forms:
        n = re.sub(r'\b' + term + r'\b', ' ', n)
    n = re.sub(r'["\'„“”«»\[\]\(\)]', ' ', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip()


def is_valid_name_match(query_name, candidate_name):
    """
    Thuật toán so khớp tên nghiêm ngặt & thông minh (Rule 11 & skill enrich-maps):
    - Không phân biệt hoa thường, khử dấu NFKD.
    - Làm sạch triệt để dấu câu và pháp nhân.
    - Tách phần dịch/chú thích tiếng Anh tự động trong ngoặc () hoặc [].
    - Phân tách theo dấu phân cách chuẩn (- – — | / : ,).
    - TỪ CHỐI nếu bị chèn từ lạ nối liền không có dấu phân tách.
    """
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_norm = normalize_text_core(query_name)
    c_norm = normalize_text_core(candidate_name)

    if not q_norm or not c_norm:
        return False, "EMPTY_AFTER_NORM"

    # 1. Khớp chính xác 100%
    if q_norm == c_norm:
        return True, "EXACT"

    # 2. Khớp sau khi bỏ ngoặc chú thích/dịch () hoặc []
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', unicodedata.normalize('NFKD', str(candidate_name)).lower())
    c_nobrackets = normalize_text_core(c_nobrackets)
    if q_norm == c_nobrackets:
        return True, "BRACKET_MATCH"

    # 3. Khớp theo dấu phân cách chuẩn (- – — | / : ,)
    raw_cand_nfkd = ''.join(c for c in unicodedata.normalize('NFKD', str(candidate_name)).lower() if not unicodedata.combining(c))
    parts = [normalize_text_core(p) for p in re.split(r'[-–—|/:,]', raw_cand_nfkd) if normalize_text_core(p)]
    if any(p == q_norm for p in parts):
        return True, "DELIMITER_MATCH"

    # 4. Token Overlap an toàn cho tên dài (>= 2 từ)
    q_tokens = [t for t in q_norm.split() if len(t) > 2]
    c_tokens = [t for t in c_norm.split() if len(t) > 2]
    if len(q_tokens) >= 2 and len(c_tokens) >= 2:
        if q_tokens == c_tokens:
            return True, "TOKEN_MATCH"
        # Nếu candidate chứa trọn vẹn query tokens liên tiếp
        if ' '.join(q_tokens) in ' '.join(c_tokens) and len(c_tokens) <= len(q_tokens) + 2:
            return True, "SUBSTRING_TOKEN_MATCH"

    return False, "NO_MATCH"


def clean_phone_lt(raw_phone):
    """Chuẩn hóa số điện thoại Litva theo chuẩn Rule 2: có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = urllib.parse.unquote(str(raw_phone)).strip()
    s = re.sub(r'^tel:\s*', '', s, flags=re.I)
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff']:
        s = s.replace(bad, ' ')
    s = s.lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''

    if digits.startswith('370'):
        if len(digits) != 11:
            return ''
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[-8:]
    elif len(digits) == 8:
        digits = '370' + digits
    else:
        return ''

    if digits.startswith('370') and len(digits) == 11:
        if digits[3] == '6':
            return f"'+370 {digits[3:6]} {digits[6:]}"
        elif digits[3] == '5':
            return f"'+370 {digits[3]} {digits[4:7]} {digits[7:]}"
        else:
            return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"

    return ''


def is_valid_website(url):
    """Kiểm tra URL hợp lệ và loại bỏ mạng xã hội / sàn danh bạ / cờ bạc."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not (u.startswith('http://') or u.startswith('https://')):
        return False
    parsed = urllib.parse.urlparse(u)
    domain = parsed.netloc.lower()
    if not domain or '.' not in domain:
        return False
    if any(b in domain for b in BLACKLIST_DOMAINS):
        return False
    if any(ext in parsed.path.lower() for ext in INVALID_EXTS):
        return False
    return True


def clean_email(email):
    """Làm sạch ký tự ẩn (%20, non-breaking space) và loại bỏ email template."""
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
    em = em.lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""
    user, domain = em.split('@', 1)
    if domain in JUNK_EMAIL_DOMAINS or any(domain.endswith('.' + d) for d in JUNK_EMAIL_DOMAINS):
        return ""
    if user in SYSTEM_USERNAMES or user in TEMPLATE_USERNAMES:
        return ""
    return em


def decode_cf(code):
    """Giải mã Cloudflare Email Protection XOR Obfuscation."""
    try:
        r = int(code[:2], 16)
        return ''.join([chr(int(code[i:i+2], 16) ^ r) for i in range(2, len(code), 2)])
    except Exception:
        return ""


def score_email_b2b_lt(email, root_url=""):
    """
    Hệ thống chấm điểm Email tuyển dụng B2B Manpower Agency (Litva) theo Rule 3:
    - Trùng domain (+50đ)
    - Tuyển dụng / Nhân sự (+50đ)
    - Ban Lãnh đạo / Giám đốc (+45đ)
    - Liên hệ chính thức / Info (+40đ)
    - Đích danh cá nhân domain riêng (+25đ)
    - Webmail (+10đ)
    - Kỹ thuật / Kế toán (+5đ)
    - Email rác / Template = 0đ
    """
    em = clean_email(email)
    if not em:
        return 0
    user, domain = em.split('@', 1)

    site_domain = ""
    if root_url:
        try:
            site_domain = urllib.parse.urlparse(root_url).netloc.lower()
            site_domain = re.sub(r'^www\.', '', site_domain)
        except Exception:
            pass

    score = 0
    if site_domain and site_domain in domain:
        score += 50

    # 1. HR / Tuyển dụng
    hr_kw = ['darbas', 'idarinimas', 'praca', 'kariera', 'hr', 'personalas', 'personalne', 'jobs', 'recruitment', 'career']
    if any(k in user for k in hr_kw):
        return score + 50

    # 2. Ban Lãnh đạo / Giám đốc
    exec_kw = ['vadovas', 'direktorius', 'generalinis', 'ceo', 'director', 'manager', 'vedenie', 'riaditel', 'sales', 'pardavimai', 'komercija']
    if any(k in user for k in exec_kw):
        return score + 45

    # 3. Liên hệ chính thức / Info
    info_kw = ['info', 'kontakt', 'kontaktai', 'contact', 'biuras', 'office', 'sekretoriatas', 'administracija', 'bendra']
    if any(k in user for k in info_kw):
        return score + 40

    # 4. Cá nhân theo domain riêng
    free_webmails = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'inbox.lt', 'one.lt', 'mail.ru']
    if domain not in free_webmails and '.' in user:
        return score + 25

    # 5. Webmail miễn phí
    if domain in free_webmails:
        return score + 10

    # 6. Kế toán / kỹ thuật
    tech_kw = ['buhalterija', 'apskaita', 'faktura', 'support', 'admin', 'servis']
    if any(k in user for k in tech_kw):
        return score + 5

    return score + 15


def select_best_email(emails_set, root_url=""):
    """Chọn duy nhất 1 email có điểm B2B cao nhất."""
    if not emails_set:
        return ""
    scored = []
    for em in emails_set:
        c = clean_email(em)
        if c:
            s = score_email_b2b_lt(c, root_url)
            if s > 0:
                scored.append((s, c))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def fetch_html_stealth(url):
    """Tải HTML an toàn qua urllib với timeout ngắn và SSL bypass."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=7) as response:
            code = response.getcode()
            if code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type or 'application/xhtml' in content_type or not content_type:
                    return response.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""


def crawl_site_for_emails(web_url):
    """
    Bóc tách Email đa tầng bản địa hóa theo Skill crawl-mail (Litva):
    - Ưu tiên 10: Thẻ <a> DOM thực tế từ trang chủ (kontaktai, karjera, apie-mus...).
    - Giải mã Cloudflare data-cfemail, regex chuẩn.
    - Ưu tiên 2: Fallback subpaths đoán nếu trang chủ không thấy mailto.
    """
    if not is_valid_website(web_url):
        return ""
    if not web_url.startswith('http'):
        web_url = 'https://' + web_url

    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()

    # 1. Quét trang chủ
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)

    if home_html:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = clean_email(m)
            if clean_m:
                found.add(clean_m)
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = clean_email(decode_cf(cf))
            if dec:
                found.add(dec)
        for em in EMAIL_REGEX.findall(home_html):
            c_em = clean_email(em)
            if c_em and score_email_b2b_lt(c_em, root) > 0:
                found.add(c_em)

        best_home = select_best_email(found, root)
        if best_home and score_email_b2b_lt(best_home, root) >= 80:
            return best_home

        # Priority 10: Quét link DOM thực tế trên menu trang chủ
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].lower()
                txt = a.get_text().lower()
                if any(k in h or k in txt for k in LT_PRIORITY_KEYWORDS):
                    full = urllib.parse.urljoin(web_url, a['href'])
                    if full not in dom_contact_links and '#' not in a['href'] and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)

            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl)
                if not chtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = clean_email(m)
                    if clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = clean_email(decode_cf(cf))
                    if dec:
                        found.add(dec)
                for em in EMAIL_REGEX.findall(chtml):
                    c_em = clean_email(em)
                    if c_em and score_email_b2b_lt(c_em, root) > 0:
                        found.add(c_em)
                if found and any(score_email_b2b_lt(e, root) >= 70 for e in found):
                    break
        except Exception:
            pass

        # Priority 2: Fallback Guess Paths
        if not found:
            for gp in LT_GUESS_SUBPATHS[:5]:
                guess_url = urllib.parse.urljoin(root, gp)
                ghtml = fetch_html_stealth(guess_url)
                if not ghtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                    clean_m = clean_email(m)
                    if clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', ghtml):
                    dec = clean_email(decode_cf(cf))
                    if dec:
                        found.add(dec)
                for em in EMAIL_REGEX.findall(ghtml):
                    c_em = clean_email(em)
                    if c_em and score_email_b2b_lt(c_em, root) > 0:
                        found.add(c_em)
                if found:
                    break

    return select_best_email(found, root)


# ----------------------------------------------------------------------
# SAVE & REORDER: ĐẨY 100% CTY CÓ EMAIL LÊN ĐẦU (Rule 3 & Rule 10)
# ----------------------------------------------------------------------
def save_and_reorder(df):
    """
    Lưu tiến trình và xuất file chuẩn 2COL Cold Mail CSV và 1ENR Master.
    - Loại bỏ triệt để danh sách đen vĩnh viễn Rule 12.
    - Sắp xếp 100% doanh nghiệp CÓ EMAIL lên đầu (with_email + without_email).
    - Chuẩn hóa số điện thoại có nháy đơn (') ở đầu.
    """
    df_out = df.copy()

    # Rule 12 Filter
    name_col = 'Company_Name' if 'Company_Name' in df_out.columns else ('Cong ty' if 'Cong ty' in df_out.columns else 'Công ty')
    if name_col in df_out.columns:
        df_out = df_out[~df_out[name_col].apply(is_blacklisted_company)].reset_index(drop=True)

    phone_col = 'Phone' if 'Phone' in df_out.columns else ('SDT' if 'SDT' in df_out.columns else 'SĐT')
    email_col = 'Email' if 'Email' in df_out.columns else 'email'

    df_out[phone_col] = df_out[phone_col].apply(clean_phone_lt)
    df_out[email_col] = df_out[email_col].apply(clean_email)

    has_em = df_out[df_out[email_col] != ''].copy()
    no_em = df_out[df_out[email_col] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # 1. Xuất file thô hoàn thiện 1ENR
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')
    OUTPUT_1ENR_CSDL.parent.mkdir(parents=True, exist_ok=True)
    df_sorted.to_csv(OUTPUT_1ENR_CSDL, index=False, encoding='utf-8-sig')

    # 2. Xuất file chuẩn Cold Mail 20 cột (2COL)
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get(name_col, '')).strip()
        manager = str(r.get('Nguoi quan ly', '') or r.get('Người liên hệ', '')).strip()
        title = str(r.get('Chuc danh', '') or r.get('Chức danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '') or r.get('Liên Hệ', '')).strip()
        email_val = str(r.get(email_col, '')).strip()
        phone_val = clean_phone_lt(r.get(phone_col, ''))

        addr_val = str(r.get('Full_Address', '') or r.get('Địa chỉ', '') or r.get('address', '')).strip()
        if not addr_val:
            loc = str(r.get('Location', '') or r.get('Municipality', '') or r.get('Thanh pho', '')).strip()
            addr_val = f"{loc}, Lithuania" if loc else "Lithuania"

        wage_val = str(r.get('Average_Wage', '') or r.get('avg_wage', '') or r.get('Lương', '')).strip()
        founded_val = str(r.get('Fin_Year', '') or r.get('fin_year', '') or r.get('Ngày đăng', '')).strip()
        cat_val = str(r.get('Sub_Industry', '') or r.get('Category', '') or r.get('sub_industry', '')).strip()
        if not cat_val:
            cat_val = 'Agriculture & Farming'

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': addr_val,
            'Lương': wage_val,
            'Ngày đăng': founded_val,
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
    OUTPUT_2COL_CSDL.parent.mkdir(parents=True, exist_ok=True)
    df_2col.to_csv(OUTPUT_2COL_CSDL, index=False, encoding='utf-8-sig')
    OUTPUT_2COL_ARCH.parent.mkdir(parents=True, exist_ok=True)
    df_2col.to_csv(OUTPUT_2COL_ARCH, index=False, encoding='utf-8-sig')

    # 3. Xuất file rút gọn chỉ chứa các công ty có email
    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    return len(has_em)


# ----------------------------------------------------------------------
# MAIN ENRICHMENT ENGINE
# ----------------------------------------------------------------------
async def run_enrichment(input_csv=None, headless=False, limit=None, start_idx=0, skip_phase1=False, phase1_only=False):
    target_input = Path(input_csv) if input_csv else DEFAULT_INPUT_CSV
    print("=" * 80)
    print("  GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN AGRICULTURE (LT_FARM_GMAP)")
    print(f"  Input File  : {target_input}")
    print(f"  Output 1ENR : {OUTPUT_1ENR_PATH}")
    print(f"  Output 2COL : {OUTPUT_2COL_PATH}")
    print(f"  Only Emails : {OUTPUT_READY_PATH}")
    print(f"  Cache File  : {CACHE_PATH}")
    print(f"  Browser     : {'HEADLESS' if headless else 'VISUAL (Headless=False, 1280x800)'}")
    if limit:
        print(f"  Limit Count : {limit}")
    if skip_phase1:
        print("  Options     : SKIP PHASE 1 (Direct to Google Maps)")
    elif phase1_only:
        print("  Options     : PHASE 1 ONLY (Fast Website Crawl)")
    print("=" * 80 + "\n")

    if not target_input.exists():
        print(f"[ERROR] Target file '{target_input}' not found!")
        return

    # Check if 1ENR already exists for resume, otherwise read input
    target_read_path = OUTPUT_1ENR_PATH if OUTPUT_1ENR_PATH.exists() else target_input
    print(f"[*] Reading source dataset from: {target_read_path.name}")
    df = pd.read_csv(target_read_path, encoding='utf-8-sig', dtype=str).fillna('')

    # Ensure common column names
    name_col = 'Company_Name' if 'Company_Name' in df.columns else ('Cong ty' if 'Cong ty' in df.columns else 'Công ty')
    phone_col = 'Phone' if 'Phone' in df.columns else ('SDT' if 'SDT' in df.columns else 'SĐT')
    email_col = 'Email' if 'Email' in df.columns else 'email'
    web_col = 'Website' if 'Website' in df.columns else ('Liên Hệ' if 'Liên Hệ' in df.columns else 'website')
    loc_col = 'Location' if 'Location' in df.columns else ('Thanh pho' if 'Thanh pho' in df.columns else 'Địa chỉ')
    code_col = 'Company_Code' if 'Company_Code' in df.columns else ''

    for col in [web_col, email_col, phone_col]:
        if col not in df.columns:
            df[col] = ''

    # Load cache
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache)} cached company records from {CACHE_PATH.name}.")
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Build memory map of known valid emails from current df
    for idx, row in df.iterrows():
        comp = str(row[name_col]).strip()
        loc = str(row.get(loc_col, '')).strip()
        code = str(row.get(code_col, '')).strip() if code_col else ''
        cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(loc)}"
        em = clean_email(str(row[email_col]).strip())
        if em and not any(bad in em for bad in BLACKLIST_DOMAINS):
            if cache_key not in cache or not cache[cache_key].get('Email'):
                cache[cache_key] = {
                    'Web': str(row.get(web_col, '')).strip(),
                    'Email': em,
                    'Phone': clean_phone_lt(str(row.get(phone_col, '')).strip())
                }

    # -------------------------------------------------------------
    # PHASE 1: Direct Website Email Crawling for existing official URLs
    # -------------------------------------------------------------
    direct_found = 0
    if not skip_phase1:
        print("\n" + "-" * 80)
        print("  PHASE 1: Direct Website Email Crawling for Existing Official URLs")
        print("-" * 80)
        direct_candidates = []
        for idx, row in df.iterrows():
            em = clean_email(str(row[email_col]).strip())
            web = str(row.get(web_col, '')).strip()
            if not em and is_valid_website(web):
                direct_candidates.append(idx)

        total_direct_avail = len(direct_candidates)
        if limit:
            direct_candidates = direct_candidates[:limit]

        print(f"[*] Found {total_direct_avail} companies with official websites pending email crawl...")
        for c_idx in direct_candidates:
            row = df.loc[c_idx]
            comp = str(row[name_col]).strip()
            web = str(row.get(web_col, '')).strip()
            code = str(row.get(code_col, '')).strip() if code_col else ''
            loc = str(row.get(loc_col, '')).strip()
            cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(loc)}"

            if cache_key in cache:
                if cache[cache_key].get('Email'):
                    df.at[c_idx, email_col] = cache[cache_key]['Email']
                continue

            em_found = crawl_site_for_emails(web)
            if em_found:
                df.at[c_idx, email_col] = em_found
                direct_found += 1
                print(f"  [+] DIRECT WEB EMAIL: {comp} -> {em_found} ({web})")
                cache[cache_key] = {
                    'Web': web,
                    'Email': em_found,
                    'Phone': clean_phone_lt(str(row.get(phone_col, '')).strip())
                }
            else:
                if cache_key not in cache:
                    cache[cache_key] = {
                        'Web': web,
                        'Email': '',
                        'Phone': clean_phone_lt(str(row.get(phone_col, '')).strip())
                    }

        if direct_found > 0:
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cnt = save_and_reorder(df)
            print(f"[*] Phase 1 complete: Discovered +{direct_found} emails directly from websites! (Total emails: {cnt})")

        if phase1_only:
            print("\n[+] Phase 1 only requested. Exiting without launching Google Maps.")
            return

    # -------------------------------------------------------------
    # PHASE 2: Google Maps Enrichment for remaining rows missing Email
    # -------------------------------------------------------------
    print("\n" + "-" * 80)
    print("  PHASE 2: Google Maps Search & Enrichment (Visual Chrome)")
    print("-" * 80)
    pending_indices = []
    for idx, row in df.iterrows():
        em = clean_email(str(row[email_col]).strip())
        if not em:
            pending_indices.append(idx)

    if start_idx > 0:
        pending_indices = [i for i in pending_indices if i >= start_idx]
    if limit:
        pending_indices = pending_indices[:limit]

    print(f"[*] Total companies: {len(df)} | Already have Email: {len(df) - len(pending_indices)} | Needing Maps: {len(pending_indices)}")

    if not pending_indices:
        print("[+] All companies already have emails!")
        final_cnt = save_and_reorder(df)
        print(f"[+] Final valid email count: {final_cnt}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--js-flags=--max-old-space-size=512"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="lt-LT"
        )
        # Pre-inject Google consent cookie to bypass consent popup
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        newly_found = 0

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row[name_col]).strip()
            loc = str(row.get(loc_col, '')).strip()
            code = str(row.get(code_col, '')).strip() if code_col else ''
            cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(loc)}"

            processed += 1

            # Check cache first
            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, email_col] = c['Email']
                if c.get('Web') and not df.at[idx, web_col]:
                    df.at[idx, web_col] = c['Web']
                if c.get('Phone') and not df.at[idx, phone_col]:
                    df.at[idx, phone_col] = c['Phone']
                continue

            # Construct Maps Query
            loc_term = loc if loc else "Lietuva"
            query = f"{comp} {loc_term} Lietuva".strip()
            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"

            web_url = None
            phone_val = None
            matched = False

            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=14000)
                await asyncio.sleep(2.0)

                # Check Captcha or Consent
                if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                    print("\n\a[WARNING] Google Captcha detected! Please solve it on browser window...\n")
                    await asyncio.sleep(15.0)

                # Case A: Multiple place results in sidebar
                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    for item in items[:4]:
                        aria_label = await item.get_attribute('aria-label') or ""
                        is_ok, match_type = is_valid_name_match(comp, aria_label)
                        if is_ok:
                            await item.click()
                            await asyncio.sleep(2.0)
                            matched = True
                            break
                else:
                    # Case B: Directly opened place detail view
                    title_elem = await page.query_selector('h1.DUwDvf')
                    if title_elem:
                        t_text = await title_elem.inner_text()
                        is_ok, match_type = is_valid_name_match(comp, t_text)
                        matched = is_ok

                # Extract details if matched
                if matched:
                    # Extract Website
                    web_btn = await page.query_selector('a[data-item-id="authority"]')
                    if web_btn:
                        cand_web = await web_btn.get_attribute('href')
                        if is_valid_website(cand_web):
                            web_url = cand_web

                    # Extract Phone
                    phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id')
                        if p_attr and p_attr.startswith('phone:tel:'):
                            phone_val = p_attr.replace('phone:tel:', '').strip()
                        else:
                            phone_val = await phone_btn.inner_text()

            except Exception:
                pass

            email = ""
            if web_url and matched:
                email = crawl_site_for_emails(web_url)

            # Apply updates
            if web_url and matched and not df.at[idx, web_col]:
                df.at[idx, web_col] = web_url
            if phone_val and matched and not df.at[idx, phone_col]:
                df.at[idx, phone_col] = clean_phone_lt(phone_val)

            if email:
                df.at[idx, email_col] = email
                newly_found += 1
                print(f"[{processed}/{len(pending_indices)}] [+] NEW EMAIL: {comp} -> {email} ({web_url})")
            elif matched and web_url:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED WEB: {comp} -> {web_url} (No direct email)")
            elif matched and phone_val:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED PHONE: {comp} -> {phone_val}")
            else:
                print(f"[{processed}/{len(pending_indices)}] [-] NO MATCH: {comp} ({loc})")

            # Update Cache
            cache[cache_key] = {
                'Web': web_url if (web_url and matched) else df.at[idx, web_col],
                'Email': email if email else df.at[idx, email_col],
                'Phone': clean_phone_lt(phone_val) if (phone_val and matched) else clean_phone_lt(df.at[idx, phone_col])
            }

            # Incremental Auto-Save every 5 companies (Rule 5)
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                save_and_reorder(df)

        await browser.close()

    # Final Save and Re-order
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    final_emails = save_and_reorder(df)

    print("\n" + "=" * 80)
    print("  HOAN TAT LAM GIAU DU LIEU GOOGLE MAPS!")
    print(f"  Tong so DN xu ly: {processed}")
    print(f"  So Email B2B moi phat hien: +{newly_found}")
    print(f"  Tong so Email hop le hien co: {final_emails} (Da day 100% len dong dau tien)")
    print(f"  Tep Master 1ENR: {OUTPUT_1ENR_PATH.name}")
    print(f"  Tep ColdMail 2COL: {OUTPUT_2COL_PATH.name}")
    print(f"  Tep chi Email: {OUTPUT_READY_PATH.name}")
    print("=" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Google Maps Data Enrichment for Lithuanian Agriculture Enterprises")
    parser.add_argument('--input', type=str, default=None, help="Input CSV path (default: LT_FARM_WEBD_0RAW.csv)")
    parser.add_argument('--headless', action='store_true', help="Run browser in headless mode (default: False)")
    parser.add_argument('--limit', type=int, default=None, help="Limit number of companies to enrich")
    parser.add_argument('--start', type=int, default=0, help="Start row index")
    parser.add_argument('--skip-phase1', action='store_true', help="Skip phase 1 website crawl, jump directly to Maps")
    parser.add_argument('--phase1-only', action='store_true', help="Run only phase 1 (direct website crawl)")

    args = parser.parse_args()
    asyncio.run(run_enrichment(
        input_csv=args.input,
        headless=args.headless,
        limit=args.limit,
        start_idx=args.start,
        skip_phase1=args.skip_phase1,
        phase1_only=args.phase1_only
    ))
