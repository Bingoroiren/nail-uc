# -*- coding: utf-8 -*-
"""
LÀM GIÀU DỮ LIỆU CHUYÊN BIỆT: MÔI GIỚI VIỆC LÀM THỦ PHỦ ĐÓNG TÀU (AGENCY ONLY)
Tập dữ liệu: KR_AGCY_WELD_0RAW.csv (543 Văn phòng Môi giới tại Geoje, Ulsan, Yeongam, Mokpo, Jinhae, Tongyeong)

Quy trình:
1. Tra cứu Google Maps (hl=ko, headless=False) theo Tên công ty + Địa phương tại các thủ phủ đóng tàu.
2. Bóc tách Website chính thức, Số điện thoại hotline (có nháy đơn '), Địa chỉ chuẩn.
3. Quét sâu Website bóc tách Email B2B (bộ chấm điểm B2B Manpower, lọc sạch rác/template).
4. Lưu tăng dần sau mỗi 5 công ty (Auto-save) và Checkpoint JSON (Resume 100%).
5. Xuất đồng bộ ra:
   - KR_AGCY_WELD_1ENR.csv (Tệp làm giàu đầy đủ)
   - KR_AGCY_WELD_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy 100% email lên đầu)
"""

import sys
import io
import os
import re
import csv
import json
import time
import asyncio
import functools
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True) if hasattr(sys.stdout, 'buffer') else sys.stdout
print = functools.partial(print, flush=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "KR_AGCY_WELD_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "KR_AGCY_WELD_1ENR.csv")
COL2_CSV = str(ROOT_DIR / "KR_AGCY_WELD_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_kr_agcy_weld.json")

EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.co.kr', 'maps.google.com', 'apple.com',
    'saramin.co.kr', 'jobkorea.co.kr', 'work24.go.kr', 'work.go.kr', 'incruit.com',
    'catch.co.kr', 'wanted.co.kr', 'alba.co.kr', 'albamon.com',
    'daum.net', 'kakao.com', 'yellowpages', 'bizno.net', 'ftc.go.kr', 'moel.go.kr'
}

def clean_phone(phone: str) -> str:
    if not phone or str(phone).lower() == 'nan':
        return ""
    p = str(phone).strip()
    p = re.sub(r'^(?:Tel|TEL|전화|T\.)[:\s]*', '', p).strip()
    p = re.sub(r'[^\d\+\-\s\(\)]', '', p).strip()
    if not p:
        return ""
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_website(web: str) -> str:
    if not web or str(web).lower() == 'nan':
        return ""
    w = str(web).strip()
    if not w.startswith('http://') and not w.startswith('https://'):
        w = 'http://' + w
    try:
        parsed = urllib.parse.urlparse(w)
        domain = parsed.netloc.lower()
        if any(ex in domain for ex in EXCLUDED_DOMAINS):
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return ""

