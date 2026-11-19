# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN METAL & FABRICATION FACTORIES
======================================================================
Mục tiêu: Làm giàu dữ liệu bằng Google Maps cho danh sách công ty kim loại Litva
          vừa được bóc tách từ info.lt (LT_METL_INLT_1ENR.csv).

Input:  LT_METL_INLT_1ENR.csv (1,990 công ty kim loại Litva)
Output: LT_METL_INLT_1ENR.csv + LT_METL_INLT_2COL.csv + LT_METL_INLT_ONLY_EMAILS_READY.csv

Quy chuẩn tuân thủ nghiêm ngặt GEMINI.md & Skill enrich-maps:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2: SĐT luôn có nháy đơn ('+370...)
- Rule 3: B2B Email Scoring, giữ duy nhất 1 email tốt nhất, đẩy 100% email lên đầu
- Rule 4: Trình duyệt thực tế (headless=False), viewport >= 1280x800
- Rule 5: Incremental Auto-Save sau mỗi 5 công ty, checkpoint cache JSON để Resume 100%
- Rule 10: Tên file cố định 17 ký tự
- Rule 11: So khớp tên thông minh với NFKD, bóc tách legal forms Litva (Smart & Strict Name Matching)
- Rule 12: Loại trừ danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre)
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

# File mục tiêu vừa làm giàu từ info.lt
INPUT_CSV_PATH = ROOT_DIR / "LT_METL_INLT_1ENR.csv"
FALLBACK_CSV_PATH = ROOT_DIR / "LT_METL_LTOR_0RAW.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_METL_INLT_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_METL_INLT_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_METL_INLT_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_metal.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

VPN_TIMEOUT = 35000
VPN_DELAY = 2.0

# Rule 12: Permanent blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'tiktok.com', 'pinterest.com', 'google.com', 'maps.google.com', 'wikipedia.org',
    'yellowpages', 'tripadvisor', 'booking.com', 'yelp.com', 'sentry.io', 'wixpress.com',
    'rekvizitai.vz.lt', 'rekvizitai.lt', 'info.lt', 'visalietuva.lt', 'imones.lt',
    'statyba.lt', 'cr.lt', 'okredo.com', 'scoris.lt', 'creditinfo.lt', 'cvbankas.lt',
    'cvonline.lt', 'cvmarket.lt', 'dirbk.lt', 'registrucentras.lt', 'vmi.lt', 'sodra.lt',
    '1588.lt', '1551.lt', 'infoplius.lt', 'imoniugidas.lt', 'verslas.lt', 'spec.lt',
    'litorg.cc', 'delfi.lt', '15min.lt', 'lrytas.lt', 'tv3.lt', 'alfa.lt'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]


# ----------------------------------------------------------------------
# CHUẨN HÓA VĂN BẢN & SO KHỚP TÊN (RULE 11, 12 - SKILL ENRICH-MAPS)
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str):
    """Rule 2: Chuẩn hóa SĐT Litva có nháy đơn (') ở đầu"""
    if not phone_str or not isinstance(phone_str, str) or str(phone_str).strip() in ['', 'None', 'nan']:
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
    """Rule 3: Làm sạch triệt để ký tự lạ, %20, \\u00a0, zero-width space"""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    return re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e).strip()


def normalize_text(text):
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    t = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'["\'„“”«»]', '', t).strip()


