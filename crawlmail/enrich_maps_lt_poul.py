# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN POULTRY & MEAT ENTERPRISES (LT_POUL_WEBD)
Built strictly adhering to:
- Skill enrich-maps & Skill data-standards (Strict Name Matching, headless=False, incremental save)
- Skill crawl-mail (Priority 10 DOM menu, Cloudflare XOR decode, B2B email scoring)
- 100% Aggregator & Junk Email Filtering (Blacklisting all Lithuanian directory/yellowpage portals)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY (Zero pandas dependency)
- Rule 2: Phone numbers with leading single quote (')
- Rule 3: 1 Best B2B email only, 100% emails sorted to the top
- Rule 10: 17-character fixed filename convention (LT_POUL_WEBD_1ENR.csv / LT_POUL_WEBD_2COL.csv)
- Rule 12: Permanent Blacklist Hard Exclusion (Scandi Standard, Biliarta, Daigre)
"""

import asyncio
import os
import sys
import re
import ssl
import csv
import json
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Reconfigure stdout for UTF-8 in Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT_DIR / "LT_POUL_WEBD_1ENR.csv"
CSV_CSDL_PATH = ROOT_DIR / "csdl_mlt" / "LT_POUL_WEBD_1ENR.csv"
COLDMAIL_CSV_PATH = ROOT_DIR / "LT_POUL_WEBD_2COL.csv"
COLDMAIL_CSDL_PATH = ROOT_DIR / "csdl_mlt" / "LT_POUL_WEBD_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_poul.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "lt_poul_maps_profile"

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Aggregator & Directory Domains Blacklist (Lithuania & Global)
BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'statyba.lt', 'info.lt', 'visalietuva.lt', 'imones.lt', 'rekvizitai.vz.lt', 'rekvizitai.lt',
    'b2lithuania.com', 'cvbankas.lt', 'cvonline.lt', 'wikipedia.org', 'delfi.lt', '15min.lt', 'lrt.lt',
    'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'scoris.lt', 'infoin.lt', 'cr.lt',
    'creditinfo.lt', 'verslas.lt', 'madeinvilnius.lt', 'lrytas.lt', 'alfa.lt', 'tv3.lt',
    'registrucentras.lt', 'vmi.lt', 'sodra.lt', '1551.lt', 'tax.lt', 'buhalteredaiva.lt',
    'geltoni.lt', 'fsaskaita.lt', 'jars.lt', 'spec.lt', 'saskaitos.lt', 'balticlei.lt',
    'infoplius.lt', 'business-baltics.com', 'imoniukatalogai.lt', '1588.lt', 'fermos.lt',
    'imoniugidas.lt', 'imoniubaze.lt', 'versloakcija.lt', 'expo.lt', 'ltkatalogas.lt',
    'lamaistas.lt', 'meniu.lt', 'ringo.lt', 'gargzdai.info', 'mokesciu-sufleris.lt',
    'cvmarket.lt', 'rekv.lt', 'proton.me', 'lovejob.lt', '014on.com', 'branch.io',
    'cookiebot.com', 'cloudflare.com', 'apple.com'
]

# Rule 12: Permanent Blacklist
EXCLUDED_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in EXCLUDED_COMPANIES)

JUNK_EMAIL_DOMAINS = set(BLACKLIST_DOMAINS) | {
    'example.com', 'domain.com', 'yourdomain.com', 'yourcompany.com',
    'company.com', 'website.com', 'site.com', 'pavyzdys.lt', 'imone.lt', 'email.com', 'mail.com',
    '014on.com', 'branch.io', 'saulesspektras.lt'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'hostmaster', 'postmaster', 'root', 'dataprivacy', 'datenschutz'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname', 'username', 'user', 'name',
    'sample', 'demo', 'test', 'testing', 'placeholder', 'someone', 'nobody',
    'john.doe', 'johndoe', 'jane.doe', 'janedoe', 'jusu', 'tavo', 'vardas', 'pavarde'
}

LT_PRIORITY_KEYWORDS = [
    'kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai',
    'susisiekite', 'administracija', 'prekyba', 'pardavimai',
    'contact', 'contacts', 'about', 'career', 'careers', 'jobs', 'team'
]

LT_GUESS_SUBPATHS = [
    '/kontaktai', '/kontaktai/', '/kontaktai.html',
    '/apie-mus', '/apie-mus/',
    '/karjera', '/karjera/', '/darbas',
    '/contact', '/contacts', '/about', '/about-us'
]

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]


def decode_cf(cf_hex):
    """Decode Cloudflare XOR data-cfemail."""
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def clean_phone_lt(phone_str):
    """Normalize Lithuanian phone number with leading single quote."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = phone_str.strip().lstrip("'")
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('370'):
        return f"'+{digits}"
    elif digits.startswith('8') and len(digits) >= 8:
        return f"'+370{digits[1:]}"
    elif digits.startswith('0'):
        return f"'+370{digits[1:]}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"


def clean_extracted_email(email_str):
    """Clean common artifacts from email text (e.g. trailing phone labels, %20)."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = email_str.replace('%20', '').strip().lower()
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def normalize_string_lt(s):
    """Khử dấu Unicode NFKD bản địa đa quốc gia đưa về ASCII thuần."""
    if not s:
        return ""
    n = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in n if not unicodedata.combining(c)).lower()


def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching per skill enrich-maps taking into account Lithuanian legal forms."""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q_norm = normalize_string_lt(query_name)
    c_norm = normalize_string_lt(candidate_name)

    # Loại bỏ ngoặc đơn chú thích tiếng Anh/dịch thuật
    c_norm = re.sub(r'\(.*?\)|\[.*?\]', '', c_norm).strip()
    
    # Strip legal forms
    legal_forms = [
        'uab', 'mb', 'ab', 'ii', 'vsi', 'zub', 'kb', 'tub', 'kub',
        'uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove',
        'zemes ukio bendrove', 'kooperatyvas', 'firmine parduotuve', 'skerdykla',
        'cechas', 'sandelis', 'parduotuve', 'filialas', 'ukininko ukis', 'ukis',
        'asociacija', 'bendrija', 'viesoji istaiga'
    ]
    for lf in legal_forms:
        q_norm = re.sub(rf'\b{re.escape(lf)}\b', '', q_norm).strip()
        c_norm = re.sub(rf'\b{re.escape(lf)}\b', '', c_norm).strip()
        
    q_norm = re.sub(r'[^a-z0-9\s]', ' ', q_norm)
    c_norm = re.sub(r'[^a-z0-9\s]', ' ', c_norm)
    q_clean = ' '.join(q_norm.split())
    c_clean = ' '.join(c_norm.split())
    
    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q_clean == c_clean:
        return True, "EXACT"
        
    if len(q_clean) >= 5 and (q_clean in c_clean or c_clean in q_clean):
        return True, "SUBSTRING_MATCH"
        
    q_tokens = set(q_clean.split())
    c_tokens = set(c_clean.split())
    if q_tokens and c_tokens:
        inter = q_tokens.intersection(c_tokens)
        if len(inter) == len(q_tokens) or (len(inter) >= 2 and len(inter) / max(len(q_tokens), len(c_tokens)) >= 0.6):
            return True, "TOKEN_SET_MATCH"

    return False, "NO_MATCH"


def score_email_b2b(email, domain=""):
    """Score email specifically for B2B Poultry & Meat Processing enterprises."""
    if not email or not isinstance(email, str):
        return -1
    e = clean_extracted_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if any(bad in d for bad in BLACKLIST_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'sample', 'placeholder', 'jusu', 'tavo']):
        return -1
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if u in ['mail', 'email'] and (d in ['mail.lt', 'email.com', 'mail.com', 'email.lt'] or u == d.split('.')[0]):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 25

    # Priority 1: HR / Recruitment (+50)
    if u in ['karjera', 'darbas', 'personalas', 'hr', 'jobs', 'recruitment', 'career', 'careers', 'talent']:
        score += 50
    # Priority 2: Executive / Management (+45)
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'prekyba', 'pardavimai', 'valdyba', 'savininkas', 'komercija', 'uzsakymai']:
        score += 45
    # Priority 3: Official portal (+40)
    elif u in ['info', 'kontaktai', 'office', 'biuras', 'sekretoriatas', 'administracija', 'bendras', 'pastas']:
        score += 40
    # Named employee on official domain (+25)
    elif '.' in u and score >= 60:
        score += 25
    # Free webmail (+10)
    elif d in ['gmail.com', 'inbox.lt', 'one.lt']:
        score += 10
    # Technical / Accounting (+5)
    elif u in ['support', 'admin', 'buhalterija', 'it', 'servisas']:
        score += 5

    return score


