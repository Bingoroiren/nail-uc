# -*- coding: utf-8 -*-
"""
Hệ thống cào và làm giàu dữ liệu Thầu phụ & Thợ hàn đóng tàu Hàn Quốc từ các cổng tuyển dụng (Saramin, JobKorea, Web Footprint)
Tập trung tối đa hóa EMAIL B2B (Ưu tiên email hơn SĐT theo chỉ đạo của USER).

Quy trình:
1. Đọc tệp KR_SHIP_HIPC_2COL.csv hiện có (183 nhà thầu phụ HD Hyundai Heavy & KOSIC).
2. Quét chiến dịch tuyển dụng thợ hàn & thầu phụ xưởng tàu trên Saramin:
   - Các từ khóa: '선박 용접', '조선소 용접', '사내협력사 용접', '선박 배관', '선박 취부', '선박 도장', '조선 협력사'
   - Truy vấn view-detail bóc tách email trực tiếp nhận CV/hồ sơ (recruit@, hr@, @domain).
3. Tra cứu footprint tuyển dụng & website cho các công ty chưa có email.
4. Chấm điểm email B2B chuẩn xác, loại bỏ 100% mail rác.
5. Hợp nhất, khử trùng lặp theo tên công ty.
6. ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU DANH SÁCH.
7. Chuẩn hóa 20 cột Cold Mail UTF-8 with BOM (utf-8-sig), SĐT có nháy đơn '.
"""

import os
import sys
import re
import csv
import json
import time
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_2COL = ROOT_DIR / "KR_SHIP_HIPC_2COL.csv"
TARGET_1ENR = ROOT_DIR / "KR_SHIP_HIPC_1ENR.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_hipc_recruitment.json"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

SEARCH_KEYWORDS = [
    "조선소 용접",       # Hàn xưởng đóng tàu
    "사내협력사 용접",   # Hàn thầu phụ trong xưởng
    "선박 용접",         # Hàn tàu biển
    "선박 배관",         # Hàn ống tàu
    "선박 취부",         # Thợ gá lắp kết cấu vỏ tàu
    "조선 협력사",       # Nhà thầu phụ đóng tàu
    "선박 도장"          # Sơn chống rỉ tàu biển
]

GARBAGE_PATTERNS = [
    'react-dom@', 'player-component@', 'core-js@', '@gabia.com',
    '@wixpress.com', '@sentry.io', 'example.com', 'domain.com',
    'someone@', 'youremail@', 'yourname@', 'name@domain',
    'user@domain', 'test@', 'email@email', '@whois', 'sample@',
    'bootstrap@', 'jquery@', 'webpack@', '@2x.png', '@3x.png',
    'saramin@', 'jobkorea@', 'worknet@', 'work24@', 'help@saramin'
]

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'[\r\n\t]+', ' ', str(name)).strip()
    return re.sub(r'\s+', ' ', name)

def normalize_key(name):
    n = clean_company_name(name).lower()
    for drop in ['(주)', '㈜', '주식회사', '(유)', '유한회사', '사내협력사', '협동조합']:
        n = n.replace(drop, '')
    return re.sub(r'[^a-zA-Z0-9가-힣]', '', n).strip()

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\r', '').replace('\n', '').strip()
    if not p_str or p_str.lower() in ['none', 'nan']:
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
    # Không lấy đuôi file ảnh
    if re.search(r'\.(png|jpg|jpeg|gif|webp|svg|css|js)$', em):
        return False
    return True

def score_email(em):
    em = em.lower()
    sc = 10
    # Ưu tiên tuyển dụng, nhân sự
    if any(p in em for p in ['recruit', 'hr', 'job', 'career', 'insa', 'work', 'chayong']):
        sc += 50
    # Ưu tiên giám đốc / lãnh đạo
    elif any(p in em for p in ['ceo', 'director', 'manager', 'boss', 'master']):
        sc += 40
    # Cổng thông tin chính thức
    elif any(p in em for p in ['info', 'contact', 'office', 'help', 'admin']):
        sc += 30
    
    # Mail công ty vs Mail miễn phí
    if any(em.endswith(f) for f in ['@gmail.com', '@naver.com', '@daum.net', '@hanmail.net']):
        sc += 10
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

def extract_emails_from_text(text):
    if not text:
        return []
    raw = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    valid = [e.strip().rstrip('.') for e in set(raw) if is_valid_email(e)]
    valid.sort(key=score_email, reverse=True)
    return valid

def extract_phones_from_text(text):
    if not text:
        return []
    raw = re.findall(r'(?:0\d{1,2}[\-\s]?\d{3,4}[\-\s]?\d{4})', text)
    cleaned = []
    for p in raw:
        cp = clean_phone(p)
        if cp and cp not in cleaned:
            cleaned.append(cp)
    return cleaned

def fetch_saramin_job_emails(session, rec_idx, headers):
    """Bóc tách email và SĐT từ view-detail của Saramin"""
    detail_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx}"
    req_headers = dict(headers)
    req_headers['Referer'] = f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}"
    try:
        r = session.get(detail_url, headers=req_headers, timeout=8)
        if r.status_code == 200:
            emails = extract_emails_from_text(r.text)
            phones = extract_phones_from_text(r.text)
            return emails, phones
    except Exception:
        pass
    return [], []

