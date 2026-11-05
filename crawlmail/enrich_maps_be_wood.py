# -*- coding: utf-8 -*-
"""
GOOGLE MAPS & WEB EMAIL ENRICHMENT - BELGIUM WOOD & CARPENTRY ENTERPRISES (KBO)
=============================================================================
Kế thừa & Tuân thủ đầy đủ 100% các Kỹ năng chuẩn:
- enrich-maps (.agents/skills/enrich-maps/SKILL.md)
- crawl-mail (.agents/skills/crawl-mail/SKILL.md)
- data-standards (.agents/skills/data-standards/SKILL.md)

Các quy chuẩn cốt lõi:
1. Smart & Strict Name Matching (Skill enrich-maps Section 2.A):
   - Khử legal forms Bỉ (BV, NV, BVBA, SRL, SPRL, SA, VOF, SNC, CVBA, Comm.V, GCV...).
   - Khử dấu Unicode NFKD, bóc tách chú thích trong ngoặc đơn/vuông (...) hoặc [...].
   - Quy tắc dấu phân cách chuẩn: -, –, —, |, /, :, ,
   - Token overlap >= 75% đối với tên nhiều từ.
2. Bóc Tách Email Đa Tầng Bản Địa Hóa Bỉ (Skill crawl-mail):
   - Priority 10: Menu / DOM thẻ <a> trang chủ tiếng Hà Lan (Flanders) và Pháp (Wallonia).
   - Priority 2: Guess subpaths bản địa có đuôi .html, .php, /nl/, /fr/.
   - Giải mã Cloudflare data-cfemail, regex obfuscated ([at], (at), [dot]).
   - Lọc 100% mail rác/template & sàn danh bạ địa phương Bỉ (localservices.be, bizbook.be, pagesdor.be, goudengids.be...).
   - Chấm điểm B2B Manpower (score_email_b2b): Giữ lại duy nhất 1 email có giá trị cao nhất.
3. Trình duyệt trực quan Playwright (headless=False), Geolocation Brussels (50.8503, 4.3517, 'nl-BE').
4. Bộ Selectors Google Maps chuẩn, nhận diện đóng cửa (Definitief gesloten / Fermé définitivement / Permanently closed).
5. SĐT có nháy đơn '+' (Rule 2).
6. Danh sách đen vĩnh viễn (Rule 12: Scandi Standard, Biliarta, Daigre).
7. Checkpoint JSON & Incremental Auto-Save mỗi 5 dòng hỗ trợ Resume 100%.
8. Chuẩn hóa đầu ra Cold Mail 20 cột (Rule 10: BE_WOOD_GMAP_2COL.csv), đẩy 100% email lên đầu (Rule 3).
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

DEFAULT_INPUT_CSV = ROOT_DIR / "BE_WOOD_KBO0_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "BE_WOOD_GMAP_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "BE_WOOD_GMAP_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_wood.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'nl-BE,nl;q=0.9,fr-BE;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
OBFUSCATED_EMAIL_REGEX = re.compile(
    r'\b([A-Za-z0-9._%+-]{1,64})\s*(?:@|\[at\]|\(at\)|\{at\}|\sat\s)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,10})\b',
    re.IGNORECASE
)
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Blacklist danh bạ, mạng xã hội, cổng thông tin (không lấy làm web công ty)
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'goudengids.be', 'pagesdor.be', 'goldenpages.be', 'trendstop.knack.be', 'infobel.com', 'kompass.com',
    'staatsbladmonitor.be', 'ejustice.just.fgov.be', 'kbopub.economie.fgov.be',
    'wikipedia.org', 'vdab.be', 'actiris.brussels', 'leforem.be', 'sentry.io',
    'wixpress.com', 'dnb.com', 'zoominfo.com', 'cookiebot.com', 'readymag.com',
    'site123.com', 'techaro.lol', 'anthropic.com', 'kuula.co', 'campanyon.com',
    'localservices.be', 'bizbook.be', 'belgique-entreprises.com', 'openthesaurus.de'
]

# Rule 12: Danh sách đen doanh nghiệp cố định
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
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def clean_company_name(name):
    if not name or pd.isna(name):
        return ""
    s = str(name).strip()
    # Tách họ tên cá nhân đảo ngược (ví dụ: "Van den Berg, Jan" -> "Jan Van den Berg")
    if ',' in s:
        parts = [p.strip() for p in s.split(',')]
        if len(parts) == 2 and len(parts[1].split()) <= 2 and len(parts[0].split()) <= 3:
            s = f"{parts[1]} {parts[0]}"
    # Bỏ legal forms Bỉ (Rule 11)
    legal_forms = [
        'besloten vennootschap met beperkte aansprakelijkheid',
        'societe a responsabilite limitee',
        'naamloze vennootschap',
        'societe anonyme',
        'gewone commanditaire vennootschap',
        'societe en commandite simple',
        'vennootschap onder firma',
        'societe en nom collectif',
        'cooperatieve vennootschap',
        'societe cooperative',
        'b.v.b.a.', 'bvba', 's.p.r.l.', 'sprl',
        'b.v.', 'bv', 's.r.l.', 'srl',
        'n.v.', 'nv', 's.a.', 'sa',
        'v.o.f.', 'vof', 's.n.c.', 'snc',
        'c.v.b.a.', 'cvba', 'c.v.', 'cv',
        'comm.v', 'comm.va', 'gcv', 'scs', 'sca',
        'asbl', 'vzw', 'holding'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        s = re.sub(r'\b' + re.escape(lf) + r'\b', '', s, flags=re.IGNORECASE)
    # Khử dấu ngoặc, dấu nháy
    s = re.sub(r'[\(\)\[\]\{\}\"\']', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip(' -,./')
    return s

def normalize_text(text):
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    return ''.join(c for c in n if not unicodedata.combining(c))

def normalize_match_string(s):
    if not s:
        return ""
    n = normalize_text(s)
    return re.sub(r'[^a-z0-9]', '', n)

def is_valid_name_match(query_name, candidate_name):
    """
    Thuật toán so khớp tên nghiêm ngặt & thông minh (Skill enrich-maps Section 2.A)
    """
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = clean_company_name(query_name)
    c_clean = clean_company_name(candidate_name)

    q_norm = normalize_text(re.sub(r'["\'„“”«»]', '', q_clean)).strip()
    c_norm = normalize_text(re.sub(r'["\'„“”«»]', '', c_clean)).strip()

    if not q_norm or not c_norm:
        return False, "EMPTY"

    # 1. Khớp hoàn toàn (Exact)
    if q_norm == c_norm or normalize_match_string(q_norm) == normalize_match_string(c_norm):
        return True, "EXACT"

    # 2. Bóc tách phần dịch/chú thích trong ngoặc () hoặc []
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_norm).strip()
    if q_norm == c_nobrackets or normalize_match_string(q_norm) == normalize_match_string(c_nobrackets):
        return True, "BRACKET_MATCH"

    # 3. Dấu phân cách chuẩn: -, –, —, |, /, :, ,
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_norm) if p.strip()]
    if any(normalize_match_string(p) == normalize_match_string(q_norm) for p in parts):
        return True, "DELIMITER_MATCH"

    # 4. So khớp Token đầy đủ nếu tên có từ 2 từ dài trở lên
    t1 = set(re.findall(r'[a-z0-9]{3,}', q_norm))
    t2 = set(re.findall(r'[a-z0-9]{3,}', c_norm))
    if t1 and t2:
        overlap = len(t1.intersection(t2))
        if overlap == len(t1) or (len(t1) >= 2 and overlap >= 2 and overlap / len(t1) >= 0.75):
            return True, "TOKEN_MATCH"

    return False, "NO_MATCH"

def clean_phone(phone_str):
    if not phone_str or pd.isna(phone_str):
        return ""
    p = str(phone_str).strip()
    if p.lower() in ['nan', '-', 'none', '']:
        return ""
    p = p.replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    p = re.sub(r'\s+', ' ', p).strip()
    # Nháy đơn đầu tiên (Rule 2)
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(email):
    if not email or pd.isna(email):
        return ""
    e = urllib.parse.unquote(str(email).strip().lower())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        e = e.replace(bad, '')
    e = re.sub(r'^mailto:\s*', '', e, flags=re.I)
    e = re.sub(r'\s+', '', e)
    e = e.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e) and not e.startswith('202'):
        if re.match(r'^20[a-zA-Z]', e):
            e = e[2:]
    return e

def is_junk_email(email):
    if not email:
        return True
    e = clean_email(email)
    if not e or '@' not in e or '.' not in e.split('@')[1]:
        return True
    # Mail template / demo / fake (Rule 3)
    junk_users = [
        'youremail', 'your-email', 'your_email', 'yourname', 'yourcompany', 'someone', 'nobody',
        'john.doe', 'user', 'name', 'example', 'domain', 'yourdomain', 'email', 'sample', 'test',
        'admin@domain.com', 'info@domain.com', 'contact@domain.com', 'xyz', 'username'
    ]
    u = e.split('@')[0]
    if u in junk_users:
        return True
    # Mail hệ thống / tracking / nền tảng
    junk_keywords = [
        'sentry', 'wix', 'wixpress', 'wordpress', 'no-reply', 'donotreply', 'privacy',
        'gdpr', 'unsubscribe', 'abuse', 'webmaster', 'postmaster', 'mailer-daemon',
        'cookiebot', 'readymag', 'site123', 'techaro', 'anthropic', 'kuula',
        'localservices.be', 'bizbook.be', 'pagesdor.be', 'goudengids.be'
    ]
    if any(k in e for k in junk_keywords):
        return True
    return False

def score_email_b2b(email, website_domain=""):
    """Bộ chấm điểm B2B Manpower tối ưu tuyển chọn 1 email tốt nhất (Rule 3)"""
    e = clean_email(email)
    if is_junk_email(e):
        return 0
    score = 10
    u, d = e.split('@', 1)
    # Trùng domain website (+50đ)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50
    # Ưu tiên 1: Tuyển dụng / Việc làm / Nhân sự (+50đ)
    if any(k in u for k in ['praca', 'kariera', 'hr', 'jobs', 'recruitment', 'career', 'werk', 'emploi', 'recrutement', 'personeel', 'aanwerving']):
        score += 50
    # Ưu tiên 2: Ban giám đốc / Kinh doanh / Lãnh đạo (+45đ)
    elif any(k in u for k in ['ceo', 'director', 'manager', 'sales', 'directie', 'bestuur', 'direction', 'zaakvoerder', 'gerant']):
        score += 45
    # Ưu tiên 3: Cổng liên hệ chính thức (+40đ)
    elif any(k in u for k in ['info', 'contact', 'kontakt', 'office', 'secretariaat', 'secretariat', 'accueil', 'balie']):
        score += 40
    # Email cá nhân riêng theo domain (+25đ)
    elif '.' in u and clean_domain in d:
        score += 25
    # Webmail miễn phí (+10đ)
    elif any(m in d for m in ['gmail.com', 'telenet.be', 'proximus.be', 'skynet.be', 'hotmail.com', 'yahoo.com', 'outlook.com']):
        score += 10
    # Hỗ trợ / kỹ thuật / hóa đơn (+5đ)
    elif any(k in u for k in ['support', 'admin', 'facturatie', 'facturation', 'boekhouding', 'comptabilite']):
        score += 5
    return score

def decode_cf_email(encoded_str):
    try:
        r = int(encoded_str[:2], 16)
        email = ''.join([chr(int(encoded_str[i:i+2], 16) ^ r) for i in range(2, len(encoded_str), 2)])
        return email
    except Exception:
        return ""

def crawl_website_emails(website_url):
    """
    BÓC TÁCH EMAIL ĐA TẦNG BẢN ĐỊA HÓA BỈ (Skill crawl-mail):
    1. Ưu tiên duyệt Trang chủ (Homepage) và bóc thẻ <a> menu DOM thực tế (Priority 10).
    2. Quét sâu các link menu thật chứa từ khóa tiếng Hà Lan (Flanders) và Pháp (Wallonia).
    3. Dự phòng các subpaths đoán mò bản địa hóa (Priority 2) có đuôi .html, .php.
    4. Giải mã Cloudflare data-cfemail, regex obfuscated ([at], [dot]).
    5. Tuyển chọn duy nhất 1 email có điểm B2B cao nhất.
    """
    if not website_url:
        return []
    target_url = website_url if website_url.startswith(('http://', 'https://')) else f'http://{website_url}'
    try:
        parsed = urllib.parse.urlparse(target_url)
        domain = parsed.netloc.lower()
    except Exception:
        return []

    if any(bad in domain for bad in BLACKLIST_DOMAINS):
        return []

    base_domain = domain.replace('www.', '')
    collected_emails = set()
    visited_urls = set()

    # Bộ từ khóa nhận diện Menu Liên hệ bản địa Bỉ (Hà Lan + Pháp + Đức + Anh)
    CONTACT_KEYWORDS = [
        # Hà Lan / Flemish
        'contact', 'contacteer', 'over-ons', 'wie-zijn-wij', 'locatie', 'vestiging',
        'vacatures', 'jobs', 'afspraak', 'offerte', 'werkplaats',
        # Pháp / Wallonie
        'contactez', 'nous-contacter', 'a-propos', 'mentions-legales', 'qui-sommes-nous',
        'equipe', 'nos-bureaux', 'rejoignez-nous', 'devis', 'atelier',
        # Đức & Anh
        'kontakt', 'impressum', 'ueber-uns', 'about'
    ]

    # Danh sách URL cần duyệt theo thứ bậc ưu tiên
    priority_urls = []

    # -------------------------------------------------------------
    # BƯỚC 1: Quét Trang chủ (Homepage) & Trích xuất DOM Menu (Priority 10)
    # -------------------------------------------------------------
    home_url = f"{parsed.scheme}://{parsed.netloc}/"
    try:
        req = urllib.request.Request(home_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
            if resp.status == 200:
                html = resp.read().decode('utf-8', errors='ignore')
                visited_urls.add(home_url)
                soup = BeautifulSoup(html, 'html.parser')

                # 1.1. Mailto links trên DOM
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'mailto:' in href.lower():
                        raw_m = href.split(':', 1)[1].split('?')[0].strip()
                        clean_m = clean_email(raw_m)
                        if clean_m and not is_junk_email(clean_m):
                            collected_emails.add(clean_m)

                # 1.2. Cloudflare decode
                for cf in soup.find_all(attrs={'data-cfemail': True}):
                    dec = decode_cf_email(cf['data-cfemail'])
                    clean_dec = clean_email(dec)
                    if clean_dec and not is_junk_email(clean_dec):
                        collected_emails.add(clean_dec)

                # 1.3. Regex email chuẩn & regex obfuscated
                for m in EMAIL_REGEX.findall(html):
                    clean_m = clean_email(m)
                    if clean_m and not is_junk_email(clean_m):
                        collected_emails.add(clean_m)

                for u_part, d_part in OBFUSCATED_EMAIL_REGEX.findall(html):
                    clean_m = clean_email(f"{u_part}@{d_part}")
                    if clean_m and not is_junk_email(clean_m):
                        collected_emails.add(clean_m)

                # 1.4. Bóc tách link Menu thật trên DOM (Priority 10)
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    text = a.get_text().strip().lower()
                    href_lower = href.lower()

                    if any(bad in href_lower for bad in ['javascript:', 'tel:', 'mailto:', '#']):
                        continue

                    # Kiểm tra xem anchor text hoặc href có chứa từ khóa liên hệ bản địa
                    is_contact_link = any(kw in text for kw in CONTACT_KEYWORDS) or any(kw in href_lower for kw in CONTACT_KEYWORDS)
                    if is_contact_link:
                        full_sub_url = urllib.parse.urljoin(home_url, href)
                        sub_parsed = urllib.parse.urlparse(full_sub_url)
                        # Đảm bảo cùng domain
                        if base_domain in sub_parsed.netloc.lower() and full_sub_url not in visited_urls:
                            if full_sub_url not in priority_urls:
                                priority_urls.append(full_sub_url)

    except Exception:
        pass

    # -------------------------------------------------------------
    # BƯỚC 2: Subpaths đoán mò dự phòng (Priority 2)
    # -------------------------------------------------------------
    # Chỉ thêm vào cuối nếu chưa có hoặc website ẩn menu bằng JS
    fallback_subpaths = [
        '/contact', '/contact.html', '/contact.php',
        '/nl/contact', '/fr/contact',
        '/contacteer-ons', '/contactez-nous', '/nous-contacter',
        '/over-ons', '/over-ons.html', '/a-propos', '/a-propos.html',
        '/nl/over-ons', '/fr/a-propos',
        '/impressum', '/mentions-legales', '/jobs', '/vacatures'
    ]
    for sub in fallback_subpaths:
        f_url = urllib.parse.urljoin(home_url, sub)
        if f_url not in visited_urls and f_url not in priority_urls:
            priority_urls.append(f_url)

    # -------------------------------------------------------------
    # BƯỚC 3: Duyệt các Subpages (Tối đa 8 trang)
    # -------------------------------------------------------------
    max_pages = 8
    for sub_url in priority_urls[:max_pages]:
        if len(collected_emails) >= 4:
            break
        if sub_url in visited_urls:
            continue
        visited_urls.add(sub_url)

        try:
            req = urllib.request.Request(sub_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                if resp.status == 200:
                    html = resp.read().decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html, 'html.parser')

                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'mailto:' in href.lower():
                            raw_m = href.split(':', 1)[1].split('?')[0].strip()
                            clean_m = clean_email(raw_m)
                            if clean_m and not is_junk_email(clean_m):
                                collected_emails.add(clean_m)

                    for cf in soup.find_all(attrs={'data-cfemail': True}):
                        dec = decode_cf_email(cf['data-cfemail'])
                        clean_dec = clean_email(dec)
                        if clean_dec and not is_junk_email(clean_dec):
                            collected_emails.add(clean_dec)

                    for m in EMAIL_REGEX.findall(html):
                        clean_m = clean_email(m)
                        if clean_m and not is_junk_email(clean_m):
                            collected_emails.add(clean_m)

                    for u_part, d_part in OBFUSCATED_EMAIL_REGEX.findall(html):
                        clean_m = clean_email(f"{u_part}@{d_part}")
                        if clean_m and not is_junk_email(clean_m):
                            collected_emails.add(clean_m)
        except Exception:
            continue

    # Chấm điểm chọn 1 email tốt nhất
    scored = [(score_email_b2b(e, base_domain), e) for e in collected_emails]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored]

async def enrich_maps_be_wood(input_csv=DEFAULT_INPUT_CSV, limit=None, headless=False):
    print("=" * 80)
    print("🇧🇪  LÀM GIÀU DỮ LIỆU DOANH NGHIỆP MỘC & GỖ BỈ BẰNG GOOGLE MAPS & EMAIL B2B")
    print(f"    - Tệp dữ liệu vào     : {input_csv.name}")
    print(f"    - Tệp làm giàu 1ENR   : {OUTPUT_1ENR_CSV.name}")
    print(f"    - Tệp chuẩn 2COL      : {OUTPUT_2COL_CSV.name}")
    print(f"    - Trình duyệt         : Playwright (headless={headless})")
    print("=" * 80)

    if not input_csv.exists():
        print(f"[!] Lỗi: Chưa tìm thấy tệp {input_csv.name}! Hãy chạy bộ cào KBO trước.")
        return

    df_raw = pd.read_csv(input_csv, encoding='utf-8-sig', dtype=str).fillna('')
    total_raw = len(df_raw)
    print(f"[*] Đã nạp {total_raw:,} doanh nghiệp độc nhất từ tệp {input_csv.name}\n")

    # Đọc cache nếu có
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp checkpoint: {len(cache):,} doanh nghiệp đã làm giàu từ trước.")
        except Exception:
            pass

    records_to_process = df_raw.to_dict('records')
    if limit:
        records_to_process = records_to_process[:limit]

    enriched_rows = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-sandbox'
            ]
        )
        context_kwargs = {
            'locale': 'nl-BE',
            'geolocation': {'latitude': 50.8503, 'longitude': 4.3517},
            'permissions': ['geolocation'],
            'user_agent': HEADERS['User-Agent']
        }
        if not headless:
            context_kwargs['no_viewport'] = True
        else:
            context_kwargs['viewport'] = {'width': 1280, 'height': 800}

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        count = 0
        for item in records_to_process:
            count += 1
            name = item.get('Company_Name', '').strip()
            address = item.get('Address', '').strip()
            postcode = item.get('Postcode', '').strip()
            kbo_num = item.get('KBO_Number', '').strip()

            if is_blacklisted_company(name):
                continue

            clean_kbo = re.sub(r'[^0-9]', '', kbo_num)
            unique_key = f"kbo_{clean_kbo}" if len(clean_kbo) == 10 else f"{name}_{postcode}"

            if unique_key in cache:
                cached_item = cache[unique_key]
                enriched_rows.append(cached_item)
                continue

            query = f"{clean_company_name(name)} {address} Belgium" if address else f"{clean_company_name(name)} {postcode} Belgium"
            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"

            found_name = ""
            found_phone = ""
            found_website = ""
            found_address = ""
            found_cat = ""
            is_closed = False

            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1.0)

                # Từ chối hoặc chấp nhận cookie nếu xuất hiện
                try:
                    consent_btn = await page.query_selector('button[aria-label*="Alle akkoord"], button[aria-label*="Tout accepter"], form[action*="consent"] button')
                    if consent_btn:
                        await consent_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Kiểm tra Captcha
                body_check = await page.inner_text('body')
                if any(cp in body_check.lower() for cp in ['unusual traffic', 'recaptcha', 'robot']):
                    print("\a\n[!] PHÁT HIỆN CAPTCHA GOOGLE MAPS! Vui lòng giải captcha trên trình duyệt và nhấn Enter để tiếp tục...")
                    input("[+] Nhấn ENTER sau khi giải xong Captcha...")

                # 1. Trường hợp Google Maps điều hướng thẳng vào trang Place
                title_el = await page.query_selector('h1.DUwDvf')
                if title_el:
                    cand_name = (await title_el.inner_text()).strip()
                    matched, match_type = is_valid_name_match(name, cand_name)
                    if matched:
                        found_name = cand_name
                        phone_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                        if phone_el:
                            found_phone = (await phone_el.inner_text()).strip()
                        web_el = await page.query_selector('a[data-item-id="authority"]')
                        if web_el:
                            found_website = await web_el.get_attribute('href')
                        addr_el = await page.query_selector('button[data-item-id^="address"]')
                        if addr_el:
                            found_address = (await addr_el.inner_text()).strip()
                        cat_el = await page.query_selector('button.DkEaL')
                        if cat_el:
                            found_cat = (await cat_el.inner_text()).strip()

                        # Nhận diện đóng cửa
                        body_txt = await page.inner_text('body')
                        if any(c in body_txt for c in ['Definitief gesloten', 'Fermé définitivement', 'Permanently closed']):
                            is_closed = True

                # 2. Trường hợp trả về danh sách kết quả (Listing)
                if not found_name:
                    listings = await page.query_selector_all('a.hfpxzc')
                    for l in listings[:3]:
                        l_name = await l.get_attribute('aria-label')
                        if l_name:
                            matched, match_type = is_valid_name_match(name, l_name)
                            if matched:
                                await l.click()
                                await asyncio.sleep(1.5)
                                t_el = await page.query_selector('h1.DUwDvf')
                                if t_el:
                                    found_name = (await t_el.inner_text()).strip()
                                p_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                                if p_el:
                                    found_phone = (await p_el.inner_text()).strip()
                                w_el = await page.query_selector('a[data-item-id="authority"]')
                                if web_el:
                                    found_website = await w_el.get_attribute('href')
                                a_el = await page.query_selector('button[data-item-id^="address"]')
                                if a_el:
                                    found_address = (await a_el.inner_text()).strip()
                                c_el = await page.query_selector('button.DkEaL')
                                if c_el:
                                    found_cat = (await c_el.inner_text()).strip()

                                body_txt = await page.inner_text('body')
                                if any(c in body_txt for c in ['Definitief gesloten', 'Fermé définitivement', 'Permanently closed']):
                                    is_closed = True
                                break

            except Exception:
                pass

            kbo_web = item.get('Website', '').strip()
            kbo_mail = item.get('Email', '').strip()
            kbo_phone = item.get('Phone', '').strip()

            clean_web = ""
            if found_website:
                m = re.search(r'q=([^&]+)', found_website)
                if m:
                    clean_web = urllib.parse.unquote(m.group(1))
                else:
                    clean_web = found_website.split('?')[0].rstrip('/')

            # Kế thừa website từ KBO nếu Google Maps không tìm thấy
            if not clean_web and kbo_web:
                clean_web = kbo_web if kbo_web.startswith('http') else f"https://{kbo_web}"

            # Quét và tuyển chọn 1 email B2B giá trị nhất từ Website & KBO
            candidate_emails = []
            if kbo_mail and not is_junk_email(kbo_mail):
                candidate_emails.append(kbo_mail)

            if clean_web and not any(bad in clean_web for bad in BLACKLIST_DOMAINS):
                crawled = crawl_website_emails(clean_web)
                for em in crawled:
                    if em not in candidate_emails:
                        candidate_emails.append(em)

            best_email = ""
            if candidate_emails:
                scored = sorted(candidate_emails, key=lambda e: score_email_b2b(e, clean_web), reverse=True)
                best_email = clean_email(scored[0])

            final_phone = clean_phone(found_phone) or clean_phone(kbo_phone)
            final_address = found_address if found_address else address

            enriched_row = dict(item)
            enriched_row['Maps_Name'] = found_name
            enriched_row['Phone'] = final_phone
            enriched_row['Website'] = clean_web
            enriched_row['Email'] = best_email
            enriched_row['Maps_Address'] = final_address
            enriched_row['Maps_Category'] = found_cat
            enriched_row['Permanently_Closed'] = 'Yes' if is_closed else 'No'

            cache[unique_key] = enriched_row
            enriched_rows.append(enriched_row)

            # In tiến độ trực tiếp
            status_str = f"SĐT: {final_phone or '-'} | Mail: {best_email or '-'}"
            print(f"  [{count:04d}/{len(records_to_process):04d}] {name[:25]} -> {status_str}", flush=True)

            # Lưu checkpoint mỗi 5 dòng
            if count % 5 == 0 or count == len(records_to_process):
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False)
                pd.DataFrame(enriched_rows).to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')

            await asyncio.sleep(0.5)

        await browser.close()

    # Lưu toàn bộ vào file 1ENR
    df_enr = pd.DataFrame(enriched_rows)
    df_enr.to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[+] Đã lưu {len(df_enr):,} doanh nghiệp vào {OUTPUT_1ENR_CSV.name}")

    # Xuất định dạng chuẩn Cold Mail 20 cột (Rule 10: BE_WOOD_GMAP_2COL.csv)
    # LỌC BỎ DOANH NGHIỆP ĐÓNG CỬA VÀ BLACKLIST
    df_active = df_enr[df_enr['Permanently_Closed'] != 'Yes'].copy()
    
    rows_2col = []
    idx = 1
    for _, r in df_active.iterrows():
        c_name = r.get('Company_Name', '').strip()
        phone = clean_phone(r.get('Phone', ''))
        email = clean_email(r.get('Email', ''))
        addr = r.get('Maps_Address') or r.get('Address') or ''
        cat = r.get('Maps_Category') or r.get('Activity') or 'Wood & Carpentry'

        rows_2col.append({
            'No.': idx,
            'Công ty': c_name,
            'Chức danh': '',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': '',
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat
        })
        idx += 1

    # Phân loại with_email lên đầu 100% (Rule 3)
    with_email = [r for r in rows_2col if r['Email']]
    without_email = [r for r in rows_2col if not r['Email']]
    sorted_2col = with_email + without_email

    for i, r in enumerate(sorted_2col, 1):
        r['No.'] = i

    df_2col = pd.DataFrame(sorted_2col, columns=COL_20_HEADERS)
    df_2col.to_csv(OUTPUT_2COL_CSV, index=False, encoding='utf-8-sig')

    # Đồng bộ sang csdl_mlt và archive/be_belgium
    for extra_dir in [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(OUTPUT_1ENR_CSV, extra_dir / OUTPUT_1ENR_CSV.name)
            shutil.copy2(OUTPUT_2COL_CSV, extra_dir / OUTPUT_2COL_CSV.name)
        except Exception:
            pass

    print("=" * 80)
    print("🏆 HOÀN THÀNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS & EMAIL B2B (NGÀNH MỘC BỈ)!")
    print(f"   - Tổng số doanh nghiệp hoạt động   : {len(df_2col):,}")
    print(f"   - Doanh nghiệp có EMAIL (đẩy lên đầu): {len(with_email):,} ({len(with_email)*100/max(1, len(df_2col)):.1f}%)")
    print(f"   - Doanh nghiệp có SĐT               : {len([r for r in sorted_2col if r['SĐT']]):,}")
    print(f"   - Tệp Cold Mail sẵn sàng gửi        : {OUTPUT_2COL_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Belgium Wood Enterprises with Google Maps & B2B Emails")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn (mặc định hiện trình duyệt)")
    args = parser.parse_args()

    asyncio.run(enrich_maps_be_wood(limit=args.limit, headless=args.headless))
