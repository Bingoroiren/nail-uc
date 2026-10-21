# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for KR_AGCY_NVER_0RAW.csv (Korean Employment Agencies):
1. Đã xoá toàn bộ 2,133 liên kết Naver Place rác.
2. Tra cứu Google Maps (hl=ko, headless=False) theo Tên công ty + Quận/Huyện/Thành phố tại Hàn Quốc để tìm Website chính thức.
3. So khớp tên nghiêm ngặt (Exact match, Delimiter match, Bracket match, loại bỏ pháp nhân Hàn: (주), 주식회사, (유)...).
4. Bóc tách Website chính thức (loại bỏ mạng xã hội & blog.naver/cafe.naver).
5. Chuẩn hóa SĐT (luôn có nháy đơn ' ở đầu) và cập nhật Địa chỉ hành chính chuẩn từ Google Maps.
6. Quét sâu Website vừa tìm được (và 660 website có sẵn) để bóc tách Email B2B (tối ưu cho tuyển dụng và hợp tác nhân sự).
7. Lưu tăng dần (Incremental Auto-Save) sau mỗi công ty và Checkpoint JSON (Resume 100%).
8. Đồng bộ ra:
   - KR_AGCY_NVER_1ENR.csv (Tệp đã làm giàu đầy đủ)
   - KR_AGCY_NVER_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
   - Cập nhật trực tiếp KR_AGCY_NVER_0RAW.csv
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Cấu hình UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "KR_AGCY_NVER_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "KR_AGCY_NVER_1ENR.csv")
COL2_CSV = str(ROOT_DIR / "KR_AGCY_NVER_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_kr_agcy.json")

LEGAL_FORMS_KR = [
    '주식회사', '(주)', '㈜', '유한회사', '(유)', '유한책임회사',
    '합자회사', '(합)', '합명회사', '사단법인', '(사)', '재단법인', '(재)',
    'co., ltd.', 'co.,ltd.', 'co., ltd', 'co.,ltd', 'co ltd',
    'inc.', 'inc', 'corp.', 'corp', 'corporation', 'company'
]

EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.co.kr', 'maps.google.com', 'apple.com',
    'naver.com', 'blog.naver.com', 'cafe.naver.com', 'm.place.naver.com',
    'place.naver.com', 'map.naver.com', 'daum.net', 'kakao.com',
    'saramin.co.kr', 'jobkorea.co.kr', 'albamon.com', 'alba.co.kr',
    'yellowpages', 'tripadvisor'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com',
    'yourcompany.com', 'yourdomain.com', 'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe', 'user'
}

SUBPATHS_CRAWL = [
    '', '/contact', '/about', '/company', '/sub/contact.html', '/sub/company.html',
    '/kor/company/location.php', '/kor/about/contact.php', '/company/location.html',
    '/html/company/location.html', '/intro.html', '/contact.html', '/about.html',
    '/career', '/recruit'
]

MENU_KEYWORDS = [
    '고객센터', '오시는길', '회사소개', '문의', '연락처', '채용', '인재채용', '채용정보',
    'contact', 'about', 'location', 'career', 'recruit', 'inquiry'
]

def clean_phone(phone):
    if not phone:
        return ""
    p = phone.strip()
    p = re.sub(r'^(?:Tel|TEL|전화|T\.)[:\s]*', '', p).strip()
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_website(url):
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    for ex in EXCLUDED_DOMAINS:
        if ex in domain:
            return ""
    return f"{parsed.scheme}://{parsed.netloc}"

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email_chars = [chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)]
        return ''.join(email_chars)
    except Exception:
        return ""

def score_email_b2b(email, website_domain=""):
    e = email.lower().strip()
    user, _, domain = e.partition('@')

    score = 0
    if website_domain and website_domain in domain:
        score += 50

    if any(k in user for k in ['recruit', 'recruiting', 'hr', 'career', 'job', 'jobs', 'nabor', 'insa', 'personal']):
        score += 50
    elif any(k in user for k in ['ceo', 'director', 'manager', 'president', 'master', 'daepyo']):
        score += 45
    elif any(k in user for k in ['info', 'contact', 'office', 'help', 'service', 'inquiry']):
        score += 40
    elif '.' in user and website_domain in domain:
        score += 25
    elif any(w in domain for w in ['naver.com', 'daum.net', 'hanmail.net', 'gmail.com']):
        score += 10
    else:
        score += 5

    return score

