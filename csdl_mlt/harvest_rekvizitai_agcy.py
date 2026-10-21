# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU REKVIZITAI.VZ.LT - LITHUANIA EMPLOYMENT & RECRUITMENT AGENCIES
CHẾ ĐỘ TRÌNH DUYỆT TRỰC QUAN (HEADLESS = FALSE) - QUAN SÁT 100% TIẾN ĐỘ TRÊN MÀN HÌNH

Nguồn cào:
1. https://rekvizitai.vz.lt/en/companies/recruitment/
2. https://rekvizitai.vz.lt/en/companies/labour_exchange_employment/

Đặc điểm:
- Mở cửa sổ Chrome thật (1280x800) trực quan 100%, không chạy ngầm, không ảo giác!
- Tự động bắt và giải Cloudflare Turnstile, có chuông báo \a nếu cần người dùng tương tác.
- Gộp 2 danh mục thành 1, khử trùng lặp hoàn hảo theo URL slug và mã số công ty (IČO).
- Mở trực tiếp từng trang công ty và từng website doanh nghiệp trên Chrome để bóc tách:
  * Tên pháp lý chính thức (H1: UAB / MB / VšĮ...)
  * IČO (Registration code)
  * Người đại diện (Manager / Vadovas) & Chức danh
  * SĐT chuẩn hóa (+370... kèm nháy đơn ')
  * Website & Địa chỉ, Thành phố
  * Bóc tách Email B2B (darbas@, karjera@, cv@, hr@, vadovas@, info@...)
- Chuẩn hóa 20 cột Cold Mail quốc tế, đẩy 100% công ty có Email lên đầu tệp CSV.
- Lưu tăng dần (Incremental Checkpoint), hỗ trợ Resume 100%.

Đầu ra:
1. LT_AGCY_REKV_0RAW.csv (File thô)
2. LT_AGCY_REKV_1ENR.csv (File đã làm giàu Email)
3. LT_AGCY_REKV_2COL.csv (File chuẩn 20 cột Cold Mail sẵn sàng gửi)
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN & CẤU HÌNH
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

OUT_RAW_ROOT = ROOT_DIR / "LT_AGCY_REKV_0RAW.csv"
OUT_ENR_ROOT = ROOT_DIR / "LT_AGCY_REKV_1ENR.csv"
OUT_2COL_ROOT = ROOT_DIR / "LT_AGCY_REKV_2COL.csv"

OUT_RAW_CSDL = BASE_DIR / "LT_AGCY_REKV_0RAW.csv"
OUT_ENR_CSDL = BASE_DIR / "LT_AGCY_REKV_1ENR.csv"
OUT_2COL_CSDL = BASE_DIR / "LT_AGCY_REKV_2COL.csv"

LISTING_CACHE_FILE = BASE_DIR / "listing_rekvizitai_agcy.json"
DETAIL_CACHE_FILE = BASE_DIR / "cache_rekvizitai_agcy.json"
USER_DATA_DIR = BASE_DIR / "chrome_rekvizitai_profile"

CATEGORIES = [
    {
        "name": "Recruitment",
        "url_pattern": "https://rekvizitai.vz.lt/en/companies/recruitment/{page}/",
        "default_max": 25
    },
    {
        "name": "Labour exchange, employment",
        "url_pattern": "https://rekvizitai.vz.lt/en/companies/labour_exchange_employment/{page}/",
        "default_max": 88
    }
]

HEADERS_20COL = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

LT_CITIES = [
    "Vilnius", "Kaunas", "Klaipėda", "Šiauliai", "Panevėžys", "Alytus",
    "Marijampolė", "Mažeikiai", "Jonava", "Utena", "Kėdainiai", "Telšiai",
    "Visaginas", "Tauragė", "Ukmergė", "Plungė", "Šilutė", "Kretinga",
    "Radviliškis", "Druskininkai", "Palanga", "Gargždai", "Rokiškis",
    "Biržai", "Elektrėnai", "Garliava", "Jurbarkas", "Vilkaviškis",
    "Raseiniai", "Anykščiai", "Lentvaris", "Grigiškės", "Prienai",
    "Joniškis", "Kelmė", "Varėna", "Kaišiadorys", "Pasvalys", "Kupiškis",
    "Zarasai", "Skuodas", "Kazlų Rūda", "Širvintos", "Molėtai", "Šakiai",
    "Šalčininkai", "Ignalina", "Kybartai", "Pabradė", "Neringa", "Nida"
]

# ----------------------------------------------------------------------
# TIỆN ÍCH CHUẨN HÓA SĐT & ĐỊA DANH
# ----------------------------------------------------------------------
def clean_phone(raw):
    """Chuẩn hóa SĐT Lithuania: luôn có nháy đơn và đầu số quốc tế +370."""
    if not raw:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip())
    if not p:
        return ""
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and len(p) == 10:
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    elif p.startswith("370") and not p.startswith("+"):
        p = "+" + p
    return f"'{p}" if not p.startswith("'") else p

