# -*- coding: utf-8 -*-
"""
DATA ENRICHMENT - LITHUANIAN TEXTILE & APPAREL ENTERPRISES VIA INFO.LT
======================================================================
Input:  LT_TEXT_LTOR_0RAW.csv (1,429 công ty dệt may Litva)
Output:
  - LT_TEXT_INLT_1ENR.csv (File làm giàu toàn bộ thông tin)
  - LT_TEXT_INLT_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
  - LT_TEXT_INLT_ONLY_EMAILS_READY.csv (Chỉ gồm các công ty có Email sẵn sàng gửi)
  - cache_enrich_infolt_lt_text.json (Checkpoint cache để Resume 100%)

Kế thừa kiến trúc chuẩn tốc độ cao từ bộ Gỗ (enrich_infolt_lt_wood.py) và Kim loại:
1. Cơ chế Pre-Validated Rotating Proxy Pool tốc độ cao:
   - Tự động lấy danh sách Proxy Elite phản hồi nhanh.
   - Tiền kiểm định trực tiếp trên info.lt (timeout 3.5s).
   - Vượt rào hoàn toàn lỗi HTTP 429 (Too Many Requests), KHÔNG BAO GIỜ BỊ ĐƠ LAG.
2. Tra cứu chính xác 100% theo Mã số doanh nghiệp (FirmCode = Company_Code 7-9 chữ số).
3. Giải mã thuật toán Base64 + XOR Obfuscation (data-text-ob & data-link-ob) lấy email B2B.
4. Bóc tách SĐT có nháy đơn ('+370...), Người đại diện (Vadovas/Direktorius), Website, Địa chỉ.
5. Fallback website nhanh (timeout 4.0s) để tránh treo mạng khi gặp website chết.
6. Checkpoint tự động sau mỗi 10 công ty (Rule 5) để Resume 100% không mất dữ liệu.
7. Tuân thủ toàn bộ quy chuẩn Rule 1, 2, 3, 5, 8, 10, 11, 12 trong GEMINI.md.
"""

import sys
import os
import re
import ssl
import json
import time
import random
import shutil
import base64
import argparse
import threading
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from bs4 import BeautifulSoup
import curl_cffi.requests as requests

# UTF-8 output cho Windows Console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV_PATH = ROOT_DIR / "LT_TEXT_LTOR_0RAW.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_TEXT_INLT_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_TEXT_INLT_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_TEXT_INLT_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_infolt_lt_text.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')


# ----------------------------------------------------------------------
# PRE-VALIDATED PROXY POOL CHO CỔNG INFO.LT (VƯỢT LỖI HTTP 429)
# ----------------------------------------------------------------------
class PreValidatedProxyPool:
    """Quản lý danh sách proxy ĐÃ ĐƯỢC KIỂM ĐỊNH thành công trên info.lt"""
    def __init__(self):
        self.live_proxies = []
        self.lock = threading.Lock()
        self.is_refreshing = False

    def validate_one(self, p):
        try:
            r = requests.get(
                'https://www.info.lt',
                proxies={'http': f'http://{p}', 'https': f'http://{p}'},
                impersonate='chrome120',
                timeout=3.5
            )
            if r.status_code == 200 and len(r.text) > 1000:
                return p
        except Exception:
            pass
        return None

    def refresh(self):
        with self.lock:
            if self.is_refreshing:
                return
            self.is_refreshing = True

        try:
            candidates = []
            # Nguồn 1: ProxyScrape HTTP SSL Elite
            try:
                url = 'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3500&country=all&ssl=yes&anonymity=elite'
                r = requests.get(url, timeout=5)
                raw = [l.strip() for l in r.text.splitlines() if l.strip()]
                candidates.extend(raw[:60])
            except Exception:
                pass

            # Nguồn 2: ProxyScrape All
            if len(candidates) < 30:
                try:
                    url2 = 'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all'
                    r2 = requests.get(url2, timeout=5)
                    raw2 = [l.strip() for l in r2.text.splitlines() if l.strip()]
                    candidates.extend(raw2[:40])
                except Exception:
                    pass

            candidates = list(dict.fromkeys(candidates))[:80]
            if candidates:
                print(f"[*] Đang kiểm định {len(candidates)} proxy phản hồi nhanh trên info.lt...")
                valid = []
                with ThreadPoolExecutor(max_workers=25) as ex:
                    for res in ex.map(self.validate_one, candidates):
                        if res:
                            valid.append(res)

                with self.lock:
                    combined = list(dict.fromkeys(self.live_proxies + valid))
                    self.live_proxies = combined
                print(f"[*] Đã xác thực thành công {len(valid)} proxy live mới (Tổng khả dụng: {len(self.live_proxies)}) trên info.lt!")
        except Exception as e:
            print(f"[!] Lỗi nạp proxy: {e}")
        finally:
            with self.lock:
                self.is_refreshing = False

    def get_proxy(self):
        with self.lock:
            if len(self.live_proxies) < 3 and not self.is_refreshing:
                threading.Thread(target=self.refresh, daemon=True).start()
            if self.live_proxies:
                return random.choice(self.live_proxies)
        for _ in range(6):
            time.sleep(0.5)
            with self.lock:
                if self.live_proxies:
                    return random.choice(self.live_proxies)
        return None

    def remove_proxy(self, p):
        with self.lock:
            if p in self.live_proxies:
                self.live_proxies.remove(p)


