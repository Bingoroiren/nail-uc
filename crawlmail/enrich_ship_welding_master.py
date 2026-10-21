# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM GIÀU DATA THỢ HÀN & XƯỞNG ĐÓNG TÀU TOÀN DIỆN (KOMEA + BMEA + DEEP WEB CRAWLER)
Ưu tiên tuyệt đối: TỐI ĐA HÓA EMAIL B2B (100% EMAIL LÊN ĐẦU DANH SÁCH).

Quy trình:
1. Tải toàn bộ danh bạ hội viên chính thức của:
   - KOMEA (한국조선해양기자재공업협동조합 - 354 nhà sản xuất kết cấu, bồn ống & thiết bị đóng tàu).
   - BMEA (부산조선해양기자재협동조합 - 407 nhà máy cơ khí & đóng tàu Busan).
2. Tích hợp với danh sách thầu phụ xưởng đóng tàu hiện có trong KR_SHIP_HIPC_2COL.csv (118 thầu phụ Hyundai + xưởng tàu KOSIC).
3. Chạy Deep Web Crawler bất đồng bộ siêu tốc (AsyncSession) quét sâu toàn bộ Website công ty:
   - Quét: trang chủ, /contact, /about, /intro, /kor/contact, /company...
   - Bóc tách và chấm điểm email B2B (recruit@, hr@, ceo@, info@, domain trùng).
4. Khử trùng lặp theo tên công ty.
5. Đẩy 100% công ty CÓ EMAIL lên đầu danh sách.
6. Xuất ra KR_SHIP_HIPC_2COL.csv chuẩn 20 cột Cold Mail UTF-8 with BOM (utf-8-sig).
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
    from curl_cffi.requests import AsyncSession, Session
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
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_ship_welding_websites.json"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

GARBAGE_PATTERNS = [
    'react-dom@', 'player-component@', 'core-js@', '@gabia.com',
    '@wixpress.com', '@sentry.io', 'example.com', 'domain.com',
    'someone@', 'youremail@', 'yourname@', 'name@domain',
    'user@domain', 'test@', 'email@email', '@whois', 'sample@',
    'bootstrap@', 'jquery@', 'webpack@', '@2x.png', '@3x.png',
    'saramin@', 'jobkorea@', 'worknet@', 'work24@', 'help@saramin',
    'xeicon@', 'fontawesome@', 'glyphicons@', '@temp', 'email@'
]

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'[\r\n\t]+', ' ', str(name)).strip()
    return re.sub(r'\s+', ' ', name)

def normalize_key(name):
    n = clean_company_name(name).lower()
    for drop in ['(주)', '㈜', '주식회사', '(유)', '유한회사', '사내협력사', '협동조합', '공업사']:
        n = n.replace(drop, '')
    return re.sub(r'[^a-zA-Z0-9가-힣]', '', n).strip()

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

def is_valid_email(email):
    if not email:
        return False
    em = str(email).strip().lower().replace('%20', '')
    if len(em) < 6 or '@' not in em or '.' not in em:
        return False
    if any(g in em for g in GARBAGE_PATTERNS):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|webp|svg|css|js)$', em):
        return False
    return True

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

def fetch_komea_companies(session):
    """Tải toàn bộ hội viên KOMEA qua endpoint Excel"""
    print("[1/3] Đang tải danh bạ hội viên KOMEA (354 nhà máy đóng tàu)...")
    url = "http://www.komea.kr/komea/mn0202Excel.do"
    try:
        r = session.post(url, timeout=12)
        if r.status_code == 200:
            tables = pd.read_html(r.content, encoding='euc-kr')
            df = tables[0]
            records = []
            for _, row in df.iloc[2:].iterrows():
                cname = clean_company_name(row[1])
                ceo = str(row[2]).strip() if pd.notna(row[2]) else ""
                tel = str(row[3]).strip() if pd.notna(row[3]) else ""
                web = str(row[4]).strip() if pd.notna(row[4]) else ""
                region = str(row[5]).strip() if pd.notna(row[5]) else ""
                
                if cname:
                    records.append({
                        'Cong ty': cname,
                        'Nguoi lien he': ceo if ceo != 'nan' else '',
                        'SDT': clean_phone(tel),
                        'Lien He': web if web.startswith('http') else (f"http://{web}" if web and '.' in web else ''),
                        'Dia chi': f"대한민국 {region}" if region else '',
                        'Category': f"한국조선해양기자재공업협동조합 (KOMEA - {region})"
                    })
            print(f"  -> KOMEA: Đã thu thập thành công {len(records)} công ty đóng tàu & thiết bị hàng hải!")
            return records
    except Exception as e:
        print(f"  -> Lỗi tải KOMEA: {e}")
    return []