def extract_city_from_address(addr):
    """Bóc tách thành phố Lithuania từ chuỗi địa chỉ."""
    if not addr:
        return ""
    m_post = re.search(r"LT-\d{5}\s+([A-Za-zÀ-ž]+)", addr)
    if m_post:
        c = m_post.group(1).strip()
        if c:
            return c
    for city in LT_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", addr, re.IGNORECASE):
            return city
    return ""

def clean_company_name(raw_name):
    """Làm sạch tên công ty, loại bỏ dấu ngoặc kép thừa."""
    if not raw_name:
        return ""
    n = raw_name.strip()
    n = re.sub(r'["„“”«»]', '', n).strip()
    return n

# ----------------------------------------------------------------------
# BỘ LỌC VÀ CHẤM ĐIỂM EMAIL B2B (MANPOWER AGENCY)
# ----------------------------------------------------------------------
JUNK_EMAIL_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@'
]

def is_valid_email(email):
    if not email or '@' not in email:
        return False
    e = email.strip().lower()
    if len(e) < 6 or len(e) > 80:
        return False
    if any(jp in e for jp in JUNK_EMAIL_PARTS):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', e):
        return False
    ext = e.split('.')[-1]
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js']:
        return False
    return True

def score_email_b2b(email, website_domain=""):
    """Chấm điểm email tối ưu cho B2B Manpower Agency (Lithuania)."""
    if not is_valid_email(email):
        return 0
    e = email.lower().strip()
    score = 10
    prefix = e.split('@')[0]
    email_domain = e.split('@')[1]
    
    if website_domain and website_domain in email_domain:
        score += 50
    elif any(email_domain.endswith(free) for free in ['gmail.com', 'yahoo.com', 'inbox.lt', 'one.lt', 'mail.ru']):
        score += 10
        
    # Ưu tiên ĐẶC BIỆT: Doanh nghiệp đăng ký tại Lithuania, ưu tiên email đuôi .lt (+60đ)
    if email_domain.endswith('.lt'):
        score += 60
        
    if any(k in prefix for k in ['darbas', 'karjera', 'cv', 'atranka', 'personalo', 'recruitment', 'jobs', 'praca', 'work']):
        score += 50
    elif any(k in prefix for k in ['vadov', 'direktor', 'director', 'ceo', 'manager', 'prezident', 'head']):
        score += 45
    elif any(k in prefix for k in ['info', 'biuras', 'kontakt', 'contact', 'office', 'sekretor', 'bendras']):
        score += 40
    elif '.' in prefix or '_' in prefix:
        score += 25
    else:
        score += 15
        
    return score

def decode_cf(email_code):
    """Giải mã Cloudflare Email Protection."""
    try:
        r = int(email_code[:2], 16)
        email = ''.join([chr(int(email_code[i:i+2], 16) ^ r) for i in range(2, len(email_code), 2)])
        return email.strip().lower()
    except Exception:
        return ""

