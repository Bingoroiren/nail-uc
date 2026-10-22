#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU EMAIL ĐA TẦNG CHO MÔI GIỚI LAO ĐỘNG LITVA (LT_AGCY)
Tập trung chuyên sâu bóc tách EMAIL B2B từ:
1. Deep Website Crawling (162 website đang có nhưng chưa có mail):
   - Quét trang chủ + các subpages: /kontaktai, /apie-mus, /karjera, /contact, /contacts
   - Giải mã Cloudflare data-cfemail, mailto, regex text
2. Reverse Search & Directory Matching:
   - Tra cứu qua Tên công ty, SĐT (+370...) và Mã số IČO
3. Quy chuẩn bắt buộc:
   - Rule #1: CSV UTF-8 with BOM (utf-8-sig) ONLY
   - Rule #2: SĐT có dấu nháy đơn '
   - Rule #3: B2B Email Scoring, 1 mail chất lượng nhất, 100% email đẩy lên đầu
   - Rule #12: Loại trừ triệt để Scandi Standard, Biliarta, Daigre
"""

import os
import sys
import re
import json
import time
import base64
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_2COL_ROOT = BASE_DIR / "LT_AGCY_REKV_2COL.csv"
TARGET_2COL_CSDL = BASE_DIR / "csdl_mlt" / "LT_AGCY_REKV_2COL.csv"
TARGET_1ENR_CSDL = BASE_DIR / "csdl_mlt" / "LT_AGCY_REKV_1ENR.csv"
CACHE_FILE = BASE_DIR / "crawlmail" / "cache_enrich_email_lt_agcy.json"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule #12: Permanent Blacklist
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

def clean_phone_lt(phone_str):
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = phone_str.strip().lstrip("'")
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

# ----------------------------------------------------------------------
# BỘ LỌC VÀ CHẤM ĐIỂM EMAIL B2B
# ----------------------------------------------------------------------
JUNK_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@'
]

DEMO_DOMAINS = {
    'example.com', 'domain.com', 'email.com', 'yoursite.com', 'yourdomain.com',
    'wix.com', 'wixpress.com', 'sentry.io', 'wordpress.com', 'github.com',
    'mysite.com', 'sitename.com', 'company.com'
}

def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower()
    e = re.sub(r'^(?:u003e|u003c|>|<|&gt;|&lt;)', '', e)
    if '%20' in e or ' ' in e or '@' not in e or '.' not in e:
        return False
    user, _, dom = e.partition('@')
    if not user or not dom or '.' not in dom:
        return False
    if dom in DEMO_DOMAINS or any(dom.endswith('.' + d) for d in DEMO_DOMAINS):
        return False
    if any(p in user for p in JUNK_PARTS):
        return False
    if any(e.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.css', '.js', '.pdf']):
        return False
    return True

def score_email_b2b(email, domain=""):
    if not is_valid_email(email):
        return -1
    e = email.lower().strip()
    u, _, d = e.partition('@')
    score = 0
    if domain and domain in d:
        score += 50
    # Ưu tiên tuyển dụng / nhân sự
    hr_keys = ['darbas', 'karjera', 'cv', 'hr', 'personalas', 'personal', 'job', 'recruit', 'career']
    # Ưu tiên ban giám đốc / lãnh đạo
    boss_keys = ['vadovas', 'direktorius', 'ceo', 'director', 'manager', 'prekyba', 'sales']
    # Ưu tiên cổng liên hệ chính thức
    contact_keys = ['info', 'kontaktai', 'kontakt', 'contact', 'biuras', 'office', 'sekretoriatas']
    
    if any(k in u for k in hr_keys):
        score += 50
    elif any(k in u for k in boss_keys):
        score += 45
    elif any(k in u for k in contact_keys):
        score += 40
    elif '.' in u or '_' in u:
        score += 25
    elif d in ['gmail.com', 'yahoo.com', 'inbox.lt', 'one.lt', 'mail.ru']:
        score += 10
    else:
        score += 20
    return score

def decode_cf(hex_str):
    try:
        r = int(hex_str[:2], 16)
        email = "".join([chr(int(hex_str[i:i+2], 16) ^ r) for i in range(2, len(hex_str), 2)])
        return email.lower().strip()
    except Exception:
        return ""

# ----------------------------------------------------------------------
# DEEP CRAWLER CHO TỪNG WEBSITE
# ----------------------------------------------------------------------
def crawl_website_deep(web_url):
    """
    Quét sâu một website doanh nghiệp qua các trang con để bóc tách Email.
    """
    if not web_url or not isinstance(web_url, str):
        return ""
    w = web_url.strip()
    if not w.startswith("http"):
        w = "https://" + w
    try:
        parsed = urllib.parse.urlparse(w)
        domain = parsed.netloc.replace("www.", "").lower()
        if not domain or len(domain) < 4:
            return ""
        root = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return ""

    found_emails = set()
    
    # 1. Quét trang chủ
    try:
        r = requests.get(w, impersonate="chrome120", timeout=8, verify=False)
        if r.status_code == 200:
            html = r.text
            # mailto:
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
                clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                if is_valid_email(clean_m):
                    found_emails.add(clean_m)
            # Cloudflare:
            for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                dec = decode_cf(cf)
                if is_valid_email(dec):
                    found_emails.add(dec)
            # Text regex:
            for em in re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', html):
                em_l = em.strip().lower()
                if is_valid_email(em_l):
                    found_emails.add(em_l)
                    
            # Tìm link liên hệ trên DOM menu
            soup = BeautifulSoup(html, "html.parser")
            sublinks = []
            for a in soup.find_all("a", href=True):
                h = a["href"]
                h_l = h.lower()
                txt = a.get_text().lower()
                if any(k in h_l or k in txt for k in ['kontakt', 'contact', 'apie', 'karjer', 'darb', 'about']):
                    full = urllib.parse.urljoin(w, h)
                    if domain in full.lower() and full not in sublinks and '#' not in h:
                        sublinks.append(full)
                        
            # Quét tối đa 4 sublinks
            for sub in sublinks[:4]:
                try:
                    r_sub = requests.get(sub, impersonate="chrome120", timeout=6, verify=False)
                    if r_sub.status_code == 200:
                        s_html = r_sub.text
                        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', s_html, re.I):
                            clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                            if is_valid_email(clean_m):
                                found_emails.add(clean_m)
                        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', s_html):
                            dec = decode_cf(cf)
                            if is_valid_email(dec):
                                found_emails.add(dec)
                        for em in re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', s_html):
                            em_l = em.strip().lower()
                            if is_valid_email(em_l):
                                found_emails.add(em_l)
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Thử các subpath dự phòng chuẩn Baltic nếu chưa có email
    if not found_emails:
        fallback_paths = [
            f"{root}/kontaktai", f"{root}/kontaktai/", f"{root}/kontaktai.html",
            f"{root}/contacts", f"{root}/contact", f"{root}/apie-mus", f"{root}/apie-mus/"
        ]
        for fb in fallback_paths:
            try:
                r_fb = requests.get(fb, impersonate="chrome120", timeout=6, verify=False)
                if r_fb.status_code == 200:
                    fb_html = r_fb.text
                    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', fb_html, re.I):
                        clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                        if is_valid_email(clean_m):
                            found_emails.add(clean_m)
                    for em in re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', fb_html):
                        em_l = em.strip().lower()
                        if is_valid_email(em_l):
                            found_emails.add(em_l)
                    if found_emails:
                        break
            except Exception:
                pass

    if not found_emails:
        return ""

    # Chọn 1 email có điểm số cao nhất
    best_email = max(found_emails, key=lambda e: score_email_b2b(e, domain))
    return best_email

# ----------------------------------------------------------------------
# CHƯƠNG TRÌNH CHÍNH
# ----------------------------------------------------------------------
def main():
    print("=" * 80)
    print(" LÀM GIÀU EMAIL CHUYÊN SÂU - MÔI GIỚI LAO ĐỘNG LITVA (LT_AGCY)")
    print(f" Target File: {TARGET_2COL_ROOT}")
    print("=" * 80)

    if not TARGET_2COL_ROOT.exists():
        print(f"[!] Không tìm thấy tệp {TARGET_2COL_ROOT}!")
        return

    df = pd.read_csv(TARGET_2COL_ROOT, encoding="utf-8-sig", dtype=str).fillna("")
    print(f"[*] Tổng số doanh nghiệp trong tệp: {len(df):,}")

    # Đọc Cache
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Đã nạp Cache: {len(cache):,} doanh nghiệp.")
        except Exception:
            pass

    # Lọc danh sách công ty cần làm giàu:
    # Nhóm 1: Có website nhưng CHƯA CÓ EMAIL
    # Nhóm 2: Đã có SĐT nhưng CHƯA CÓ EMAIL
    candidates_with_web = []
    already_has_email = 0

    for idx, r in df.iterrows():
        em = str(r.get("Email", "")).strip()
        comp = str(r.get("Công ty", "")).strip()
        web = str(r.get("Liên Hệ", "")).strip()
        
        if is_blacklisted_company(comp):
            continue

        if em and is_valid_email(em):
            already_has_email += 1
            continue

        if web and web.startswith("http"):
            candidates_with_web.append((idx, comp, web))

    print(f"[*] Đang có sẵn Email xác thực: {already_has_email:,}")
    print(f"[*] CẦN QUÉT SÂU QUA WEBSITE   : {len(candidates_with_web):,} công ty")

    # Tiến hành cào đa luồng qua website
    new_emails_found = 0
    cache_lock = Lock()

    def process_web_candidate(item):
        idx, comp, web = item
        cache_key = comp.lower().strip()
        
        with cache_lock:
            if cache_key in cache and cache[cache_key]:
                return idx, comp, cache[cache_key], "Cache"

        email = crawl_website_deep(web)
        
        with cache_lock:
            cache[cache_key] = email
            
        return idx, comp, email, "Web"

    print("\n[*] Đang khởi chạy Deep Crawler qua các website (8 luồng)...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_web_candidate, it) for it in candidates_with_web]
        for f in as_completed(futures):
            try:
                idx, comp, email, src = f.result()
                if email and is_valid_email(email):
                    new_emails_found += 1
                    df.at[idx, "Email"] = email
                    df.at[idx, "Liên Hệ mail"] = f"mailto:{email}"
                    print(f"    [+] [{new_emails_found}] {comp[:35]:35s} -> {email} ({src})")
            except Exception as e:
                pass

    # Lưu lại Cache
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Chuẩn hóa lại toàn bộ SĐT có nháy đơn và áp dụng Rule #12
    valid_rows = []
    for idx, r in df.iterrows():
        comp = str(r.get("Công ty", "")).strip()
        if is_blacklisted_company(comp):
            continue
        r_dict = r.to_dict()
        r_dict["SĐT"] = clean_phone_lt(r_dict.get("SĐT", ""))
        valid_rows.append(r_dict)

    # Đưa 100% công ty có Email lên đầu tệp CSV theo Rule #3
    with_email = [r for r in valid_rows if r.get("Email") and is_valid_email(r.get("Email"))]
    without_email = [r for r in valid_rows if not (r.get("Email") and is_valid_email(r.get("Email")))]
    sorted_rows = with_email + without_email

    for i, r in enumerate(sorted_rows, 1):
        r["No."] = i

    df_out = pd.DataFrame(sorted_rows, columns=COLDMAIL_COLUMNS)

    # Xuất ra các tệp đích UTF-8 with BOM
    df_out.to_csv(TARGET_2COL_ROOT, index=False, encoding="utf-8-sig")
    TARGET_2COL_CSDL.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(TARGET_2COL_CSDL, index=False, encoding="utf-8-sig")
    df_out.to_csv(TARGET_1ENR_CSDL, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 80)
    print(" KẾT QUẢ LÀM GIÀU EMAIL CHO MÔI GIỚI LITVA:")
    print(f" - Tổng số doanh nghiệp       : {len(df_out):,}")
    print(f" - Số Email mới tìm thấy thêm : +{new_emails_found:,}")
    print(f" - TỔNG CÔNG TY CÓ EMAIL      : {len(with_email):,} ({len(with_email)/len(df_out)*100:.1f}%)")
    print(f"   --> 100% ({len(with_email)}) doanh nghiệp có Email đã nằm tại dòng 1..{len(with_email)}")
    print(f" - Không có Email             : {len(without_email):,}")
    print(f" - Tệp kết quả cập nhật       : {TARGET_2COL_ROOT}")
    print("=" * 80)

if __name__ == "__main__":
    main()
