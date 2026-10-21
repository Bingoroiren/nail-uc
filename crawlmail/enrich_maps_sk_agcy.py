# -*- coding: utf-8 -*-
"""
Google Maps & Web Email Data Enrichment for Slovak Employment Agencies
Tuân thủ toàn bộ quy chuẩn tại GEMINI.md, data-standards, crawl-mail và enrich-maps:
1. Strict Name Matching (Exact, Brackets, Delimiters).
2. SĐT có nháy đơn (') ở đầu: phone = f"'{phone}".
3. Chấm điểm email B2B (score_email_b2b) tối ưu cho Manpower Agency:
   - Ưu tiên Nhân sự / Việc làm (praca@, kariera@, hr@, personalne@...) +50
   - Ưu tiên Lãnh đạo / Giám đốc (vedenie@, riaditel@, konatel@, ceo@...) +45
   - Ưu tiên Liên hệ chính thức (info@, kontakt@, office@...) +40
   - Lọc bỏ 100% mail rác/template (youremail@, example@, sentry, wix...).
   - Chỉ giữ DUY NHẤT 1 email tốt nhất.
4. Ưu tiên thẻ <a> DOM thực tế (Priority 10), quét sâu subpages.
5. Playwright headless=False (mặc định), chống Captcha.
6. Lưu tăng dần (Incremental Auto-Save) mỗi 5 dòng & Checkpoint JSON (Resume 100%).
7. Luôn đẩy công ty có Email lên đầu file CSV.
"""

import os
import sys
import re
import ssl
import json
import argparse
import urllib.parse
import urllib.request
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
import asyncio

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path("D:/glc/nail uc")
DEFAULT_INPUT_CSV = ROOT_DIR / "csdl_sk_agcy" / "dnb_slovakia_agcy_detailed.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_agcy.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no', 'zlatestranky.sk',
    'azet.sk', 'finstat.sk', 'orsr.sk', 'zrsr.sk', 'wikipedia.org', 'portal.sk',
    'profesia.sk', 'kariera.zoznam.sk', 'praca.sme.sk', 'worki.sk', 'sentry.io', 'wixpress.com',
    'dnb.com', 'zoominfo.com', 'kompass.com'
]

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""

def clean_phone(p):
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip()
    return s if s.startswith("'") else f"'{s}"

