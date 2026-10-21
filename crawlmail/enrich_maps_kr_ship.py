# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for KR_SHIP_DSTU_0RAW.csv:
1. Tập trung tối ưu vào 386 doanh nghiệp ĐANG THIẾU EMAIL.
2. Với công ty đã có website -> Quét trực tiếp website tìm Email B2B.
3. Với công ty chưa có website -> Tra cứu Google Maps (hl=ko, headless=False) để bóc tách Website, SĐT, Địa chỉ.
4. Quét sâu website vừa tìm được để lấy Email B2B tối ưu nhất.
5. Lưu tăng dần từng dòng vào KR_SHIP_DSTU_1ENR.csv, đồng bộ KR_SHIP_DSTU_2COL.csv và cache JSON (hỗ trợ Resume 100%).
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
INPUT_CSV = str(ROOT_DIR / "KR_SHIP_DSTU_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "KR_SHIP_DSTU_1ENR.csv")
COL2_CSV = str(ROOT_DIR / "KR_SHIP_DSTU_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_kr_ship.json")

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
    'naver.com', 'daum.net', 'kakao.com', 'saramin.co.kr', 'jobkorea.co.kr',
    'yellowpages', 'tripadvisor', 'seanet.co.kr', 'maritimepress.co.kr', 'dstug.org'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com',
    'yourcompany.com', 'yourdomain.com', 'email.com', 'mail.com', 'deepcircle.net'
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
    '/career', '/recruit', '/kor/recruit/notice.php'
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

    if any(k in user for k in ['crew', 'crewing', 'recruit', 'recruiting', 'hr', 'career', 'job', 'jobs', 'nabor', 'insa', 'personal']):
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

    if q_clean and len(q_clean) >= 3 and q_clean in c_clean:
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

def save_csv_and_cache(headers, rows, cache):
    with open(CACHE_FILE, mode="w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)

    # Đồng bộ 2COL
    with_email = [r for r in rows if r[7].strip()]
    without_email = [r for r in rows if not r[7].strip()]
    sorted_rows = with_email + without_email

    col2_headers = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]
    with open(COL2_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(col2_headers)
        for idx, r in enumerate(sorted_rows, 1):
            comp_name = r[1]
            category = r[2]
            pos_val = r[4] if len(r) > 4 else ""
            job_title = pos_val if pos_val else category
            phone = r[5]
            email = r[7]
            rep = r[8] if len(r) > 8 else ""
            addr = r[9] if len(r) > 9 else ""
            web = r[10] if len(r) > 10 else ""
            writer.writerow([
                idx, comp_name, job_title, rep, phone, web, email,
                "", addr, "", "", "", "", "", "", "", "", "", "", category
            ])

async def main():
    print("=" * 70)
    print(" LÀM GIÀU DỮ LIỆU GOOGLE MAPS & DEEP WEB CHO TẬP DỮ LIỆU HÀNG HẢI")
    print("=" * 70)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy tệp {INPUT_CSV}")
        return

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    print(f"\n[1/4] Đã nạp {len(rows)} doanh nghiệp từ {INPUT_CSV}")

    # Đọc cache nếu có
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, mode="r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f" -> Đã khôi phục cache checkpoint: {len(cache)} doanh nghiệp.")
        except Exception:
            cache = {}

    # Đếm số dòng còn thiếu email
    missing_email_indices = []
    for idx, r in enumerate(rows):
        comp = r[1]
        email = r[7].strip()
        # Nạp từ cache nếu có
        if comp in cache:
            c_data = cache[comp]
            if c_data.get("email"):
                r[7] = c_data["email"]
            if c_data.get("phone") and not r[5].strip():
                r[5] = c_data["phone"]
            if c_data.get("website"):
                if len(r) > 10:
                    r[10] = c_data["website"]
                else:
                    r.append(c_data["website"])
            if c_data.get("addr") and not r[9].strip():
                r[9] = c_data["addr"]
            email = r[7].strip()

        if not email:
            missing_email_indices.append(idx)

    print(f" -> Tổng số doanh nghiệp: {len(rows)} | Đã có email: {len(rows)-len(missing_email_indices)} | CẦN LÀM GIÀU EMAIL: {len(missing_email_indices)} công ty.")

    # 2. Khởi động Playwright
    print("\n[2/4] Đang khởi động trình duyệt Chrome trực quan (headless=False)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="ko-KR")
        page = await context.new_page()

        total_missing = len(missing_email_indices)
        processed = 0

        for current_idx, row_idx in enumerate(missing_email_indices, 1):
            r = rows[row_idx]
            comp_name = r[1]
            existing_phone = r[5].strip()
            existing_addr = r[9].strip()
            existing_web = r[10].strip() if len(r) > 10 else ""

            new_email = ""
            new_web = existing_web
            new_phone = existing_phone
            new_addr = existing_addr

            # Bước A: Nếu đã có website -> Quét website trước
            if existing_web:
                print(f"[{current_idx}/{total_missing}] Quét website có sẵn: {comp_name} ({existing_web})...")
                found_em = await crawl_website_for_email(existing_web)
                if found_em:
                    new_email = found_em
                    print(f"    [+] Tìm thấy Email từ website: {new_email}")

            # Bước B: Nếu vẫn chưa có email -> Tra cứu Google Maps
            if not new_email:
                city = ""
                m_city = re.search(r'([가-힣]+(?:시|군|구))', existing_addr)
                if m_city:
                    city = m_city.group(1)

                query = f"{comp_name} {city}".strip()
                print(f"[{current_idx}/{total_missing}] Tìm Google Maps: {query}...")

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

                        # Website
                        web_btn = await page.query_selector("a[data-item-id='authority']")
                        if web_btn:
                            href = await web_btn.get_attribute("href")
                            clean_w = clean_website(href)
                            if clean_w:
                                new_web = clean_w
                                print(f"    [+] Website Google Maps: {new_web}")

                        # SĐT
                        phone_btn = await page.query_selector("button[data-item-id^='phone:']")
                        if phone_btn:
                            ph_text = await phone_btn.inner_text()
                            c_ph = clean_phone(ph_text)
                            if c_ph and not new_phone:
                                new_phone = c_ph
                                print(f"    [+] SĐT Google Maps: {new_phone}")

                        # Địa chỉ
                        addr_btn = await page.query_selector("button[data-item-id='address']")
                        if addr_btn:
                            ad_text = await addr_btn.inner_text()
                            if ad_text and (not new_addr or len(ad_text) > len(existing_addr)):
                                new_addr = ad_text.strip()
                                print(f"    [+] Địa chỉ Google Maps: {new_addr}")

                        # Quét website vừa tìm được
                        if new_web:
                            print(f"    -> Quét email từ website vừa tìm được: {new_web}...")
                            found_em = await crawl_website_for_email(new_web)
                            if found_em:
                                new_email = found_em
                                print(f"    [+] Tìm thấy Email: {new_email}")
                    else:
                        print(f"    [-] Không khớp tên (Ggmap: '{candidate_name}')")

                except Exception as e:
                    print(f"    [!] Lỗi Google Maps: {e}")

            # Cập nhật kết quả vào dòng
            if new_email:
                r[7] = new_email
            if new_phone:
                r[5] = new_phone
            if new_addr:
                r[9] = new_addr
            if new_web:
                if len(r) > 10:
                    r[10] = new_web
                else:
                    r.append(new_web)

            # Cập nhật cache
            cache[comp_name] = {
                "phone": r[5],
                "email": r[7],
                "addr": r[9],
                "website": r[10] if len(r) > 10 else ""
            }

            processed += 1
            # Lưu tăng dần sau mỗi công ty
            save_csv_and_cache(headers, rows, cache)

        await browser.close()

    print(f"\n[V] HOÀN TẤT QUÁ TRÌNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
    # Tóm tắt
    with_email_cnt = sum(1 for r in rows if r[7].strip())
    print(f" - Tổng doanh nghiệp: {len(rows)}")
    print(f" - Doanh nghiệp có Email: {with_email_cnt} (Tăng thêm {with_email_cnt - (len(rows)-len(missing_email_indices))} email)")
    print(f" - Tệp làm giàu hoàn tất: {OUTPUT_CSV}")
    print(f" - Tệp Cold Mail 20 cột: {COL2_CSV}")

if __name__ == "__main__":
    asyncio.run(main())
