# -*- coding: utf-8 -*-
"""
Hệ thống Làm giàu dữ liệu Google Maps cho ADENVIRK.csv (Môi giới lao động & Tuyển dụng Đan Mạch):
1. Nhắm mục tiêu: Chỉ làm giàu cho các bản ghi CHƯA CÓ EMAIL trong file ADENVIRK.csv.
2. Tra cứu Google Maps (hl=da, Denmark) kết hợp tên công ty và thành phố trích xuất từ link Proff.dk.
3. Quy tắc so khớp tên công ty nghiêm ngặt theo yêu cầu:
   - Không phân biệt hoa thường.
   - Kết quả và tên gốc phải giống hệt (sau khi chuẩn hóa các hậu tố pháp nhân ApS, A/S, P/S, I/S, K/S...).
   - Nếu có từ khác thì cụm đó phải được ngăn cách bằng dấu ngoặc (...) hoặc gạch ngang/dấu phân tách (-, –, —, |, :, ,).
4. Cào Website để tìm Email, SĐT và link Facebook:
   - Loại bỏ triệt để các ký tự URL artifact như %20, mailto:.
   - Lọc bỏ email rác hệ thống (sentry, wixpress, noreply, privacy, terms, cookies...).
   - Chấm điểm chọn đúng 1 email có giá trị B2B cao nhất cho môi giới lao động / tuyển dụng (info@, kontakt@, job@, hr@, vikar@...).
   - Hỗ trợ giải mã Cloudflare email và fallback Playwright Chrome cho các trang SPA/JS.
5. Cập nhật địa chỉ thực tế (thay thế cho placeholder 'Du følger virksomheden').
6. Lưu file động tức thời: Cập nhật trực tiếp vào ADENVIRK.csv và cache JSON sau mỗi bản ghi, bảo toàn tiến độ khi bấm Ctrl+C.
"""

import asyncio
import csv
import json
import os
import re
import sys
import html
import urllib.parse
from urllib.parse import urlparse
from pathlib import Path
import argparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Cấu hình mã hóa hiển thị UTF-8
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)

DEFAULT_INPUT_CSV = os.path.join(BASE_DIR, "ADENVIRK.csv")
DEFAULT_OUTPUT_CSV = os.path.join(BASE_DIR, "ADENVMAP.csv")
CACHE_FILE = os.path.join(SCRIPT_DIR, "cache_maps_enrich_aden_virk.json")

# Danh sách hậu tố pháp nhân Đan Mạch
LEGAL_FORMS_DK = [
    'aps', 'a/s', 'as', 'a.s.', 'p/s', 'ps', 'i/s', 'is', 'k/s', 'ks',
    'amba', 'a.m.b.a.', 'fmba', 'smba', 'ivs', 'ltd', 'limited', 'holding',
    'danmark', 'denmark'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')

# Tên miền rác, nền tảng tạo web hoặc mạng xã hội không phải email riêng của doanh nghiệp
JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'sentry-next.wixpress.com', 'schema.org',
    'trustpilot.com', 'trustpilot.dk', 'google.com', 'google.dk'
}

# Tiền tố email hệ thống / không có giá trị B2B
SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'admin', 'mailer-daemon',
    'test', 'user', 'example', 'postmaster'
}

# Danh sách tiền tố B2B được ưu tiên cao nhất cho môi giới lao động / tuyển dụng / agency
B2B_STAFFING_USERNAMES = [
    'info', 'kontakt', 'contact', 'rekruttering', 'job', 'jobs', 'karriere',
    'hr', 'administration', 'kontor', 'office', 'post', 'booking', 'vikar',
    'bureau', 'sales', 'mail', 'support', 'salg'
]

# Danh sách các trang danh bạ / nền tảng Đan Mạch cần bỏ qua khi tìm web riêng
EXCLUDED_DIRECTORIES_DK = {
    'proff.dk', 'krak.dk', 'degulesider.dk', 'cvr.dk', 'virk.dk', 'lasso.dk',
    'biq.dk', 'dnb.com', 'kompass.com', 'europages.com', 'trustpilot.dk',
    'trustpilot.com', 'jobindex.dk', 'ofir.dk', 'stepstone.dk', 'linkedin.com',
    'facebook.com', 'instagram.com', 'youtube.com', 'google.com', 'google.dk',
    'yellowpages.dk', 'eniro.dk', 'wix.com', 'wordpress.com'
}

