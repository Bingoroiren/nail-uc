# -*- coding: utf-8 -*-
"""
HỆ THỐNG DEEP SCAN V2 BÓC TÁCH EMAIL B2B XƯỞNG ĐÓNG TÀU & THỢ HÀN HÀN QUỐC
- Giải mã Cloudflare Email Protection (data-cfemail & /cdn-cgi/l/email-protection#)
- Bóc tách menu DOM động (Priority 10: contact, location, 오시는길, 회사소개, inquiry)
- Trích xuất liên kết mailto:
- Bộ lọc phiên bản phần mềm & font chữ rác
- Chấm điểm tối ưu B2B Manpower / Welder Recruitment
- Đẩy 100% doanh nghiệp CÓ EMAIL lên hàng đầu danh sách
"""

import os
import sys
import re
import csv
import json
import time
import asyncio
import urllib.parse
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL = True
except ImportError:
    HAS_CURL = False

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_2COL = ROOT_DIR / "KR_SHIP_HIPC_2COL.csv"
TARGET_1ENR = ROOT_DIR / "KR_SHIP_HIPC_1ENR.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_ship_deep_v2.json"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

GARBAGE_PATTERNS = [
    'react', 'player', 'core-js', 'gabia.com',
    'wixpress', 'sentry', 'example.com', 'domain.com',
    'someone@', 'youremail@', 'yourname@', 'name@domain',
    'user@domain', 'test@', 'email@email', '@whois', 'sample@',
    'bootstrap', 'jquery', 'webpack', '.png', '.jpg',
    'saramin', 'jobkorea', 'worknet', 'work24', 'help@saramin',
    'xeicon', 'fontawesome', 'glyphicons', 'temp@', 'email@',
    'aos@', 'lenis@', 'pretendard@', 'swiper@', 'lodash@',
    'grad@', 'opsz@', 'wght@', 'fill@'
]

def decode_cf_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email
    except Exception:
        return ""

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\r', '').replace('\n', '').strip()
    if not p_str or p_str.lower() in ['none', 'nan', '-']:
        return ""
    p_str = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_str:
        return ""
    if not p_str.startswith("'"):
        p_str = f"'{p_str}"
    return p_str

VALID_TLDS = {
    'com', 'kr', 'co.kr', 'net', 'org', 'or.kr', 'io', 'ne.kr', 
    'go.kr', 're.kr', 'biz', 'info', 'me', 'asia', 'cn', 'jp', 
    'vn', 'de', 'uk', 'eu', 'sg', 'tw'
}

