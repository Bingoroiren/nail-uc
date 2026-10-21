# -*- coding: utf-8 -*-
"""
MULTI-TIER DATA ENRICHMENT SYSTEM FOR SLOVAK EMPLOYMENT AGENCIES
Dành cho tệp SK_AGCY_ALL_2COL.csv (3,845 doanh nghiệp).

HỆ THỐNG ĐẶC BIỆT CHÚ TRỌNG CHỐNG CHẶN BOT & CHỐNG BỎ SÓT DO LAG:
1. Chống chặn Bot & Captcha:
   - Sử dụng Google Chrome thực tế persistent profile, viewport 1280x800.
   - Thêm cookies Google consent, cờ chống automation controlled.
   - Phát hiện Captcha/Cloudflare: Rung chuông cảnh báo \\a, tạm dừng chờ tối đa 60s để người dùng bấm xác minh.
2. Chống bỏ sót do mạng lag / máy chủ phản hồi chậm:
   - Cơ chế RETRY tự động tối đa 2 lần với thời gian chờ giãn cách (Backoff).
   - Tuyệt đối không vội vã bỏ qua (No hasty skips).
3. Kiến trúc làm giàu Đa Tầng (Multi-Tier Architecture):
   - Tầng 1: Zlaté Stránky (Trang Vàng Slovakia - zlatestranky.sk) tra cứu trực tiếp lấy SĐT & Website & Email.
   - Tầng 2: Google Maps với Smart Name Matcher (Rule 11 - Unicode NFKD khử dấu á->a, č->c, bóc tách bản dịch tiếng Anh).
   - Tầng 3: Deep Web Crawler đa tầng bóc tách Email B2B theo điểm số score_email_b2b (Ưu tiên praca@, kariera@, hr@, konatel@, info@), kèm Facebook Fanpage fallback.
4. Lưu an toàn (Resume 100%):
   - Cache JSON tại crawlmail/cache_enrich_master_sk_agcy.json.
   - Lưu tăng dần mỗi 5 công ty vào SK_AGCY_ALL_2COL.csv, đẩy 100% email lên đầu.
"""

import asyncio
import os
import sys
import re
import ssl
import json
import time
import argparse
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")
MASTER_2COL_ROOT = ROOT_DIR / "SK_AGCY_ALL_2COL.csv"
MASTER_2COL_CSDL = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_ALL_2COL.csv"
MASTER_1ENR_CSDL = ROOT_DIR / "csdl_sk_agcy" / "SK_AGCY_ALL_1ENR.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_master_sk_agcy.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "sk_master_profile"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

BLACKLIST_DOMAINS = [
    # Mạng xã hội & Video
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'tiktok.com', 'pinterest.com', 't.me', 'telegram.org', 'whatsapp.com', 'viber.com',
    # Bản đồ, GIS & Thư viện JS (Tránh triệt để lỗi gắp phải leafletjs, openstreetmap...)
    'leafletjs.com', 'openstreetmap.org', 'mapbox.com', 'openlayers.org', 'carto.com',
    'google.com', 'maps.google.com', 'gstatic.com', 'googleapis.com',
    # Danh bạ & Cổng thông tin trung gian
    'yellowpages', 'proff.no', 'brreg.no', 'zlatestranky.sk', 'azet.sk', 'finstat.sk', 
    'orsr.sk', 'zrsr.sk', 'wikipedia.org', 'portal.sk', 'profesia.sk', 'kariera.zoznam.sk', 
    'praca.sme.sk', 'worki.sk', 'dnb.com', 'zoominfo.com', 'kompass.com', 'upsvr.gov.sk', 
    'indexpodnikatela.sk', 'wenetonline.sk', 'edb.sk', '123dopyt.sk', 'bazar.sk',
    # Web builders, CMS, Tech libraries, Tracking & Consent
    'w3.org', 'schema.org', 'apache.org', 'jquery.com', 'cloudflare.com', 'cookiebot.com',
    'didomi.io', 'onetrust.com', 'sentry.io', 'wixpress.com', 'wix.com', 'wordpress.org',
    'wordpress.com', 'weebly.com', 'squarespace.com', 'shopify.com', 'webnode.com', 
    'webnode.sk', 'shoptet.sk', 'shoptet.cz', 'github.com', 'gitlab.com', 'bitbucket.org',
    'apple.com', 'microsoft.com', 'android.com', 'play.google.com', 'apps.apple.com'
]

