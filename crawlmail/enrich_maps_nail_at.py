# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU TIỆM NAIL ÁO BẰNG GOOGLE MAPS (ENRICH-MAPS)
=============================================================================
Kỹ năng: enrich-maps (.agents/skills/enrich-maps/SKILL.md)
Tệp mục tiêu: AT_NAIL_ALL_2COL.csv (Master 4 nguồn hợp nhất)
Mục tiêu: Quét Google Maps cho 2.395 tiệm nail chưa có email -> Lấy Website chính thức
         -> Cào sâu /impressum & /kontakt (§ 5 ECG Áo) -> Tăng tối đa số lượng Email B2B.

Quy chuẩn kỹ thuật:
1. So khớp tên nghiêm ngặt & thông minh (Smart & Strict Match - Rule 11)
2. Playwright Chromium trực quan (headless=False - Rule 4)
3. SĐT chuẩn nháy đơn ' ('+43...)
4. Giải mã Cloudflare + Obfuscated Mail + Loại bỏ 100% mail rác
5. Chấm điểm chọn DUY NHẤT 1 email tối ưu nhất (Rule 3)
6. Lưu tăng dần (Incremental Checkpoint) & Cache JSON Resume 100% (Rule 5)
7. Đẩy 100% dòng có email lên đầu danh sách (dòng 1..N)
8. Đồng bộ tự động sang csdl_mlt/ và archive/at_austria/
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
import curl_cffi.requests as requests
from playwright.sync_api import sync_playwright
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_MASTER_CSV = ROOT_DIR / "AT_NAIL_ALL_2COL.csv"
OUTPUT_READY_CSV = ROOT_DIR / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_nail_at.json"

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')

JUNK_EMAIL_DOMAINS = {
    'example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io',
    'wixpress.com', 'wordpress.com', 'webador.de', 'webador.com', 'beispiel.de',
    'ivof.com', 'chilly.domains', 'netports.at', 'jimdofree.com', 'squarespace.com',
    'world4you.com', 'ionos.de', 'strato.de'
}

JUNK_USERNAMES = {
    'support', 'webador', 'mustermann', 'example', 'sample', 'youremail',
    'your-email', 'someone', 'nobody', 'user', 'name', 'john.doe', 'privacy',
    'gdpr', 'abuse', 'postmaster', 'hostmaster', 'admin', 'mailer-daemon',
    'datenschutz', 'noreply', 'no-reply', 'donotreply'
}