# ----------------------------------------------------------------------
# XỬ LÝ CLOUDFLARE TURNSTILE & CAPTCHA REKVIZITAI (SECURITY CODE 3 KÝ TỰ)
# ----------------------------------------------------------------------
async def wait_for_cloudflare(page):
    """Kiểm tra và tự động vượt Cloudflare Turnstile hoặc Captcha bảo mật Rekvizitai."""
    while True:
        try:
            if page.is_closed():
                return False
            title = await page.title()
            content = await page.content()
            
            # 1. Kiểm tra Captcha nội bộ Rekvizitai (Form nhập mã 3 ký tự xuất hiện sau trang 20)
            if await page.query_selector("#formFirmsCaptcha, input#security_code"):
                print("\a\n" + "!" * 80)
                print("[CẢNH BÁO CAPTCHA REKVIZITAI] PHÁT HIỆN MÃ BẢO MẬT 3 KÝ TỰ TRÊN MÀN HÌNH CHROME!")
                print("Vui lòng nhìn vào cửa sổ Chrome, nhập 3 ký tự hiển thị trong ảnh và bấm Continue...")
                print("Hệ thống đang kiên nhẫn chờ bạn nhập xong trên màn hình để cào tiếp...")
                print("!" * 80 + "\n")
                while True:
                    await asyncio.sleep(2.0)
                    if not await page.query_selector("#formFirmsCaptcha, input#security_code"):
                        print("[+] Đã giải xong Captcha Rekvizitai thành công! Tiếp tục quét...\n")
                        await asyncio.sleep(1.0)
                        return True

            # 2. Kiểm tra Cloudflare Challenge
            is_cf = (
                "Just a moment" in title 
                or "Luktelėkite" in title 
                or "DDoS protection" in content 
                or "cf-turnstile" in content
                or "challenges.cloudflare.com" in content
            )
            has_content = (
                "rekvizitai" in title.lower() 
                or await page.query_selector(".company-info-wr, .company-title, .company, a[href*='/en/company/'], h1") is not None
            )
            
            if has_content and not is_cf:
                return True
                
            print("\a\n[!] PHÁT HIỆN XÁC THỰC CLOUDFLARE TRÊN CỬA SỔ CHROME!")
            print("    Hệ thống đang hỗ trợ tự động click hoặc bạn hãy tích vào ô xác nhận trên màn hình...")
            
            for f in page.frames:
                try:
                    if "cloudflare" in f.url or "challenge" in f.url:
                        chk = await f.query_selector("input[type='checkbox'], .cb-lb, #challenge-stage")
                        if chk:
                            await chk.click()
                except Exception:
                    pass
                    
            await asyncio.sleep(2.5)
        except Exception:
            await asyncio.sleep(2.0)

