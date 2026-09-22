# -*- coding: utf-8 -*-
"""
Bộ Cào Doanh Nghiệp Chế Biến Thực Phẩm & Ngành Thực Phẩm Litva (Lithuania) trên Google Maps:
- Ngôn ngữ Google Maps: Tiếng Lithuania (hl=lt)
- Zoom: 11z (hoặc 10z)
- Trình duyệt: Google Chrome (ggchrome)
- Bộ lọc Tag nghiêm ngặt: Chỉ nhận 22 tag ngành nghề thực phẩm đã chỉ định
- Dịch Tag ra tiếng Việt chuẩn xác
- Cào SĐT và Email trực tiếp từ Website (xử lý Cloudflare, mailto, contact links)
- Bỏ qua các công ty đã có sẵn EMAIL trong file "chế biến thực phẩm litva - đã làm giàu rekvizitai.csv"
- Lưu file động (CSV UTF-8-BOM + Excel đa tính năng), bảo toàn dữ liệu khi chạy trên nhiều máy qua Git
"""

import asyncio
import csv
import json
import os
import random
import re
import sys
import urllib.parse
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Import cấu hình và danh sách tọa độ Lithuania
import config_thuc_pham_lt as config
import locations_lt

# Cấu hình mã hóa hiển thị terminal UTF-8 và flush tức thì
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

LEGAL_FORMS_LT = [
    'uab', 'ab', 'mb', 'všį', 'vsi', 'iį', 'ii', 'žūb', 'zub', 'tūb', 'tub', 'viešoji įstaiga'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'sentry-next.wixpress.com', 'dvv.fi',
    'traficom.fi', 'email.fi', 'sivusto.com', 'yourdomain.com', 'schema.org'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'admin', 'mailer-daemon',
    'saavutettavuus', 'etunimi.sukunimi', 'esimerkki', 'test', 'user'
}

GENERIC_BIZ_USERNAMES = [
    'info', 'uzsakymai', 'pardavimai', 'buhalterija', 'vadyba', 'komercija',
    'gamyba', 'administracija', 'kontaktai', 'biuras', 'marketingas', 'office',
    'contact', 'sales', 'order', 'post'
]

CSV_HEADERS = [
    "Name", "Category_LT", "Category_VN", "Email", "Phone", "Website",
    "Address", "City", "State", "Rating", "Reviews_Count", "Facebook_URL",
    "Search_Query", "Google_Maps_URL", "Permanently_Closed", "Latitude", "Longitude"
]

def normalize_company_name(name):
    """Chuẩn hóa tên công ty để so sánh lọc trùng với tập dữ liệu cũ."""
    if not name:
        return ""
    s = re.sub(r'["\'„“”«».,;:()\[\]\-–—/]', ' ', name).lower().strip()
    words = [w for w in s.split() if w not in LEGAL_FORMS_LT]
    return ' '.join(words)

