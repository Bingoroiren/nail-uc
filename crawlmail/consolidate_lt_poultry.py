#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHUYÊN GIA LÀM GIÀU & ĐỊNH DẠNG COLD MAIL CHO XƯỞNG GÀ LITVA (LT_POUL)
Input : LT_POUL_WEBD_0RAW.csv
Output: LT_POUL_WEBD_1ENR.csv, LT_POUL_WEBD_2COL.csv

Tuân thủ nghiêm ngặt Workspace Rules:
- Rule #1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule #2: SĐT có dấu nháy đơn '
- Rule #3: Chấm điểm B2B email, lấy 1 mail chất lượng nhất, 100% mail đẩy lên đầu
- Rule #10: Tên file cố định 17 ký tự ([CC]_[IND4]_[SRC4]_[STG4].csv)
- Rule #12: Loại trừ triệt để Scandi Standard, Biliarta, Daigre
"""

import os
import sys
import re
import csv
import json
import time
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_RAW = BASE_DIR / "LT_POUL_WEBD_0RAW.csv"
OUTPUT_1ENR = BASE_DIR / "LT_POUL_WEBD_1ENR.csv"
OUTPUT_2COL = BASE_DIR / "LT_POUL_WEBD_2COL.csv"
CACHE_FILE = BASE_DIR / "crawlmail" / "cache_email_lt_poultry.json"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# ----------------------------------------------------------------------
# RULE #12: PERMANENT BLACKLIST
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# BỘ LỌC EMAIL RÁC & CHẤM ĐIỂM B2B EMAIL
# ----------------------------------------------------------------------
JUNK_PREFIXES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse', 'postmaster',
    'mailer-daemon', 'sentry', 'security', 'billing', 'support', 'help', 'admin'
}

DEMO_DOMAINS = {
    'example.com', 'domain.com', 'email.com', 'yoursite.com', 'yourdomain.com',
    'wix.com', 'wixpress.com', 'sentry.io', 'wordpress.com', 'github.com',
    'mysite.com', 'sitename.com', 'company.com', 'saulesspektras.lt', 'info.lt'
}

def clean_phone_lt(raw):
    if not raw or not isinstance(raw, str):
        return ""
    p = re.sub(r"[^\d+]", "", raw.strip().lstrip("'"))
    if not p:
        return ""
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and len(p) == 10:
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    return f"'{p}" if not p.startswith("'") else p

def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower()
    if '%20' in e or ' ' in e or '@' not in e:
        return False
    user, _, dom = e.partition('@')
    if not user or not dom or '.' not in dom:
        return False
    if dom in DEMO_DOMAINS or any(dom.endswith('.' + d) for d in DEMO_DOMAINS):
        return False
    if any(user.startswith(p) for p in JUNK_PREFIXES):
        return False
    if any(k in user for k in ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'user']):
        return False
    return True

def score_email_b2b(email, domain=""):
    """
    Chấm điểm email tối ưu cho tuyển dụng & kết nối B2B (Lithuania & Quốc tế):
    - Trùng domain website (+50đ)
    - Nhân sự/Tuyển dụng: darbas@, karjera@, cv@, hr@, personalas@ (+50đ)
    - Lãnh đạo/Giám đốc: vadovas@, direktorius@, ceo@, manager@ (+45đ)
    - Đầu mối liên hệ: info@, kontaktai@, biuras@, office@ (+40đ)
    - Cá nhân tên.họ@: (+25đ)
    - Webmail miễn phí (@gmail.com...): (+10đ)
    """
    if not is_valid_email(email):
        return -1
    e = email.lower().strip()
    u, _, d = e.partition('@')
    score = 0
    
    if domain and domain in d:
        score += 50
        
    hr_keys = ['darbas', 'karjera', 'cv', 'hr', 'personalas', 'personal', 'job', 'recruit', 'career']
    boss_keys = ['vadovas', 'direktorius', 'ceo', 'director', 'manager', 'prekyba', 'sales']
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

# ----------------------------------------------------------------------
# DEEP CRAWL EMAIL QUA WEBSITE DOANH NGHIỆP
# ----------------------------------------------------------------------
def decode_cf(hex_str):
    try:
        r = int(hex_str[:2], 16)
        email = "".join([chr(int(hex_str[i:i+2], 16) ^ r) for i in range(2, len(hex_str), 2)])
        return email.lower().strip()
    except Exception:
        return ""

def crawl_website_for_email(web_url):
    """
    Quét sâu website doanh nghiệp tìm Email với Priority 10 DOM menu & subpaths bản địa Litva.
    """
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith("http"):
        web_url = "https://" + web_url
        
    try:
        parsed = urllib.parse.urlparse(web_url)
        domain = parsed.netloc.replace('www.', '').lower()
        if not domain or len(domain) < 4:
            return ""
    except Exception:
        return ""
        
    found_emails = set()
    root = f"{parsed.scheme}://{parsed.netloc}"
    
    # 1. Trang chủ
    try:
        r = requests.get(web_url, impersonate="chrome120", timeout=10, verify=False)
        if r.status_code == 200:
            html = r.text
            # Mailto:
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
                clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                if is_valid_email(clean_m):
                    found_emails.add(clean_m)
            # Cloudflare
            for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                dec = decode_cf(cf)
                if is_valid_email(dec):
                    found_emails.add(dec)
            # Regex
            for em in re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', html):
                em_l = em.strip().lower()
                if is_valid_email(em_l):
                    found_emails.add(em_l)
                    
            # Tìm link liên hệ trên DOM menu (Priority 10)
            soup = BeautifulSoup(html, 'html.parser')
            sublinks = []
            for a in soup.find_all('a', href=True):
                h = a['href']
                h_l = h.lower()
                txt = a.get_text().lower()
                if any(k in h_l or k in txt for k in ['kontakt', 'contact', 'apie', 'karjer', 'darb', 'about']):
                    full = urllib.parse.urljoin(web_url, h)
                    if domain in full.lower() and full not in sublinks and '#' not in h:
                        sublinks.append(full)
                        
            # Quét tối đa 4 subpages
            for sub in sublinks[:4]:
                try:
                    r_sub = requests.get(sub, impersonate="chrome120", timeout=8, verify=False)
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
        
    # 2. Thử các subpath dự phòng nếu chưa có email
    if not found_emails:
        fallback_paths = [
            f"{root}/kontaktai", f"{root}/kontaktai/", f"{root}/kontaktai.html",
            f"{root}/contact", f"{root}/contact/", f"{root}/contacts",
            f"{root}/apie-mus", f"{root}/about", f"{root}/about-us"
        ]
        for fb in fallback_paths:
            try:
                r_fb = requests.get(fb, impersonate="chrome120", timeout=7, verify=False)
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
        
    # Chọn ra DUY NHẤT 1 EMAIL CÓ ĐIỂM SỐ CAO NHẤT
    best_email = max(found_emails, key=lambda e: score_email_b2b(e, domain))
    return best_email

# ----------------------------------------------------------------------
# CONSOLIDATE VÀ XUẤT FILE COLD MAIL CHUẨN
# ----------------------------------------------------------------------
def main():
    print("=" * 80)
    print(" CONSOLIDATION & COLD MAIL FORMATTER: LITHUANIA POULTRY (LT_POUL)")
    print(f" Input Raw: {INPUT_RAW}")
    print(f" Out 1ENR : {OUTPUT_1ENR}")
    print(f" Out 2COL : {OUTPUT_2COL}")
    print("=" * 80)

    if not INPUT_RAW.exists():
        print(f"[!] File thô {INPUT_RAW} chưa tồn tại. Vui lòng chạy bộ cào crawl_lt_poultry.py trước.")
        return

    # Load cache
    email_cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                email_cache = json.load(f)
        except Exception:
            pass

    # Đọc dữ liệu thô bằng csv.DictReader
    with open(INPUT_RAW, "r", encoding="utf-8-sig", errors="ignore") as f:
        raw_rows = list(csv.DictReader(f))
    print(f"[*] Tổng số dòng dữ liệu thô: {len(raw_rows)}")

    # 1. Khử trùng lặp theo tên và IČO + Áp dụng Rule #12 Permanent Blacklist
    dedup_rows = []
    seen_names = set()
    seen_icos = set()
    blacklisted_count = 0

    for row in raw_rows:
        comp_name = str(row.get("Công ty", "")).strip()
        if not comp_name:
            continue

        if is_blacklisted_company(comp_name):
            blacklisted_count += 1
            continue

        norm_name = unicodedata.normalize('NFKD', comp_name).lower()
        norm_name = re.sub(r"[^\w\s]", "", norm_name)
        norm_name = " ".join(norm_name.split())
        
        ico = str(row.get("IČO", "")).strip()
        
        if norm_name in seen_names or (ico and ico in seen_icos):
            continue

        seen_names.add(norm_name)
        if ico:
            seen_icos.add(ico)

        r_dict = dict(row)
        # Chuẩn hóa SĐT
        r_dict["SĐT"] = clean_phone_lt(r_dict.get("SĐT", ""))
        dedup_rows.append(r_dict)

    print(f"[*] Sau khử trùng lặp và loại trừ {blacklisted_count} công ty blacklist: còn lại {len(dedup_rows)} doanh nghiệp.")

    # 2. Quét làm giàu Email qua Website nếu chưa có
    enriched_rows = []
    cache_lock = Lock()
    
    def process_row(r_dict):
        existing_email = str(r_dict.get("Email", "")).strip()
        web = str(r_dict.get("Web", "")).strip()
        
        if existing_email and is_valid_email(existing_email):
            r_dict["Email"] = existing_email
            return r_dict

        if web:
            parsed = urllib.parse.urlparse(web if web.startswith("http") else "http://" + web)
            domain = parsed.netloc.replace("www.", "").lower()
            
            with cache_lock:
                if domain in email_cache:
                    cached_mail = email_cache[domain]
                    if cached_mail:
                        r_dict["Email"] = cached_mail
                    return r_dict
                    
            crawled_mail = crawl_website_for_email(web)
            with cache_lock:
                email_cache[domain] = crawled_mail
                
            if crawled_mail:
                r_dict["Email"] = crawled_mail
                print(f"    [+] Bóc tách email mới: {r_dict['Công ty']} -> {crawled_mail}")
                
        return r_dict

    print("[*] Đang làm giàu email sâu từ website (đa luồng)...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_row, r) for r in dedup_rows]
        for f in as_completed(futures):
            enriched_rows.append(f.result())

    # Lưu cache
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(email_cache, f, indent=2, ensure_ascii=False)

    # 3. Phân loại và đẩy 100% doanh nghiệp có Email lên đầu
    with_email = [r for r in enriched_rows if r.get("Email") and is_valid_email(r.get("Email"))]
    without_email = [r for r in enriched_rows if not (r.get("Email") and is_valid_email(r.get("Email")))]
    sorted_rows = with_email + without_email

    # Gán lại No.
    for i, r in enumerate(sorted_rows, 1):
        r["No."] = i

    # Xuất file 1ENR
    if sorted_rows:
        fieldnames_1enr = list(sorted_rows[0].keys())
        with open(OUTPUT_1ENR, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_1enr)
            writer.writeheader()
            writer.writerows(sorted_rows)
    print(f"[*] Đã xuất {len(sorted_rows)} dòng vào file 1ENR: {OUTPUT_1ENR}")

    # 4. Xuất file 2COL (Cold Mail)
    cold_rows = []
    for r in sorted_rows:
        cold_dict = {
            'No.': r.get("No.", ""),
            'Công ty': r.get("Công ty", ""),
            'Chức danh': "Direktorius" if r.get("Direktorius") else "",
            'Người liên hệ': r.get("Direktorius", ""),
            'SĐT': clean_phone_lt(r.get("SĐT", "")),
            'Liên Hệ': r.get("Web", ""),
            'Email': r.get("Email", ""),
            'Liên Hệ mail': "",
            'Địa chỉ': r.get("Địa chỉ", ""),
            'Lương': "",
            'Ngày đăng': "",
            'Hạn tuyển': "",
            'Check gửi': "",
            'Last Subject': "",
            'Last Body HTML': "",
            'Trạng thái Reply': "",
            'Lần Follow-up': "",
            'Ngày Follow-up gần nhất': "",
            'Mailbox đã dùng': "",
            'Category': r.get("Category", "Poultry & Meat Processing")
        }
        cold_rows.append(cold_dict)

    with open(OUTPUT_2COL, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(cold_rows)

    print("\n" + "=" * 80)
    total_cold = len(cold_rows)
    pct_email = (len(with_email) / total_cold * 100) if total_cold > 0 else 0
    print(f" - Tổng số công ty: {total_cold}")
    print(f" - Có Email: {len(with_email)} ({pct_email:.1f}%) -> Nằm ngay các dòng 1..{len(with_email)}")
    print(f" - Không có Email: {len(without_email)}")
    print(f" - File Cold Mail 20 cột: {OUTPUT_2COL}")
    print("=" * 80)

if __name__ == "__main__":
    main()
