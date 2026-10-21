# -*- coding: utf-8 -*-
"""
DEEP MULTI-TIER DATA ENRICHMENT - CROATIAN EMPLOYMENT AGENCIES (HR_AGCY_MROS)
Pipeline:
1. Load HR_AGCY_MROS_0RAW.csv / HR_AGCY_1ENR.csv (757 licensed agencies from MROSP Croatia)
2. Tier 1 - Croatian Corporate Registry (CompanyWall.hr & FINA data):
   - Extract 11-digit OIB (Mã số thuế Croatia)
   - Extract Director / Authorized Representative (Direktor / Vlasnik)
   - Extract Financial / Account status (Nije u blokadi / Aktivan)
   - Extract Official Telephone & Direct Email
   - Extract Official Website link
3. Tier 2 - Official Website Deep Crawl (crawl-mail compliant):
   - Priority 10 DOM menu navigation (kontakt, o-nama, posao, karijera, zaposljavanje, crewing)
   - Cloudflare data-cfemail XOR decode, mailto extraction, obfuscation decode
   - B2B email scoring (+50 for HR/Recruitment: posao@, karijera@, hr@, zaposljavanje@)
   - Single best email selection
4. Standard Formatter & Checkpoint Engine:
   - Incremental saving every 10 companies to cache and CSV
   - Exports HR_AGCY_MROS_1ENR.csv
   - Exports HR_AGCY_MROS_2COL.csv (Standard 20 cols, 100% emails sorted on top, phone with leading ')
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

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_0RAW_PATH = os.path.join(ROOT_DIR, "HR_AGCY_MROS_0RAW.csv")
EXISTING_1ENR_PATH = os.path.join(ROOT_DIR, "HR_AGCY_1ENR.csv")
OUTPUT_1ENR_PATH = os.path.join(ROOT_DIR, "HR_AGCY_MROS_1ENR.csv")
OUTPUT_2COL_PATH = os.path.join(ROOT_DIR, "HR_AGCY_MROS_2COL.csv")
CACHE_PATH = os.path.join(ROOT_DIR, "crawlmail", "cache_hr_agcy_croatia_deep.json")

# Strict Email Regex with boundary protection
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

# Obfuscated Patterns (e.g. info [at] domain [dot] hr)
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})'),
]

# Blacklisted directory/aggregator domains that are not company official websites
AGGREGATOR_DOMAINS = {
    'zagreb.place',
    'poslovnenovine.ba',
    'tvojioglasi.hr',
    'moja-djelatnost.hr',
    'freelance.hr',
    'bon.hr',
    'mmpi.hr',
    'hgk.hr',
    'hup.hr',
    'euroestate-nekretnine.hr',
    'omnis-nekretnine.com',
    'ombudsman.hr',
    'notar-maroslavac.hr',
    'company.hr',
    'reputacija.hr',
    'infobiz.fina.hr',
    'fina.hr',
    'companywall.hr', 'fininfo.hr', 'poslovna.hr', 'mojatvrtka.net', 'tvrtke.hr',
    'crobiz.net', 'provjera.hr', 'imenik.eu', 'tvrtko.ai', 'dnb.com', 'bika.net',
    'mojposao.net', 'posao.hr', 'danasradim.hr', 'hzz.hr', 'adzuna', 'jooble',
    'indeed', 'glassdoor', 'facebook.com', 'instagram.com', 'linkedin.com',
    'youtube.com', 'twitter.com', 'x.com', 'duckduckgo.com', 'google.com',
    'maps.google.com', 'wikipedia.org', 'sentry.io', 'wixpress.com'
}

# Junk / Fake / Template Domains
JUNK_EMAIL_DOMAINS = {
    'zagreb.place',
    'poslovnenovine.ba',
    'tvojioglasi.hr',
    'moja-djelatnost.hr',
    'freelance.hr',
    'bon.hr',
    'mmpi.hr',
    'hgk.hr',
    'hup.hr',
    'euroestate-nekretnine.hr',
    'omnis-nekretnine.com',
    'ombudsman.hr',
    'notar-maroslavac.hr',
    'company.hr',
    'reputacija.hr',
    'infobiz.fina.hr',
    'fina.hr',
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'schema.org', 'trustpilot.com', 'google.com', 'facebook.com',
    'instagram.com', 'twitter.com', 'tiktok.com', 'youtube.com', 'linkedin.com',
    'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com',
    'yourcompany.com', 'your-domain.com', 'your-site.com', 'mydomain.com',
    'mycompany.com', 'company.com', 'website.com', 'site.com', 'placeholder.com',
    'sample.com', 'demo.com', 'companywall.hr', 'fininfo.hr', 'email.com', 'mail.com'
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
    'placeholder', 'someone', 'nobody', 'john.doe', 'johndoe', 'jane.doe', 'janedoe'
}

# Croatian Priority Keywords & Subpaths for crawl-mail
HR_PRIORITY_KEYWORDS = [
    'kontakt', 'kontakti', 'o-nama', 'onama', 'posao', 'karijera',
    'zaposljavanje', 'crewing', 'radnici', 'agencija', 'uprava',
    'contact', 'contacts', 'about', 'career', 'careers', 'jobs', 'team'
]

HR_SECONDARY_KEYWORDS = [
    'usluge', 'posredovanje', 'projekti', 'partneri', 'services', 'about-us'
]

HR_GUESS_SUBPATHS = [
    '/kontakt', '/kontakt.html', '/kontakt.php',
    '/o-nama', '/o-nama.html', '/onama',
    '/posao', '/posao.html', '/karijera', '/karijera.html',
    '/zaposljavanje', '/crewing', '/contact', '/about'
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


def clean_phone_hr(phone_str):
    """Normalize Croatian phone number with leading single quote."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
    p = str(phone_str).strip().lstrip("'")
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('385'):
        return f"'+{digits}"
    elif digits.startswith('0') and len(digits) >= 8:
        # e.g. 01 4633885 -> '+38514633885 or '+385...
        return f"'+385{digits[1:]}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"


