# -*- coding: utf-8 -*-
"""
CRAWL MAIL DEEP CRAWLER - LITHUANIAN FOOD PROCESSING (LT_FOOD_WEBD)
Built strictly adhering to:
- Skill crawl-mail & Skill data-standards (Priority 10 DOM menu, Baltic Subpaths, CF decode, B2B email scoring)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY
- Rule 2: Phone numbers with leading single quote (')
- Rule 3: 1 Best B2B email only, 100% emails sorted to the top
- Rule 8: Windows batch runner compatible
- Rule 10: 17-character fixed filename convention (LT_FOOD_WEBD_1ENR.csv / LT_FOOD_WEBD_2COL.csv)
"""

import os
import sys
import re
import json
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

# Reconfigure stdout for UTF-8 in Windows Terminal
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_1ENR_PATH = os.path.join(ROOT_DIR, "LT_FOOD_WEBD_1ENR.csv")
CSV_2COL_PATH = os.path.join(ROOT_DIR, "LT_FOOD_WEBD_2COL.csv")
CSDL_1ENR_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_FOOD_WEBD_1ENR.csv")
CSDL_2COL_PATH = os.path.join(ROOT_DIR, "csdl_mlt", "LT_FOOD_WEBD_2COL.csv")
CACHE_PATH = os.path.join(ROOT_DIR, "crawlmail", "cache_crawl_mail_lt_food.json")

# Strict Email Regex with boundary protection
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Obfuscated Patterns (e.g. info [at] domain [dot] lt)
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})'),
]

# Blacklisted directory/aggregator domains that are not company official websites
AGGREGATOR_DOMAINS = {
    'statyba.lt', 'info.lt', 'visalietuva.lt', 'imones.lt', 'rekvizitai.vz.lt', 'rekvizitai.lt',
    'b2lithuania.com', 'duckduckgo.com', 'google.com', 'maps.google.com',
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'cvbankas.lt', 'cvonline.lt', 'wikipedia.org', 'delfi.lt', '15min.lt', 'lrt.lt',
    'okredo.com', 'scamvn.com', 'yellowpages', 'sentry.io', 'wixpress.com',
    'scoris.lt', 'infoin.lt', 'cr.lt', 'creditinfo.lt', 'verslas.lt', 'madeinvilnius.lt',
    'lrytas.lt', 'alfa.lt', 'tv3.lt', 'registrucentras.lt', 'vmi.lt', 'sodra.lt',
    '1551.lt', 'tax.lt', 'buhalteredaiva.lt', 'geltoni.lt', 'fsaskaita.lt', 'jars.lt',
    'spec.lt', 'saskaitos.lt', 'balticlei.lt'
}

# Junk / Fake / Template Domains
JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'schema.org', 'trustpilot.com', 'google.com', 'facebook.com',
    'instagram.com', 'twitter.com', 'tiktok.com', 'youtube.com', 'linkedin.com',
    'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com',
    'yourcompany.com', 'your-domain.com', 'your-site.com', 'mydomain.com',
    'mycompany.com', 'company.com', 'website.com', 'site.com', 'placeholder.com',
    'sample.com', 'demo.com', 'templatemonster.com', 'themeforest.net', 'envato.com',
    'colorlib.com', 'bootstrapmade.com', 'htmlstream.com', 'nicepage.com', 'mobirise.com',
    'pavyzdys.lt', 'imone.lt', 'email.com', 'mail.com', 'email.lt', 'pastas.lt', 'domain.lt',
    'scoris.lt', 'infoin.lt', '1551.lt', 'tax.lt', 'buhalteredaiva.lt', 'geltoni.lt',
    'fsaskaita.lt', 'jars.lt', 'spec.lt', 'saskaitos.lt', 'balticlei.lt'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'hostmaster', 'postmaster', 'root', 'dataprivacy', 'datenschutz'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname',
    'username', 'user', 'name', 'sample', 'demo', 'test', 'testing',
    'placeholder', 'someone', 'nobody', 'john.doe', 'johndoe', 'jane.doe', 'janedoe',
    'jusu', 'tavo', 'vardas', 'pavarde', 'jusu-vardas', 'jusu.vardas', 'el.pastas', 'pastas', 'pavyzdys'
}

# Lithuanian Priority Keywords & Subpaths
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

cache_lock = Lock()
file_save_lock = Lock()


