# -*- coding: utf-8 -*-
"""
RESCUE PASS: SMART GOOGLE MAPS & WEB EMAIL ENRICHMENT FOR SLOVAK EMPLOYMENT AGENCIES
Tuân thủ toàn bộ Rule 11 tại GEMINI.md và skill enrich-maps:
1. Smart & Strict Name Matcher:
   - Unicode NFKD diacritics stripping (á->a, č->c, ď->d, é->e, í->i, ľ->l, ň->n, ó->o, ô->o, ŕ->r, š->s, ť->t, ú->u, ý->y, ž->z).
   - Làm sạch triệt để dấu phẩy, dấu chấm, gạch nối thừa sau khi cắt legal forms (s.r.o., a.s., v likvidácii...).
   - Bóc tách bản dịch tiếng Anh tự động trong ngoặc (...) của Google Maps.
2. Tối ưu truy vấn Google Maps: Tên cốt lõi + Thành phố + Slovakia.
3. Fallback đa tầng:
   - Quét sâu DOM menu homepage + subpages (/kontakt, /sk/kontakt, /kariera, /o-nas...).
   - Quét Facebook Fanpage từ website nếu web dùng contact form không có email trong HTML tĩnh.
4. Chấm điểm email B2B (score_email_b2b) tối ưu cho Manpower Agency:
   - praca@, kariera@, hr@, personalne@, jobs@ (+50đ)
   - vedenie@, konatel@, riaditel@, ceo@, director@ (+45đ)
   - info@, kontakt@, office@ (+40đ)
5. Lưu tăng dần mỗi 5 dòng vào SK_AGCY_DNB_1ENR.csv & SK_AGCY_DNB_2COL.csv, 100% email lên đầu.
"""

import asyncio
import os
import sys
import re
import ssl
import json
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

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")
CSV_1ENR = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_1ENR.csv"
CSV_2COL = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_2COL.csv"
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

def normalize_text_core(s):
    """Khử dấu Unicode NFKD, loại bỏ ngoặc kép, legal forms và dấu câu thừa."""
    if not s:
        return ""
    # 1. Khử dấu Unicode NFKD đa quốc gia (á->a, č->c, ď->d, é->e, í->i, ľ->l, ň->n, ó->o, ô->o, ŕ->r, š->s, ť->t, ú->u, ý->y, ž->z)
    s_norm = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8').lower()
    s_norm = re.sub(r'["\'„“”«»]', '', s_norm)
    # 2. Loại bỏ legal forms Slovakia
    for lf in ['spol. s r.o.', 'spol. s r. o.', 'spol. s.r.o.', 's.r.o.', 's. r. o.', 'a.s.', 'a. s.', 
               'k.s.', 'v.o.s.', 'druzstvo', 'gmbh', 'v likvidacii', 'v konkurze', 'organizacna zlozka']:
        s_norm = re.sub(rf'\b{re.escape(lf)}\b', '', s_norm)
    # 3. Cắt sạch dấu câu thừa ở đầu/cuối
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

