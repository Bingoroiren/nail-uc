# -*- coding: utf-8 -*-
"""
Tool làm giàu dữ liệu (Data Enrichment) cho danh sách công ty Môi giới / Cung ứng nhân lực Đóng tàu Hàn Quốc
Input:  KR_AGCY_SHIP_0RAW.csv + knesa_ship_agencies_raw.csv
Output: KR_AGCY_SHIP_1ENR.csv (Đầy đủ SĐT, Địa chỉ, Website, Email)
        KR_AGCY_SHIP_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy email/SĐT lên đầu)

Cơ chế tra cứu đa tầng & so khớp kiềng 3 chân:
1. Nạp dữ liệu KNESA đã có sẵn SĐT di động trực tiếp 010- và địa chỉ chi tiết.
2. Tra cứu Daum/Kakao Search theo [Tên công ty] [Tên sếp] [Quận/Huyện] để bóc tách SĐT, địa chỉ và web.
3. Tra cứu Naver Blog / Cafe / Saramin / JobKorea để tìm Email tuyển dụng (@naver.com, @daum.net).
4. Lưu tăng dần (Incremental Auto-save) & Checkpoint Resume 100%.
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

# Cau hinh console Windows de flush ngay lap tuc
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "KR_AGCY_SHIP_0RAW.csv")
KNESA_CSV = str(ROOT_DIR / "crawlmail" / "knesa_ship_agencies_raw.csv")
OUTPUT_ENR_CSV = str(ROOT_DIR / "KR_AGCY_SHIP_1ENR.csv")
OUTPUT_COLD_CSV = str(ROOT_DIR / "KR_AGCY_SHIP_2COL.csv")
OUTPUT_FMT_CSV = str(ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv")
CHECKPOINT_JSON = str(ROOT_DIR / "crawlmail" / "checkpoint_kr_agcy_ship.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{2,64}@[A-Za-z0-9.-]{2,255}\.[A-Za-z]{2,10}\b')
PHONE_REGEX = re.compile(r'(?:010[-.\s]?\d{4}[-.\s]?\d{4}|0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4})')

IGNORE_EMAILS = [
    'sentry', 'wixpress', 'example.com', 'domain.com', 'yourcompany',
    'contentpartnership@axzcorp.com', 'help@daum.net', 'help@naver.com',
    'privacy@naver.com', 'webmaster@', 'ad@daum.net', 'support@daum.net',
    'customer@', 'noreply@', 'privacy@'
]

def clean_phone(p):
    if not p:
        return ""
    p = p.strip()
    digits = re.sub(r'[^\d]', '', p)
    if digits.startswith('82'):
        digits = '0' + digits[2:]
    if len(digits) >= 8:
        if digits.startswith('02'):
            fmt = f"{digits[:2]}-{digits[2:-4]}-{digits[-4:]}"
        elif digits.startswith('010'):
            fmt = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        elif len(digits) >= 10:
            fmt = f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
        else:
            fmt = digits
        return f"'{fmt}"
    return ""

def is_valid_korean_phone(p):
    digits = re.sub(r'[^\d]', '', p)
    if any(digits.startswith(prefix) for prefix in ['080', '070', '020', '050', '15', '16', '18', '0220', '0260', '0250']):
        return False
    # Di động 010 (11 số)
    if digits.startswith('010') and len(digits) == 11:
        return True
    # Cố định Seoul 02 (9 hoặc 10 số, số thứ 3 phải từ 2-8)
    if digits.startswith('02') and len(digits) in [9, 10] and digits[2] in '2345678':
        return True
    # Cố định các tỉnh (055, 052, 061, 051, 063...) độ dài 10 hoặc 11 số, số thứ 4 từ 2-9
    local_prefixes = ('055', '052', '061', '051', '063', '031', '032', '033', '041', '042', '043', '053', '054', '062', '064')
    if any(digits.startswith(pre) for pre in local_prefixes) and len(digits) in [10, 11] and digits[3] in '23456789':
        return True
    return False

def score_email_korean(email, company_name):
    if not email:
        return -1
    email = email.lower()
    if any(ig in email for ig in IGNORE_EMAILS):
        return -1
    score = 10
    if any(kw in email for kw in ['job', 'work', 'recruit', 'hr', 'ship', 'chosun', 'hire', 'insa']):
        score += 30
    if any(kw in email for kw in ['ceo', 'master', 'contact', 'info', 'office']):
        score += 20
    if email.endswith('@naver.com') or email.endswith('@daum.net') or email.endswith('@hanmail.net'):
        score += 15
    return score

def search_agency_online(cname, ceo, loc):
    result = {'phone': '', 'address': loc, 'website': '', 'email': ''}
    clean_name = re.sub(r'[\(（].*?[\)）]', '', cname).strip()
    
    # Truy vấn Daum / Kakao theo kiềng 3 chân
    query = f"{clean_name} {ceo} {loc}".strip()
    try:
        url = f"https://search.daum.net/search?q={urllib.parse.quote(query)}"
        r = requests.get(url, headers=HEADERS, impersonate='chrome120', timeout=8)
        if r.status_code == 200:
            text = r.text
            soup = BeautifulSoup(text, 'html.parser')
            
            phones = PHONE_REGEX.findall(text)
            valid_p = [p for p in phones if is_valid_korean_phone(p)]
            if valid_p:
                result['phone'] = valid_p[0]
                
            emails = EMAIL_REGEX.findall(text)
            clean_e = [e for e in emails if not any(ig in e.lower() for ig in IGNORE_EMAILS)]
            if clean_e:
                scored = sorted(clean_e, key=lambda e: score_email_korean(e, clean_name), reverse=True)
                result['email'] = scored[0]
                
            addr_elem = soup.select_one('.info_address, .txt_address, .desc_detail')
            if addr_elem:
                result['address'] = addr_elem.get_text().strip()
                
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(dom in href for dom in ['blog.naver.com', 'cafe.naver.com', 'saramin.co.kr', 'jobkorea.co.kr']) and 'daum' not in href:
                    result['website'] = href
                    break
    except Exception:
        pass
        
    # Nếu chưa có Email: Tìm tin tuyển dụng
    if not result['email']:
        try:
            q_recruit = f"{clean_name} {loc} 채용 이메일"
            url_nv = f"https://search.daum.net/search?q={urllib.parse.quote(q_recruit)}"
            r_nv = requests.get(url_nv, headers=HEADERS, impersonate='chrome120', timeout=8)
            if r_nv.status_code == 200:
                text_nv = r_nv.text
                if not result['phone']:
                    phones = PHONE_REGEX.findall(text_nv)
                    valid_p = [p for p in phones if is_valid_korean_phone(p)]
                    if valid_p:
                        result['phone'] = valid_p[0]
                emails = EMAIL_REGEX.findall(text_nv)
                clean_e = [e for e in emails if not any(ig in e.lower() for ig in IGNORE_EMAILS)]
                if clean_e:
                    scored = sorted(clean_e, key=lambda e: score_email_korean(e, clean_name), reverse=True)
                    result['email'] = scored[0]
        except Exception:
            pass
            
    return result

def save_incremental(rows):
    with_email = [r for r in rows if r.get('Email')]
    with_phone_only = [r for r in rows if r.get('SĐT') and not r.get('Email')]
    remaining = [r for r in rows if not r.get('SĐT') and not r.get('Email')]
    sorted_rows = with_email + with_phone_only + remaining
    
    for i, r in enumerate(sorted_rows, 1):
        r['No.'] = str(i)
        
    for path in [OUTPUT_ENR_CSV, OUTPUT_COLD_CSV, OUTPUT_FMT_CSV]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
                writer.writeheader()
                writer.writerows(sorted_rows)
        except Exception:
            pass

def main():
    print("=" * 80)
    print("QUY TRINH LAM GIAU DATA: CÔNG TY MÔI GIỚI / PHÁI CỬ NHÂN LỰC ĐÓNG TÀU HÀN QUỐC")
    print(f"File nguồn: {INPUT_CSV}")
    print(f"File đầu ra: {OUTPUT_COLD_CSV}")
    print("=" * 80, flush=True)

    # 1. Đọc dữ liệu KNESA đã có SĐT di động
    knesa_map = {}
    if os.path.exists(KNESA_CSV):
        with open(KNESA_CSV, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                cname_clean = re.sub(r'[\(（].*?[\)）]', '', r['company']).strip()
                knesa_map[cname_clean] = r
                if r.get('ceo'):
                    knesa_map[r['ceo'].strip()] = r
        print(f"[*] Đã nạp {len(knesa_map)} bản ghi từ Hiệp hội KNESA.", flush=True)

    # 2. Đọc tệp MOEL mục tiêu
    with open(INPUT_CSV, encoding='utf-8-sig') as f:
        target_rows = [r for r in csv.DictReader(f) if '변경' not in r.get('Tên công ty (사업장명)', '') and len(r.get('Tên công ty (사업장명)', '')) >= 2]
    total_targets = len(target_rows)
    print(f"[*] Tổng số công ty môi giới cần làm giàu: {total_targets}", flush=True)

    # 3. Nạp Checkpoint
    checkpoint_data = {}
    if os.path.exists(CHECKPOINT_JSON):
        try:
            with open(CHECKPOINT_JSON, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            print(f"[*] Đã nạp Checkpoint: {len(checkpoint_data)} công ty đã xử lý.", flush=True)
        except Exception:
            pass

    processed_rows = []

    for idx, r in enumerate(target_rows, 1):
        cname = r.get('Tên công ty (사업장명)', '').strip()
        ceo = r.get('Người đại diện (대표자)', '').strip()
        loc = r.get('Địa chỉ khu vực (소재지)', '').strip()
        hub = r.get('Cụm xưởng tàu mục tiêu', '').strip()
        clean_cname = re.sub(r'[\(（].*?[\)）]', '', cname).strip()
        key = f"{cname}_{ceo}_{loc}"

        if key in checkpoint_data:
            info = checkpoint_data[key]
        else:
            # Kiểm tra KNESA trước
            k_match = knesa_map.get(clean_cname) or (knesa_map.get(ceo) if ceo else None)
            k_phone = k_match.get('mobile') or k_match.get('tel') if k_match else ""
            k_addr = k_match.get('address') if k_match else loc

            # Tra cứu trực tuyến
            print(f"[{idx}/{total_targets}] Tra cứu: {cname} ({ceo} - {loc})...", end='', flush=True)
            info = search_agency_online(cname, ceo, loc)
            
            # Ưu tiên SĐT di động KNESA nếu online không có hoặc KNESA chuẩn hơn
            if k_phone and not info['phone']:
                info['phone'] = k_phone
            if k_addr and len(k_addr) > len(info['address']):
                info['address'] = k_addr

            checkpoint_data[key] = info
            p_display = info['phone'] if info['phone'] else '---'
            e_display = info['email'] if info['email'] else '---'
            print(f" => SĐT: {p_display} | Mail: {e_display}", flush=True)

            if idx % 5 == 0:
                with open(CHECKPOINT_JSON, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
                save_incremental(processed_rows)

            time.sleep(0.4)

        row_item = {
            'No.': str(idx),
            'Công ty': cname,
            'Chức danh': 'Đại diện pháp luật',
            'Người liên hệ': ceo,
            'SĐT': clean_phone(info.get('phone', '')),
            'Liên Hệ': info.get('website', ''),
            'Email': info.get('email', ''),
            'Liên Hệ mail': '',
            'Địa chỉ': info.get('address', loc),
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': f"Môi giới nhân lực - {hub}"
        }
        processed_rows.append(row_item)

    # Lưu cuối cùng
    with open(CHECKPOINT_JSON, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    save_incremental(processed_rows)

    print("\n" + "=" * 80)
    print("HOÀN TẤT LÀM GIÀU DỮ LIỆU ĐÓNG TÀU HÀN QUỐC!")
    print(f"Tổng số công ty: {len(processed_rows)}")
    print(f"Số công ty có Email: {sum(1 for r in processed_rows if r.get('Email'))}")
    print(f"Số công ty có SĐT: {sum(1 for r in processed_rows if r.get('SĐT'))}")
    print(f"Tệp đích: {OUTPUT_COLD_CSV}")
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