def decode_cloudflare_email(cf_hex):
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
    """Clean common artifacts from email text (e.g. trailing Tel, Mob, punctuation)."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = email_str.replace('%20', '').strip().lower()
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    # Strip accidental trailing labels attached to TLD
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def score_email_b2b(email, domain=""):
    """
    Score email specifically for B2B Manpower / Food Processing enterprises.
    Returns -1 for invalid/junk, or a positive integer score.
    """
    if not email or not isinstance(email, str):
        return -1
    e = clean_extracted_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    
    u, d = e.split('@', 1)
    
    # 1. Filter out junk domains and system/template users
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if any(agg in d for agg in AGGREGATOR_DOMAINS):
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
    
    # Domain match bonus (+50)
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
    elif d in ['gmail.com', 'inbox.lt', 'one.lt', 'mail.ru']:
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


def fetch_html_stealth(url, timeout=6):
    """Fetch URL using curl_cffi Chrome120 TLS impersonation."""
    try:
        r = requests.get(
            url,
            impersonate='chrome120',
            timeout=timeout,
            verify=False,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept-Language': 'lt,en-US;q=0.9,en;q=0.8'
            }
        )
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def extract_emails_from_html(html_text):
    """Multi-source email extraction per skill crawl-mail."""
    if not html_text:
        return set()
    found = set()
    soup = BeautifulSoup(html_text, 'html.parser')

    # 1. Cloudflare XOR emails
    for tag in soup.find_all(attrs={'data-cfemail': True}):
        dec = decode_cloudflare_email(tag['data-cfemail'])
        if dec:
            found.add(dec)

    # 2. mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().startswith('mailto:'):
            raw_mail = href[7:].split('?')[0].strip()
            if raw_mail:
                found.add(raw_mail)

    # 3. Obfuscated patterns
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(html_text):
            found.add(f"{match[0]}@{match[1]}.{match[2]}")

    # 4. Standard text & raw HTML regex
    raw_matches = EMAIL_REGEX.findall(html_text)
    for m in raw_matches:
        cleaned = clean_extracted_email(m)
        if cleaned:
            found.add(cleaned)

    return found


def extract_priority_links(base_url, html_text):
    """Extract and prioritize subpage links matching Lithuanian keywords (Priority 10)."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, 'html.parser')
    parsed_base = urllib.parse.urlparse(base_url)
    base_netloc = parsed_base.netloc.lower().replace('www.', '')

    p10_links = []
    p5_links = []
    seen = {base_url.rstrip('/')}

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        text = a.get_text().strip().lower()
        if not href or href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
            continue
        full_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full_url)
        netloc = parsed.netloc.lower().replace('www.', '')

        # Stay on the same domain
        if netloc != base_netloc:
            continue

        clean_sub = full_url.split('#')[0].rstrip('/')
        if clean_sub in seen:
            continue
        seen.add(clean_sub)

        path_and_text = (parsed.path + ' ' + text).lower()
        if any(k in path_and_text for k in LT_PRIORITY_KEYWORDS):
            p10_links.append(clean_sub)
        elif any(k in path_and_text for k in LT_SECONDARY_KEYWORDS):
            p5_links.append(clean_sub)

    # Fallback to candidate guess paths if very few priority links found
    guess_links = []
    if len(p10_links) < 2:
        for gp in LT_GUESS_SUBPATHS:
            g_url = urllib.parse.urljoin(base_url, gp).rstrip('/')
            if g_url not in seen:
                guess_links.append(g_url)
                seen.add(g_url)

    # Return ordered list: Priority 10 -> Priority 5 -> Guess Paths
    return (p10_links + p5_links + guess_links)[:8]


def discover_website_via_search(company_name, city=""):
    """
    Intelligent DuckDuckGo search fallback for companies without website.
    Discovers the true official domain of the Lithuanian food enterprise.
    """
    clean_name = re.sub(r'["\'„“”«»]', '', company_name).strip()
    query = f'{clean_name} {city} Lietuva maistas'.strip()
    url = f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}'
    
    html = fetch_html_stealth(url, timeout=6)
    if not html:
        return ""

    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.select('.result__url'):
        raw_url = a.get_text().strip()
        if not raw_url.startswith('http'):
            raw_url = 'https://' + raw_url
        parsed = urllib.parse.urlparse(raw_url)
        domain = parsed.netloc.lower().replace('www.', '')
        
        # Check against aggregator blacklist
        if not any(agg in domain for agg in AGGREGATOR_DOMAINS) and '.' in domain:
            # Valid domain found
            return f"https://{domain}"
            
    return ""


