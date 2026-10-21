# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Email Enrichment for KR_WELD_E703_0RAW.csv
(Các xưởng đóng tàu và nhà thầu phụ đang khát thợ hàn E-7-3):
1. Tra cứu Google Maps (hl=ko, headless=False) theo Tên công ty + Địa phương.
2. So khớp tên nghiêm ngặt (loại bỏ legal form Hàn: (주), 주식회사...).
3. Bóc tách Website chính thức, Số điện thoại (luôn có nháy đơn '), Địa chỉ chuẩn.
4. Quét sâu Website bóc tách Email B2B (chấm điểm theo chuẩn B2B Manpower).
5. Lưu tăng dần sau mỗi công ty và Checkpoint JSON (Resume 100%).
6. Xuất đồng bộ ra:
   - KR_WELD_E703_1ENR.csv
   - KR_WELD_E703_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
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

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "KR_WELD_E703_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "KR_WELD_E703_1ENR.csv")
COL2_CSV = str(ROOT_DIR / "KR_WELD_E703_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_weld_e703.json")

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
    'saramin.co.kr', 'jobkorea.co.kr', 'work24.go.kr', 'work.go.kr', 'incruit.com',
    'catch.co.kr', 'wanted.co.kr', 'alba.co.kr', 'albamon.com',
    'blog.naver.com', 'cafe.naver.com', 'kin.naver.com', 'map.naver.com',
    'daum.net', 'tistory.com', 'brunch.co.kr', 'map.kakao.com'
}

def clean_company_name(name: str) -> str:
    if not name:
        return ""
    res = name.strip()
    for lf in LEGAL_FORMS_KR:
        res = re.sub(re.escape(lf), '', res, flags=re.IGNORECASE)
    res = re.sub(r'[\(\)\[\]\{\}\.,]', '', res)
    return res.strip()

def clean_phone(phone: str) -> str:
    if not phone:
        return ""
    p = str(phone).strip()
    if not p or p.lower() == 'nan' or p.lower() == 'none':
        return ""
    p = re.sub(r'[^\d\+\-\s\(\)]', '', p)
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_website(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith('http'):
        url = 'http://' + url
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    for ex in EXCLUDED_DOMAINS:
        if ex in netloc:
            return ""
    return f"{parsed.scheme}://{parsed.netloc}"

def score_email_b2b(email: str, website_url: str = "") -> int:
    em = email.lower().strip()
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em):
        return 0

    garbage = [
        'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
        'user@domain', 'name@domain', 'example.com', 'domain.com', 'email@email.com',
        'sentry.wixpress', 'sentry.io', 'wix.com', 'wordpress.com', 'no-reply',
        'donotreply', 'privacy@', 'gdpr@', 'webmaster@', 'postmaster@'
    ]
    if any(g in em for g in garbage):
        return 0

    score = 10
    if website_url:
        try:
            domain = urllib.parse.urlparse(website_url).netloc.lower().replace('www.', '')
            if domain and domain in em:
                score += 50
        except Exception:
            pass

    # Ưu tiên nhân sự, tuyển dụng
    hr_prefixes = ['praca@', 'kariera@', 'hr@', 'recruit@', 'jobs@', 'nabor@', 'personal@']
    if any(em.startswith(p) for p in hr_prefixes):
        score += 50
    # Ưu tiên ban giám đốc
    exec_prefixes = ['ceo@', 'director@', 'manager@', 'obchod@', 'sales@', 'boss@']
    if any(em.startswith(p) for p in exec_prefixes):
        score += 45
    # Cổng liên hệ chính thức
    contact_prefixes = ['info@', 'contact@', 'office@', 'help@', 'support@']
    if any(em.startswith(p) for p in contact_prefixes):
        score += 40

    if any(em.endswith(free) for free in ['@gmail.com', '@naver.com', '@daum.net', '@hanmail.net']):
        score += 15

    return score

