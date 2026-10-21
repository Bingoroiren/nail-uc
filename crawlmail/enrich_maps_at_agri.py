# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for AT_AGRI_WBIO_0RAW.csv (Austria Agriculture & Bio Farms):
1. Tra cứu Google Maps (hl=de, headless=False) theo Tên Trang trại / Doanh nghiệp Nông nghiệp tại Áo.
2. So khớp tên nghiêm ngặt (Exact match, Delimiter match, Bracket match, loại bỏ legal forms Áo: GmbH, e.U., KG, OG, GesbR...).
3. Kiểm tra tương thích địa chỉ Áo (Mã bưu chính 4 số PLZ, Tên bang/thành phố).
4. Bóc tách Số điện thoại (chuẩn hóa nháy đơn '), Website chính thức.
5. Quét website tìm email B2B đa tầng:
   - mailto:, regex, Cloudflare data-cfemail, Obfuscated email.
   - Quét subpages liên hệ bản địa hóa Áo/Đức theo độ ưu tiên (/kontakt, /impressum, /ueber-uns, /karriere, /jobs...).
   - Heuristic scoring B2B (HR: +50, Lãnh đạo/Chủ trại: +45, Liên hệ chính thức: +40, Domain: +50). Tuyển chọn 1 email tốt nhất.
6. Lưu tăng dần (Incremental Auto-Save) sau mỗi 5 bản ghi và Checkpoint JSON (Resume 100%).
7. Xuất file chuẩn 17 ký tự: AT_AGRI_WBIO_1ENR.csv (Đẩy 100% cơ sở có email lên đầu danh sách).
"""

import sys
import os
import re
import csv
import json
import time
import html
import asyncio
import urllib.parse
from datetime import datetime
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
INPUT_CSV = str(ROOT_DIR / "AT_AGRI_WBIO_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "AT_AGRI_WBIO_1ENR.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_at_agri.json")

# Danh sách hậu tố loại hình doanh nghiệp Áo (Austria Legal Forms)
LEGAL_FORMS_AT = [
    'gesellschaft mit beschränkter haftung', 'gesellschaft mit beschrankter haftung',
    'gmbh & co. kg', 'gmbh & co kg', 'gmbh & co.kg', 'gmbh & co',
    'gesellschaft m.b.h.', 'gesellschaft mbh', 'ges.m.b.h.', 'gesmbh', 'ges. mbh',
    'gmbh', 'g.m.b.h.',
    'aktiengesellschaft', 'ag', 'a.g.',
    'offene gesellschaft', 'og', 'o.g.',
    'kommanditgesellschaft', 'kg', 'k.g.',
    'eingetragenes einzelunternehmen', 'eingetragene unternehmerin', 'e.u.', 'eu',
    'societas europaea', 'se',
    'genossenschaft', 'egen', 'e.gen.',
    'gesbr', 'holding', 'group', 'gruppe'
]

# Danh sách domain rác / directory loại trừ
EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.at', 'maps.google.com', 'apple.com',
    'firmenabc.at', 'wko.at', 'herold.at', 'docfinder.at', 'karriere.at',
    'stepstone.at', 'monster.at', 'willhaben.at', 'gelbeseiten.de',
    'gelbeseiten.at', 'yellowpages', 'tripadvisor', 'bio-austria.at',
    'bioaustria.at', 'ama.at', 'gutesvombauernhof.at', 'bauernhof.at',
    'urlaubambauernhof.at', 'landwirt.com', 'agrarheute.com', 'meinbezirk.at',
    'ots.at', 'sn.at', 'nachrichten.at', 'orf.at', 'kurier.at', 'derstandard.at',
    'cylex.sk', 'cylex-oesterreich.at', 'cylex.at', 'adresarfiriem.sk', 'efirma.sk',
    'cybo.com', 'northdata.com', 'opencorporates.com', 'doveryhodnafirma.eu'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})'),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*(?:@|\[at\]|\(at\))\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', re.IGNORECASE),
]

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

DOMAIN_EMAIL_CACHE = {}


def clean_company_name_at(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_AT, key=len, reverse=True):
        pattern = rf'(?:^|[\s,;]){re.escape(lf)}(?:$|[\s,;])'
        n = re.sub(pattern, ' ', n)
    n = re.sub(r'\b(gmbh|e\s*u|k\s*g|o\s*g|a\s*g)\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def is_valid_name_match_at(query_name, candidate_name):
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_raw = re.sub(r'["\'„“”«»]', '', query_name).strip().lower()
    c_raw = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()

    if q_raw == c_raw:
        return True, "EXACT_FULL"

    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw).strip()
    if q_raw == c_nobrackets:
        return True, "BRACKET_MATCH"

    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
    if any(p == q_raw for p in parts):
        return True, "DELIMITER_MATCH"

    q_clean = clean_company_name_at(query_name)
    c_clean = clean_company_name_at(candidate_name)

    if q_clean and c_clean:
        if q_clean == c_clean:
            return True, "CLEAN_EXACT"

        c_clean_parts = [clean_company_name_at(p) for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
        if any(p == q_clean for p in c_clean_parts if p):
            return True, "CLEAN_DELIMITER"

        q_words = set(q_clean.split())
        c_words = set(c_clean.split())
        if q_words and q_words.issubset(c_words) and len(q_words) >= 2:
            return True, "CLEAN_SUBSET"

    return False, "NO_MATCH"


def check_address_compatibility_at(file_address, gmap_address):
    if not gmap_address:
        return True, "NO_GMAP_ADDRESS"

    fa = file_address.lower()
    ga = gmap_address.lower()

    foreign_keywords = ['deutschland', 'germany', 'schweiz', 'switzerland', 'italy', 'tschechien', 'ungarn', 'slowakei']
    if any(k in ga for k in foreign_keywords) and not any(k in fa for k in foreign_keywords):
        return False, "LECH_QUOC_GIA"

    # Austrian Postal code match (4 digits)
    f_zips = re.findall(r'\b\d{4}\b', fa)
    g_zips = re.findall(r'\b\d{4}\b', ga)
    if set(f_zips).intersection(set(g_zips)):
        return True, "TRUNG_MA_BUU_CHINH"

    # Bundesland match
    bundeslaender = ['burgenland', 'kärnten', 'kaernten', 'niederösterreich', 'niederoesterreich',
                     'oberösterreich', 'oberoesterreich', 'salzburg', 'steiermark', 'tirol', 'vorarlberg', 'wien', 'vienna']
    matched_regions = [b for b in bundeslaender if b in fa and b in ga]
    if matched_regions:
        return True, f"CUNG_BANG_{matched_regions[0]}"

    tokens = re.split(r'[,/\-\s]+', fa)
    meaningful_tokens = [
        t for t in tokens
        if len(t) >= 4 and not t.isdigit() and t not in {'österreich', 'oesterreich', 'austria', 'straße', 'strasse', 'gasse', 'weg'}
    ]
    matched_tokens = [t for t in meaningful_tokens if t in ga]
    if len(matched_tokens) >= 1:
        return True, f"CUNG_KHU_VUC_{matched_tokens[0]}"

    if 'österreich' in ga or 'austria' in ga or re.search(r'\b\d{4}\b', ga):
        return True, "CUNG_NUOC_AO"

    return True, "DIA_CHI_KHA_DUNG"


def clean_phone_at(raw_phone):
    if not raw_phone:
        return ""
    p = str(raw_phone).strip()
    p = re.sub(r'[\ue000-\uf8ff]', '', p)
    p = re.sub(r'[\r\n]+', ' ', p).strip()
    p = p.lstrip("'").strip()
    p = re.sub(r'[^\d+()\s-]', '', p).strip()
    p = re.sub(r'\s+', ' ', p).strip()
    if p:
        p = f"'{p}"
    return p


def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email.strip().lower()
    except Exception:
        return ""


def is_valid_b2b_email(email, website_domain=None):
    if not email or not isinstance(email, str):
        return False
    e = email.strip().lower().replace('%20', '')
    if not EMAIL_REGEX.match(e):
        return False
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return False

    parts = e.split('@')
    if len(parts) != 2:
        return False
    user, domain = parts[0], parts[1]

    if domain in JUNK_EMAIL_DOMAINS:
        return False
    if any(domain.endswith('.' + j) for j in JUNK_EMAIL_DOMAINS):
        return False
    if user in SYSTEM_USERNAMES:
        return False
    return True


def score_email_b2b(email, website_domain=None):
    e = email.lower().replace('%20', '')
    score = 0
    parts = e.split('@')
    if len(parts) != 2:
        return 0
    user, domain = parts[0], parts[1]

    if website_domain and (domain == website_domain or domain.endswith('.' + website_domain)):
        score += 50

    # Ưu tiên Tuyển dụng / Nhân sự
    if any(k in user for k in ['karriere', 'jobs', 'bewerbung', 'personal', 'recruiting', 'career', 'hr']):
        score += 50
    # Ưu tiên Lãnh đạo / Chủ trại
    elif any(k in user for k in ['geschaeftsfuehrung', 'inhaber', 'chef', 'leiter', 'direktion', 'management', 'vorstand']):
        score += 45
    # Cổng liên hệ chính thức
    elif any(k in user for k in ['office', 'info', 'kontakt', 'post', 'empfang', 'service', 'zentrale', 'mail', 'anfrage']):
        score += 40
    elif '.' in user:
        score += 25
    elif domain in {'gmx.at', 'aon.at', 'sbg.at', 'gmail.com', 'a1.net', 'hotmail.com'}:
        score += 15
    else:
        score += 5

    return score


async def fetch_html(url, session):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }
    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=12)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return ""


def extract_emails_from_html(html_text, website_domain=None):
    if not html_text:
        return set()

    found = set()
    soup = BeautifulSoup(html_text, 'html.parser')

    # 1. Cloudflare protected
    for cf in soup.find_all(attrs={"data-cfemail": True}):
        dec = decode_cloudflare_email(cf["data-cfemail"])
        if is_valid_b2b_email(dec, website_domain):
            found.add(dec)

    # 2. mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().startswith('mailto:'):
            clean_mail = href[7:].split('?')[0].strip().replace('%20', '')
            clean_mail = urllib.parse.unquote(clean_mail)
            if is_valid_b2b_email(clean_mail, website_domain):
                found.add(clean_mail.lower())

    # 3. Regex on body
    text_content = soup.get_text(separator=' ')
    for match in EMAIL_REGEX.findall(text_content):
        m = match.strip().replace('%20', '').lower()
        if is_valid_b2b_email(m, website_domain):
            found.add(m)

    # 4. Obfuscated emails
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(text_content):
            if len(match) == 3:
                rec = f"{match[0]}@{match[1]}.{match[2]}".replace(' ', '').lower()
            elif len(match) == 2:
                rec = f"{match[0]}@{match[1]}".replace(' ', '').lower()
            else:
                continue
            if is_valid_b2b_email(rec, website_domain):
                found.add(rec)

    return found


async def crawl_website_for_contacts(website_url, session):
    if not website_url:
        return ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')

    if domain in DOMAIN_EMAIL_CACHE:
        return DOMAIN_EMAIL_CACHE[domain]

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    all_found_emails = set()

    # 1. Fetch homepage
    home_html = await fetch_html(base_url, session)
    if home_html:
        emails = extract_emails_from_html(home_html, domain)
        all_found_emails.update(emails)

    # 2. Discover subpages from DOM menu
    subpage_urls = []
    if home_html:
        soup = BeautifulSoup(home_html, 'html.parser')
        contact_keywords = ['kontakt', 'contact', 'impressum', 'ueber-uns', 'uber-uns', 'ueberuns', 'about', 'team', 'karriere', 'jobs', 'anfrage']
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            anchor_text = a.get_text(strip=True).lower()
            link_lower = href.lower()

            if any(k in link_lower or k in anchor_text for k in contact_keywords):
                full_url = urllib.parse.urljoin(base_url, href)
                parsed_sub = urllib.parse.urlparse(full_url)
                if parsed_sub.netloc.lower().replace('www.', '') == domain:
                    clean_target = f"{parsed_sub.scheme}://{parsed_sub.netloc}{parsed_sub.path}"
                    if clean_target not in subpage_urls and clean_target != base_url:
                        subpage_urls.append(clean_target)

    # Priority 2: Fallback subpaths
    fallback_paths = [
        '/kontakt', '/kontakt.html', '/kontakt.php',
        '/impressum', '/impressum.html', '/impressum.php',
        '/ueber-uns', '/ueber-uns.html', '/karriere'
    ]
    for fp in fallback_paths:
        candidate = f"{base_url}{fp}"
        if candidate not in subpage_urls:
            subpage_urls.append(candidate)

    # Fetch top 6 subpages
    for s_url in subpage_urls[:6]:
        sub_html = await fetch_html(s_url, session)
        if sub_html:
            emails = extract_emails_from_html(sub_html, domain)
            all_found_emails.update(emails)
            if any(score_email_b2b(e, domain) >= 90 for e in emails):
                break

    best_email = ""
    if all_found_emails:
        scored = [(e, score_email_b2b(e, domain)) for e in all_found_emails]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_email = scored[0][0]

    DOMAIN_EMAIL_CACHE[domain] = best_email
    return best_email


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_output_csv(rows, fieldnames):
    with_email = []
    without_email = []
    for r in rows:
        em = str(r.get('Email', '')).strip()
        if em and em != 'nan':
            with_email.append(r)
        else:
            without_email.append(r)

    final_rows = with_email + without_email
    for idx, r in enumerate(final_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan':
            r['SĐT'] = clean_phone_at(p)

    temp = OUTPUT_CSV + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
    if os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)
    os.rename(temp, OUTPUT_CSV)


async def bypass_google_consent(page):
    try:
        btns = page.locator('button:has-text("Alle akzeptieren"), button:has-text("Ich stimme zu"), button:has-text("Accept all"), form:has(button) button:has-text("Zustimmen")')
        if await btns.count() > 0:
            await btns.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass


async def extract_details_from_panel(page):
    phone = ""
    website = ""
    address = ""

    try:
        phone_btn = page.locator('button[data-tooltip*="Telefon"], button[data-tooltip*="phone"], button[data-item-id*="phone:tel:"]')
        if await phone_btn.count() > 0:
            raw_phone = await phone_btn.first.inner_text()
            phone = clean_phone_at(raw_phone)
    except Exception:
        pass

    try:
        web_btn = page.locator('a[data-tooltip*="Website"], a[data-tooltip*="web"], a[data-item-id="authority"]')
        if await web_btn.count() > 0:
            href = await web_btn.first.get_attribute("href") or ""
            if href:
                parsed = urllib.parse.urlparse(href)
                domain = parsed.netloc.lower().replace('www.', '')
                if not any(d in domain for d in EXCLUDED_DOMAINS):
                    website = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass

    try:
        addr_btn = page.locator('button[data-item-id="address"]')
        if await addr_btn.count() > 0:
            address = (await addr_btn.first.inner_text()).strip()
    except Exception:
        pass

    return phone, website, address


async def search_google_maps_for_company(page, company_name, file_address):
    # Trích xuất mã bưu chính hoặc địa phương để truy vấn chính xác
    plz = ""
    m = re.search(r'\b\d{4}\b', file_address)
    if m:
        plz = m.group(0)

    query = f"{company_name} {plz} Österreich".strip()
    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=de"

    try:
        await page.goto(search_url, timeout=30000)
        await page.wait_for_timeout(2000)
        await bypass_google_consent(page)
    except Exception:
        return None

    # Case A: Direct Detail Card
    try:
        header = page.locator('h1.DUwDvf')
        if await header.count() > 0:
            gmap_name = (await header.first.inner_text()).strip()
            valid, m_type = is_valid_name_match_at(company_name, gmap_name)
            if valid:
                phone, web, gmap_addr = await extract_details_from_panel(page)
                addr_ok, addr_reason = check_address_compatibility_at(file_address, gmap_addr)
                if addr_ok:
                    return {
                        "name": gmap_name,
                        "phone": phone,
                        "website": web,
                        "gmap_address": gmap_addr,
                        "match_type": m_type,
                        "addr_status": addr_reason
                    }
    except Exception:
        pass

    # Case B: Result list
    try:
        items = page.locator('div[role="feed"] div[role="article"]')
        count = await items.count()
        for i in range(min(count, 4)):
            item = items.nth(i)
            aria = await item.get_attribute("aria-label")
            if aria:
                valid, m_type = is_valid_name_match_at(company_name, aria.strip())
                if valid:
                    await item.click()
                    await page.wait_for_timeout(2500)
                    phone, web, gmap_addr = await extract_details_from_panel(page)
                    addr_ok, addr_reason = check_address_compatibility_at(file_address, gmap_addr)
                    if addr_ok:
                        return {
                            "name": aria.strip(),
                            "phone": phone,
                            "website": web,
                            "gmap_address": gmap_addr,
                            "match_type": m_type,
                            "addr_status": addr_reason
                        }
    except Exception:
        pass

    return None


async def run_enrichment():
    print("=====================================================================")
    print("🚀 BẮT ĐẦU LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP ÁO (AT_AGRI_WBIO_0RAW -> 1ENR)")
    print("=====================================================================")

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp đầu vào: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Tổng số cơ sở nông nghiệp: {len(rows):,} cơ sở")

    cache = load_cache()
    cached_count = len(cache)
    print(f"[*] Đã tải Cache: {cached_count:,} cơ sở đã xử lý trước đó.")

    # Phân loại cơ sở cần xử lý tiếp
    output_rows = []
    need_process = []

    for r in rows:
        cname = str(r.get('Công ty', '')).strip()
        f_addr = str(r.get('Địa chỉ', '')).strip()
        plz = ""
        m = re.search(r'\b\d{4}\b', f_addr)
        if m: plz = m.group(0)
        cache_key = f"{clean_company_name_at(cname)}_{plz}".strip('_')

        # Nếu đã có email từ file gốc -> không cần cào lại
        if r.get('Email'):
            if cache_key in cache:
                c_data = cache[cache_key]
                if c_data.get('phone') and not r.get('SĐT'): r['SĐT'] = c_data['phone']
                if c_data.get('website') and not r.get('Liên Hệ'): r['Liên Hệ'] = c_data['website']
            output_rows.append(r)
        else:
            if cache_key in cache:
                c_data = cache[cache_key]
                if c_data.get('phone') and not r.get('SĐT'): r['SĐT'] = c_data['phone']
                if c_data.get('website') and not r.get('Liên Hệ'): r['Liên Hệ'] = c_data['website']
                if c_data.get('email') and not r.get('Email'): r['Email'] = c_data['email']
                output_rows.append(r)
            else:
                need_process.append(r)

    print(f"[*] Đã có Email / Cache sẵn sàng: {len(output_rows):,} cơ sở.")
    print(f"[*] Cần tra cứu tiếp Google Maps: {len(need_process):,} cơ sở.\n")

    if not need_process:
        print("[V] Toàn bộ cơ sở đã được làm giàu từ Cache! Đang ghi file xuất...")
        save_output_csv(output_rows, fieldnames)
        print(f"[V] Hoàn tất: {OUTPUT_CSV}")
        return

    session = AsyncSession() if HAS_CURL_CFFI else aiohttp.ClientSession()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--window-size=1280,850"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 850},
            locale="de-AT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("[*] Đang khởi động Google Maps...")
        try:
            await page.goto("https://www.google.com/maps?hl=de", timeout=30000)
            await page.wait_for_timeout(2000)
            await bypass_google_consent(page)
        except Exception:
            pass

        processed_batch = 0

        for idx, r in enumerate(need_process, 1):
            cname = str(r.get('Công ty', '')).strip()
            f_addr = str(r.get('Địa chỉ', '')).strip()
            plz = ""
            m = re.search(r'\b\d{4}\b', f_addr)
            if m: plz = m.group(0)
            cache_key = f"{clean_company_name_at(cname)}_{plz}".strip('_')

            print(f"[{idx}/{len(need_process)}] Tra cứu: {cname} | Địa chỉ: {f_addr[:35]}...")

            gmap_res = await search_google_maps_for_company(page, cname, f_addr)

            phone = ""
            website = ""
            email = ""

            if gmap_res:
                phone = gmap_res.get('phone', '')
                website = gmap_res.get('website', '')
                print(f"    -> [Maps Khớp ({gmap_res['match_type']})] SĐT: {phone or 'N/A'} | Web: {website or 'N/A'}")
            else:
                print(f"    -> [Maps Không tìm thấy/Không khớp]")

            # Quét website tìm email nếu có website
            if website:
                email = await crawl_website_for_contacts(website, session)
                if email:
                    print(f"    -> [Email B2B Tuyển Chọn] {email}")
                else:
                    print(f"    -> [Website không có Email B2B]")

            if phone:
                phone = clean_phone_at(phone)

            if phone and not r.get('SĐT'): r['SĐT'] = phone
            if website and not r.get('Liên Hệ'): r['Liên Hệ'] = website
            if email and not r.get('Email'): r['Email'] = email

            output_rows.append(r)

            # Cập nhật cache
            cache[cache_key] = {
                "name": cname,
                "phone": phone,
                "website": website,
                "email": email,
                "updated_at": datetime.now().isoformat()
            }
            save_cache(cache)

            processed_batch += 1
            if processed_batch % 5 == 0:
                save_output_csv(output_rows, fieldnames)
                print(f"    [+] Auto-save checkpoint: Đã lưu {len(output_rows)} cơ sở vào {OUTPUT_CSV}")

            await asyncio.sleep(1.2)

        # Lưu lần cuối
        save_output_csv(output_rows, fieldnames)
        await browser.close()

    if not HAS_CURL_CFFI:
        await session.close()

    print("\n=====================================================================")
    print(f"🎉 HOÀN TẤT LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP ÁO!")
    print(f"📁 Tệp kết quả: {OUTPUT_CSV}")
    print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(run_enrichment())
