# -*- coding: utf-8 -*-
"""
GOOGLE MAPS & WEB EMAIL ENRICHMENT - BELGIUM MEAT ENTERPRISES (KBO)
=============================================================================
Kế thừa & Tuân thủ đầy đủ 100% các Skill:
- enrich-maps (.agents/skills/enrich-maps/SKILL.md)
- scrape-maps (.agents/skills/scrape-maps/SKILL.md)
- crawl-mail (.agents/skills/crawl-mail/SKILL.md)
- data-standards (.agents/skills/data-standards/SKILL.md)

Các quy chuẩn cốt lõi:
1. Lọc trùng lặp thông minh theo Tên công ty & Mã số KBO trước khi làm giàu Maps:
   - Gom các cơ sở chi nhánh (VE), lò mổ phụ trùng tên về 1 doanh nghiệp độc nhất.
   - Ưu tiên giữ lại bản ghi Trụ sở chính (ENT RP, ENT NP) và địa chỉ chi tiết nhất.
2. Geolocation Bỉ chuẩn xác (Brussels: 50.8503, 4.3517, locale 'nl-BE') tránh lệch vị trí.
3. Bộ Selectors chuẩn Google Maps:
   - 'a.hfpxzc' (Listing links)
   - 'h1.DUwDvf' (Business Name)
   - 'a[data-item-id="authority"]' (Website)
   - 'button[data-item-id^="phone:tel:"]' (Phone)
   - 'button[data-item-id^="address"]' (Address)
   - 'button.DkEaL' (Category)
   - Nhận diện đóng cửa: 'Permanently closed' / 'Definitief gesloten' / 'Fermé définitivement'
4. Smart & Strict Name Matching: Khử legal forms Bỉ (NV, BV, BVBA, SRL, SPRL, SA, BLDC...), NFKD accents, delimiter.
5. Bóc tách SĐT có nháy đơn '+32... (Rule 2).
6. Bóc tách email B2B đa tầng: DOM <a> link Priority 10, Cloudflare decoding, regex, lọc mail template rác, chấm điểm B2B Bỉ.
7. Checkpoint JSON & Incremental Save mỗi 5 dòng hỗ trợ Resume 100%.
8. Rule 12 Hard Blacklist: Scandi Standard, Biliarta, Daigre.
9. Định dạng đầu ra Cold Mail 20 cột (Rule 10: BE_MEAT_GMAP_2COL.csv), đẩy 100% email lên đầu.
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

DEFAULT_INPUT_CSV = ROOT_DIR / "BE_MEAT_KBO0_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "BE_MEAT_GMAP_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "BE_MEAT_GMAP_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_meat.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'nl-BE,nl;q=0.9,fr-BE;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
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
    'daigre'
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
    if ',' in s:
        parts = [p.strip() for p in s.split(',')]
        if len(parts) == 2 and len(parts[1].split()) <= 2 and len(parts[0].split()) <= 3:
            s = f"{parts[1]} {parts[0]}"
    legal_forms = [
        r'\bbvba\b', r'\bsprl\b', r'\bnv\b', r'\bsa\b', r'\bbv\b', r'\bsrl\b',
        r'\bvof\b', r'\bsnc\b', r'\bcomm\.v\b', r'\bcvba\b', r'\bscrnl\b',
        r'\besv\b', r'\bgie\b', r'\bvzw\b', r'\basbl\b', r'\bcoop\b', r'\bholding\b'
    ]
    for pattern in legal_forms:
        s = re.sub(pattern, '', s, flags=re.IGNORECASE)
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

    if q_norm == c_norm or normalize_match_string(q_norm) == normalize_match_string(c_norm):
        return True, "EXACT"

    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_norm).strip()
    if q_norm == c_nobrackets or normalize_match_string(q_norm) == normalize_match_string(c_nobrackets):
        return True, "BRACKET_MATCH"

    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_norm) if p.strip()]
    if any(normalize_match_string(p) == normalize_match_string(q_norm) for p in parts):
        return True, "DELIMITER_MATCH"

    t1 = set(re.findall(r'[a-z0-9]{3,}', q_norm))
    t2 = set(re.findall(r'[a-z0-9]{3,}', c_norm))
    if t1 and t2:
        overlap = len(t1.intersection(t2))
        if overlap == len(t1) or (len(t1) >= 2 and overlap >= 2 and overlap / len(t1) >= 0.75):
            return True, "TOKEN_MATCH"

    return False, "NO_MATCH"

def deduplicate_companies(df):
    """
    LỌC TRÙNG TÊN CÔNG TY & MÃ SỐ KBO THÔNG MINH:
    - Gom các cơ sở chi nhánh (VE), phân xưởng trùng tên về 1 doanh nghiệp độc nhất.
    - Ưu tiên giữ lại bản ghi Trụ sở chính (ENT RP, ENT NP) và địa chỉ chi tiết nhất.
    """
    initial_count = len(df)
    grouped = {}

    for row in df.to_dict('records'):
        c_name = str(row.get('Company_Name', '')).strip()
        if not c_name or is_blacklisted_company(c_name) or len(c_name.strip(' .,-_/\\')) < 2:
            continue

        kbo_raw = str(row.get('KBO_Number', ''))
        clean_kbo = re.sub(r'[^0-9]', '', kbo_raw)
        norm_name = normalize_match_string(clean_company_name(c_name))

        if len(clean_kbo) == 10:
            dedup_key = f"kbo_{clean_kbo}"
        elif norm_name:
            dedup_key = f"name_{norm_name}"
        else:
            continue

        score = 0
        t = str(row.get('Type', '')).upper()
        if 'ENT RP' in t:
            score += 100
        elif 'ENT NP' in t:
            score += 80
        elif 'VE' in t:
            score += 50
        else:
            score += 10

        if str(row.get('Status', '')).lower() == 'actief':
            score += 20

        addr = str(row.get('Address', '')).strip()
        score += min(len(addr), 50)

        if row.get('Activity'):
            score += 10

        if dedup_key not in grouped or score > grouped[dedup_key][0]:
            grouped[dedup_key] = (score, row)

    deduped_rows = [v[1] for v in grouped.values()]
    df_dedup = pd.DataFrame(deduped_rows)
    removed_count = initial_count - len(df_dedup)
    return df_dedup, removed_count

def clean_phone(phone_str):
    if not phone_str or pd.isna(phone_str):
        return ""
    p = str(phone_str).strip()
    if p == 'nan' or p == '-':
        return ""
    p = p.replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    p = re.sub(r'\s+', ' ', p).strip()
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
    junk_users = [
        'youremail', 'your-email', 'your_email', 'yourname', 'yourcompany', 'someone', 'nobody',
        'john.doe', 'user', 'name', 'example', 'domain', 'yourdomain', 'email', 'sample', 'test',
        'admin@domain.com', 'info@domain.com', 'contact@domain.com', 'xyz', 'username'
    ]
    u = e.split('@')[0]
    if u in junk_users:
        return True
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
    e = clean_email(email)
    if is_junk_email(e):
        return 0
    score = 10
    u, d = e.split('@', 1)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50
    if any(k in u for k in ['praca', 'kariera', 'hr', 'jobs', 'recruitment', 'career', 'werk', 'emploi', 'recrutement']):
        score += 50
    elif any(k in u for k in ['ceo', 'director', 'manager', 'sales', 'directie', 'bestuur', 'direction']):
        score += 45
    elif any(k in u for k in ['info', 'contact', 'kontakt', 'office', 'secretariaat', 'secretariat', 'accueil']):
        score += 40
    elif '.' in u and clean_domain in d:
        score += 25
    elif any(m in d for m in ['gmail.com', 'telenet.be', 'proximus.be', 'skynet.be', 'hotmail.com', 'yahoo.com', 'outlook.com']):
        score += 10
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
    if not website_url:
        return []
    target_url = website_url if website_url.startswith(('http://', 'https://')) else f'http://{website_url}'
    domain = urllib.parse.urlparse(target_url).netloc.lower()
    if any(bad in domain for bad in BLACKLIST_DOMAINS):
        return []

    collected_emails = set()
    subpaths = [
        '', '/contact', '/nl/contact', '/fr/contact', '/contact-us', '/contacteer-ons',
        '/over-ons', '/nl/over-ons', '/a-propos', '/impressum', '/jobs', '/over-ons/vacatures'
    ]

    base_domain = domain.replace('www.', '')

    for path in subpaths:
        test_url = urllib.parse.urljoin(target_url, path)
        try:
            req = urllib.request.Request(test_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                if resp.status == 200:
                    html = resp.read().decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html, 'html.parser')

                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if 'mailto:' in href:
                            raw_m = href.split('mailto:')[1].split('?')[0].strip()
                            clean_m = clean_email(raw_m)
                            if clean_m and not is_junk_email(clean_m):
                                collected_emails.add(clean_m)

                    for cf in soup.find_all(attrs={'data-cfemail': True}):
                        dec = decode_cf_email(cf['data-cfemail'])
                        clean_dec = clean_email(dec)
                        if clean_dec and not is_junk_email(clean_dec):
                            collected_emails.add(clean_dec)

                    matches = EMAIL_REGEX.findall(html)
                    for m in matches:
                        clean_m = clean_email(m)
                        if clean_m and not is_junk_email(clean_m):
                            collected_emails.add(clean_m)

                    if len(collected_emails) >= 5:
                        break
        except Exception:
            continue

    scored = [(score_email_b2b(e, base_domain), e) for e in collected_emails]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored]

async def enrich_maps_be_meat(input_csv=DEFAULT_INPUT_CSV, limit=None, headless=False):
    print("=" * 80)
    print("🇧🇪  LÀM GIÀU DỮ LIỆU DOANH NGHIỆP THỊT BỈ BẰNG GOOGLE MAPS & EMAIL B2B")
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
    print(f"[*] Đã nạp {total_raw:,} bản ghi thô từ tệp {input_csv.name}")

    # 1. LỌC TRÙNG TÊN CÔNG TY & MÃ SỐ KBO THÔNG MINH
    df_dedup, num_removed = deduplicate_companies(df_raw)
    print(f"[+] Lọc trùng lặp thông minh: Đã loại bỏ {num_removed:,} chi nhánh/văn phòng phụ trùng lặp.")
    print(f"[+] Còn lại {len(df_dedup):,} doanh nghiệp độc nhất sẵn sàng làm giàu Google Maps.\n")

    # Đọc cache nếu có
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp checkpoint: {len(cache):,} doanh nghiệp đã làm giàu từ trước.")
        except Exception:
            pass

    records_to_process = df_dedup.to_dict('records')
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

            clean_kbo = re.sub(r'[^0-9]', '', kbo_num)
            unique_key = f"kbo_{clean_kbo}" if len(clean_kbo) == 10 else f"{name}_{postcode}"

            if unique_key in cache:
                cached_item = cache[unique_key]
                enriched_rows.append(cached_item)
                continue

            query = f"{clean_company_name(name)} {address} Belgium"
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

                try:
                    consent_btn = await page.query_selector('button[aria-label*="Alle akkoord"], button[aria-label*="Tout accepter"], form[action*="consent"] button')
                    if consent_btn:
                        await consent_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

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

                        body_txt = await page.inner_text('body')
                        if any(c in body_txt for c in ['Definitief gesloten', 'Fermé définitivement', 'Permanently closed']):
                            is_closed = True

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
                                if w_el:
                                    found_website = await w_el.get_attribute('href')
                                a_el = await page.query_selector('button[data-item-id^="address"]')
                                if a_el:
                                    found_address = (await a_el.inner_text()).strip()
                                c_el = await page.query_selector('button.DkEaL')
                                if c_el:
                                    found_cat = (await c_el.inner_text()).strip()
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

            status_str = f"SĐT: {final_phone or '-'} | Mail: {best_email or '-'}"
            print(f"  [{count:04d}/{len(records_to_process):04d}] {name[:25]} -> {status_str}", flush=True)

            if count % 5 == 0 or count == len(records_to_process):
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False)
                pd.DataFrame(enriched_rows).to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')

            await asyncio.sleep(0.5)

        await browser.close()

    df_enr = pd.DataFrame(enriched_rows)
    df_enr.to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[+] Đã lưu {len(df_enr):,} doanh nghiệp vào {OUTPUT_1ENR_CSV.name}")

    df_active = df_enr[df_enr['Permanently_Closed'] != 'Yes'].copy()
    
    rows_2col = []
    idx = 1
    for _, r in df_active.iterrows():
        c_name = r.get('Company_Name', '').strip()
        phone = clean_phone(r.get('Phone', ''))
        email = clean_email(r.get('Email', ''))
        addr = r.get('Maps_Address') or r.get('Address') or ''
        cat = r.get('Maps_Category') or r.get('Activity') or 'Meat Processing'

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

    with_email = [r for r in rows_2col if r['Email']]
    without_email = [r for r in rows_2col if not r['Email']]
    sorted_2col = with_email + without_email

    for i, r in enumerate(sorted_2col, 1):
        r['No.'] = i

    df_2col = pd.DataFrame(sorted_2col, columns=COL_20_HEADERS)
    df_2col.to_csv(OUTPUT_2COL_CSV, index=False, encoding='utf-8-sig')

    for extra_dir in [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(OUTPUT_1ENR_CSV, extra_dir / OUTPUT_1ENR_CSV.name)
            shutil.copy2(OUTPUT_2COL_CSV, extra_dir / OUTPUT_2COL_CSV.name)
        except Exception:
            pass

    print("=" * 80)
    print("🏆 HOÀN THÀNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS & EMAIL B2B (NGÀNH THỊT BỈ)!")
    print(f"   - Tổng số doanh nghiệp hoạt động   : {len(df_2col):,}")
    print(f"   - Doanh nghiệp có EMAIL (đẩy lên đầu): {len(with_email):,} ({len(with_email)*100/max(1, len(df_2col)):.1f}%)")
    print(f"   - Doanh nghiệp có SĐT               : {len([r for r in sorted_2col if r['SĐT']]):,}")
    print(f"   - Tệp Cold Mail sẵn sàng gửi        : {OUTPUT_2COL_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Belgium Meat Enterprises with Google Maps & B2B Emails")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn (mặc định hiện trình duyệt)")
    args = parser.parse_args()

    asyncio.run(enrich_maps_be_meat(limit=args.limit, headless=args.headless))