def is_valid_name_match(query_name, candidate_name):
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_raw = re.sub(r'["\'„“”«»]', '', query_name).strip().lower()
    c_raw = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()

    if q_raw == c_raw:
        return True, "EXACT"

    def strip_legal(name):
        res = name
        for lf in LEGAL_FORMS_KR:
            res = res.replace(lf, '')
        return re.sub(r'\s+', ' ', res).strip()

    q_clean = strip_legal(q_raw)
    c_clean = strip_legal(c_raw)

    if q_clean and q_clean == c_clean:
        return True, "LEGAL_FORM_MATCH"

    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw).strip()
    c_nobrackets_clean = strip_legal(c_nobrackets)
    if q_clean and q_clean == c_nobrackets_clean:
        return True, "BRACKET_MATCH"

    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
    parts_clean = [strip_legal(p) for p in parts if strip_legal(p)]
    if any(p == q_clean for p in parts_clean):
        return True, "DELIMITER_MATCH"

    if q_clean and len(q_clean) >= 3 and (q_clean in c_clean or c_clean in q_clean):
        return True, "SUBSTRING_MATCH"

    return False, "NO_MATCH"

async def fetch_page_content(session, url):
    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url, timeout=7, impersonate="chrome120")
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, timeout=7, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return ""

async def crawl_website_for_email(start_url):
    if not start_url:
        return ""

    parsed = urllib.parse.urlparse(start_url)
    base_netloc = parsed.netloc.lower()
    clean_domain = base_netloc[4:] if base_netloc.startswith('www.') else base_netloc

    found_emails = set()
    visited_urls = set()

    session_mgr = AsyncSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) if HAS_CURL_CFFI else aiohttp.ClientSession()

    try:
        async with session_mgr as session:
            home_html = await fetch_page_content(session, start_url)
            visited_urls.add(start_url.rstrip('/'))

            if home_html:
                soup = BeautifulSoup(home_html, 'html.parser')
                for cf in soup.find_all(attrs={"data-cfemail": True}):
                    decoded = decode_cloudflare_email(cf['data-cfemail'])
                    if decoded and '@' in decoded:
                        found_emails.add(decoded)
                for a in soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
                    href = a['href'][7:].split('?')[0].strip()
                    unquoted = urllib.parse.unquote(href).replace('%20', '').strip()
                    if '@' in unquoted:
                        found_emails.add(unquoted)
                for m in EMAIL_REGEX.findall(home_html):
                    if not any(m.lower().endswith(ext) for ext in INVALID_EXTENSIONS):
                        found_emails.add(m)

                dom_links = []
                for a in soup.find_all('a', href=True):
                    txt = a.get_text(strip=True).lower()
                    href = a['href'].strip()
                    if any(k in txt for k in MENU_KEYWORDS) or any(k in href.lower() for k in MENU_KEYWORDS):
                        full_url = urllib.parse.urljoin(start_url, href)
                        p = urllib.parse.urlparse(full_url)
                        if p.netloc.lower() == base_netloc and full_url not in visited_urls:
                            dom_links.append(full_url)

                for sub_url in dom_links[:5]:
                    if sub_url in visited_urls:
                        continue
                    visited_urls.add(sub_url)
                    sub_html = await fetch_page_content(session, sub_url)
                    if sub_html:
                        for cf in BeautifulSoup(sub_html, 'html.parser').find_all(attrs={"data-cfemail": True}):
                            decoded = decode_cloudflare_email(cf['data-cfemail'])
                            if decoded and '@' in decoded:
                                found_emails.add(decoded)
                        for a in BeautifulSoup(sub_html, 'html.parser').find_all('a', href=re.compile(r'^mailto:', re.I)):
                            href = a['href'][7:].split('?')[0].strip()
                            unquoted = urllib.parse.unquote(href).replace('%20', '').strip()
                            if '@' in unquoted:
                                found_emails.add(unquoted)
                        for m in EMAIL_REGEX.findall(sub_html):
                            if not any(m.lower().endswith(ext) for ext in INVALID_EXTENSIONS):
                                found_emails.add(m)

            if not found_emails:
                for subpath in SUBPATHS_CRAWL[1:5]:
                    guess_url = urllib.parse.urljoin(start_url, subpath)
                    if guess_url in visited_urls:
                        continue
                    visited_urls.add(guess_url)
                    sub_html = await fetch_page_content(session, guess_url)
                    if sub_html:
                        for m in EMAIL_REGEX.findall(sub_html):
                            if not any(m.lower().endswith(ext) for ext in INVALID_EXTENSIONS):
                                found_emails.add(m)
    except Exception:
        pass

    valid_candidates = []
    for em in found_emails:
        em_clean = em.lower().strip().replace('%20', '')
        user, _, dom = em_clean.partition('@')
        if not dom or not user:
            continue
        if dom in JUNK_EMAIL_DOMAINS:
            continue
        if any(s in user for s in SYSTEM_USERNAMES):
            continue
        score = score_email_b2b(em_clean, clean_domain)
        valid_candidates.append((score, em_clean))

    if valid_candidates:
        valid_candidates.sort(key=lambda x: x[0], reverse=True)
        return valid_candidates[0][1]

    return ""