def load_existing_companies_with_email():
    """Tải danh sách các công ty đã có sẵn email từ dataset rekvizitai để bỏ qua."""
    existing_set = set()
    
    # 1. Từ file CSV Rekvizitai
    if os.path.exists(config.EXISTING_REKVIZITAI_CSV):
        try:
            with open(config.EXISTING_REKVIZITAI_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    e = row.get('email', '').strip()
                    n1 = row.get('ten_cong_ty', '').strip()
                    n2 = row.get('ten_chinh_thuc_rekvizitai', '').strip()
                    if e:
                        if n1:
                            existing_set.add(normalize_company_name(n1))
                        if n2:
                            existing_set.add(normalize_company_name(n2))
        except Exception as err:
            print(f"[*] Cảnh báo khi đọc file rekvizitai cũ: {err}")

    # 2. Từ cache email đã cào của Rekvizitai
    if os.path.exists(config.EXISTING_EMAIL_CACHE) and os.path.exists(config.EXISTING_REKVIZITAI_CSV):
        try:
            with open(config.EXISTING_EMAIL_CACHE, mode='r', encoding='utf-8') as f:
                web_cache = json.load(f)
            with open(config.EXISTING_REKVIZITAI_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    w = row.get('website', '').strip()
                    n1 = row.get('ten_cong_ty', '').strip()
                    n2 = row.get('ten_chinh_thuc_rekvizitai', '').strip()
                    if w and w in web_cache and web_cache[w]:
                        if n1:
                            existing_set.add(normalize_company_name(n1))
                        if n2:
                            existing_set.add(normalize_company_name(n2))
        except Exception as err:
            print(f"[*] Cảnh báo khi đọc cache email cũ: {err}")

    print(f"[+] Đã tải {len(existing_set)} công ty ĐÃ CÓ EMAIL trong danh sách cũ để tự động bỏ qua khi cào.")
    return existing_set

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    """Tải các địa điểm đã cào từ file CSV kết quả để tránh cào trùng khi khởi động lại."""
    scraped_urls = set()
    if os.path.exists(config.OUTPUT_CSV):
        try:
            with open(config.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    u = row.get('Google_Maps_URL', '')
                    if u:
                        scraped_urls.add(extract_place_id(u))
        except Exception as e:
            print(f"[-] Lỗi đọc file CSV kết quả cũ: {e}")
    return scraped_urls

def append_to_csv(row_dict):
    """Ghi trực tiếp tức thì từng bản ghi vào file CSV (Lưu file động chống mất dữ liệu)."""
    os.makedirs(os.path.dirname(config.OUTPUT_CSV), exist_ok=True)
    file_exists = os.path.isfile(config.OUTPUT_CSV)
    try:
        with open(config.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Lỗi ghi dữ liệu vào CSV: {e}")

def sync_to_excel():
    """Đồng bộ từ CSV sang file Excel có định dạng đẹp mắt."""
    if not os.path.exists(config.OUTPUT_CSV):
        return
    try:
        os.makedirs(os.path.dirname(config.OUTPUT_XLSX), exist_ok=True)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Thực Phẩm Litva (Google Maps)"

        with open(config.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")

        for r_idx, row_data in enumerate(rows, 1):
            ws.append(row_data)
            if r_idx == 1:
                for col_idx in range(1, len(row_data) + 1):
                    cell = ws.cell(row=1, column=col_idx)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.freeze_panes = "B2"

        # Tự căn chỉnh độ rộng cột
        col_widths = {
            "Name": 32, "Category_LT": 30, "Category_VN": 32, "Email": 28, "Phone": 18,
            "Website": 28, "Address": 38, "City": 18, "State": 18, "Rating": 8,
            "Reviews_Count": 14, "Facebook_URL": 28, "Search_Query": 28,
            "Google_Maps_URL": 22, "Permanently_Closed": 16, "Latitude": 12, "Longitude": 12
        }
        for col_idx, col_name in enumerate(CSV_HEADERS, 1):
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = col_widths.get(col_name, 16)

        wb.save(config.OUTPUT_XLSX)
    except Exception as err:
        print(f"[*] Cảnh báo đồng bộ file Excel: {err}")

def load_progress():
    """Tải tiến trình các cặp (Location, Keyword) đã hoàn thành."""
    os.makedirs(os.path.dirname(config.PROGRESS_FILE), exist_ok=True)
    completed = set()
    if os.path.exists(config.PROGRESS_FILE):
        try:
            with open(config.PROGRESS_FILE, mode='r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get("completed", []):
                    completed.add((item[0].lower(), item[1].lower()))
        except Exception:
            pass
    return completed

def save_progress(loc_name, keyword):
    """Lưu cặp (Location, Keyword) đã hoàn thành vào file JSON tiến trình."""
    completed_list = []
    if os.path.exists(config.PROGRESS_FILE):
        try:
            with open(config.PROGRESS_FILE, mode='r', encoding='utf-8') as f:
                data = json.load(f)
                completed_list = data.get("completed", [])
        except Exception:
            pass
    pair = [loc_name, keyword]
    if pair not in completed_list:
        completed_list.append(pair)
        try:
            with open(config.PROGRESS_FILE, mode='w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def load_email_cache():
    os.makedirs(os.path.dirname(config.EMAIL_CACHE_FILE), exist_ok=True)
    if os.path.exists(config.EMAIL_CACHE_FILE):
        try:
            with open(config.EMAIL_CACHE_FILE, mode='r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_email_cache(cache):
    try:
        with open(config.EMAIL_CACHE_FILE, mode='w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# -------------------------------------------------------------
# Module Cào Email & Facebook từ Website Doanh Nghiệp
# -------------------------------------------------------------
def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def score_email(email, comp_domain=""):
    email = email.lower().strip()
    if '@' not in email:
        return 0
    user, dom = email.split('@', 1)
    if dom in JUNK_EMAIL_DOMAINS or any(dom.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return 0
    if user in SYSTEM_USERNAMES or any(s in user for s in ['noreply', 'no-reply', 'privacy', 'test']):
        return 0
    if dom.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return 0
    
    score = 10
    if comp_domain and (dom == comp_domain or comp_domain.endswith('.' + dom) or dom.endswith('.' + comp_domain)):
        score += 25
    if any(user == g or user.startswith(g + '.') or user.startswith(g + '-') for g in GENERIC_BIZ_USERNAMES):
        score += 15
    if dom in ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'inbox.lt', 'mail.ru']:
        score -= 5
    return score

async def fetch_html_content(url):
    """Tải mã nguồn HTML an toàn với Chrome impersonation hoặc aiohttp."""
    if not url or not url.startswith('http'):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "lt-LT,lt;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        if HAS_CURL_CFFI:
            async with AsyncSession(impersonate="chrome124", timeout=10) as session:
                resp = await session.get(url, headers=headers, verify=False)
                if resp.status_code == 200:
                    return resp.text
        else:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
                    if resp.status == 200:
                        return await resp.text()
    except Exception:
        pass
    return ""

async def crawl_site_contacts(website_url, email_cache):
    """Cào Email và Fanpage Facebook từ Website công ty."""
    if not website_url or not website_url.startswith("http"):
        return "", ""
        
    cache_key = website_url.strip().rstrip('/')
    if cache_key in email_cache:
        cached_info = email_cache[cache_key]
        return cached_info.get("email", ""), cached_info.get("facebook", "")

    comp_domain = urlparse(website_url).netloc.lower().replace('www.', '')
    raw_emails = set()
    found_facebook = ""

    # 1. Tải trang chủ
    homepage_html = await fetch_html_content(website_url)
    if homepage_html:
        # Giải mã Cloudflare email
        for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', homepage_html):
            dec = decode_cloudflare_email(cf)
            if dec:
                raw_emails.add(dec)
        # Mailto:
        for mailto in re.findall(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7})', homepage_html, re.I):
            raw_emails.add(mailto)
        # Text regex
        for em in EMAIL_REGEX.findall(homepage_html):
            raw_emails.add(em)

        # Tìm link Facebook
        fb_match = re.search(r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9._-]+', homepage_html, re.I)
        if fb_match:
            fb_url = fb_match.group(0)
            if not any(x in fb_url.lower() for x in ['sharer', 'share', 'dialog', 'plugins', 'tr?id']):
                found_facebook = fb_url

        # Tìm trang liên hệ tiếng Lithuania
        soup = BeautifulSoup(homepage_html, 'html.parser')
        contact_urls = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            href_lower = href.lower()
            if any(k in href_lower or k in text for k in ['kontakt', 'kontaktai', 'apie-mus', 'rekvizit', 'contact', 'info']):
                full_url = urljoin(website_url, href)
                if full_url.startswith(website_url) and full_url not in contact_urls:
                    contact_urls.append(full_url)

        # 2. Tải trang liên hệ (tối đa 2 trang con)
        for c_url in contact_urls[:2]:
            sub_html = await fetch_html_content(c_url)
            if sub_html:
                for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', sub_html):
                    dec = decode_cloudflare_email(cf)
                    if dec:
                        raw_emails.add(dec)
                for mailto in re.findall(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7})', sub_html, re.I):
                    raw_emails.add(mailto)
                for em in EMAIL_REGEX.findall(sub_html):
                    raw_emails.add(em)
                if not found_facebook:
                    fb_sub = re.search(r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9._-]+', sub_html, re.I)
                    if fb_sub:
                        fb_u = fb_sub.group(0)
                        if not any(x in fb_u.lower() for x in ['sharer', 'share', 'dialog', 'plugins', 'tr?id']):
                            found_facebook = fb_u

    # Chấm điểm chọn email đơn tốt nhất
    best_email = ""
    scored = []
    for em in raw_emails:
        sc = score_email(em, comp_domain)
        if sc > 0:
            scored.append((sc, em.lower().strip()))
    if scored:
        scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
        best_email = scored[0][1]

    # Lưu cache
    email_cache[cache_key] = {
        "email": best_email,
        "facebook": found_facebook
    }
    save_email_cache(email_cache)
    return best_email, found_facebook

# -------------------------------------------------------------
# Trình Thu Thập Google Maps Playwright
# -------------------------------------------------------------
def is_lithuania_address(address):
    """Kiểm tra xem địa chỉ có thuộc lãnh thổ Lithuania hay không."""
    if not address:
        return False
    a_lower = address.lower()
    if "lietuva" in a_lower or "lithuania" in a_lower or "lt-" in a_lower:
        return True
    lt_cities = [
        "vilnius", "kaunas", "klaipėda", "klaipeda", "šiauliai", "siauliai", "panevėžys", "panevezys",
        "alytus", "marijampolė", "marijampole", "mažeikiai", "mazeikiai", "jonava", "utena", "kėdainiai",
        "kedainiai", "telšiai", "telsiai", "visaginas", "tauragė", "taurage", "ukmergė", "ukmerge", "plungė",
        "plunge", "kretinga", "šilutė", "silute", "radviliškis", "radviliskis", "palanga", "gargždai", "gargzdai",
        "druskininkai", "rokiškis", "rokiskis", "biržai", "birzai", "kaišiadorys", "kaisiadorys"
    ]
    return any(city in a_lower for city in lt_cities)

def parse_lithuanian_address(address):
    if not address:
        return "", "Lietuva"
    addr = re.sub(r',\s*Lietuva\s*$', '', address, flags=re.I).strip()
    addr = re.sub(r',\s*Lithuania\s*$', '', addr, flags=re.I).strip()
    parts = [p.strip() for p in addr.split(',')]
    city = parts[-1] if parts else ""
    return city, "Lietuva"

async def handle_captcha(page):
    """Nhận diện Captcha / Bot Block và phát cảnh báo."""
    try:
        title = await page.title()
        if any(w in title.lower() for w in ['sorry', 'recaptcha', 'captcha', 'unusual traffic']):
            print("\n" + "=" * 65)
            print("[!] CẢNH BÁO: GOOGLE MAPS PHÁT HIỆN LƯU LƯỢNG BẤT THƯỜNG / CAPTCHA!")
            print("[!] Vui lòng bấm vào trình duyệt để giải Captcha nếu có.")
            print("=" * 65 + "\n")
            sys.stdout.write('\a')
            sys.stdout.flush()
            await asyncio.sleep(15)
    except Exception:
        pass

async def bypass_consent_screen(page):
    """Tự động vượt qua màn hình Cookie Consent của Google tại Châu Âu (tiếng Lithuania & Anh)."""
    try:
        consent_btn = page.locator('button:has-text("Priimti viską"), button:has-text("Sutinku"), button:has-text("Sutikti su viskuo"), button:has-text("Priimti"), button:has-text("Accept all"), button:has-text("Agree")')
        if await consent_btn.count() > 0:
            print("[*] Đã phát hiện bảng Google Cookie Consent (Châu Âu). Đang chấp nhận...")
            await consent_btn.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def scroll_results_feed(page, max_scrolls=18):
    """Cuộn danh sách kết quả bên trái Google Maps để tải hết địa điểm."""
    feed_sel = config.SELECTORS["results_container"]
    try:
        await page.wait_for_selector(feed_sel, timeout=7000)
    except Exception:
        return

    feed = page.locator(feed_sel)
    if await feed.count() == 0:
        return

    scrolls = 0
    last_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())

    while scrolls < max_scrolls:
        await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
        await page.wait_for_timeout(random.uniform(500, 900))

        inner_text = await feed.inner_text()
        if "pasiekėte sąrašo pabaigą" in inner_text.lower() or "reached the end of the list" in inner_text.lower():
            break

        new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
        if new_height == last_height:
            await page.wait_for_timeout(600)
            await page.evaluate('(el) => el.scrollTop = el.scrollHeight', await feed.element_handle())
            new_height = await page.evaluate('(el) => el.scrollHeight', await feed.element_handle())
            if new_height == last_height:
                break

        last_height = new_height
        scrolls += 1

async def extract_details(page, url, search_query, loc_info, existing_with_email, email_cache):
    """Trích xuất thông tin chi tiết một địa điểm, lọc tag và cào email."""
    sel = config.SELECTORS
    
    # 1. Tên công ty
    name = ""
    name_loc = page.locator(sel["business_name"])
    if await name_loc.count() > 0:
        name = (await name_loc.first.inner_text()).strip()
        
    if not name:
        return None

    # 2. KIỂM TRA LỌC TRÙNG VỚI DOANH NGHIỆP ĐÃ CÓ EMAIL TRONG REKVIZITAI
    norm_name = normalize_company_name(name)
    if norm_name in existing_with_email:
        print(f"    [-] Bỏ qua: Doanh nghiệp '{name}' đã có sẵn Email trong dataset Rekvizitai cũ.")
        return None

    # 3. Tag ngành nghề trên Google Maps (tiếng Lithuania)
    category_lt = ""
    try:
        cat_loc = page.locator(sel["category"])
        for _ in range(12):
            count = await cat_loc.count()
            if count > 0:
                for i in range(count):
                    txt = (await cat_loc.nth(i).inner_text()).strip()
                    if txt:
                        category_lt = txt
                        break
                if category_lt:
                    break
            await page.wait_for_timeout(150)
    except Exception:
        pass

    if not category_lt:
        print(f"    [-] Bỏ qua: '{name}' không có Category tag.")
        return None

    # 4. BỘ LỌC TAG NGHIÊM NGẶT (Strict Category Whitelist)
    cat_lower = category_lt.lower().strip()
    matched_key = None
    for allowed_tag in config.ALLOWED_CATEGORIES:
        if allowed_tag == cat_lower or allowed_tag in cat_lower or cat_lower in allowed_tag:
            matched_key = allowed_tag
            break

    if not matched_key:
        print(f"    [-] Bỏ qua: Tag '{category_lt}' không nằm trong danh sách 22 tag ngành thực phẩm cho phép.")
        return None

    category_vn = config.TAG_TRANSLATIONS.get(matched_key, "Chế biến & Kinh doanh thực phẩm")

    # 5. Địa chỉ
    address = ""
    addr_loc = page.locator(sel["address"])
    if await addr_loc.count() > 0:
        addr_label = await addr_loc.first.get_attribute("aria-label")
        if addr_label:
            address = addr_label.replace("Adresas:", "").replace("Address:", "").strip()
        else:
            address = (await addr_loc.first.inner_text()).strip()

    if not is_lithuania_address(address):
        print(f"    [-] Bỏ qua: Địa chỉ '{address}' nằm ngoài lãnh thổ Litva.")
        return None

    city, state = parse_lithuanian_address(address)
    if not city:
        city = loc_info["name"]

    # 6. Số điện thoại (chuẩn hóa nháy đơn để không mất số 0 trong Excel)
    phone = ""
    phone_loc = page.locator(sel["phone"])
    if await phone_loc.count() > 0:
        p_attr = await phone_loc.first.get_attribute("data-item-id")
        if p_attr:
            clean_p = p_attr.replace("phone:tel:", "").strip()
            phone = f"'{clean_p}"

    # 7. Website
    website = ""
    web_loc = page.locator(sel["website"])
    if await web_loc.count() > 0:
        w_href = await web_loc.first.get_attribute("href")
        if w_href:
            website = w_href.strip()

    # 8. Rating & Reviews
    rating = ""
    reviews_count = ""
    try:
        r_loc = page.locator('div.F7nice span[aria-hidden="true"]')
        if await r_loc.count() > 0:
            rating = (await r_loc.first.inner_text()).strip()
        rev_loc = page.locator(sel["reviews_count"])
        if await rev_loc.count() > 0:
            rev_text = await rev_loc.first.get_attribute("aria-label") or await rev_loc.first.inner_text()
            m = re.search(r'\d+', rev_text.replace(" ", "").replace(",", ""))
            if m:
                reviews_count = m.group()
    except Exception:
        pass

    # 9. Trạng thái đóng cửa
    permanently_closed = "No"
    try:
        closed_loc = page.locator('span:has-text("Permanently closed"), span:has-text("Uždaryta visam laikui"), span:has-text("Đóng cửa vĩnh viễn")')
        if await closed_loc.count() > 0:
            permanently_closed = "Yes"
    except Exception:
        pass

    # 10. Tọa độ từ URL
    lat, lng = loc_info["lat"], loc_info["lng"]
    coord_m = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url) or re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if coord_m:
        lat, lng = float(coord_m.group(1)), float(coord_m.group(2))
        # Kiểm tra tọa độ trong biên giới Lithuania (53.8 - 56.6, 20.8 - 27.0)
        if not (53.8 < lat < 56.6) or not (20.8 < lng < 27.0):
            print(f"    [-] Bỏ qua: Tọa độ ({lat}, {lng}) nằm ngoài biên giới Litva.")
            return None

    # 11. CÀO EMAIL VÀ FANPAGE FACEBOOK TRỰC TIẾP TỪ WEBSITE
    email = ""
    facebook_url = ""
    if website:
        print(f"    [*] Đang cào Email & Contact từ Website: {website} ...")
        email, facebook_url = await crawl_site_contacts(website, email_cache)
        if email:
            print(f"    [+] Tìm thấy Email: {email}")
        else:
            print(f"    [-] Không tìm thấy Email trên web.")

    record = {
        "Name": name,
        "Category_LT": category_lt,
        "Category_VN": category_vn,
        "Email": email,
        "Phone": phone,
        "Website": website,
        "Address": address,
        "City": city,
        "State": state,
        "Rating": rating,
        "Reviews_Count": reviews_count,
        "Facebook_URL": facebook_url,
        "Search_Query": search_query,
        "Google_Maps_URL": url,
        "Permanently_Closed": permanently_closed,
        "Latitude": lat,
        "Longitude": lng
    }
    return record

async def process_location_keyword(page, keyword, loc_info, scraped_urls, existing_with_email, email_cache):
    """Tìm kiếm một từ khóa tại một cụm tọa độ cụ thể của Lithuania."""
    search_query = f"{keyword} in {loc_info['name']}, Lithuania"
    print(f"\n[+] Đang tìm kiếm: '{search_query}' (Zoom {config.ZOOM_LEVEL}z)")

    query_encoded = urllib.parse.quote_plus(keyword)
    zoom = config.ZOOM_LEVEL
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{zoom}z?hl={config.MAPS_LANG}"

    try:
        await page.goto(search_url, timeout=config.TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"[-] Timeout khi mở trang tìm kiếm: {e}")
        return False

    await handle_captcha(page)
    await bypass_consent_screen(page)

    # Trường hợp Google Maps tự chuyển thẳng vào chi tiết một địa điểm duy nhất
    current_url = page.url
    if "/maps/place/" in current_url:
        pid = extract_place_id(current_url)
        if pid not in scraped_urls:
            rec = await extract_details(page, current_url, search_query, loc_info, existing_with_email, email_cache)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                print(f"    -> ĐÃ LƯU: {rec['Name']} | {rec['Category_VN']} | SĐT: {rec['Phone']} | Mail: {rec['Email']}")
        return True

    # Cuộn danh sách kết quả để tải hết địa điểm
    await scroll_results_feed(page)

    listing_sel = config.SELECTORS["listing_link"]
    items = await page.locator(listing_sel).all()
    print(f"[*] Tìm thấy {len(items)} địa điểm tiềm năng trong khung nhìn.")

    saved_in_batch = 0
    for idx, item in enumerate(items, 1):
        try:
            url = await item.get_attribute("href")
            if not url or "/maps/place/" not in url:
                continue

            pid = extract_place_id(url)
            if pid in scraped_urls:
                continue

            # Bấm vào xem chi tiết
            await item.scroll_into_view_if_needed()
            await item.click()
            await page.wait_for_timeout(1200)
            await handle_captcha(page)

            rec = await extract_details(page, url, search_query, loc_info, existing_with_email, email_cache)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                saved_in_batch += 1
                print(f"    [{saved_in_batch}] ĐÃ LƯU: {rec['Name']} | {rec['Category_VN']} | SĐT: {rec['Phone']} | Mail: {rec['Email']}")

        except Exception as item_err:
            pass

    return True

# -------------------------------------------------------------
# Hàm Điều Khiển Chính (Main Runner)
# -------------------------------------------------------------
async def run_scraper():
    print("=" * 72)
    print("   HỆ THỐNG CÀO DỮ LIỆU NGÀNH THỰC PHẨM & CHẾ BIẾN THỰC PHẨM LITVA")
    print("   Nguồn: Google Maps (hl=lt) | Trình duyệt: Google Chrome")
    print("   Tự động lọc 22 Tag cho phép + Dịch sang Tiếng Việt + Cào Email & SĐT")
    print("=" * 72)

    # 1. Tải các công ty đã có email trong Rekvizitai để bỏ qua
    existing_with_email = load_existing_companies_with_email()

    # 2. Tải danh sách địa điểm đã cào trước đó để tiếp tục không trùng lặp
    scraped_urls = get_scraped_urls()
    print(f"[+] Đã có {len(scraped_urls)} địa điểm trong file kết quả cũ ({config.OUTPUT_CSV}).")

    # 3. Tải tiến trình quét (Locations, Keywords)
    completed_scans = load_progress()
    print(f"[+] Đã hoàn thành {len(completed_scans)} lượt quét (Cụm vị trí + Từ khóa).")

    # 4. Tải cache email
    email_cache = load_email_cache()

    # 5. Khởi động Google Chrome với Playwright
    async with async_playwright() as p:
        print("[*] Đang khởi động Google Chrome...")
        browser = None
        try:
            # Thử mở trình duyệt Google Chrome cài sẵn trên máy
            browser = await p.chromium.launch(
                channel="chrome",
                headless=config.HEADLESS,
                args=[
                    "--lang=lt-LT",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            )
        except Exception:
            print("[*] Không tìm thấy Chrome mặc định, chuyển sang Chromium...")
            browser = await p.chromium.launch(
                headless=config.HEADLESS,
                args=["--lang=lt-LT", "--disable-blink-features=AutomationControlled"]
            )

        context = await browser.new_context(
            locale="lt-LT",
            extra_http_headers={"Accept-Language": "lt-LT,lt;q=0.9,en;q=0.8"},
            viewport={"width": 1280, "height": 850}
        )
        page = await context.new_page()

        locations = locations_lt.get_locations()
        total_locations = len(locations)
        total_keywords = len(config.KEYWORDS)
        total_combos = total_locations * total_keywords

        print(f"[*] Tổng số cụm tọa độ phủ khắp Litva: {total_locations}")
        print(f"[*] Tổng số Tag ngành thực phẩm cần quét: {total_keywords}")
        print(f"[*] Tổng số lượt quét dự kiến: {total_combos}")
        print("-" * 72)

        combo_count = 0
        for loc in locations:
            loc_name = loc["name"]
            for kw in config.KEYWORDS:
                combo_count += 1
                pair = (loc_name.lower(), kw.lower())
                if pair in completed_scans:
                    continue

                print(f"\n>>> [{combo_count}/{total_combos}] Khu vực: {loc_name} ({loc['state']}) | Tag: '{kw}'")
                success = await process_location_keyword(page, kw, loc, scraped_urls, existing_with_email, email_cache)
                if success:
                    save_progress(loc_name, kw)
                    completed_scans.add(pair)
                    # Định kỳ đồng bộ sang Excel mỗi 10 lượt quét
                    if combo_count % 10 == 0:
                        sync_to_excel()

                await asyncio.sleep(random.uniform(1.0, 2.5))

        await browser.close()

    # Đồng bộ lần cuối sang file Excel
    sync_to_excel()

    print("\n" + "=" * 72)
    print("   [HOÀN TẤT] ĐÃ QUÉT XONG TOÀN BỘ DOANH NGHIỆP THỰC PHẨM LITVA!")
    print(f"   File CSV kết quả:   {config.OUTPUT_CSV}")
    print(f"   File Excel kết quả: {config.OUTPUT_XLSX}")
    print("=" * 72)

if __name__ == "__main__":
    asyncio.run(run_scraper())