def normalize_legal_forms_dk(name):
    """Chuẩn hóa và loại bỏ các hậu tố pháp nhân Đan Mạch."""
    s = re.sub(r'\bA/S\b|\bAS\b|\bA\.S\.\b', ' ', name, flags=re.I)
    s = re.sub(r'\bApS\b|\bAPS\b|\bA\.P\.S\.\b', ' ', s, flags=re.I)
    s = re.sub(r'\bP/S\b|\bPS\b', ' ', s, flags=re.I)
    s = re.sub(r'\bI/S\b|\bIS\b', ' ', s, flags=re.I)
    s = re.sub(r'\bK/S\b|\bKS\b', ' ', s, flags=re.I)
    s = re.sub(r'\bA\.M\.B\.A\b|\bAMBA\b', ' ', s, flags=re.I)
    s = re.sub(r'\bIVS\b', ' ', s, flags=re.I)
    s = re.sub(r'\bLTD\b|\bLIMITED\b', ' ', s, flags=re.I)
    return s

def clean_company_name_dk(name):
    """Làm sạch tên công ty để so sánh."""
    if not name:
        return ""
    n = normalize_legal_forms_dk(name)
    words = re.sub(r'["\'„“”«».,;:()\[\]\-–—/]', ' ', n).lower().split()
    return ' '.join(words)

def is_valid_name_match_dk(query_name, candidate_name):
    """
    Quy tắc so khớp tên công ty theo yêu cầu:
    - Không phân biệt hoa thường.
    - Kết quả và tên gốc phải giống hệt.
    - Nếu có từ khác thì cụm đó phải được ngăn cách bằng dấu ngoặc (...) hoặc gạch ngang/dấu phân tách (-, –, —, |, :, ,).
    """
    q_clean = clean_company_name_dk(query_name)
    c_clean = clean_company_name_dk(candidate_name)

    if not q_clean or not c_clean:
        return False, "EMPTY"

    # 1. Giống hệt 100%
    if q_clean == c_clean:
        return True, "EXACT"

    # 2. Ngăn cách bằng dấu ngoặc đơn (...) hoặc ngoặc vuông [...]
    c_no_brackets = re.sub(r'\(.*?\)|\[.*?\]', '', candidate_name)
    if q_clean == clean_company_name_dk(c_no_brackets):
        return True, "BRACKET"

    # 3. Ngăn cách bằng dấu gạch ngang hoặc dấu phân tách (-, –, —, |, :, ,)
    parts = re.split(r'[-–—|:,]', candidate_name)
    for p in parts:
        if clean_company_name_dk(p) == q_clean:
            return True, "SEPARATOR"

    return False, "NO_MATCH"

def extract_city_from_proff_url(proff_url):
    """Trích xuất thành phố từ URL Proff.dk: /firma/{company}/{city}/arbejdskrafts-tjenester/..."""
    if not proff_url:
        return ""
    m = re.search(r'/firma/[^/]+/([^/]+)/', proff_url)
    if m:
        raw_city = m.group(1)
        city = urllib.parse.unquote(raw_city).replace('-', ' ').title()
        return city
    return ""

