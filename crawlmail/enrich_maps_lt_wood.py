# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN WOOD & FURNITURE ENTERPRISES (LT_WOOD_GMAP)
Dataset: LT_WOOD_COMB_0RAW.csv -> LT_WOOD_GMAP_1ENR.csv + LT_WOOD_GMAP_2COL.csv

Core Architecture & Compliance:
- Skill enrich-maps & data-standards: Strict Name Matching, headless=False, incremental auto-save
- Skill crawl-mail: Priority 10 DOM menu, Cloudflare XOR decode, B2B email scoring
- Anti-Aggregator & Anti-Casino Blacklist (Filtering info.lt, rekvizitai, statyba, facebook, etc.)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2: Phone numbers strictly formatted with leading single quote ('+370...)
- Rule 3: Single best B2B email per company, 100% emails sorted to the top
- Rule 4: Visual browser mode (headless=False) with viewport >= 1280x800
- Rule 5: Incremental auto-save every 5 companies, checkpoint cache JSON for 100% resume
- Rule 10: 17-character fixed filename convention (LT_WOOD_GMAP_1ENR.csv / LT_WOOD_GMAP_2COL.csv)
- Rule 11: Smart & strict name matching with NFKD unicode normalization & legal forms stripping
- Rule 12: Permanent blacklist company exclusion (Scandi Standard, Biliarta, Daigre)
"""

import sys
import os
import re
import ssl
import json
import time
import asyncio
import argparse
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Ensure UTF-8 output in Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# PATH CONSTANTS
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV_PATH = ROOT_DIR / "LT_WOOD_COMB_0RAW.csv"
OUTPUT_1ENR_PATH = ROOT_DIR / "LT_WOOD_GMAP_1ENR.csv"
OUTPUT_1ENR_CSDL = ROOT_DIR / "csdl_mlt" / "LT_WOOD_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_WOOD_GMAP_2COL.csv"
OUTPUT_2COL_CSDL = ROOT_DIR / "csdl_mlt" / "LT_WOOD_GMAP_2COL.csv"
OUTPUT_2COL_ARCH = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_WOOD_GMAP_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_wood.json"

# ----------------------------------------------------------------------
# NETWORK & SSL SETUP
# ----------------------------------------------------------------------
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# ----------------------------------------------------------------------
# BLACKLISTS & FILTERING
# ----------------------------------------------------------------------
# Aggregators, directories, social portals, governmental databases
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
    'cvmarket.lt', 'rekv.lt', 'proton.me', 'lovejob.lt', 'tinklalapiai.lt'
]

# Rule 12: Permanent company blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

GAMBLING_KEYWORDS = [
    'casino', 'kazino', 'ggbet', 'vulkan', 'betting', 'lažybos', 'lazybos',
    'poker', 'slots', 'jackpot', 'roulette', 'bukmeker', 'gambling', 'guarana.lt'
]

JUNK_EMAIL_DOMAINS = set(BLACKLIST_DOMAINS) | {
    'example.com', 'domain.com', 'yourdomain.com', 'yourcompany.com',
    'company.com', 'website.com', 'site.com', 'pavyzdys.lt', 'imone.lt', 'email.com', 'mail.com'
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

# Lithuanian localized menu navigation keywords (Priority 10)
LT_PRIORITY_KEYWORDS = [
    'kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai',
    'susisiekite', 'administracija', 'prekyba', 'pardavimai', 'gamyba',
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


# ----------------------------------------------------------------------
# HELPER FUNCTIONS: NORMALIZATION, VALIDATION, SCORING
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    """Rule 12: Permanent company blacklist exclusion."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str):
    """Normalize Lithuanian phone number strictly with leading single quote."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = str(phone_str).strip().lstrip("'")
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


def clean_email(email_str):
    """Decode and scrub zero-width spaces, %20, and phone labels from email text."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = urllib.parse.unquote(email_str).strip().lower()
    # Remove unicode whitespace artifacts
    for bad_char in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ']:
        e = e.replace(bad_char, '')
    if e.startswith('20') and '@' in e and not e.startswith('202'):
        e = e[2:]
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def decode_cf(cf_hex):
    """Decode Cloudflare XOR data-cfemail."""
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def is_valid_website(url):
    """Verify that website is a legitimate business domain and not aggregator/casino."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.replace('www.', '').lower()
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        if any(bad in domain for bad in BLACKLIST_DOMAINS):
            return False
        if any(g in domain for g in GAMBLING_KEYWORDS):
            return False
        return True
    except Exception:
        return False


def normalize_text_core(text):
    """Strip punctuation, quotes, legal forms, and NFKD normalize."""
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    t = ''.join(c for c in n if not unicodedata.combining(c))
    t = re.sub(r'["\'„“”«»]', '', t).strip()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    
    legal_forms = [
        'uzdaroji akcine bendrove', 'mazoji bendrija', 'akcine bendrove',
        'viesoji istaiga', 'individuali imone', 'zemes ukio bendrove',
        'uab', 'mb', 'ab', 'vsi', 'ii', 'zub', 'kb', 'filialas', 'skyrius',
        'imone', 'bendra imone', 'kooperatyvas'
    ]
    for lf in legal_forms:
        t = re.sub(rf'\b{re.escape(lf)}\b', '', t).strip()
        
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return t


def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching per skill enrich-maps taking into account Lithuanian legal forms."""
    if not query_name or not candidate_name:
        return False, "EMPTY"
        
    q = normalize_text_core(query_name)
    c = normalize_text_core(candidate_name)
    
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c) if p.strip()]
    if any(p == q for p in parts):
        return True, "DELIMITER_MATCH"
        
    # Substring match if sufficiently distinctive (>= 5 chars)
    if len(q) >= 5 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    return False, "NO_MATCH"


