# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU REKVIZITAI.VZ.LT - NGÀNH GỖ VÀ NỘI THẤT LITVA (LT_WOOD_REKV)
CHẾ ĐỘ GOOGLE CHROME THỰC TẾ (NATIVE GOOGLE CHROME VIA REMOTE DEBUGGING CDP)
================================================================================
Nguồn cào mục tiêu:
1. https://rekvizitai.vz.lt/paieskos-frazes/medienos+apdirbimas/ (Chế biến gỗ & Lâm sản)
2. https://rekvizitai.vz.lt/imones/baldai_gamyba/ (Sản xuất nội thất)

TẠI SAO SỬ DỤNG GOOGLE CHROME THẬT 100% (NATIVE GOOGLE CHROME)?
1. Không phải trình duyệt giả lập Chromium của thư viện bot: Khởi chạy trực tiếp file
   chrome.exe từ hệ điều hành Windows, mang đầy đủ chữ ký số, chứng chỉ TLS, Widevine và GPU thực tế.
2. Không bị cắm cờ tự động hóa (--enable-automation) và không bị inject Runtime.enable ban đầu:
   Cloudflare Turnstile nhận diện đây là người dùng mở Chrome từ Desktop Windows 100%.
3. Người dùng click giải Turnstile 1 lần duy nhất: Cloudflare hiện ngay tích xanh (V),
   hoàn toàn KHÔNG BỊ LẶP LẠI (chấm dứt triệt để Turnstile Looping).
4. Phân trang bằng Click Link DOM: Các trang tiếp theo bấm lật trang trực tiếp trên giao diện,
   bảo toàn phiên duyệt web tự nhiên, không bị hỏi lại Captcha!
5. Bóc tách dữ liệu và tự động hợp nhất làm giàu 1 lượt với file Info.lt (LT_WOOD_INLT_0RAW.csv).
"""

import sys
import os
import re
import csv
import json
import time
import socket
import asyncio
import subprocess
import unicodedata
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

# Tệp đầu ra Rekvizitai độc lập (Chuẩn 17 ký tự)
REKV_RAW_CSV = ROOT_DIR / "LT_WOOD_REKV_0RAW.csv"
REKV_COL2_CSV = ROOT_DIR / "LT_WOOD_REKV_2COL.csv"

# Tệp đầu ra Hợp Nhất Đa Nguồn (Info.lt + Rekvizitai)
COMB_RAW_CSV = ROOT_DIR / "LT_WOOD_COMB_0RAW.csv"
COMB_COL2_CSV = ROOT_DIR / "LT_WOOD_COMB_2COL.csv"
COMB_READY_CSV = ROOT_DIR / "LT_WOOD_COMB_ONLY_EMAILS_READY.csv"

# Cache & Profile
LISTING_CACHE_FILE = ROOT_DIR / "crawlmail" / "listing_rekvizitai_wood.json"
DETAIL_CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_rekvizitai_wood.json"
NATIVE_CHROME_PROFILE = Path.home() / ".gemini" / "antigravity" / "chrome_wood_native"

# Tệp Info.lt đã cào để hợp nhất
INFOLT_RAW_CSV = ROOT_DIR / "LT_WOOD_INLT_0RAW.csv"

ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

CATEGORIES = [
    {
        "name": "Medienos apdirbimas",
        "en_name": "Wood Processing",
        "base_url": "https://rekvizitai.vz.lt/paieskos-frazes/medienos+apdirbimas/1/",
        "pattern": "/paieskos-frazes/medienos+apdirbimas/{page}/",
        "default_max": 100
    },
    {
        "name": "Baldų gamyba",
        "en_name": "Furniture Manufacturing",
        "base_url": "https://rekvizitai.vz.lt/imones/baldai_gamyba/1/",
        "pattern": "/imones/baldai_gamyba/{page}/",
        "default_max": 80
    }
]

HEADERS_20COL = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

COLUMNS_RAW = [
    'No.', 'Company_Code', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'VAT_Code', 'Nguoi quan ly', 'Chuc danh',
    'Average_Wage', 'So nhan vien', 'Nam thanh lap', 'Source_URL'
]

# Rule 12: Danh sách đen vĩnh viễn
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone(raw):
    """Chuẩn hóa SĐT Litva: luôn có nháy đơn (') ở đầu theo Rule 2."""
    if not raw or str(raw).strip() in ['', 'None', 'nan']:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip().lstrip("'"))
    if not p:
        return ""
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and (len(p) == 9 or len(p) == 10):
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    elif p.startswith("370") and not p.startswith("+"):
        p = "+" + p

    digits = re.sub(r'\D', '', p)
    if digits.startswith('370') and len(digits) == 11:
        if digits[3] == '6':
            formatted = f"+370 {digits[3:6]} {digits[6:]}"
        elif digits[3] == '5':
            formatted = f"+370 {digits[3]} {digits[4:7]} {digits[7:]}"
        else:
            formatted = f"+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        return f"'{formatted}"
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    return em.lower()