def crawl_company_website_deep(website_url):
    """
    Deep crawl a company's website following skill crawl-mail:
    1. Pre-check root domain (fail-fast if dead).
    2. Extract emails on homepage.
    3. Extract Priority 10 menu links and visit up to 8 subpages.
    4. Return best email and list of all valid emails found.
    """
    if not website_url or not isinstance(website_url, str):
        return "", []

    url = website_url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    if any(agg in domain for agg in AGGREGATOR_DOMAINS):
        return "", []

    # Pre-check homepage
    home_html = fetch_html_stealth(url, timeout=6)
    if not home_html:
        # Retry with http if https failed
        if url.startswith('https://'):
            alt_url = 'http://' + url[8:]
            home_html = fetch_html_stealth(alt_url, timeout=6)
            if home_html:
                url = alt_url

    if not home_html:
        return "", []

    all_emails = extract_emails_from_html(home_html)
    best_mail = select_best_email(all_emails, domain)
    # If high quality HR or executive or official domain email found on homepage, stop early
    if best_mail and score_email_b2b(best_mail, domain) >= 80:
        return best_mail, list(all_emails)

    # Priority 10 link traversal
    sub_urls = extract_priority_links(url, home_html)
    for sub in sub_urls:
        sub_html = fetch_html_stealth(sub, timeout=5)
        if sub_html:
            sub_emails = extract_emails_from_html(sub_html)
            all_emails.update(sub_emails)
            current_best = select_best_email(all_emails, domain)
            if current_best and score_email_b2b(current_best, domain) >= 80:
                best_mail = current_best
                break

    best_mail = select_best_email(all_emails, domain)
    return best_mail, list(all_emails)


def process_single_company(row, cache):
    """Worker function for multithreaded processing of a single company."""
    name = row.get('Công ty', '').strip()
    city = row.get('Thành phố', '').strip()
    ico = row.get('IČO', '').strip()
    web = row.get('Web', '').strip()
    current_email = row.get('Email', '').strip()

    # Clean bogus directory websites like statyba.lt
    clean_web = web
    if clean_web:
        parsed_web = urllib.parse.urlparse(clean_web)
        domain_web = parsed_web.netloc.lower().replace('www.', '')
        if any(agg in domain_web for agg in AGGREGATOR_DOMAINS):
            clean_web = ""

    # Check cache first
    cache_key = f"{ico}_{name}" if ico else name
    with cache_lock:
        if cache_key in cache:
            cached_entry = cache[cache_key]
            c_email = cached_entry.get('email', '')
            c_web = cached_entry.get('web', clean_web)
            if c_email and score_email_b2b(c_email, c_web) > 0:
                return {
                    'row_index': row.name,
                    'email': c_email,
                    'web': c_web,
                    'status': 'CACHED'
                }

    # If already has valid email and website is clean
    if current_email and score_email_b2b(current_email, clean_web) > 0:
        res = {
            'row_index': row.name,
            'email': clean_extracted_email(current_email),
            'web': clean_web,
            'status': 'EXISTING_VALID'
        }
        with cache_lock:
            cache[cache_key] = {'email': res['email'], 'web': res['web']}
        return res

    final_email = ""
    discovered_web = clean_web

    # If no website, attempt intelligent discovery
    if not discovered_web:
        discovered_web = discover_website_via_search(name, city)

    # Perform deep crawl if website exists
    if discovered_web:
        best_email, all_found = crawl_company_website_deep(discovered_web)
        if best_email:
            final_email = best_email

    res = {
        'row_index': row.name,
        'email': final_email,
        'web': discovered_web,
        'status': 'CRAWLED_SUCCESS' if final_email else 'NO_EMAIL_FOUND'
    }

    with cache_lock:
        cache[cache_key] = {'email': final_email, 'web': discovered_web}

    return res


def save_checkpoint(df, cache):
    """Save progress incrementally to cache and both 1ENR and 2COL CSV files."""
    with file_save_lock:
        # Save cache JSON with thread-safe snapshot
        with cache_lock:
            cache_snapshot = dict(cache)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache_snapshot, f, ensure_ascii=False, indent=2)

        # 1. Update 1ENR DataFrame
        df_out = df.copy()
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_lt)

        # Separate with email and without email (100% emails on top)
        with_email = df_out[df_out['Email'] != '']
        without_email = df_out[df_out['Email'] == '']
        merged_1enr = pd.concat([with_email, without_email], ignore_index=True)
        merged_1enr['No.'] = range(1, len(merged_1enr) + 1)

        # Write 1ENR
        merged_1enr.to_csv(CSV_1ENR_PATH, index=False, encoding='utf-8-sig')
        os.makedirs(os.path.dirname(CSDL_1ENR_PATH), exist_ok=True)
        merged_1enr.to_csv(CSDL_1ENR_PATH, index=False, encoding='utf-8-sig')

        # 2. Generate 2COL Cold Mail CSV (Standard 20 columns)
        coldmail_rows = []
        for _, r in merged_1enr.iterrows():
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
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': '',
                'Lần Follow-up': '',
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': r.get('Category', 'Mėsa, Žuvis, Pienas')
            })

        df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
        df_2col.to_csv(CSV_2COL_PATH, index=False, encoding='utf-8-sig')
        df_2col.to_csv(CSDL_2COL_PATH, index=False, encoding='utf-8-sig')