def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching per skill enrich-maps: exact, brackets, delimiters, or long substring"""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q = re.sub(r'["\'„“”«»]', '', str(query_name)).strip().lower()
    c = re.sub(r'["\'„“”«»]', '', str(candidate_name)).strip().lower()
    
    # Loại bỏ hình thức pháp lý để so khớp cốt lõi
    for lf in ['spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'a.s.', 'a. s.', 'k.s.', 'v.o.s.', 'druzstvo', 'gmbh', 'v likvidácii', 'v likvidacii', 'v konkurze']:
        q = q.replace(lf, '').strip()
        c = c.replace(lf, '').strip()
        
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    if q == c_nobrackets:
        return True, "BRACKET_MATCH"
        
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c) if p.strip()]
    if any(p == q for p in parts):
        return True, "DELIMITER_MATCH"
        
    # Nếu tên công ty có độ dài >= 5 ký tự và nằm gọn trong tên kết quả
    if len(q) >= 5 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    return False, "NO_MATCH"

def score_email_b2b(email, domain=""):
    """Hàm chấm điểm email B2B cho Manpower Agency theo chuẩn GEMINI.md"""
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    # Loại bỏ mail version rác / js bundles (es-module-shims@1.10.0, 1@yu.wk...)
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
        
    # Loại bỏ mail template rác / web developer demo
    if any(bad in d for bad in ['sentry', 'wixpress', 'wix.com', 'example.com', 'domain.com', 'email.com', 'address.com', 'mail.sk']):
        return -1
    if any(bad in u for bad in ['sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply', 'donotreply', 'es-module', 'someone', 'john.doe', 'privacy', 'gdpr']):
        return -1
    if u in ['mail', 'email'] and (d in ['mail.sk', 'email.com', 'address.com'] or u == d.split('.')[0]):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.sk'):
        score += 25

    # Ưu tiên số 1: Tuyển dụng / Nhân sự / Việc làm (+50đ)
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career', 'job']:
        score += 50
    # Ưu tiên số 2: Ban Giám Đốc / Lãnh đạo điều hành (+45đ)
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']:
        score += 45
    # Ưu tiên số 3: Cổng liên hệ chính thức / Thông tin (+40đ)
    elif u in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria', 'agency']:
        score += 40
    # Email cá nhân đích danh (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # Email kỹ thuật / hỗ trợ chung (+5đ)
    elif u in ['support', 'admin', 'servis', 'faktury']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def fetch_html_stealth(url):
    """Fetch HTML với curl_cffi chrome120 hoặc urllib fallback"""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=7, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""

def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor per Skill crawl-mail"""
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith('http'):
        web_url = f"https://{web_url}"
    if any(bad in web_url.lower() for bad in BLACKLIST_DOMAINS):
        return ""
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
    if home_html:
        # Priority 1: Check mailto on homepage
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = m.split('?')[0].strip().lower()
            if '@' in clean_m:
                found.add(clean_m)
        # Check cloudflare on homepage
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = decode_cf(cf)
            if '@' in dec:
                found.add(dec.strip().lower())
        # Check direct regex on homepage
        for em in EMAIL_REGEX.findall(home_html):
            if score_email_b2b(em, root) > 0:
                found.add(em.strip().lower())
                
        # Nếu tìm được email khớp domain có điểm số cao (>= 75đ), trả về ngay
        best_home = select_best_email(found, root)
        if best_home and score_email_b2b(best_home, root) >= 75:
            return best_home

        # Priority 2: Extract real DOM contact links from homepage (<a href="...">)
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].lower()
                txt = a.get_text().lower()
                if any(k in h or k in txt for k in ['kontakt', 'kontakty', 'contact', 'o-nas', 'kariera', 'praca', 'impressum', 'career', 'about']):
                    full = urllib.parse.urljoin(web_url, a['href'])
                    if full not in dom_contact_links and '#' not in a['href'] and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)
                        
            for cl in dom_contact_links[:5]:
                chtml = fetch_html_stealth(cl)
                if not chtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = m.split('?')[0].strip().lower()
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = decode_cf(cf)
                    if '@' in dec:
                        found.add(dec.strip().lower())
                for em in EMAIL_REGEX.findall(chtml):
                    if score_email_b2b(em, root) > 0:
                        found.add(em.strip().lower())
                if found and any(score_email_b2b(e, root) >= 60 for e in found):
                    break
        except Exception:
            pass

    # Priority 3: Fallback Guess Paths if still nothing found
    if not found:
        guess_paths = [
            f"{root}/kontakt", f"{root}/sk/kontakt", f"{root}/kontakt.html", f"{root}/kontakty",
            f"{root}/o-nas", f"{root}/kariera", f"{root}/praca", f"{root}/contact", f"{root}/contact.html"
        ]
        for gp in guess_paths:
            ghtml = fetch_html_stealth(gp)
            if not ghtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                clean_m = m.split('?')[0].strip().lower()
                if '@' in clean_m:
                    found.add(clean_m)
            for em in EMAIL_REGEX.findall(ghtml):
                if score_email_b2b(em, root) > 0:
                    found.add(em.strip().lower())
            if found:
                break

    return select_best_email(found, root)

def save_and_reorder_files(df, output_1enr, output_2col):
    """
    Lưu 2 file chuẩn hóa:
    - 1ENR: CSDL đầy đủ tất cả cột.
    - 2COL: Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu danh sách!
    """
    # 1. Chuẩn hóa SĐT có nháy đơn
    if 'Phone' in df.columns:
        df['Phone'] = df['Phone'].apply(clean_phone)
    if 'SĐT' in df.columns:
        df['SĐT'] = df['SĐT'].apply(clean_phone)

    # 2. Phân loại Has Email vs No Email
    em_col = 'Email' if 'Email' in df.columns else None
    if em_col:
        has_em = df[df[em_col].notna() & (df[em_col].astype(str).str.strip() != '') & (df[em_col].astype(str).str.strip() != 'nan')].copy()
        no_em = df[df[em_col].isna() | (df[em_col].astype(str).str.strip() == '') | (df[em_col].astype(str).str.strip() == 'nan')].copy()
        df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    else:
        df_sorted = df.copy()

    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

    # 3. Tạo file 2COL (Chuẩn 20 cột)
    col20_rows = []
    for idx, row in df_sorted.iterrows():
        cname = str(row.get('Company', '') or row.get('Công ty', '')).strip()
        director = str(row.get('Key_Principal', '') or row.get('Người liên hệ', '')).strip()
        phone = str(row.get('Phone', '') or row.get('SĐT', '')).strip()
        web = str(row.get('Website', '') or row.get('Liên Hệ', '') or row.get('Web', '')).strip()
        email = str(row.get('Email', '')).strip()
        addr = str(row.get('Address', '') or row.get('Địa chỉ', '')).strip()
        city = str(row.get('City', '') or row.get('Thành phố', '')).strip()
        full_addr = f"{addr}, {city}".strip(', ') if city and city not in addr else addr

        r20 = {
            'No.': idx + 1,
            'Công ty': cname,
            'Chức danh': 'Konateľ / Director' if director else '',
            'Người liên hệ': director,
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': 'Agentúry dočasného zamestnávania / Employment Agency'
        }
        col20_rows.append(r20)

    df_2col = pd.DataFrame(col20_rows, columns=COL_20_HEADERS)
    df_2col.to_csv(output_2col, index=False, encoding='utf-8-sig')
    return len(has_em) if em_col else 0