def is_valid_website(comp_name, url):
    """Check if URL is valid official company website (not social or ad banner)."""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        return False
    u_low = url.lower()
    if any(bad in u_low for bad in BLACKLIST_DOMAINS):
        return False
    if 'citma.lt' in u_low and 'citma' not in comp_name.lower():
        return False
    return True


def fetch_html_quick(url, timeout_s=4):
    """Fetch HTML with curl_cffi Chrome120 and strict timeout."""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=timeout_s, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def crawl_site_for_emails_quick(web_url, comp_name=""):
    """Quick DOM-First Multi-Tier Email Extractor with strict timeouts."""
    if not is_valid_website(comp_name, web_url):
        return ""
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_quick(web_url, timeout_s=4)
    if not home_html and web_url != root:
        home_html = fetch_html_quick(root, timeout_s=4)
        
    if home_html:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = clean_extracted_email(m)
            if '@' in clean_m:
                found.add(clean_m)
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = clean_extracted_email(decode_cf(cf))
            if '@' in dec:
                found.add(dec)
        for em in EMAIL_REGEX.findall(home_html):
            if score_email_b2b(em, root) > 0:
                found.add(clean_extracted_email(em))
                
        best_home = max(found, key=lambda e: score_email_b2b(e, root)) if found else ""
        if best_home and score_email_b2b(best_home, root) >= 70:
            return best_home

        # Priority 10: Extract real DOM contact links from homepage
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].lower()
                txt = a.get_text().lower()
                if any(k in h or k in txt for k in LT_PRIORITY_KEYWORDS):
                    full = urllib.parse.urljoin(web_url, a['href'])
                    if full not in dom_contact_links and '#' not in a['href'] and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)
                        
            for cl in dom_contact_links[:3]:
                chtml = fetch_html_quick(cl, timeout_s=3)
                if not chtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = clean_extracted_email(m)
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = clean_extracted_email(decode_cf(cf))
                    if '@' in dec:
                        found.add(dec)
                for em in EMAIL_REGEX.findall(chtml):
                    if score_email_b2b(em, root) > 0:
                        found.add(clean_extracted_email(em))
                if found and any(score_email_b2b(e, root) >= 70 for e in found):
                    break
        except Exception:
            pass

    # Priority 2: Fallback Guess Paths if still nothing found
    if not found:
        for gp in LT_GUESS_SUBPATHS[:4]:
            guess_url = urllib.parse.urljoin(root, gp)
            ghtml = fetch_html_quick(guess_url, timeout_s=2)
            if not ghtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                clean_m = clean_extracted_email(m)
                if '@' in clean_m:
                    found.add(clean_m)
            for em in EMAIL_REGEX.findall(ghtml):
                if score_email_b2b(em, root) > 0:
                    found.add(clean_extracted_email(em))
            if found:
                break

    valid = [e for e in found if score_email_b2b(e, root) > 0]
    return max(valid, key=lambda e: score_email_b2b(e, root)) if valid else ""


