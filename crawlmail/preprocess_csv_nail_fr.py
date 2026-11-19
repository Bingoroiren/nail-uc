# -*- coding: utf-8 -*-
"""
HỆ THỐNG BÓC TÁCH EMAIL ĐA TẦNG & CHUẨN HÓA COLD MAIL: TIỆM NAIL PHÁP (FR_NAIL_GMAP)
===================================================================================
Tuân thủ toàn bộ quy chuẩn tại GEMINI.md, skill crawl-mail và data-standards:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY.
- Rule 2: Số điện thoại luôn có dấu nháy đơn (') ở đầu (+33... / 01... / 06...).
- Rule 3: Bộ chấm điểm B2B tối ưu tiệm nail/spa Pháp. ĐẨY 100% TIỆM CÓ EMAIL LÊN ĐẦU DANH SÁCH.
- Rule 5: Lưu tăng dần và Checkpoint cache JSON cho phép Resume 100%.
- Rule 6: Lọc bỏ mạng xã hội và sàn danh bạ (facebook, instagram, treatwell, planity, pagesjaunes).
- Rule 7: Bóc tách email đa tầng bản địa hóa Pháp (DOM-First Priority 10, Cloudflare XOR, WP Encoder, ROT13).
- Rule 10: Tên file cố định chuẩn 17 ký tự (FR_NAIL_GMAP_1ENR.csv / FR_NAIL_GMAP_2COL.csv).
- Rule 12: Loại trừ 100% danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre).
- Tự động đồng bộ sang archive/fr_france/ và csdl_mlt/.
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
import unicodedata
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# UTF-8 Output cho Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV_PATH = ROOT_DIR / "FR_NAIL_GMAP_0RAW.csv"
ENR1_CSV_PATH = ROOT_DIR / "FR_NAIL_GMAP_1ENR.csv"
COL2_CSV_PATH = ROOT_DIR / "FR_NAIL_GMAP_2COL.csv"
READY_CSV_PATH = ROOT_DIR / "FR_NAIL_GMAP_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_nail_fr.json"
DOMAIN_CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_domain_contacts_fr.json"
ARCHIVE_DIR = ROOT_DIR / "archive" / "fr_france"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

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
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'pagesjaunes.fr', 'treatwell.fr', 'planity.com',
    'kiute.fr', 'balinea.com', 'yelp.fr', 'yelp.com', 'tripadvisor.fr', 'leboncoin.fr',
    'sentry.io', 'wixpress.com', 'tiktok.com', 'pinterest.com'
]

JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'wix.com', 'wixpress.com', 'wordpress.com', 'wordpress.org',
    'example.com', 'domain.com', 'email.com', 'yourcompany.com', 'yourdomain.com',
    'pagesjaunes.fr', 'treatwell.fr', 'planity.com', 'facebook.com', 'instagram.com',
    'google.com', 'schema.org'
}

JUNK_EMAIL_PREFIXES = {
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'example', 'domain', 'no-reply', 'noreply', 'donotreply',
    'privacy', 'gdpr', 'abuse', 'webmaster', 'postmaster', 'sample'
}

FR_PRIORITY_KEYWORDS = [
    'contact', 'nous-contacter', 'mentions-legales', 'mentions',
    'a-propos', 'apropos', 'qui-sommes-nous', 'institut', 'salon',
    'tarifs', 'prestations', 'rendez-vous', 'rdv', 'equipe'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Tải domain cache nếu có
domain_contacts_cache = {}
if DOMAIN_CACHE_FILE.exists():
    try:
        with open(DOMAIN_CACHE_FILE, 'r', encoding='utf-8') as f:
            domain_contacts_cache = json.load(f)
    except Exception:
        domain_contacts_cache = {}

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_fr(raw_phone):
    """Chuẩn hóa SĐT Pháp: luôn có nháy đơn (') theo Rule 2."""
    if not raw_phone or pd.isna(raw_phone):
        return ""
    p = str(raw_phone).strip()
    p = re.sub(r'^tel:\s*', '', p, flags=re.I)
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email):
    """Làm sạch email triệt để theo Rule 3 (loại bỏ %20, \\u00a0, junk)."""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(email.strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")

    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]

    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""

    user, domain = em.split('@', 1)
    user_low = user.lower()
    domain_low = domain.lower()

    if domain_low in JUNK_EMAIL_DOMAINS:
        return ""
    if any(domain_low.endswith(bad) for bad in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf']):
        return ""
    if user_low in JUNK_EMAIL_PREFIXES:
        return ""

    return f"{user_low}@{domain_low}"

def score_email_b2b_fr(email, website_domain="", city=""):
    """
    Chấm điểm email theo Rule 3 tối ưu cho ngành Nail / Làm đẹp tại Pháp:
    - Trùng domain website (+50đ)
    - Trùng chi nhánh thành phố (+35đ)
    - Liên hệ chính thức / Salon / Institut / RDV (+40-45đ): contact, info, salon, institut, rdv, accueil
    - Ban quản lý / Chủ salon (+45đ): direction, gerant, responsable
    - Đích danh cá nhân domain riêng (+25đ)
    - Webmail miễn phí phổ biến tại Pháp (+10đ): @gmail.com, @orange.fr, @wanadoo.fr, @free.fr, @sfr.fr
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
    elif domain.endswith('.fr'):
        score += 20

    # 1. Ban quản lý / Chủ salon
    if any(k in user for k in ['direction', 'gerant', 'responsable', 'directeur', 'management', 'owner']):
        score += 45
    # 2. Cổng liên hệ chính thức / Đặt lịch / Salon
    elif any(k in user for k in ['contact', 'info', 'salon', 'institut', 'rdv', 'rendezvous', 'accueil', 'reservation', 'onglerie', 'manucure']):
        score += 40
    # 3. Tuyển dụng thợ nail / nhân viên
    elif any(k in user for k in ['recrutement', 'emploi', 'job', 'rh', 'career']):
        score += 40

    # 3.1 Khớp chi nhánh thành phố
    if city:
        c_city = re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', city).lower().replace('ß', 'ss'))
        if len(c_city) >= 3 and c_city in user:
            score += 35

    # 4. Email đích danh domain riêng
    if '.' in user and score >= 50:
        score += 25
    # 5. Webmail miễn phí thông dụng tại Pháp
    elif any(w in domain for w in ['gmail.com', 'orange.fr', 'wanadoo.fr', 'free.fr', 'sfr.fr', 'laposte.net', 'hotmail.fr', 'yahoo.fr']):
        score += 10
    # 6. Kỹ thuật / Kế toán
    elif any(k in user for k in ['comptabilite', 'admin', 'support', 'facturation']):
        score += 5

    return score

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
    Bóc tách email đa tầng chuyên sâu cho website Pháp:
    1. Decode JSON data-email
    2. Cloudflare XOR (data-cfemail)
    3. WordPress Email Encoder (var ml="...", mi="...")
    4. ROT13 Cipher (data-enc-email / data-rot13)
    5. JavaScript variables & string concatenation
    6. Thẻ mailto & Regex an toàn tuyến tính O(N)
    """
    found = set()
    if not page_html:
        return found

    # 1. data-email JSON attribute
    for m in re.finditer(r'data-email=(["\'])(.*?)\1', page_html):
        val = html.unescape(m.group(2))
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

    # 2. Cloudflare XOR
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', page_html):
        c = clean_email(decode_cf(cf))
        if c:
            found.add(c)

    # 3. WordPress Email Encoder (var ml="...", mi="...")
    for ml, mi in re.findall(r'var\s+ml\s*=\s*["\']([^"\']+)["\']\s*,\s*mi\s*=\s*["\']([^"\']+)["\']', page_html):
        try:
            dec = "".join(ml[ord(c) - 48] for c in mi if 0 <= ord(c) - 48 < len(ml))
            dec = urllib.parse.unquote(dec)
            c = clean_email(dec)
            if c:
                found.add(c)
        except Exception:
            pass

    # 4. ROT13 Obfuscated Emails
    for enc in re.findall(r'data-(?:enc-email|rot13)=["\']([^"\']+)["\']', page_html, re.I):
        try:
            raw = enc.replace('[at]', '@').replace('(at)', '@').replace('[dot]', '.').replace('(dot)', '.')
            dec = codecs.decode(raw, 'rot_13')
            c = clean_email(dec)
            if c:
                found.add(c)
        except Exception:
            pass

    # 5. JavaScript variables & concatenation
    js_patterns = [
        r'var\s+mailadr\s*=\s*["\']([^"\']+)["\']\s*;\s*var\s+maildom\s*=\s*["\']([^"\']+)["\']',
        r'mailadr\s*=\s*["\']([^"\']+)["\']\s*;\s*maildom\s*=\s*["\']([^"\']+)["\']',
        r'["\']mailto:["\']\s*\+\s*["\']([^"\']+)["\']\s*\+\s*["\']@["\']\s*\+\s*["\']([^"\']+)["\']',
    ]
    for pat in js_patterns:
        for m in re.findall(pat, page_html, re.I):
            c = clean_email(f"{m[0]}@{m[1]}")
            if c:
                found.add(c)

    # 6. Unescape HTML & direct regex
    unescaped = html.unescape(page_html)
    for em in EMAIL_REGEX.findall(unescaped):
        c = clean_email(em)
        if c:
            found.add(c)

    # 7. Mailto links
    for m in re.findall(r'href=["\']mailto:([^"?\'\s>]+)', unescaped, re.I):
        c = clean_email(m.split('?')[0])
        if c:
            found.add(c)

    # 8. Safe obfuscation replacements O(N)
    obf_text = re.sub(r'\[at\]|\(at\)', '@', unescaped, flags=re.I)
    obf_text = re.sub(r'\[dot\]|\(dot\)', '.', obf_text, flags=re.I)
    obf_text = re.sub(r'(?<=\w)\s+@\s+(?=\w)', '@', obf_text)
    obf_text = re.sub(r'(?<=\w)\s+\.\s+(?=\w)', '.', obf_text)
    for em in EMAIL_REGEX.findall(obf_text):
        c = clean_email(em)
        if c:
            found.add(c)

    return found

def detect_client_redirect(html_content, base_url):
    """Phát hiện chuyển hướng client-side JS / Meta refresh tức thì trong 0.001s."""
    if not html_content:
        return None

    m_meta = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'](?:\d+\s*;\s*url=)?([^"\']+)["\']', html_content, re.I)
    if m_meta:
        target = m_meta.group(1).strip().strip("'\"")
        if target:
            return urllib.parse.urljoin(base_url, target)

    patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)["\']',
        r'(?:window\.)?location\.replace\(["\'](https?://[^"\']+)["\']\)',
        r'(?:window\.)?location\.assign\(["\'](https?://[^"\']+)["\']\)',
        r'targetDomain\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'redirectUrl\s*[:=]\s*["\'](https?://[^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html_content, re.I)
        if m:
            target = m.group(1).strip()
            if target != base_url and not target.endswith(urllib.parse.urlparse(base_url).netloc):
                return urllib.parse.urljoin(base_url, target)

    return None

def crawl_site_for_emails(web_url, city=""):
    """
    DOM-First Multi-Tier Email Extractor cho website Pháp:
    1. Tra cứu cache domain
    2. Tự động nhận diện Client-side redirect
    3. Quét homepage + thẻ <a> DOM thực tế (/contact, /mentions-legales, /tarifs)
    4. Giải mã toàn diện (CF, WP, ROT13, JS, Obfuscation)
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

    # 1.1 Kiểm tra Client-Side Redirect
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

        valid_home = [e for e in candidate_emails if score_email_b2b_fr(e, root_domain, city) >= 75]
        if valid_home:
            best_home = max(valid_home, key=lambda e: score_email_b2b_fr(e, root_domain, city))
            domain_contacts_cache[root_domain] = {'email': best_home}
            if original_domain and original_domain != root_domain:
                domain_contacts_cache[original_domain] = {'email': best_home}
            return best_home

        # Bóc tách subpages & Facebook từ DOM
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
                if any(k in h_low or k in txt for k in FR_PRIORITY_KEYWORDS):
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

            # Ưu tiên trang liên hệ / pháp lý lên trước
            dom_contact_links.sort(key=lambda u: 0 if any(k in u.lower() for k in ['contact', 'mentions-legales', 'institut']) else 1)

            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl, timeout=2.0)
                if not chtml:
                    continue
                found_sub = extract_advanced_emails_from_html(chtml, root_domain)
                candidate_emails.update(found_sub)

                if candidate_emails and any(score_email_b2b_fr(e, root_domain, city) >= 60 for e in candidate_emails):
                    break
        except Exception:
            pass

    # 2. Guess paths cơ bản chuẩn Pháp
    if not candidate_emails:
        for gp in [f"{root_url}/contact", f"{root_url}/contact.html", f"{root_url}/mentions-legales"]:
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

    valid_candidates = [e for e in candidate_emails if score_email_b2b_fr(e, root_domain, city) > 0]
    best_final = max(valid_candidates, key=lambda e: score_email_b2b_fr(e, root_domain, city)) if valid_candidates else ""
    if best_final:
        domain_contacts_cache[root_domain] = {'email': best_final}
        if original_domain and original_domain != root_domain:
            domain_contacts_cache[original_domain] = {'email': best_final}
    return best_final

def save_and_reorder_files(df, output_0raw, output_1enr, output_2col, output_ready):
    """
    Xuất file 0RAW, 1ENR, 2COL và ONLY_EMAILS_READY chuẩn Rule 1, 2, 3, 10.
    ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU DANH SÁCH.
    """
    df_out = df.copy()

    # Chuẩn hóa SĐT Rule 2
    if 'Phone' in df_out.columns:
        df_out['Phone'] = df_out['Phone'].apply(clean_phone_fr)
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_fr)

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

    # Xuất file 1ENR
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

    # Cập nhật ngược lại 0RAW
    df_sorted.to_csv(output_0raw, index=False, encoding='utf-8-sig')

    # Xuất file Cold Mail 20 cột (2COL)
    col20_rows = []
    for idx, row in df_sorted.iterrows():
        cname = str(row.get('Name', '') or row.get('Company_Name', '') or row.get('Công ty', '')).strip()
        phone = str(row.get('Phone', '') or row.get('SĐT', '')).strip()
        web = str(row.get('Website', '') or row.get('Liên Hệ', '')).strip()
        raw_em = row.get('Email', '')
        email = '' if pd.isna(raw_em) or str(raw_em).strip().lower() in ['nan', 'none', ''] else str(raw_em).strip()
        addr = str(row.get('Address', '') or row.get('Full_Address', '') or row.get('Địa chỉ', '')).strip()
        cat = str(row.get('Category', '')).strip() or 'Institut de beauté / Salon de manucure'
        loc_name = str(row.get('Location_Name', '')).strip()

        title = 'Gérant / Propriétaire'
        full_addr = addr if addr else (f"{loc_name}, France" if loc_name else "France")

        r20 = {
            'No.': idx + 1,
            'Công ty': cname,
            'Chức danh': title,
            'Người liên hệ': '',
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

    # Xuất file ONLY_EMAILS_READY
    df_ready = df_2col[df_2col['Email'].notna() & (df_2col['Email'].str.strip() != '') & (df_2col['Email'].str.contains('@'))].copy()
    df_ready['No.'] = range(1, len(df_ready) + 1)
    df_ready.to_csv(output_ready, index=False, encoding='utf-8-sig')

    # Tự động đồng bộ sang archive và csdl_mlt
    for target_dir in [ARCHIVE_DIR, CSDL_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        for p in [output_0raw, output_1enr, output_2col, output_ready]:
            shutil.copy2(p, target_dir / p.name)

    return len(df_ready)

def main():
    print("=" * 80)
    print("  HỆ THỐNG BÓC TÁCH EMAIL ĐA TẦNG: TIỆM NAIL & LÀM ĐẸP PHÁP")
    print("  Tuân thủ: GEMINI.md - Rule 1, 2, 3, 5, 6, 7, 10, 12")
    print("=" * 80)
    print(f"[*] CSDL Thô ban đầu : {RAW_CSV_PATH.name}")
    print(f"[*] CSDL Làm giàu     : {ENR1_CSV_PATH.name}")
    print(f"[*] Cold Mail 20 cột  : {COL2_CSV_PATH.name}")
    print(f"[*] Tệp sẵn sàng gửi  : {READY_CSV_PATH.name}")
    print("=" * 80 + "\n")

    if not RAW_CSV_PATH.exists():
        print(f"[!] Chưa có file dữ liệu thô: {RAW_CSV_PATH}")
        print("Vui lòng chạy bộ cào Google Maps (src/scraper_nail_fr.py) trước!")
        return

    df = pd.read_csv(RAW_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    if 'Email' not in df.columns:
        df['Email'] = ''

    name_col = 'Name' if 'Name' in df.columns else 'Company_Name'
    web_col = 'Website' if 'Website' in df.columns else 'Liên Hệ'
    phone_col = 'Phone' if 'Phone' in df.columns else 'SĐT'
    city_col = 'Location_Name' if 'Location_Name' in df.columns else 'Department'

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    processed = 0
    rescued_emails = 0
    total = len(df)

    print(f"[*] Tổng số tiệm nail trong CSDL: {total}")

    for idx, row in df.iterrows():
        comp = str(row.get(name_col, '')).strip()
        web = str(row.get(web_col, '')).strip()
        city = str(row.get(city_col, '')).strip()
        current_email = str(row.get('Email', '')).strip()

        if is_blacklisted_company(comp):
            continue

        processed += 1
        print(f"[{processed:04d}/{total}] {comp[:28]:<28} | Đang xử lý...", end="\r", flush=True)

        found_email = current_email
        cache_key = comp.lower()

        # Kiểm tra cache
        if not found_email and cache.get(cache_key, {}).get('Email'):
            found_email = cache[cache_key]['Email']
            df.at[idx, 'Email'] = found_email
            rescued_emails += 1

        # Quét email từ website
        if web and web != 'nan' and not found_email:
            found_email = crawl_site_for_emails(web, city)
            if found_email:
                df.at[idx, 'Email'] = found_email
                rescued_emails += 1

        cache[cache_key] = {
            'Web': web,
            'Email': found_email,
            'Phone': row.get(phone_col, '')
        }

        status_em = f"[NEW EMAIL] {found_email}" if found_email else ("Có Web, chưa có mail" if web else "Không có Web")
        status_web = (web[:28] + '..') if len(web) > 30 else (web or "Chưa có web")
        print(f"[{processed:04d}/{total}] {comp[:28]:<28} | {status_web:<30} | {status_em}          ")

        # Lưu checkpoint mỗi 5 dòng
        if processed % 5 == 0:
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            with open(DOMAIN_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(domain_contacts_cache, f, ensure_ascii=False, indent=2)
            cur_ready = save_and_reorder_files(df, RAW_CSV_PATH, ENR1_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH)
            print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Tổng tiệm có Email hiện tại: {cur_ready}/{len(df)}")

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    with open(DOMAIN_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(domain_contacts_cache, f, ensure_ascii=False, indent=2)

    final_ready = save_and_reorder_files(df, RAW_CSV_PATH, ENR1_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH)

    print("\n" + "=" * 80)
    print("  HOÀN TẤT BÓC TÁCH EMAIL & CHUẨN HÓA COLD MAIL PHÁP!")
    print(f"[*] Số tiệm đã xử lý               : {processed}")
    print(f"[*] Số Email B2B mới bóc tách      : {rescued_emails}")
    print(f"[*] TỔNG TIỆM CÓ EMAIL SẴN SÀNG    : {final_ready} / {total} (100% đã gom lên đầu)")
    print(f"[*] Tệp thô cập nhật               : {RAW_CSV_PATH.name}")
    print(f"[*] Tệp làm giàu                   : {ENR1_CSV_PATH.name}")
    print(f"[*] Tệp Cold Mail 20 cột           : {COL2_CSV_PATH.name}")
    print(f"[*] Tệp chỉ email sẵn sàng         : {READY_CSV_PATH.name}")
    print("=" * 80)

if __name__ == '__main__':
    main()