def clean_extracted_email(email_str):
    """Clean common artifacts from email text (e.g. trailing punctuation)."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = email_str.replace('%20', '').strip().lower()
    e = re.sub(r'^[<("{\[]+|[>)"}\],;:]+$', '', e)
    for suffix in ['tel', 'mob', 'fax', 'phone', 'el']:
        if e.endswith(suffix) and len(e.split('@')[-1].split('.')[-1]) > 5:
            e = e[:-len(suffix)]
    return e.strip()


def score_email_b2b(email, domain=""):
    """
    Score email specifically for B2B Employment Agencies in Croatia.
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
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'sample', 'placeholder']):
        return -1
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    
    # Domain match bonus (+50)
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.hr'):
        score += 25

    # Priority 1: HR / Recruitment / Crewing (+50)
    if u in ['posao', 'karijera', 'hr', 'zaposljavanje', 'crewing', 'recruitment', 'jobs', 'career', 'careers', 'ljudski.resursi']:
        score += 50
    # Priority 2: Executive / Management (+45)
    elif u in ['direktor', 'uprava', 'ceo', 'director', 'manager', 'voditelj', 'poslovanje', 'tajnik', 'vlasnik']:
        score += 45
    # Priority 3: Official portal (+40)
    elif u in ['info', 'kontakt', 'office', 'ured', 'agencija', 'prijava', 'administracija']:
        score += 40
    # Named employee on official domain (+25)
    elif '.' in u and score >= 60:
        score += 25
    # Free webmail (+10)
    elif d in ['gmail.com', 'net.hr', 't-com.hr', 'optinet.hr', 'yahoo.com']:
        score += 10
    # Technical / Accounting (+5)
    elif u in ['support', 'admin', 'racunovodstvo', 'it']:
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
                'Accept-Language': 'hr,en-US;q=0.9,en;q=0.8'
            }
        )
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def search_companywall_profile(brand, city):
    """Search CompanyWall Croatia profile using DuckDuckGo HTML."""
    query = f'{brand} {city} companywall.hr'.strip()
    url = f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}'
    html = fetch_html_stealth(url, timeout=6)
    if not html:
        return ""
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.select('.result__url'):
        txt = a.get_text().strip()
        if 'companywall.hr/tvrtka/' in txt:
            full_url = txt if txt.startswith('http') else 'https://' + txt
            return full_url
    return ""


