# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for SK_UDZC_UPSV_2COL.csv (Slovakia SZU Employment Agencies):
1. Tra cuu Google Maps (hl=sk, headless=False) bang Ten Cong Ty + ", Slovakia" (KHONG truyen dia chi vao query tim kiem).
2. Khi Google Maps tra ve ket qua, boc tach dia chi tren Maps panel de DOI CHIEU (cross-check):
   - So khop ten nghiem ngat (Exact match, Delimiter match, Bracket match, loai bo legal forms).
   - Doi chieu dia chi: Ma buu chinh (5 chu so), Ten thanh pho/quan, Ten duong pho de dam bao dung chi nhanh/tru so.
3. Boc tach So dien thoai (luon co dau nhay don ' o dau), Website chinh thuc, Dia chi.
4. Quet website tim email B2B da tang:
   - mailto:, regex, Cloudflare data-cfemail, Obfuscated email.
   - Quet subpages lien he theo do uu tien (/kontakt, /kontakty, /o-nas, /kariera, /contact...).
   - Heuristic scoring b2b: uu tien email lien he B2B chinh thuc (praca@, kariera@, hr@, vedenie@, info@, kontakt@...).
5. Luu tang dan (Incremental Auto-Save) sau moi 5 cong ty va Checkpoint JSON (Resume 100%).
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

# UTF-8 encoding for Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_udzc.json")

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'spolocnost s rucenim obmedzenym', 'spoločnosť s ručením obmedzeným',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'neziskova organizacia', 'nezisková organizácia', 'n.o.', 'n. o.',
    'obcianske zdruzenie', 'občianske združenie', 'o.z.', 'o. z.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'z.z.p.o.', 'organizačná zložka', 'opc'
]

EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.sk', 'maps.google.com', 'apple.com',
    'finstat.sk', 'zrsr.sk', 'orsr.sk', 'profesia.sk', 'kariera.zoznam.sk',
    'azet.sk', 'zlatestranky.sk', 'indexpodnikatela.sk', 'foaf.sk',
    'vzdelavanie.sk', 'portal.gov.sk', 'yellowpages', 'tripadvisor'
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
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example'
}

DOMAIN_EMAIL_CACHE = {}

def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def is_valid_name_match_sk(query_name, candidate_name):
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_raw = re.sub(r'["\'„“”«»]', '', query_name).strip().lower()
    c_raw = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()

    if q_raw == c_raw:
        return True, "EXACT_RAW"

    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw).strip()
    if q_raw == c_nobrackets:
        return True, "BRACKET_MATCH"

    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
    if any(p == q_raw for p in parts):
        return True, "DELIMITER_MATCH"

    q_clean = clean_company_name_sk(query_name)
    c_clean = clean_company_name_sk(candidate_name)
    if q_clean and q_clean == c_clean:
        return True, "EXACT_CORE"

    c_nobrackets_clean = clean_company_name_sk(c_nobrackets)
    if q_clean and q_clean == c_nobrackets_clean:
        return True, "BRACKET_CORE"

    parts_clean = [clean_company_name_sk(p) for p in parts if clean_company_name_sk(p)]
    if q_clean and any(p == q_clean for p in parts_clean):
        return True, "DELIMITER_CORE"

    return False, "NO_MATCH"

