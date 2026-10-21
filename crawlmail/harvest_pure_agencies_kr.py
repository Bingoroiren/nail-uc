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

# Load existing emails to avoid duplicates
existing_emails = set()
existing_companies = set()

# Also load previously sent emails from old ship campaigns to guarantee NO overlap!
previous_campaign_emails = set()
for old_file in ["KR_SHIP_ALLS_2COL.csv", "KR_SHIP_HIPC_2COL.csv", "KR_SHIP_DSTU_2COL.csv"]:
    old_path = ROOT_DIR / old_file
    if old_path.exists():
        with open(old_path, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                em = r.get('Email', '').strip().lower()
                if em:
                    previous_campaign_emails.add(em)

print(f"[*] Loaded {len(previous_campaign_emails)} previously sent emails from past ship campaigns (will be 100% blocked).")

if os.path.exists(MASTER_2COL):
    with open(MASTER_2COL, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            em = r.get('Email', '').strip().lower()
            cname = r.get('Công ty', '').strip()
            if em:
                existing_emails.add(em)
            if cname:
                existing_companies.add(cname)

print(f"[*] Current master has {len(existing_emails)} active emails.")

HEADERS = {
    'Referer': 'https://section.blog.naver.com/Search/Post.naver',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

TARGET_KEYWORDS = [
    # Mảng Thủy thủ / Thuyền viên (Seafarer Manning Agencies & E-10 Visa Brokers)
    "외국인 선원 송출 대행",
    "선원 송입업체",
    "선원관리사업체",
    "외국인선원 관리업체",
    "외국인 선원 채용 대행",
    "선원 인력소개소",
    "선박관리 외국인 선원",
    "베트남 선원 송출",
    "E-10 비자 선원 대행",
    "어선 외국인선원 관리",
    "해사행정사 선원 비자",
    "외국인 선원 송입",
    
    # Mảng Thợ hàn tàu / Đóng tàu (Shipyard Manpower Agencies & E-7-3 Attorneys)
    "조선소 E73 비자 행정사",
    "조선용접공 E-7 비자 대행",
    "조선소 기량검증 대행",
    "조선소 외국인 인력공급",
    "조선소 용접공 인력소개소",
    "조선 E-7-3 고용추천서 대행",
    "베트남 용접공 E7 비자 대행",
    "외국인 용접공 초청 행정사",
    "조선소 외국인 비자 행정사",
    "조선업 전문 인력공급업체",
    "울산 조선소 인력소개소",
    "거제 조선소 인력소개소",
    "영암 조선소 인력소개소",
    "통영 조선소 인력소개소",
    "조선소 외국인 용접공 비자",
    "조선소 E-7 비자 발급 대행"
]

STRICT_RELEVANT_KW = [
    '행정사', '인력', '소개소', '취업', '채용', '소개', '비자', 'e7', 'e-7', 'e-10', 'e10',
    '용접', '조선소', '선박', '선원', '해무', '송입', '송출', '파견', '도급', '아웃소싱',
    '기량검증', '고용추천서', '직업소개'
]

GARBAGE_KEYWORDS = [
    '부동산', '공인중개사', '인테리어', '맛집', '영화', '주식', '차트', '가치투자', '의회',
    '군청', '수학', '학원', '화물', '용달', '골굴사', '포르노', '중국 주식', '소화용구', '베개'
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(?:01[016789][\-\s]?\d{3,4}[\-\s]?\d{4}|0\d{1,2}[\-\s]?\d{3,4}[\-\s]?\d{4})')

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
    for g in ['naver.com/s', 'schema.org', 'w3.org', 'example.com', 'domain.com', 'sentry.io', 'wixpress.com', 'blog.me', 'help@', 'support@']:
        if g in e:
            return False
    if re.search(r'\.(png|jpg|jpeg|gif|webp|svg|css|js)$', e):
        return False
    return True

new_harvested = []
seen_new_emails = set()

for idx, kw in enumerate(TARGET_KEYWORDS, 1):
    print(f"[{idx}/{len(TARGET_KEYWORDS)}] Đang quét: '{kw}'...", flush=True)
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

                # Filter garbage
                if any(bad in full_text for bad in GARBAGE_KEYWORDS):
                    continue
                if not any(good in full_text for good in STRICT_RELEVANT_KW):
                    continue

                # Email extraction
                snip_emails = EMAIL_REGEX.findall(full_text)
                valid_custom = [e.lower() for e in snip_emails if is_valid_email(e)]
                target_email = valid_custom[0] if valid_custom else f"{blog_id}@naver.com"

                # Check deduplication
                if target_email in existing_emails or target_email in previous_campaign_emails or target_email in seen_new_emails:
                    continue

                seen_new_emails.add(target_email)

                # Phone extraction
                snip_phones = PHONE_REGEX.findall(f"{author} {title} {contents}")
                clean_phones = [clean_phone_format(ph) for ph in snip_phones if clean_phone_format(ph)]
                phone = clean_phones[0] if clean_phones else ""

                # Company name cleanup
                clean_company = author
                for trim in ['공식블로그', '블로그', 'BLOG', 'Official', '뉴스']:
                    clean_company = clean_company.replace(trim, '').strip()
                if not clean_company or len(clean_company) < 2:
                    clean_company = f"{blog_id} (Agency)"

                # Category tag
                if any(k in kw for k in ['선원', '해사', '어선']):
                    cat_tag = "Seafarer Crewing Agency (Môi giới Thủy thủ/E-10)"
                else:
                    cat_tag = "Shipyard Manpower & Visa E-7-3 Agency (Môi giới Hàn tàu/E-7-3)"

                new_harvested.append({
                    "No.": "",
                    "Công ty": clean_company,
                    "Chức danh": "Giám đốc / Đại diện pháp lý",
                    "Người liên hệ": "Quản lý tuyển dụng",
                    "SĐT": phone,
                    "Liên Hệ": phone,
                    "Email": target_email,
                    "Liên Hệ mail": target_email,
                    "Địa chỉ": "Hàn Quốc",
                    "Lương": "Thỏa thuận theo HĐ B2B",
                    "Ngày đăng": "",
                    "Hạn tuyển": "Thường xuyên",
                    "Check gửi": "",
                    "Last Subject": "",
                    "Last Body HTML": "",
                    "Trạng thái Reply": "",
                    "Lần Follow-up": "",
                    "Ngày Follow-up gần nhất": "",
                    "Mailbox đã dùng": "",
                    "Category": cat_tag
                })
                print(f"   [+] MỚI: {clean_company} | {target_email} | {phone} | {cat_tag}")

        except Exception as e:
            continue
        time.sleep(0.3)

print("=" * 80)
print(f"[*] Thu hoạch được {len(new_harvested)} agency môi giới mới hoàn toàn!")
print("=" * 80)

# Save to cache
os.makedirs('data/cache', exist_ok=True)
with open('data/cache/new_harvested_agencies.json', 'w', encoding='utf-8') as f:
    json.dump(new_harvested, f, ensure_ascii=False, indent=2)