PROXY_POOL = PreValidatedProxyPool()


# ----------------------------------------------------------------------
# CHUẨN HÓA VĂN BẢN & SO KHỚP TÊN (RULE 2, 3, 11, 12)
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_lt(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Litva có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('370'):
        pass
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370') and len(digits) == 11:
        formatted = f"+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        return f"'{formatted}"
    return f"'+{digits}"

def clean_email(email_str):
    """Rule 3: Làm sạch email, cắt bỏ %20, \\xa0, khoảng trắng thừa"""
    if not email_str or not isinstance(email_str, str):
        return ""
    em = urllib.parse.unquote(str(email_str).strip().lower())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        em = em.replace(bad, '')
    if em.startswith('20') and '@' in em and not em.startswith('202'):
        em = em[2:]
    em = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', em)
    return em.strip()

def decode_info_lt_ob(encoded_str):
    """Giải mã chuỗi Base64 + XOR Obfuscation của info.lt"""
    if not encoded_str:
        return ""
    try:
        raw = base64.b64decode(encoded_str).decode('utf-8').split(',')
        key = int(raw[0])
        decoded = ''.join(chr(int(x) ^ key) for x in raw[1:])
        return clean_email(decoded.replace('mailto:', ''))
    except Exception:
        return ""

def score_email_b2b_lt(email, domain=""):
    """Rule 3: Chấm điểm email B2B cho thị trường Dệt may Litva"""
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
    elif d.endswith('.lt'):
        score += 35

    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'gamyba']:
        score += 45
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
    elif u in ['komercija', 'pardavimai', 'uzsakymai', 'sales', 'prekyba', 'tekstile', 'siuvimas']:
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'inbox.lt', 'one.lt']:
        score += 10
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


# ----------------------------------------------------------------------
# FETCH HTTP QUA ROTATING PROXY CHỐNG 429
# ----------------------------------------------------------------------
def fetch_infolt_html(url, max_retries=4):
    """Tải HTML từ info.lt qua Rotating Proxy Pool chống 429 triệt để"""
    for _ in range(max_retries):
        p = PROXY_POOL.get_proxy()
        proxies = {'http': f'http://{p}', 'https': f'http://{p}'} if p else None
        try:
            r = requests.get(url, proxies=proxies, impersonate='chrome120', timeout=6.0)
            if r.status_code == 200 and len(r.text) > 800:
                return r.text
            elif r.status_code in [403, 429] and p:
                PROXY_POOL.remove_proxy(p)
        except Exception:
            if p:
                PROXY_POOL.remove_proxy(p)

    # Thử gọi trực tiếp nếu proxy chưa hồi đáp
    try:
        r = requests.get(url, impersonate='chrome120', timeout=5.0)
        if r.status_code == 200 and len(r.text) > 800:
            return r.text
    except Exception:
        pass

    return None