def is_valid_email(email):
    if not email:
        return False
    em = str(email).strip().lower().replace('%20', '').rstrip('.')
    if len(em) < 6 or '@' not in em or '.' not in em or '..' in em:
        return False
    if any(g in em for g in GARBAGE_PATTERNS):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|webp|svg|css|js|woff|woff2|ttf)$', em):
        return False
    
    user, _, dom = em.partition('@')
    if len(user) < 2 or len(dom) < 3:
        return False
    if not re.search(r'^[a-zA-Z0-9_.+-]+$', user):
        return False
    # Domain must not have version numbers or digit-only TLDs
    parts = dom.split('.')
    tld = parts[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    # Two-level TLD check like co.kr, or.kr
    if len(parts) >= 2 and f"{parts[-2]}.{parts[-1]}" in VALID_TLDS:
        return True
    if tld in VALID_TLDS:
        return True
    return False

def score_email(em, domain=""):
    em = em.lower()
    sc = 10
    user, _, em_dom = em.partition('@')
    
    if domain and domain in em_dom:
        sc += 50
        
    if any(p in user for p in ['recruit', 'hr', 'job', 'career', 'insa', 'work', 'chayong']):
        sc += 50
    elif any(p in user for p in ['ceo', 'director', 'manager', 'president', 'master', 'daepyo']):
        sc += 45
    elif any(p in user for p in ['info', 'contact', 'office', 'help', 'admin', 'service', 'inquiry']):
        sc += 40
    elif '.' in user:
        sc += 25
        
    if any(em.endswith(f) for f in ['@gmail.com', '@naver.com', '@daum.net', '@hanmail.net']):
        sc += 15
    else:
        sc += 25
    return sc

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def scan_single_website(session, site_url):
    """Deep scan 1 website: CF decode, mailto:, DOM menu links, up to 2 subpages"""
    if not site_url or not site_url.startswith('http'):
        return ""
        
    parsed = urllib.parse.urlparse(site_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.lower().replace('www.', '')
    
    candidates = set()
    visited = set()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    # 1. Quét trang chủ
    try:
        r = await session.get(site_url, timeout=7, headers=headers)
        visited.add(site_url)
        if r.status_code == 200:
            text = r.text
            # CF
            for cf in re.findall(r'data-cfemail="([a-fA-F0-9]+)"', text):
                dec = decode_cf_email(cf)
                if is_valid_email(dec):
                    candidates.add(dec)
            for cf in re.findall(r'/cdn-cgi/l/email-protection#([a-fA-F0-9]+)', text):
                dec = decode_cf_email(cf)
                if is_valid_email(dec):
                    candidates.add(dec)
            # mailto:
            for mail in re.findall(r'mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text, re.I):
                if is_valid_email(mail):
                    candidates.add(mail.lower())
            # raw
            for mail in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text):
                if is_valid_email(mail):
                    candidates.add(mail.lower())
                    
            # 2. Nếu chưa có email, tìm subpage từ menu DOM
            if not candidates:
                soup = BeautifulSoup(r.content, 'html.parser')
                sub_links = []
                for a in soup.find_all('a', href=True):
                    h = a['href'].strip()
                    t = a.get_text().strip().lower()
                    h_lower = h.lower()
                    if any(k in h_lower or k in t for k in ['contact', 'location', '오시는', '회사소개', 'inquiry', 'about', 'intro', 'customer', 'sub']):
                        if not h.startswith('javascript') and not h.startswith('mailto:') and not h.startswith('#'):
                            full = urllib.parse.urljoin(site_url, h)
                            if full.startswith(base_url) and full not in visited:
                                sub_links.append(full)
                                
                # Thử thêm các subpath phổ biến của Hàn Quốc nếu DOM không có
                fallback_paths = ['/contact', '/about', '/location', '/sub/contact.php', '/kor/contact', '/company']
                for fp in fallback_paths:
                    fb_url = base_url.rstrip('/') + fp
                    if fb_url not in visited and fb_url not in sub_links:
                        sub_links.append(fb_url)
                        
                for sub in sub_links[:3]:
                    visited.add(sub)
                    try:
                        sr = await session.get(sub, timeout=6, headers=headers)
                        if sr.status_code == 200:
                            stext = sr.text
                            for cf in re.findall(r'data-cfemail="([a-fA-F0-9]+)"', stext):
                                dec = decode_cf_email(cf)
                                if is_valid_email(dec):
                                    candidates.add(dec)
                            for cf in re.findall(r'/cdn-cgi/l/email-protection#([a-fA-F0-9]+)', stext):
                                dec = decode_cf_email(cf)
                                if is_valid_email(dec):
                                    candidates.add(dec)
                            for mail in re.findall(r'mailto:([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', stext, re.I):
                                if is_valid_email(mail):
                                    candidates.add(mail.lower())
                            for mail in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', stext):
                                if is_valid_email(mail):
                                    candidates.add(mail.lower())
                            if candidates:
                                break
                    except Exception:
                        pass
    except Exception:
        pass
        
    if not candidates:
        return ""
        
    scored = [(score_email(c, domain), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]

def save_both_csvs(records):
    """Xuất file chuẩn 20 cột, đẩy 100% doanh nghiệp có Email lên đầu"""
    with_email = []
    without_email = []
    
    for r in records:
        em = str(r.get('Email', '')).strip()
        if em and '@' in em:
            with_email.append(r)
        else:
            without_email.append(r)
            
    sorted_all = with_email + without_email
    
    for path in [TARGET_2COL, TARGET_1ENR]:
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
            writer.writeheader()
            for idx, item in enumerate(sorted_all, 1):
                row_dict = {col: item.get(col, '') for col in COLUMNS_20}
                row_dict['No.'] = str(idx)
                if row_dict['SDT']:
                    row_dict['SDT'] = clean_phone(row_dict['SDT'])
                if not row_dict.get('Luong'):
                    row_dict['Luong'] = 'Thỏa thuận theo bậc tay nghề E-7-3'
                if not row_dict.get('Ngay dang'):
                    row_dict['Ngay dang'] = '2026-10-06'
                writer.writerow(row_dict)

async def run_deep_scan():
    print("=" * 70)
    print(" CÁCH 1: KHỞI CHẠY DEEP SCAN V2 TRÊN TẤT CẢ WEBSITE CÒN THIẾU EMAIL")
    print(" (Cloudflare Decode + Thẻ DOM Menu Priority 10 + mailto: + Subpages)")
    print("=" * 70)
    
    if not TARGET_2COL.exists():
        print(f"[!] Không tìm thấy tệp {TARGET_2COL}")
        return
        
    records = []
    with open(TARGET_2COL, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            records.append(r)
            
    cache = load_cache()
    
    # Lọc các công ty chưa có email nhưng có website
    to_scan = []
    for r in records:
        em = str(r.get('Email', '')).strip()
        web = str(r.get('Lien He', '')).strip()
        if not em and web and web.startswith('http'):
            to_scan.append(r)
            
    print(f"[*] Tổng số công ty: {len(records)}")
    print(f"[*] Đã có email trước đó: {len([r for r in records if r.get('Email')])}")
    print(f"[*] Cần quét sâu (có web, chưa có mail): {len(to_scan)} công ty")
    print(f"[*] Đã lưu trong cache v2: {len(cache)} sites")
    
    semaphore = asyncio.Semaphore(15)
    new_found = 0
    scanned_count = 0
    
    async def bound_scan(comp, session):
        nonlocal new_found, scanned_count
        async with semaphore:
            site = comp.get('Lien He', '').strip()
            if not site:
                return
            if site in cache:
                em = cache[site]
            else:
                em = await scan_single_website(session, site)
                cache[site] = em
                
            scanned_count += 1
            if em:
                comp['Email'] = em
                new_found += 1
                try:
                    print(f"[{scanned_count}/{len(to_scan)}] [NEW EMAIL] {comp['Cong ty']} -> {em}")
                except Exception:
                    print(f"[{scanned_count}/{len(to_scan)}] [NEW EMAIL] -> {em}")
                    
            if scanned_count % 30 == 0:
                save_cache(cache)
                save_both_csvs(records)
                print(f"  --> Checkpoint: Đã quét {scanned_count}/{len(to_scan)} | Tìm thêm được {new_found} emails mới!")

    async with AsyncSession(impersonate="chrome120") as session:
        tasks = [bound_scan(c, session) for c in to_scan]
        await asyncio.gather(*tasks)
        
    save_cache(cache)
    save_both_csvs(records)
    
    total_with_email = len([r for r in records if r.get('Email')])
    print("\n" + "=" * 70)
    print(f" HOÀN TẤT CÁCH 1 (DEEP SCAN V2)!")
    print(f" - Số email B2B mới tìm thấy thêm: {new_found}")
    print(f" - Tổng số công ty CÓ EMAIL trong KR_SHIP_HIPC_2COL.csv: {total_with_email}/{len(records)}")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(run_deep_scan())