def is_valid_email(email):
    e = clean_email(email)
    if not e or '@' not in e or len(e) < 6 or len(e) > 80:
        return False
    bad_parts = ['sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail', 'someone', 'no-reply', 'donotreply', 'privacy', 'gdpr']
    if any(b in e for b in bad_parts):
        return False
    ext = e.split('.')[-1]
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf']:
        return False
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e))

def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email B2B cho thị trường Litva theo Rule 3"""
    e = clean_email(email)
    if not is_valid_email(e):
        return -1
    u, d = e.split('@', 1)
    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 25

    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'prezidentas']:
        score += 45
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
    elif u in ['komercija', 'pardavimai', 'uzsakymai', 'sales', 'prekyba']:
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    return score

def decode_cf(email_code):
    try:
        r = int(email_code[:2], 16)
        email = ''.join([chr(int(email_code[i:i+2], 16) ^ r) for i in range(2, len(email_code), 2)])
        return email.strip().lower()
    except Exception:
        return ""

def launch_native_google_chrome(port=9222):
    """Khởi chạy trình duyệt Google Chrome THẬT 100% của Windows"""
    NATIVE_CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

    # Kiểm tra xem cổng 9222 đã có Chrome đang chạy chưa
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.8):
            print(f"[*] Phát hiện Google Chrome thật đang chạy sẵn trên cổng {port}. Kết nối ngay...")
            return None
    except Exception:
        pass

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe")
    ]
    chrome_exe = next((p for p in chrome_paths if os.path.exists(p)), None)
    if not chrome_exe:
        raise RuntimeError("Không tìm thấy tệp chrome.exe trên máy tính! Vui lòng cài đặt Google Chrome.")

    print(f"\n[*] Đang khởi chạy Google Chrome THẬT 100% từ hệ thống:")
    print(f"    Exe    : {chrome_exe}")
    print(f"    Profile: {NATIVE_CHROME_PROFILE}")
    print(f"    Port   : {port}")

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={NATIVE_CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized"
    ]
    proc = subprocess.Popen(cmd)
    time.sleep(2.5)
    return proc

async def wait_for_human_verification(page):
    """Kiểm tra và kiên nhẫn chờ người dùng click trên Google Chrome thật"""
    alert_printed = False
    while True:
        try:
            if page.is_closed():
                return False
            title = await page.title()
            content = await page.content()

            # 1. Kiểm tra Captcha nội bộ Rekvizitai (Form nhập mã 3 ký tự)
            if await page.query_selector("#formFirmsCaptcha, input#security_code"):
                if not alert_printed:
                    print("\a\n" + "!" * 80)
                    print("[CẢNH BÁO CAPTCHA REKVIZITAI] PHÁT HIỆN FORM MÃ 3 KÝ TỰ TRÊN MÀN HÌNH GOOGLE CHROME!")
                    print("-> Vui lòng nhìn sang cửa sổ Google Chrome: nhập 3 ký tự và bấm Tęsti...")
                    print("-> Hệ thống đang kiên nhẫn chờ bạn nhập xong để tiếp tục...")
                    print("!" * 80 + "\n")
                    alert_printed = True
                await asyncio.sleep(2.0)
                continue

            # 2. Kiểm tra Cloudflare Turnstile Challenge
            is_cf = (
                "Just a moment" in title
                or "Luktelėkite" in title
                or "DDoS protection" in content
                or "cf-turnstile" in content
                or "challenges.cloudflare.com" in content
            )
            has_content = (
                ("rekvizitai" in title.lower() or "baldai" in title.lower() or "medienos" in title.lower())
                and await page.query_selector(".company-info-wr, .company-title, .company, a[href*='/imone/']") is not None
            )

            if has_content and not is_cf:
                return True

            if not alert_printed:
                print("\a\n" + "=" * 80)
                print("[XÁC THỰC CLOUDFLARE TRÊN GOOGLE CHROME THẬT]")
                print("-> Cửa sổ Google Chrome thật đã mở trên màn hình.")
                print("-> Vui lòng dùng chuột CLICK vào ô xác nhận 'Verify you are human' nếu xuất hiện.")
                print("-> Vì đây là Google Chrome thật 100%, bạn chỉ cần click 1 LẦN DUY NHẤT là qua ngay!")
                print("=" * 80 + "\n")

    # Tự động lọc trùng tên công ty triệt để
    try:
        from crawlmail.dedup_wood_companies import deduplicate_dataset
        deduplicate_dataset(COMB_RAW_CSV, COMB_RAW_CSV, COMB_COL2_CSV, COMB_READY_CSV)
    except Exception as e:
        print(f"[!] Warning deduplicating: {e}")
                alert_printed = True

            await asyncio.sleep(2.0)
        except Exception:
            await asyncio.sleep(2.0)

async def crawl_site_for_email_visual(page, web_url):
    """Mở trực quan website công ty trên Chrome để quét Email B2B."""
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith("http"):
        web_url = "https://" + web_url

    try:
        parsed = urllib.parse.urlparse(web_url)
        domain = parsed.netloc.replace('www.', '').lower()
        if not domain or len(domain) < 4:
            return ""
    except Exception:
        return ""

    found_emails = set()

    try:
        await page.goto(web_url, wait_until='domcontentloaded', timeout=12000)
        await asyncio.sleep(0.8)
        actual_url = page.url or web_url
        parsed_actual = urllib.parse.urlparse(actual_url)
        domain = parsed_actual.netloc.replace('www.', '').lower()

        html = await page.content()

        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
            clean_m = clean_email(m.split('?')[0])
            if is_valid_email(clean_m):
                found_emails.add(clean_m)

        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
            dec = decode_cf(cf)
            if is_valid_email(dec):
                found_emails.add(dec)

        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', html):
            em_clean = clean_email(em)
            if is_valid_email(em_clean):
                found_emails.add(em_clean)

        contact_sublinks = []
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            txt = a.get_text().lower()
            if any(k in h.lower() or k in txt for k in ['kontakt', 'contact', 'apie', 'karjer', 'darb', 'about']):
                full = urllib.parse.urljoin(actual_url, h)
                if domain in full.lower() and full not in contact_sublinks and '#' not in h:
                    contact_sublinks.append(full)

        contact_sublinks.sort(key=lambda u: 0 if any(k in u.lower() for k in ['contact', 'kontakt']) else 1)

        for cl in contact_sublinks[:3]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=8000)
                await asyncio.sleep(0.6)
                sub_html = await page.content()
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                    clean_m = clean_email(m.split('?')[0])
                    if is_valid_email(clean_m):
                        found_emails.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', sub_html):
                    dec = decode_cf(cf)
                    if is_valid_email(dec):
                        found_emails.add(dec)
                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', sub_html):
                    em_clean = clean_email(em)
                    if is_valid_email(em_clean):
                        found_emails.add(em_clean)
                if found_emails and any(score_email_b2b_lt(e, domain) >= 60 for e in found_emails):
                    break
            except Exception:
                pass
    except Exception:
        pass

    if not found_emails:
        return ""

    best_email = max(found_emails, key=lambda e: score_email_b2b_lt(e, domain))
    return best_email

def parse_card_info(c, cat_name):
    """Bóc tách toàn bộ thông tin có sẵn ngay trên thẻ danh sách Rekvizitai"""
    title_a = c.select_one('a.company-title, a.title, a[href*="/imone/"]')
    if not title_a:
        return None
    name_card = title_a.get_text(' ', strip=True).replace('"', '').replace('„', '').replace('“', '')
    href = title_a.get('href', '')
    if not href or '/imone/' not in href:
        return None
    full_detail = href if href.startswith("http") else f"https://rekvizitai.vz.lt{href}"

    card_text = c.get_text(' | ', strip=True)

    code = ""
    m_code = re.search(r'kodas\s*[:\s]*(\d{7,10})', card_text, re.I)
    if not m_code:
        m_code = re.search(r'\b(\d{9})\b', card_text)
    if m_code:
        code = m_code.group(1)

    phone = ""
    m_phone = re.search(r'(?:Tel\.?|Mob\.?|Telefonas)\s*[:\s]*([0-9\s()+-]+)', card_text, re.I)
    if m_phone:
        phone = clean_phone(m_phone.group(1))

    addr = ""
    addr_elem = c.select_one('.address, [class*="address"]')
    if addr_elem:
        addr = addr_elem.get_text(' ', strip=True).rstrip('.')
    else:
        for part in card_text.split('|'):
            p_strip = part.strip()
            if any(k in p_strip.lower() for k in [' g.', ' al.', ' pl.', ' k.', ' r.', 'gatvė', 'vilnius', 'kaunas', 'klaipėda']):
                addr = p_strip
                break

    city = ""
    zipcode = ""
    m_zip = re.search(r'LT-(\d{5})', addr)
    if m_zip:
        zipcode = m_zip.group(1)
        after_zip = addr.split(f"LT-{zipcode}")
        if len(after_zip) > 1:
            city = after_zip[1].strip().lstrip(',').strip()

    return {
        'detail_url': full_detail,
        'name': name_card,
        'code': code,
        'phone': phone,
        'address': addr,
        'zipcode': zipcode,
        'city': city,
        'category': cat_name
    }

async def harvest_all_listings(page):
    """Thu thập toàn bộ thẻ công ty từ 2 danh mục Rekvizitai bằng Google Chrome thật"""
    print("\n" + "=" * 80)
    print(" BƯỚC 1: THU THẬP DANH SÁCH BẰNG GOOGLE CHROME THẬT (CLICK LẬT TRANG DOM)")
    print("=" * 80)

    listings = {}
    if LISTING_CACHE_FILE.exists():
        try:
            with open(LISTING_CACHE_FILE, "r", encoding="utf-8") as f:
                listings = json.load(f)
            if len(listings) >= 1200:
                print(f"[*] Đã nạp từ Listing Cache: {len(listings):,} công ty hợp nhất từ trước.")
                return listings
        except Exception:
            pass

    for cat_info in CATEGORIES:
        cat_name = cat_info["name"]
        base_url = cat_info["base_url"]
        pattern = cat_info["pattern"]
        max_page = cat_info["default_max"]

        print(f"\n[+] Khởi động danh mục: {cat_name}...")
        print(f"    -> Mở trang đầu: {base_url}")

        await page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
        await wait_for_human_verification(page)
        await asyncio.sleep(1.0)

        current_page = 1
        consecutive_empty = 0

        while current_page <= max_page:
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            cards = soup.select('.company-info-wr, .company, [class*="firm"]')

            if not cards and soup.select_one('#formFirmsCaptcha, input#security_code'):
                await wait_for_human_verification(page)
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                cards = soup.select('.company-info-wr, .company, [class*="firm"]')

            new_in_page = 0
            for c in cards:
                card_data = parse_card_info(c, cat_name)
                if not card_data:
                    continue

                d_url = card_data['detail_url']
                key = d_url.rstrip('/')

                if key not in listings:
                    listings[key] = {
                        "card_name": card_data['name'],
                        "detail_url": d_url,
                        "card_address": card_data['address'],
                        "code": card_data['code'],
                        "phone": card_data['phone'],
                        "city": card_data['city'],
                        "zipcode": card_data['zipcode'],
                        "categories": [cat_name]
                    }
                    new_in_page += 1
                else:
                    if cat_name not in listings[key]["categories"]:
                        listings[key]["categories"].append(cat_name)

            print(f"    -> Trang {current_page:02d}: +{new_in_page} mới | Lũy kế gộp: {len(listings):,}")

            if new_in_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3 and current_page > 5:
                    print(f"    [*] Đã đến trang cuối của danh mục {cat_name}.")
                    break
            else:
                consecutive_empty = 0

            # LẬT TRANG TIẾP THEO BẰNG CLICK LINK DOM TRÊN GOOGLE CHROME THẬT
            next_page_num = current_page + 1
            next_link = await page.query_selector(f"a[href*='/{next_page_num}/']")
            if next_link:
                try:
                    await next_link.click()
                    await page.wait_for_timeout(2500)
                except Exception:
                    next_url = f"https://rekvizitai.vz.lt{pattern.format(page=next_page_num)}"
                    await page.goto(next_url, wait_until='domcontentloaded', timeout=30000)
                    await wait_for_human_verification(page)
            else:
                next_btn = await page.query_selector("a.next, .pagination a:has-text('›'), .pages a:has-text('›')")
                if next_btn:
                    try:
                        await next_btn.click()
                        await page.wait_for_timeout(2500)
                    except Exception:
                        break
                else:
                    print(f"    [*] Hoàn tất toàn bộ trang của {cat_name}.")
                    break

            current_page += 1

    with open(LISTING_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)

    print(f"\n[✔] HOÀN TẤT BƯỚC 1: Đã thu thập {len(listings):,} công ty từ Rekvizitai!\n")
    return listings

async def harvest_and_enrich_details(page, listings):
    """Bóc tách chi tiết & làm giàu Email B2B"""
    print("\n" + "=" * 80)
    print(" BƯỚC 2 & 3: BÓC TÁCH CHI TIẾT DOANH NGHIỆP & LÀM GIÀU EMAIL B2B")
    print("=" * 80)

    detail_cache = {}
    if DETAIL_CACHE_FILE.exists():
        try:
            with open(DETAIL_CACHE_FILE, "r", encoding="utf-8") as f:
                detail_cache = json.load(f)
            print(f"[*] Nạp Cache Chi tiết: {len(detail_cache):,} công ty đã hoàn tất từ trước.")
        except Exception:
            pass

    total_total = len(listings)
    processed = 0

    for idx, (detail_url, info) in enumerate(listings.items(), 1):
        if detail_url in detail_cache:
            processed += 1
            continue

        print(f"[{idx:04d}/{total_total:04d}] {info['card_name'][:28]:<28} | ", end="", flush=True)

        official_name = info["card_name"]
        manager = ""
        phone = info.get("phone", "")
        web = ""
        code = info.get("code", "")
        vat_code = ""
        address = info.get("card_address", "")
        city = info.get("city", "")
        zipcode = info.get("zipcode", "")
        employees = ""
        wage = ""

        try:
            if page.is_closed():
                page = await page.context.new_page()

            await page.goto(detail_url, wait_until='domcontentloaded', timeout=18000)
            await wait_for_human_verification(page)
            await asyncio.sleep(0.4)

            detail_html = await page.content()
            soup = BeautifulSoup(detail_html, 'html.parser')

            h1 = soup.find('h1')
            if h1:
                official_name = h1.get_text(' ', strip=True).replace('"', '').replace('„', '').replace('“', '')

            for tr in soup.find_all('tr'):
                td_name = tr.find('td', class_='name')
                td_val = tr.find('td', class_='value')
                if not td_name or not td_val:
                    continue
                k = td_name.get_text(strip=True).lower()
                v = td_val.get_text(' ', strip=True)

                if any(x in k for x in ['vadov', 'direktor', 'manager', 'head']):
                    manager = v.replace('More ›', '').replace('Daugiau ›', '').strip()
                elif any(x in k for x in ['telefon', 'mobil', 'phone', 'tel']):
                    if not phone:
                        phone = clean_phone(v)
                elif any(x in k for x in ['tinklalap', 'website', 'web']):
                    w_a = td_val.find('a', href=True)
                    if w_a and w_a['href'].startswith('http'):
                        web = w_a['href'].strip()
                    else:
                        web = v.replace('Uždaryti', '').replace('Close', '').strip()
                elif any(x in k for x in ['įmonės kodas', 'imones kodas', 'kodas', 'code']):
                    if not code:
                        m_code = re.search(r'\b(\d{7,10})\b', v)
                        if m_code:
                            code = m_code.group(1)
                elif any(x in k for x in ['pvm', 'vat']):
                    vat_code = v.strip()
                elif any(x in k for x in ['adres', 'address']):
                    if not address:
                        addr_a = td_val.find('a', href=True)
                        address = addr_a.get_text(' ', strip=True).strip() if addr_a else v.strip()
                elif any(x in k for x in ['darbuotoj', 'employees']):
                    employees = v.strip()
                elif any(x in k for x in ['atlyginim', 'wage', 'salary']):
                    wage = v.strip()

        except Exception as e:
            print(f"Lỗi đọc trang: {e} | ", end="", flush=True)

        found_email = ""
        if web:
            found_email = await crawl_site_for_email_visual(page, web)
            em_log = f"EMAIL: {found_email}" if found_email else "(Chưa thấy mail)"
            print(f"SĐT: {phone:<18} | {em_log}")
        else:
            print(f"SĐT: {phone:<18} | (Không có web)")

        cat_str = " | ".join(info["categories"])

        record = {
            'No.': str(idx),
            'Company_Code': code,
            'Cong ty': official_name,
            'Ten phap ly': official_name,
            'SDT': clean_phone(phone),
            'Email': found_email,
            'Website': web,
            'Dia chi': address,
            'Ma buu dien': zipcode,
            'Khu vuc': '',
            'Thanh pho': city,
            'Tag_Chinh': cat_str,
            'All_Tags': cat_str,
            'VAT_Code': vat_code,
            'Nguoi quan ly': manager,
            'Chuc danh': 'Vadovas / Direktorius' if manager else '',
            'Average_Wage': wage,
            'So nhan vien': employees,
            'Nam thanh lap': '',
            'Source_URL': detail_url
        }

        detail_cache[detail_url] = record
        processed += 1

        if processed % 10 == 0:
            with open(DETAIL_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(detail_cache, f, ensure_ascii=False, indent=2)
            save_rekvizitai_csv(detail_cache)
            print(f"  >>> [AUTO-SAVE] Checkpoint Rekvizitai: {len(detail_cache):,} công ty.")

    with open(DETAIL_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(detail_cache, f, ensure_ascii=False, indent=2)

    save_rekvizitai_csv(detail_cache)
    return detail_cache

def save_rekvizitai_csv(detail_cache):
    """Lưu dữ liệu cào từ Rekvizitai thành file CSV chuẩn"""
    records = list(detail_cache.values())
    valid = [r for r in records if not is_blacklisted_company(r.get('Cong ty', ''))]

    with_em = [r for r in valid if r.get('Email') and '@' in r.get('Email')]
    without_em = [r for r in valid if not r.get('Email') or '@' not in r.get('Email')]
    sorted_raw = with_em + without_em
    for i, r in enumerate(sorted_raw, 1):
        r['No.'] = str(i)

    REKV_RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted_raw, columns=COLUMNS_RAW).to_csv(REKV_RAW_CSV, index=False, encoding='utf-8-sig')

    col20_rows = []
    for r in sorted_raw:
        c_name = r.get('Cong ty', '')
        c_leader = r.get('Nguoi quan ly', '')
        c_phone = r.get('SDT', '')
        c_email = r.get('Email', '')
        c_web = r.get('Website', '')
        c_addr = r.get('Dia chi', '')

        row = {
            'No.': r.get('No.', ''),
            'Công ty': c_name,
            'Chức danh': r.get('Chuc danh', '') or 'Vadovas / Direktorius',
            'Người liên hệ': c_leader,
            'SĐT': c_phone,
            'Liên Hệ': c_web,
            'Email': c_email,
            'Liên Hệ mail': f"mailto:{c_email}" if c_email else '',
            'Địa chỉ': c_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if c_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Gỗ & Nội thất')
        }
        col20_rows.append(row)

    pd.DataFrame(col20_rows, columns=HEADERS_20COL).to_csv(REKV_COL2_CSV, index=False, encoding='utf-8-sig')

def normalize_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['uab', 'mb', 'vsi', 'ii', 'ab', 'as', 'sro', 'gmbh', 'ltd']:
        n = re.sub(rf'\b{legal}\b', '', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n.strip()

def merge_infolt_and_rekvizitai():
    """HỢP NHẤT VÀ LÀM GIÀU 1 LƯỢT: Info.lt + Rekvizitai.vz.lt"""
    print("\n" + "=" * 80)
    print(" BƯỚC 4: HỢP NHẤT DỮ LIỆU ĐA NGUỒN (INFO.LT + REKVIZITAI.VZ.LT)")
    print("=" * 80)

    infolt_dict = {}
    if INFOLT_RAW_CSV.exists():
        df_infolt = pd.read_csv(INFOLT_RAW_CSV, encoding='utf-8-sig', dtype=str).fillna('')
        for _, row in df_infolt.iterrows():
            rec = row.to_dict()
            code = rec.get('Company_Code', '').strip()
            name_norm = normalize_name(rec.get('Cong ty', ''))
            key = code if code and len(code) >= 7 else f"name_{name_norm}"
            infolt_dict[key] = rec
        print(f"[*] Nạp từ Info.lt: {len(infolt_dict):,} doanh nghiệp.")

    rekv_dict = {}
    if REKV_RAW_CSV.exists():
        df_rekv = pd.read_csv(REKV_RAW_CSV, encoding='utf-8-sig', dtype=str).fillna('')
        for _, row in df_rekv.iterrows():
            rec = row.to_dict()
            code = rec.get('Company_Code', '').strip()
            name_norm = normalize_name(rec.get('Cong ty', ''))
            key = code if code and len(code) >= 7 else f"name_{name_norm}"
            rekv_dict[key] = rec
        print(f"[*] Nạp từ Rekvizitai: {len(rekv_dict):,} doanh nghiệp.")

    master = {}

    for k, v in infolt_dict.items():
        master[k] = dict(v)

    enrich_count = 0
    new_from_rekv = 0

    for k, r_item in rekv_dict.items():
        if k in master:
            target = master[k]
            if not target.get('Email') and r_item.get('Email'):
                target['Email'] = r_item['Email']
                enrich_count += 1
            if not target.get('SDT') and r_item.get('SDT'):
                target['SDT'] = r_item['SDT']
            if not target.get('Nguoi quan ly') and r_item.get('Nguoi quan ly'):
                target['Nguoi quan ly'] = r_item['Nguoi quan ly']
                target['Chuc danh'] = r_item.get('Chuc danh', 'Vadovas / Direktorius')
            if not target.get('Website') and r_item.get('Website'):
                target['Website'] = r_item['Website']
            if not target.get('Company_Code') and r_item.get('Company_Code'):
                target['Company_Code'] = r_item['Company_Code']
            if not target.get('VAT_Code') and r_item.get('VAT_Code'):
                target['VAT_Code'] = r_item['VAT_Code']
            if r_item.get('Tag_Chinh'):
                if r_item['Tag_Chinh'] not in target.get('Tag_Chinh', ''):
                    target['Tag_Chinh'] = f"{target.get('Tag_Chinh', '')} | Rekv: {r_item['Tag_Chinh']}".strip(' | ')
        else:
            master[k] = dict(r_item)
            new_from_rekv += 1

    all_master = list(master.values())
    valid_master = [r for r in all_master if not is_blacklisted_company(r.get('Cong ty', ''))]

    with_em = [r for r in valid_master if r.get('Email') and '@' in r.get('Email')]
    without_em = [r for r in valid_master if not r.get('Email') or '@' not in r.get('Email')]
    sorted_comb = with_em + without_em
    for i, r in enumerate(sorted_comb, 1):
        r['No.'] = str(i)

    COMB_RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted_comb, columns=COLUMNS_RAW).to_csv(COMB_RAW_CSV, index=False, encoding='utf-8-sig')

    col20_master = []
    for r in sorted_comb:
        c_name = r.get('Cong ty', '')
        c_leader = r.get('Nguoi quan ly', '')
        c_phone = r.get('SDT', '')
        c_email = r.get('Email', '')
        c_web = r.get('Website', '')
        c_addr = r.get('Dia chi', '')

        row = {
            'No.': r.get('No.', ''),
            'Công ty': c_name,
            'Chức danh': r.get('Chuc danh', '') or 'Vadovas / Direktorius',
            'Người liên hệ': c_leader,
            'SĐT': c_phone,
            'Liên Hệ': c_web,
            'Email': c_email,
            'Liên Hệ mail': f"mailto:{c_email}" if c_email else '',
            'Địa chỉ': c_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if c_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Gỗ & Nội thất')
        }
        col20_master.append(row)

    df_col2_master = pd.DataFrame(col20_master, columns=HEADERS_20COL)
    df_col2_master.to_csv(COMB_COL2_CSV, index=False, encoding='utf-8-sig')

    df_ready_master = df_col2_master[df_col2_master['Email'].str.contains('@', na=False)].copy()
    for i, _ in enumerate(df_ready_master.index, 1):
        df_ready_master.iloc[i-1, df_ready_master.columns.get_loc('No.')] = str(i)
    df_ready_master.to_csv(COMB_READY_CSV, index=False, encoding='utf-8-sig')

    CSDL_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    df_col2_master.to_csv(CSDL_DIR / COMB_COL2_CSV.name, index=False, encoding='utf-8-sig')
    df_col2_master.to_csv(ARCHIVE_DIR / COMB_COL2_CSV.name, index=False, encoding='utf-8-sig')
    pd.DataFrame(sorted_comb, columns=COLUMNS_RAW).to_csv(ARCHIVE_DIR / COMB_RAW_CSV.name, index=False, encoding='utf-8-sig')
    df_ready_master.to_csv(ARCHIVE_DIR / COMB_READY_CSV.name, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 80)
    print(" BÁO CÁO HỢP NHẤT TOÀN DIỆN (INFO.LT + REKVIZITAI.VZ.LT)")
    print(f" - Tổng doanh nghiệp sau hợp nhất     : {len(valid_master):,}")
    print(f" - Doanh nghiệp mới từ Rekvizitai     : +{new_from_rekv:,}")
    print(f" - Doanh nghiệp được bổ sung Email    : +{enrich_count:,}")
    print(f" - Tổng Doanh nghiệp CÓ EMAIL B2B     : {len(with_em):,} (Dòng 1..{len(with_em)})")
    print(f" - File RAW Tổng Hợp                  : {COMB_RAW_CSV.name}")
    print(f" - File Cold Mail 20 cột Tổng Hợp     : {COMB_COL2_CSV.name}")
    print(f" - File Ready to Send (Chỉ có Email)  : {COMB_READY_CSV.name}")
    print("=" * 80 + "\n")

    # Tự động lọc trùng tên công ty triệt để
    try:
        from crawlmail.dedup_wood_companies import deduplicate_dataset
        deduplicate_dataset(COMB_RAW_CSV, COMB_RAW_CSV, COMB_COL2_CSV, COMB_READY_CSV)
    except Exception as e:
        print(f"[!] Warning deduplicating: {e}")

async def main():
    print("=" * 80)
    print(" HỆ THỐNG CÀO REKVIZITAI.VZ.LT - NGÀNH GỖ VÀ NỘI THẤT LITVA")
    print(" CHẾ ĐỘ NATIVE GOOGLE CHROME (THẬT 100% CỦA WINDOWS - VƯỢT TURNSTILE)")
    print("=" * 80)

    # 1. Khởi chạy Google Chrome thật của hệ thống
    chrome_proc = launch_native_google_chrome(port=9222)

    try:
        async with async_playwright() as p:
            print("[*] Đang kết nối tới Google Chrome thật qua cổng 9222...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            # 2. Thu thập thẻ công ty qua Google Chrome thật (Click DOM lật trang)
            listings = await harvest_all_listings(page)

            # 3. Bóc tách chi tiết & làm giàu Email B2B
            await harvest_and_enrich_details(page, listings)

            await browser.close()
    finally:
        if chrome_proc:
            try:
                chrome_proc.terminate()
            except Exception:
                pass

    # 4. Hợp nhất và làm giàu chéo với Info.lt
    merge_infolt_and_rekvizitai()

if __name__ == '__main__':
    asyncio.run(main())