def parse_companywall_page(cw_url):
    """
    Extract structured official corporate data from CompanyWall.hr:
    - OIB (11 digits)
    - Phone (tel/mob)
    - Email(s)
    - Director / Owner (Direktor / Vlasnik)
    - Account & Financial Status (Aktivan / Nije u blokadi)
    - Address & Postal Code
    """
    html = fetch_html_stealth(cw_url, timeout=6)
    if not html:
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    res = {
        'OIB': '',
        'Phone': '',
        'Email': '',
        'Director': '',
        'Status': 'Aktivan',
        'PostalCode': '',
        'Street': ''
    }

    # 1. Parse JSON-LD Schema.org
    for s in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(s.string)
            if data.get('@type') == 'LocalBusiness':
                if data.get('telephone'):
                    res['Phone'] = clean_phone_hr(data['telephone'])
                addr = data.get('address', {})
                if isinstance(addr, dict):
                    res['PostalCode'] = addr.get('postalCode', '')
                    res['Street'] = addr.get('streetAddress', '')
            elif data.get('@type') == 'Dataset':
                for acc in data.get('bankAccounts', []):
                    if acc.get('Blocked') is False:
                        res['Status'] = 'Aktivan (Nije u blokadi)'
        except Exception:
            pass

    # 2. Parse 11-digit OIB
    oib_matches = re.findall(r'OIB[^\d]*(\d{11})', html)
    if oib_matches:
        res['OIB'] = oib_matches[0]

    # 3. Parse Director / Owner from <dl> <dt>/<dd>
    directors = []
    for dl in soup.find_all('dl'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            lbl = dt.get_text().strip()
            val = dd.get_text().strip()
            if any(k in lbl for k in ['Direktor', 'Vlasnik', 'Član uprave']):
                val_clean = re.sub(r'[\r\n\t]+', ' ', val).strip()
                if val_clean and len(val_clean) > 3 and not any(k in val_clean.lower() for k in ['prikaži', 'opis', 'detalji']):
                    directors.append(val_clean)
    if directors:
        res['Director'] = directors[0]

    # 4. Parse Emails on CompanyWall
    found_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    valid_cw_emails = [e for e in found_emails if not any(agg in e.lower() for agg in AGGREGATOR_DOMAINS)]
    if valid_cw_emails:
        res['Email'] = select_best_email(valid_cw_emails)

    return res


def discover_official_website(brand, city):
    """Discover company's official standalone website via search."""
    clean_brand = re.sub(r'["\'„“”«»]', '', brand).strip()
    query = f'{clean_brand} {city} agencija zapošljavanje Hrvatska'.strip()
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
            return f"https://{domain}"
            
    return ""


def extract_priority_links(base_url, html_text):
    """Extract and prioritize subpage links matching Croatian keywords (Priority 10)."""
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

        if netloc != base_netloc:
            continue

        clean_sub = full_url.split('#')[0].rstrip('/')
        if clean_sub in seen:
            continue
        seen.add(clean_sub)

        path_and_text = (parsed.path + ' ' + text).lower()
        if any(k in path_and_text for k in HR_PRIORITY_KEYWORDS):
            p10_links.append(clean_sub)
        elif any(k in path_and_text for k in HR_SECONDARY_KEYWORDS):
            p5_links.append(clean_sub)

    # Fallback to candidate guess paths
    guess_links = []
    if len(p10_links) < 2:
        for gp in HR_GUESS_SUBPATHS:
            g_url = urllib.parse.urljoin(base_url, gp).rstrip('/')
            if g_url not in seen:
                guess_links.append(g_url)
                seen.add(g_url)

    return (p10_links + p5_links + guess_links)[:8]


def crawl_official_website(website_url):
    """Deep crawl company's official website per skill crawl-mail."""
    if not website_url or not isinstance(website_url, str):
        return "", []

    url = website_url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    if any(agg in domain for agg in AGGREGATOR_DOMAINS):
        return "", []

    home_html = fetch_html_stealth(url, timeout=6)
    if not home_html and url.startswith('https://'):
        alt_url = 'http://' + url[8:]
        home_html = fetch_html_stealth(alt_url, timeout=6)
        if home_html:
            url = alt_url

    if not home_html:
        return "", []

    all_emails = set()
    
    # 1. Cloudflare decode
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
        dec = decode_cloudflare_email(cf)
        if dec:
            all_emails.add(dec)

    # 2. mailto
    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
        c_m = m.split('?')[0].strip()
        if c_m:
            all_emails.add(c_m)

    # 3. Regex
    for em in EMAIL_REGEX.findall(home_html):
        all_emails.add(em)

    best_home = select_best_email(all_emails, domain)
    if best_home and score_email_b2b(best_home, domain) >= 80:
        return best_home, list(all_emails)

    # Subpages Priority 10
    sub_urls = extract_priority_links(url, home_html)
    for sub in sub_urls:
        sub_html = fetch_html_stealth(sub, timeout=5)
        if sub_html:
            for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', sub_html):
                dec = decode_cloudflare_email(cf)
                if dec:
                    all_emails.add(dec)
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', sub_html, re.I):
                c_m = m.split('?')[0].strip()
                if c_m:
                    all_emails.add(c_m)
            for em in EMAIL_REGEX.findall(sub_html):
                all_emails.add(em)
                
            cur_best = select_best_email(all_emails, domain)
            if cur_best and score_email_b2b(cur_best, domain) >= 80:
                best_home = cur_best
                break

    best_home = select_best_email(all_emails, domain)
    return best_home, list(all_emails)


def process_single_agency(row, cache):
    """Enrich a single Croatian agency across all tiers."""
    name = row.get('Công ty', '').strip()
    brand = row.get('Tên thương hiệu', '').strip() or name
    city = row.get('Thành phố', '').strip()
    current_oib = row.get('OIB', '').strip()
    current_phone = row.get('SĐT', '').strip()
    current_email = row.get('Email', '').strip()
    current_web = row.get('Web', '').strip()
    current_director = row.get('Người đại diện', '').strip()
    current_status = row.get('Trạng thái', '').strip()

    cache_key = f"{brand}::{city}".lower()

    # Check cache first
    with cache_lock:
        if cache_key in cache:
            c = cache[cache_key]
            # If cache has valid email and OIB
            if c.get('Email') and c.get('OIB'):
                return {
                    'row_index': row.name,
                    'OIB': c.get('OIB', current_oib),
                    'SĐT': c.get('SĐT', current_phone),
                    'Email': c.get('Email', current_email),
                    'Web': c.get('Web', current_web),
                    'Director': c.get('Director', current_director),
                    'Status': c.get('Status', current_status),
                    'Source': 'CACHE'
                }

    # Step 1: Query CompanyWall for official corporate registry data
    cw_url = search_companywall_profile(brand, city)
    cw_data = parse_companywall_page(cw_url) if cw_url else {}

    final_oib = cw_data.get('OIB') or current_oib
    final_phone = cw_data.get('Phone') or clean_phone_hr(current_phone)
    final_email = cw_data.get('Email') or current_email
    final_director = cw_data.get('Director') or current_director
    final_status = cw_data.get('Status') or current_status or 'Aktivan'
    final_web = current_web

    # Step 2: Discover and deep crawl official website
    if not final_web or any(agg in final_web.lower() for agg in AGGREGATOR_DOMAINS):
        final_web = discover_official_website(brand, city)

    if final_web:
        web_email, _ = crawl_official_website(final_web)
        if web_email:
            # Website email has highest Priority if scored >= current email
            if not final_email or score_email_b2b(web_email, final_web) >= score_email_b2b(final_email, final_web):
                final_email = web_email

    # Clean phone and email
    final_phone = clean_phone_hr(final_phone)
    final_email = clean_extracted_email(final_email)

    res = {
        'row_index': row.name,
        'OIB': final_oib,
        'SĐT': final_phone,
        'Email': final_email,
        'Web': final_web,
        'Director': final_director,
        'Status': final_status,
        'Source': 'ENRICHED'
    }

    with cache_lock:
        cache[cache_key] = {
            'OIB': final_oib,
            'SĐT': final_phone,
            'Email': final_email,
            'Web': final_web,
            'Director': final_director,
            'Status': final_status
        }

    return res


def save_checkpoint(df, cache):
    """Save progress incrementally to cache and both 1ENR and 2COL CSV files."""
    with file_save_lock:
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        df_out = df.copy()
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_hr)

        # Separate with email and without email (100% emails on top)
        with_email = df_out[df_out['Email'] != '']
        without_email = df_out[df_out['Email'] == '']
        merged_1enr = pd.concat([with_email, without_email], ignore_index=True)
        merged_1enr['No.'] = range(1, len(merged_1enr) + 1)

        merged_1enr.to_csv(OUTPUT_1ENR_PATH, index=False, encoding='utf-8-sig')
        # Also sync to EXISTING_1ENR_PATH
        merged_1enr.to_csv(EXISTING_1ENR_PATH, index=False, encoding='utf-8-sig')

        # Generate 2COL Cold Mail CSV (Standard 20 columns)
        coldmail_rows = []
        for _, r in merged_1enr.iterrows():
            coldmail_rows.append({
                'No.': r.get('No.', ''),
                'Công ty': r.get('Công ty', ''),
                'Chức danh': 'Direktor' if r.get('Người đại diện', '') else 'Voditelj',
                'Người liên hệ': r.get('Người đại diện', ''),
                'SĐT': clean_phone_hr(r.get('SĐT', '')),
                'Liên Hệ': r.get('Web', ''),
                'Email': clean_extracted_email(r.get('Email', '')),
                'Liên Hệ mail': r.get('Web', '') or r.get('Source', ''),
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
                'Category': r.get('Category', 'Employment Agency')
            })

        df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
        df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')