VIP_ROWS_STATIC = [
    [
        "1", "(주)GK아너스 / GK글로벌행정사사무소 (GK Honors)",
        "Cung ứng thợ hàn & thợ điện E-7-3 đóng tàu (HD Hyundai Samho, Samsung Heavy)",
        "Đại diện di trú (Giấy phép: 23-SU-RG-059)",
        "'+82-2-773-7731 / +82-10-8004-7104",
        "http://www.gkhonors.com/",
        "pe1350063@daum.net",
        "http://www.gkhonors.com/",
        "서울특별시 금천구 가산동 459-7 가산A1타워 1512호",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Agency E-7-3 Đóng tàu & Hành chính di trú"
    ],
    [
        "2", "랑스파트너스(주) (Langs Partners)",
        "Cung ứng thợ hàn E-7-3 đóng tàu (Hợp tác trực tiếp cty phái cử VN)",
        "이현주 (Hyunju Lee) - Hotline phụ trách VN",
        "'+82-51-965-1000 / +82-10-3021-1345",
        "https://www.langspartners.com/",
        "info@langspartners.com",
        "https://www.langspartners.com/",
        "부산광역시 해운대구 좌동로 166",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Agency E-7-3 Đóng tàu & Cung ứng nhân lực quốc tế"
    ],
    [
        "3", "주식회사 탑코리아 (Top Korea)",
        "Cung ứng thợ hàn E-7-3 đóng tàu & cơ khí (Xưởng Ulsan/Geoje)",
        "노성환 대표 (No Seong-hwan - Luật sư hành chính di trú)",
        "'+82-51-723-2840 / +82-10-6894-1345",
        "http://top-korea.co.kr/sub0201.php",
        "topkorea2840@naver.com",
        "http://top-korea.co.kr/",
        "부산광역시 기장군",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Agency E-7-3 Đóng tàu & Luật sư di trú"
    ],
    [
        "4", "티엠글로벌서비스 (TM Global Service)",
        "Nhập khẩu thợ hàn E-7-3 đóng tàu (VPĐD Hà Nội, Nha Trang, Vũng Tàu)",
        "김병일 대표 (Kim Byeong-il)",
        "'+82-10-9145-1451",
        "https://www.tmgs.co.kr/?id=inc&action=shipbuilding",
        "tm1451@tmgs.co.kr",
        "https://www.tmgs.co.kr/?id=request",
        "Hàn Quốc (VPĐD tại Hà Nội, Nha Trang, Vũng Tàu)",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Agency E-7-3 Đóng tàu"
    ],
    [
        "5", "정의LAW행정사사무소 (Jeong-ui Law)",
        "Hành chính tuyển dụng & Quota E-7 nhân lực Việt Nam (đóng tàu, cơ khí)",
        "권근환 대표 행정사 (Kwon Geun-hwan)",
        "'+82-53-252-9068 / +82-53-252-9069",
        "https://blog.naver.com/lawfirm_jeongui",
        "lawjeongui@naver.com",
        "https://blog.naver.com/lawfirm_jeongui",
        "대구광역시 수성구 범어동 173-1 상영빌딩 4층",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Văn phòng Hành chính Di trú (행정사) E-7"
    ],
    [
        "6", "안민 행정사사무소 (Anmin)",
        "Xin Thư tiến cử KOSHIPA & Visa E-7-3 thợ hàn đóng tàu",
        "Bộ phận Visa E-7-3 Đóng tàu",
        "'+82-1544-5799 / +82-2-866-6800",
        "http://anmin.kr/34",
        "anmin5799@naver.com",
        "http://anmin.kr/",
        "서울특별시 구로구 구로동 155-75 도림로16길 10, 3층",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Văn phòng Hành chính Di trú (행정사) KOSHIPA E-7-3"
    ],
    [
        "7", "비전행정사사무소 (Visas Korea / Vision)",
        "Thủ tục bảo lãnh doanh nghiệp & Mời lao động E-7 đóng tàu / kỹ thuật",
        "이원중 대표 (Lee Won-jung)",
        "'+82-2-363-2251 / +82-10-2081-3408",
        "https://www.visaskorea.com/",
        "5000meter@gmail.com",
        "https://www.visaskorea.com/",
        "서울특별시 중구 퇴계로 324 성우빌딩 3층",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Văn phòng Hành chính Di trú (행정사) E-7"
    ],
    [
        "8", "임원일 행정사사무소 (Im Won-il)",
        "Thủ tục nhập cảnh thợ hàn/thợ sơn E-7-3 (Gần HD Hyundai Samho Yeongam)",
        "임원일 대표 행정사 (Im Won-il)",
        "'+82-61-721-0048 / +82-10-2261-0257",
        "http://blog.naver.com/wonil5262",
        "wonil5262@naver.com",
        "http://blog.naver.com/wonil5262",
        "전라남도 순천시 (Khu vực lân cận HD Hyundai Samho)",
        "", "2026-10-06", "", "", "", "", "", "", "", "",
        "Văn phòng Hành chính Di trú (행정사) E-7-3 Đóng tàu"
    ]
]