async def run_enrichment(input_csv, headless=False, limit=0):
    print("=" * 80)
    print(" GOOGLE MAPS & WEB DATA ENRICHMENT - SLOVAK EMPLOYMENT AGENCIES")
    print("=" * 80)
    print(f"[*] Input File   : {input_csv}")
    print(f"[*] Output 1ENR  : {OUTPUT_1ENR_CSV}")
    print(f"[*] Output 2COL  : {OUTPUT_2COL_CSV}")
    print(f"[*] Cache JSON   : {CACHE_PATH}")
    print(f"[*] Trình duyệt  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False - Quan sát tiến độ)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(input_csv):
        print(f"[ERROR] Không tìm thấy file: '{input_csv}'")
        return

    df = pd.read_csv(input_csv, encoding='utf-8-sig', dtype=str).fillna('')
    
    # Chuẩn hóa tên cột
    name_col = 'Company' if 'Company' in df.columns else ('Công ty' if 'Công ty' in df.columns else df.columns[1])
    city_col = 'City' if 'City' in df.columns else ('Thành phố' if 'Thành phố' in df.columns else None)
    web_col = 'Website' if 'Website' in df.columns else ('Liên Hệ' if 'Liên Hệ' in df.columns else ('Web' if 'Web' in df.columns else None))
    phone_col = 'Phone' if 'Phone' in df.columns else ('SĐT' if 'SĐT' in df.columns else None)
    email_col = 'Email' if 'Email' in df.columns else None

    # Bổ sung các cột nếu chưa có
    if not phone_col:
        phone_col = 'Phone'
        df[phone_col] = ''
    if not email_col:
        email_col = 'Email'
        df[email_col] = ''
    if not web_col:
        web_col = 'Website'
        df[web_col] = ''

    # Đọc cache nếu có
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp cache: {len(cache)} bản ghi đã được xử lý từ trước.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # Đưa các bản ghi đã có email sẵn vào cache
    for idx, row in df.iterrows():
        comp = str(row[name_col]).strip()
        em = str(row[email_col]).strip()
        wb = str(row[web_col]).strip()
        ph = str(row[phone_col]).strip()
        if comp and em and em != 'nan':
            cache[comp.lower()] = {
                'Web': wb,
                'Email': em,
                'Phone': ph
            }

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="sk-SK"
        )
        # Bỏ qua cookie consent Google
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        total = len(df) if limit == 0 else min(limit, len(df))
        processed = 0
        new_emails = 0
        new_webs = 0
        new_phones = 0

        for idx, row in df.iterrows():
            if limit > 0 and processed >= limit:
                break

            comp = str(row[name_col]).strip()
            city = str(row[city_col]).strip() if city_col and pd.notna(row[city_col]) else ""
            current_web = str(df.at[idx, web_col]).strip()
            current_email = str(df.at[idx, email_col]).strip()
            current_phone = str(df.at[idx, phone_col]).strip()
            cache_key = comp.lower()

            # Nếu trong cache đã có kết quả
            if cache_key in cache:
                c_item = cache[cache_key]
                if c_item.get('Email') and not current_email:
                    df.at[idx, email_col] = c_item['Email']
                if c_item.get('Web') and not current_web:
                    df.at[idx, web_col] = c_item['Web']
                if c_item.get('Phone') and not current_phone:
                    df.at[idx, phone_col] = c_item['Phone']

                # Cập nhật lại giá trị hiện tại
                current_web = str(df.at[idx, web_col]).strip()
                current_email = str(df.at[idx, email_col]).strip()
                current_phone = str(df.at[idx, phone_col]).strip()

                # Nếu đã có cả Web và Email, có thể bỏ qua query Google Maps
                if current_email and current_web:
                    processed += 1
                    print(f"[{processed:04d}/{total}] {comp[:32]:<32} | Cache Hit: {current_email}")
                    continue

            # Bước 1: Nếu đã có Web từ D&B nhưng chưa có Email -> Quét trực tiếp website trước!
            if current_web and not current_email:
                em_found = crawl_site_for_emails(current_web)
                if em_found:
                    df.at[idx, email_col] = em_found
                    current_email = em_found
                    new_emails += 1

            # Bước 2: Nếu chưa có Web hoặc chưa có Phone -> Tìm kiếm Google Maps!
            matched = False
            gmap_web = None
            gmap_phone = None

            if not current_web or not current_phone:
                q_term = f"{comp} {city} Slovakia".strip()
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                    await page.wait_for_timeout(1800)

                    # Kiểm tra Captcha
                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\n\a[CẢNH BÁO] Phát hiện Captcha trên Google Maps! Vui lòng bấm xác minh trên cửa sổ Chrome...\n")
                        await page.wait_for_timeout(10000)

                    # 1. Danh sách kết quả (Multiple places)
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
                        # 2. Trang chi tiết địa điểm trực tiếp (Direct place panel)
                        title_elem = await page.query_selector('h1.DUwDvf')
                        if title_elem:
                            t_text = await title_elem.inner_text()
                            is_ok, reason = is_valid_name_match(comp, t_text)
                            matched = is_ok

                    if matched:
                        # Lấy website
                        web_btn = await page.query_selector('a[data-item-id="authority"]')
                        if web_btn:
                            cand_web = await web_btn.get_attribute('href')
                            if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                                gmap_web = cand_web

                        # Lấy số điện thoại
                        phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                        if phone_btn:
                            p_attr = await phone_btn.get_attribute('data-item-id')
                            if p_attr and p_attr.startswith('phone:tel:'):
                                gmap_phone = p_attr.replace('phone:tel:', '').strip()
                            else:
                                p_txt = await phone_btn.inner_text()
                                if re.search(r'\d{3,}', p_txt):
                                    gmap_phone = p_txt.strip()
                except Exception as ex:
                    pass

            # Bước 3: Cập nhật Web & Phone từ Google Maps
            if gmap_web:
                if not current_web:
                    df.at[idx, web_col] = gmap_web
                    current_web = gmap_web
                    new_webs += 1
            if gmap_phone:
                formatted_p = clean_phone(gmap_phone)
                if not current_phone:
                    df.at[idx, phone_col] = formatted_p
                    current_phone = formatted_p
                    new_phones += 1

            # Bước 4: Nếu vừa tìm được web mới từ ggmap và chưa có email -> Quét email ngay!
            if current_web and not current_email:
                em_found = crawl_site_for_emails(current_web)
                if em_found:
                    df.at[idx, email_col] = em_found
                    current_email = em_found
                    new_emails += 1

            # Bước 5: Cập nhật cache
            cache[cache_key] = {
                'Web': current_web,
                'Email': current_email,
                'Phone': current_phone,
                'Matched': matched
            }

            processed += 1
            status_mail = f"[EMAIL] {current_email}" if current_email else "No email"
            status_web = current_web[:30] if current_web else "No web"
            status_match = " [GMAP MATCH]" if matched else ""
            print(f"[{processed:04d}/{total}] {comp[:30]:<30} | {status_web:<30} | {status_mail}{status_match}")

            # Lưu tăng dần (Incremental Checkpoint) mỗi 5 dòng
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                em_top = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {em_top} công ty có Email được đẩy lên đầu file CSV.")

            # Tái tạo trang Chromium định kỳ mỗi 25 lượt để giải phóng RAM
            if processed % 25 == 0:
                try:
                    await page.close()
                    page = await context.new_page()
                except Exception:
                    pass

        await browser.close()

    # Lưu bản cuối cùng
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    em_top = save_and_reorder_files(df, OUTPUT_1ENR_CSV, OUTPUT_2COL_CSV)

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
    print(f"[*] Tổng công ty đã xử lý : {processed}/{total}")
    print(f"[*] Số công ty có EMAIL   : {em_top} (100% được sắp xếp lên đầu file CSV)")
    print(f"[*] File CSDL Chi tiết    : {OUTPUT_1ENR_CSV}")
    print(f"[*] File Cold Mail 20 Cột : {OUTPUT_2COL_CSV}")
    print("=" * 80)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Slovak Employment Agencies via Google Maps & Web Crawler")
    parser.add_argument('--input', default=str(DEFAULT_INPUT_CSV), help="File CSV nguồn cần làm giàu")
    parser.add_argument('--headless', action='store_true', help="Chạy ẩn danh không mở cửa sổ trình duyệt")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số lượng bản ghi chạy thử nghiệm (0 = toàn bộ)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(input_csv=args.input, headless=args.headless, limit=args.limit))
