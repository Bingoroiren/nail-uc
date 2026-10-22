# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN POULTRY & MEAT PROCESSING (LT_POUL_WEBD)
Built strictly adhering to:
- Skill enrich-maps & Skill data-standards (Strict Name Matching, headless=False, incremental save)
- Skill crawl-mail (Priority 10 DOM menu, Cloudflare XOR decode, B2B email scoring)
- 100% Aggregator & Junk Email Filtering (Blacklisting all Lithuanian directory/yellowpage portals)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY (Native csv, zero pandas dependency)
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
import urllib.request
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Reconfigure stdout for UTF-8 in Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT_DIR, "LT_POUL_WEBD_1ENR.csv")
CSV_CSDL_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_POUL_WEBD_1ENR.csv")
COLDMAIL_CSV_PATH = os.path.join(ROOT_DIR, "LT_POUL_WEBD_2COL.csv")
COLDMAIL_CSDL_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_POUL_WEBD_2COL.csv")
CACHE_PATH = os.path.join(ROOT_DIR, "crawlmail", "cache_enrich_maps_lt_poul.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
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

# Rule 12: Danh sách công ty loại trừ vĩnh viễn khỏi danh sách kết nối
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
    '/kontaktai', '/kontaktai/', '/kontaktai.html', '/kontaktai.php',
    '/apie-mus', '/apie-mus/', '/apie-mus.html',
    '/karjera', '/karjera/', '/darbas',
    '/rekvizitai', '/susisiekite',
    '/contact', '/contacts', '/contact-us', '/about', '/about-us'
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
        
    # Check if candidate or query is substring with at least 5 chars
    if len(q_clean) >= 5 and (q_clean in c_clean or c_clean in q_clean):
        return True, "SUBSTRING_MATCH"
        
    # Token set intersection
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


def select_best_email(emails, domain=""):
    """Select the single best B2B email with the highest score."""
    valid = [clean_extracted_email(e) for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))


def fetch_html_stealth(url):
    """Fetch HTML with curl_cffi Chrome120 or fallback urllib."""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=7, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""