def check_address_compatibility(file_address, gmap_address):
    """
    Doi chieu dia chi: khong bat be gat gao ve so nha/duong pho.
    Mien la cong ty o cung thanh pho/khu vuc hoac tai Slovakia (khong bi vuot ra nuoc ngoai).
    """
    if not file_address or not gmap_address:
        return True, "DIA_CHI_CHAP_NHAN"

    fa = file_address.lower()
    ga = gmap_address.lower()

    # Neu dia chi Maps ro rang o nuoc khac (ngoai tru Slovakia) thi loai bo
    other_countries = ['česko', 'czech', 'rakúsko', 'austria', 'deutschland', 'nemecko', 'maďarsko', 'hungary', 'poľsko', 'poland']
    if any(oc in ga for oc in other_countries) and not ('slovensko' in ga or 'slovakia' in ga):
        return False, "LECH_QUOC_GIA"

    # 1. So khop Ma buu chinh hoac khu vuc/thanh pho
    f_zips = re.findall(r'\b\d{5}\b', fa.replace(' ', ''))
    g_zips = re.findall(r'\b\d{5}\b', ga.replace(' ', ''))
    if set(f_zips).intersection(set(g_zips)):
        return True, "TRUNG_MA_BUU_CHINH"

    tokens = re.split(r'[,/\-\s]+', fa)
    meaningful_tokens = [
        t for t in tokens
        if len(t) >= 4 and not t.isdigit() and t not in {'slovensko', 'slovakia', 'ulica', 'trieda', 'namestie'}
    ]
    matched_tokens = [t for t in meaningful_tokens if t in ga]
    if len(matched_tokens) >= 1:
        return True, f"CUNG_KHU_VUC_{matched_tokens[0]}"

    # Neu cung o Slovakia thi van chap nhan (vi cty co the doi tru so hoac mo van phong khac quan)
    if 'slovensko' in ga or 'slovakia' in ga or re.search(r'\b\d{5}\b', ga) or re.search(r'\b\d{3}\s*\d{2}\b', ga):
        return True, "CUNG_NUOC_SLOVAKIA"

    return True, "DIA_CHI_KHA_DUNG"

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
    e = email.strip().lower()
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
    e = email.lower()
    score = 0
    user = e.split('@')[0]
    domain = e.split('@')[1] if '@' in e else ''
    
    if website_domain and (domain == website_domain or domain.endswith('.' + website_domain)):
        score += 50
    # HR / Recruitment: Priority 1 (+50)
    if any(k in user for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    # Management / Executive: Priority 2 (+45)
    elif any(k in user for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # Official / Contact: Priority 3 (+40)
    elif any(k in user for k in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria']):
        score += 40
    elif '.' in user:
        score += 25
    elif domain in {'gmail.com', 'azet.sk', 'centrum.sk', 'zoznam.sk', 'post.sk', 'seznam.cz'}:
        score += 10
    else:
        score += 5
        
    return score

async def fetch_html(url, session):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7'
    }
    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=10, verify=False)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return ""

def extract_emails_from_html(html_text, website_domain=None):
    if not html_text:
        return set()
    found = set()
    
    # Cloudflare
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if is_valid_b2b_email(dec, website_domain):
            found.add(dec)
            
    # mailto
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found.add(clean_m)
            
    # regex
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found.add(clean_m)
            
    # Obfuscated
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(html_text):
            if len(match) == 3:
                rec = f"{match[0]}@{match[1]}.{match[2]}".lower()
            elif len(match) == 2:
                rec = f"{match[0]}@{match[1]}".lower()
            else:
                continue
            if is_valid_b2b_email(rec, website_domain):
                found.add(rec)
                
    return found

async def crawl_website_for_contacts(website_url, session):
    if not website_url or not website_url.startswith(('http://', 'https://')):
        return ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    if domain in DOMAIN_EMAIL_CACHE:
        return DOMAIN_EMAIL_CACHE[domain]

    all_emails = set()

    subpaths = [
        "", "/kontakt", "/kontakty", "/kontakt.html", "/kontakty.html",
        "/o-nas", "/o-nas.html", "/onas", "/kariera", "/praca", "/contact"
    ]

    for sp in subpaths:
        target = urllib.parse.urljoin(website_url, sp)
        html_content = await fetch_html(target, session)
        if not html_content:
            continue
            
        emails = extract_emails_from_html(html_content, domain)
        all_emails.update(emails)
        if any(domain in e for e in all_emails):
            break

    best_email = ""
    if all_emails:
        sorted_emails = sorted(list(all_emails), key=lambda e: score_email_b2b(e, domain), reverse=True)
        best_email = sorted_emails[0]

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

def save_csv_and_sort(rows, fieldnames):
    # Rule 3: Always push companies with Email to the top
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
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    temp = INPUT_CSV + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
    if os.path.exists(INPUT_CSV):
        os.remove(INPUT_CSV)
    os.rename(temp, INPUT_CSV)

async def bypass_google_consent(page):
    try:
        btns = page.locator('button:has-text("Prijať všetko"), button:has-text("I agree"), button:has-text("Accept all"), form:has(button) button:has-text("Prijať")')
        if await btns.count() > 0:
            await btns.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def handle_captcha(page):
    current_url = page.url.lower()
    content = await page.content()
    if "sorry" in current_url or "captcha" in current_url or "unusual traffic" in content.lower():
        print("\a" * 3)
        print("[!] CAPTCHA PHAT HIEN! Vui long giai captcha tren trinh duyet...")
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha da giai xong! Tiep tuc chay...")
                break

async def extract_details_from_panel(page):
    phone = ""
    website = ""
    address = ""

    try:
        phone_btn = page.locator('button[data-tooltip*="telefón"], button[data-item-id*="phone:tel:"]')
        if await phone_btn.count() > 0:
            raw_phone = await phone_btn.first.inner_text()
            phone = raw_phone.strip()
    except Exception:
        pass

    try:
        web_btn = page.locator('a[data-tooltip*="web"], a[data-item-id="authority"]')
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

async def search_google_maps_for_company(page, company_name, file_address=""):
    # CHUYEN DOI: Chi tim kiem bang Ten cong ty + ", Slovakia" (Khong dua dia chi vao query de tranh bi nham sang dia danh)
    query = f"{company_name}, Slovakia".strip()
    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}?hl=sk"
    
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception:
        return None

    await handle_captcha(page)
    await bypass_google_consent(page)

    current_url = page.url

    # Case 1: Direct place
    if "/maps/place/" in current_url:
        h1 = page.locator('h1.DUwDvf')
        cand_name = (await h1.first.inner_text()).strip() if await h1.count() > 0 else ""
        valid, m_type = is_valid_name_match_sk(company_name, cand_name)
        if valid:
            phone, web, gmap_addr = await extract_details_from_panel(page)
            addr_ok, addr_reason = check_address_compatibility(file_address, gmap_addr)
            if not addr_ok:
                return None
            return {
                "name": cand_name,
                "phone": phone,
                "website": web,
                "address": gmap_addr,
                "match_type": m_type,
                "addr_ok": addr_ok,
                "addr_reason": addr_reason
            }
        return None

    # Case 2: Search results list
    link_selector = 'a.hfpxzc'
    links = page.locator(link_selector)
    count = await links.count()
    if count == 0:
        return None

    best_cand = None

    for i in range(min(count, 4)):
        cand_elem = links.nth(i)
        cand_aria = await cand_elem.get_attribute("aria-label") or ""
        valid, m_type = is_valid_name_match_sk(company_name, cand_aria)
        if valid:
            try:
                await cand_elem.click()
                await page.wait_for_timeout(2500)
                await handle_captcha(page)
                phone, web, gmap_addr = await extract_details_from_panel(page)
                addr_ok, addr_reason = check_address_compatibility(file_address, gmap_addr)
                
                cand_info = {
                    "name": cand_aria,
                    "phone": phone,
                    "website": web,
                    "address": gmap_addr,
                    "match_type": m_type,
                    "addr_ok": addr_ok,
                    "addr_reason": addr_reason
                }
                
                # Neu trung dia chi (city/zip/street), chon ngay
                if addr_ok and addr_reason != "KHONG_CO_DIA_CHI_DE_SO_SANH":
                    return cand_info
                
                if best_cand is None:
                    best_cand = cand_info
            except Exception:
                continue

    return best_cand