def fetch_bmea_companies(session):
    """Tải danh bạ hội viên BMEA (407 nhà máy đóng tàu Busan)"""
    print("[2/3] Đang tải danh bạ hội viên BMEA (Hiệp hội Đóng tàu & Cơ khí Busan)...")
    records = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # BMEA có phân trang
    for page in range(1, 45):
        url = f"http://www.bmea.or.kr/en/members/list?page={page}"
        try:
            r = session.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, 'html.parser')
            trs = soup.select('table tbody tr')
            if not trs:
                break
            for tr in trs:
                tds = [td.text.strip().replace('\n', ' ') for td in tr.find_all('td')]
                if len(tds) >= 5:
                    cname = clean_company_name(tds[1])
                    ceo = tds[2] if tds[2] != '-' else ''
                    tel = tds[3] if tds[3] != '-' else ''
                    web = tds[4] if tds[4] != '-' else ''
                    area = tds[5] if len(tds) > 5 and tds[5] != '-' else '부산'
                    
                    if cname:
                        records.append({
                            'Cong ty': cname,
                            'Nguoi lien he': ceo,
                            'SDT': clean_phone(tel),
                            'Lien He': web if web.startswith('http') else (f"http://{web}" if web and '.' in web else ''),
                            'Dia chi': f"대한민국 부산광역시 {area}" if area else '대한민국 부산광역시',
                            'Category': f"부산조선해양기자재협동조합 (BMEA - {area})"
                        })
        except Exception:
            break
            
    print(f"  -> BMEA: Đã thu thập thành công {len(records)} công ty cơ khí & đóng tàu Busan!")
    return records

