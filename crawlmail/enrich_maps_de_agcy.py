# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU CÔNG TY VIỆC LÀM & ZEITARBEIT ĐỨC BẰNG GOOGLE MAPS (DE_AGCY_WEBD)
========================================================================================
Tuân thủ toàn bộ quy chuẩn tại GEMINI.md và skill enrich-maps:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY. Tuyệt đối không xuất Excel.
- Rule 2: Số điện thoại luôn có dấu nháy đơn (') ở đầu (+49...).
- Rule 3: Bộ chấm điểm B2B tối ưu tuyển dụng (Bewerbung/HR +50, GF/CEO +45, Info/Kontakt +40).
          Lọc sạch 100% mail rác/template. ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU DANH SÁCH.
- Rule 4: Chế độ trực quan (headless=False) với viewport 1280x800 để người dùng theo dõi và xử lý Captcha.
- Rule 5: Lưu tăng dần mỗi 5 dòng và Checkpoint cache JSON cho phép Resume 100%.
- Rule 8: File launcher .bat thuần ASCII, không dấu tiếng Việt, không dùng ký tự '&' trần.
- Rule 9: Cung cấp đầy đủ câu lệnh Terminal cho người dùng IDE (PowerShell, CMD, Python).
- Rule 10: Tên file cố định chuẩn 17 ký tự (DE_AGCY_WEBD_1ENR.csv / DE_AGCY_WEBD_2COL.csv).
- Rule 11: So khớp tên nghiêm ngặt & thông minh (Smart & Strict Name Matcher, NFKD, loại bỏ GmbH, AG, UG...).
- Rule 12: Loại trừ 100% danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre).
- Tự động đồng bộ sang archive/de_germany/ và csdl_mlt/.
"""

import os
import sys
import re
import ssl
import json
import html
import codecs
import shutil
import argparse
import asyncio
import unicodedata
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from playwright.async_api import async_playwright

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# UTF-8 Output cho Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# PATH CONSTANTS (Rule 10: 17 characters fixed)
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_0RAW.csv"
ENR1_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_1ENR.csv"
COL2_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_2COL.csv"
READY_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_de_agcy.json"
DOMAIN_CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_domain_contacts_de.json"
ARCHIVE_DIR = ROOT_DIR / "archive" / "de_germany"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

# Rule 12: Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no', 'gelbeseiten.de',
    'wer-zu-wem.de', 'dasoertliche.de', 'dastelefonbuch.de', 'wikipedia.org', 'stepstone.de',
    'indeed.com', 'monster.de', 'xing.com', 'kununu.com', 'sentry.io', 'wixpress.com'
]

JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'wix.com', 'wixpress.com', 'wordpress.com', 'wordpress.org',
    'example.com', 'domain.com', 'email.com', 'yourcompany.com', 'yourdomain.com',
    'gelbeseiten.de', 'wer-zu-wem.de', 'facebook.com', 'instagram.com', 'linkedin.com',
    'schema.org', 'google.com'
}

JUNK_EMAIL_PREFIXES = {
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'example', 'domain', 'no-reply', 'noreply', 'donotreply',
    'privacy', 'gdpr', 'abuse', 'webmaster', 'postmaster', 'datenschutz', 'sample'
}

DE_PRIORITY_KEYWORDS = [
    'impressum', 'kontakt', 'karriere', 'jobs', 'ansprechpartner',
    'team', 'ueber-uns', 'uber-uns', 'contact', 'about', 'standorte'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Tải domain contacts cache nếu có
domain_contacts_cache = {}
if DOMAIN_CACHE_FILE.exists():
    try:
        with open(DOMAIN_CACHE_FILE, 'r', encoding='utf-8') as f:
            domain_contacts_cache = json.load(f)
    except Exception:
        domain_contacts_cache = {}


# ----------------------------------------------------------------------
# HELPER FUNCTIONS: NORMALIZATION & RULE COMPLIANCE
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    """Rule 12: Permanent Blacklist check & loại bỏ dòng quảng cáo rác từ web nguồn."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    if any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES):
        return True
    if any(ad in n_clean for ad in ['unbegrenzter zugriff', 'recherchieren sie in', 'excel-datei herunter', 'top 150.000']):
        return True
    return False