def score_email_b2b_lt(email, domain=""):
    """
    Score email specifically for Lithuanian Wood & Furniture enterprises (Rule 3).
    B2B Manpower / Supply Brokerage scoring hierarchy.
    """
    if not email or not isinstance(email, str):
        return -1
    e = clean_email(email)
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
        score += 35

    # Priority 1: HR / Recruitment (+50)
    if any(k in u for k in ['karjera', 'darbas', 'personalas', 'hr', 'jobs', 'recruitment', 'career', 'careers', 'talent']):
        score += 50
    # Priority 2: Executive / Management / Owner (+45)
    elif any(k in u for k in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'savininkas', 'prekyba', 'pardavimai', 'gamyba']):
        score += 45
    # Priority 3: Official portal (+40)
    elif any(k in u for k in ['info', 'kontaktai', 'office', 'biuras', 'sekretoriatas', 'administracija', 'bendras', 'pastas']):
        score += 40
    # Named employee on official domain (+25)
    elif '.' in u and score >= 60:
        score += 25
    # Free webmail (+10)
    elif d in ['gmail.com', 'inbox.lt', 'one.lt', 'zebra.lt']:
        score += 10
    # Technical / Accounting (+5)
    elif any(k in u for k in ['support', 'admin', 'buhalterija', 'it', 'servisas']):
        score += 5

    return score