AGGREGATOR_DOMAINS = {
    'treatwell', 'facebook.com', 'fb.com', 'instagram.com', 'herold.at', 'firmenabc.at', 'wko.at',
    'gelbeseiten', 'yelp', 'cylex', 'tupalo', 'fyle', 'google.com', 'youtube.com',
    'linkedin.com', 'pinterest.com', 'tiktok.com', 'twitter.com', 'x.com', 'ivof.com', 'tripadvisor',
    'firmania.at', 'sabisu.org', 'findglocal.com', 'beautynailhairsalons.com', 'cybo.com',
    'infobel.com', 'stadtbranchenbuch.at', 'yellowmap.at'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigrė'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()

    em = re.sub(r'(\.[a-z]{2,6})www\..*$', r'\1', em, flags=re.I)
    em = re.sub(r'(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$', r'\1', em, flags=re.I)

    if not re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""

    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return ""
    if u in JUNK_USERNAMES or any(k in u for k in ['mustermann', 'youremail', 'your-email']):
        return ""
    if any(em.endswith(ext) for ext in INVALID_EXTS):
        return ""

    return em

def decode_cloudflare(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return clean_email(email)
    except Exception:
        return ""

def score_email_at(email, domain=""):
    e = clean_email(email)
    if not e:
        return -1
    u, d = e.split('@', 1)
    score = 10

    clean_dom = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50
    elif d.endswith('.at'):
        score += 25
    elif d.endswith('.de') or d.endswith('.eu'):
        score += 15

    if any(u == k or u.startswith(k) for k in ['office', 'kontakt', 'contact', 'info', 'salon', 'studio', 'termin', 'termine', 'buchung', 'anfrage', 'nail', 'nagel']):
        score += 40
    elif any(u == k or u.startswith(k) for k in ['chefin', 'inhaber', 'geschäftsführung', 'geschaeftsfuehrung', 'leitung', 'management', 'direktion']):
        score += 45
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'gmx.at', 'aon.at', 'yahoo.de', 'hotmail.com']:
        score += 10

    return score

def select_best_email(emails, domain=""):
    valid = [clean_email(e) for e in emails if clean_email(e)]
    valid = [e for e in set(valid) if score_email_at(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_at(e, domain))

def fetch_html(url, timeout=4):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=timeout, verify=False, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

def extract_emails_from_page(html_text, domain=""):
    found = set()
    if not html_text:
        return found

    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare(cf)
        if dec: found.add(dec)

    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = clean_email(m)
        if clean_m: found.add(clean_m)

    for m in EMAIL_REGEX.findall(html_text):
        clean_m = clean_email(m)
        if clean_m: found.add(clean_m)

    obf_patterns = [
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([a-zA-Z0-9.-]{1,50})\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*([a-zA-Z]{2,10})', re.I),
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*&#64;\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,10})', re.I)
    ]
    for pat in obf_patterns:
        for match in pat.findall(html_text):
            if len(match) == 3:
                cand = clean_email(f"{match[0]}@{match[1]}.{match[2]}")
                if cand: found.add(cand)
            elif len(match) == 2:
                cand = clean_email(f"{match[0]}@{match[1]}")
                if cand: found.add(cand)

    return found

def crawl_salon_website(website_url):
    """Quét trang chủ và các trang con Impressum / Kontakt của Áo"""
    if not website_url or not isinstance(website_url, str):
        return ""
    u_str = website_url.strip()
    if not u_str.startswith(('http://', 'https://')):
        u_str = 'https://' + u_str

    try:
        domain_parsed = urllib.parse.urlparse(u_str)
        base_origin = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
        domain = domain_parsed.netloc.lower().replace('www.', '')
    except Exception:
        return ""

    if any(ag in domain for ag in AGGREGATOR_DOMAINS):
        return ""

    all_emails = set()

    home_html = fetch_html(u_str, timeout=4)
    if not home_html:
        alt_url = u_str.replace('http://', 'https://') if u_str.startswith('http://') else u_str.replace('https://', 'http://')
        home_html = fetch_html(alt_url, timeout=3)
        if home_html:
            u_str = alt_url
            domain_parsed = urllib.parse.urlparse(u_str)
            base_origin = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
        else:
            return ""

    all_emails.update(extract_emails_from_page(home_html, domain))
    best = select_best_email(all_emails, domain)
    if best and score_email_at(best, domain) >= 60:
        return best

    candidate_links = []
    sub_keywords = ['impressum', 'kontakt', 'contact', 'ueber-uns', 'ueber-mich', 'team', 'about', 'termine', 'buchung']
    try:
        soup = BeautifulSoup(home_html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            href_lower = href.lower()
            text_lower = (a.get_text() or "").strip().lower()
            if any(k in href_lower or k in text_lower for k in sub_keywords):
                full_url = urllib.parse.urljoin(u_str, href).split('#')[0]
                if urllib.parse.urlparse(full_url).netloc == domain_parsed.netloc:
                    candidate_links.append((10, full_url))
    except Exception:
        pass

    guess_paths = ['/impressum', '/impressum/', '/impressum.html', '/kontakt', '/kontakt/', '/contact']
    for gp in guess_paths:
        candidate_links.append((5, f"{base_origin.rstrip('/')}{gp}"))

    candidate_links.sort(key=lambda x: x[0], reverse=True)
    unique_subs = []
    seen_subs = {u_str.rstrip('/')}
    for prio, s_url in candidate_links:
        clean_s = s_url.rstrip('/')
        if clean_s not in seen_subs:
            seen_subs.add(clean_s)
            unique_subs.append(s_url)
            if len(unique_subs) >= 5:
                break

    for sub_url in unique_subs:
        sub_html = fetch_html(sub_url, timeout=3)
        if sub_html:
            all_emails.update(extract_emails_from_page(sub_html, domain))
            best = select_best_email(all_emails, domain)
            if best and score_email_at(best, domain) >= 60:
                return best

    return select_best_email(all_emails, domain)

def normalize_text_for_match(text):
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    clean = ''.join(c for c in n if not unicodedata.combining(c)).replace('ß', 'ss')
    clean = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', clean)
    clean = re.sub(r'[.,;:\-_/\\\"\'`´’!?*#|]', ' ', clean)
    
    legal_forms = [r'\bgmbh\b', r'\bgesmbh\b', r'\bm\s*b\s*h\b', r'\bag\b', r'\bkg\b', r'\bog\b', r'\be\s*u\b', r'\binhaber\b', r'\binh\b']
    for lf in legal_forms:
        clean = re.sub(lf, ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def is_valid_name_match(query_name, candidate_name):
    """So khớp tên nghiêm ngặt & thông minh theo SKILL.md (Rule 11)"""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_norm = normalize_text_for_match(query_name)
    c_norm = normalize_text_for_match(candidate_name)

    if not q_norm or not c_norm:
        return False, "EMPTY_AFTER_CLEAN"

    # 1. So khớp chính xác hoàn toàn
    if q_norm == c_norm:
        return True, "EXACT"

    # 2. So khớp hoán vị từ (Token Sort Exact: ví dụ "Bella Nails" vs "Nails Bella")
    q_words = sorted(q_norm.split())
    c_words = sorted(c_norm.split())
    if q_words == c_words and len(q_words) > 0:
        return True, "TOKEN_EXACT"

    # 3. So khớp không khoảng trắng
    q_flat = re.sub(r'[^a-z0-9]', '', q_norm)
    c_flat = re.sub(r'[^a-z0-9]', '', c_norm)
    if q_flat == c_flat:
        return True, "FLAT_EXACT"

    # 4. Match tiền tố / hậu tố khi có dấu phân tách
    if q_flat in c_flat or c_flat in q_flat:
        if len(q_flat) >= 4 and len(c_flat) >= 4:
            ratio = min(len(q_flat), len(c_flat)) / max(len(q_flat), len(c_flat))
            if ratio >= 0.70:
                return True, f"SUBSTRING_{int(ratio*100)}%"

    return False, "NO_MATCH"

def save_all_destinations(df_current):
    """Lưu tăng dần và tự động phân loại đẩy 100% email lên dòng đầu tiên"""
    df_current = df_current[~df_current['Công ty'].apply(is_blacklisted)].copy()

    has_em = df_current[df_current['Email'].str.contains('@', na=False)].copy()
    no_em = df_current[~df_current['Email'].str.contains('@', na=False)].copy()

    has_em['SĐT'] = has_em['SĐT'].apply(clean_phone)
    no_em['SĐT'] = no_em['SĐT'].apply(clean_phone)

    # Khử trùng email
    has_em['clean_em'] = has_em['Email'].str.lower().str.strip()
    has_em = has_em.drop_duplicates(subset=['clean_em'], keep='first').copy()
    has_em.drop(columns=['clean_em'], inplace=True, errors='ignore')

    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted['Check gửi'] = df_sorted['Email'].apply(lambda x: 'Chưa gửi' if x else '')
    df_sorted['Liên Hệ mail'] = df_sorted['Email'].apply(lambda x: f"mailto:{x}" if x else '')

    # Ready file (chỉ có email)
    ready_df = has_em.copy()
    ready_df['No.'] = range(1, len(ready_df) + 1)
    ready_df['Check gửi'] = 'Chưa gửi'
    ready_df['Liên Hệ mail'] = ready_df['Email'].apply(lambda x: f"mailto:{x}" if x else '')

    def safe_export(dframe, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            dframe.to_csv(path, index=False, encoding="utf-8-sig")
        except PermissionError:
            tmp = path.with_name(f"{path.stem}_updated{path.suffix}")
            dframe.to_csv(tmp, index=False, encoding="utf-8-sig")

    for rp in [OUTPUT_READY_CSV, ROOT_DIR / "csdl_mlt" / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv", ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv"]:
        safe_export(ready_df, rp)

    for mp in [INPUT_MASTER_CSV, ROOT_DIR / "data" / "formatted" / "AT_NAIL_ALL_2COL.csv", ROOT_DIR / "csdl_mlt" / "AT_NAIL_ALL_2COL.csv", ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_ALL_2COL.csv"]:
        safe_export(df_sorted, mp)

    return len(ready_df)

def handle_google_consent(page):
    try:
        btn = page.locator("button:has-text('Alle akzeptieren'), button:has-text('Ich stimme zu'), button:has-text('Accept all')")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

def run_enrichment():
    print("=" * 80)
    print("🇦🇹  HỆ THỐNG LÀM GIÀU DỮ LIỆU TIỆM NAIL ÁO BẰNG GOOGLE MAPS (ENRICH-MAPS)")
    print(f"    - Tệp nguồn   : {INPUT_MASTER_CSV.name}")
    print(f"    - Chế độ xem : Trực quan (headless=False - Rule 4)")
    print(f"    - Checkpoint  : {CACHE_FILE.name}")
    print("=" * 80)

    if not INPUT_MASTER_CSV.exists():
        print(f"[!] Không tìm thấy file {INPUT_MASTER_CSV}!")
        return

    with open(INPUT_MASTER_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[*] Đã nạp {len(rows):,} tiệm nail từ tệp Master.")

    # Nạp cache checkpoint
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp cache checkpoint: {len(cache):,} cơ sở đã tra cứu.")
        except Exception:
            pass

    initial_email_count = sum(1 for r in rows if r.get('Email', '').strip())
    print(f"[*] Số cơ sở ĐÃ CÓ Email ban đầu: {initial_email_count:,}")

    # Đồng bộ cache đã tra cứu từ trước và lọc danh sách CÒN LẠI cần tra cứu Google Maps
    to_scan_indices = []
    cached_sync_count = 0
    for idx, r in enumerate(rows):
        comp_name = r.get('Công ty', '').strip()
        address = r.get('Địa chỉ', '').replace('\ue0c8', '').strip()
        city_m = re.search(r'\b\d{4}(?:\.0)?\s+([A-Za-zÄÖÜäöüß\s\-]+)', address)
        city = city_m.group(1).split(',')[0].replace('Austria', '').replace('Österreich', '').strip() if city_m else ""
        cache_key = f"{comp_name.lower()}_{city.lower()}".strip("_")

        if cache_key in cache:
            cached = cache[cache_key]
            c_email = cached.get('email', '')
            c_web = cached.get('website', '')
            c_phone = cached.get('phone', '')

            if c_email and not r.get('Email'):
                r['Email'] = c_email
                r['Liên Hệ mail'] = f"mailto:{c_email}"
                r['Check gửi'] = "Chưa gửi"
            if c_web and not r.get('Liên Hệ'):
                r['Liên Hệ'] = c_web
            if c_phone and not r.get('SĐT'):
                r['SĐT'] = c_phone
            cached_sync_count += 1
            continue

        if not r.get('Email', '').strip():
            to_scan_indices.append(idx)

    print(f"[*] Đã đồng bộ và bỏ qua: {cached_sync_count:,} cơ sở đã xử lý trong cache.")
    print(f"[*] Số cơ sở CÒN LẠI cần tra cứu Google Maps: {len(to_scan_indices):,} tiệm.")

    new_emails = 0
    new_websites = 0
    new_phones = 0
    processed_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=30)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="de-AT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Mở Maps và vượt cookie lần đầu
        page.goto("https://www.google.com/maps?hl=de", timeout=60000)
        page.wait_for_timeout(2000)
        handle_google_consent(page)

        for step_idx, row_idx in enumerate(to_scan_indices, 1):
            row = rows[row_idx]
            comp_name = row.get('Công ty', '').strip()
            address = row.get('Địa chỉ', '').replace('\ue0c8', '').strip()

            city_m = re.search(r'\b\d{4}(?:\.0)?\s+([A-Za-zÄÖÜäöüß\s\-]+)', address)
            city = city_m.group(1).split(',')[0].replace('Austria', '').replace('Österreich', '').strip() if city_m else ""

            cache_key = f"{comp_name.lower()}_{city.lower()}".strip("_")

            # 1. Kiểm tra cache checkpoint
            if cache_key in cache:
                cached = cache[cache_key]
                c_email = cached.get('email', '')
                c_web = cached.get('website', '')
                c_phone = cached.get('phone', '')

                if c_email and not row.get('Email'):
                    row['Email'] = c_email
                    row['Liên Hệ mail'] = f"mailto:{c_email}"
                    row['Check gửi'] = "Chưa gửi"
                    new_emails += 1
                if c_web and not row.get('Liên Hệ'):
                    row['Liên Hệ'] = c_web
                if c_phone and not row.get('SĐT'):
                    row['SĐT'] = c_phone
                processed_count += 1
                continue

            found_web = ""
            found_phone = ""
            found_email = ""

            # 2. Kiểm tra Website có sẵn trước (nếu đã có link web chuẩn không phải aggregator)
            existing_web = row.get('Liên Hệ', '').strip()
            if existing_web and not any(ag in existing_web.lower() for ag in AGGREGATOR_DOMAINS):
                found_email = crawl_salon_website(existing_web)

            # Nếu đã có email và đã có SĐT, không cần search Maps để tiết kiệm thời gian
            need_maps = not (found_email and row.get('SĐT'))

            if need_maps:
                query = f"{comp_name} {city} Austria".strip()
                search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=de"

                try:
                    page.goto(search_url, timeout=30000)
                    page.wait_for_timeout(1000)
                    handle_google_consent(page)

                    # Kiểm tra Captcha
                    if "sorry/index" in page.url or page.locator("iframe[src*='recaptcha']").count() > 0:
                        print(f"\n\a[!] PHÁT HIỆN CAPTCHA GOOGLE! Vui lòng giải Captcha trên trình duyệt...")
                        while "sorry/index" in page.url:
                            page.wait_for_timeout(2000)
                        print("[+] Captcha đã được xử lý, tiếp tục cào...")

                    # Chờ Maps hiển thị kết quả
                    try:
                        page.wait_for_selector("h1.DUwDvf, a.hfpxzc, div[role='feed']", timeout=4000)
                    except Exception:
                        pass

                    # Kiểm tra xem Maps hiển thị Chi tiết (Detail) hay Danh sách (List)
                    is_detail = page.locator("h1.DUwDvf").count() > 0

                    if not is_detail:
                        # Kiểm tra top 3 kết quả tìm kiếm
                        items = page.locator("a.hfpxzc")
                        num_items = min(items.count(), 3)
                        for it_idx in range(num_items):
                            item = items.nth(it_idx)
                            aria_title = item.get_attribute("aria-label") or ""
                            is_match, reason = is_valid_name_match(comp_name, aria_title)
                            if is_match:
                                item.click()
                                try:
                                    page.wait_for_selector("h1.DUwDvf", timeout=4000)
                                except Exception:
                                    page.wait_for_timeout(1200)
                                is_detail = page.locator("h1.DUwDvf").count() > 0
                                break

                    if is_detail:
                        maps_title = page.locator("h1.DUwDvf").inner_text().strip()
                        is_match, reason = is_valid_name_match(comp_name, maps_title)

                        if is_match:
                            # 1. Lấy Website từ Google Maps
                            web_el = page.locator("a[data-item-id='authority'], a[aria-label*='Website'], a[aria-label*='Webseite'], a[aria-label*='website']")
                            if web_el.count() > 0:
                                raw_web = web_el.first.get_attribute("href") or ""
                                if "google.com/url" in raw_web:
                                    parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_web).query)
                                    if 'q' in parsed_q:
                                        raw_web = parsed_q['q'][0]
                                if raw_web and not any(ag in raw_web.lower() for ag in AGGREGATOR_DOMAINS):
                                    found_web = raw_web

                            # 2. Lấy SĐT từ Google Maps
                            phone_el = page.locator("button[data-item-id^='phone:'], button[aria-label*='Telefon'], a[data-item-id^='phone:'], a[aria-label*='Telefon']")
                            if phone_el.count() > 0:
                                p_text = phone_el.first.inner_text().strip()
                                if not p_text or not re.search(r'\d{6,}', p_text):
                                    p_label = phone_el.first.get_attribute("aria-label") or ""
                                    p_m = re.search(r'[\d+\s\(\)\/\-]{7,}', p_label)
                                    if p_m:
                                        p_text = p_m.group(0)
                                clean_p = clean_phone(p_text)
                                if clean_p:
                                    found_phone = clean_p

                            # 3. Quét sâu Website nếu chưa có mail hoặc tìm thấy Website mới
                            target_site = found_web or (existing_web if not found_email else "")
                            if target_site and not found_email:
                                found_email = crawl_salon_website(target_site)

                except Exception as e:
                    pass

            # Cập nhật kết quả vào bản ghi
            if found_email:
                row['Email'] = found_email
                row['Liên Hệ mail'] = f"mailto:{found_email}"
                row['Check gửi'] = "Chưa gửi"
                new_emails += 1
                log_em = f"✨ {found_email}"
            else:
                log_em = "Không có mail"

            if found_web and not row.get('Liên Hệ'):
                row['Liên Hệ'] = found_web
                new_websites += 1
                log_wb = f"Web: {found_web[:25]}"
            else:
                log_wb = f"Web: {row.get('Liên Hệ', '')[:25]}" if row.get('Liên Hệ') else "Web: -"

            if found_phone and not row.get('SĐT'):
                row['SĐT'] = found_phone
                new_phones += 1

            # Lưu cache
            cache[cache_key] = {
                'email': found_email,
                'website': found_web or row.get('Liên Hệ', ''),
                'phone': found_phone or row.get('SĐT', ''),
                'updated_at': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed_count += 1
            print(f"[{processed_count:04d}/{len(to_scan_indices):04d}] {comp_name[:25]:<25} | {city[:12]:<12} | {log_em:<30} | {log_wb}", flush=True)

            # Checkpoint tự động mỗi 5 tiệm
            if processed_count % 5 == 0:
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)

                df_temp = pd.DataFrame(rows)
                cur_ready = save_all_destinations(df_temp)
                print(f"  >>> [AUTO-SAVE CHECKPOINT] Hiện có {cur_ready:,} tiệm có email trên dòng 1..N.", flush=True)

            time.sleep(0.1)

        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        df_final = pd.DataFrame(rows)
        final_ready = save_all_destinations(df_final)
        browser.close()

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CHIẾN DỊCH LÀM GIÀU BẰNG GOOGLE MAPS!")
    print(f"   - Số cơ sở đã tra cứu đợt này      : {processed_count:,}")
    print(f"   - EMAIL B2B MỚI BỔ SUNG            : +{new_emails:,}")
    print(f"   - Website mới tìm thấy             : +{new_websites:,}")
    print(f"   - SĐT mới bổ sung                  : +{new_phones:,}")
    print(f"   - TỔNG SỐ TIỆM CÓ EMAIL ĐẦY ĐỦ     : {final_ready:,} (Tăng từ {initial_email_count:,})")
    print(f"   - File Cold Mail sẵn sàng gửi      : {OUTPUT_READY_CSV.name}")
    print(f"   - File Master 2COL cập nhật        : {INPUT_MASTER_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_enrichment()