def search_web_footprint_email(session, comp_name, headers):
    """Tìm email tuyển dụng trên web qua query footprint"""
    clean = clean_company_name(comp_name)
    clean = re.sub(r'[\(\)주식회사]', '', clean).strip()
    if len(clean) < 2:
        return []
    
    query = f'"{clean}" (조선 OR 용접 OR 협력사) (채용 OR 입사지원) @'
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        r = session.get(url, headers=headers, impersonate="chrome120", timeout=6)
        if r.status_code == 200:
            return extract_emails_from_text(r.text)
    except Exception:
        pass
    return []

def save_csv_datasets(all_records):
    """Lưu trữ dữ liệu chuẩn 20 cột, đẩy 100% công ty có Email lên đầu"""
    # Phân loại: có email vs không có email
    with_email = []
    without_email = []
    
    for r in all_records:
        em = str(r.get('Email', '')).strip()
        if em and '@' in em:
            with_email.append(r)
        else:
            without_email.append(r)
            
    sorted_records = with_email + without_email
    
    # Ghi KR_SHIP_HIPC_2COL.csv
    with open(TARGET_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
        writer.writeheader()
        for idx, item in enumerate(sorted_records, 1):
            row_dict = {col: item.get(col, '') for col in COLUMNS_20}
            row_dict['No.'] = str(idx)
            # Đảm bảo SĐT luôn có nháy đơn
            if row_dict['SDT']:
                row_dict['SDT'] = clean_phone(row_dict['SDT'])
            writer.writerow(row_dict)
            
    # Ghi KR_SHIP_HIPC_1ENR.csv
    with open(TARGET_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
        writer.writeheader()
        for idx, item in enumerate(sorted_records, 1):
            row_dict = {col: item.get(col, '') for col in COLUMNS_20}
            row_dict['No.'] = str(idx)
            if row_dict['SDT']:
                row_dict['SDT'] = clean_phone(row_dict['SDT'])
            writer.writerow(row_dict)

def main():
    print("=" * 70)
    print(" CHIẾN DỊCH CÀO & LÀM GIÀU EMAIL THẦU PHỤ & THỢ HÀN ĐÓNG TÀU HÀN QUỐC")
    print(" MỤC TIÊU: ƯU TIÊN TỐI ĐA EMAIL B2B (ĐẨY 100% CÓ MAIL LÊN ĐẦU)")
    print("=" * 70)
    
    cache = load_cache()
    records_map = {} # norm_name -> dict
    
    # 1. Đọc dữ liệu hiện có từ KR_SHIP_HIPC_2COL.csv
    if TARGET_2COL.exists():
        with open(TARGET_2COL, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                cname = clean_company_name(r.get('Cong ty', ''))
                if cname:
                    k = normalize_key(cname)
                    records_map[k] = r
        print(f"[*] Đã tải {len(records_map)} doanh nghiệp ban đầu từ KR_SHIP_HIPC_2COL.csv")
    
    session = requests.Session(impersonate="chrome120")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    # 2. Cào các tin tuyển dụng thợ hàn & thầu phụ từ Saramin
    total_new_jobs = 0
    total_emails_found = 0
    
    print("\n[+] BƯỚC 1: Quét tin tuyển dụng thợ hàn / thầu phụ trên Saramin...")
    for kw in SEARCH_KEYWORDS:
        print(f"\n---> Từ khóa tuyển dụng: [{kw}]")
        for page in range(1, 4): # Quét 3 trang đầu mỗi từ khóa
            encoded_kw = urllib.parse.quote(kw)
            search_url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={encoded_kw}&recruitPage={page}"
            try:
                r = session.get(search_url, headers=headers, timeout=10)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.select('div.item_recruit')
                if not items:
                    break
                
                print(f"  Trang {page}: Tìm thấy {len(items)} tin tuyển dụng")
                for it_idx, it in enumerate(items, 1):
                    corp_a = it.select_one('strong.corp_name a') or it.select_one('strong.corp_name')
                    if not corp_a:
                        continue
                    corp_name = clean_company_name(corp_a.text)
                    if not corp_name:
                        continue
                    
                    tit_a = it.select_one('h2.job_tit a')
                    job_title = tit_a.text.strip() if tit_a else ""
                    job_href = "https://www.saramin.co.kr" + tit_a.get("href") if tit_a and tit_a.get("href") else ""
                    
                    conditions = [s.text.strip() for s in it.select("div.job_condition span")]
                    loc_text = conditions[0] if conditions else ""
                    
                    date_el = it.select_one("span.date")
                    due_date = date_el.text.strip() if date_el else ""
                    
                    k = normalize_key(corp_name)
                    
                    # Trích xuất rec_idx để bóc tách view-detail
                    rec_idx = ""
                    m = re.search(r'rec_idx=(\d+)', job_href)
                    if m:
                        rec_idx = m.group(1)
                        
                    emails = []
                    phones = []
                    
                    # Kiểm tra cache
                    if rec_idx and rec_idx in cache:
                        emails = cache[rec_idx].get('emails', [])
                        phones = cache[rec_idx].get('phones', [])
                    elif rec_idx:
                        emails, phones = fetch_saramin_job_emails(session, rec_idx, headers)
                        cache[rec_idx] = {'emails': emails, 'phones': phones, 'corp': corp_name}
                        time.sleep(0.3)
                        
                    best_email = emails[0] if emails else ""
                    best_phone = phones[0] if phones else ""
                    
                    if best_email:
                        total_emails_found += 1
                        print(f"    [MAIL TÌM THẤY] {corp_name}: {best_email}", flush=True)

                    # Nếu công ty đã có trong records_map
                    if k in records_map:
                        existing = records_map[k]
                        if not existing.get('Email') and best_email:
                            existing['Email'] = best_email
                            existing['Lien He mail'] = job_href
                        if not existing.get('SDT') and best_phone:
                            existing['SDT'] = best_phone
                        if not existing.get('Han tuyen'):
                            existing['Han tuyen'] = due_date
                        if not existing.get('Chuc danh'):
                            existing['Chuc danh'] = f"[Thợ hàn/kỹ thuật] {job_title}"
                    else:
                        # Thêm công ty mới đang tuyển thợ hàn đóng tàu
                        new_record = {
                            'No.': '',
                            'Cong ty': corp_name,
                            'Chuc danh': f"[Thợ hàn/kỹ thuật] {job_title}",
                            'Nguoi lien he': "Phòng Nhân Sự / Tuyển Dụng",
                            'SDT': best_phone,
                            'Lien He': job_href,
                            'Email': best_email,
                            'Lien He mail': job_href,
                            'Dia chi': loc_text,
                            'Luong': "Thỏa thuận theo bậc tay nghề E-7-3",
                            'Ngay dang': "2026-10-06",
                            'Han tuyen': due_date,
                            'Check gui': '',
                            'Last Subject': '',
                            'Last Body HTML': '',
                            'Trang thai Reply': '',
                            'Lan Follow-up': '',
                            'Ngay Follow-up gan nhat': '',
                            'Mailbox da dung': '',
                            'Category': f"Thầu phụ / Tuyển thợ hàn ({kw})"
                        }
                        records_map[k] = new_record
                        total_new_jobs += 1
                    
                    if it_idx % 5 == 0:
                        save_cache(cache)
                        save_csv_datasets(list(records_map.values()))
                
                # Lưu tăng dần sau mỗi trang
                save_cache(cache)
                save_csv_datasets(list(records_map.values()))
                time.sleep(0.5)
            except Exception as e:
                print(f"  Lỗi trang {page}: {e}")
                break

    # 3. Quét footprint cho các công ty thầu phụ trong danh sách mà chưa có Email
    print("\n[+] BƯỚC 2: Quét sâu email tuyển dụng cho các công ty thầu phụ còn thiếu mail...")
    missing_email_targets = [r for r in records_map.values() if not r.get('Email')]
    print(f"[*] Có {len(missing_email_targets)} công ty cần quét footprint bổ sung...")
    
    enriched_from_web = 0
    for idx, r in enumerate(missing_email_targets[:60], 1): # Quét 60 công ty ưu tiên
        cname = r.get('Cong ty', '')
        k = normalize_key(cname)
        if f"fp_{k}" in cache:
            found = cache[f"fp_{k}"]
        else:
            found = search_web_footprint_email(session, cname, headers)
            cache[f"fp_{k}"] = found
            time.sleep(0.6)
            
        if found:
            r['Email'] = found[0]
            enriched_from_web += 1
            print(f"  [{idx}] {cname} -> TÌM THẤY: {found[0]}")
            save_cache(cache)
            save_csv_datasets(list(records_map.values()))
        else:
            if idx % 10 == 0:
                print(f"  Đã quét {idx}/{min(60, len(missing_email_targets))} công ty...")

    # 4. Xuất kết quả tổng kết cuối cùng
    all_final = list(records_map.values())
    save_csv_datasets(all_final)
    
    total_final = len(all_final)
    final_emails = sum(1 for r in all_final if str(r.get('Email', '')).strip())
    final_phones = sum(1 for r in all_final if str(r.get('SDT', '')).strip())
    
    print("\n" + "=" * 70)
    print(" CHIẾN DỊCH HOÀN TẤT THÀNH CÔNG!")
    print(f" - Tổng số doanh nghiệp thầu phụ & tuyển dụng: {total_final}")
    print(f" - Tổng số EMAIL B2B thu thập được: {final_emails} (ƯU TIÊN 100% LÊN ĐẦU DANH SÁCH)")
    print(f" - Tổng số SĐT có nháy đơn: {final_phones}")
    print(f" - Tệp xuất chuẩn Cold Mail: KR_SHIP_HIPC_2COL.csv")
    print("=" * 70)

if __name__ == '__main__':
    main()