def select_best_email(emails, domain=""):
    """Select the single best B2B email with the highest score."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


# ----------------------------------------------------------------------
# WEBSITE EMAIL CRAWLING (MULTI-TIER DOM-FIRST)
# ----------------------------------------------------------------------
def fetch_html_stealth(url):
    """Fetch HTML with curl_cffi Chrome120 impersonation or fallback urllib."""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=4, verify=False)
        if r.status_code == 200:
            return r.text
        elif r.status_code in (404, 403, 410, 500, 502, 503):
            return ""
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""


def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor per Skill crawl-mail (Lithuania)."""
    if not is_valid_website(web_url):
        return ""
    if not web_url.startswith('http'):
        web_url = 'https://' + web_url
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
    if home_html:
        # Check mailto:
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = clean_email(m)
            if '@' in clean_m:
                found.add(clean_m)
        # Check cloudflare XOR
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = clean_email(decode_cf(cf))
            if '@' in dec:
                found.add(dec)
        # Check direct regex
        for em in EMAIL_REGEX.findall(home_html):
            if score_email_b2b_lt(em, root) > 0:
                found.add(clean_email(em))
                
        best_home = select_best_email(found, root)
        if best_home and score_email_b2b_lt(best_home, root) >= 80:
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
                        
            # Crawl up to 4 real DOM contact links
            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl)
                if not chtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = clean_email(m)
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = clean_email(decode_cf(cf))
                    if '@' in dec:
                        found.add(dec)
                for em in EMAIL_REGEX.findall(chtml):
                    if score_email_b2b_lt(em, root) > 0:
                        found.add(clean_email(em))
                if found and any(score_email_b2b_lt(e, root) >= 70 for e in found):
                    break
        except Exception:
            pass

        # Priority 2: Fallback Guess Paths ONLY if homepage was reachable but no email found yet
        if not found:
            for gp in LT_GUESS_SUBPATHS[:5]:
                guess_url = urllib.parse.urljoin(root, gp)
                ghtml = fetch_html_stealth(guess_url)
                if not ghtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                    clean_m = clean_email(m)
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', ghtml):
                    dec = clean_email(decode_cf(cf))
                    if '@' in dec:
                        found.add(dec)
                for em in EMAIL_REGEX.findall(ghtml):
                    if score_email_b2b_lt(em, root) > 0:
                        found.add(clean_email(em))
                if found:
                    break

    return select_best_email(found, root)


# ----------------------------------------------------------------------
# SAVE & REORDER FUNCTION (PUSH 100% EMAILS TO TOP)
# ----------------------------------------------------------------------
def save_and_reorder(df):
    """
    Save progress and generate standard 2COL Cold Mail CSV and 1ENR Master.
    - Excludes Rule 12 permanent blacklist companies.
    - Sorts 100% of companies WITH EMAIL to the top (rows 1..N).
    - Ensures phone numbers strictly start with single quote.
    """
    df_out = df.copy()

    # Rule 12 Filter
    if 'Cong ty' in df_out.columns:
        df_out = df_out[~df_out['Cong ty'].apply(is_blacklisted_company)].reset_index(drop=True)

    df_out['SDT'] = df_out['SDT'].apply(clean_phone_lt)
    df_out['Email'] = df_out['Email'].apply(clean_email)

    # Separate with email and without email (100% emails on top)
    has_em = df_out[df_out['Email'] != ''].copy()
    no_em = df_out[df_out['Email'] == ''].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Write LT_WOOD_GMAP_1ENR.csv (Root and CSDL)
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')
    OUTPUT_1ENR_CSDL.parent.mkdir(parents=True, exist_ok=True)
    df_sorted.to_csv(OUTPUT_1ENR_CSDL, index=False, encoding='utf-8-sig')

    # Prepare standard 2COL Cold Mail CSV
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = str(r.get('Cong ty', '')).strip()
        manager = str(r.get('Nguoi quan ly', '')).strip()
        title = str(r.get('Chuc danh', '')).strip()
        if not title:
            title = 'Direktorius' if manager else 'Vadovas'

        web_val = str(r.get('Website', '')).strip()
        email_val = str(r.get('Email', '')).strip()
        phone_val = clean_phone_lt(r.get('SDT', ''))
        city_val = str(r.get('Thanh pho', '')).strip()
        addr_val = str(r.get('Dia chi', '')).strip()
        full_addr = f"{addr_val}, {city_val}".strip(', ') if city_val else addr_val

        coldmail_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': comp_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone_val,
            'Liên Hệ': web_val,
            'Email': email_val,
            'Liên Hệ mail': f"mailto:{email_val}" if email_val else web_val,
            'Địa chỉ': full_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': r.get('Nam thanh lap', ''),
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Baldų gamyba / Medienos apdirbimas')
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')
    OUTPUT_2COL_CSDL.parent.mkdir(parents=True, exist_ok=True)
    df_2col.to_csv(OUTPUT_2COL_CSDL, index=False, encoding='utf-8-sig')
    OUTPUT_2COL_ARCH.parent.mkdir(parents=True, exist_ok=True)
    df_2col.to_csv(OUTPUT_2COL_ARCH, index=False, encoding='utf-8-sig')

    # Also save subset with email ready
    df_ready = df_2col[df_2col['Email'] != ''].copy()
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding='utf-8-sig')

    return len(has_em)


