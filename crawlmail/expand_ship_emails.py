# -*- coding: utf-8 -*-
"""
Hệ thống Mở rộng và Tối đa hóa EMAIL cho tệp chủ KR_AGCY_SHIP_2COL.csv
Cào thêm 25 bộ từ khóa chuyên sâu về tiếp nhận CV, thủ tục visa E-7-3 và cung ứng thợ hàn xưởng tàu.
Gộp thẳng vào KR_AGCY_SHIP_2COL.csv và đẩy toàn bộ lên đầu tệp.
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

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_2COL = str(ROOT_DIR / "KR_AGCY_SHIP_2COL.csv")
MASTER_1ENR = str(ROOT_DIR / "KR_AGCY_SHIP_1ENR.csv")
FMT_2COL = str(ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv")
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
    'blog.me', 'help@', 'support@', 'privacy@', 'admin@', 'webmaster@', 'info@naver.com'
]

HEADERS = {
    'Referer': 'https://section.blog.naver.com/Search/Post.naver',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

EXPAND_KEYWORDS = [
    "조선소 취업 이메일 접수",
    "조선소 협력사 이력서 접수",
    "조선소 용접공 이력서 접수",
    "거제 조선소 취업 이메일",
    "울산 조선소 취업 이메일",
    "영암 삼호중공업 취업 이메일",
    "E-7 비자 고용추천서 신청",
    "KOSHIPA 기량검증 대행",
    "외국인 근로자 E73 비자 행정사",
    "베트남 용접공 E7 비자",
    "외국인 기능인력 조선소 채용",
    "조선소 기량검증 대행",
    "선박제조 용접공 채용",
    "조선소 취부사 구인",
    "조선소 비계공 구인",
    "조선소 결선 구인",
    "조선업 전문 인력공급업체",
    "선박 임가공 사내협력사",
    "조선소 인력송출",
    "E-7-3 비자 발급 대행",
    "조선소 취업상담 이메일",
    "조선소 E7비자 초청",
    "조선소 용접기능사 취업",
    "통영 조선소 인력 채용",
    "진해 조선소 인력 채용"
]

GOOD_KW = [
    '행정사', '인력', '취업', '채용', '소개', '협력사', '용접', '비자', 'e7', 'e-7', 'e9', 'e-9',
    '조선소', '선박', '해양', '도급', '파견', '아웃소싱', '노무', '노동', '에이전시', '헤드헌팅', '잡',
    '구인', '일자리', '기능인력', '외국인', '배관', '취부', '직업소개'
]

BAD_KW = [
    '부동산', '공인중개사', '인테리어', '맛집', '영화', '주식', '차트', '가치투자', '의회', '군청',
    '보건복지부', '수학', '학원', '화물', '용달', '소화용구', '베개', '서평', '책', '일상', '패션', '보험'
]

def clean_phone_format(p):
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
    print("MỞ RỘNG EMAIL TỐI ĐA CHO FILE MASTER: KR_AGCY_SHIP_2COL.csv")
    print("=" * 80)

    # 1. Đọc dữ liệu Master hiện có
    master_rows = []
    existing_emails = set()
    existing_companies = set()

    if os.path.exists(MASTER_2COL):
        with open(MASTER_2COL, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                em = r.get('Email', '').strip().lower()
                cname = r.get('Công ty', '').strip()
                if em:
                    existing_emails.add(em)
                if cname:
                    existing_companies.add(cname)
                master_rows.append(r)

    print(f"[*] Tệp hiện tại: {len(master_rows)} dòng (Trong đó đã có {len(existing_emails)} Email).")

    # 2. Cào thêm từ 25 từ khóa mới
    new_agencies = {}

    for idx, kw in enumerate(EXPAND_KEYWORDS, 1):
        print(f"[{idx}/{len(EXPAND_KEYWORDS)}] Quét: '{kw}'...", flush=True)
        for page in range(1, 6):
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
                    post_url = p.get('postUrl', '')
                    if not post_url or 'blog.naver.com' not in post_url:
                        continue
                    parts = post_url.rstrip('/').split('/')
                    if len(parts) < 2:
                        continue
                    blog_id = parts[-2]

                    if blog_id in ['naver', 'blog', 'admin', 'post', 'help']:
                        continue

                    author = p.get('blogName', '').strip()
                    title = BeautifulSoup(p.get('title', ''), 'html.parser').get_text().strip()
                    contents = BeautifulSoup(p.get('contents', ''), 'html.parser').get_text().strip()
                    full_text = f"{title} {contents}".lower()

                    if any(bad in full_text for bad in BAD_KW):
                        continue
                    if not any(good in full_text for good in GOOD_KW):
                        continue

                    # Bóc tách email
                    snip_emails = EMAIL_REGEX.findall(full_text)
                    valid_custom = [e.lower() for e in snip_emails if is_valid_email(e)]
                    target_email = valid_custom[0] if valid_custom else f"{blog_id}@naver.com"

                    if target_email in existing_emails or target_email in new_agencies:
                        continue

                    # SĐT
                    snip_phones = PHONE_REGEX.findall(f"{author} {title} {contents}")
                    clean_phones = [clean_phone_format(ph) for ph in snip_phones if clean_phone_format(ph)]
                    phone = clean_phones[0] if clean_phones else ""

                    # Khu vực
                    region = "Hàn Quốc"
                    for r_name in ['거제', '울산', '영암', '목포', '창원', '진해', '통영', '부산', '군산']:
                        if r_name in full_text:
                            region = r_name
                            break

                    clean_name = re.sub(r'01[016789][\-\s]?\d{3,4}[\-\s]?\d{4}', '', author).strip()
                    clean_name = re.sub(r'[\[\]\(\)]', ' ', clean_name)
                    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
                    if len(clean_name) < 2:
                        clean_name = f"Văn phòng Tuyển dụng & Visa E-7 ({target_email.split('@')[0]})"

                    new_agencies[target_email] = {
                        'No.': '',
                        'Công ty': clean_name,
                        'Chức danh': 'Trưởng ban Tuyển dụng / Đại diện Pháp lý',
                        'Người liên hệ': '',
                        'SĐT': phone,
                        'Liên Hệ': post_url,
                        'Email': target_email,
                        'Liên Hệ mail': '',
                        'Địa chỉ': f"Khu vực {region}, Hàn Quốc",
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
                        'Category': f"Đại lý Visa & Cung ứng thợ hàn đóng tàu ({kw})"
                    }
                    print(f"  [+] THU ĐƯỢC EMAIL MỚI: {clean_name} -> {target_email} ({region})", flush=True)

                time.sleep(0.3)
            except Exception:
                pass

    print(f"\n[+] Tổng số Email mới thu thập thêm: {len(new_agencies)}")

    # 3. Gộp toàn bộ vào tệp Master
    all_final = list(new_agencies.values()) + master_rows

    # Đẩy 100% CÔNG TY CÓ EMAIL LÊN ĐẦU
    with_email = [r for r in all_final if r.get('Email', '').strip()]
    without_email = [r for r in all_final if not r.get('Email', '').strip()]

    # Sắp xếp ưu tiên
    with_email.sort(key=lambda x: (1 if x.get('SĐT') else 0), reverse=True)

    master_sorted = with_email + without_email

    for idx, r in enumerate(master_sorted, 1):
        r['No.'] = str(idx)

    # 4. Ghi đè đồng bộ
    for path in [MASTER_2COL, MASTER_1ENR, FMT_2COL]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(master_sorted)
        print(f"[OK] Đã ghi đè cập nhật: {path}")

    print("\n" + "=" * 80)
    print("HOÀN TẤT MỞ RỘNG EMAIL VÀO FILE MASTER DUY NHẤT!")
    print(f"  • TỔNG SỐ EMAIL TRONG TỆP (XẾP 100% LÊN ĐẦU): {len(with_email)}")
    print(f"  • Tổng số dòng trong tệp: {len(master_sorted)}")
    print(f"  • Tệp đích: {MASTER_2COL}")
    print("=" * 80)

if __name__ == "__main__":
    main()