def load_dataset(csv_path):
    """Load CSV dataset using native csv module."""
    with open(csv_path, mode='r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    return fieldnames, rows


def save_and_reorder(fieldnames, rows):
    """Save progress and generate standard 2COL Cold Mail CSV with 100% emails on top."""
    # Rule 12: Exclude blacklisted companies
    clean_rows = []
    for r in rows:
        if not is_blacklisted_company(r.get('Công ty', '')):
            clean_rows.append(r)

    # Format phone with '
    for r in clean_rows:
        r['SĐT'] = clean_phone_lt(r.get('SĐT', ''))

    # Separate with email and without email (100% emails on top)
    has_em = [r for r in clean_rows if r.get('Email', '').strip()]
    no_em = [r for r in clean_rows if not r.get('Email', '').strip()]
    sorted_rows = has_em + no_em

    for i, r in enumerate(sorted_rows, 1):
        r['No.'] = str(i)

    # Write 1ENR
    with open(CSV_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    if CSV_CSDL_PATH.parent.exists():
        with open(CSV_CSDL_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_rows)

    # Write 2COL Cold Mail CSV
    coldmail_rows = []
    for r in sorted_rows:
        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': r.get('Công ty', ''),
            'Chức danh': 'Direktorius' if r.get('Direktorius', '') else 'Vadovas',
            'Người liên hệ': r.get('Direktorius', '') or r.get('Nhân sự', ''),
            'SĐT': clean_phone_lt(r.get('SĐT', '')),
            'Liên Hệ': r.get('Web', ''),
            'Email': clean_extracted_email(r.get('Email', '')),
            'Liên Hệ mail': r.get('Source_URL', '') or r.get('Web', ''),
            'Địa chỉ': f"{r.get('Địa chỉ', '')}, {r.get('Thành phố', '')}".strip(', '),
            'Lương': '', 'Ngày đăng': '', 'Hạn tuyển': '', 'Check gửi': '',
            'Last Subject': '', 'Last Body HTML': '', 'Trạng thái Reply': '',
            'Lần Follow-up': '', 'Ngày Follow-up gần nhất': '', 'Mailbox đã dùng': '',
            'Category': r.get('Category', 'Paukštiena ir mėsa (Poultry & Meat)')
        })

    with open(COLDMAIL_CSV_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(coldmail_rows)

    if COLDMAIL_CSDL_PATH.parent.exists():
        with open(COLDMAIL_CSDL_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_COLUMNS)
            writer.writeheader()
            writer.writerows(coldmail_rows)

    return len(has_em)


async def run_enrichment(headless=False, limit=None):
    print("=" * 80)
    print("  GOOGLE MAPS ENRICHMENT - LITHUANIAN POULTRY & MEAT ENTERPRISES (LT_POUL)")
    print(f"  Target File : {CSV_PATH}")
    print(f"  Cold Mail   : {COLDMAIL_CSV_PATH}")
    print(f"  Cache File  : {CACHE_PATH}")
    print(f"  Profile Dir : {PROFILE_DIR}")
    print(f"  View Mode   : {'HEADLESS (Background)' if headless else 'VISUAL (Headless=False)'}")
    print("=" * 80 + "\n")

    if not CSV_PATH.exists():
        print(f"[ERROR] Target file '{CSV_PATH}' not found!")
        return

    fieldnames, rows = load_dataset(CSV_PATH)
    for col in ['Web', 'Email', 'SĐT', 'Địa chỉ', 'Thành phố']:
        if col not in fieldnames:
            fieldnames.append(col)

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache Checkpoint: {len(cache):,} công ty đã kiểm tra từ trước.")
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Lọc danh sách công ty cần xử lý (Chưa có Email)
    pending_rows = []
    for r in rows:
        em = r.get('Email', '').strip()
        comp = r.get('Công ty', '').strip()
        cache_key = comp.lower()
        if em:
            continue
        if cache_key in cache:
            c = cache[cache_key]
            if c.get('Email'):
                r['Email'] = c['Email']
            if c.get('Web') and not r.get('Web', '').strip():
                r['Web'] = c['Web']
            if c.get('SĐT') and not r.get('SĐT', '').strip():
                r['SĐT'] = c['SĐT']
            continue
        pending_rows.append(r)

    already_has = sum(1 for r in rows if r.get('Email', '').strip())
    print(f"[*] Tổng số doanh nghiệp       : {len(rows):,}")
    print(f"[*] Đã có Email B2B            : {already_has:,} ({already_has/len(rows)*100:.1f}%)")
    print(f"[*] Đã lưu trong Cache         : {len(cache):,} công ty")
    print(f"[*] CẦN LÀM GIÀU GOOGLE MAPS   : {len(pending_rows):,} công ty\n")

    if not pending_rows:
        print("[✔] Toàn bộ công ty đã có email hoặc đã kiểm tra xong!")
        save_and_reorder(fieldnames, rows)
        return

    if limit and limit > 0:
        pending_rows = pending_rows[:limit]
        print(f"[*] Giới hạn xử lý: {limit} công ty theo tùy chọn --limit.")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("[*] Đang khởi động Google Chrome trực quan (Headless=False)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            locale="lt-LT",
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
        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed = 0
        newly_found = 0

        for r in pending_rows:
            if page.is_closed():
                try:
                    page = await browser.new_page()
                except Exception:
                    pass

            comp = r.get('Công ty', '').strip()
            city = r.get('Thành phố', '').strip()
            curr_web = r.get('Web', '').strip()
            cache_key = comp.lower()

            processed += 1
            print(f"[{processed:04d}/{len(pending_rows):04d}] {comp[:35]:<35} | ", end="", flush=True)

            found_email = ""
            gmap_web = None
            gmap_phone = None
            gmap_addr = None

            # BƯỚC 1: Nếu công ty đã có website hợp lệ sẵn từ file
            if curr_web and is_valid_website(comp, curr_web):
                found_email = crawl_site_for_emails_quick(curr_web, comp)
                if found_email:
                    print(f"WEB SẴN: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    r['Email'] = found_email
                    newly_found += 1

            # BƯỚC 2: Nếu chưa có Email -> Tìm kiếm trên Google Maps
            if not found_email:
                queries = []
                if city:
                    queries.append(f"{comp} {city} Lietuva")
                queries.append(f"{comp} Lietuva")

                matched = False
                for q_term in queries:
                    if matched:
                        break
                    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}"

                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=14000)
                        await asyncio.sleep(1.2)

                        # Bấm nút đồng ý Cookie nếu có
                        try:
                            consent_btn = await page.query_selector(
                                'button:has-text("Priimti viską"), button:has-text("Accept all"), button:has-text("Sutinku")'
                            )
                            if consent_btn:
                                await consent_btn.click()
                                await asyncio.sleep(0.8)
                        except Exception:
                            pass

                        # Chờ kết quả hiển thị
                        for _ in range(6):
                            if await page.query_selector('a[href*="/maps/place/"], h1.DUwDvf'):
                                break
                            await asyncio.sleep(0.5)

                        # 1. Danh sách nhiều kết quả
                        items = await page.query_selector_all('a[href*="/maps/place/"]')
                        if items:
                            for item in items[:3]:
                                aria_label = await item.get_attribute('aria-label') or ""
                                is_ok, reason = is_valid_name_match(comp, aria_label)
                                if is_ok:
                                    await item.click()
                                    await asyncio.sleep(1.5)
                                    matched = True
                                    break
                        else:
                            # 2. Trang chi tiết địa điểm duy nhất
                            title_elem = await page.query_selector('h1.DUwDvf')
                            if title_elem:
                                t_text = await title_elem.inner_text()
                                is_ok, reason = is_valid_name_match(comp, t_text)
                                matched = is_ok

                        if matched:
                            # Lấy website
                            web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Svetainė"], a[aria-label*="Website"]')
                            if web_btn:
                                cand_web = await web_btn.get_attribute('href')
                                if cand_web and is_valid_website(comp, cand_web):
                                    gmap_web = cand_web

                            # Lấy SĐT
                            phone_btn = await page.query_selector('button[data-item-id^="phone:"], button[aria-label*="Telefonas"]')
                            if phone_btn:
                                p_attr = await phone_btn.get_attribute('data-item-id')
                                if p_attr and p_attr.startswith('phone:tel:'):
                                    gmap_phone = p_attr.replace('phone:tel:', '').strip()
                                else:
                                    p_txt = await phone_btn.inner_text()
                                    if p_txt:
                                        gmap_phone = p_txt.strip()

                            # Lấy Địa chỉ
                            addr_btn = await page.query_selector('button[data-item-id="address"]')
                            if addr_btn:
                                a_txt = await addr_btn.inner_text()
                                if a_txt:
                                    gmap_addr = a_txt.strip()

                    except Exception:
                        pass

                # Cập nhật kết quả từ Maps
                if matched:
                    if gmap_web:
                        if not r.get('Web', '').strip():
                            r['Web'] = gmap_web
                        # Quét email từ website vừa tìm được
                        found_email = crawl_site_for_emails_quick(gmap_web, comp)
                        if found_email:
                            r['Email'] = found_email
                            newly_found += 1
                            print(f"GMAP WEB: {gmap_web[:22]:<22} | EMAIL: {found_email}")
                        else:
                            print(f"GMAP WEB: {gmap_web[:22]:<22} | (Không có mail)")
                    elif gmap_phone:
                        print(f"GMAP PHONE: {gmap_phone} (Không có web)")
                    else:
                        print("Khớp tên trên Maps (Không có web/sđt)")

                    if gmap_phone and not r.get('SĐT', '').strip():
                        r['SĐT'] = clean_phone_lt(gmap_phone)
                    if gmap_addr and not r.get('Địa chỉ', '').strip():
                        r['Địa chỉ'] = gmap_addr
                else:
                    print("Không tìm thấy trên Maps")

            # Lưu vào Cache
            cache[cache_key] = {
                'Web': r.get('Web', ''),
                'Email': r.get('Email', ''),
                'SĐT': clean_phone_lt(r.get('SĐT', ''))
            }

            # Checkpoint tự động sau mỗi 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cnt = save_and_reorder(fieldnames, rows)
                print(f"[*] Checkpoint saved: {cnt} công ty có email (+{newly_found} mới)")

        # Final Save
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_cnt = save_and_reorder(fieldnames, rows)

        print("\n" + "=" * 80)
        print("  GOOGLE MAPS ENRICHMENT COMPLETED SUCCESSFULLY!")
        print(f"  Tổng doanh nghiệp  : {len(rows):,}")
        print(f"  Tổng số có Email   : {final_cnt:,} ({(final_cnt/len(rows))*100:.1f}%)")
        print(f"  Email mới tìm thấy : +{newly_found:,}")
        print("  Đã lưu đồng bộ:")
        print(f"    - {CSV_PATH}")
        print(f"    - {COLDMAIL_CSV_PATH}")
        print("=" * 80)

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Lithuanian Poultry & Meat Enterprises")
    parser.add_argument("--headless", action="store_true", help="Run browser in background (headless mode)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to enrich")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless, limit=args.limit))


if __name__ == '__main__':
    main()