def main():
    print("=" * 80)
    print("  DEEP MULTI-TIER DATA ENRICHMENT - CROATIAN EMPLOYMENT AGENCIES")
    print(f"  Source Dataset : {INPUT_0RAW_PATH}")
    print(f"  Target 1ENR    : {OUTPUT_1ENR_PATH}")
    print(f"  Target 2COL    : {OUTPUT_2COL_PATH}")
    print("========================================================================\n")

    # Load starting dataframe
    if os.path.exists(EXISTING_1ENR_PATH):
        df = pd.read_csv(EXISTING_1ENR_PATH, dtype=str).fillna('')
        print(f"[*] Loaded existing progress from {EXISTING_1ENR_PATH} ({len(df)} agencies).")
    elif os.path.exists(INPUT_0RAW_PATH):
        df = pd.read_csv(INPUT_0RAW_PATH, dtype=str).fillna('')
        print(f"[*] Loaded raw data from {INPUT_0RAW_PATH} ({len(df)} agencies).")
    else:
        print("[ERROR] Neither HR_AGCY_MROS_0RAW.csv nor HR_AGCY_1ENR.csv found!")
        sys.exit(1)

    # Ensure required columns
    for col in ['OIB', 'SĐT', 'Web', 'Email', 'Người đại diện', 'Trạng thái']:
        if col not in df.columns:
            df[col] = ''

    total_rows = len(df)
    init_emails = len(df[df['Email'] != ''])
    init_oibs = len(df[df['OIB'] != ''])
    init_phones = len(df[df['SĐT'] != ''])
    print(f"[*] Initial status: {init_emails} emails, {init_phones} phones, {init_oibs} OIBs.")

    # Load cache
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache)} cached company profiles from {CACHE_PATH}.")
        except Exception as e:
            print(f"[!] Warning reading cache: {e}")

    # Identify pending rows: prioritize rows without email or without OIB
    pending_rows = []
    for idx, row in df.iterrows():
        em = row['Email'].strip()
        oib = row['OIB'].strip()
        brand = row['Tên thương hiệu'].strip() or row['Công ty'].strip()
        city = row['Thành phố'].strip()
        cache_key = f"{brand}::{city}".lower()

        # If already cached with both email and OIB, update immediately
        if cache_key in cache and cache[cache_key].get('Email') and cache[cache_key].get('OIB'):
            c = cache[cache_key]
            df.at[idx, 'Email'] = c['Email']
            df.at[idx, 'OIB'] = c['OIB']
            df.at[idx, 'SĐT'] = c.get('SĐT', df.at[idx, 'SĐT'])
            df.at[idx, 'Web'] = c.get('Web', df.at[idx, 'Web'])
            df.at[idx, 'Người đại diện'] = c.get('Director', df.at[idx, 'Người đại diện'])
            df.at[idx, 'Trạng thái'] = c.get('Status', df.at[idx, 'Trạng thái'])
        elif not em or not oib:
            pending_rows.append(row)

    print(f"[*] Agencies pending deep multi-tier enrichment: {len(pending_rows)}")

    if not pending_rows:
        print("[+] All agencies have emails and OIBs or are fully cached!")
        save_checkpoint(df, cache)
        return

    MAX_WORKERS = 8
    print(f"[*] Starting {MAX_WORKERS} concurrent worker threads...")
    completed_count = 0
    newly_found_emails = 0
    newly_found_oibs = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_agency, row, cache): row for row in pending_rows}

        for future in as_completed(futures):
            res = future.result()
            completed_count += 1
            idx = res['row_index']

            if res['Email']:
                if not df.at[idx, 'Email']:
                    newly_found_emails += 1
                    print(f"[{completed_count}/{len(pending_rows)}] [+] EMAIL: {df.at[idx, 'Công ty']} -> {res['Email']} (Dir: {res['Director']})")
                df.at[idx, 'Email'] = res['Email']

            if res['OIB']:
                if not df.at[idx, 'OIB']:
                    newly_found_oibs += 1
                df.at[idx, 'OIB'] = res['OIB']

            if res['SĐT']:
                df.at[idx, 'SĐT'] = res['SĐT']
            if res['Web']:
                df.at[idx, 'Web'] = res['Web']
            if res['Director']:
                df.at[idx, 'Người đại diện'] = res['Director']
            if res['Status']:
                df.at[idx, 'Trạng thái'] = res['Status']

            if completed_count % 10 == 0:
                save_checkpoint(df, cache)
                elapsed = time.time() - start_time
                speed = completed_count / elapsed if elapsed > 0 else 0
                print(f"[*] Checkpoint saved ({completed_count}/{len(pending_rows)} done, +{newly_found_emails} new emails, +{newly_found_oibs} new OIBs, {speed:.1f} comp/sec)")

    # Final Save
    save_checkpoint(df, cache)
    final_emails = len(df[df['Email'] != ''])
    final_oibs = len(df[df['OIB'] != ''])
    final_phones = len(df[df['SĐT'] != ''])

    print("\n" + "=" * 80)
    print("  CROATIAN ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f"  Total Agencies : {total_rows}")
    print(f"  Final Emails   : {final_emails} / {total_rows} ({(final_emails/total_rows)*100:.1f}%) [+{newly_found_emails} new]")
    print(f"  Final OIBs     : {final_oibs} / {total_rows} ({(final_oibs/total_rows)*100:.1f}%) [+{newly_found_oibs} new]")
    print(f"  Final Phones   : {final_phones} / {total_rows} ({(final_phones/total_rows)*100:.1f}%)")
    print("  Output Files:")
    print(f"    - {OUTPUT_1ENR_PATH}")
    print(f"    - {OUTPUT_2COL_PATH}")
    print("=" * 80)


if __name__ == '__main__':
    main()