def clean_phone_de(raw_phone):
    """Chuẩn hóa số điện thoại Đức theo chuẩn Rule 2: có nháy đơn (') ở đầu (+49...)"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = urllib.parse.unquote(str(raw_phone)).strip()
    s = re.sub(r'^tel:\s*', '', s, flags=re.I)
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff']:
        s = s.replace(bad, ' ')
    s = s.lstrip("'").strip()
    s = re.sub(r'\(\s*0\s*\)', '', s)
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''

    if digits.startswith('49'):
        pass
    elif digits.startswith('0'):
        digits = '49' + digits[1:]
    else:
        digits = '49' + digits

    if len(digits) < 9 or len(digits) > 15:
        return ''

    if digits.startswith('4930') and len(digits) > 4:
        formatted = f"+49 30 {digits[4:]}"
    elif digits.startswith('4940') and len(digits) > 4:
        formatted = f"+49 40 {digits[4:]}"
    elif digits.startswith('4989') and len(digits) > 4:
        formatted = f"+49 89 {digits[4:]}"
    elif len(digits) >= 6:
        formatted = f"+49 {digits[2:5]} {digits[5:]}"
    else:
        formatted = f"+{digits}"

    return f"'{formatted}"


def clean_email(email):
    """Làm sạch ký tự ẩn (%20, non-breaking space, u003e) và loại bỏ email template."""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'^(?:u003e|u003c|&gt;|&lt;|>|<)+', '', em, flags=re.I)
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
    if user in JUNK_EMAIL_PREFIXES:
        return ""
    return em


def score_email_b2b_de(email, website_domain="", city=""):
    """
    Chấm điểm email tuyển dụng B2B Manpower Agency theo chuẩn Rule 3 (Đức):
    - Trùng domain website (+50đ)
    - Tuyển dụng / Nhân sự / Bewerbung (+50đ)
    - Ban Giám đốc / Lãnh đạo / Geschäftsführung (+45đ)
    - Liên hệ chính thức / Info / Kontakt (+40đ)
    - Trùng chi nhánh thành phố (+35đ)
    - Đích danh cá nhân domain riêng (+25đ)
    - Webmail miễn phí (+10đ)
    - Kỹ thuật / Kế toán (+5đ)
    """
    if not email:
        return 0
    em = email.lower()
    if '@' not in em:
        return 0
    user, domain = em.split('@', 1)

    score = 0
    clean_d = re.sub(r'^www\.', '', website_domain.lower()) if website_domain else ""
    if clean_d and (clean_d in domain or domain in clean_d):
        score += 50
    elif domain.endswith('.de'):
        score += 20

    # 1. Nhân sự / Tuyển dụng / Bewerbung
    if any(k in user for k in ['bewerbung', 'karriere', 'jobs', 'personal', 'hr', 'recruiting', 'praca', 'nabor']):
        score += 50
    # 2. Ban giám đốc / Quản lý
    elif any(k in user for k in ['geschaeftsfuehrung', 'gf', 'leitung', 'vorstand', 'ceo', 'director', 'manager']):
        score += 45
    # 3. Liên hệ chính thức / Bộ phận thông tin
    elif any(k in user for k in ['info', 'kontakt', 'contact', 'zentrale', 'office', 'service', 'empfang']):
        score += 40
    # 3.1 Trùng chi nhánh thành phố (vd: giessen@fara.de cho TP Gießen)
    if city:
        c_city = re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', city).lower().replace('ß', 'ss').replace('ue', 'u').replace('ae', 'a').replace('oe', 'o'))
        if len(c_city) >= 3 and c_city in user:
            score += 35
    # 4. Email cá nhân domain riêng
    if '.' in user and score >= 50:
        score += 25
    # 5. Webmail miễn phí
    elif any(w in domain for w in ['gmail.com', 'gmx.de', 'web.de', 't-online.de']):
        score += 10
    # 6. Kỹ thuật / Kế toán
    elif any(k in user for k in ['buchhaltung', 'rechnung', 'support', 'admin', 'service']):
        score += 5

    return score


def normalize_text_core(s):
    """Khử dấu Unicode NFKD, loại bỏ pháp nhân Đức và làm sạch dấu câu (Rule 11)."""
    if not s:
        return ""
    # Chuyển đổi ký tự đặc biệt Đức
    text = str(s).replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    s_norm = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()
    s_norm = re.sub(r'["\'„“”«»]', '', s_norm)

    # Loại bỏ legal forms Đức
    legal_forms = [
        'gmbh & co. kg', 'gmbh & co kg', 'gmbh & co.', 'gmbh & co',
        'gmbh', 'ag', 'ug (haftungsbeschrankt)', 'ug', 'e.k.', 'ek',
        'ohg', 'kg', 'se', 'kgaa', 'personaldienstleistungen',
        'personaldienstleister', 'personalservice', 'zeitarbeit',
        'personalvermittlung'
    ]
    for lf in legal_forms:
        s_norm = re.sub(rf'\b{re.escape(lf)}\b', ' ', s_norm)

    s_norm = re.sub(r'^[,.\-_/|\s]+|[,.\-_/|\s]+$', '', s_norm)
    s_norm = re.sub(r'\s+', ' ', s_norm).strip()
    return s_norm


def is_valid_name_match(query_name, candidate_name):
    """Smart & Strict Name Matcher theo Rule 11 GEMINI.md."""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = normalize_text_core(query_name)
    c_clean = normalize_text_core(candidate_name)

    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    # 1. Khớp tuyệt đối sau làm sạch
    if q_clean == c_clean:
        return True, "EXACT"

    # 2. Bỏ phần dịch trong ngoặc đơn/vuông của Google Maps (vd: "Employment agency")
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', candidate_name)
    c_nobrackets_clean = normalize_text_core(c_nobrackets)
    if q_clean == c_nobrackets_clean:
        return True, "BRACKET_MATCH"

    # 3. Dấu ngăn cách phân tách (-, |, /, :)
    parts = [normalize_text_core(p) for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    if any(p == q_clean for p in parts if p):
        return True, "DELIMITER_MATCH"

    # 4. Khớp chuỗi con an toàn (nếu từ khóa đủ dài >= 5 ký tự)
    if len(q_clean) >= 5 and (q_clean in c_clean or c_clean in q_clean or q_clean in c_nobrackets_clean or c_nobrackets_clean in q_clean):
        return True, "SUBSTRING_MATCH"

    return False, "NO_MATCH"


def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def fetch_html_stealth(url, timeout=2.5):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return r.read(1_000_000).decode('utf-8', errors='ignore')
    except Exception:
        pass
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=(timeout, timeout), verify=False)
        if r.status_code == 200:
            return r.text[:1_000_000]
    except Exception:
        pass
    return ""


def extract_advanced_emails_from_html(page_html, root_domain=""):
    """
    Bóc tách email đa tầng chuyên sâu cho website doanh nghiệp Đức:
    1. Decode thuộc tính data-email dạng JSON (vd: {"name":"info","host":"general-work.de"})
    2. Regex JSON name/host trong script và text
    3. Decode Cloudflare XOR (data-cfemail)
    4. Bóc tách biến JavaScript ghép chuỗi (var mailadr="info"; var maildom="...";)
    5. Giải mã HTML entities (&#64;, &#x40;, &commat;)
    6. Nhận diện obfuscated text ([at], (at), [ät], [dot])
    7. Thẻ mailto và regex chuẩn
    """
    found = set()
    if not page_html:
        return found

    # 1. data-email JSON attribute
    for m in re.finditer(r'data-email=(["\'])(.*?)\1', page_html):
        raw_val = m.group(2)
        val = html.unescape(raw_val)
        try:
            data = json.loads(val)
            if isinstance(data, dict):
                name = data.get('name') or data.get('user') or ''
                host = data.get('host') or data.get('domain') or ''
                if name and host:
                    c = clean_email(f"{name}@{host}")
                    if c:
                        found.add(c)
        except Exception:
            c = clean_email(val)
            if c:
                found.add(c)

    # 1.1 JSON in scripts/text: {"name":"...","host":"..."}
    for m in re.finditer(r'\{\s*"(?:name|user)"\s*:\s*"([^"]+)"\s*,\s*"(?:host|domain)"\s*:\s*"([^"]+)"\s*\}', page_html):
        c = clean_email(f"{m.group(1)}@{m.group(2)}")
        if c:
            found.add(c)
    for m in re.finditer(r'\{&quot;(?:name|user)&quot;:&quot;([^&]+)&quot;,&quot;(?:host|domain)&quot;:&quot;([^&]+)&quot;\}', page_html):
        c = clean_email(f"{m.group(1)}@{m.group(2)}")
        if c:
            found.add(c)

    # 2. Cloudflare XOR
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', page_html):
        c = clean_email(decode_cf(cf))
        if c:
            found.add(c)

    # 3. JavaScript concatenation patterns
    js_patterns = [
        r'var\s+mailadr\s*=\s*["\']([^"\']+)["\']\s*;\s*var\s+maildom\s*=\s*["\']([^"\']+)["\']',
        r'mailadr\s*=\s*["\']([^"\']+)["\']\s*;\s*maildom\s*=\s*["\']([^"\']+)["\']',
        r'var\s+user\s*=\s*["\']([^"\']+)["\']\s*;\s*var\s+domain\s*=\s*["\']([^"\']+)["\']',
        r'["\']mailto:["\']\s*\+\s*["\']([^"\']+)["\']\s*\+\s*["\']@["\']\s*\+\s*["\']([^"\']+)["\']',
    ]
    for pat in js_patterns:
        for m in re.findall(pat, page_html, re.I):
            c = clean_email(f"{m[0]}@{m[1]}")
            if c:
                found.add(c)

    # 3.1 WordPress Email Encoder (var ml="...", mi="...")
    for ml, mi in re.findall(r'var\s+ml\s*=\s*["\']([^"\']+)["\']\s*,\s*mi\s*=\s*["\']([^"\']+)["\']', page_html):
        try:
            dec = "".join(ml[ord(c) - 48] for c in mi if 0 <= ord(c) - 48 < len(ml))
            dec = urllib.parse.unquote(dec)
            c = clean_email(dec)
            if c:
                found.add(c)
        except Exception:
            pass

    # 3.2 ROT13 Obfuscated Emails (data-enc-email="..." / data-rot13="...")
    for enc in re.findall(r'data-(?:enc-email|rot13)=["\']([^"\']+)["\']', page_html, re.I):
        try:
            raw = enc.replace('[at]', '@').replace('(at)', '@').replace('[dot]', '.').replace('(dot)', '.')
            dec = codecs.decode(raw, 'rot_13')
            c = clean_email(dec)
            if c:
                found.add(c)
        except Exception:
            pass

    # 4. Unescape HTML entities
    unescaped = html.unescape(page_html)

    # 5. Direct Regex on unescaped HTML
    for em in EMAIL_REGEX.findall(unescaped):
        c = clean_email(em)
        if c:
            found.add(c)

    # 6. Mailto links
    for m in re.findall(r'href=["\']mailto:([^"?\'\s>]+)', unescaped, re.I):
        c = clean_email(m.split('?')[0])
        if c:
            found.add(c)

    # 7. Obfuscated text: [at], (at), [ät], [dot] (tối ưu O(N) không regex backtracking)
    obf_text = re.sub(r'\[at\]|\(at\)|\[ät\]|\(ät\)', '@', unescaped, flags=re.I)
    obf_text = re.sub(r'\[dot\]|\(dot\)|\[punkt\]|\(punkt\)', '.', obf_text, flags=re.I)
    obf_text = re.sub(r'(?<=\w)\s+@\s+(?=\w)', '@', obf_text)
    obf_text = re.sub(r'(?<=\w)\s+\.\s+(?=\w)', '.', obf_text)
    for em in EMAIL_REGEX.findall(obf_text):
        c = clean_email(em)
        if c:
            found.add(c)

    return found


def detect_client_redirect(html_content, base_url):
    """
    Tự động phát hiện chuyển hướng trang phía client (Client-side Redirect):
    1. Thẻ Meta Refresh: <meta http-equiv="refresh" content="5; url=https://promedis24.de">
    2. JavaScript location: window.location.href, location.replace, location.assign
    3. Biến config JavaScript: CONFIG.targetDomain, targetDomain, redirectUrl, redirectTo
    4. Nút bấm redirect / splash link trên landing page
    -> Lấy ngay URL đích trong 0.001s mà KHÔNG CẦN CHỜ (sleep 5s), giúp tăng tốc độ cào gấp hàng chục lần!
    """
    if not html_content:
        return None

    # 1. Meta refresh
    m_meta = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'](?:\d+\s*;\s*url=)?([^"\']+)["\']', html_content, re.I)
    if m_meta:
        target = m_meta.group(1).strip().strip("'\"")
        if target:
            return urllib.parse.urljoin(base_url, target)

    # 2. JavaScript location assignment / Config target
    patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)["\']',
        r'(?:window\.)?location\.replace\(["\'](https?://[^"\']+)["\']\)',
        r'(?:window\.)?location\.assign\(["\'](https?://[^"\']+)["\']\)',
        r'targetDomain\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'redirectUrl\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'redirectTo\s*[:=]\s*["\'](https?://[^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html_content, re.I)
        if m:
            target = m.group(1).strip()
            if target != base_url and not target.endswith(urllib.parse.urlparse(base_url).netloc):
                return urllib.parse.urljoin(base_url, target)

    # 3. Nút bấm redirect hoặc link chuyển tiếp trên splash page
    m_btn = re.search(r'<a[^>]+(?:id=["\']redirectButton["\']|class=["\'][^"\']*(?:redirect|forward)[^"\']*["\'])[^>]+href=["\']([^"\']+)["\']', html_content, re.I)
    if m_btn:
        target = m_btn.group(1).strip()
        if target.startswith('http'):
            return target

    return None


def crawl_site_for_emails(web_url, city=""):
    """
    DOM-First Multi-Tier Email Extractor cho website Đức:
    1. Kiểm tra cache domain
    2. Tự động nhận diện Client-side redirect (JS/Meta refresh) trong 0.001s
    3. Quét homepage + thẻ <a> DOM thực tế (/impressum, /kontakt, /karriere, /jobs)
    4. Giải mã toàn diện các hình thức obfuscation (data-email, JS variable, Cloudflare, entities, WP encoder, ROT13)
    5. Fallback Facebook Fanpage
    """
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith('http'):
        web_url = f"https://{web_url}"
    if any(bad in web_url.lower() for bad in BLACKLIST_DOMAINS):
        return ""

    parsed = urllib.parse.urlparse(web_url)
    root_domain = parsed.netloc.lower()
    root_domain = re.sub(r'^www\.', '', root_domain)
    root_url = f"{parsed.scheme}://{parsed.netloc}"
    original_domain = root_domain

    if root_domain in domain_contacts_cache and domain_contacts_cache[root_domain].get('email'):
        return domain_contacts_cache[root_domain]['email']

    candidate_emails = set()
    fb_links = []

    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root_url:
        home_html = fetch_html_stealth(root_url)

    # 1.1 Kiểm tra Client-Side Redirect (JS Redirect / Meta Refresh / Splash Landing)
    if home_html:
        redir_url = detect_client_redirect(home_html, web_url)
        if redir_url and redir_url.strip('/') != web_url.strip('/'):
            redir_parsed = urllib.parse.urlparse(redir_url)
            redir_domain = re.sub(r'^www\.', '', redir_parsed.netloc.lower())
            if redir_domain and not any(bad in redir_domain for bad in BLACKLIST_DOMAINS):
                redir_html = fetch_html_stealth(redir_url)
                if redir_html:
                    home_html = redir_html
                    web_url = redir_url
                    parsed = redir_parsed
                    root_domain = redir_domain
                    root_url = f"{parsed.scheme}://{parsed.netloc}"

    if home_html:
        found_home = extract_advanced_emails_from_html(home_html, root_domain)
        candidate_emails.update(found_home)

        valid_home = [e for e in candidate_emails if score_email_b2b_de(e, root_domain, city) >= 75]
        if valid_home:
            best_home = max(valid_home, key=lambda e: score_email_b2b_de(e, root_domain, city))
            domain_contacts_cache[root_domain] = {'email': best_home}
            if original_domain and original_domain != root_domain:
                domain_contacts_cache[original_domain] = {'email': best_home}
            return best_home

        # Bóc tách subpages & Facebook links từ DOM
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].strip()
                h_low = h.lower()
                txt = a.get_text().lower()
                if 'facebook.com/' in h_low and not any(bad in h_low for bad in ['sharer', 'share.php', 'plugins']):
                    if h not in fb_links:
                        fb_links.append(h)
                if any(k in h_low or k in txt for k in DE_PRIORITY_KEYWORDS):
                    if '?' in h or '#' in h:
                        continue
                    full = urllib.parse.urljoin(web_url, h)
                    sub_d = urllib.parse.urlparse(full).netloc.lower().replace('www.', '')
                    if any(bad in sub_d for bad in BLACKLIST_DOMAINS):
                        continue
                    brand = root_domain.split('.')[0]
                    is_same_org = (sub_d == root_domain) or sub_d.endswith('.' + root_domain) or (len(brand) >= 3 and brand in sub_d)
                    if not is_same_org:
                        continue
                    if full not in dom_contact_links and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)

            # Ưu tiên các trang chứa impressum, kontakt, contact lên đầu
            dom_contact_links.sort(key=lambda u: 0 if any(k in u.lower() for k in ['impressum', 'kontakt', 'contact']) else 1)

            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl, timeout=2.0)
                if not chtml:
                    continue
                found_sub = extract_advanced_emails_from_html(chtml, root_domain)
                candidate_emails.update(found_sub)

                if candidate_emails and any(score_email_b2b_de(e, root_domain) >= 60 for e in candidate_emails):
                    break
        except Exception:
            pass

    # 2. Guess paths cơ bản (chỉ quét Impressum & Kontakt chuẩn luật Đức)
    if not candidate_emails:
        for gp in [f"{root_url}/impressum", f"{root_url}/kontakt"]:
            ghtml = fetch_html_stealth(gp, timeout=1.8)
            if not ghtml:
                continue
            found_guess = extract_advanced_emails_from_html(ghtml, root_domain)
            candidate_emails.update(found_guess)
            if candidate_emails:
                break

    # 3. Facebook Fallback
    if not candidate_emails and fb_links:
        for fbl in fb_links[:1]:
            fb_html = fetch_html_stealth(fbl, timeout=2.2)
            if fb_html:
                found_fb = extract_advanced_emails_from_html(fb_html, root_domain)
                candidate_emails.update(found_fb)

    valid_candidates = [e for e in candidate_emails if score_email_b2b_de(e, root_domain, city) > 0]
    best_final = max(valid_candidates, key=lambda e: score_email_b2b_de(e, root_domain, city)) if valid_candidates else ""
    if best_final:
        domain_contacts_cache[root_domain] = {'email': best_final}
        if original_domain and original_domain != root_domain:
            domain_contacts_cache[original_domain] = {'email': best_final}
    return best_final


# ----------------------------------------------------------------------
# INCREMENTAL SAVE & EXPORT PIPELINE
# ----------------------------------------------------------------------
def save_and_reorder_files(df, output_0raw, output_1enr, output_2col, output_ready):
    """
    Xuất file 0RAW, 1ENR, 2COL và ONLY_EMAILS_READY chuẩn Rule 1, 2, 3, 10.
    ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU DANH SÁCH.
    """
    df_out = df.copy()

    # Chuẩn hóa SĐT Rule 2
    if 'Phone' in df_out.columns:
        df_out['Phone'] = df_out['Phone'].apply(clean_phone_de)
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_de)

    # Phân loại có email và không có email để đẩy 100% email lên đầu
    em_col = 'Email' if 'Email' in df_out.columns else None
    if em_col:
        is_valid_em = df_out[em_col].notna() & (df_out[em_col].astype(str).str.strip() != '') & (df_out[em_col].astype(str).str.strip().str.lower() != 'nan') & (df_out[em_col].astype(str).str.contains('@'))
        has_em = df_out[is_valid_em].copy()
        no_em = df_out[~is_valid_em].copy()
        df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    else:
        df_sorted = df_out.copy()

    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Xuất file 1ENR (Chi tiết đã làm giàu)
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

    # Cập nhật ngược lại 0RAW
    df_sorted.to_csv(output_0raw, index=False, encoding='utf-8-sig')

    # Xuất file Cold Mail 20 cột (2COL)
    col20_rows = []
    for idx, row in df_sorted.iterrows():
        cname = str(row.get('Company_Name', '') or row.get('Công ty', '')).strip()
        director = str(row.get('Managing_Director', '') or row.get('Người liên hệ', '')).strip()
        phone = str(row.get('Phone', '') or row.get('SĐT', '')).strip()
        web = str(row.get('Website', '') or row.get('Liên Hệ', '')).strip()
        raw_em = row.get('Email', '')
        email = '' if pd.isna(raw_em) or str(raw_em).strip().lower() in ['nan', 'none', ''] else str(raw_em).strip()
        addr = str(row.get('Full_Address', '') or row.get('Address', '') or row.get('Địa chỉ', '')).strip()
        city = str(row.get('City', '') or row.get('Thành phố', '')).strip()
        full_addr = addr if addr else (f"{city}, Germany" if city else "Germany")

        title = 'Geschäftsführer / Managing Director' if director else 'Director / Geschaeftsfuehrer'
        cat = str(row.get('Category', '')).strip() or 'Personalvermittlung / Zeitarbeit'

        r20 = {
            'No.': idx + 1,
            'Công ty': cname,
            'Chức danh': title,
            'Người liên hệ': director,
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else web,
            'Địa chỉ': full_addr,
            'Lương': '', 'Ngày đăng': '', 'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '', 'Last Body HTML': '', 'Trạng thái Reply': '',
            'Lần Follow-up': '0', 'Ngày Follow-up gần nhất': '', 'Mailbox đã dùng': '',
            'Category': cat
        }
        col20_rows.append(r20)

    df_2col = pd.DataFrame(col20_rows, columns=COLUMNS_20)
    df_2col.to_csv(output_2col, index=False, encoding='utf-8-sig')

    # Xuất file ONLY_EMAILS_READY (Chỉ chứa các công ty có email hợp lệ)
    df_ready = df_2col[df_2col['Email'].notna() & (df_2col['Email'].str.strip() != '') & (df_2col['Email'].str.contains('@'))].copy()
    df_ready['No.'] = range(1, len(df_ready) + 1)
    df_ready.to_csv(output_ready, index=False, encoding='utf-8-sig')

    # Đồng bộ tự động sang archive và csdl_mlt
    for target_dir in [ARCHIVE_DIR, CSDL_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        for p in [output_0raw, output_1enr, output_2col, output_ready]:
            shutil.copy2(p, target_dir / p.name)

    return len(df_ready)


# ----------------------------------------------------------------------
# GOOGLE MAPS PLAYWRIGHT ENRICHMENT RUNNER
# ----------------------------------------------------------------------
async def run_enrichment(headless=False, limit=0):
    print("=" * 80)
    print("  HE THONG LAM GIAU DU LIEU VIEC LAM & ZEITARBEIT DUC BANG GOOGLE MAPS")
    print("  Tuan thu: GEMINI.md - Rule 1, 2, 3, 4, 5, 8, 9, 10, 11, 12")
    print("=" * 80)
    print(f"[*] CSDL Thô ban dau : {RAW_CSV_PATH.name}")
    print(f"[*] CSDL Lam giau     : {ENR1_CSV_PATH.name}")
    print(f"[*] Cold Mail 20 cot  : {COL2_CSV_PATH.name}")
    print(f"[*] Tep chi email     : {READY_CSV_PATH.name}")
    print(f"[*] Checkpoint cache  : {CACHE_PATH.name}")
    print(f"[*] Che do trinh duyet: {'Headless=True (An)' if headless else 'Headless=False (Truc quan 1280x800)'}")
    print("=" * 80 + "\n")

    if not RAW_CSV_PATH.exists():
        print(f"[!] Khong tim thay file nguon: {RAW_CSV_PATH}")
        return

    df = pd.read_csv(RAW_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')

    # Nhận diện cột tên và thành phố
    name_col = 'Company_Name' if 'Company_Name' in df.columns else ('Company' if 'Company' in df.columns else 'Công ty')
    web_col = 'Website' if 'Website' in df.columns else 'Liên Hệ'
    phone_col = 'Phone' if 'Phone' in df.columns else 'SĐT'
    city_col = 'City' if 'City' in df.columns else 'Thành phố'

    # Lọc danh sách các công ty đang thiếu Email hoặc Website để ưu tiên làm giàu
    missing_mask = (df['Email'].str.strip() == '') | (df['Email'].str.strip() == 'nan')
    missing_indices = df[missing_mask].index.tolist()

    print(f"[*] Tong so doanh nghiep trong CSDL : {len(df)}")
    print(f"[*] Da co Email B2B hop le          : {len(df) - len(missing_indices)}")
    print(f"[*] CAN LAM GIAU (Dang thieu Email) : {len(missing_indices)} cong ty\n")

    if not missing_indices:
        print("[+] 100% doanh nghiep da co Email day du! Tien hanh dong bo va xuat file.")
        save_and_reorder_files(df, RAW_CSV_PATH, ENR1_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH)
        return

    # Tải cache checkpoint nếu có
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    target_list = missing_indices if limit == 0 else missing_indices[:limit]

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="de-DE"
        )
        # Google Cookie bypass cookie consent banner
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        rescued_emails = 0
        rescued_webs = 0
        rescued_phones = 0

        for idx in target_list:
            comp = str(df.at[idx, name_col]).strip()
            city = str(df.at[idx, city_col]).strip() if city_col in df.columns else ""

            # Rule 12 Exclusion
            if is_blacklisted_company(comp):
                print(f"[-] Rule 12 Exclusion: Bo qua {comp}")
                continue

            curr_i = processed + 1
            print(f"[{curr_i:04d}/{len(target_list)}] {comp[:28]:<28} | Dang xu ly...", end="\r", flush=True)

            cache_key = comp.lower()
            curr_web = str(df.at[idx, web_col]).strip()
            curr_phone = str(df.at[idx, phone_col]).strip()
            found_email = ""

            # Loại trừ link mạng xã hội và thư bạ khỏi Website chính thức
            if any(bad in curr_web.lower() for bad in ['facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'gelbeseiten.de', 'wer-zu-wem.de']):
                curr_web = ""

            # Kiểm tra cache trước: chỉ tái sử dụng nếu cache đã tìm thấy email hợp lệ
            if not found_email and cache.get(cache_key, {}).get('Email'):
                found_email = cache[cache_key]['Email']
                df.at[idx, 'Email'] = found_email
                rescued_emails += 1

            # Bước 1: Nếu đã có Website sẵn nhưng chưa có Email -> Quét sâu website với bộ giải mã obfuscation
            if curr_web and curr_web != 'nan' and not found_email:
                found_email = crawl_site_for_emails(curr_web, city)
                if found_email:
                    df.at[idx, 'Email'] = found_email
                    rescued_emails += 1

            # Bước 2: Nếu chưa có Web hoặc chưa tìm được Email -> Tìm Google Maps với Smart & Strict Match
            matched = False
            gmap_web = None
            gmap_phone = None
            gmap_addr = None

            if not curr_web or curr_web == 'nan' or not found_email:
                core_name = normalize_text_core(comp)
                q_term = f"{core_name} {city} Deutschland".strip() if city else f"{core_name} Deutschland".strip()
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                    await page.wait_for_timeout(2000)

                    # Phát hiện Captcha
                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\n\a" + "=" * 70)
                        print("[CANH BAO] Google Maps yeu cau Captcha!")
                        print("Vui long giai Captcha truc tiep tren cua so Chrome, sau do nhan Enter tai day de tiep tuc...")
                        print("=" * 70 + "\n")
                        await asyncio.get_event_loop().run_in_executor(None, input, "Nhan Enter de tiep tuc:")
                        await page.wait_for_timeout(2000)

                    # Kiểm tra danh sách kết quả (List view)
                    items = await page.query_selector_all('a[href*="/maps/place/"]')
                    if items:
                        for item in items[:4]:
                            aria_label = await item.get_attribute('aria-label') or ""
                            is_ok, reason = is_valid_name_match(comp, aria_label)
                            if is_ok:
                                await item.click()
                                await page.wait_for_timeout(2000)
                                matched = True
                                break
                    else:
                        # Kiểm tra trang chi tiết trực tiếp (Detail view)
                        title_elem = await page.query_selector('h1.DUwDvf')
                        if title_elem:
                            t_text = await title_elem.inner_text()
                            is_ok, reason = is_valid_name_match(comp, t_text)
                            matched = is_ok

                    if matched:
                        # 1. Trích xuất Website chính thức
                        web_btn = await page.query_selector('a[data-item-id="authority"]')
                        if web_btn:
                            cand_web = await web_btn.get_attribute('href')
                            if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                                gmap_web = cand_web

                        # 2. Trích xuất Số điện thoại
                        phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                        if phone_btn:
                            p_attr = await phone_btn.get_attribute('data-item-id')
                            if p_attr and p_attr.startswith('phone:tel:'):
                                gmap_phone = p_attr.replace('phone:tel:', '').strip()
                            else:
                                p_txt = await phone_btn.inner_text()
                                if re.search(r'\d{3,}', p_txt):
                                    gmap_phone = p_txt.strip()

                        # 3. Trích xuất Địa chỉ
                        addr_btn = await page.query_selector('button[data-item-id="address"]')
                        if addr_btn:
                            gmap_addr = await addr_btn.inner_text()
                except Exception:
                    pass

            # Cập nhật thông tin từ Google Maps
            if gmap_web and (not curr_web or curr_web == 'nan'):
                df.at[idx, web_col] = gmap_web
                curr_web = gmap_web
                rescued_webs += 1

            if gmap_phone and (not curr_phone or curr_phone == 'nan'):
                df.at[idx, phone_col] = clean_phone_de(gmap_phone)
                rescued_phones += 1

            if gmap_addr and ('Full_Address' in df.columns and not df.at[idx, 'Full_Address']):
                df.at[idx, 'Full_Address'] = gmap_addr

            # Quét email từ website mới tìm được qua Google Maps
            if curr_web and curr_web != 'nan' and not found_email:
                found_email = crawl_site_for_emails(curr_web, city)
                if found_email:
                    df.at[idx, 'Email'] = found_email
                    rescued_emails += 1

            # Ghi nhận cache
            cache[cache_key] = {
                'Web': curr_web,
                'Email': found_email,
                'Phone': df.at[idx, phone_col],
                'Matched': matched
            }

            processed += 1
            status_em = f"[NEW EMAIL] {found_email}" if found_email else ("Co Web, chua co mail" if curr_web else "Khong co Web")
            status_web = (curr_web[:28] + '..') if len(curr_web) > 30 else (curr_web or "Chua co web")
            status_match = " [SMART MATCH]" if matched else ""
            print(f"[{processed:04d}/{len(target_list)}] {comp[:28]:<28} | {status_web:<30} | {status_em}{status_match}          ")

            # Checkpoint lưu tăng dần mỗi 5 dòng (Rule 5)
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                with open(DOMAIN_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(domain_contacts_cache, f, ensure_ascii=False, indent=2)
                cur_total = save_and_reorder_files(df, RAW_CSV_PATH, ENR1_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH)
                print(f"  --> [CHECKPOINT] Da luu tang dan! Tong DN co Email hien tai: {cur_total}/{len(df)}")

            # Refresh page sau mỗi 25 công ty để giải phóng bộ nhớ
            if processed % 25 == 0:
                try:
                    await page.close()
                    page = await context.new_page()
                except Exception:
                    pass

        await browser.close()

    # Lưu checkpoint lần cuối
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    with open(DOMAIN_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(domain_contacts_cache, f, ensure_ascii=False, indent=2)

    final_total = save_and_reorder_files(df, RAW_CSV_PATH, ENR1_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH)

    print("\n" + "=" * 80)
    print("  HOAN TAT QUA TRINH LAM GIAU DU LIEU BANG GOOGLE MAPS!")
    print(f"[*] So cong ty da kiem tra lam giau: {processed}")
    print(f"[*] So Website moi tim duoc         : {rescued_webs}")
    print(f"[*] So SĐT moi bo sung              : {rescued_phones}")
    print(f"[*] So Email B2B moi bóc tách       : {rescued_emails}")
    print(f"[*] TONG SO DOANH NGHIEP CO EMAIL   : {final_total} / {len(df)} (100% da gom len dau)")
    print(f"[*] Tep thô cap nhat                : {RAW_CSV_PATH.name}")
    print(f"[*] Tep da lam giau                 : {ENR1_CSV_PATH.name}")
    print(f"[*] Tep ColdMail 20 cot             : {COL2_CSV_PATH.name}")
    print(f"[*] Tep chi email san sang          : {READY_CSV_PATH.name}")
    print("=" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for German Agencies")
    parser.add_argument('--headless', action='store_true', help="Chay an danh khong mo Chrome")
    parser.add_argument('--limit', type=int, default=0, help="Gioi han so cong ty lam giau (0 = toan bo)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless, limit=args.limit))
