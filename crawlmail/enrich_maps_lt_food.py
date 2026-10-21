# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN FOOD PROCESSING ENTERPRISES (LT_FOOD_WEBD)
Built strictly adhering to:
- Skill enrich-maps & Skill data-standards (Strict Name Matching, headless=False, incremental save)
- Skill crawl-mail (Priority 10 DOM menu, Cloudflare XOR decode, B2B email scoring)
- 100% Aggregator & Junk Email Filtering (Blacklisting all Lithuanian directory/yellowpage portals)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2: Phone numbers with leading single quote (')
- Rule 3: 1 Best B2B email only, 100% emails sorted to the top
- Rule 10: 17-character fixed filename convention (LT_FOOD_WEBD_1ENR.csv / LT_FOOD_WEBD_2COL.csv)
"""

import asyncio
import os
import sys
import re
import ssl
import json
import argparse
import urllib.parse
import urllib.request
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Reconfigure stdout for UTF-8 in Windows Terminal
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT_DIR, "LT_FOOD_WEBD_1ENR.csv")
CSV_CSDL_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_FOOD_WEBD_1ENR.csv")
COLDMAIL_CSV_PATH = os.path.join(ROOT_DIR, "LT_FOOD_WEBD_2COL.csv")
COLDMAIL_CSDL_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_FOOD_WEBD_2COL.csv")
CACHE_PATH = os.path.join(ROOT_DIR, "crawlmail", "cache_enrich_maps_lt_food.json")

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
    'cvmarket.lt', 'rekv.lt', 'proton.me', 'lovejob.lt'
]

# Danh sách công ty loại trừ vĩnh viễn khỏi danh sách kết nối
EXCLUDED_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
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

LT_PRIORITY_KEYWORDS = [
    'kontaktai', 'kontakt', 'apie', 'karjera', 'darbas', 'rekvizitai',
    'susisiekite', 'administracija', 'prekyba', 'pardavimai',
    'contact', 'contacts', 'about', 'career', 'careers', 'jobs', 'team'
]

LT_SECONDARY_KEYWORDS = [
    'paslaugos', 'produktai', 'gamyba', 'partneriai', 'services', 'products'
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
    """Clean common artifacts from email text (e.g. trailing phone labels)."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = email_str.replace('%20', '').strip().lower()
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching per skill enrich-maps taking into account Lithuanian legal forms."""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q = re.sub(r'["\'„“”«»]', '', str(query_name)).strip().lower()
    c = re.sub(r'["\'„“”«»]', '', str(candidate_name)).strip().lower()
    
    # Strip legal forms
    legal_forms = [
        'uab', 'mb', 'ab', 'iį', 'všį', 'žūb', 'kb', 'tūb', 'kūb',
        'uždaroji akcinė bendrovė', 'mažoji bendrija', 'akcinė bendrovė',
        'žemės ūkio bendrovė', 'kooperatyvas', 'firminė parduotuvė', 'skerdykla',
        'cechas', 'sandėlis', 'parduotuvė', 'filialas'
    ]
    for lf in legal_forms:
        q = re.sub(rf'\b{re.escape(lf)}\b', '', q).strip()
        c = re.sub(rf'\b{re.escape(lf)}\b', '', c).strip()
        
    q = re.sub(r'\s+', ' ', q).strip(' ,.-')
    c = re.sub(r'\s+', ' ', c).strip(' ,.-')
    
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    if q == c_nobrackets:
        return True, "BRACKET_MATCH"
        
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c) if p.strip()]
    if any(p == q for p in parts):
        return True, "DELIMITER_MATCH"
        
    if len(q) >= 6 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    return False, "NO_MATCH"


def score_email_b2b(email, domain=""):
    """Score email specifically for B2B Food Processing enterprises."""
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
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'prekyba', 'pardavimai', 'valdyba', 'savininkas']:
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
        r = c_requests.get(url, impersonate='chrome120', timeout=6, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
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
        # Check mailto
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = clean_extracted_email(m)
            if '@' in clean_m:
                found.add(clean_m)
        # Check cloudflare
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = clean_extracted_email(decode_cf(cf))
            if '@' in dec:
                found.add(dec)
        # Check direct regex
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


def save_and_reorder(df):
    """Save progress and generate standard 2COL Cold Mail CSV."""
    df_out = df.copy()
    if 'Công ty' in df_out.columns:
        df_out = df_out[
            ~df_out['Công ty'].astype(str).str.lower().apply(
                lambda c: any(ex in unicodedata.normalize('NFKD', str(c)).lower() for ex in EXCLUDED_COMPANIES)
            )
        ].reset_index(drop=True)

    df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_lt)

    # Separate with email and without email (100% emails on top)
    has_em = df_out[df_out['Email'] != '']
    no_em = df_out[df_out['Email'] == '']
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Write 1ENR
    df_sorted.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    os.makedirs(os.path.dirname(CSV_CSDL_PATH), exist_ok=True)
    df_sorted.to_csv(CSV_CSDL_PATH, index=False, encoding='utf-8-sig')

    # Write 2COL Cold Mail CSV
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
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
            'Category': r.get('Category', 'Mėsa, Žuvis, Pienas')
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(COLDMAIL_CSV_PATH, index=False, encoding='utf-8-sig')
    df_2col.to_csv(COLDMAIL_CSDL_PATH, index=False, encoding='utf-8-sig')
    return len(has_em)


async def run_enrichment(headless=False):
    print("=" * 80)
    print("  GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN FOOD PROCESSING (STRICT MATCH)")
    print(f"  Target File : {CSV_PATH}")
    print(f"  Cold Mail   : {COLDMAIL_CSV_PATH}")
    print(f"  Cache File  : {CACHE_PATH}")
    print(f"  View Mode   : {'HEADLESS (Background)' if headless else 'VISUAL (Headless=False)'}")
    print("=" * 80 + "\n")

    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] Target file '{CSV_PATH}' not found!")
        return

    df = pd.read_csv(CSV_PATH, encoding='utf-8-sig', dtype=str).fillna('')
    for col in ['Web', 'Email', 'SĐT']:
        if col not in df.columns:
            df[col] = ''

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache)} cached company profiles from {CACHE_PATH}.")
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Build memory map of known valid emails
    for idx, row in df.iterrows():
        comp = str(row['Công ty']).strip()
        city = str(row['Thành phố']).strip()
        ico = str(row.get('IČO', '')).strip()
        cache_key = ico if ico else f"{comp}::{city}".lower()
        em = str(row['Email']).strip()
        if em and not any(bad in em.lower() for bad in BLACKLIST_DOMAINS):
            cache[cache_key] = {
                'Web': str(row['Web']).strip(),
                'Email': em,
                'SĐT': str(row['SĐT']).strip()
            }

    # Find rows needing enrichment
    pending_indices = []
    for idx, row in df.iterrows():
        em = str(row['Email']).strip()
        if not em:
            pending_indices.append(idx)

    print(f"[*] Total companies: {len(df)} | Already have Email: {len(df) - len(pending_indices)} | Needing Maps: {len(pending_indices)}")

    if not pending_indices:
        print("[+] All companies already have emails!")
        save_and_reorder(df)
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

        for idx in pending_indices:
            row = df.loc[idx]
            comp = str(row['Công ty']).strip()
            city = str(row['Thành phố']).strip()
            ico = str(row.get('IČO', '')).strip()
            cache_key = ico if ico else f"{comp}::{city}".lower()

            processed += 1

            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, 'Email'] = c['Email']
                if c.get('Web') and not df.at[idx, 'Web']:
                    df.at[idx, 'Web'] = c['Web']
                if c.get('SĐT') and not df.at[idx, 'SĐT']:
                    df.at[idx, 'SĐT'] = c['SĐT']
                continue

            # Query Google Maps
            q = f"{comp} {city} Lietuva".strip() if city else f"{comp} Lietuva".strip()
            url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q)}"
            web_url = None
            phone_val = None
            matched = False

            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                await page.wait_for_timeout(2000)

                if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                    print("\n\a[WARNING] Google Captcha detected! Please solve it on browser window...\n")
                    await page.wait_for_timeout(10000)

                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    for item in items[:3]:
                        aria_label = await item.get_attribute('aria-label') or ""
                        is_ok, _ = is_valid_name_match(comp, aria_label)
                        if is_ok:
                            await item.click()
                            await page.wait_for_timeout(2000)
                            matched = True
                            break
                else:
                    title_elem = await page.query_selector('h1.DUwDvf')
                    if title_elem:
                        t_text = await title_elem.inner_text()
                        is_ok, _ = is_valid_name_match(comp, t_text)
                        matched = is_ok

                if matched:
                    web_btn = await page.query_selector('a[data-item-id="authority"]')
                    if web_btn:
                        cand_web = await web_btn.get_attribute('href')
                        if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                            web_url = cand_web

                    phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id')
                        if p_attr and p_attr.startswith('phone:tel:'):
                            phone_val = p_attr.replace('phone:tel:', '').strip()
            except Exception:
                pass

            email = ""
            if web_url and matched:
                email = crawl_site_for_emails(web_url)

            if web_url and matched and not df.at[idx, 'Web']:
                df.at[idx, 'Web'] = web_url
            if email:
                df.at[idx, 'Email'] = email
                newly_found += 1
                print(f"[{processed}/{len(pending_indices)}] [+] NEW EMAIL: {comp} -> {email} ({web_url})")
            elif matched and web_url:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED WEB: {comp} -> {web_url} (No direct email)")
            elif matched and phone_val:
                print(f"[{processed}/{len(pending_indices)}] [~] MATCHED PHONE: {comp} -> {phone_val}")

            if phone_val and matched and not df.at[idx, 'SĐT']:
                df.at[idx, 'SĐT'] = clean_phone_lt(phone_val)

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
                cnt = save_and_reorder(df)
                print(f"[*] Checkpoint saved ({processed}/{len(pending_indices)} processed, {cnt} total valid emails, +{newly_found} new)")

        # Final Save
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_cnt = save_and_reorder(df)

        print("\n" + "=" * 80)
        print("  GOOGLE MAPS ENRICHMENT COMPLETED SUCCESSFULLY!")
        print(f"  Total companies: {len(df)}")
        print(f"  Final emails with clean data: {final_cnt} / {len(df)} ({(final_cnt/len(df))*100:.1f}%)")
        print(f"  Newly discovered: +{newly_found}")
        print("  Files saved:")
        print(f"    - {CSV_PATH}")
        print(f"    - {COLDMAIL_CSV_PATH}")
        print("=" * 80)

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for Lithuanian Food Processing Enterprises")
    parser.add_argument("--headless", action="store_true", help="Run browser in background (headless mode)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless))


if __name__ == '__main__':
    main()