def clean_phone_dk(raw_phone):
    """Chuẩn hóa số điện thoại Đan Mạch (8 chữ số, mã +45, thêm nháy đơn cho Excel)."""
    if not raw_phone:
        return ""
    clean_p = re.sub(r'[\ue000-\uf8ff]', '', str(raw_phone)).strip()
    digits = re.sub(r'[^\d]', '', clean_p)
    if not digits:
        return ""
    if digits.startswith("0045"):
        digits = digits[4:]
    elif digits.startswith("45") and len(digits) >= 10:
        digits = digits[2:]

    if len(digits) == 8:
        return f"'+45{digits}"
    elif len(digits) > 8:
        return f"'+45{digits[-8:]}"
    return f"'{digits}"

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def clean_email_string(email_str):
    """Làm sạch email, loại bỏ mã %20 và ký tự thừa."""
    if not email_str:
        return ""
    em = urllib.parse.unquote(email_str).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(em.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return ""
    if '@' not in em or len(em) < 6:
        return ""
    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or u in SYSTEM_USERNAMES:
        return ""
    return em

def score_email_b2b(email, comp_domain=""):
    """
    Chấm điểm email để chọn duy nhất 1 email có giá trị B2B cao nhất cho Agency tuyển dụng / Môi giới lao động.
    """
    clean_em = clean_email_string(email)
    if not clean_em:
        return 0
    u, d = clean_em.split('@', 1)

    score = 10
    # Khớp chính xác tên miền công ty (+25 điểm)
    if comp_domain and (d == comp_domain or comp_domain.endswith('.' + d) or d.endswith('.' + comp_domain)):
        score += 25
    # Tiền tố phục vụ tuyển dụng / liên hệ B2B (+20 điểm)
    if any(u == b or u.startswith(b + '.') or u.startswith(b + '-') for b in B2B_STAFFING_USERNAMES):
        score += 20
    # Email dạng info@, kontakt@ ở tên miền công ty là số 1
    if u in ['info', 'kontakt', 'contact'] and comp_domain and (d == comp_domain or comp_domain.endswith('.' + d)):
        score += 15
    # Trừ điểm mail miễn phí phổ thông (gmail, hotmail, yahoo)
    if d in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.dk']:
        score -= 8

    return score

def extract_facebook_url(html_str):
    if not html_str:
        return ""
    fb_match = re.search(r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9._-]+', html_str, re.I)
    if fb_match:
        fb_url = fb_match.group(0)
        if not any(x in fb_url.lower() for x in ['sharer', 'share', 'dialog', 'plugins', 'tr?id']):
            return fb_url
    return ""

def extract_emails_from_html(html_str):
    if not html_str:
        return set()
    found = set()
    unescaped = html.unescape(html_str)

    # 1. Cloudflare emails
    for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_str):
        dec = decode_cloudflare_email(cf)
        em = clean_email_string(dec)
        if em:
            found.add(em)

    # 2. mailto: links (loại bỏ %20)
    for mailto in re.findall(r'mailto:([^\s"\'<>]+)', unescaped, re.IGNORECASE):
        cleaned_m = mailto.split('?')[0]
        em = clean_email_string(cleaned_m)
        if em:
            found.add(em)

    # 3. Plain text regex
    for match in EMAIL_REGEX.findall(unescaped):
        em = clean_email_string(match)
        if em:
            found.add(em)

    return found

async def fetch_html(url):
    """Tải mã nguồn HTML an toàn với Chrome impersonation hoặc aiohttp."""
    if not url or not url.startswith('http'):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        if HAS_CURL_CFFI:
            async with AsyncSession(impersonate="chrome124", timeout=12) as session:
                resp = await session.get(url, headers=headers, verify=False)
                if resp.status_code == 200:
                    return resp.text
        else:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), ssl=False) as resp:
                    if resp.status == 200:
                        return await resp.text()
    except Exception:
        pass
    return ""