def clean_company_name_lt(name):
    """Bóc tách loại hình doanh nghiệp Litva (Rule 11)"""
    if not name:
        return ""
    t = normalize_text(name)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    legal_forms = [
        'uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove',
        'individuali imone', 'viesoji istaiga',
        'uab', 'mb', 'ab', 'ii', 'vsi', 'tub', 'kub', 'filialas'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
    return re.sub(r'\s+', ' ', t).strip(' ,.-')


def is_valid_name_match_lt(query_name, candidate_name):
    """
    So khớp tên thông minh & nghiêm ngặt (Skill enrich-maps Section 2.A)
    """
    q_c = clean_company_name_lt(query_name)
    c_c = clean_company_name_lt(candidate_name)
    if not q_c or not c_c:
        return False, "EMPTY"

    # 1. Khớp hoàn toàn
    if q_c == c_c or re.sub(r'[^a-z0-9]', '', q_c) == re.sub(r'[^a-z0-9]', '', c_c):
        return True, "EXACT"

    # 2. Khớp sau khi bỏ ngoặc dịch/chú thích
    c_nobr = re.sub(r'\(.*?\)|\[.*?\]', '', c_c).strip()
    if q_c == c_nobr or re.sub(r'[^a-z0-9]', '', q_c) == re.sub(r'[^a-z0-9]', '', c_nobr):
        return True, "BRACKET"

    # 3. Phân tách theo dấu ngăn cách (chi nhánh, thành phố, dịch vụ)
    parts = [clean_company_name_lt(p) for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    if any(q_c == p or re.sub(r'[^a-z0-9]', '', q_c) == re.sub(r'[^a-z0-9]', '', p) for p in parts if p):
        return True, "DELIMITER"

    # 4. Token Overlap nếu tên có 2 từ dài trở lên
    t1 = set(re.findall(r'[a-z0-9]{3,}', q_c))
    t2 = set(re.findall(r'[a-z0-9]{3,}', c_c))
    if t1 and t2:
        overlap = len(t1.intersection(t2))
        if overlap == len(t1) or (len(t1) >= 2 and overlap >= 2 and overlap / len(t1) >= 0.75):
            return True, "TOKEN_MATCH"

    return False, "NO_MATCH"


def is_valid_website(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        domain = urllib.parse.urlparse(u).netloc.replace('www.', '').lower()
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        return not any(bad in domain for bad in BLACKLIST_DOMAINS)
    except Exception:
        return False


def score_email_b2b_lt(email, domain=""):
    """Rule 3: Chấm điểm email B2B cho thị trường Kim loại Litva"""
    if not email:
        return -1
    e = clean_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if any(bad in d for bad in BLACKLIST_DOMAINS):
        return -1
    if u in ['noreply', 'no-reply', 'privacy', 'gdpr', 'abuse', 'webmaster', 'sentry', 'test', 'sample']:
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 35

    # Ưu tiên nhân sự / tuyển dụng (+50)
    if any(k in u for k in ['karjera', 'darbas', 'personalas', 'hr', 'jobs', 'recruitment', 'career']):
        score += 50
    # Lãnh đạo / Giám đốc / Kỹ thuật (+45)
    elif any(k in u for k in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'pardavimai', 'gamyba', 'technikos']):
        score += 45
    # Cổng liên hệ chính thức (+40)
    elif any(k in u for k in ['info', 'kontaktai', 'office', 'biuras', 'administracija', 'bendras']):
        score += 40
    # Cá nhân đích danh (+25)
    elif '.' in u and score >= 60:
        score += 25
    # Webmail (+10)
    elif d in ['gmail.com', 'inbox.lt', 'one.lt']:
        score += 10

    return score


def select_best_email(emails, domain=""):
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


# ----------------------------------------------------------------------
# BÓC TÁCH EMAIL TRÊN WEBSITE CÔNG TY (PRIORITY 10 DOM MENU)
# ----------------------------------------------------------------------
async def crawl_website_for_email(page, web_url):
    if not is_valid_website(web_url):
        return ""
    if not web_url.startswith('http'):
        web_url = 'https://' + web_url

    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found_emails = set()

    try:
        await page.goto(web_url, wait_until='domcontentloaded', timeout=VPN_TIMEOUT)
        await asyncio.sleep(2.0)
        html = await page.content()

        # Cloudflare decoded emails
        for m in re.findall(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', html):
            try:
                r = int(m[:2], 16)
                dec = ''.join([chr(int(m[i:i+2], 16) ^ r) for i in range(2, len(m), 2)])
                found_emails.add(clean_email(dec))
            except Exception:
                pass

        # mailto:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
            found_emails.add(clean_email(m))

        # regex emails
        for em in EMAIL_REGEX.findall(html):
            found_emails.add(clean_email(em))

        best = select_best_email(found_emails, root)
        if best and score_email_b2b_lt(best, root) >= 80:
            return best

        # Tìm link menu liên hệ (Priority 10 trên DOM)
        soup = BeautifulSoup(html, 'html.parser')
        contact_links = []
        for a in soup.find_all('a', href=True):
            h = a['href'].lower()
            txt = a.get_text().lower()
            if any(k in h or k in txt for k in ['kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai', 'contact', 'about']):
                full = urllib.parse.urljoin(web_url, a['href'])
                if root in full and full not in contact_links and '#' not in a['href']:
                    contact_links.append(full)

        for cl in contact_links[:3]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(1.5)
                sub_html = await page.content()
                for m in re.findall(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', sub_html):
                    try:
                        r = int(m[:2], 16)
                        dec = ''.join([chr(int(m[i:i+2], 16) ^ r) for i in range(2, len(m), 2)])
                        found_emails.add(clean_email(dec))
                    except Exception:
                        pass
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                    found_emails.add(clean_email(m))
                for em in EMAIL_REGEX.findall(sub_html):
                    found_emails.add(clean_email(em))
                if found_emails and any(score_email_b2b_lt(e, root) >= 70 for e in found_emails):
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
    df_out = df.copy()
    if 'Cong ty' in df_out.columns:
        df_out = df_out[~df_out['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['SDT'] = df_out['SDT'].apply(clean_phone_lt)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # Đẩy 100% email lên đầu (Rule 3)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi_Quan_Ly', r.get('Nguoi quan ly', ''))).strip()
        title = str(r.get('Chuc_Danh', r.get('Chuc danh', ''))).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('City', r.get('Thanh pho', ''))).strip()
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
            'Lương': r.get('Doanh_Thu', r.get('Doanh thu', '')),
            'Ngày đăng': r.get('Nam_Thanh_Lap', r.get('Nam thanh lap', '')),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Category', 'Manufacture of fabricated metal products')
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')

    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_dir / OUTPUT_READY_PATH.name)
            shutil.copy2(OUTPUT_1ENR_PATH, extra_dir / OUTPUT_1ENR_PATH.name)
        except Exception:
            pass

    return len(has_em)


# ----------------------------------------------------------------------
# TIẾN TRÌNH LÀM GIÀU BẰNG GOOGLE MAPS
# ----------------------------------------------------------------------
async def run_enrichment(limit=None):
    src_file = INPUT_CSV_PATH if INPUT_CSV_PATH.exists() else FALLBACK_CSV_PATH
    if not src_file.exists():
        print(f"[!] Không tìm thấy tệp đầu vào {INPUT_CSV_PATH.name}!")
        return

    df = pd.read_csv(src_file, encoding='utf-8-sig', dtype=str).fillna('')
    for col in ['Website', 'Email', 'SDT', 'Dia chi', 'Nguoi_Quan_Ly', 'Chuc_Danh']:
        if col not in df.columns:
            df[col] = ''

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} bản ghi từ checkpoint cache.")
        except Exception:
            pass

    # Chỉ quét những công ty chưa có Email
    pending_indices = [i for i, r in df.iterrows() if not clean_email(r['Email'])]
    if limit:
        pending_indices = pending_indices[:limit]

    print("=" * 80)
    print("🌟 LÀM GIÀU DỮ LIỆU KIM LOẠI LITVA BẰNG GOOGLE MAPS (ENRICH-MAPS)")
    print(f"   - Tệp nguồn vào     : {src_file.name}")
    print(f"   - Tổng số công ty   : {len(df):,}")
    print(f"   - Đã có Email B2B   : {len(df) - len(pending_indices):,} (Được giữ nguyên 100%)")
    print(f"   - Cần tìm qua Maps  : {len(pending_indices):,}")
    print("=" * 80 + "\n")

    if not pending_indices:
        print("[+] Toàn bộ công ty đều đã có Email!")
        export_and_sync_all_files(df)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=['--start-maximized', '--no-sandbox']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='lt-LT',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        processed = 0
        newly_found = 0

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('City', row.get('Thanh pho', ''))).strip()
            code = str(row.get('Company_Code', '')).strip()
            cache_key = code if code else f"{comp}::{city}"

            processed += 1

            # 1. Kiểm tra cache
            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, 'Email'] = c['Email']
                if c.get('Website') and not df.at[idx, 'Website']:
                    df.at[idx, 'Website'] = c['Website']
                if c.get('SDT') and not df.at[idx, 'SDT']:
                    df.at[idx, 'SDT'] = c['SDT']
                if c.get('Dia chi') and not df.at[idx, 'Dia chi']:
                    df.at[idx, 'Dia chi'] = c['Dia chi']
                if c.get('Email'):
                    print(f"[{processed}/{len(pending_indices)}] [CACHE] {comp} -> {c['Email']}")
                    continue

            # 2. Tìm kiếm trên Google Maps
            search_query = f"{comp} {city} Lietuva"
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(search_query)}?hl=lt"
            print(f"[{processed}/{len(pending_indices)}] 📍 Maps: {comp} ({city})")

            found_web = ""
            found_phone = ""
            found_addr = ""
            found_email = ""

            try:
                await page.goto(maps_url, timeout=VPN_TIMEOUT, wait_until='domcontentloaded')
                await asyncio.sleep(VPN_DELAY)

                # Xử lý Captcha Google nếu có (Rule 4)
                cur_u = page.url.lower()
                c_cnt = await page.content()
                if "sorry" in cur_u or "captcha" in cur_u or "unusual traffic" in c_cnt.lower():
                    print("\a" * 3)
                    print("\n[!] PHÁT HIỆN CAPTCHA! Vui lòng bấm xác thực trên trình duyệt...\n")
                    while "sorry" in page.url.lower() or "captcha" in page.url.lower():
                        await asyncio.sleep(3)
                    print("[+] Captcha đã xử lý xong! Tiếp tục...")

                # Trường hợp 1: Chuyển thẳng vào trang chi tiết 1 công ty
                if "/maps/place/" in page.url:
                    h1 = await page.query_selector('h1.DUwDvf')
                    cand_name = (await h1.inner_text()).strip() if h1 else ""
                    is_match, match_type = is_valid_name_match_lt(comp, cand_name)
                    
                    if is_match:
                        # Nút Website
                        web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="svetain"], a[aria-label*="Website"]')
                        if web_btn:
                            w_href = await web_btn.get_attribute('href')
                            if is_valid_website(w_href):
                                found_web = w_href

                        # Nút SĐT
                        phone_btn = await page.query_selector('button[data-item-id*="phone:"], [aria-label*="Telefonas"]')
                        if phone_btn:
                            p_txt = await phone_btn.inner_text()
                            found_phone = clean_phone_lt(p_txt)

                        # Địa chỉ
                        addr_btn = await page.query_selector('button[data-item-id*="address"], [aria-label*="Adresas"]')
                        if addr_btn:
                            found_addr = (await addr_btn.inner_text()).strip()

                # Trường hợp 2: Hiển thị danh sách kết quả (Feed)
                else:
                    cards = await page.query_selector_all('div[role="feed"] a.hfpxzc, div[role="feed"] div.fontHeadlineSmall')
                    matched_card = None
                    for card in cards[:4]:
                        card_txt = (await card.inner_text()).strip()
                        if not card_txt:
                            card_txt = (await card.get_attribute('aria-label') or '').strip()
                        is_match, match_type = is_valid_name_match_lt(comp, card_txt)
                        if is_match:
                            matched_card = card
                            break

                    if matched_card:
                        await matched_card.click()
                        await asyncio.sleep(2.0)

                        web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="svetain"], a[aria-label*="Website"]')
                        if web_btn:
                            w_href = await web_btn.get_attribute('href')
                            if is_valid_website(w_href):
                                found_web = w_href

                        phone_btn = await page.query_selector('button[data-item-id*="phone:"], [aria-label*="Telefonas"]')
                        if phone_btn:
                            p_txt = await phone_btn.inner_text()
                            found_phone = clean_phone_lt(p_txt)

                        addr_btn = await page.query_selector('button[data-item-id*="address"], [aria-label*="Adresas"]')
                        if addr_btn:
                            found_addr = (await addr_btn.inner_text()).strip()

                # 3. Quét website tìm Email B2B nếu có Website
                target_web = found_web or df.at[idx, 'Website']
                if is_valid_website(target_web):
                    found_email = await crawl_website_for_email(page, target_web)

            except Exception as e:
                print(f"    [!] Error: {e}")

            # Cập nhật kết quả vào DataFrame
            if found_web and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = found_web
            if found_phone and not df.at[idx, 'SDT']:
                df.at[idx, 'SDT'] = found_phone
            if found_addr and not df.at[idx, 'Dia chi']:
                df.at[idx, 'Dia chi'] = found_addr

            if found_email:
                df.at[idx, 'Email'] = found_email
                newly_found += 1
                print(f"    🎯 [+] TÌM THẤY EMAIL: {comp} -> {found_email} (Web: {target_web})")
            elif found_web:
                print(f"    🌐 [~] Khớp Maps: Web: {found_web} | SĐT: {found_phone}")
            else:
                print("    [-] Không tìm thấy thẻ khớp trên Google Maps.")

            cache[cache_key] = {
                'Website': found_web or df.at[idx, 'Website'],
                'SDT': found_phone or df.at[idx, 'SDT'],
                'Dia chi': found_addr or df.at[idx, 'Dia chi'],
                'Email': found_email or df.at[idx, 'Email']
            }

            # Lưu tăng dần sau mỗi 5 công ty (Rule 5)
            if processed % 5 == 0:
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_em = export_and_sync_all_files(df)
                print(f"    [*] Checkpoint saved ({processed}/{len(pending_indices)} | Tổng email: {cur_em:,} | +{newly_found} mới)")

            await asyncio.sleep(1.0)

        # Lưu lần cuối
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        total_em = export_and_sync_all_files(df)
        print(f"\n[+] Hoàn tất làm giàu Google Maps! Doanh nghiệp có email: {total_em:,} / {len(df):,}")

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Enrich Lithuanian Metal Enterprises with Google Maps & Websites")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty cần làm giàu")
    parser.add_argument("--export-only", action="store_true", help="Chỉ xuất lại file Cold Mail từ cache mà không chạy cào")
    args = parser.parse_args()

    if args.export_only:
        src_file = INPUT_CSV_PATH if INPUT_CSV_PATH.exists() else FALLBACK_CSV_PATH
        if src_file.exists():
            df = pd.read_csv(src_file, encoding='utf-8-sig', dtype=str).fillna('')
            cnt = export_and_sync_all_files(df)
            print(f"[+] Xuất thành công! Doanh nghiệp có email: {cnt:,}")
        return

    asyncio.run(run_enrichment(limit=args.limit))


if __name__ == '__main__':
    main()