# ----------------------------------------------------------------------
# TRA CỨU & BÓC TÁCH CHI TIẾT DOANH NGHIỆP TRÊN INFO.LT
# ----------------------------------------------------------------------
def search_and_enrich_from_infolt(comp_code, comp_name):
    """
    1. Tra cứu theo Mã số doanh nghiệp (FirmCode = Company_Code)
    2. Fallback tra theo tên doanh nghiệp nếu mã số không khớp
    3. Mở trang chi tiết, giải mã Base64 + XOR lấy email
    4. Bóc tách SĐT, Website, Người quản lý, Địa chỉ
    5. Fallback quét website (timeout ngắn 3.5s)
    """
    detail_url = None

    # 1. Tra cứu theo mã số doanh nghiệp (chính xác 100%)
    clean_code = re.sub(r'\D', '', str(comp_code).strip()) if comp_code else ""
    if clean_code and len(clean_code) in [7, 8, 9]:
        search_url = f"https://www.info.lt/en?action=ieskoti&page=imones&view=detali&FirmCode={clean_code}"
        html = fetch_infolt_html(search_url)
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for h2 in soup.find_all('h2', class_='pavadinimas_paprastas'):
                a = h2.find('a', href=True)
                if a:
                    detail_url = a['href']
                    break

    # 2. Fallback tra cứu theo tên doanh nghiệp
    if not detail_url and comp_name:
        clean_q = re.sub(r'\([^\)]*\)|\[[^\]]*\]', '', comp_name).strip()
        clean_q = re.sub(r'\b(UAB|MB|AB|IĮ|VšĮ|TŪB)\b', '', clean_q, flags=re.I).strip(' ,-"\'')
        if clean_q:
            search_url = f"https://www.info.lt/en?action=ieskoti&page=imones&view=greita&q={urllib.parse.quote_plus(clean_q)}"
            html = fetch_infolt_html(search_url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for h2 in soup.find_all('h2', class_='pavadinimas_paprastas'):
                    a = h2.find('a', href=True)
                    if a:
                        detail_url = a['href']
                        break

    if not detail_url:
        return None

    det_html = fetch_infolt_html(detail_url)
    if not det_html:
        return None

    soup = BeautifulSoup(det_html, 'html.parser')

    found_emails = []
    found_phones = []
    found_website = ""
    manager_name = ""
    manager_title = "Vadovas"
    full_address = ""

    # Giải mã email XOR từ data-text-ob
    for tag in soup.find_all(attrs={'data-text-ob': True}):
        dec = decode_info_lt_ob(tag['data-text-ob'])
        if dec and '@' in dec:
            found_emails.append(dec)

    # Giải mã email XOR từ data-link-ob
    for tag in soup.find_all(attrs={'data-link-ob': True}):
        dec = decode_info_lt_ob(tag['data-link-ob'])
        if dec and '@' in dec:
            found_emails.append(dec)

    for row in soup.find_all('div', class_='row'):
        c4 = row.find('div', class_='col-xs-4')
        c8 = row.find('div', class_='col-xs-8')
        if not c4 or not c8:
            continue
        label = c4.text.strip().lower()
        val = ' '.join(c8.stripped_strings)

        if 'website' in label or 'tinklapis' in label or 'tinklalapis' in label:
            a_tag = c8.find('a', href=True)
            if a_tag and a_tag['href'].startswith('http'):
                found_website = a_tag['href'].strip()
            elif val and not val.lower().startswith('www.facebook'):
                found_website = val if val.startswith('http') else f"https://{val}"
        elif 'phone' in label or 'telefonas' in label:
            m_ph = re.search(r'(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|\(0\s*\d+\)\s*\d+[\d\s]*|8\s*\d+[\d\s]*)', val)
            if m_ph:
                found_phones.append(clean_phone_lt(m_ph.group(1).strip()))
        elif any(k in label for k in ['direktor', 'vadov', 'manager', 'prezident', 'savinink']):
            manager_title = c4.text.strip()
            manager_name = val

    for kt in soup.select('span.kont_tel, [itemprop="telephone"]'):
        p_txt = kt.get_text(strip=True)
        if p_txt:
            found_phones.append(clean_phone_lt(p_txt))

    addr_elem = soup.find(attrs={'itemprop': 'address'})
    if addr_elem:
        full_address = addr_elem.get_text(' ', strip=True)
    if not full_address:
        h1 = soup.find('h1')
        if h1 and h1.find_next_sibling():
            full_address = h1.find_next_sibling().get_text(' ', strip=True).splitlines()[0].strip()

    best_phone = found_phones[0] if found_phones else ""
    best_email = select_best_email(found_emails, found_website)

    # Fallback quét website nếu info.lt chưa có mail (timeout ngắn 3.5s)
    if not best_email and found_website:
        try:
            w_resp = requests.get(found_website, impersonate='chrome120', timeout=3.5, verify=False)
            if w_resp.status_code == 200:
                site_emails = EMAIL_REGEX.findall(w_resp.text)
                best_email = select_best_email(site_emails, found_website)
        except Exception:
            pass

    return {
        'Email': best_email,
        'SDT': best_phone,
        'Website': found_website,
        'Nguoi_Quan_Ly': manager_name,
        'Chuc_Danh': manager_title,
        'Dia_Chi': full_address,
        'InfoLT_URL': detail_url
    }


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
        manager = str(r.get('Nguoi_Quan_Ly', '')).strip()
        title = str(r.get('Chuc_Danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('City', '')).strip()
        addr_val = str(r.get('Dia_Chi', r.get('Dia chi', ''))).strip()
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"

        cat_val = str(r.get('Category', '')).strip()

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val if web_val else r.get('Detail_URL', ''),
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': addr_val,
            'Lương': r.get('Doanh_Thu', ''),
            'Ngày đăng': r.get('Nam_Thanh_Lap', ''),
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

    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready['No.'] = range(1, len(df_ready) + 1)
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
# TIẾN TRÌNH LÀM GIÀU CHÍNH (ENRICHMENT RUNNER)
# ----------------------------------------------------------------------
def run_enrichment(limit=None):
    print("=" * 80)
    print("🌟 LÀM GIÀU DỮ LIỆU CÔNG TY DỆT MAY LITVA QUA CỔNG INFO.LT (RULE 3 & 11)")
    print(f"    - Tệp dữ liệu vào       : {INPUT_CSV_PATH.name}")
    print(f"    - Tệp Master 1ENR       : {OUTPUT_1ENR_PATH.name}")
    print(f"    - Tệp Cold Mail 2COL    : {OUTPUT_2COL_PATH.name}")
    print(f"    - Tệp CHỈ CÓ EMAIL      : {OUTPUT_READY_PATH.name}")
    print(f"    - Checkpoint Cache      : {CACHE_FILE.name}")
    if limit:
        print(f"    - Giới hạn xử lý        : {limit} công ty")
    print("=" * 80 + "\n")
    sys.stdout.flush()

    if not INPUT_CSV_PATH.exists():
        print(f"[!] Không tìm thấy tệp {INPUT_CSV_PATH.name}!")
        return

    df = pd.read_csv(INPUT_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    for col in ['Website', 'Email', 'SDT', 'Nguoi_Quan_Ly', 'Chuc_Danh', 'Dia_Chi']:
        if col not in df.columns:
            df[col] = ''

    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp {len(cache):,} bản ghi từ checkpoint cache.")
        except Exception:
            pass

    # Populate existing cache into df
    cached_emails = 0
    for idx, row in df.iterrows():
        comp = str(row['Cong ty']).strip()
        code = str(row.get('Company_Code', '')).strip()
        cache_key = code if code else comp
        if cache_key in cache:
            c = cache[cache_key]
            if c.get('Email'):
                df.at[idx, 'Email'] = c['Email']
                cached_emails += 1
            if c.get('Website') and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = c['Website']
            if c.get('SDT') and not df.at[idx, 'SDT']:
                df.at[idx, 'SDT'] = c['SDT']
            if c.get('Nguoi_Quan_Ly') and not df.at[idx, 'Nguoi_Quan_Ly']:
                df.at[idx, 'Nguoi_Quan_Ly'] = c['Nguoi_Quan_Ly']
            if c.get('Chuc_Danh') and not df.at[idx, 'Chuc_Danh']:
                df.at[idx, 'Chuc_Danh'] = c['Chuc_Danh']
            if c.get('Dia_Chi') and not df.at[idx, 'Dia_Chi']:
                df.at[idx, 'Dia_Chi'] = c['Dia_Chi']

    # Lọc danh sách công ty cần tra cứu (chưa có Email)
    all_pending = [i for i, r in df.iterrows() if not clean_email(r['Email'])]
    pending_indices = all_pending[:limit] if limit else all_pending

    print(f"[*] Tổng số công ty: {len(df):,} | Đã có Email B2B (từ cache): {cached_emails:,} | Cần tra cứu info.lt: {len(pending_indices):,}\n")
    sys.stdout.flush()

    if not pending_indices:
        print("[+] Toàn bộ công ty đều đã được xử lý xong!")
        export_and_sync_all_files(df)
        return

    # Khởi tạo Proxy Pool chống lỗi 429
    PROXY_POOL.refresh()

    processed = 0
    newly_found = 0

    for idx in pending_indices:
        row = df.loc[idx]
        comp = str(row['Cong ty']).strip()
        code = str(row.get('Company_Code', '')).strip()
        city = str(row.get('City', '')).strip()
        cache_key = code if code else comp

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
            if c.get('Nguoi_Quan_Ly') and not df.at[idx, 'Nguoi_Quan_Ly']:
                df.at[idx, 'Nguoi_Quan_Ly'] = c['Nguoi_Quan_Ly']
            if c.get('Dia_Chi') and not df.at[idx, 'Dia_Chi']:
                df.at[idx, 'Dia_Chi'] = c['Dia_Chi']
            if c.get('Email'):
                print(f"[{processed}/{len(pending_indices)}] [CACHE] {comp} (Mã: {code}) -> {c['Email']}")
                continue

        # 2. Tra cứu info.lt qua Rotating Proxy
        print(f"[{processed}/{len(pending_indices)}] 🔍 info.lt: {comp} (Mã DN: {code} | {city})")
        res = search_and_enrich_from_infolt(code, comp)

        if res:
            if res.get('Website') and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = res['Website']
            if res.get('SDT') and not df.at[idx, 'SDT']:
                df.at[idx, 'SDT'] = res['SDT']
            if res.get('Nguoi_Quan_Ly') and not df.at[idx, 'Nguoi_Quan_Ly']:
                df.at[idx, 'Nguoi_Quan_Ly'] = res['Nguoi_Quan_Ly']
            if res.get('Chuc_Danh') and not df.at[idx, 'Chuc_Danh']:
                df.at[idx, 'Chuc_Danh'] = res['Chuc_Danh']
            if res.get('Dia_Chi') and not df.at[idx, 'Dia_Chi']:
                df.at[idx, 'Dia_Chi'] = res['Dia_Chi']

            if res.get('Email'):
                df.at[idx, 'Email'] = res['Email']
                newly_found += 1
                print(f"    🎯 [+] TÌM THẤY EMAIL: {comp} -> {res['Email']} (Web: {res.get('Website', '')})")
            elif res.get('Website'):
                print(f"    🌐 [~] Có Website & SĐT: {comp} -> Web: {res['Website']} | SĐT: {res.get('SDT', '')}")
            else:
                print(f"    [-] Tìm thấy thẻ trên info.lt nhưng không có email công khai.")

            cache[cache_key] = {
                'Email': res.get('Email', ''),
                'SDT': res.get('SDT', df.at[idx, 'SDT']),
                'Website': res.get('Website', df.at[idx, 'Website']),
                'Nguoi_Quan_Ly': res.get('Nguoi_Quan_Ly', df.at[idx, 'Nguoi_Quan_Ly']),
                'Chuc_Danh': res.get('Chuc_Danh', df.at[idx, 'Chuc_Danh']),
                'Dia_Chi': res.get('Dia_Chi', df.at[idx, 'Dia_Chi'])
            }
        else:
            print(f"    [-] Không tìm thấy thông tin trên info.lt.")
            cache[cache_key] = {
                'Email': '',
                'SDT': df.at[idx, 'SDT'],
                'Website': df.at[idx, 'Website'],
                'Nguoi_Quan_Ly': df.at[idx, 'Nguoi_Quan_Ly'],
                'Chuc_Danh': df.at[idx, 'Chuc_Danh'],
                'Dia_Chi': df.at[idx, 'Dia_Chi']
            }

        # Lưu checkpoint mỗi 10 công ty (Rule 5)
        if processed % 10 == 0:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cur_em = export_and_sync_all_files(df)
            print(f"    [*] Đã lưu Checkpoint ({processed}/{len(pending_indices)} | Tổng Email: {cur_em:,} | +{newly_found} mới)")

        time.sleep(0.3)

    # Lưu lần cuối
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total_valid_emails = export_and_sync_all_files(df)

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH TIẾN TRÌNH LÀM GIÀU EMAIL QUA CỔNG INFO.LT (DỆT MAY LITVA)!")
    print(f"   - Tổng số doanh nghiệp trong danh sách : {len(df):,}")
    print(f"   - Doanh nghiệp có EMAIL hợp lệ        : {total_valid_emails:,} ({total_valid_emails*100/len(df):.1f}%)")
    print(f"   - Email mới tìm được đợt này          : +{newly_found:,}")
    print("   - Tệp dữ liệu đã xuất:")
    print(f"     1. {OUTPUT_1ENR_PATH.name} (Full dataset master)")
    print(f"     2. {OUTPUT_2COL_PATH.name} (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)")
    print(f"     3. {OUTPUT_READY_PATH.name} (Tệp chỉ có email gửi chiến dịch)")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Enrich Lithuanian Textile Enterprises via info.lt")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số công ty cần xử lý")
    parser.add_argument("--re-export", action="store_true", help="Chỉ xuất lại file Cold Mail từ Cache mà không cào")
    args = parser.parse_args()

    if args.re_export:
        if INPUT_CSV_PATH.exists():
            df = pd.read_csv(INPUT_CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
            for col in ['Website', 'Email', 'SDT', 'Nguoi_Quan_Ly', 'Chuc_Danh', 'Dia_Chi']:
                if col not in df.columns:
                    df[col] = ''
            if CACHE_FILE.exists():
                try:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                    for idx, row in df.iterrows():
                        code = str(row.get('Company_Code', '')).strip()
                        comp = str(row['Cong ty']).strip()
                        key = code if code else comp
                        if key in cache:
                            c = cache[key]
                            if c.get('Email'): df.at[idx, 'Email'] = c['Email']
                            if c.get('Website'): df.at[idx, 'Website'] = c['Website']
                            if c.get('SDT'): df.at[idx, 'SDT'] = c['SDT']
                            if c.get('Nguoi_Quan_Ly'): df.at[idx, 'Nguoi_Quan_Ly'] = c['Nguoi_Quan_Ly']
                            if c.get('Chuc_Danh'): df.at[idx, 'Chuc_Danh'] = c['Chuc_Danh']
                            if c.get('Dia_Chi'): df.at[idx, 'Dia_Chi'] = c['Dia_Chi']
                except Exception:
                    pass
            cnt = export_and_sync_all_files(df)
            print(f"[+] Xuất thành công! Doanh nghiệp có email: {cnt:,}")
        return

    run_enrichment(limit=args.limit)


if __name__ == '__main__':
    main()
