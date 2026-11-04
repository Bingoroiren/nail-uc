# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU NHÀ THẦU XÂY DỰNG BỈ TỪ PAGESDOR.BE (PLAYWRIGHT STEALTH)
=============================================================================
Kỹ năng: data-standards, crawl-mail
Mục tiêu: Cào danh mục "Entrepreneurs - Bâtiments résidentiels" (Nhà thầu xây dựng dân dụng)
Nguồn: https://www.pagesdor.be/entreprises/entrepreneurs+-+b%C3%A2timents+r%C3%A9sidentiels/

Quy chuẩn kỹ thuật:
1. CSV ONLY (utf-8-sig) - Tuyệt đối không dùng Excel (Rule 1)
2. SĐT chuẩn nháy đơn ' ('+32...) (Rule 2)
3. Bóc tách email đa tầng:
   - Trực tiếp từ nút chọn hộp mail (<a href="mailto:...">) & JSON-LD LocalBusiness trên Pages d'Or
   - Quét sâu website chính thức (/contact, /contactez-nous, /a-propos...)
   - Chấm điểm chọn DUY NHẤT 1 email B2B tối ưu cho cung ứng nhân lực (Rule 3)
4. Trình duyệt trực quan (headless=False - Rule 4) hiển thị tiến độ và xử lý challenge
5. Lưu tăng dần (Incremental Checkpoint) & Cache JSON Resume 100% (Rule 5)
6. Đẩy 100% dòng có email lên đầu danh sách (dòng 1..N)
7. Đặt tên file chuẩn 17 ký tự: BE_CNST_PDOR_0RAW.csv, BE_CNST_PDOR_2COL.csv (Rule 10)
8. Loại trừ danh sách đen cố định (Rule 12): Scandi Standard, Biliarta, Daigre
"""

import sys
import os
import re
import csv
import json
import time
import random
import argparse
import urllib.parse
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
import curl_cffi.requests as requests
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# File outputs tuân thủ chuẩn 17 ký tự (Rule 10)
RAW_CSV = ROOT_DIR / "BE_CNST_PDOR_0RAW.csv"
COLDMAIL_CSV = ROOT_DIR / "BE_CNST_PDOR_2COL.csv"
READY_CSV = ROOT_DIR / "BE_CNST_PDOR_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_be_cnst_pdor.json"

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')

JUNK_EMAIL_DOMAINS = {
    'example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io',
    'wixpress.com', 'wordpress.com', 'pagesdor.be', 'goudengids.be', 'fcrmedia.be',
    'fcrmedia.com', 'goldenpages.be', 'yellowpages.be', 'squarespace.com'
}

JUNK_USERNAMES = {
    'support', 'example', 'sample', 'youremail', 'your-email', 'someone',
    'nobody', 'user', 'name', 'john.doe', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'admin', 'mailer-daemon', 'noreply', 'no-reply'
}

AGGREGATOR_DOMAINS = {
    'pagesdor.be', 'goudengids.be', 'goldenpages.be', 'fcrmedia.be', 'fcrmedia.com',
    'facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'google.com',
    'youtube.com', 'twitter.com', 'x.com', 'tiktok.com', 'pinterest.com'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigre'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    if not p_clean:
        return ""
    if not p_clean.startswith('+') and not p_clean.startswith('00'):
        if p_clean.startswith('0'):
            p_clean = '+32 ' + p_clean[1:]
        elif p_clean.startswith('32'):
            p_clean = '+' + p_clean
    return f"'{p_clean}"

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()

    em = re.sub(r'(\.[a-z]{2,6})www\..*$', r'\1', em, flags=re.I)
    em = re.sub(r'(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$', r'\1', em, flags=re.I)

    if not re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""

    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return ""
    if u in JUNK_USERNAMES or any(k in u for k in ['youremail', 'your-email']):
        return ""
    if any(em.endswith(ext) for ext in INVALID_EXTS):
        return ""

    return em

def decode_cloudflare(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return clean_email(email)
    except Exception:
        return ""

def score_email_b2b(email, domain=""):
    """Chấm điểm email tối ưu cho cung ứng nhân lực ngành Nhà thầu xây dựng dân dụng"""
    e = clean_email(email)
    if not e:
        return -1
    u, d = e.split('@', 1)
    score = 10

    clean_dom = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50
    elif d.endswith('.be'):
        score += 25
    elif d.endswith('.com') or d.endswith('.eu'):
        score += 15

    # 1. Ưu tiên Nhân sự / Tuyển dụng
    if any(u == k or u.startswith(k) for k in ['recrutement', 'jobs', 'rh', 'personnel', 'carrieres', 'hr', 'recruitment', 'work', 'werf', 'vacature', 'personeel']):
        score += 50
    # 2. Ban giám đốc / Quản lý điều hành / Chỉ huy
    elif any(u == k or u.startswith(k) for k in ['direction', 'gerant', 'patron', 'ceo', 'director', 'administrateur', 'production', 'zaakvoerder', 'bestuur', 'werfleider']):
        score += 45
    # 3. Cổng liên hệ chính thức / Kinh doanh / Báo giá
    elif any(u == k or u.startswith(k) for k in ['info', 'contact', 'bureau', 'secretariat', 'commandes', 'sales', 'commercial', 'devis', 'offerte', 'kantoor']):
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['skynet.be', 'proximus.be', 'telenet.be']:
        score += 20
    elif d in ['gmail.com', 'hotmail.com', 'outlook.com', 'live.be']:
        score += 10

    return score

def select_best_email(emails, domain=""):
    valid = [clean_email(e) for e in emails if clean_email(e)]
    valid = [e for e in set(valid) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def fetch_html(url, timeout=6):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-BE,fr;q=0.9,nl-BE;q=0.8,en;q=0.7'
    }
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=timeout, verify=False, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

def extract_emails_from_page(html_text, domain=""):
    found = set()
    if not html_text:
        return found

    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare(cf)
        if dec: found.add(dec)

    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = clean_email(m)
        if clean_m: found.add(clean_m)

    for m in EMAIL_REGEX.findall(html_text):
        clean_m = clean_email(m)
        if clean_m: found.add(clean_m)

    obf_patterns = [
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([a-zA-Z0-9.-]{1,50})\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*([a-zA-Z]{2,10})', re.I),
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*&#64;\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,10})', re.I)
    ]
    for pat in obf_patterns:
        for match in pat.findall(html_text):
            if len(match) == 3:
                cand = clean_email(f"{match[0]}@{match[1]}.{match[2]}")
                if cand: found.add(cand)
            elif len(match) == 2:
                cand = clean_email(f"{match[0]}@{match[1]}")
                if cand: found.add(cand)

    return found

def crawl_company_website(website_url):
    """Quét trang chủ và các trang con liên hệ của website doanh nghiệp Bỉ"""
    if not website_url or not isinstance(website_url, str):
        return ""
    u_str = website_url.strip()
    if not u_str.startswith(('http://', 'https://')):
        u_str = 'https://' + u_str

    try:
        parsed = urllib.parse.urlparse(u_str)
        domain = parsed.netloc.lower()
    except Exception:
        return ""

    html = fetch_html(u_str, timeout=5)
    if not html and u_str.startswith('https://'):
        html = fetch_html(u_str.replace('https://', 'http://'), timeout=5)

    all_emails = extract_emails_from_page(html, domain)
    best = select_best_email(all_emails, domain)
    if best and score_email_b2b(best, domain) >= 60:
        return best

    # Bóc tách menu subpages liên hệ
    candidate_links = []
    contact_keywords = [
        'contact', 'contactez', 'contact-us', 'contactus',
        'a-propos', 'apropos', 'qui-sommes-nous', 'over-ons',
        'recrutement', 'jobs', 'carrieres', 'mentions-legales',
        'impressum', 'wie-zijn-wij', 'contacteer-ons', 'offerte'
    ]

    if html:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            anchor_text = a.get_text().strip().lower()
            if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
                continue

            sub_full = urllib.parse.urljoin(u_str, href)
            try:
                sub_parsed = urllib.parse.urlparse(sub_full)
                if sub_parsed.netloc.lower() != domain:
                    continue
                path_lower = sub_parsed.path.lower()
                prio = 0
                for kw in contact_keywords:
                    if kw in path_lower or kw in anchor_text:
                        prio = 10
                        break
                if prio > 0 and sub_full not in [lnk for _, lnk in candidate_links]:
                    candidate_links.append((prio, sub_full))
            except Exception:
                pass

    candidate_links.sort(key=lambda x: x[0], reverse=True)
    unique_subs = []
    seen_subs = {u_str.rstrip('/')}
    for prio, s_url in candidate_links:
        clean_s = s_url.rstrip('/')
        if clean_s not in seen_subs:
            seen_subs.add(clean_s)
            unique_subs.append(s_url)
            if len(unique_subs) >= 4:
                break

    for sub_url in unique_subs:
        sub_html = fetch_html(sub_url, timeout=3)
        if sub_html:
            all_emails.update(extract_emails_from_page(sub_html, domain))
            best = select_best_email(all_emails, domain)
            if best and score_email_b2b(best, domain) >= 60:
                return best

    return select_best_email(all_emails, domain)

def parse_detail_page(page, detail_url, item_summary):
    """Truy cập thẻ chi tiết bằng Playwright Stealth, bóc tách nút hộp mail, JSON-LD và Website"""
    comp_name = item_summary.get('name', '').strip()
    phone = clean_phone(item_summary.get('telephone', ''))

    # 1. Bóc tách địa chỉ chi tiết
    addr_dict = item_summary.get('address', {})
    if isinstance(addr_dict, dict):
        parts = [
            addr_dict.get('streetAddress', ''),
            f"{addr_dict.get('postalCode', '')} {addr_dict.get('addressLocality', '')}".strip(),
            addr_dict.get('addressRegion', ''),
            "Belgique"
        ]
        full_address = ", ".join([p for p in parts if p])
    else:
        full_address = str(addr_dict or "")

    found_email = ""
    found_web = ""
    vat_id = ""

    try:
        page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(random.uniform(0.8, 1.3))

        if "pardon" in page.title().lower() or page.locator("iframe#main-iframe, iframe[src*='incapsula']").count() > 0:
            print("\n\a[!] PHÁT HIỆN THỬ THÁCH XÁC MINH INCAPSULA! Đang chờ 5s để vượt qua...")
            time.sleep(5)

        soup = BeautifulSoup(page.content(), 'html.parser')

        # 2. Bóc tách nút hộp mail (<a href="mailto:...">)
        mail_el = soup.find_all('a', href=re.compile(r'^mailto:', re.I))
        for a in mail_el:
            m_href = a.get('href', '')
            m_match = re.search(r'mailto:\s*([^?&#\s]+)', m_href)
            if m_match:
                c_em = clean_email(m_match.group(1))
                if c_em:
                    found_email = c_em
                    break

        # 3. Phân tích JSON-LD LocalBusiness trên trang chi tiết
        for s in soup.find_all('script', type='application/ld+json'):
            try:
                d = json.loads(s.string or s.text)
                if isinstance(d, dict) and d.get('@type') == 'LocalBusiness':
                    if not found_email and d.get('email'):
                        c_em = clean_email(d.get('email'))
                        if c_em:
                            found_email = c_em
                    if d.get('url'):
                        raw_u = d.get('url').strip()
                        if not any(ag in raw_u.lower() for ag in AGGREGATOR_DOMAINS):
                            found_web = raw_u
                    if d.get('telephone') and not phone:
                        phone = clean_phone(d.get('telephone'))
                    if d.get('vatID'):
                        vat_id = d.get('vatID').strip()
                    if not full_address and d.get('address'):
                        ad = d['address']
                        if isinstance(ad, dict):
                            parts = [ad.get('streetAddress', ''), f"{ad.get('postalCode', '')} {ad.get('addressLocality', '')}".strip(), 'Belgique']
                            full_address = ", ".join([p for p in parts if p])
            except Exception:
                pass

        # 4. Tìm thêm SĐT phụ nếu còn thiếu
        if not phone:
            tel_el = soup.find_all('a', href=re.compile(r'^tel:', re.I))
            for t in tel_el:
                clean_t = clean_phone(t.get_text().strip())
                if clean_t:
                    phone = clean_t
                    break

        # 5. Tìm website từ thẻ link ngoài nếu JSON-LD chưa có
        if not found_web:
            for a in soup.find_all('a', href=re.compile(r'^https?://')):
                h = a.get('href', '')
                if not any(ag in h.lower() for ag in AGGREGATOR_DOMAINS):
                    found_web = h
                    break
    except Exception as e:
        print(f"    [!] Chú ý tải thẻ {detail_url}: {e}")

    # 6. Quét sâu website chính thức nếu chưa có email
    if not found_email and found_web:
        found_email = crawl_company_website(found_web)

    return {
        'company': comp_name,
        'phone': phone,
        'email': found_email,
        'website': found_web or detail_url,
        'address': full_address,
        'vat': vat_id,
        'detail_url': detail_url
    }

def extract_items_from_listing(page, list_url):
    """Trích xuất 20 doanh nghiệp từ trang danh sách bằng Playwright Stealth"""
    items = []
    seen_urls = set()
    try:
        page.goto(list_url, timeout=40000, wait_until="domcontentloaded")
        
        # Đợi Imperva Reese84 xác minh và danh sách thẻ doanh nghiệp render trên DOM
        try:
            page.wait_for_selector('a[href*="/entreprise/"]', state="attached", timeout=20000)
        except Exception:
            pass
            
        time.sleep(1.0)

        # Chấp nhận cookie nếu có
        try:
            cookie_btn = page.locator("button#onetrust-accept-btn-handler, button:has-text('Accepter tout'), button:has-text('Tout accepter')")
            if cookie_btn.count() > 0 and cookie_btn.first.is_visible():
                cookie_btn.first.click()
                time.sleep(0.5)
        except Exception:
            pass

        soup = BeautifulSoup(page.content(), 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'^/entreprise/[^/]+/[^/]+/[^/]+/')):
            href = a.get('href', '').strip()
            if href and href not in seen_urls:
                seen_urls.add(href)
                name = a.get('aria-label', '').strip()
                if not name:
                    parent_card = a.find_parent('div', class_=lambda c: c and 'border' in c)
                    if parent_card:
                        name_span = parent_card.find('span', class_=lambda c: c and 'font-semibold' in c)
                        if name_span:
                            name = name_span.get_text().strip()
                if not name:
                    name = a.get_text().strip()

                full_u = f"https://www.pagesdor.be{href}"
                items.append({
                    'name': name or "Entreprise",
                    'url': full_u,
                    'telephone': '',
                    'address': ''
                })
    except Exception as e:
        print(f"[!] Lỗi tải danh sách {list_url}: {e}")

    return items

def save_all_destinations(all_records):
    """Lưu dữ liệu tăng dần, tự động phân loại đẩy 100% email lên đầu dòng 1..N"""
    if not all_records:
        return 0

    valid_records = [r for r in all_records if not is_blacklisted(r.get('company'))]

    # Phân loại records có email và không có email
    has_email = []
    no_email = []
    seen_emails = set()

    for r in valid_records:
        em = clean_email(r.get('email', ''))
        row_dict = {
            "No.": "",
            "Công ty": r.get('company', ''),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": clean_phone(r.get('phone', '')),
            "Liên Hệ": r.get('website', ''),
            "Email": em,
            "Liên Hệ mail": f"mailto:{em}" if em else "",
            "Địa chỉ": r.get('address', ''),
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi" if em else "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": "Entrepreneurs - Bâtiments résidentiels (Thầu xây dựng)"
        }

        if em:
            if em not in seen_emails:
                seen_emails.add(em)
                has_email.append(row_dict)
        else:
            no_email.append(row_dict)

    # Đẩy 100% dòng có email lên đầu (dòng 1..N)
    master_rows = has_email + no_email
    for idx, r in enumerate(master_rows, 1):
        r["No."] = idx

    ready_rows = [dict(r) for r in has_email]
    for idx, r in enumerate(ready_rows, 1):
        r["No."] = idx

    df_master = pd.DataFrame(master_rows, columns=COLDMAIL_COLUMNS)
    df_ready = pd.DataFrame(ready_rows, columns=COLDMAIL_COLUMNS)

    def safe_export(df, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig")
        except PermissionError:
            tmp = path.with_name(f"{path.stem}_updated{path.suffix}")
            df.to_csv(tmp, index=False, encoding="utf-8-sig")

    # Xuất các file chính chuẩn 17 ký tự (Rule 10)
    safe_export(df_master, RAW_CSV)
    safe_export(df_master, COLDMAIL_CSV)
    safe_export(df_ready, READY_CSV)

    # Đồng bộ sang csdl_mlt và archive/be_belgium
    for extra_dir in [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]:
        safe_export(df_master, extra_dir / COLDMAIL_CSV.name)
        safe_export(df_ready, extra_dir / READY_CSV.name)

    return len(ready_rows)

def run_scraper(start_page=1, max_pages=None, headless=False):
    print("=" * 80)
    print("🇧🇪  HỆ THỐNG CÀO DỮ LIỆU NHÀ THẦU XÂY DỰNG BỈ (PAGESDOR.BE - PLAYWRIGHT STEALTH)")
    print(f"    - URL Nguồn   : https://www.pagesdor.be/entreprises/entrepreneurs+-+b%C3%A2timents+r%C3%A9sidentiels/")
    print(f"    - Trang bắt đầu: Trang {start_page}")
    print(f"    - Giới hạn trang: {'Tất cả các trang' if not max_pages else f'{max_pages} trang'}")
    print(f"    - Chế độ xem  : {'Ẩn (headless)' if headless else 'Trực quan (headless=False - Rule 4)'}")
    print(f"    - Checkpoint   : {CACHE_FILE.name}")
    print("=" * 80)

    # Nạp cache checkpoint
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp cache checkpoint: {len(cache):,} cơ sở đã lưu.")
        except Exception:
            pass

    all_records = list(cache.values())
    initial_email_count = sum(1 for r in all_records if r.get('email'))
    print(f"[*] Số cơ sở đã có email trong cache: {initial_email_count:,}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        stealth_sync(page)

        current_page = start_page
        pages_processed = 0

        while True:
            if max_pages and pages_processed >= max_pages:
                print(f"\n[*] Đã đạt giới hạn {max_pages} trang theo yêu cầu.")
                break

            list_url = f"https://www.pagesdor.be/entreprises/entrepreneurs+-+b%C3%A2timents+r%C3%A9sidentiels/{page}/".replace("{page}", str(current_page)) if current_page > 1 else "https://www.pagesdor.be/entreprises/entrepreneurs+-+b%C3%A2timents+r%C3%A9sidentiels/"
            print(f"\n--- [Trang {current_page:04d}] Đang duyệt danh sách: {list_url} ---", flush=True)

            items = extract_items_from_listing(page, list_url)
            if not items:
                print(f"[*] Không tìm thấy doanh nghiệp nào trên trang {current_page}. Đã duyệt hết danh mục!")
                break

            print(f"[*] Tìm thấy {len(items)} cơ sở trên trang {current_page}. Đang mở thẻ chi tiết lấy email...", flush=True)

            page_new_emails = 0
            for idx, item in enumerate(items, 1):
                comp_name = item.get('name', '').strip()
                detail_url = item.get('url') or ""

                if not detail_url:
                    continue

                # Kiểm tra cache
                if detail_url in cache:
                    cached_rec = cache[detail_url]
                    log_em = f"✨ {cached_rec.get('email')}" if cached_rec.get('email') else "Không có mail"
                    print(f"  [{idx:02d}/{len(items):02d}] {comp_name[:25]:<25} | (Cached) | {log_em:<30} | Tel: {cached_rec.get('phone')}", flush=True)
                    continue

                # Bóc tách thẻ chi tiết bằng Playwright Stealth
                res = parse_detail_page(page, detail_url, item)
                if not res:
                    continue

                cache[detail_url] = res
                all_records.append(res)

                if res.get('email'):
                    page_new_emails += 1
                    log_em = f"✨ {res.get('email')}"
                else:
                    log_em = "Không có mail"

                log_web = f"Web: {res.get('website', '')[:25]}" if res.get('website') else "Web: -"
                print(f"  [{idx:02d}/{len(items):02d}] {comp_name[:25]:<25} | Tel: {res.get('phone', ''):<15} | {log_em:<30} | {log_web}", flush=True)

                # Giãn cách tự nhiên
                time.sleep(random.uniform(0.8, 1.4))

            # Checkpoint lưu tăng dần sau mỗi trang
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            ready_count = save_all_destinations(all_records)
            print(f"  >>> [CHECKPOINT TRANG {current_page}] Đã lưu {len(all_records):,} cơ sở | Hiện có {ready_count:,} EMAIL B2B trên dòng 1..N.", flush=True)

            pages_processed += 1
            current_page += 1
            time.sleep(1.0)

        browser.close()

    final_ready = save_all_destinations(all_records)
    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CHIẾN DỊCH CÀO NHÀ THẦU XÂY DỰNG BỈ!")
    print(f"   - Tổng số cơ sở đã cào              : {len(all_records):,}")
    print(f"   - TỔNG SỐ EMAIL B2B XÁC MINH SẴN SÀNG: {final_ready:,}")
    print(f"   - Tệp Cold Mail 20 cột chuẩn       : {COLDMAIL_CSV.name}")
    print(f"   - Tệp chỉ doanh nghiệp có Email     : {READY_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Pagesdor.be NHÀ THẦU XÂY DỰNG")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu cào (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa cần cào (để trống = cào tất cả)")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt (mặc định: False)")
    args = parser.parse_args()

    run_scraper(start_page=args.start_page, max_pages=args.max_pages, headless=args.headless)
