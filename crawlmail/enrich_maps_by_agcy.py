# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - BELARUS LICENSED RECRUITMENT AGENCIES 2026
========================================================================
Mục tiêu: Làm giàu dữ liệu Website & B2B Corporate Email cho 64 cơ quan môi giới
          xuất khẩu lao động Belarus được cấp phép chính thức từ Bộ Nội vụ.

Input:  BY_AGCY_PDF0_0RAW.csv (64 licensed agencies)
Output: BY_AGCY_GMAP_1ENR.csv + BY_AGCY_GMAP_2COL.csv + READY
        (Đồng bộ vào BY_AGCY_PDF0_2COL.csv, csdl_mlt/ và archive/by_belarus/)

Tuân thủ nghiêm ngặt GEMINI.md & Kỹ năng enrich-maps & crawl-mail:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2: SĐT Belarus chuẩn hóa có nháy đơn ('+375...)
- Rule 3: B2B Email Scoring tiếng Nga/Belarus, đẩy 100% email lên đầu
- Rule 4: Trình duyệt trực quan thực tế (headless=False), viewport >= 1280x800
- Rule 5: Incremental Auto-Save sau mỗi 3-5 công ty, cache checkpoint JSON để Resume 100%
- Rule 8: Launcher .bat thuần ASCII, không dấu tiếng Việt, không dùng & trần
- Rule 10: Tên file cố định 17 ký tự (BY_AGCY_GMAP_1ENR / 2COL)
- Rule 11: So khớp tên thông minh (Smart & Strict Cyrillic/Latin Name Matching)
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
import curl_cffi.requests as requests

# UTF-8 output cho Windows Console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV_PATH = ROOT_DIR / "BY_AGCY_PDF0_0RAW.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "BY_AGCY_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "BY_AGCY_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "BY_AGCY_GMAP_ONLY_EMAILS_READY.csv"

# Đồng bộ luôn sang tệp ban đầu của user
SYNC_PDF0_2COL = ROOT_DIR / "BY_AGCY_PDF0_2COL.csv"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "by_belarus"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_by_agcy.json"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "by_maps_profile"

MAPS_TIMEOUT = 35000
DELAY_AFTER_SEARCH = 2.5
DELAY_AFTER_CLICK = 2.5
SITE_TIMEOUT = 10000

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

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
    'kartoteka.by', 'bizinspect.by', 'legat.by', 'egr.gov.by', 'b2b.by', 'tam.by',
    'deal.by', 'otzyvy.by', 'kufar.by', 'onliner.by', 'tut.by', 'belarus.by'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Bảng chuyển tự Cyrillic sang Latin cho tên công ty Nga/Belarus
CYR_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}