# ----------------------------------------------------------------------
# MAIN ENRICHMENT ENGINE
# ----------------------------------------------------------------------
async def run_enrichment(headless=False, limit=None, start_idx=0, skip_phase1=False, phase1_only=False):
    print("=" * 80)
    print("  GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN WOOD & FURNITURE (STRICT MATCH)")
    print(f"  Input File  : {INPUT_CSV_PATH}")
    print(f"  Output 1ENR : {OUTPUT_1ENR_PATH}")
    print(f"  Output 2COL : {OUTPUT_2COL_PATH}")
    print(f"  Only Emails : {OUTPUT_READY_PATH}")
    print(f"  Cache File  : {CACHE_PATH}")
    print(f"  Browser     : {'HEADLESS (Background)' if headless else 'VISUAL (Headless=False, 1280x800)'}")
    if limit:
        print(f"  Limit Count : {limit}")
    if skip_phase1:
        print("  Options     : SKIP PHASE 1 (Direct to Google Maps)")
    elif phase1_only:
        print("  Options     : PHASE 1 ONLY (Fast Website Crawl)")
    print("=" * 80 + "\n")

    if not INPUT_CSV_PATH.exists():
        print(f"[ERROR] Target file '{INPUT_CSV_PATH}' not found!")
        return

    # Check if 1ENR already exists for resume, otherwise read 0RAW
    target_read_path = OUTPUT_1ENR_PATH if OUTPUT_1ENR_PATH.exists() else INPUT_CSV_PATH
    print(f"[*] Reading source dataset from: {target_read_path.name}")
    df = pd.read_csv(target_read_path, encoding='utf-8-sig', dtype=str).fillna('')

    for col in ['Website', 'Email', 'SDT']:
        if col not in df.columns:
            df[col] = ''

    # Load cache
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache)} cached company records from {CACHE_PATH.name}.")
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Build memory map of known valid emails from current df
    for idx, row in df.iterrows():
        comp = str(row['Cong ty']).strip()
        city = str(row.get('Thanh pho', '')).strip()
        code = str(row.get('Company_Code', '')).strip()
        cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(city)}"
        em = clean_email(str(row['Email']).strip())
        if em and not any(bad in em for bad in BLACKLIST_DOMAINS):
            if cache_key not in cache or not cache[cache_key].get('Email'):
                cache[cache_key] = {
                    'Web': str(row.get('Website', '')).strip(),
                    'Email': em,
                    'SDT': clean_phone_lt(str(row.get('SDT', '')).strip())
                }

    # Step 1: Rapid Direct Website Crawling for existing official websites without email
    direct_found = 0
    if not skip_phase1:
        print("\n" + "-" * 80)
        print("  PHASE 1: Direct Website Email Crawling for Existing Official URLs")
        print("-" * 80)
        direct_candidates = []
        for idx, row in df.iterrows():
            em = clean_email(str(row['Email']).strip())
            web = str(row.get('Website', '')).strip()
            if not em and is_valid_website(web):
                direct_candidates.append(idx)

        total_direct_avail = len(direct_candidates)
        if limit:
            direct_candidates = direct_candidates[:limit]

        print(f"[*] Found {total_direct_avail} companies with official websites pending email crawl...")
        for c_idx in direct_candidates:
            row = df.loc[c_idx]
            comp = str(row['Cong ty']).strip()
            web = str(row.get('Website', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            city = str(row.get('Thanh pho', '')).strip()
            cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(city)}"

            # If cache already says we crawled this, skip (even if without email)
            if cache_key in cache:
                if cache[cache_key].get('Email'):
                    df.at[c_idx, 'Email'] = cache[cache_key]['Email']
                continue

            em_found = crawl_site_for_emails(web)
            if em_found:
                df.at[c_idx, 'Email'] = em_found
                direct_found += 1
                print(f"  [+] DIRECT WEB EMAIL: {comp} -> {em_found} ({web})")
                cache[cache_key] = {
                    'Web': web,
                    'Email': em_found,
                    'SDT': clean_phone_lt(str(row.get('SDT', '')).strip())
                }
            else:
                if cache_key not in cache:
                    cache[cache_key] = {
                        'Web': web,
                        'Email': '',
                        'SDT': clean_phone_lt(str(row.get('SDT', '')).strip())
                    }

        if direct_found > 0:
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            cnt = save_and_reorder(df)
            print(f"[*] Phase 1 complete: Discovered +{direct_found} emails directly from official websites! (Total emails: {cnt})")

        if phase1_only:
            print("\n[+] Phase 1 only requested. Exiting without launching Google Maps.")
            return

    # Step 2: Google Maps Enrichment for remaining rows missing Email
    print("\n" + "-" * 80)
    print("  PHASE 2: Google Maps Search & Enrichment (Visual Chrome)")
    print("-" * 80)
    pending_indices = []
    for idx, row in df.iterrows():
        em = clean_email(str(row['Email']).strip())
        if not em:
            pending_indices.append(idx)

    if start_idx > 0:
        pending_indices = [i for i in pending_indices if i >= start_idx]
    if limit:
        pending_indices = pending_indices[:limit]

    print(f"[*] Total companies: {len(df)} | Already have Email: {len(df) - len(pending_indices)} | Needing Maps: {len(pending_indices)}")

    if not pending_indices:
        print("[+] All pending companies already have emails!")
        final_cnt = save_and_reorder(df)
        print(f"[+] Final valid email count: {final_cnt}")
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
        # Pre-inject Google consent cookie to bypass consent popup
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        processed = 0
        newly_found = 0

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row['Cong ty']).strip()
            city = str(row.get('Thanh pho', '')).strip()
            khu_vuc = str(row.get('Khu vuc', '')).strip()
            code = str(row.get('Company_Code', '')).strip()
            cache_key = code if code else f"{normalize_text_core(comp)}::{normalize_text_core(city)}"

            processed += 1

            # Check cache first (skip if already searched in previous run)
            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, 'Email'] = c['Email']
                if c.get('Web') and not df.at[idx, 'Website']:
                    df.at[idx, 'Website'] = c['Web']
                if c.get('SDT') and not df.at[idx, 'SDT']:
                    df.at[idx, 'SDT'] = c['SDT']
                continue

            # Construct Maps Query
            loc_term = city if city else (khu_vuc if khu_vuc else "Lietuva")
            query = f"{comp} {loc_term} Lietuva".strip()
            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"

            web_url = None
            phone_val = None
            matched = False

            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=14000)
                await asyncio.sleep(2.0)

                # Check Captcha or Consent
                if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                    print("\n\a[WARNING] Google Captcha detected! Please solve it on browser window...\n")
                    await asyncio.sleep(15.0)

                # Case A: Multiple place results in sidebar
                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    for item in items[:4]:
                        aria_label = await item.get_attribute('aria-label') or ""
                        is_ok, match_type = is_valid_name_match(comp, aria_label)
                        if is_ok:
                            await item.click()
                            await asyncio.sleep(2.0)
                            matched = True
                            break
                else:
                    # Case B: Directly opened place detail view
                    title_elem = await page.query_selector('h1.DUwDvf')
                    if title_elem:
                        t_text = await title_elem.inner_text()
                        is_ok, match_type = is_valid_name_match(comp, t_text)
                        matched = is_ok

                # Extract details if matched
                if matched:
                    # Extract Website
                    web_btn = await page.query_selector('a[data-item-id="authority"]')
                    if web_btn:
                        cand_web = await web_btn.get_attribute('href')
                        if is_valid_website(cand_web):
                            web_url = cand_web

                    # Extract Phone
                    phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id')
                        if p_attr and p_attr.startswith('phone:tel:'):
                            phone_val = p_attr.replace('phone:tel:', '').strip()
                        else:
                            phone_val = await phone_btn.inner_text()

            except Exception as e:
                pass

            email = ""
            if web_url and matched:
                email = crawl_site_for_emails(web_url)

            # Apply updates
            if web_url and matched and not df.at[idx, 'Website']:
                df.at[idx, 'Website'] = web_url
            if phone_val and matched and not df.at[idx, 'SDT']:
                df.at[idx, 'SDT'] = clean_phone_lt(phone_val)

            if email:
                df.at[idx, 'Email'] = email
                newly_found += 1
                print(f"[{processed}/{len(pending_indices)}] [+] NEW EMAIL: {comp} -> {email} ({web_url})")
            elif matched and web_url:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED WEB: {comp} -> {web_url} (No direct email)")
            elif matched and phone_val:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED PHONE: {comp} -> {phone_val}")
            else:
                print(f"[{processed}/{len(pending_indices)}] [-] NO MATCH: {comp} ({city})")

            # Update Cache
            cache[cache_key] = {
                'Web': web_url if (web_url and matched) else df.at[idx, 'Website'],
                'Email': email if email else df.at[idx, 'Email'],
                'SDT': clean_phone_lt(phone_val) if (phone_val and matched) else clean_phone_lt(df.at[idx, 'SDT'])
            }

            # Incremental auto-save every 5 companies
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cnt = save_and_reorder(df)
                print(f"[*] Checkpoint saved ({processed}/{len(pending_indices)} processed, {cnt} total emails, +{newly_found} new)")

        # Final Save
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_cnt = save_and_reorder(df)

        print("\n" + "=" * 80)
        print("  GOOGLE MAPS ENRICHMENT COMPLETED SUCCESSFULLY!")
        print(f"  Total companies in master dataset : {len(df)}")
        print(f"  Final emails with clean data      : {final_cnt} / {len(df)} ({(final_cnt/len(df))*100:.1f}%)")
        print(f"  Newly discovered this run         : +{newly_found + direct_found}")
        print("  Outputs delivered:")
        print(f"    1. {OUTPUT_1ENR_PATH} (Full enriched master)")
        print(f"    2. {OUTPUT_2COL_PATH} (Standard 20-col Cold Mail, 100% emails on top)")
        print(f"    3. {OUTPUT_READY_PATH} (Ready cold mail emails)")
        print(f"    4. {OUTPUT_2COL_CSDL} (Synced to csdl_mlt)")
        print("=" * 80)

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Lithuanian Wood & Furniture Enterprises")
    parser.add_argument("--headless", action="store_true", help="Run browser in background (headless mode)")
    parser.add_argument("--limit", type=int, default=None, help="Process maximum N companies for testing/batching")
    parser.add_argument("--start-idx", type=int, default=0, help="Start from specific index")
    parser.add_argument("--skip-phase1", action="store_true", help="Skip direct website crawling and go directly to Google Maps")
    parser.add_argument("--phase1-only", action="store_true", help="Only run fast direct website crawling, then exit")
    parser.add_argument("--re-export", action="store_true", help="Re-generate CSV files without running scraper")
    args = parser.parse_args()

    if args.re_export:
        print("[*] Re-exporting standard CSV files...")
        target_read_path = OUTPUT_1ENR_PATH if OUTPUT_1ENR_PATH.exists() else INPUT_CSV_PATH
        df = pd.read_csv(target_read_path, encoding='utf-8-sig', dtype=str).fillna('')
        cnt = save_and_reorder(df)
        print(f"[+] Successfully exported! Total companies with email: {cnt} / {len(df)}")
        return

    asyncio.run(run_enrichment(
        headless=args.headless,
        limit=args.limit,
        start_idx=args.start_idx,
        skip_phase1=args.skip_phase1,
        phase1_only=args.phase1_only
    ))


if __name__ == '__main__':
    main()