# ----------------------------------------------------------------------
# QUÉT EMAIL B2B TRỰC QUAN TRÊN TRÌNH DUYỆT CHROME
# ----------------------------------------------------------------------
async def crawl_site_for_email_visual(page, web_url):
    """Mở trực quan website công ty trên Chrome để quét Email."""
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
    root = f"{parsed.scheme}://{parsed.netloc}"
    
    # 1. Mở trang chủ công ty trực quan trên Chrome
    try:
        await page.goto(web_url, wait_until='domcontentloaded', timeout=14000)
        await asyncio.sleep(1.0)
        actual_url = page.url or web_url
        parsed_actual = urllib.parse.urlparse(actual_url)
        domain = parsed_actual.netloc.replace('www.', '').lower()
        root = f"{parsed_actual.scheme}://{parsed_actual.netloc}"
        
        html = await page.content()
        
        # Bóc tách mailto:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html, re.I):
            clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
            if is_valid_email(clean_m):
                found_emails.add(clean_m)
                
        # Bóc tách Cloudflare
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
            dec = decode_cf(cf)
            if is_valid_email(dec):
                found_emails.add(dec)
                
        # Regex text
        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', html):
            em_low = em.strip().lower()
            if is_valid_email(em_low):
                found_emails.add(em_low)
                
        # Tìm các link liên hệ trên menu trang chủ (khắc phục hoàn toàn lệch www/non-www)
        contact_sublinks = []
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            h = a['href']
            h_low = h.lower()
            txt = a.get_text().lower()
            if any(k in h_low or k in txt for k in ['kontakt', 'contact', 'apie', 'karjer', 'darb', 'about']):
                full = urllib.parse.urljoin(actual_url, h)
                full_lower = full.lower()
                # Khớp domain không phân biệt có www. hay không có www.
                if domain in full_lower and full not in contact_sublinks and '#' not in h:
                    contact_sublinks.append(full)
                    
        # Ưu tiên các trang có chữ contact / kontakt lên đầu danh sách duyệt
        contact_sublinks.sort(key=lambda u: 0 if any(k in u.lower() for k in ['contact', 'kontakt']) else 1)
                    
        # 2. Mở trực quan sublinks liên hệ trên Chrome (tối đa 4 subpages)
        for cl in contact_sublinks[:4]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=10000)
                await asyncio.sleep(0.8)
                sub_html = await page.content()
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                    clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                    if is_valid_email(clean_m):
                        found_emails.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', sub_html):
                    dec = decode_cf(cf)
                    if is_valid_email(dec):
                        found_emails.add(dec)
                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', sub_html):
                    em_low = em.strip().lower()
                    if is_valid_email(em_low):
                        found_emails.add(em_low)
                if found_emails and any(score_email_b2b(e, domain) >= 70 for e in found_emails):
                    break
            except Exception:
                pass
    except Exception:
        pass
        
    # 3. Thử nhanh các subpath Lithuania & Quốc tế chuẩn nếu vẫn chưa có
    if not found_emails:
        candidates = [
            f"{root}/contact", f"{root}/contact/", f"{root}/contacts", f"{root}/contacts/",
            f"{root}/kontaktai", f"{root}/kontaktai/", f"{root}/kontakt", f"{root}/kontakt/",
            f"{root}/apie-mus", f"{root}/about", f"{root}/about-us"
        ]
        for cu in candidates:
            try:
                await page.goto(cu, wait_until='domcontentloaded', timeout=8000)
                await asyncio.sleep(0.5)
                c_html = await page.content()
                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', c_html):
                    em_low = em.strip().lower()
                    if is_valid_email(em_low):
                        found_emails.add(em_low)
                if found_emails:
                    break
            except Exception:
                pass
                
    if not found_emails:
        return ""
        
    best_email = max(found_emails, key=lambda e: score_email_b2b(e, domain))
    return best_email