async def crawl_website_for_email(website_url: str) -> str:
    if not website_url:
        return ""
    
    clean_base = clean_website(website_url)
    if not clean_base:
        return ""

    candidates = set()
    subpaths = ['', '/contact', '/about', '/company', '/intro', '/kor/contact']
    
    async with AsyncSession(impersonate="chrome120") as s:
        for sp in subpaths:
            t_url = clean_base.rstrip('/') + sp
            try:
                resp = await s.get(t_url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code == 200:
                    text = resp.text
                    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
                    for em in emails:
                        em_clean = em.strip().rstrip('.')
                        candidates.add(em_clean)
                    if candidates:
                        break
            except Exception:
                pass

    if not candidates:
        return ""

    scored = []
    for c in candidates:
        sc = score_email_b2b(c, clean_base)
        if sc > 0:
            scored.append((sc, c))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    return ""

def save_all_files(headers, rows, cache):
    with open(CACHE_FILE, mode="w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)

    with_email = [r for r in rows if r[6].strip()]
    without_email = [r for r in rows if not r[6].strip()]
    sorted_rows = with_email + without_email

    with open(COL2_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(sorted_rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)

async def main():
    print("=" * 70)
    print(" LÀM GIÀU DỮ LIỆU GOOGLE MAPS CHO KR_WELD_E703_0RAW.CSV")
    print("=" * 70)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Chưa có tệp {INPUT_CSV}. Chờ scraper hoàn tất.")
        return

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    print(f"[1/3] Đã nạp {len(rows)} doanh nghiệp xưởng tàu đang tuyển thợ hàn E-7-3")

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, mode="r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f" -> Khôi phục cache checkpoint: {len(cache)} công ty đã xử lý.")
        except Exception:
            cache = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--lang=ko-KR', '--window-size=1280,800'])
        context = await browser.new_context(locale='ko-KR', viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        for idx, r in enumerate(rows, 1):
            comp_name = r[1].strip()
            loc_hint = r[8].strip() if len(r) > 8 else ""
            clean_name = clean_company_name(comp_name)

            if not clean_name:
                continue

            if comp_name in cache:
                c = cache[comp_name]
                if c.get("phone"): r[4] = clean_phone(c["phone"])
                if c.get("website"): r[5] = c["website"]
                if c.get("email"): r[6] = c["email"]
                if c.get("addr"): r[8] = c["addr"]
                continue

            print(f"\n[{idx}/{len(rows)}] Tra cứu Google Maps: {comp_name} ({clean_name})...")
            
            new_phone = r[4].strip()
            new_web = r[5].strip() if r[5].startswith('http') and not any(k in r[5] for k in ['work24', 'saramin', 'jobkorea']) else ""
            new_email = r[6].strip()
            new_addr = r[8].strip()

            query = f"{clean_name} {loc_hint}".strip() if loc_hint and loc_hint != 'Hàn Quốc' else f"{clean_name} 조선"
            gmap_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=ko"

            try:
                await page.goto(gmap_url, timeout=20000, wait_until='domcontentloaded')
                await page.wait_for_timeout(1500)

                # Kiểm tra kết quả
                title_el = await page.query_selector("h1.DUwDvf, div.qBF1Pd, h1")
                cand_name = await title_el.inner_text() if title_el else ""
                
                clean_cand = clean_company_name(cand_name)
                if clean_name in clean_cand or clean_cand in clean_name or len(clean_name) > 3 and clean_name[:3] in clean_cand:
                    print(f"    [+] Khớp tên Google Maps: {cand_name}")
                    
                    # Bóc tách Website
                    web_btn = await page.query_selector("a[data-item-id='authority']")
                    if web_btn:
                        href = await web_btn.get_attribute("href")
                        cw = clean_website(href)
                        if cw:
                            new_web = cw
                            print(f"    [+] Website Google Maps: {new_web}")

                    # Bóc tách SĐT
                    phone_btn = await page.query_selector("button[data-item-id^='phone:']")
                    if phone_btn:
                        ph_text = await phone_btn.inner_text()
                        c_ph = clean_phone(ph_text)
                        if c_ph:
                            new_phone = c_ph
                            print(f"    [+] SĐT Google Maps: {new_phone}")

                    # Bóc tách Địa chỉ
                    addr_btn = await page.query_selector("button[data-item-id='address']")
                    if addr_btn:
                        ad_text = await addr_btn.inner_text()
                        if ad_text:
                            new_addr = ad_text.strip()
                            print(f"    [+] Địa chỉ Google Maps: {new_addr}")

                    # Quét email nếu có website
                    if new_web and not new_email:
                        print(f"    -> Quét email từ website: {new_web}...")
                        found_em = await crawl_website_for_email(new_web)
                        if found_em:
                            new_email = found_em
                            print(f"    [+] Tìm thấy Email B2B: {new_email}")
                else:
                    print(f"    [-] Không khớp tên (Ggmap: '{cand_name}')")

            except Exception as e:
                print(f"    [!] Lỗi tìm kiếm Google Maps: {e}")

            r[4] = clean_phone(new_phone)
            r[5] = new_web if new_web else r[5]
            r[6] = new_email
            r[8] = new_addr

            cache[comp_name] = {
                "phone": new_phone,
                "website": new_web,
                "email": new_email,
                "addr": new_addr
            }

            save_all_files(headers, rows, cache)

        await browser.close()

    print(f"\n[V] HOÀN TẤT LÀM GIÀU DỮ LIỆU GOOGLE MAPS CHO KR_WELD_E703!")

if __name__ == "__main__":
    asyncio.run(main())