def save_all_files(headers, rows, cache):
    # Lưu cache JSON
    with open(CACHE_FILE, mode="w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Đảm bảo 8 VIP agency luôn đứng đầu
    vip_names = [v[1] for v in VIP_ROWS_STATIC]
    cleaned_rows = [r for r in rows if r[1] not in vip_names]
    full_rows = [list(v) for v in VIP_ROWS_STATIC] + cleaned_rows

    # Lưu KR_AGCY_NVER_1ENR.csv
    with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(full_rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)

    # Cập nhật KR_AGCY_NVER_0RAW.csv
    with open(INPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(full_rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)

    # Lưu KR_AGCY_NVER_2COL.csv (8 VIP đứng đầu, sau đó là các hàng có Email khác, cuối cùng là không Email)
    vip_rows_list = [list(v) for v in VIP_ROWS_STATIC]
    with_email_others = [r for r in cleaned_rows if r[6].strip()]
    without_email = [r for r in cleaned_rows if not r[6].strip()]
    sorted_rows = vip_rows_list + with_email_others + without_email

    with open(COL2_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(sorted_rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)

async def main():
    print("=" * 70)
    print(" LÀM GIÀU DỮ LIỆU GOOGLE MAPS CHO KR_AGCY_NVER_0RAW.CSV")
    print("=" * 70)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy tệp {INPUT_CSV}")
        return

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    print(f"\n[1/4] Đã nạp {len(rows)} công ty giới thiệu việc làm từ {INPUT_CSV}")

    # Đọc cache nếu có
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, mode="r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f" -> Khôi phục cache checkpoint: {len(cache)} công ty đã xử lý.")
        except Exception:
            cache = {}

    # Thống kê trạng thái
    # Columns in KR_AGCY_NVER_0RAW.csv:
    # 0: No., 1: Cong ty, 4: SDT, 5: Lien He (Web), 6: Email, 8: Dia chi
    to_process_indices = []
    for idx, r in enumerate(rows):
        comp = r[1]
        phone = r[4].strip()
        web = r[5].strip()
        email = r[6].strip()

        # Nạp lại từ cache nếu có
        if comp in cache:
            c = cache[comp]
            if c.get("website"):
                r[5] = c["website"]
                web = c["website"]
            if c.get("email"):
                r[6] = c["email"]
                email = c["email"]
            if c.get("phone") and not r[4].strip():
                r[4] = c["phone"]

        # Nếu chưa có website hoặc chưa có email -> Cần xử lý
        if not web or not email:
            to_process_indices.append(idx)

    print(f" -> Tổng số công ty: {len(rows)}")
    print(f" -> Đã có Website hợp lệ: {sum(1 for r in rows if r[5].strip())}")
    print(f" -> Đã có Email: {sum(1 for r in rows if r[6].strip())}")
    print(f" -> SỐ CÔNG TY CẦN TRA CỨU GOOGLE MAPS / QUÉT EMAIL: {len(to_process_indices)} công ty.")

    # 2. Khởi động Playwright
    print("\n[2/4] Đang khởi động trình duyệt Chrome trực quan (headless=False)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="ko-KR")
        page = await context.new_page()

        total_proc = len(to_process_indices)
        save_counter = 0

        for current_cnt, row_idx in enumerate(to_process_indices, 1):
            r = rows[row_idx]
            comp_name = r[1]
            existing_phone = r[4].strip()
            existing_web = r[5].strip()
            existing_email = r[6].strip()
            existing_addr = r[8].strip()

            new_web = existing_web
            new_email = existing_email
            new_phone = existing_phone
            new_addr = existing_addr

            # Bước 1: Nếu đã có website nhưng chưa có email -> Quét website trực tiếp
            if existing_web and not existing_email:
                print(f"[{current_cnt}/{total_proc}] Quét website có sẵn: {comp_name} ({existing_web})...")
                found_em = await crawl_website_for_email(existing_web)
                if found_em:
                    new_email = found_em
                    print(f"    [+] Tìm thấy Email từ website: {new_email}")

            # Bước 2: Nếu chưa có Website -> Tra cứu trên Google Maps
            if not new_web:
                # Trích xuất quận/huyện/thành phố để truy vấn chính xác
                city_matches = re.findall(r'([가-힣]+(?:시|군|구))', existing_addr)
                city_str = ' '.join(city_matches[:2]) if city_matches else ''
                query = f"{comp_name} {city_str}".strip()

                print(f"[{current_cnt}/{total_proc}] Tìm Google Maps: {query}...")

                try:
                    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=ko"
                    await page.goto(search_url, timeout=12000, wait_until="domcontentloaded")
                    await asyncio.sleep(2)

                    if "consent.google.com" in page.url or "google.com/sorry" in page.url:
                        print("\a[!] PHÁT HIỆN CAPTCHA! Vui lòng giải captcha trên trình duyệt...")
                        await asyncio.sleep(10)

                    candidate_name = ""
                    h1 = await page.query_selector("h1")
                    if h1:
                        candidate_name = (await h1.inner_text()).strip()

                    if not candidate_name:
                        first_res = await page.query_selector("div[role='feed'] a[aria-label]")
                        if first_res:
                            candidate_name = await first_res.get_attribute("aria-label") or ""
                            await first_res.click()
                            await asyncio.sleep(2)

                    is_match, match_type = is_valid_name_match(comp_name, candidate_name)
                    if is_match:
                        print(f"    -> Khớp tên ({match_type}): '{candidate_name}'")

                        # Bóc tách Website
                        web_btn = await page.query_selector("a[data-item-id='authority']")
                        if web_btn:
                            href = await web_btn.get_attribute("href")
                            clean_w = clean_website(href)
                            if clean_w:
                                new_web = clean_w
                                print(f"    [+] Tìm thấy Website từ Google Maps: {new_web}")

                        # Bóc tách SĐT
                        phone_btn = await page.query_selector("button[data-item-id^='phone:']")
                        if phone_btn:
                            ph_text = await phone_btn.inner_text()
                            c_ph = clean_phone(ph_text)
                            if c_ph and not new_phone:
                                new_phone = c_ph
                                print(f"    [+] SĐT Google Maps: {new_phone}")

                        # Bóc tách Địa chỉ
                        addr_btn = await page.query_selector("button[data-item-id='address']")
                        if addr_btn:
                            ad_text = await addr_btn.inner_text()
                            if ad_text and (not new_addr or len(ad_text) > len(existing_addr)):
                                new_addr = ad_text.strip()
                                print(f"    [+] Địa chỉ Google Maps: {new_addr}")

                        # Nếu vừa tìm được website -> Quét sâu tìm Email ngay
                        if new_web and not new_email:
                            print(f"    -> Quét email từ website vừa tìm được: {new_web}...")
                            found_em = await crawl_website_for_email(new_web)
                            if found_em:
                                new_email = found_em
                                print(f"    [+] Tìm thấy Email: {new_email}")
                    else:
                        print(f"    [-] Không khớp tên trên Google Maps (Ggmap: '{candidate_name}')")

                except Exception as e:
                    print(f"    [!] Lỗi tìm kiếm Google Maps: {e}")

            # Cập nhật kết quả vào dòng
            r[4] = clean_phone(new_phone)
            r[5] = new_web
            r[6] = new_email
            r[8] = new_addr

            # Lưu vào cache
            cache[comp_name] = {
                "phone": new_phone,
                "website": new_web,
                "email": new_email,
                "addr": new_addr
            }

            save_counter += 1
            # Lưu tăng dần sau mỗi công ty
            save_all_files(headers, rows, cache)

        await browser.close()

    print(f"\n[V] HOÀN TẤT LÀM GIÀU DỮ LIỆU BẰNG GOOGLE MAPS CHO KR_AGCY_NVER!")

if __name__ == "__main__":
    asyncio.run(main())
