# -*- coding: utf-8 -*-
"""
Hệ thống cào và bóc tách Email & SĐT các đơn vị Môi giới, Tuyển dụng và Cung ứng Nhân lực Đóng tàu Hàn Quốc
(E-7-3, E-9, Thợ hàn, Thợ lắp ráp, Thợ ống, Thầu phụ xưởng tàu) từ Cổng thông tin Tuyển dụng Naver.

Đặc điểm dữ liệu đầu ra:
- 100% ĐẦY ĐỦ EMAIL B2B (blogId@naver.com hoặc email doanh nghiệp riêng trong bài đăng).
- 100% SĐT có dấu nháy đơn '.
- Chuẩn Cold Mail 20 cột COLDMAIL_FIELDNAMES.
- Đẩy 100% công ty có Email và SĐT lên đầu tệp.
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

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = str(ROOT_DIR / "KR_AGCY_RECR_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_ship_recruiters.json")

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(?:01[016789][\-\s]?\d{3,4}[\-\s]?\d{4}|0\d{1,2}[\-\s]?\d{3,4}[\-\s]?\d{4})')

GARBAGE_EMAILS = [
    'naver.com/s', 'naver.com/favicon', 'schema.org', 'w3.org', 'daumcorp.com',
    'example.com', 'domain.com', 'yourcompany.com', 'sentry.io', 'wixpress.com',
    'blog.me', 'help@', 'support@', 'privacy@', 'admin@', 'webmaster@'
]

HEADERS = {
    'Referer': 'https://section.blog.naver.com/Search/Post.naver',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

KEYWORDS = [
    "E73비자 조선용접공",
    "E7비자 조선소 채용",
    "조선소 용접공 외국인 채용",
    "조선소 사내협력사 채용",
    "외국인 근로자 E7 조선소",
    "거제 조선소 인력 채용",
    "울산 현대중공업 협력사 채용",
    "영암 삼호중공업 인력 채용",
    "조선소 배관공 구인",
    "조선소 취부공 구인",
    "조선소 용접사 구인",
    "조선소 취업소개소",
    "조선소 인력사무소",
    "조선소 도급업체 채용",
    "조선소 아웃소싱 채용",
    "한화오션 협력사 채용",
    "삼성중공업 협력사 채용",
    "조선소 E-7 비자 행정사",
    "조선소 외국인 인력 공급",
    "조선소 용접 취업 이력서",
    "거제 통영 조선소 인력",
    "울산 조선소 취업",
    "대불산단 조선소 인력",
    "조선소 취업사무실",
    "조선소 기능인력 E7-3"
]

def clean_phone(p):
    if not p:
        return ""
    digits = re.sub(r'[^\d]', '', str(p))
    if any(digits.startswith(pre) for pre in ['080', '070', '15', '16', '18']):
        return ""
    if digits.startswith('010') and len(digits) == 11:
        fmt = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    elif digits.startswith('02') and len(digits) in [9, 10]:
        fmt = f"{digits[:2]}-{digits[2:-4]}-{digits[-4:]}"
    elif len(digits) in [10, 11]:
        fmt = f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    else:
        fmt = digits
    return f"'{fmt}" if fmt else ""

def is_valid_email(e):
    if not e:
        return False
    e = e.strip().lower()
    if len(e) < 6 or '@' not in e or '.' not in e:
        return False
    if any(g in e for g in GARBAGE_EMAILS):
        return False
    if re.search(r'\.(png|jpg|jpeg|gif|webp|svg|css|js)$', e):
        return False
    return True

def main():
    print("=" * 80)
    print("CÀO DỮ LIỆU EMAIL & SĐT MÔI GIỚI / TUYỂN DỤNG NHÂN LỰC ĐÓNG TÀU HÀN QUỐC")
    print("=" * 80)

    # Đọc cache cũ nếu có
    recruiters = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                recruiters = json.load(f)
            print(f"[*] Đã nạp cache cũ: {len(recruiters)} đơn vị tuyển dụng.")
        except Exception:
            pass

    total_scanned = 0

    for kw_idx, kw in enumerate(KEYWORDS, 1):
        print(f"\n[{kw_idx}/{len(KEYWORDS)}] Đang quét từ khóa: '{kw}'...")
        for page in range(1, 6): # Quét 5 trang đầu (50 bài đăng mỗi từ khóa)
            url = f"https://section.blog.naver.com/ajax/SearchList.naver?countPerPage=10&currentPage={page}&keyword={urllib.parse.quote(kw)}&type=post"
            try:
                r = requests.get(url, headers=HEADERS, impersonate='chrome120', timeout=8)
                if r.status_code != 200:
                    continue
                raw_text = r.text
                j_idx = raw_text.find('{')
                if j_idx == -1:
                    continue
                data = json.loads(raw_text[j_idx:])
                posts = data.get('result', {}).get('searchList', [])
                if not posts:
                    break

                for p in posts:
                    total_scanned += 1
                    post_url = p.get('postUrl', '')
                    if not post_url or 'blog.naver.com' not in post_url:
                        continue

                    parts = post_url.rstrip('/').split('/')
                    if len(parts) < 2:
                        continue
                    blog_id = parts[-2]
                    log_no = parts[-1]

                    # Bỏ qua các blog id hệ thống
                    if blog_id in ['naver', 'blog', 'admin', 'post', 'help']:
                        continue

                    author = p.get('blogName', '').strip()
                    title = BeautifulSoup(p.get('title', ''), 'html.parser').get_text().strip()
                    contents = BeautifulSoup(p.get('contents', ''), 'html.parser').get_text().strip()

                    # Tìm email trong snippet/title
                    full_snip = f"{title} {contents}"
                    snip_emails = EMAIL_REGEX.findall(full_snip)
                    valid_custom = [e.lower() for e in snip_emails if is_valid_email(e)]

                    # Ưu tiên email đích danh trong bài, nếu không có thì lấy blogId@naver.com
                    target_email = valid_custom[0] if valid_custom else f"{blog_id}@naver.com"

                    # Bóc tách SĐT từ snippet
                    snip_phones = PHONE_REGEX.findall(full_snip)
                    clean_phones = [clean_phone(ph) for ph in snip_phones if clean_phone(ph)]
                    primary_phone = clean_phones[0] if clean_phones else ""

                    # Bóc tách địa bàn / khu vực
                    region = "Hàn Quốc"
                    for r_name in ['거제', '울산', '영암', '목포', '창원', '진해', '통영', '부산', '군산', '인천', '평택', '화성', '서울', '경기']:
                        if r_name in full_snip:
                            region = r_name
                            break

                    # Nếu đơn vị chưa có hoặc đơn vị cũ chưa có SĐT mà bản ghi này có SĐT
                    if target_email not in recruiters:
                        recruiters[target_email] = {
                            'company': author if author else f"Văn phòng tuyển dụng ({blog_id})",
                            'ceo': '',
                            'phone': primary_phone,
                            'website': post_url,
                            'email': target_email,
                            'address': f"Khu vực {region}, Hàn Quốc",
                            'title': title[:80],
                            'category': f"Tuyển dụng & Môi giới nhân lực đóng tàu ({kw})"
                        }
                        print(f"  [+] {author} ({region}) -> Mail: {target_email} | SĐT: {primary_phone}", flush=True)
                    else:
                        if not recruiters[target_email]['phone'] and primary_phone:
                            recruiters[target_email]['phone'] = primary_phone

                time.sleep(0.3)
            except Exception as e:
                pass

        # Lưu checkpoint sau mỗi từ khóa
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(recruiters, f, ensure_ascii=False, indent=2)

    # Xuất ra file chuẩn Cold Mail 20 cột
    rows = []
    for item in recruiters.values():
        row = {
            'No.': '',
            'Công ty': item['company'],
            'Chức danh': 'Trưởng ban tuyển dụng / Đại diện pháp luật',
            'Người liên hệ': item['ceo'],
            'SĐT': item['phone'],
            'Liên Hệ': item['website'],
            'Email': item['email'],
            'Liên Hệ mail': '',
            'Địa chỉ': item['address'],
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
            'Category': item['category']
        }
        rows.append(row)

    # Đẩy các đơn vị vừa có Email vừa có SĐT lên đầu tiên
    with_both = [r for r in rows if r.get('Email') and r.get('SĐT')]
    with_email_only = [r for r in rows if r.get('Email') and not r.get('SĐT')]
    final_rows = with_both + with_email_only

    for idx, r in enumerate(final_rows, 1):
        r['No.'] = str(idx)

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    print("\n" + "=" * 80)
    print(f"HOÀN TẤT THU THẬP EMAIL TUYỂN DỤNG & MÔI GIỚI ĐÓNG TÀU!")
    print(f"  • Tổng số đơn vị có 100% EMAIL: {len(final_rows)}")
    print(f"  • Số đơn vị có CẢ EMAIL VÀ SĐT: {len(with_both)}")
    print(f"  • Tệp xuất: {OUTPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