def score_email_b2b(email: str, website_url: str = "") -> int:
    if not email:
        return 0
    em = email.strip().lower()
    if '@' not in em or '.' not in em:
        return 0

    if not re.search(r'@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?$', em):
        return 0

    garbage = [
        'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
        'user@domain', 'name@domain', 'example.com', 'domain.com', 'email@email.com',
        'sentry', 'wix', 'wixpress', 'wordpress', 'no-reply', 'donotreply', 'privacy@',
        'gdpr@', 'webmaster@', 'postmaster@', '@2x.png', '.svg', 'gabia.com', 'hosting@',
        'polyfill', 'component', 'player', 'focus-within', 'cloudflare', 'schema.org'
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

    hr_prefixes = ['recruit@', 'hr@', 'jobs@', 'insa@', 'job@', 'work@', 'career@', 'praca@']
    if any(em.startswith(p) for p in hr_prefixes):
        score += 50
    exec_prefixes = ['ceo@', 'director@', 'manager@', 'master@', 'boss@', 'president@', 'sales@']
    if any(em.startswith(p) for p in exec_prefixes):
        score += 45
    contact_prefixes = ['info@', 'contact@', 'office@', 'help@', 'support@', 'admin@']
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
    subpaths = ['', '/contact', '/about', '/company', '/intro', '/recruit', '/kor/contact.php', '/sub/contact.html']

    if HAS_CURL_CFFI:
        async with AsyncSession(impersonate="chrome120") as s:
            for sp in subpaths:
                t_url = clean_base.rstrip('/') + sp
                try:
                    resp = await s.get(t_url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
                    if resp.status_code == 200:
                        emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', resp.text)
                        for em in emails:
                            candidates.add(em.strip().rstrip('.'))
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
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    col2_rows = [r.copy() for r in rows]
    def sort_key(item):
        em = str(item.get('Email', '')).strip()
        ph = str(item.get('SDT', '')).strip()
        has_em = 1 if em and '@' in em else 0
        has_ph = 1 if ph else 0
        return (has_em, has_ph)

    col2_rows.sort(key=sort_key, reverse=True)
    for idx, r in enumerate(col2_rows, 1):
        r['No.'] = str(idx)

    with open(COL2_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(col2_rows)

async def main(max_limit=0):
    print("=" * 75)
    print(" KHỞI CHẠY QUÉT LÀM GIÀU MÔI GIỚI THỦ PHỦ ĐÓNG TÀU (KR_AGCY_WELD)")
    print("=" * 75)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy tệp {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)

    print(f"Tổng số Agency Môi giới việc làm đóng tàu: {len(rows)}")

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f" -> Khôi phục Checkpoint JSON: {len(cache)} cơ sở đã lưu.")
        except Exception:
            cache = {}

    todo_indices = []
    for idx, r in enumerate(rows):
        cname = r['Cong ty'].strip()
        em = r.get('Email', '').strip()
        ph = r.get('SDT', '').strip()
        if (not em or em == 'nan') and cname not in cache:
            todo_indices.append(idx)

    target_count = len(todo_indices) if max_limit <= 0 else min(len(todo_indices), max_limit)
    print(f"Số lượng cơ sở cần quét đợt này: {target_count} {'(TOÀN BỘ CƠ SỞ CÒN LẠI)' if max_limit <= 0 else ''}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--lang=ko-KR', '--window-size=1280,800'])
        context = await browser.new_context(locale='ko-KR', viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        processed = 0
        for idx in todo_indices:
            if max_limit > 0 and processed >= max_limit:
                break
            processed += 1

            row = rows[idx]
            raw_name = row['Cong ty'].strip()
            addr = row.get('Dia chi', '').strip()
            city = addr.split()[0] if addr else ''

            pct = (processed / target_count * 100) if target_count > 0 else 0
            print(f"\n[{processed}/{target_count}] ({pct:.1f}%) Tra cứu: {raw_name} ({city})...")

            found_web = row.get('Lien He', '').strip()
            if 'moel.go.kr' in found_web:
                found_web = ""
            found_phone = row.get('SDT', '').strip()
            found_email = row.get('Email', '').strip()

            # Bước 1: Tra cứu Google Maps
            if not found_web or not found_phone:
                search_q = f"{raw_name} {city}".strip()
                gmap_url = f"https://www.google.com/maps/search/{urllib.parse.quote(search_q)}?hl=ko"
                try:
                    await page.goto(gmap_url, timeout=14000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(1000)

                    # Bóc tách Website
                    if not found_web:
                        web_el = await page.query_selector("a[data-item-id='authority']")
                        if web_el:
                            href = await web_el.get_attribute("href")
                            cw = clean_website(href)
                            if cw:
                                found_web = cw
                                print(f"    [+] Ggmap: Tìm thấy Website: {found_web}")

                    # Bóc tách SĐT
                    if not found_phone:
                        ph_el = await page.query_selector("button[data-item-id^='phone:']")
                        if ph_el:
                            p_txt = await ph_el.inner_text()
                            cp = clean_phone(p_txt)
                            if cp:
                                found_phone = cp
                                print(f"    [+] Ggmap: Tìm thấy SĐT: {found_phone}")

                    # Bóc tách Địa chỉ chuẩn
                    addr_el = await page.query_selector("button[data-item-id='address']")
                    if addr_el:
                        a_txt = await addr_el.inner_text()
                        if a_txt and len(a_txt) > 5:
                            row['Dia chi'] = a_txt.strip()
                except Exception:
                    pass

            # Bước 2: Quét sâu Website bóc tách Email B2B
            if found_web and not found_email:
                try:
                    em_scraped = await crawl_website_for_email(found_web)
                    if em_scraped:
                        found_email = em_scraped
                        print(f"    [+] Website: Bóc tách được Email B2B: {found_email}")
                except Exception:
                    pass

            # Cập nhật vào dòng
            if found_phone and not row.get('SDT'):
                row['SDT'] = found_phone
            if found_web and ('moel.go.kr' in str(row.get('Lien He')) or not row.get('Lien He')):
                row['Lien He'] = found_web
            if found_email and not row.get('Email'):
                row['Email'] = found_email

            cache[raw_name] = {
                'phone': found_phone,
                'web': found_web,
                'email': found_email
            }

            # Lưu tăng dần định kỳ sau mỗi 5 cơ sở
            if processed % 5 == 0:
                save_all_files(headers, rows, cache)
                print(f"  -> [Auto-save] Đã ghi lưu tăng dần vào {OUTPUT_CSV} & {COL2_CSV}")

        await browser.close()

    save_all_files(headers, rows, cache)
    print("\n" + "=" * 75)
    print(f"HOÀN TẤT CHIẾN DỊCH QUÉT LÀM GIÀU {processed} AGENCY MÔI GIỚI THỦ PHỦ ĐÓNG TÀU!")
    print(f"Dữ liệu được lưu trữ chuẩn Cold Mail tại:")
    print(f" - {OUTPUT_CSV}")
    print(f" - {COL2_CSV}")
    print("=" * 75)

if __name__ == '__main__':
    max_limit = 0
    if len(sys.argv) > 1:
        arg = str(sys.argv[1]).strip().lower()
        if arg not in ['all', '0', '-1', 'full']:
            try: max_limit = int(arg)
            except: max_limit = 0
    asyncio.run(main(max_limit))