def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor per Skill crawl-mail (Lithuania)."""
    if not web_url or not web_url.startswith('http'):
        return ""
    if any(bad in web_url.lower() for bad in BLACKLIST_DOMAINS):
        return ""
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
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
                
        best_home = select_best_email(found, root)
        if best_home and score_email_b2b(best_home, root) >= 80:
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
                        
            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl)
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
                if found:
                    break
        except Exception:
            pass

    # Priority 2: Fallback Guess Paths if still nothing found
    if not found:
        for gp in LT_GUESS_SUBPATHS[:6]:
            guess_url = urllib.parse.urljoin(root, gp)
            ghtml = fetch_html_stealth(guess_url)
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

    return select_best_email(found, root)


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

    if os.path.exists(os.path.dirname(CSV_CSDL_PATH)):
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

    if os.path.exists(os.path.dirname(COLDMAIL_CSDL_PATH)):
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
    print(f"  View Mode   : {'HEADLESS (Background)' if headless else 'VISUAL (Headless=False)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] Target file '{CSV_PATH}' not found!")
        return

    fieldnames, rows = load_dataset(CSV_PATH)
    for col in ['Web', 'Email', 'SĐT', 'Địa chỉ', 'Thành phố']:
        if col not in fieldnames:
            fieldnames.append(col)

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache)} cached company profiles from {CACHE_PATH}.")
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Step 0: Quick direct crawl for companies already having Web but no Email
    has_web_no_email_rows = [
        r for r in rows
        if not r.get('Email', '').strip() 
        and r.get('Web', '').strip().startswith('http') 
        and not any(bad in r.get('Web', '').lower() for bad in BLACKLIST_DOMAINS)
        and not ('citma.lt' in r.get('Web', '').lower() and 'citma' not in r.get('Công ty', '').lower())
    ]
    if has_web_no_email_rows:
        print(f"\n[*] STEP 0: Direct Website Crawling for {len(has_web_no_email_rows)} companies with existing Web link...")
        direct_found = 0
        for i_idx, r in enumerate(has_web_no_email_rows, 1):
            w = r.get('Web', '').strip()
            comp = r.get('Công ty', '').strip()
            em = crawl_site_for_emails(w)
            if em:
                r['Email'] = em
                direct_found += 1
                print(f"    [{i_idx}/{len(has_web_no_email_rows)}] [+] DIRECT EMAIL: {comp} -> {em}")
            if i_idx % 10 == 0:
                save_and_reorder(fieldnames, rows)
        print(f"[*] STEP 0 COMPLETED: Discovered +{direct_found} emails directly from existing websites!\n")
        save_and_reorder(fieldnames, rows)

    # Find rows needing Google Maps enrichment
    pending_rows = [
        r for r in rows
        if not r.get('Email', '').strip()
    ]

    if limit and limit > 0:
        pending_rows = pending_rows[:limit]

    print(f"[*] Total companies: {len(rows)} | Already have Email: {len(rows) - len(pending_rows)} | Needing Maps: {len(pending_rows)}")

    if not pending_rows:
        print("[+] All companies already have emails!")
        save_and_reorder(fieldnames, rows)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--js-flags=--max-old-space-size=512"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="lt-LT"
        )
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        newly_found = 0

        for r in pending_rows:
            comp = r.get('Công ty', '').strip()
            city = r.get('Thành phố', '').strip()
            ico = r.get('IČO', '').strip()
            cache_key = ico if ico else f"{comp}::{city}".lower()

            processed += 1

            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    r['Email'] = c['Email']
                if c.get('Web') and not r.get('Web', '').strip():
                    r['Web'] = c['Web']
                if c.get('SĐT') and not r.get('SĐT', '').strip():
                    r['SĐT'] = c['SĐT']
                continue

            # Query Google Maps
            q = f"{comp} {city} Lietuva".strip() if city else f"{comp} Lietuva".strip()
            url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q)}"
            web_url = None
            phone_val = None
            addr_val = None
            matched = False

            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                await page.wait_for_timeout(2000)

                # Consent handle
                if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                    print("\n\a[WARNING] Google Captcha / Consent detected! Please solve it on browser window...\n")
                    await page.wait_for_timeout(10000)

                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    for item in items[:3]:
                        aria_label = await item.get_attribute('aria-label') or ""
                        is_ok, reason = is_valid_name_match(comp, aria_label)
                        if is_ok:
                            await item.click()
                            await page.wait_for_timeout(2000)
                            matched = True
                            break
                else:
                    title_elem = await page.query_selector('h1.DUwDvf')
                    if title_elem:
                        t_text = await title_elem.inner_text()
                        is_ok, reason = is_valid_name_match(comp, t_text)
                        matched = is_ok

                if matched:
                    # Website link
                    web_btn = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Svetainė"], a[aria-label*="Website"]')
                    if web_btn:
                        cand_web = await web_btn.get_attribute('href')
                        if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS) and not ('citma.lt' in cand_web.lower() and 'citma' not in comp.lower()):
                            web_url = cand_web

                    # Phone button
                    phone_btn = await page.query_selector('button[data-item-id^="phone:"], button[aria-label*="Telefonas"]')
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id')
                        if p_attr and p_attr.startswith('phone:tel:'):
                            phone_val = p_attr.replace('phone:tel:', '').strip()
                        else:
                            p_txt = await phone_btn.inner_text()
                            if p_txt:
                                phone_val = p_txt.strip()

                    # Address button
                    addr_btn = await page.query_selector('button[data-item-id="address"]')
                    if addr_btn:
                        a_txt = await addr_btn.inner_text()
                        if a_txt:
                            addr_val = a_txt.strip()

            except Exception:
                pass

            email = ""
            if web_url and matched:
                email = crawl_site_for_emails(web_url)

            if web_url and matched and not r.get('Web', '').strip():
                r['Web'] = web_url
            if email:
                r['Email'] = email
                newly_found += 1
                print(f"[{processed}/{len(pending_rows)}] [+] NEW EMAIL: {comp} -> {email} ({web_url})")
            elif matched and web_url:
                print(f"[{processed}/{len(pending_rows)}] [~] MATCHED WEB: {comp} -> {web_url} (No direct email)")
            elif matched and phone_val:
                print(f"[{processed}/{len(pending_rows)}] [~] MATCHED PHONE: {comp} -> {phone_val}")

            if phone_val and matched and not r.get('SĐT', '').strip():
                r['SĐT'] = clean_phone_lt(phone_val)
            if addr_val and matched and not r.get('Địa chỉ', '').strip():
                r['Địa chỉ'] = addr_val

            # Record in cache
            cache[cache_key] = {
                'Web': web_url if (web_url and matched) else "",
                'Email': email,
                'SĐT': clean_phone_lt(phone_val) if (phone_val and matched) else ""
            }

            # Incremental auto-save every 5 companies
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cnt = save_and_reorder(fieldnames, rows)
                print(f"[*] Checkpoint saved ({processed}/{len(pending_rows)} processed, {cnt} total valid emails, +{newly_found} new)")

        # Final Save
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_cnt = save_and_reorder(fieldnames, rows)

        print("\n" + "=" * 80)
        print("  GOOGLE MAPS ENRICHMENT COMPLETED SUCCESSFULLY!")
        print(f"  Total companies: {len(rows)}")
        print(f"  Final emails with clean data: {final_cnt} / {len(rows)} ({(final_cnt/len(rows))*100:.1f}%)")
        print(f"  Newly discovered: +{newly_found}")
        print("  Files saved:")
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