async def scrape_website_contacts(website_url, page=None):
    """Cào Email chuẩn B2B và link Facebook từ Website doanh nghiệp."""
    if not website_url or not website_url.startswith("http"):
        return "", ""

    comp_domain = urlparse(website_url).netloc.lower().replace('www.', '')
    raw_emails = set()
    found_facebook = ""

    # 1. Quét trang chủ
    homepage_html = await fetch_html(website_url)
    if homepage_html:
        raw_emails.update(extract_emails_from_html(homepage_html))
        found_facebook = extract_facebook_url(homepage_html)

        # Quét menu tìm các trang liên hệ tiếng Đan Mạch
        soup = BeautifulSoup(homepage_html, 'html.parser')
        contact_urls = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            href_lower = href.lower()
            if any(k in href_lower or k in text for k in ['kontakt', 'contact', 'om-os', 'om', 'vikar', 'job', 'karriere', 'info']):
                full_url = urllib.parse.urljoin(website_url, href)
                if full_url.startswith(website_url) and full_url not in contact_urls:
                    contact_urls.append(full_url)

        # 2. Quét tối đa 2 trang con liên hệ
        for c_url in contact_urls[:2]:
            sub_html = await fetch_html(c_url)
            if sub_html:
                raw_emails.update(extract_emails_from_html(sub_html))
                if not found_facebook:
                    found_facebook = extract_facebook_url(sub_html)

    # 3. Nếu chưa thấy email và có page Playwright -> Mở trực tiếp (xử lý trang SPA/JS như React/Vue)
    if not raw_emails and page:
        try:
            await page.goto(website_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            rendered_html = await page.content()
            raw_emails.update(extract_emails_from_html(rendered_html))
            if not found_facebook:
                found_facebook = extract_facebook_url(rendered_html)
        except Exception:
            pass

    # 4. Chấm điểm chọn 1 Email B2B tốt nhất
    scored = []
    for em in raw_emails:
        sc = score_email_b2b(em, comp_domain)
        if sc > 0:
            scored.append((sc, clean_email_string(em)))

    if scored:
        scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
        best_email = scored[0][1]
    else:
        best_email = ""

    return best_email, found_facebook

# -------------------------------------------------------------
# Quét Google Maps cho một Công Ty Đan Mạch
# -------------------------------------------------------------
async def query_google_maps_denmark(page, company_name, city):
    """
    Tìm kiếm công ty trên Google Maps Đan Mạch (hl=da),
    áp dụng quy tắc so khớp tên nghiêm ngặt.
    """
    res = {
        "matched": False,
        "match_reason": "",
        "maps_title": "",
        "website": "",
        "phone": "",
        "address": "",
        "maps_url": ""
    }

    # Tạo truy vấn tìm kiếm kết hợp thành phố nếu có
    if city and city.lower() != "danmark":
        search_query = f"{company_name} {city} Denmark"
    else:
        search_query = f"{company_name} Denmark"

    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(search_query)}?hl=da"

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.0)

        # Xử lý nút Cookie Consent của Google tại Đan Mạch nếu xuất hiện
        consent = page.locator('button:has-text("Afvis alle"), button:has-text("Accepter alle"), button:has-text("Jeg accepterer"), button:has-text("Accept all")')
        if await consent.count() > 0:
            await consent.first.click()
            await asyncio.sleep(1.0)

        # Kiểm tra Captcha
        title = await page.title()
        if any(w in title.lower() for w in ['sorry', 'recaptcha', 'captcha', 'unusual traffic']):
            print("\n[!] CẢNH BÁO CAPTCHA GOOGLE MAPS! Vui lòng bấm vào trình duyệt để giải Captcha...")
            sys.stdout.write('\a')
            sys.stdout.flush()
            await asyncio.sleep(15)

        # Chờ các thành phần chi tiết (Website, Phone, Address) hydrate trên DOM
        try:
            await page.wait_for_selector(
                'h1.DUwDvf, a.hfpxzc, button[data-item-id*="phone"], a[data-item-id="authority"]',
                timeout=6000
            )
        except Exception:
            pass
        await asyncio.sleep(1.5)

        # Trường hợp A: Mở trực tiếp trang chi tiết (Direct Place View)
        h1 = page.locator('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
        if await h1.count() > 0:
            maps_title = (await h1.first.inner_text()).strip()
            matched, reason = is_valid_name_match_dk(company_name, maps_title)
            if matched:
                res["matched"] = True
                res["match_reason"] = reason
                res["maps_title"] = maps_title
                res["maps_url"] = page.url

                # Đợi website & phone xuất hiện thêm 1.5s nếu cần
                try:
                    await page.wait_for_selector('a[data-item-id="authority"], button[data-item-id*="phone"]', timeout=3000)
                except Exception:
                    pass

                web_loc = page.locator('a[data-item-id="authority"]')
                if await web_loc.count() > 0:
                    raw_w = await web_loc.first.get_attribute("href")
                    if raw_w:
                        w_clean = urllib.parse.unquote(raw_w).replace('%20', '').strip()
                        dom = urlparse(w_clean).netloc.lower().replace('www.', '')
                        if dom and dom not in EXCLUDED_DIRECTORIES_DK:
                            res["website"] = w_clean

                phone_loc = page.locator('button[data-item-id*="phone"]')
                if await phone_loc.count() > 0:
                    phone_attr = await phone_loc.first.get_attribute("data-item-id")
                    if phone_attr and "phone:tel:" in phone_attr:
                        p_txt = phone_attr.replace("phone:tel:", "").strip()
                    else:
                        raw_p = await phone_loc.first.inner_text()
                        p_txt = re.sub(r'[\ue000-\uf8ff]', '', raw_p).strip()
                    res["phone"] = clean_phone_dk(p_txt)

                addr_loc = page.locator('button[data-item-id="address"]')
                if await addr_loc.count() > 0:
                    addr_label = await addr_loc.first.get_attribute("aria-label")
                    if addr_label:
                        raw_a = addr_label.replace("Adresse:", "").replace("Address:", "").strip()
                    else:
                        raw_a = await addr_loc.first.inner_text()
                    res["address"] = re.sub(r'[\ue000-\uf8ff]', '', raw_a).strip()

                return res

        # Trường hợp B: Danh sách nhiều thẻ kết quả (Cards list)
        cards = page.locator('a.hfpxzc')
        card_count = await cards.count()
        if card_count > 0:
            for i in range(min(card_count, 4)):
                card_title = await cards.nth(i).get_attribute('aria-label') or ""
                matched, reason = is_valid_name_match_dk(company_name, card_title)
                if matched:
                    res["matched"] = True
                    res["match_reason"] = reason
                    res["maps_title"] = card_title.strip()

                    await cards.nth(i).click()
                    try:
                        await page.wait_for_selector('h1.DUwDvf, a[data-item-id="authority"], button[data-item-id*="phone"]', timeout=6000)
                    except Exception:
                        pass
                    await asyncio.sleep(1.5)
                    res["maps_url"] = page.url

                    web_loc = page.locator('a[data-item-id="authority"]')
                    if await web_loc.count() > 0:
                        raw_w = await web_loc.first.get_attribute("href")
                        if raw_w:
                            w_clean = urllib.parse.unquote(raw_w).replace('%20', '').strip()
                            dom = urlparse(w_clean).netloc.lower().replace('www.', '')
                            if dom and dom not in EXCLUDED_DIRECTORIES_DK:
                                res["website"] = w_clean

                    phone_loc = page.locator('button[data-item-id*="phone"]')
                    if await phone_loc.count() > 0:
                        phone_attr = await phone_loc.first.get_attribute("data-item-id")
                        if phone_attr and "phone:tel:" in phone_attr:
                            p_txt = phone_attr.replace("phone:tel:", "").strip()
                        else:
                            raw_p = await phone_loc.first.inner_text()
                            p_txt = re.sub(r'[\ue000-\uf8ff]', '', raw_p).strip()
                        res["phone"] = clean_phone_dk(p_txt)

                    addr_loc = page.locator('button[data-item-id="address"]')
                    if await addr_loc.count() > 0:
                        addr_label = await addr_loc.first.get_attribute("aria-label")
                        if addr_label:
                            raw_a = addr_label.replace("Adresse:", "").replace("Address:", "").strip()
                        else:
                            raw_a = await addr_loc.first.inner_text()
                        res["address"] = re.sub(r'[\ue000-\uf8ff]', '', raw_a).strip()

                    return res
    except Exception as e:
        print(f"    [-] Lỗi trong query_google_maps_denmark: {e}")

    return res

# -------------------------------------------------------------
# Quản lý Tiến Trình & Lưu Dữ Liệu Động
# -------------------------------------------------------------
def load_cache(cache_path):
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache, cache_path):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        temp_cache = cache_path + ".tmp"
        with open(temp_cache, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(temp_cache):
            os.replace(temp_cache, cache_path)
    except Exception:
        pass

def save_csv_dynamically(rows, fieldnames, target_csv_path):
    """Ghi đè an toàn file CSV kết quả, bảo toàn tiến trình 100% kể cả khi file đang được đọc."""
    temp_file = target_csv_path + ".tmp"
    try:
        with open(temp_file, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        
        # Thử thay thế file nguyên tử (atomic replace), retry nếu Excel đang mở tạm thời
        for attempt in range(3):
            try:
                if os.path.exists(temp_file):
                    os.replace(temp_file, target_csv_path)
                break
            except PermissionError:
                import time
                time.sleep(0.5)
    except Exception as e:
        print(f"[-] Lỗi lưu file CSV: {e}")

# -------------------------------------------------------------
# Tiến Trình Cào Chính
# -------------------------------------------------------------
async def run_enrichment(input_csv=None, output_csv=None, cache_file=None, headless=None):
    # Xác định đường dẫn động tương đối theo thư mục của file script
    script_dir = Path(__file__).resolve().parent
    base_dir = script_dir.parent

    input_csv_path = Path(input_csv) if input_csv else (base_dir / "ADENVIRK.csv")
    output_csv_path = Path(output_csv) if output_csv else (base_dir / "ADENVMAP.csv")
    cache_file_path = Path(cache_file) if cache_file else (script_dir / "cache_maps_enrich_aden_virk.json")

    input_csv_str = str(input_csv_path)
    output_csv_str = str(output_csv_path)
    cache_file_str = str(cache_file_path)

    if not os.path.exists(input_csv_str):
        print(f"[ERROR] Không tìm thấy file dữ liệu gốc: {input_csv_str}!")
        return

    # 1. Khởi tạo file kết quả ADENVMAP.csv nếu chưa có (sao chép từ ADENVIRK.csv)
    if not os.path.exists(output_csv_str):
        print(f"[*] Khởi tạo file kết quả mới: {output_csv_str} (sao chép từ {input_csv_str}) ...")
        try:
            import shutil
            shutil.copy2(input_csv_str, output_csv_str)
        except Exception as e:
            print(f"[-] Cảnh báo khởi tạo file: {e}")

    # 2. Đọc dữ liệu hiện tại từ output_csv_str (để bảo toàn tiến độ nếu đã chạy trước đó)
    with open(output_csv_str, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    cache = load_cache(cache_file_str)
    print("=" * 72)
    print("     HỆ THỐNG LÀM GIÀU DỮ LIỆU GOOGLE MAPS CHO ADENVIRK -> ADENVMAP")
    print("     Môi giới Lao động & Nhân sự Đan Mạch (Denmark - hl=da)")
    print(f"     Tập tin NGUỒN (Gốc):      {input_csv_str}")
    print(f"     Tập tin KẾT QUẢ ĐỘNG:     {output_csv_str}")
    print(f"     Tập tin Cache tiến độ:    {cache_file_str}")
    print(f"     Tổng số bản ghi:          {len(rows):,}")
    
    # Xác định các dòng cần làm giàu (Chưa có Email)
    indices_to_enrich = []
    for idx, r in enumerate(rows):
        if not r.get("Email", "").strip():
            indices_to_enrich.append(idx)

    total_need_enrich = len(indices_to_enrich)
    print(f"     Số bản ghi CHƯA CÓ EMAIL cần làm giàu: {total_need_enrich:,}")
    print(f"     Số bản ghi trong Cache đã lưu: {len(cache):,}")
    print("=" * 72)

    if total_need_enrich == 0:
        print("[+] Tuyệt vời! Tất cả các dòng trong file kết quả đều đã có email.")
        return

    # Tự động phát hiện headless phù hợp với môi trường (Windows GUI vs Linux server/CI)
    if headless is None:
        env_headless = os.environ.get("HEADLESS", "").strip().lower()
        if env_headless in ("1", "true", "yes"):
            is_headless = True
        elif sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            is_headless = True
        else:
            is_headless = False
    else:
        is_headless = headless

    print(f"[*] Khởi động trình duyệt (Chế độ Headless: {is_headless})...")

    # 3. Khởi động Google Chrome / Chromium
    async with async_playwright() as p:
        browser = None
        launch_args = ["--lang=da-DK", "--disable-blink-features=AutomationControlled"]
        try:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=is_headless,
                args=launch_args
            )
        except Exception:
            # Fallback sang Chromium tiêu chuẩn nếu máy khác không cài sẵn Chrome
            browser = await p.chromium.launch(
                headless=is_headless,
                args=launch_args
            )

        context = await browser.new_context(
            locale="da-DK",
            extra_http_headers={"Accept-Language": "da-DK,da;q=0.9,en;q=0.8"},
            viewport={"width": 1280, "height": 850}
        )
        page = await context.new_page()

        found_count = 0
        processed_count = 0

        for row_idx in indices_to_enrich:
            row = rows[row_idx]
            comp_name = row.get("Cong ty", "").strip()
            proff_url = row.get("Lien He", "").strip()
            city = extract_city_from_proff_url(proff_url)
            processed_count += 1

            print(f"\n[{processed_count}/{total_need_enrich}] (No.{row.get('No.', row_idx+1)}) Xử lý: '{comp_name}' | Khu vực: '{city}'")

            # 3.1 Kiểm tra Cache trước
            cache_key = comp_name.lower().strip()
            cached_data = cache.get(cache_key)

            if cached_data:
                print(f"    [*] Nạp từ Cache: Match={cached_data.get('matched')} | Email={cached_data.get('email')}")
                if cached_data.get("email"):
                    row["Email"] = cached_data["email"]
                    row["Check gui"] = "OK"
                if cached_data.get("website"):
                    row["Lien He"] = cached_data["website"]
                if cached_data.get("phone") and not row.get("SDT"):
                    row["SDT"] = cached_data["phone"]
                if cached_data.get("address"):
                    row["Dia chi"] = cached_data["address"]
                if cached_data.get("facebook"):
                    row["Link FB"] = cached_data["facebook"]
                continue

            # 3.2 Tra cứu Google Maps
            maps_info = await query_google_maps_denmark(page, comp_name, city)

            email_found = ""
            fb_found = ""

            if maps_info["matched"]:
                print(f"    [+] Khớp Google Maps: '{maps_info['maps_title']}' ({maps_info['match_reason']})")
                if maps_info["address"]:
                    row["Dia chi"] = maps_info["address"]
                    print(f"    [+] Địa chỉ thực tế: {maps_info['address']}")
                if maps_info["phone"] and not row.get("SDT"):
                    row["SDT"] = maps_info["phone"]
                    print(f"    [+] Số điện thoại: {maps_info['phone']}")

                # Nếu có website từ Google Maps -> Cào Email B2B
                if maps_info["website"]:
                    row["Lien He"] = maps_info["website"]
                    print(f"    [+] Website công ty: {maps_info['website']}")
                    print(f"    [*] Đang cào Email B2B từ website...")
                    email_found, fb_found = await scrape_website_contacts(maps_info["website"], page)
                    if email_found:
                        row["Email"] = email_found
                        row["Check gui"] = "OK"
                        found_count += 1
                        print(f"    [>>>] TÌM THẤY EMAIL B2B: {email_found}")
                    else:
                        print(f"    [-] Không tìm thấy email trên website.")
                    if fb_found and not row.get("Link FB"):
                        row["Link FB"] = fb_found
            else:
                print(f"    [-] Không tìm thấy hoặc không khớp tên theo quy tắc nghiêm ngặt.")

            # 3.3 Lưu vào Cache và File CSV kết quả động (ADENVMAP.csv) tức thì
            cache[cache_key] = {
                "matched": maps_info["matched"],
                "maps_title": maps_info.get("maps_title", ""),
                "website": maps_info.get("website", ""),
                "phone": maps_info.get("phone", ""),
                "address": maps_info.get("address", ""),
                "email": email_found,
                "facebook": fb_found
            }
            save_cache(cache, cache_file_str)

            # Cập nhật trực tiếp vào file kết quả ADENVMAP.csv tức thì
            save_csv_dynamically(rows, fieldnames, output_csv_str)

            # Giãn cách nhẹ để an toàn IP
            await asyncio.sleep(1.2)

        await browser.close()

    print("\n" + "=" * 72)
    print("      HOÀN TẤT LÀM GIÀU DỮ LIỆU CHO ADENVMAP.CSV!")
    print(f"      Số email mới tìm thấy: {found_count}")
    print(f"      File kết quả đã được lưu động vào: {output_csv_str}")
    print("=" * 72)

def main():
    parser = argparse.ArgumentParser(description="Làm giàu dữ liệu Google Maps: ADENVIRK.csv -> ADENVMAP.csv")
    parser.add_argument("--input", "-i", default=None, help="Đường dẫn đến file CSV gốc (mặc định ADENVIRK.csv)")
    parser.add_argument("--output", "-o", default=None, help="Đường dẫn đến file CSV kết quả (mặc định ADENVMAP.csv)")
    parser.add_argument("--cache", "-c", default=None, help="Đường dẫn đến file cache JSON")
    parser.add_argument("--headless", action="store_true", default=None, help="Chạy ẩn trình duyệt (phù hợp cho VPS / server)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(input_csv=args.input, output_csv=args.output, cache_file=args.cache, headless=args.headless))

if __name__ == "__main__":
    main()