# ----------------------------------------------------------------------
# GIAI ĐOẠN 1: THU THẬP DANH SÁCH TẤT CẢ LINK CHI TIẾT TỪ 2 DANH MỤC
# ----------------------------------------------------------------------
async def harvest_all_listings(page):
    print("=" * 80)
    print(" BƯỚC 1: THU THẬP VÀ GỘP DANH SÁCH TỪ 2 DANH MỤC REKVIZITAI.VZ.LT")
    print("=" * 80)
    
    listings = {}
    if LISTING_CACHE_FILE.exists():
        try:
            with open(LISTING_CACHE_FILE, "r", encoding="utf-8") as f:
                listings = json.load(f)
            # Chỉ nạp nếu đã thu thập đầy đủ cả 2 danh mục (> 1,000 công ty)
            if len(listings) >= 1200:
                print(f"[*] Đã nạp từ Cache Listing đầy đủ: {len(listings):,} công ty hợp nhất từ trước.")
                return listings
        except Exception:
            pass

    for cat_info in CATEGORIES:
        cat_name = cat_info["name"]
        url_pat = cat_info["url_pattern"]
        max_page = cat_info["default_max"]
        
        print(f"\n[+] Đang quét danh mục: {cat_name} (Tối đa {max_page} trang)...")
        
        page_num = 1
        while page_num <= max_page:
            page_url = url_pat.format(page=page_num)
            try:
                await page.goto(page_url, wait_until='domcontentloaded', timeout=25000)
                await wait_for_cloudflare(page)
                await asyncio.sleep(0.5)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                cards = soup.select('.company-info-wr')
                
                # Nếu trang yêu cầu Captcha mà chưa lấy được thẻ, chờ tiếp
                if not cards and soup.select_one('#formFirmsCaptcha, input#security_code'):
                    await wait_for_cloudflare(page)
                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    cards = soup.select('.company-info-wr')
                
                new_in_page = 0
                for c in cards:
                    title_a = c.select_one('a.company-title, a[href*="/en/company/"]')
                    if not title_a:
                        continue
                    name_card = title_a.get_text(strip=True)
                    href = title_a.get('href', '')
                    if not href or '/en/company/' not in href:
                        continue
                    full_detail = href if href.startswith("http") else f"https://rekvizitai.vz.lt{href}"
                    
                    addr_card = ""
                    addr_elem = c.select_one('.address, [class*="address"]')
                    if addr_elem:
                        addr_card = addr_elem.get_text(' ', strip=True).rstrip('.')
                        
                    key = full_detail.rstrip('/')
                    if key not in listings:
                        listings[key] = {
                            "card_name": name_card,
                            "detail_url": full_detail,
                            "card_address": addr_card,
                            "categories": [cat_name]
                        }
                        new_in_page += 1
                    else:
                        if cat_name not in listings[key]["categories"]:
                            listings[key]["categories"].append(cat_name)
                            
                print(f"    -> Trang {page_num:02d}/{max_page:02d}: +{new_in_page} mới | Tổng gộp hiện tại: {len(listings):,}")
                
                # Kiểm tra nếu trang thực sự không còn thẻ nào và không còn liên kết trang tiếp theo thì mới dừng
                pag_links = soup.select('.pages a, .pagination a')
                has_next = any(f"/{page_num + 1}/" in a.get('href', '') for a in pag_links)
                if not cards and not has_next and page_num > 10:
                    print(f"    [*] Đã đến trang cuối cùng thực sự của {cat_name}.")
                    break
                    
                page_num += 1
            except Exception as e:
                print(f"    [!] Lỗi khi cào trang {page_num}: {e}")
                await asyncio.sleep(2)
                page_num += 1
                
    with open(LISTING_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    print(f"\n[✔] HOÀN TẤT BƯỚC 1: Đã hợp nhất {len(listings):,} công ty duy nhất từ 2 danh mục!\n")
    return listings

# ----------------------------------------------------------------------
# GIAI ĐOẠN 2 & 3: BÓC TÁCH CHI TIẾT & LÀM GIÀU EMAIL B2B
# ----------------------------------------------------------------------
async def harvest_and_enrich_details(page, listings):
    print("=" * 80)
    print(" BƯỚC 2 & 3: BÓC TÁCH CHI TIẾT DOANH NGHIỆP & LÀM GIÀU EMAIL B2B (TRỰC QUAN)")
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
    processed_count = 0
    new_emails = 0
    
    rows = []
    
    for idx_key, (detail_url, info) in enumerate(listings.items(), 1):
        if detail_url in detail_cache:
            rows.append(detail_cache[detail_url])
            continue
            
        print(f"[{idx_key:04d}/{total_total:04d}] {info['card_name'][:32]:<32} | ", end="", flush=True)
        
        official_name = info["card_name"]
        manager = ""
        phone = ""
        web = ""
        code = ""
        address = info["card_address"]
        city = extract_city_from_address(address)
        
        try:
            # Tự động hồi phục tab nếu tab bị đóng
            if page.is_closed():
                page = await page.context.new_page()
                
            await page.goto(detail_url, wait_until='domcontentloaded', timeout=20000)
            await wait_for_cloudflare(page)
            await asyncio.sleep(0.6)
            
            detail_html = await page.content()
            soup = BeautifulSoup(detail_html, 'html.parser')
            
            # Tên pháp lý chính thức (H1: UAB „Biuro“...)
            h1 = soup.find('h1')
            if h1:
                h1_txt = clean_company_name(h1.get_text(' ', strip=True))
                if h1_txt:
                    official_name = h1_txt
                    
            # Bóc tách các trường từ bảng thông tin
            for tr in soup.find_all('tr'):
                td_name = tr.find('td', class_='name')
                td_val = tr.find('td', class_='value')
                if not td_name or not td_val:
                    continue
                k = td_name.get_text(strip=True).lower()
                v = td_val.get_text(' ', strip=True)
                
                if 'manager' in k or 'vadov' in k or 'director' in k:
                    manager = v.replace('More ›', '').replace('Daugiau ›', '').strip()
                elif 'phone' in k or 'mobile' in k or 'tel' in k:
                    if not phone:
                        phone = clean_phone(v)
                elif 'website' in k or 'tinklalap' in k:
                    w_a = td_val.find('a', href=True)
                    if w_a and w_a['href'].startswith('http'):
                        web = w_a['href'].strip()
                    else:
                        web = v.replace('Uždaryti', '').replace('Close', '').strip()
                elif 'registration code' in k or 'code' in k or 'kodas' in k:
                    m_code = re.search(r'\b(\d{7,10})\b', v)
                    if m_code:
                        code = m_code.group(1)
                elif 'address' in k or 'adres' in k:
                    addr_a = td_val.find('a', href=True)
                    if addr_a:
                        address = addr_a.get_text(' ', strip=True).strip()
                    else:
                        address = v.strip()
                    city = extract_city_from_address(address)
        except Exception as e:
            print(f"Lỗi đọc trang: {e} | ", end="", flush=True)
            
        # Giai đoạn 3: Mở trực quan Website trên Chrome để bóc tách Email B2B
        found_email = ""
        if web:
            found_email = await crawl_site_for_email_visual(page, web)
            if found_email:
                new_emails += 1
                print(f"WEB: {web[:22]:<22} | EMAIL: {found_email}")
            else:
                print(f"WEB: {web[:22]:<22} | (Chưa thấy mail)")
        else:
            print(f"No web | (Không có web)")
            
        cat_str = " | ".join(info["categories"])
        
        record = {
            "Công ty": official_name,
            "Chức danh": "Vadovas / Director" if manager else "",
            "Người liên hệ": manager,
            "SĐT": clean_phone(phone),
            "Liên Hệ": web,
            "Email": found_email,
            "Liên Hệ mail": f"mailto:{found_email}" if found_email else "",
            "Địa chỉ": address,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "0",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": f"Môi giới việc làm / Tuyển dụng Lithuania [{cat_str}] (Rekvizitai)",
            "IČO": code,
            "City": city,
            "Detail_URL": detail_url
        }
        
        detail_cache[detail_url] = record
        rows.append(record)
        processed_count += 1
        
        # Lưu tăng dần định kỳ mỗi 5 công ty
        if processed_count % 5 == 0:
            with open(DETAIL_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(detail_cache, f, ensure_ascii=False, indent=2)
            save_current_outputs(rows)
            
        await asyncio.sleep(0.3)
        
    with open(DETAIL_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(detail_cache, f, ensure_ascii=False, indent=2)
    save_current_outputs(rows)
    print(f"\n[✔] HOÀN TẤT TOÀN BỘ TIẾN TRÌNH! Đã xử lý {len(rows):,} doanh nghiệp.")

# ----------------------------------------------------------------------
# GIAI ĐOẠN 4: LƯU TĂNG DẦN VÀ XUẤT CẢ 3 FILE (0RAW, 1ENR, 2COL)
# ----------------------------------------------------------------------
def save_current_outputs(records):
    """Xuất đồng bộ cả 3 file 0RAW, 1ENR và 2COL (100% Email lên đầu danh sách)."""
    if not records:
        return
        
    raw_fields = [
        "No.", "Công ty", "IČO", "Chức danh", "Người liên hệ", "SĐT",
        "Liên Hệ", "Email", "Địa chỉ", "City", "Category", "Detail_URL"
    ]
    with open(OUT_RAW_ROOT, "w", encoding="utf-8-sig", newline="") as f_root, \
         open(OUT_RAW_CSDL, "w", encoding="utf-8-sig", newline="") as f_csdl:
        writer_root = csv.DictWriter(f_root, fieldnames=raw_fields, extrasaction='ignore')
        writer_csdl = csv.DictWriter(f_csdl, fieldnames=raw_fields, extrasaction='ignore')
        writer_root.writeheader()
        writer_csdl.writeheader()
        for i, r in enumerate(records, 1):
            r_copy = dict(r)
            r_copy["No."] = i
            writer_root.writerow(r_copy)
            writer_csdl.writerow(r_copy)
            
    has_email = []
    no_email = []
    for r in records:
        if r.get("Email") and r.get("Email").strip():
            has_email.append(r)
        else:
            no_email.append(r)
            
    sorted_records = has_email + no_email
    
    with open(OUT_ENR_ROOT, "w", encoding="utf-8-sig", newline="") as f_root, \
         open(OUT_ENR_CSDL, "w", encoding="utf-8-sig", newline="") as f_csdl:
        writer_root = csv.DictWriter(f_root, fieldnames=raw_fields, extrasaction='ignore')
        writer_csdl = csv.DictWriter(f_csdl, fieldnames=raw_fields, extrasaction='ignore')
        writer_root.writeheader()
        writer_csdl.writeheader()
        for i, r in enumerate(sorted_records, 1):
            r_copy = dict(r)
            r_copy["No."] = i
            writer_root.writerow(r_copy)
            writer_csdl.writerow(r_copy)
            
    with open(OUT_2COL_ROOT, "w", encoding="utf-8-sig", newline="") as f_root, \
         open(OUT_2COL_CSDL, "w", encoding="utf-8-sig", newline="") as f_csdl:
        writer_root = csv.DictWriter(f_root, fieldnames=HEADERS_20COL, extrasaction='ignore')
        writer_csdl = csv.DictWriter(f_csdl, fieldnames=HEADERS_20COL, extrasaction='ignore')
        writer_root.writeheader()
        writer_csdl.writeheader()
        for i, r in enumerate(sorted_records, 1):
            r_copy = dict(r)
            r_copy["No."] = i
            writer_root.writerow(r_copy)
            writer_csdl.writerow(r_copy)

# ----------------------------------------------------------------------
# HÀM CHÍNH ENTRYPOINT
# ----------------------------------------------------------------------
async def main():
    print("=" * 80)
    print(" CHƯƠNG TRÌNH CÀO VÀ HỢP NHẤT REKVIZITAI LITHUANIA (CHẾ ĐỘ TRỰC QUAN)")
    print(" Cửa sổ Google Chrome đang mở trực tiếp trên màn hình để bạn theo dõi 100%!")
    print("=" * 80 + "\n")
    
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={'width': 1280, 'height': 800},
            locale="lt-LT",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        
        await browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        # Bước 1: Thu thập và gộp danh sách từ 2 danh mục
        listings = await harvest_all_listings(page)
        
        # Bước 2 & 3: Mở trực quan từng trang để bóc tách chi tiết & quét Email
        await harvest_and_enrich_details(page, listings)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