async def run_enrichment():
    print("="*70)
    print("BAT DAU LAM GIAU DU LIEU GOOGLE MAPS + EMAIL CHO SK_UDZC_UPSV_2COL.CSV")
    print("QUY CHUAN MOI: TIM KIEM BANG TEN CONG TY, DUNG DIA CHI DE DOI CHIEU")
    print("="*70)

    rows = []
    fieldnames = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)

    print(f"Tong so doanh nghiep trong file: {len(rows)}")

    cache = load_cache()
    print(f"Da nap cache: {len(cache)} doanh nghiep da xu ly thanh cong tu truoc.")

    # Target rows to enrich: companies without Email OR without Phone/Web
    to_enrich = []
    for idx, r in enumerate(rows):
        c_name = r.get('Công ty', '').strip()
        if not c_name:
            continue
        has_email = bool(r.get('Email', '').strip())
        has_phone = bool(r.get('SĐT', '').strip())
        has_web = bool(r.get('Liên Hệ', '').strip())
        if not (has_email and has_phone and has_web):
            to_enrich.append(idx)

    print(f"So luong doanh nghiep can lam giau them: {len(to_enrich)}")

    if HAS_CURL_CFFI:
        session = AsyncSession()
    else:
        session = aiohttp.ClientSession()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--window-size=1280,800"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="sk-SK",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        processed_since_save = 0

        for i, row_idx in enumerate(to_enrich, 1):
            r = rows[row_idx]
            company_name = r.get('Công ty', '').strip()
            file_address = r.get('Địa chỉ', '').strip()

            # Check cache
            if company_name in cache:
                c_data = cache[company_name]
                if c_data.get('phone') and not r.get('SĐT'):
                    p_val = c_data['phone']
                    r['SĐT'] = f"'{p_val}" if not p_val.startswith("'") else p_val
                if c_data.get('website') and not r.get('Liên Hệ'):
                    r['Liên Hệ'] = c_data['website']
                if c_data.get('email') and not r.get('Email'):
                    r['Email'] = c_data['email']
                continue

            print(f"\n[{i}/{len(to_enrich)}] Tim kiem ten: {company_name}")
            print(f"   -> Dia chi file: {file_address}")

            # Check if company already has website
            existing_web = r.get('Liên Hệ', '').strip()
            web_to_crawl = existing_web if existing_web and existing_web.startswith(('http://', 'https://')) else ""

            # If no website or no phone, search Google Maps by NAME ONLY
            res = None
            if not web_to_crawl or not r.get('SĐT'):
                res = await search_google_maps_for_company(page, company_name, file_address)

            found_phone = ""
            found_web = ""
            found_email = ""

            if res:
                print(f"  [GMAP KHOP: {res['match_type']}] {res['name']}")
                print(f"   -> Doi chieu dia chi: {res['addr_reason']} ({res['address']})")
                if res['phone']:
                    found_phone = res['phone']
                    p_val = res['phone']
                    r['SĐT'] = f"'{p_val}" if not p_val.startswith("'") else p_val
                    print(f"    -> SDT: {p_val}")
                if res['website']:
                    found_web = res['website']
                    r['Liên Hệ'] = res['website']
                    print(f"    -> Web: {res['website']}")
                    web_to_crawl = res['website']
            else:
                if not web_to_crawl:
                    print(f"  [!] Khong tim thay tren Google Maps.")

            # Crawl website for Email
            if web_to_crawl and not r.get('Email'):
                print(f"  [WEB] Quet email: {web_to_crawl} ...", end=" ", flush=True)
                email = await crawl_website_for_contacts(web_to_crawl, session)
                if email:
                    found_email = email
                    r['Email'] = email
                    print(f"-> EMAIL B2B: {email}")
                else:
                    print("-> Khong co email")

            # Chi luu vao cache khi tim thay it nhat mot thong tin (phone, web, email) hoac xac nhan da check
            if found_phone or found_web or found_email:
                cache[company_name] = {
                    "phone": found_phone or r.get('SĐT', ''),
                    "website": found_web or r.get('Liên Hệ', ''),
                    "email": found_email or r.get('Email', ''),
                    "timestamp": datetime.now().isoformat()
                }
                save_cache(cache)

            processed_since_save += 1
            if processed_since_save >= 5:
                save_csv_and_sort(rows, fieldnames)
                print(f"  [+] Da tu dong luu tang dan vao CSV.")
                processed_since_save = 0

            await asyncio.sleep(1.5)

        # Final save
        save_csv_and_sort(rows, fieldnames)
        print(f"\n[HOAN TAT] Da hoan thanh lam giau du lieu cho toan bo danh sach!")
        await browser.close()
        await session.close()

if __name__ == '__main__':
    asyncio.run(run_enrichment())