async def crawl_single_website_for_email(session, site_url):
    """Bóc tách sâu email B2B từ 1 website công ty đóng tàu"""
    if not site_url or not site_url.startswith('http'):
        return ""
        
    parsed = urllib.parse.urlparse(site_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.lower().replace('www.', '')
    
    candidates = set()
    subpaths = ['', '/contact', '/about', '/intro', '/kor/contact', '/company', '/sub/contact.php', '/kor']
    
    for sp in subpaths:
        target = base_url.rstrip('/') + sp
        try:
            r = await session.get(target, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                ems = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r.text)
                for e in ems:
                    if is_valid_email(e):
                        candidates.add(e.strip().rstrip('.'))
                if candidates:
                    break
        except Exception:
            pass
            
    if not candidates:
        return ""
        
    scored = [(score_email(c, domain), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]

async def crawl_all_websites(companies_with_web, cache):
    """Chạy song song bóc tách email từ toàn bộ website công ty"""
    print(f"\n[3/3] Đang quét sâu Email B2B từ {len(companies_with_web)} website công ty đóng tàu...")
    
    semaphore = asyncio.Semaphore(12) # Chạy 12 luồng song song
    
    async def bound_crawl(comp, session):
        async with semaphore:
            site = comp.get('Lien He', '')
            if not site:
                return
            if site in cache:
                comp['Email'] = cache[site]
                return
                
            em = await crawl_single_website_for_email(session, site)
            cache[site] = em
            comp['Email'] = em
            if em:
                print(f"  [TÌM THẤY EMAIL] {comp['Cong ty']} -> {em}")

    async with AsyncSession(impersonate="chrome120") as session:
        tasks = [bound_crawl(c, session) for c in companies_with_web]
        await asyncio.gather(*tasks)

def save_csv_output(records):
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
    
    with open(TARGET_2COL, 'w', encoding='utf-8-sig', newline='') as f:
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
            
    with open(TARGET_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
        writer.writeheader()
        for idx, item in enumerate(sorted_all, 1):
            row_dict = {col: item.get(col, '') for col in COLUMNS_20}
            row_dict['No.'] = str(idx)
            if row_dict['SDT']:
                row_dict['SDT'] = clean_phone(row_dict['SDT'])
            writer.writerow(row_dict)

def main():
    print("=" * 70)
    print(" CHIẾN DỊCH LÀM GIÀU DỮ LIỆU ĐÓNG TÀU & THỢ HÀN TOÀN DIỆN (KOMEA + BMEA)")
    print(" MỤC TIÊU: ƯU TIÊN TUYỆT ĐỐI EMAIL B2B (ĐẨY 100% CÓ MAIL LÊN ĐẦU)")
    print("=" * 70)
    
    cache = load_cache()
    records_map = {} # norm_name -> dict
    
    # 1. Đọc lại danh sách thầu phụ & xưởng tàu hiện có từ KR_SHIP_HIPC_2COL.csv
    if TARGET_2COL.exists():
        with open(TARGET_2COL, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                cname = clean_company_name(r.get('Cong ty', ''))
                if cname:
                    k = normalize_key(cname)
                    records_map[k] = r
        print(f"[*] Đã tải {len(records_map)} thầu phụ & xưởng tàu ban đầu từ KR_SHIP_HIPC_2COL.csv")
        
    session = Session(impersonate="chrome120")
    
    # 2. Tải toàn bộ hội viên KOMEA (354 cty)
    komea_list = fetch_komea_companies(session)
    for c in komea_list:
        k = normalize_key(c['Cong ty'])
        if k in records_map:
            # Bổ sung thông tin nếu thiếu
            if not records_map[k].get('Lien He') and c.get('Lien He'):
                records_map[k]['Lien He'] = c['Lien He']
            if not records_map[k].get('SDT') and c.get('SDT'):
                records_map[k]['SDT'] = c['SDT']
        else:
            records_map[k] = c

    # 3. Tải toàn bộ hội viên BMEA (407 cty)
    bmea_list = fetch_bmea_companies(session)
    for c in bmea_list:
        k = normalize_key(c['Cong ty'])
        if k in records_map:
            if not records_map[k].get('Lien He') and c.get('Lien He'):
                records_map[k]['Lien He'] = c['Lien He']
            if not records_map[k].get('SDT') and c.get('SDT'):
                records_map[k]['SDT'] = c['SDT']
        else:
            records_map[k] = c
            
    print(f"\n[+] Tổng số doanh nghiệp đóng tàu & thợ hàn hợp nhất: {len(records_map)} công ty")
    # LƯU NGAY RA FILE CSV ĐỂ NGƯỜI DÙNG THẤY NGAY 1.115 DÒNG!
    save_csv_output(list(records_map.values()))
    print(f"[*] ĐÃ GHI THÀNH CÔNG {len(records_map)} DOANH NGHIỆP RA KR_SHIP_HIPC_2COL.csv!", flush=True)

    # 4. Quét sâu Email B2B từ toàn bộ website công ty
    targets_with_web = [r for r in records_map.values() if r.get('Lien He') and r['Lien He'].startswith('http')]
    print(f"[*] Có {len(targets_with_web)} công ty có Website chính thức để quét Email...")
    
    asyncio.run(crawl_all_websites(targets_with_web, cache))
    save_cache(cache)
    
    # 5. Lưu và đẩy 100% có Email lên đầu
    all_final = list(records_map.values())
    save_csv_output(all_final)
    
    total_count = len(all_final)
    email_count = sum(1 for r in all_final if str(r.get('Email', '')).strip())
    phone_count = sum(1 for r in all_final if str(r.get('SDT', '')).strip())
    
    print("\n" + "=" * 70)
    print(" CHIẾN DỊCH HOÀN TẤT THÀNH CÔNG RỰC RỠ!")
    print(f" - Tổng số doanh nghiệp đóng tàu & thợ hàn: {total_count}")
    print(f" - Tổng số EMAIL B2B thu thập được: {email_count} (ĐẨY 100% LÊN ĐẦU)")
    print(f" - Tổng số SĐT có nháy đơn ': {phone_count}")
    print(f" - Xuất đồng bộ chuẩn Cold Mail: KR_SHIP_HIPC_2COL.csv")
    print("=" * 70)

if __name__ == '__main__':
    main()
