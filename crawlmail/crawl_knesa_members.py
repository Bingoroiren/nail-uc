# -*- coding: utf-8 -*-
"""
Crawler bóc tách dữ liệu chính thống từ Hiệp hội Dịch vụ Việc làm Quốc gia Hàn Quốc (KNESA - knesa.org)
Bao gồm các chi hội tại các thủ phủ xưởng tàu:
- Gyeongnam (경남지회: 거제, 통영, 창원...)
- Ulsan (울산지회: 현대중공업, 현대미포...)
- Jeonnam (전남지회: 영암, 목포, 대불산단...)
- Busan (부산지회: 영도, 사하, 강서...)
- Jeonbuk (전북지회: 군산...)

Dữ liệu bóc tách được:
- Tên công ty (사업장명)
- Tên giám đốc / đại diện (대표자)
- SĐT di động trực tiếp (휴대폰 010-...)
- SĐT cố định công ty (회사전화번호)
- Địa chỉ chi tiết (회사주소)
- Ngành nghề chuyên môn (직종구분 / 전문분야)
"""

import sys
import os
import re
import csv
import json
import time
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = str(ROOT_DIR / "crawlmail" / "knesa_ship_agencies_raw.csv")

BRANCHES = [
    ('gyeongnam', 'Gyeongnam (거제/통영/창원)'),
    ('ulsan', 'Ulsan (울산)'),
    ('jeonnam', 'Jeonnam (영암/목포)'),
    ('busan', 'Busan (부산)'),
    ('jeonbuk', 'Jeonbuk (군산)')
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

def clean_phone_format(p):
    if not p:
        return ""
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

def crawl_branch(branch_code, branch_name):
    base_url = f"http://{branch_code}.knesa.org"
    print(f"\n[*] Đang cào dữ liệu Chi hội: {branch_name} ({base_url})...")
    
    records = []
    page = 1
    
    while True:
        list_url = f"{base_url}/myboard/member?page={page}"
        try:
            r = requests.get(list_url, headers=HEADERS, impersonate='chrome120', timeout=15)
            if r.status_code != 200:
                break
                
            soup = BeautifulSoup(r.text, 'html.parser')
            detail_links = soup.find_all('a', href=lambda h: h and 'myboard_read.htm' in h)
            
            # Khử trùng lặp link trên trang
            seen_hrefs = set()
            page_links = []
            for a in detail_links:
                href = a['href']
                if href not in seen_hrefs:
                    seen_hrefs.add(href)
                    page_links.append((href, a.get_text().strip()))
                    
            if not page_links:
                break
                
            print(f"  -> Trang {page}: Tìm thấy {len(page_links)} đơn vị thành viên.")
            
            for href, anchor_text in page_links:
                detail_url = base_url + href if href.startswith('/') else f"{base_url}/{href}"
                try:
                    r_det = requests.get(detail_url, headers=HEADERS, impersonate='chrome120', timeout=10)
                    soup_det = BeautifulSoup(r_det.text, 'html.parser')
                    
                    data = {
                        'branch': branch_name,
                        'company': '',
                        'ceo': '',
                        'mobile': '',
                        'tel': '',
                        'address': '',
                        'category': '',
                        'detail_url': detail_url
                    }
                    
                    # Bóc tách tên công ty từ tiêu đề hoặc thẻ h / b
                    title_elem = soup_det.select_one('.board_title, .tit, h3, .view_title, strong')
                    if title_elem:
                        data['company'] = title_elem.get_text().strip()
                    if not data['company'] and anchor_text:
                        data['company'] = anchor_text.split('\n')[0].strip()
                        
                    # Bóc tách bảng thuộc tính key: value
                    for tr in soup_det.find_all('tr'):
                        text_row = tr.get_text(separator='|').strip()
                        parts = [p.strip() for p in text_row.split('|') if p.strip()]
                        for i in range(len(parts)-1):
                            k = parts[i]
                            v = parts[i+1]
                            if '대표자' in k: data['ceo'] = v
                            elif '휴대폰' in k: data['mobile'] = clean_phone_format(v)
                            elif '회사전화' in k or '전화번호' in k: data['tel'] = clean_phone_format(v)
                            elif '회사주소' in k or '주소' in k: data['address'] = v
                            elif '직종' in k or '분야' in k: data['category'] = v
                            
                    if data['company']:
                        records.append(data)
                        
                except Exception as e:
                    pass
                time.sleep(0.1)
                
            page += 1
            if page > 10: # Giới hạn an toàn số trang mỗi tỉnh
                break
                
        except Exception as e:
            print(f"[-] Lỗi cào trang {page}: {e}")
            break
            
    print(f"[+] Hoàn tất chi hội {branch_name}: {len(records)} công ty.")
    return records

def main():
    print("=" * 80)
    print("BÓC TÁCH DỮ LIỆU HIỆP HỘI VIỆC LÀM KOREA (KNESA)")
    print("Cụm đại bản doanh đóng tàu: Gyeongnam, Ulsan, Jeonnam, Busan, Jeonbuk")
    print("=" * 80)
    
    all_members = []
    for b_code, b_name in BRANCHES:
        res = crawl_branch(b_code, b_name)
        all_members.extend(res)
        
    print(f"\n[*] TỔNG SỐ HỘI VIÊN BÓC TÁCH ĐƯỢC: {len(all_members)}")
    
    fieldnames = ['branch', 'company', 'ceo', 'mobile', 'tel', 'address', 'category', 'detail_url']
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_members)
        
    print(f"[OK] Đã lưu dữ liệu gốc vào: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