def score_email_b2b(email, domain=""):
    """Hàm chấm điểm email B2B cho Manpower Agency theo chuẩn GEMINI.md"""
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if any(bad in d for bad in ['sentry', 'wixpress', 'wix.com', 'example.com', 'domain.com', 'email.com', 'address.com', 'mail.sk']):
        return -1
    if any(bad in u for bad in ['sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply', 'donotreply', 'es-module', 'someone', 'john.doe', 'privacy', 'gdpr']):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.sk'):
        score += 25

    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career', 'job', 'naborove']:
        score += 50
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']:
        score += 45
    elif u in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria', 'agency']:
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif u in ['support', 'admin', 'servis', 'faktury']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def fetch_html_stealth(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=3.0) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=(2, 3), verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor với Fallback Facebook Fanpage."""
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
    fb_links = []
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
    if home_html:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = m.split('?')[0].strip().lower()
            if '@' in clean_m:
                found.add(clean_m)
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = decode_cf(cf)
            if '@' in dec:
                found.add(dec.strip().lower())
        for em in EMAIL_REGEX.findall(home_html):
            if score_email_b2b(em, root) > 0:
                found.add(em.strip().lower())
                
        best_home = select_best_email(found, root)
        if best_home and score_email_b2b(best_home, root) >= 75:
            return best_home

        # Bóc tách subpages & Facebook links
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href']
                h_low = h.lower()
                txt = a.get_text().lower()
                if 'facebook.com/' in h_low and not any(bad in h_low for bad in ['sharer', 'share.php', 'plugins']):
                    if h not in fb_links:
                        fb_links.append(h)
                if any(k in h_low or k in txt for k in ['kontakt', 'kontakty', 'contact', 'o-nas', 'kariera', 'praca', 'impressum', 'about']):
                    full = urllib.parse.urljoin(web_url, h)
                    if full not in dom_contact_links and '#' not in h and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)
                        
            for cl in dom_contact_links[:3]:
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

    # 2. Guess paths (tinh gọn 3 đường dẫn cốt lõi)
    if not found:
        guess_paths = [f"{root}/kontakt", f"{root}/sk/kontakt", f"{root}/contact"]
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

    # 3. Facebook Fallback nếu website không có email trong HTML tĩnh
    if not found and fb_links:
        for fbl in fb_links[:1]:
            fb_html = fetch_html_stealth(fbl)
            if fb_html:
                for em in EMAIL_REGEX.findall(fb_html):
                    if score_email_b2b(em, root) > 0:
                        found.add(em.strip().lower())

    return select_best_email(found, root)


def save_and_reorder_files(df, output_1enr, output_2col):
    df_out = df.copy()
    if 'Phone' in df_out.columns:
        df_out['Phone'] = df_out['Phone'].apply(clean_phone)
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone)

    em_col = 'Email' if 'Email' in df_out.columns else None
    if em_col:
        has_em = df_out[df_out[em_col].notna() & (df_out[em_col].astype(str).str.strip() != '') & (df_out[em_col].astype(str).str.strip() != 'nan')].copy()
        no_em = df_out[df_out[em_col].isna() | (df_out[em_col].astype(str).str.strip() == '') | (df_out[em_col].astype(str).str.strip() == 'nan')].copy()
        df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    else:
        df_sorted = df_out.copy()

    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(output_1enr, index=False, encoding='utf-8-sig')

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
            'Lương': '', 'Ngày đăng': '', 'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '', 'Last Body HTML': '', 'Trạng thái Reply': '',
            'Lần Follow-up': '0', 'Ngày Follow-up gần nhất': '', 'Mailbox đã dùng': '',
            'Category': 'Agentúry dočasného zamestnávania / Employment Agency'
        }
        col20_rows.append(r20)

    df_2col = pd.DataFrame(col20_rows, columns=COL_20_HEADERS)
    df_2col.to_csv(output_2col, index=False, encoding='utf-8-sig')
    return len(has_em) if em_col else 0

async def run_rescue(headless=False, limit=0):
    print("=" * 80)
    print(" RESCUE PASS: SMART GOOGLE MAPS ENRICHMENT - SLOVAK EMPLOYMENT AGENCIES")
    print("=" * 80)
    print(f"[*] CSDL Chi tiet : {CSV_1ENR}")
    print(f"[*] Cold Mail 20C : {CSV_2COL}")
    print(f"[*] Cache JSON    : {CACHE_PATH}")
    print(f"[*] Trinh duyet   : {'Chay ngam (Headless)' if headless else 'Truc quan (Headless=False)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(CSV_1ENR):
        print(f"[ERROR] Khong tim thay file: {CSV_1ENR}")
        return

    df = pd.read_csv(CSV_1ENR, encoding='utf-8-sig', dtype=str).fillna('')
    name_col = 'Company' if 'Company' in df.columns else 'Công ty'
    web_col = 'Website' if 'Website' in df.columns else 'Liên Hệ'
    phone_col = 'Phone' if 'Phone' in df.columns else 'SĐT'
    city_col = 'City' if 'City' in df.columns else 'Thành phố'

    # Lọc danh sách các công ty ĐANG THIẾU EMAIL để cứu hộ
    missing_mask = (df['Email'].str.strip() == '') | (df['Email'].str.strip() == 'nan')
    missing_indices = df[missing_mask].index.tolist()

    print(f"[*] Tong so cong ty trong CSDL : {len(df)}")
    print(f"[*] Da co Email thanh cong      : {len(df) - len(missing_indices)}")
    print(f"[*] CAN CUU HO (Dang thieu Mail): {len(missing_indices)} cong ty\n")

    if not missing_indices:
        print("[✔] 100% cong ty da co email!")
        return

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            pass

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
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        rescued_emails = 0
        rescued_webs = 0
        rescued_phones = 0

        target_list = missing_indices if limit == 0 else missing_indices[:limit]

        for idx in target_list:
            comp = str(df.at[idx, name_col]).strip()
            city = str(df.at[idx, city_col]).strip() if city_col in df.columns else ""
            cache_key = comp.lower()

            # Bước 1: Nếu đã có Web sẵn nhưng chưa có email (như manpower.sk, atena.sk...) -> Quét sâu lại
            curr_web = str(df.at[idx, web_col]).strip()
            curr_phone = str(df.at[idx, phone_col]).strip()
            found_email = ""

            if curr_web:
                found_email = crawl_site_for_emails(curr_web)
                if found_email:
                    df.at[idx, 'Email'] = found_email
                    rescued_emails += 1

            # Bước 2: Nếu chưa có Web hoặc chưa tìm được Email -> Tìm Google Maps với Smart Match
            matched = False
            gmap_web = None
            gmap_phone = None

            if not curr_web or not found_email:
                core_name = normalize_text_core(comp)
                q_term = f"{core_name} {city} Slovakia".strip() if city else f"{core_name} Slovakia".strip()
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                    await page.wait_for_timeout(2000)

                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\n\a[CANH BAO] Google Maps xuat hien Captcha! Vui long bam xac minh tren Chrome...\n")
                        await page.wait_for_timeout(10000)

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
                        title_elem = await page.query_selector('h1.DUwDvf')
                        if title_elem:
                            t_text = await title_elem.inner_text()
                            is_ok, reason = is_valid_name_match(comp, t_text)
                            matched = is_ok

                    if matched:
                        web_btn = await page.query_selector('a[data-item-id="authority"]')
                        if web_btn:
                            cand_web = await web_btn.get_attribute('href')
                            if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                                gmap_web = cand_web

                        phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                        if phone_btn:
                            p_attr = await phone_btn.get_attribute('data-item-id')
                            if p_attr and p_attr.startswith('phone:tel:'):
                                gmap_phone = p_attr.replace('phone:tel:', '').strip()
                            else:
                                p_txt = await phone_btn.inner_text()
                                if re.search(r'\d{3,}', p_txt):
                                    gmap_phone = p_txt.strip()
                except Exception:
                    pass

            # Cập nhật thông tin từ Google Maps
            if gmap_web and not curr_web:
                df.at[idx, web_col] = gmap_web
                curr_web = gmap_web
                rescued_webs += 1

            if gmap_phone and not curr_phone:
                df.at[idx, phone_col] = clean_phone(gmap_phone)
                rescued_phones += 1

            # Quét website mới tìm được từ Google Maps
            if curr_web and not found_email:
                found_email = crawl_site_for_emails(curr_web)
                if found_email:
                    df.at[idx, 'Email'] = found_email
                    rescued_emails += 1

            # Cập nhật cache JSON
            cache[cache_key] = {
                'Web': curr_web,
                'Email': found_email,
                'Phone': df.at[idx, phone_col],
                'Matched': matched
            }

            processed += 1
            status_em = f"[RESCUED] {found_email}" if found_email else ("No email" if curr_web else "No web")
            status_web = curr_web[:30] if curr_web else "No web"
            status_match = " [SMART MATCH]" if matched else ""
            print(f"[{processed:04d}/{len(target_list)}] {comp[:30]:<30} | {status_web:<30} | {status_em}{status_match}")

            # Checkpoint mỗi 5 dòng
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_total = save_and_reorder_files(df, CSV_1ENR, CSV_2COL)
                print(f"  --> [CHECKPOINT] Da luu tang dan! Tong so cong ty co Email hien tai: {cur_total}/{len(df)}")

            if processed % 25 == 0:
                try:
                    await page.close()
                    page = await context.new_page()
                except Exception:
                    pass

        await browser.close()

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    final_total = save_and_reorder_files(df, CSV_1ENR, CSV_2COL)

    print("\n" + "=" * 80)
    print(" HOAN TAT VONG CUU HO MOI GIOI VIEC LAM SLOVAKIA!")
    print(f"[*] So cong ty da kiem tra cuu ho : {processed}")
    print(f"[*] So Website moi cuu ho duoc    : {rescued_webs}")
    print(f"[*] So Email moi cuu ho duoc      : {rescued_emails}")
    print(f"[*] TONG SO EMAIL CO DUOC HIEN TAI: {final_total} / {len(df)} cong ty (Da gom 100% len dau)")
    print(f"[*] File CSDL Chi tiet : {CSV_1ENR}")
    print(f"[*] File Cold Mail 20C : {CSV_2COL}")
    print("=" * 80)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Rescue Pass for Slovak Employment Agencies")
    parser.add_argument('--headless', action='store_true', help="Chay an danh khong mo Chrome")
    parser.add_argument('--limit', type=int, default=0, help="Gioi han so cong ty test (0 = toan bo danh sach thieu)")
    args = parser.parse_args()

    asyncio.run(run_rescue(headless=args.headless, limit=args.limit))