def main():
    print("=" * 75)
    print("  DEEP EMAIL CRAWLER - LITHUANIAN FOOD PROCESSING ENTERPRISES")
    print(f"  Target: {CSV_1ENR_PATH}")
    print(f"  Standard 20-col Cold Mail: {CSV_2COL_PATH}")
    print("=" * 75)

    if not os.path.exists(CSV_1ENR_PATH):
        print(f"[ERROR] Target file {CSV_1ENR_PATH} does not exist!")
        sys.exit(1)

    df = pd.read_csv(CSV_1ENR_PATH, dtype=str).fillna('')
    total_rows = len(df)
    initial_email_count = len(df[df['Email'] != ''])
    print(f"[*] Loaded dataset: {total_rows} companies ({initial_email_count} already have Email).")

    # Load cache
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                raw_cache = json.load(f)
            # Filter out invalid entries from cache
            for k, v in raw_cache.items():
                em = v.get('email', '')
                wb = v.get('web', '')
                if em and score_email_b2b(em, wb) > 0:
                    cache[k] = v
                elif not em and wb and not any(agg in wb for agg in AGGREGATOR_DOMAINS):
                    cache[k] = v
            print(f"[*] Loaded {len(cache)} validated cached company profiles.")
        except Exception as e:
            print(f"[!] Warning reading cache: {e}")

    # Determine companies to process
    rows_to_process = []
    for idx, row in df.iterrows():
        name = row['Công ty'].strip()
        ico = row['IČO'].strip()
        email = row['Email'].strip()
        web = row['Web'].strip()
        cache_key = f"{ico}_{name}" if ico else name

        # If already cached, apply immediately
        if cache_key in cache:
            cached_data = cache[cache_key]
            if cached_data.get('email'):
                df.at[idx, 'Email'] = cached_data['email']
            if cached_data.get('web'):
                df.at[idx, 'Web'] = cached_data['web']
        elif not email or any(agg in web.lower() for agg in AGGREGATOR_DOMAINS):
            rows_to_process.append(row)

    print(f"[*] Companies pending deep crawling / enrichment: {len(rows_to_process)}")

    if not rows_to_process:
        print("[+] All companies already have emails or are fully cached!")
        save_checkpoint(df, cache)
        print("[+] Cold Mail 20-column files successfully regenerated.")
        return

    # Multithreaded execution with ThreadPoolExecutor
    MAX_WORKERS = 8
    print(f"[*] Starting {MAX_WORKERS} concurrent worker threads...")
    completed_count = 0
    newly_found_count = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_company, row, cache): row for row in rows_to_process}

        for future in as_completed(futures):
            res = future.result()
            completed_count += 1
            idx = res['row_index']

            if res['email']:
                if not df.at[idx, 'Email']:
                    newly_found_count += 1
                    print(f"[{completed_count}/{len(rows_to_process)}] [+] NEW EMAIL: {df.at[idx, 'Công ty']} -> {res['email']} ({res['web']})")
                df.at[idx, 'Email'] = res['email']

            if res['web']:
                df.at[idx, 'Web'] = res['web']

            # Incremental checkpoint save every 10 companies
            if completed_count % 10 == 0:
                save_checkpoint(df, cache)
                elapsed = time.time() - start_time
                speed = completed_count / elapsed if elapsed > 0 else 0
                print(f"[*] Checkpoint saved ({completed_count}/{len(rows_to_process)} done, +{newly_found_count} new emails, {speed:.1f} comp/sec)")

    # Final Save
    save_checkpoint(df, cache)
    final_email_count = len(df[df['Email'] != ''])
    print("=" * 75)
    print(f"  CRAWL & ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f"  Total Companies: {total_rows}")
    print(f"  Companies with Email: {final_email_count} / {total_rows} ({(final_email_count/total_rows)*100:.1f}%)")
    print(f"  Newly Discovered Emails: +{newly_found_count}")
    print(f"  Files saved:")
    print(f"    - {CSV_1ENR_PATH}")
    print(f"    - {CSV_2COL_PATH}")
    print("=" * 75)


if __name__ == '__main__':
    main()