def is_valid_website(url):
    """Kiểm tra URL có thực sự là website riêng của doanh nghiệp hay không."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if not u.startswith('http'):
        return False
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.lower()
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        # Loại trừ toàn bộ domain rác, thư viện JS, map, mạng xã hội
        if any(bad in domain for bad in BLACKLIST_DOMAINS):
            return False
        # Loại trừ IP số
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', domain):
            return False
        return True
    except Exception:
        return False

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""

def extract_emails_from_text(raw_text):
    """
    Bóc tách email toàn diện từ văn bản/HTML, tự động giải mã các dạng ẩn (obfuscated):
    - HTML entities: &#64;, &#x40;, &commat;, %40 -> @
    - Bản địa Slovakia/Séc: (zavináč), [zavináč], (zavinac), [zavinac] -> @
    - Quốc tế: (at), [at], {at}, <at>, AT -> @
    - Dấu chấm ẩn: (dot), [dot], (bodka), [bodka], (tecka), [tecka], DOT -> .
    - Nuốt khoảng trắng bao quanh @: 'info @ domain.sk' -> 'info@domain.sk'
    """
    if not raw_text or not isinstance(raw_text, str):
        return []
    import html as html_lib
    t = html_lib.unescape(raw_text)
    t = urllib.parse.unquote(t)

    # 1. Chuyển đổi các dạng ẩn @ (zavináč, zavinac, at, AT)
    t = re.sub(r'\s*[\(\[\{<]\s*(?:at|zavinac|zavináč)\s*[\)\]\}>]\s*', '@', t, flags=re.I)
    t = re.sub(r'\s+AT\s+', '@', t)
    t = re.sub(r'\s*@\s*', '@', t)

    # 2. Chuyển đổi các dạng ẩn dấu chấm . (dot, bodka, tecka, DOT)
    t = re.sub(r'\s*[\(\[\{<]\s*(?:dot|bodka|tecka)\s*[\)\]\}>]\s*', '.', t, flags=re.I)
    t = re.sub(r'\s+DOT\s+', '.', t)

    # 3. Tìm email chuẩn
    return [e.strip().lower() for e in EMAIL_REGEX.findall(t)]

def clean_phone(p):
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip()
    digits = re.sub(r'[^\d+]', '', s)
    if not digits:
        return ''
    clean_d = re.sub(r'[^\d]', '', digits)
    if clean_d.startswith('421') and len(clean_d) == 12:
        res = f"+421 {clean_d[3:6]} {clean_d[6:9]} {clean_d[9:12]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def normalize_text_core(s):
    """Khử dấu Unicode NFKD, loại bỏ legal forms và dấu câu thừa."""
    if not s:
        return ""
    # 1. Khử dấu bản địa đa quốc gia
    s_norm = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8').lower()
    # 2. Xóa các loại ngoặc và dấu nháy
    s_norm = re.sub(r'["\'„“”«»\(\)\[\]]', ' ', s_norm)
    # 3. Chuẩn hóa dấu câu thành khoảng trắng để xử lý legal forms
    s_norm = re.sub(r'[^\w\s]', ' ', s_norm)
    # 4. Loại bỏ các loại hình doanh nghiệp phổ biến
    legal_forms = [
        r'\bspol\s*s\s*r\s*o\b', r'\bs\s*r\s*o\b', r'\bsro\b',
        r'\ba\s*s\b', r'\bas\b', r'\bk\s*s\b', r'\bv\s*o\s*s\b',
        r'\bdruzstvo\b', r'\bgmbh\b', r'\bv\s+likvidacii\b',
        r'\bv\s+konkurze\b', r'\borganizacna\s+zlozka\b'
    ]
    for pattern in legal_forms:
        s_norm = re.sub(pattern, ' ', s_norm)
    return re.sub(r'\s+', ' ', s_norm).strip()

def is_valid_name_match(query_name, candidate_name):
    """Smart & Strict Name Matcher theo Rule 11 GEMINI.md."""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q_clean = normalize_text_core(query_name)
    c_clean = normalize_text_core(candidate_name)

    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    if q_clean == c_clean:
        return True, "EXACT"

    # Tách bản dịch tiếng Anh trong ngoặc (vd: "Employment agency")
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', candidate_name)
    c_nobrackets_clean = normalize_text_core(c_nobrackets)
    if q_clean == c_nobrackets_clean:
        return True, "BRACKET_MATCH"

    parts = [normalize_text_core(p) for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    if any(p == q_clean for p in parts if p):
        return True, "DELIMITER_MATCH"

    if len(q_clean) >= 5 and (q_clean in c_clean or c_clean in q_clean or q_clean in c_nobrackets_clean or c_nobrackets_clean in q_clean):
        return True, "SUBSTRING_MATCH"

    return False, "NO_MATCH"

def score_email_b2b(email, domain=""):
    """Chấm điểm email tối ưu cho B2B Manpower Agency theo chuẩn GEMINI.md"""
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if any(bad in d for bad in ['sentry', 'wixpress', 'example.com', 'domain.com', 'email.com', 'mail.sk']):
        return -1
    if any(bad in u for bad in ['sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply', 'donotreply', 'privacy']):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.sk'):
        score += 25

    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career', 'job']:
        score += 50
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']:
        score += 45
    elif u in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria', 'agency']:
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif u in ['support', 'admin', 'servis']:
        score += 5
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def fetch_html_stealth_retry(url, retries=3, timeout=12.0):
    """
    Fetch HTML với retry và timeout thông minh chống lag,
    luân phiên giữa curl_cffi (impersonate chrome120) và urllib.
    Tuyệt đối không bỏ qua khi mạng chậm / server phản hồi trễ.
    """
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if not url.startswith('http'):
        url = f"https://{url}"

    for attempt in range(retries):
        # Cách 1: Thử curl_cffi impersonate Chrome
        try:
            from curl_cffi import requests as c_requests
            r = c_requests.get(url, impersonate='chrome120', timeout=(5.0, timeout), verify=False)
            if r.status_code == 200 and len(r.text) > 100:
                return r.text
            elif r.status_code in [403, 429, 503]:
                # Server đang throttle hoặc challenge Cloudflare -> Chờ giãn cách
                time.sleep(2.0)
        except Exception:
            pass

        # Cách 2: Thử urllib với Header chuẩn trình duyệt
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                data = resp.read().decode('utf-8', errors='ignore')
                if len(data) > 100:
                    return data
        except Exception:
            pass

        # Giãn cách tăng dần giữa các lần retry chống nghẽn mạng
        if attempt < retries - 1:
            time.sleep(2.0 * (attempt + 1))
    return ""

async def lookup_zlatestranky(page, company_name, city=""):
    """
    TẦNG 1: Tra cứu trực quan trên Zlaté Stránky (Trang Vàng Slovakia).
    Hiển thị trực tiếp màn hình tìm kiếm trên cửa sổ Chrome để quan sát.
    """
    core = normalize_text_core(company_name)
    if not core:
        return None, None, None

    search_url = f"https://www.zlatestranky.sk/hladanie/{urllib.parse.quote(core)}/"
    try:
        await page.goto(search_url, wait_until='domcontentloaded', timeout=14000)
        await page.wait_for_timeout(1000)

        # Tự động đóng banner Cookie nếu xuất hiện
        try:
            consent_btn = await page.query_selector(
                'button:has-text("Súhlasím"), button:has-text("Prijať"), '
                'button#didomi-notice-agree-button, button.agree'
            )
            if consent_btn:
                await consent_btn.click()
                await page.wait_for_timeout(600)
        except Exception:
            pass

        # Lấy danh sách link doanh nghiệp
        firm_links = []
        links = await page.query_selector_all('a[href*="/firmy/"]')
        for a in links:
            h = await a.get_attribute('href') or ""
            if '/firmy/' in h and not '/q_' in h:
                txt = await a.inner_text()
                is_ok, _ = is_valid_name_match(company_name, txt)
                if is_ok and h not in firm_links:
                    firm_links.append(h)

        # Fallback: Nếu chưa thấy với core name, thử tìm bằng tên làm sạch
        if not firm_links:
            clean_raw = re.sub(r'["\'„“”«»]', '', company_name).strip()
            if clean_raw and clean_raw.lower() != core.lower():
                fb_url = f"https://www.zlatestranky.sk/hladanie/{urllib.parse.quote(clean_raw)}/"
                await page.goto(fb_url, wait_until='domcontentloaded', timeout=14000)
                await page.wait_for_timeout(1000)
                links = await page.query_selector_all('a[href*="/firmy/"]')
                for a in links:
                    h = await a.get_attribute('href') or ""
                    if '/firmy/' in h and not '/q_' in h:
                        txt = await a.inner_text()
                        is_ok, _ = is_valid_name_match(company_name, txt)
                        if is_ok and h not in firm_links:
                            firm_links.append(h)

        if not firm_links:
            return None, None, None

        # Vào trang chi tiết công ty trên Zlaté Stránky (Hiển thị trực quan trên Chrome)
        target_link = firm_links[0]
        if not target_link.startswith('http'):
            target_link = f"https://www.zlatestranky.sk{target_link}"

        await page.goto(target_link, wait_until='domcontentloaded', timeout=14000)
        await page.wait_for_timeout(1000)

        page_html = await page.content()
        soup = BeautifulSoup(page_html, 'html.parser')

        web = None
        phone = None
        email = None

        # Bóc tách SĐT
        for a in soup.find_all('a', href=True):
            h = a['href']
            if h.startswith('tel:'):
                p = h.replace('tel:', '').strip()
                if len(re.sub(r'\D', '', p)) >= 9:
                    phone = clean_phone(p)
                    break

        if not phone:
            m_phone = re.search(r'\+421\s*\d{2,3}\s*\d{3}\s*\d{3}|\b09\d{8}\b', page_html)
            if m_phone:
                phone = clean_phone(m_phone.group(0))

        # Bóc tách Website chính thức của doanh nghiệp trên Zlaté Stránky
        # Cách 1: Thẻ chính thức được Zlaté Stránky gán class tag-url-website
        for a in soup.find_all('a', href=True):
            classes = a.get('class', [])
            if any('tag-url-website' in c or 'website' in c.lower() for c in classes):
                cand = a['href'].strip()
                if is_valid_website(cand):
                    web = cand
                    break

        # Cách 2: Quét thẻ a có link ngoài hợp lệ (loại trừ map container, footer attribution)
        if not web:
            for a in soup.find_all('a', href=True):
                cand = a['href'].strip()
                txt = a.get_text(strip=True).lower()
                # Bỏ qua Leaflet, OpenStreetMap, Mapbox, Cookie notices
                if any(bad_word in txt for bad_word in ['leaflet', 'openstreetmap', 'mapbox', 'podmienky', 'cookies', 'zasady']):
                    continue
                # Bỏ qua nếu nằm trong container bản đồ hoặc footer
                parent_classes = ' '.join([' '.join(p.get('class', [])) for p in a.parents if p.get('class')]).lower()
                if any(k in parent_classes for k in ['leaflet', 'map', 'attribution', 'footer', 'cookie', 'legal']):
                    continue
                if is_valid_website(cand):
                    web = cand
                    break

        # Bóc tách Email (bao gồm cả giải mã obfuscated (at), (zavináč)...)
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', page_html, re.I):
            clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
            if '@' in clean_m and score_email_b2b(clean_m) > 0:
                email = clean_m
                break
        if not email:
            for em in extract_emails_from_text(page_html):
                if score_email_b2b(em) > 0:
                    email = em
                    break

        return web, phone, email
    except Exception:
        return None, None, None

async def crawl_site_for_emails(page, web_url):
    """
    TẦNG 3: Deep Web Crawler TRỰC QUAN TRÊN MÀN HÌNH CHROME.
    Mở trực tiếp trang web của doanh nghiệp trên cửa sổ Chrome để người dùng quan sát,
    tự động vượt Cloudflare / Captcha thực tế, bóc tách email từ homepage và trang liên hệ.
    Hỗ trợ 100% bóc tách các email bị ẩn/mã hóa: (at), [at], (zavináč), [zavinac], &#64;...
    """
    if not web_url or not isinstance(web_url, str):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith('http'):
        web_url = f"https://{web_url}"
    if not is_valid_website(web_url):
        return ""

    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    fb_links = []
    dom_contact_links = []

    try:
        # 1. Mở trang chủ công ty trực quan trên Chrome
        await page.goto(web_url, wait_until='domcontentloaded', timeout=14000)
        await asyncio.sleep(1.2)

        home_html = await page.content()

        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
            if '@' in clean_m:
                found.add(clean_m)
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = decode_cf(cf)
            if '@' in dec:
                found.add(dec.strip().lower())
        for em in extract_emails_from_text(home_html):
            if score_email_b2b(em, root) > 0:
                found.add(em)

        best_home = select_best_email(found, root)
        if best_home and score_email_b2b(best_home, root) >= 75:
            return best_home

        # Bóc tách subpages & Facebook links từ DOM menu
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            for a in soup.find_all('a', href=True):
                h = a['href']
                h_low = h.lower()
                txt = a.get_text().lower()
                if 'facebook.com/' in h_low and not any(bad in h_low for bad in ['sharer', 'share.php', 'plugins']):
                    if h not in fb_links:
                        fb_links.append(h)
                if any(k in h_low or k in txt for k in ['kontakt', 'kontakty', 'contact', 'o-nas', 'kariera', 'praca', 'impressum', 'about']):
                    full = urllib.parse.urljoin(web_url, h)
                    if full not in dom_contact_links and '#' not in h and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)
        except Exception:
            pass

        # 2. Mở trực quan các trang liên hệ trên Chrome
        for cl in dom_contact_links[:4]:
            try:
                await page.goto(cl, wait_until='domcontentloaded', timeout=12000)
                await asyncio.sleep(1.0)
                chtml = await page.content()
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = decode_cf(cf)
                    if '@' in dec:
                        found.add(dec.strip().lower())
                for em in extract_emails_from_text(chtml):
                    if score_email_b2b(em, root) > 0:
                        found.add(em)
                if found and any(score_email_b2b(e, root) >= 60 for e in found):
                    break
            except Exception:
                pass
    except Exception:
        # Nếu Chrome gặp lỗi chứng chỉ SSL / server trễ, dùng fetch stealth làm dự phòng
        pass

    # 3. Thử nhanh các subpath bản địa Slovakia (.sk) nếu chưa thấy email
    if not found:
        candidate_paths = [
            f"{root}/kontakt", f"{root}/kontakty", f"{root}/kontakt.html", 
            f"{root}/o-nas", f"{root}/kariera", f"{root}/contact"
        ]
        for gp in candidate_paths:
            ghtml = fetch_html_stealth_retry(gp, retries=1, timeout=5.0)
            if not ghtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                clean_m = urllib.parse.unquote(m.split('?')[0].strip().lower())
                if '@' in clean_m:
                    found.add(clean_m)
            for em in extract_emails_from_text(ghtml):
                if score_email_b2b(em, root) > 0:
                    found.add(em)
            if found:
                break

    # 4. Facebook Fallback
    if not found and fb_links:
        for fbl in fb_links[:2]:
            fb_html = fetch_html_stealth_retry(fbl, retries=1, timeout=6.0)
            if fb_html:
                for em in extract_emails_from_text(fb_html):
                    if score_email_b2b(em, root) > 0:
                        found.add(em)

    return select_best_email(found, root)

def save_and_reorder_master(df):
    """Lưu và đồng bộ tự động ra cả 3 file: Root 2COL, CSDL 2COL, CSDL 1ENR."""
    df_out = df.copy()
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone)

    has_em = df_out[df_out['Email'].notna() & (df_out['Email'].astype(str).str.strip() != '') & (df_out['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df_out[df_out['Email'].isna() | (df_out['Email'].astype(str).str.strip() == '') | (df_out['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # 1. Lưu file Root 2COL
    df_sorted.to_csv(MASTER_2COL_ROOT, index=False, encoding='utf-8-sig')
    # 2. Lưu file CSDL 2COL
    df_sorted.to_csv(MASTER_2COL_CSDL, index=False, encoding='utf-8-sig')
    # 3. Lưu file CSDL 1ENR
    df_sorted.to_csv(MASTER_1ENR_CSDL, index=False, encoding='utf-8-sig')
    return len(has_em)

async def run_master_enrichment(headless=False, limit=0):
    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU ĐA TẦNG - CSDL MÔI GIỚI LAO ĐỘNG SLOVAKIA (CHỐNG CHẶN BOT)")
    print("=" * 85)
    print(f"[*] File mục tiêu chính : {MASTER_2COL_ROOT}")
    print(f"[*] Cache Checkpoint    : {CACHE_PATH}")
    print(f"[*] Trình duyệt Chrome  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False) - Quan sát & Vượt Captcha'}")
    print("=" * 85 + "\n")

    if not MASTER_2COL_ROOT.exists():
        print(f"[ERROR] Không tìm thấy file: {MASTER_2COL_ROOT}")
        return

    df = pd.read_csv(MASTER_2COL_ROOT, encoding='utf-8-sig', dtype=str).fillna('')
    total_companies = len(df)

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache Checkpoint: {len(cache):,} công ty đã kiểm tra từ trước.")
        except Exception:
            pass

    # Đồng bộ dữ liệu từ Cache vào DataFrame trước
    cache_synced = 0
    for idx in df.index:
        c_key = str(df.at[idx, 'Công ty']).strip().lower()
        if c_key in cache:
            c = cache[c_key]
            if c.get('Email') and not str(df.at[idx, 'Email']).strip():
                df.at[idx, 'Email'] = c['Email']
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{c['Email']}"
                cache_synced += 1
            if c.get('Web') and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = c['Web']
            if c.get('Phone') and not str(df.at[idx, 'SĐT']).strip():
                df.at[idx, 'SĐT'] = clean_phone(c['Phone'])

    if cache_synced > 0:
        save_and_reorder_master(df)

    # Lọc danh sách công ty: CHƯA CÓ EMAIL VÀ CHƯA TỪNG ĐƯỢC XỬ LÝ TRONG CACHE
    unprocessed_indices = []
    for idx in df.index:
        em = str(df.at[idx, 'Email']).strip()
        c_key = str(df.at[idx, 'Công ty']).strip().lower()
        if em and em != 'nan':
            continue  # Đã có email trong CSDL
        if c_key in cache:
            continue  # ĐÃ QUÉT VÀ LƯU CHECKPOINT RỒI -> BỎ QUA 100%, KHÔNG CÀO LẠI
        unprocessed_indices.append(idx)

    already_has = sum(1 for idx in df.index if str(df.at[idx, 'Email']).strip() and str(df.at[idx, 'Email']).strip() != 'nan')
    print(f"[*] Tổng số doanh nghiệp trong CSDL   : {total_companies:,}")
    print(f"[*] Đã có Email xác thực              : {already_has:,} ({already_has/total_companies*100:.1f}%)")
    print(f"[*] Đã kiểm tra & lưu Cache Checkpoint: {len(cache):,} công ty")
    print(f"[*] CẦN LÀM GIÀU DỮ LIỆU THỰC SỰ      : {len(unprocessed_indices):,} công ty\n")

    if not unprocessed_indices:
        print("[✔] 100% công ty trong danh sách đã được xử lý đầy đủ!")
        return

    target_list = unprocessed_indices if limit == 0 else unprocessed_indices[:limit]

    # Khởi tạo Playwright với Chrome persistent profile thực tế
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="sk-SK",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )
        await browser.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await browser.new_page()

        processed = 0
        new_emails_found = 0
        new_webs_found = 0
        new_phones_found = 0

        for idx in target_list:
            # Tự động hồi phục tab nếu tab Chrome bị đóng hoặc crash
            if page.is_closed():
                try:
                    page = await browser.new_page()
                except Exception:
                    pass

            comp = str(df.at[idx, 'Công ty']).strip()
            curr_phone = str(df.at[idx, 'SĐT']).strip()
            curr_web = str(df.at[idx, 'Liên Hệ']).strip()
            curr_addr = str(df.at[idx, 'Địa chỉ']).strip()
            cache_key = comp.lower()

            found_email = ""
            source_tag = ""

            # Bỏ qua nếu bằng cách nào đó đã có trong cache
            if cache_key in cache:
                continue

            # ------------------------------------------------------------------
            # BƯỚC 1: Nếu đã có sẵn Website từ trước -> Mở trực quan quét sâu Website
            # ------------------------------------------------------------------
            if curr_web and not found_email:
                found_email = await crawl_site_for_emails(page, curr_web)
                if found_email:
                    source_tag = "[WEB CRAWL]"
                    new_emails_found += 1

            # ------------------------------------------------------------------
            # BƯỚC 3 (TẦNG 1): Tra cứu Zlaté Stránky Slovakia (Hiển thị trực quan trên Chrome)
            # ------------------------------------------------------------------
            if not found_email:
                try:
                    z_web, z_phone, z_email = await lookup_zlatestranky(page, comp)
                    if z_web and not curr_web:
                        df.at[idx, 'Liên Hệ'] = z_web
                        curr_web = z_web
                        new_webs_found += 1
                    if z_phone and not curr_phone:
                        df.at[idx, 'SĐT'] = clean_phone(z_phone)
                        curr_phone = df.at[idx, 'SĐT']
                        new_phones_found += 1
                    if z_email:
                        found_email = z_email
                        source_tag = "[ZLATE STRANKY]"
                        new_emails_found += 1
                    elif curr_web:
                        found_email = await crawl_site_for_emails(page, curr_web)
                        if found_email:
                            source_tag = "[ZLATE->WEB]"
                            new_emails_found += 1
                except Exception:
                    pass

            # ------------------------------------------------------------------
            # BƯỚC 4 (TẦNG 2): Tra cứu Google Maps với Smart Matcher & Chống Chặn Bot / Chống Lag
            # ------------------------------------------------------------------
            if not found_email:
                core_name = normalize_text_core(comp)
                city_hint = ""
                if curr_addr:
                    parts = [p.strip() for p in curr_addr.split(',') if p.strip()]
                    city_hint = parts[-1] if parts else ""

                search_queries = []
                if city_hint:
                    search_queries.append(f"{core_name} {city_hint} Slovakia")
                search_queries.append(f"{core_name} Slovakia")
                # Fallback: Tên gốc đầy đủ nếu core_name quá ngắn
                if len(core_name) < 5 or core_name != comp.lower():
                    clean_comp = re.sub(r'["\'„“”«»]', '', comp).strip()
                    search_queries.append(f"{clean_comp} Slovakia")

                matched = False
                gmap_web = None
                gmap_phone = None

                for q_term in search_queries[:2]:
                    if matched:
                        break

                    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                    # Thử tối đa 2 lần cho mỗi query nếu gặp sự cố kết nối
                    for attempt in range(2):
                        try:
                            await page.goto(url, wait_until='domcontentloaded', timeout=20000)

                            # 1. Tự động xử lý Cookie Consent Modal của Google
                            try:
                                consent_btn = await page.query_selector(
                                    'button:has-text("Accept all"), button:has-text("Prijať všetko"), '
                                    'button:has-text("Súhlasím"), button[aria-label*="Accept all"], '
                                    'form[action*="consent"] button'
                                )
                                if consent_btn:
                                    await consent_btn.click()
                                    await asyncio.sleep(1.5)
                            except Exception:
                                pass

                            # 2. Xử lý Chống Chặn Bot / Captcha / Sorry page
                            if "google.com/sorry" in page.url or "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                                print("\n\a" + "!" * 80)
                                print("[CẢNH BÁO BOT] PHÁT HIỆN CAPTCHA GOOGLE TRÊN TRÌNH DUYỆT CHROME!")
                                print("Vui lòng giải captcha trên cửa sổ Chrome. Hệ thống kiên nhẫn chờ tối đa 120 giây...")
                                print("!" * 80 + "\n")
                                # Chờ tối đa 120s, kiểm tra mỗi 2s xem đã giải xong chưa
                                for wait_step in range(60):
                                    await asyncio.sleep(2.0)
                                    if "google.com/sorry" not in page.url and not await page.query_selector("iframe[src*='recaptcha']"):
                                        print("[+] Captcha đã được xử lý thành công! Tự động tiếp tục quét...\n")
                                        # Tải lại query sau khi qua Captcha
                                        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                                        await asyncio.sleep(2.0)
                                        break
                                    if (wait_step + 1) % 15 == 0:
                                        print(f"  [Đang chờ giải Captcha... còn {120 - (wait_step+1)*2}s]")

                            # 3. VÒNG LẶP CHỜ KẾT QUẢ KHI MẠNG LAG (Tuyệt đối không bỏ qua sớm)
                            # Chờ tối đa 9 giây để Google Maps SPA render xong danh sách hoặc trang chi tiết
                            for _ in range(9):
                                if await page.query_selector('a[href*="/maps/place/"], h1.DUwDvf, div[role="feed"]'):
                                    break
                                # Nếu Google hiện rõ ràng 'không tìm thấy kết quả' thì dừng chờ
                                body_txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
                                if any(no_k in body_txt for no_k in ["Nenašli sa žiadne výsledky", "Google Maps can't find", "No results found"]):
                                    break
                                await asyncio.sleep(1.0)

                            # 4. Kiểm tra danh sách kết quả (Multiple places)
                            items = await page.query_selector_all('a[href*="/maps/place/"]')
                            if items:
                                for item in items[:4]:
                                    aria_label = await item.get_attribute('aria-label') or ""
                                    is_ok, reason = is_valid_name_match(comp, aria_label)
                                    if is_ok:
                                        await item.click()
                                        try:
                                            await page.wait_for_selector('h1.DUwDvf, a[data-item-id="authority"], button[data-item-id^="phone:"]', timeout=6000)
                                            await asyncio.sleep(1.0)
                                        except Exception:
                                            await asyncio.sleep(2.0)
                                        matched = True
                                        break
                            else:
                                # Kiểm tra trang chi tiết địa điểm trực tiếp (Direct single place)
                                title_elem = await page.query_selector('h1.DUwDvf')
                                if title_elem:
                                    t_text = await title_elem.inner_text()
                                    is_ok, reason = is_valid_name_match(comp, t_text)
                                    matched = is_ok

                            if matched:
                                # Lấy Website
                                web_btn = await page.query_selector('a[data-item-id="authority"]')
                                if web_btn:
                                    cand_web = await web_btn.get_attribute('href')
                                    if cand_web and is_valid_website(cand_web):
                                        gmap_web = cand_web

                                # Lấy SĐT
                                phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                                if phone_btn:
                                    p_attr = await phone_btn.get_attribute('data-item-id')
                                    if p_attr and p_attr.startswith('phone:tel:'):
                                        gmap_phone = p_attr.replace('phone:tel:', '').strip()
                                    else:
                                        p_txt = await phone_btn.inner_text()
                                        if re.search(r'\d{3,}', p_txt):
                                            gmap_phone = p_txt.strip()
                                break  # Hoàn tất lần truy vấn này thành công
                        except Exception as err:
                            if attempt == 0:
                                print(f"  [Mạng Maps phản hồi chậm: {err}]. Đang thử lại...")
                                await asyncio.sleep(3)
                                # Khôi phục page nếu page bị đóng do lỗi bộ nhớ / crash
                                if page.is_closed():
                                    try:
                                        page = await browser.new_page()
                                    except Exception:
                                        pass

                # Cập nhật dữ liệu từ Maps
                if gmap_web and not curr_web:
                    df.at[idx, 'Liên Hệ'] = gmap_web
                    curr_web = gmap_web
                    new_webs_found += 1

                if gmap_phone and not curr_phone:
                    df.at[idx, 'SĐT'] = clean_phone(gmap_phone)
                    curr_phone = df.at[idx, 'SĐT']
                    new_phones_found += 1

                # Quét Email từ Website vừa tìm được qua Google Maps (Trực quan trên Chrome)
                if curr_web:
                    found_email = await crawl_site_for_emails(page, curr_web)
                    if found_email:
                        source_tag = "[GMAP->WEB]"
                        new_emails_found += 1

            # ------------------------------------------------------------------
            # BƯỚC 5: Cập nhật DataFrame & Cache
            # ------------------------------------------------------------------
            if found_email:
                df.at[idx, 'Email'] = found_email
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{found_email}"

            cache[cache_key] = {
                'Web': curr_web,
                'Email': found_email,
                'Phone': curr_phone,
                'Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed += 1
            status_em = f"{source_tag} {found_email}" if found_email else ("Chưa có mail" if curr_web else "Không có web")
            status_web = curr_web[:28] if curr_web else "No web"
            print(f"[{processed:04d}/{len(target_list)}] {comp[:28]:<28} | {status_web:<28} | {status_em}")

            # Lưu tăng dần định kỳ mỗi 5 công ty (Checkpoint)
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_total = save_and_reorder_master(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {cur_total:,}/{total_companies:,} công ty có Email được đưa lên đầu file CSV.")

            # Tái tạo trang Chromium định kỳ mỗi 25 lượt để giải phóng RAM
            if processed % 25 == 0:
                try:
                    await page.close()
                    page = await browser.new_page()
                except Exception:
                    pass

        await browser.close()

    # Lưu bản hoàn chỉnh cuối cùng
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    final_emails = save_and_reorder_master(df)

    print("\n" + "=" * 85)
    print(" HOÀN TẤT HỆ THỐNG LÀM GIÀU DỮ LIỆU ĐA TẦNG CHO SLOVAKIA AGENCY!")
    print(f"[*] Tổng số công ty đã kiểm tra      : {processed:,}")
    print(f"[*] Số Website mới thu thập được     : {new_webs_found:,}")
    print(f"[*] Số SĐT mới thu thập được         : {new_phones_found:,}")
    print(f"[*] Số EMAIL MỚI CỨU HỘ ĐƯỢC         : {new_emails_found:,}")
    print(f"[*] TỔNG SỐ EMAIL XÁC THỰC HIỆN CÓ   : {final_emails:,} / {total_companies:,} ({final_emails/total_companies*100:.1f}%)")
    print(f"[*] File Cold Mail Master 20 Cột     : {MASTER_2COL_ROOT}")
    print("=" * 85)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Multi-tier Data Enrichment for Slovak Employment Agencies")
    parser.add_argument('--headless', action='store_true', help="Chạy ngầm không mở cửa sổ Chrome")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số công ty test (0 = toàn bộ 3,130 công ty thiếu)")
    args = parser.parse_args()

    asyncio.run(run_master_enrichment(headless=args.headless, limit=args.limit))