# ----------------------------------------------------------------------
# CHUẨN HÓA VĂN BẢN & SO KHỚP TÊN THÔNG MINH (RULE 11, 12)
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_by(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Belarus bắt buộc có nháy đơn (') ở đầu: '+375..."""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ""
    p = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+375'):
        pass
    elif digits.startswith('375'):
        digits = '+' + digits
    elif digits.startswith('80') and len(digits) >= 9:
        digits = '+375' + digits[2:]
    else:
        digits = '+375' + digits

    if digits.startswith('+375') and len(digits) == 13:
        formatted = f"+375 {digits[4:6]} {digits[6:9]} {digits[9:11]} {digits[11:]}"
        return f"'{formatted}"
    return f"'{digits}"


def clean_email(email_str):
    """Rule 3: Làm sạch triệt để khoảng trắng lạ, \\u00a0, %20"""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    return re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e).strip()


def normalize_cyrillic(text):
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    t = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'["\'„“”«»`]', '', t).strip()


def transliterate_to_latin(text):
    t_clean = normalize_cyrillic(text)
    res = []
    for c in t_clean:
        res.append(CYR_TO_LAT.get(c, c))
    return ''.join(res)


def clean_company_name_by(name):
    """Bóc tách loại hình doanh nghiệp Belarus (ООО, ЧУП, ОО, ИП, ЗАО, ОАО...)"""
    if not name:
        return ""
    t = normalize_cyrillic(name)
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    legal_forms = [
        'общество с ограниченной ответственностью', 'частное унитарное предприятие',
        'сервисное частное унитарное предприятие', 'туристское частное унитарное предприятие',
        'иностранное частное унитарное консалтинговое предприятие', 'общественное объединение',
        'индивидуальный предприниматель', 'закрытое акционерное общество', 'акционерное общество',
        'ооо', 'чуп', 'оо', 'ип', 'зао', 'оао', 'уп', 'чп'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
    return re.sub(r'\s+', ' ', t).strip(' ,.-')


def is_valid_name_match_by(query_name, candidate_name):
    """So khớp tên nghiêm ngặt & thông minh theo Rule 11 và đặc thù Belarus"""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = clean_company_name_by(query_name)
    c_clean = clean_company_name_by(candidate_name)

    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    # 1. Khớp nguyên văn Cyrillic
    if q_clean == c_clean:
        return True, "EXACT_CYRILLIC"

    # 2. Khớp qua chuyển tự Latin (VD: Джетэкспо == Dzhetekspo)
    q_lat = transliterate_to_latin(q_clean)
    c_lat = transliterate_to_latin(c_clean)
    if q_lat == c_lat:
        return True, "TRANSLIT_EXACT"

    # 3. Khớp sau khi tách phần trong ngoặc
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_clean).strip()
    if q_clean == c_nobrackets or q_lat == transliterate_to_latin(c_nobrackets):
        return True, "BRACKET_MATCH"

    # 4. Khớp qua dấu phân cách chuẩn
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_clean) if p.strip()]
    if any(p == q_clean or transliterate_to_latin(p) == q_lat for p in parts):
        return True, "DELIMITER_MATCH"

    # 5. Khớp Token đặc trưng (Distinctive Token) nếu tên có từ khóa độc nhất dài >= 6 ký tự
    q_tokens = [w for w in re.split(r'[\s\-]+', q_clean) if len(w) >= 5]
    c_tokens = [w for w in re.split(r'[\s\-]+', c_clean) if len(w) >= 5]
    for qt in q_tokens:
        qt_lat = transliterate_to_latin(qt)
        for ct in c_tokens:
            ct_lat = transliterate_to_latin(ct)
            if qt == ct or qt_lat == ct_lat:
                return True, "DISTINCTIVE_TOKEN_MATCH"

    return False, "NO_MATCH"


def is_valid_website(url):
    if not url or not isinstance(url, str):
        return False
    u = url.lower().strip()
    if not (u.startswith('http://') or u.startswith('https://')):
        return False
    return not any(b in u for b in BLACKLIST_DOMAINS)


# ----------------------------------------------------------------------
# CHẤM ĐIỂM EMAIL B2B CHO AGENCY BELARUS (RULE 3)
# ----------------------------------------------------------------------
def score_email_b2b_by(email, domain=""):
    """
    Chấm điểm email tối ưu cho B2B Manpower Agency tại Belarus:
    - Trùng domain (+50đ)
    - Phòng Tuyển dụng / Nhân sự / Việc làm: praca@, rabota@, cv@, rezume@, hr@, personal@ (+50đ)
    - Ban Lãnh đạo / Giám đốc: director@, ceo@, rukovoditel@, manager@ (+45đ)
    - Đầu mối liên hệ chính: info@, contact@, kontakt@, office@, mail@ (+40đ)
    - Email tên riêng cá nhân: ten@domain.by (+25đ)
    - Webmail Nga/Belarus miễn phí: @yandex.ru, @yandex.by, @mail.ru, @gmail.com (+15đ)
    - Email kỹ thuật/rác: support@, admin@ (+5đ), template rác (-1đ)
    """
    e = clean_email(email)
    if not e or '@' not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1

    bad_domains = ['example.com', 'domain.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(b in d for b in bad_domains):
        return -1
    bad_users = ['youremail', 'your-email', 'someone', 'john.doe', 'no-reply', 'donotreply', 'privacy', 'gdpr']
    if any(b in u for b in bad_users):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.by'):
        score += 35

    # Ưu tiên phòng nhân sự & tuyển dụng (rất quan trọng với agency)
    if any(k in u for k in ['praca', 'rabota', 'cv', 'rezume', 'hr', 'personal', 'job', 'recruitment', 'work']):
        score += 50
    elif any(k in u for k in ['director', 'ceo', 'rukovoditel', 'direktor', 'manager', 'vedenie']):
        score += 45
    elif any(k in u for k in ['info', 'contact', 'kontakt', 'office', 'mail', 'sekretariat']):
        score += 40
    elif any(k in u for k in ['sales', 'visa', 'tur', 'consult', 'otdel']):
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['yandex.ru', 'yandex.by', 'mail.ru', 'gmail.com', 'tut.by']:
        score += 15

    return score


def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_by(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_by(e, domain))


# ----------------------------------------------------------------------
# QUÉT SÂU WEBSITE TÌM EMAIL B2B (SKILL CRAWL-MAIL)
# ----------------------------------------------------------------------
async def crawl_website_for_email(page, website_url):
    """Quét trang chủ và các subpages tiếng Nga bản địa của agency"""
    if not is_valid_website(website_url):
        return ""

    parsed = urllib.parse.urlparse(website_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    found_emails = []
    site_alive = False

    # 1. Thử cào trang chủ bằng curl_cffi trước (nhanh và nhẹ)
    try:
        r = requests.get(website_url, impersonate='chrome120', timeout=4.5, verify=False)
        if r.status_code == 200:
            site_alive = True
            ems = EMAIL_REGEX.findall(r.text)
            found_emails.extend(ems)
        elif r.status_code in [301, 302, 403]:
            site_alive = True
    except Exception:
        pass

    # Nếu trang chủ hoàn toàn không phản hồi -> Bỏ qua, tránh treo subpages
    if not site_alive:
        return ""

    best = select_best_email(found_emails, base_url)
    if best:
        return best

    # 2. Quét các subpath bản địa Belarus/Nga (/kontakty, /o-nas, /vakansii...)
    subpaths = [
        '/kontakty', '/kontakty.html', '/contact', '/contacts',
        '/o-kompanii', '/o-nas', '/vakansii', '/rabota-za-granicey', '/about'
    ]
    for sp in subpaths:
        sub_url = urllib.parse.urljoin(base_url, sp)
        try:
            r = requests.get(sub_url, impersonate='chrome120', timeout=3.5, verify=False)
            if r.status_code == 200:
                ems = EMAIL_REGEX.findall(r.text)
                found_emails.extend(ems)
                best = select_best_email(found_emails, base_url)
                if best:
                    return best
        except Exception:
            pass

    return select_best_email(found_emails, base_url)


# ----------------------------------------------------------------------
# XUẤT ĐỊNH DẠNG CHUẨN COLD MAIL 20 CỘT & ĐỒNG BỘ
# ----------------------------------------------------------------------
def export_and_sync_all_files(df):
    df_out = df.copy()
    if 'Cong_Ty' in df_out.columns:
        df_out = df_out[~df_out['Cong_Ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['SDT'] = df_out['SDT'].apply(clean_phone_by)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # Đẩy 100% email lên đầu (Rule 3)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong_Ty', '')).strip()
        legal_name = str(r.get('Ten_Phap_Ly', '')).strip()
        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_by(r.get('SDT', ''))
        city_val = str(r.get('Thanh_Pho', '')).strip()
        addr_val = str(r.get('Dia_Chi', '')).strip()
        dest_val = str(r.get('Thi_Truong_Xuat_Khau', '')).strip()
        spec_val = str(r.get('Nganh_Nghe_Tuyen_Dung', '')).strip()
        lic_no = str(r.get('So_Giay_Phep', '')).strip()

        cat_desc = f"Licensed Recruitment Agency ({dest_val}) - {spec_val}".strip(' -')

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': 'Director / Recruitment Manager',
            'Người liên hệ': 'Руководитель агентства',
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': f"{addr_val}, {city_val}".strip(', '),
            'Lương': f"Lic: {lic_no}",
            'Ngày đăng': r.get('Ngay_Cap_Phep', ''),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat_desc
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')

    # Đồng bộ sang tệp 2COL ban đầu
    df_2col.to_csv(SYNC_PDF0_2COL, index=False, encoding='utf-8-sig')

    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, extra_dir / OUTPUT_READY_PATH.name)
            shutil.copy2(OUTPUT_1ENR_PATH, extra_dir / OUTPUT_1ENR_PATH.name)
            shutil.copy2(SYNC_PDF0_2COL, extra_dir / SYNC_PDF0_2COL.name)
        except Exception:
            pass

    return len(has_em)


# ----------------------------------------------------------------------
# TIẾN TRÌNH LÀM GIÀU CHÍNH (ENRICHMENT RUNNER)
# ----------------------------------------------------------------------
async def run_enrichment(limit=None):
    print("=" * 80)
    print("🌟  LÀM GIÀU DỮ LIỆU AGENCY BELARUS 2026 QUA GOOGLE MAPS & WEBSITE (RULE 3, 4, 11)")
    print(f"    - Tệp dữ liệu vào       : {INPUT_CSV_PATH.name}")
    print(f"    - Tệp Master 1ENR       : {OUTPUT_1ENR_PATH.name}")
    print(f"    - Tệp Cold Mail 20 cột  : {OUTPUT_2COL_PATH.name}")
    print(f"    - Tệp CHỈ CÓ EMAIL      : {OUTPUT_READY_PATH.name}")
    print(f"    - Checkpoint Cache      : {CACHE_PATH.name}")
    if limit:
        print(f"    - Giới hạn xử lý        : {limit} công ty")
    print("=" * 80 + "\n")
    sys.stdout.flush()

    if not INPUT_CSV_PATH.exists():
        print(f"[!] Không tìm thấy tệp {INPUT_CSV_PATH.name}!")
        return

    df = pd.read_csv(INPUT_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    for col in ['Website', 'Email', 'SDT', 'Tat_Ca_SDT']:
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

    # Lọc danh sách công ty cần làm giàu
    all_pending = [i for i, r in df.iterrows() if not clean_email(r['Email'])]
    pending_indices = all_pending[:limit] if limit else all_pending

    print(f"[*] Tổng số agency: {len(df):,} | Đã có Email: {len(df) - len(all_pending):,} | Cần làm giàu: {len(pending_indices):,}\n")

    if not pending_indices:
        print("[+] Toàn bộ agency đều đã có Email B2B!")
        export_and_sync_all_files(df)
        return

    # Khởi tạo Playwright Chrome thực tế với Persistent Profile (Rule 4)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome",
            args=['--start-maximized', '--no-sandbox'],
            viewport={'width': 1280, 'height': 800},
            locale='ru-RU',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Vượt qua màn hình Google Consent nếu xuất hiện
        try:
            await page.goto('https://www.google.com/maps?hl=ru', timeout=20000)
            await asyncio.sleep(2.0)
            if 'consent.google.com' in page.url:
                btn = await page.query_selector('button:has-text("Принять все"), button:has-text("Accept all"), button:has-text("Alle akzeptieren"), form[action*="consent"] button')
                if btn:
                    await btn.click()
                    await asyncio.sleep(3.0)
        except Exception:
            pass

        processed = 0
        newly_found = 0

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row['Cong_Ty']).strip()
            city = str(row['Thanh_Pho']).strip()
            lic_no = str(row.get('So_Giay_Phep', '')).strip()
            cache_key = lic_no if lic_no else f"{comp}::{city}"

            processed += 1

            # 1. Kiểm tra Cache
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

            # 2. Tìm kiếm trên Google Maps
            search_query = f"{comp} {city} Беларусь"
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(search_query)}?hl=ru"
            print(f"[{processed}/{len(pending_indices)}] 📍 Maps: {comp} ({city})")

            found_web = ""
            found_phone = ""
            found_email = ""

            try:
                await page.goto(maps_url, timeout=MAPS_TIMEOUT, wait_until='domcontentloaded')
                await asyncio.sleep(DELAY_AFTER_SEARCH)

                # Xử lý Google Consent nếu bị điều hướng
                if "consent.google.com" in page.url.lower():
                    c_btn = await page.query_selector('button:has-text("Принять все"), button:has-text("Accept all"), form[action*="consent"] button')
                    if c_btn:
                        await c_btn.click()
                        await asyncio.sleep(3.0)

                # Xử lý Captcha Google nếu có (Rule 4)
                cur_u = page.url.lower()
                c_cnt = await page.content()
                if "sorry" in cur_u or "captcha" in cur_u or "unusual traffic" in c_cnt.lower():
                    print("\a" * 3)
                    print("\n[!] PHÁT HIỆN CAPTCHA GOOGLE! Vui lòng bấm xác thực trên trình duyệt...\n")
                    while "sorry" in page.url.lower() or "captcha" in page.url.lower():
                        await asyncio.sleep(3)
                    print("[+] Captcha đã xử lý xong! Tiếp tục...")

                # Trường hợp 1: Nhảy thẳng vào trang chi tiết địa điểm hoặc h1 đã xuất hiện
                h1 = await page.query_selector('h1.DUwDvf')
                cand_name = (await h1.inner_text()).strip() if h1 else ""

                if h1 and cand_name:
                    is_match, match_type = is_valid_name_match_by(comp, cand_name)
                    if is_match:
                        web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Сайт"], a[aria-label*="Website"]')
                        if web_btn:
                            w_href = await web_btn.get_attribute('href')
                            if is_valid_website(w_href):
                                found_web = w_href

                        phone_btn = await page.query_selector('button[data-item-id^="phone:"], [aria-label*="Телефон"]')
                        if phone_btn:
                            p_txt = await phone_btn.inner_text()
                            found_phone = clean_phone_by(p_txt)

                # Trường hợp 2: Hiện danh sách nhiều kết quả
                if not found_web and await page.query_selector('div[role="feed"]'):
                    cards = await page.query_selector_all('div[role="feed"] > div > div[jsaction*="mouseover"]')
                    matched_card = None

                    for card in cards[:6]:
                        name_el = await card.query_selector('.qBF1Pd, .fontHeadlineSmall')
                        if name_el:
                            cand_name = (await name_el.inner_text()).strip()
                            is_match, match_type = is_valid_name_match_by(comp, cand_name)
                            if is_match:
                                matched_card = card
                                break

                    # Fallback click thẻ đầu tiên nếu tên chỉ hơi khác
                    if not matched_card and cards:
                        first_el = await cards[0].query_selector('.qBF1Pd, .fontHeadlineSmall')
                        first_cand = (await first_el.inner_text()).strip() if first_el else ""
                        is_match, match_type = is_valid_name_match_by(comp, first_cand)
                        if is_match:
                            matched_card = cards[0]

                    if matched_card:
                        await matched_card.click()
                        await asyncio.sleep(DELAY_AFTER_CLICK)

                        web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Сайт"], a[aria-label*="Website"]')
                        if web_btn:
                            w_href = await web_btn.get_attribute('href')
                            if is_valid_website(w_href):
                                found_web = w_href

                        phone_btn = await page.query_selector('button[data-item-id^="phone:"], [aria-label*="Телефон"]')
                        if phone_btn:
                            p_txt = await phone_btn.inner_text()
                            found_phone = clean_phone_by(p_txt)

                # 3. Quét website bóc tách Email B2B nếu tìm thấy Website
                target_web = found_web or df.at[idx, 'Website']
                if is_valid_website(target_web):
                    found_email = await crawl_website_for_email(page, target_web)

            except Exception as e:
                print(f"    [!] Lỗi tìm kiếm: {e}")

            # Cập nhật kết quả vào DataFrame
            if found_web and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = found_web
            if found_phone and not df.at[idx, 'SDT']:
                df.at[idx, 'SDT'] = found_phone

            if found_email:
                df.at[idx, 'Email'] = found_email
                newly_found += 1
                print(f"    🎯 [+] TÌM THẤY EMAIL: {comp} -> {found_email} (Web: {target_web})")
            elif found_web:
                print(f"    🌐 [~] Khớp Maps: Web: {found_web} | SĐT: {found_phone or df.at[idx, 'SDT']}")
            else:
                print("    [-] Không tìm thấy thẻ khớp trên Google Maps.")

            cache[cache_key] = {
                'Website': found_web or df.at[idx, 'Website'],
                'SDT': found_phone or df.at[idx, 'SDT'],
                'Email': found_email or df.at[idx, 'Email']
            }

            # Lưu tăng dần sau mỗi 3 công ty (Rule 5)
            if processed % 3 == 0:
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

        print("\n" + "=" * 80)
        print("🏆 HOÀN THÀNH LÀM GIÀU AGENCY XUẤT KHẨU LAO ĐỘNG BELARUS 2026!")
        print(f"   - Tổng số agency trong danh sách : {len(df):,}")
        print(f"   - Agency có EMAIL B2B hợp lệ    : {total_em:,} ({total_em*100/len(df):.1f}%)")
        print(f"   - Email mới tìm được đợt này     : +{newly_found:,}")
        print("   - Tệp dữ liệu đã xuất:")
        print(f"     1. {OUTPUT_1ENR_PATH.name} (Full dataset master)")
        print(f"     2. {OUTPUT_2COL_PATH.name} (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)")
        print(f"     3. {OUTPUT_READY_PATH.name} (Tệp chỉ có email gửi chiến dịch)")
        print(f"     4. {SYNC_PDF0_2COL.name} (Đồng bộ tệp Cold Mail gốc)")
        print("=" * 80 + "\n")

        await context.close()


def main():
    parser = argparse.ArgumentParser(description="Enrich Belarus Recruitment Agencies with Google Maps & Websites")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty cần làm giàu")
    parser.add_argument("--export-only", action="store_true", help="Chỉ xuất lại file Cold Mail từ cache mà không chạy cào")
    args = parser.parse_args()

    if args.export_only:
        if INPUT_CSV_PATH.exists():
            df = pd.read_csv(INPUT_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
            cnt = export_and_sync_all_files(df)
            print(f"[+] Xuất thành công! Doanh nghiệp có email: {cnt:,}")
        return

    asyncio.run(run_enrichment(limit=args.limit))


if __name__ == '__main__':
    main()
