import os
import sys
import re
import csv
import json
import time
import shutil
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import urllib3

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Suppress insecure SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Paths
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_CSV = os.path.join(WORKSPACE_DIR, "(11_9) doanh nghiệp có giấy phép Canada - Trang tính1.csv")
BACKUP_CSV = os.path.join(WORKSPACE_DIR, "(11_9) doanh nghiệp có giấy phép Canada - Trang tính1.backup.csv")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_canada_emails_11_9.json")

# Standard Cold Mail Output Columns (20 columns)
STANDARD_FIELDNAMES = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT',
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong',
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject',
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up',
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

# Regex patterns
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})', re.IGNORECASE),
]

INVALID_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
    '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf', '.eot'
)

# Directories, Platforms, Aggregators & Social Media (NEVER guess info@ for these)
PLATFORM_DOMAINS = {
    # Directory & Registry aggregators in Canada
    'opengovca.com', 'lmiagrader.com', 'b2bhint.com', 'workabroadlink.com',
    'canada.chamberofcommerce.com', 'albertacorporations.com', 'quebecentreprises.com',
    'visatalents.ca', 'ref.quebec', 'canadacareersite.com', 'opencorporates.com',
    'canadacompanyregistry.com', 'canadacompanyregistry.ca', 'allbiz.ca', 'cybo.com',
    'infobel.com', 'local.infobel.ca', 'federalcorporation.ca', 'profilecanada.com',
    'firmania.ca', 'info-clipper.com', 'search.infobelpro.com', 'opencorpdata.com',
    'lmia.ca', 'ontario.ca', 'sponsorarchive.com', 'findglocal.com', 'restaurantguru.com',
    'nexdu.com', 'yellowpages.ca', '411.ca', 'ca.411.info', 'bbb.org', 'zoominfo.com',
    'dnb.com', 'yelp.ca', 'yelp.com', 'lei.report', 'lei-lookup.com', 'chamberofcommerce.com',
    # Social media & Big Tech
    'facebook.com', 'm.facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'linkedin.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
    'google.com', 'maps.google.com', 'sites.google.com', 'apple.com', 'bing.com',
    # Lodging / Travel / Generic
    'tripadvisor.ca', 'tripadvisor.com', 'booking.com', 'airbnb.ca', 'airbnb.com',
    # Free CMS hosts
    'squarespace.com', 'wixsite.com', 'wix.com', 'wordpress.com', 'weebly.com',
    'site123.me', 'jimdosite.com', 'webador.com', 'suntuubi.com', 'blogspot.com'
}

PLATFORM_KEYWORDS = [
    'opengovca', 'lmiagrader', 'b2bhint', 'workabroadlink', 'chamberofcommerce',
    'albertacorporations', 'quebecentreprises', 'visatalents', 'canadacareersite',
    'opencorporates', 'canadacompanyregistry', 'infobel', 'federalcorporation',
    'profilecanada', 'firmania', 'opencorpdata', 'sponsorarchive', 'findglocal',
    'restaurantguru', 'yellowpages', '411.ca', 'facebook', 'instagram', 'twitter',
    'linkedin', 'youtube', 'tiktok', 'booking.com', 'tripadvisor', 'airbnb',
    'squarespace', 'wixsite', 'wordpress', 'weebly', 'blogspot'
]

# Junk / Spammer / Placeholder Email Domains
JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'squarespace.com', 'weebly.com', 'webador.com', 'one.com',
    'godaddy.com', 'wordpress.com', 'bluepillow.com', 'booking.com',
    'tripadvisor.com', 'google.com', 'facebook.com', 'instagram.com',
    'handkerchiefstudio.com', 'hervieu.me', 'example.com', 'example.org', 'example.ca',
    'domain.com', 'placeholder.com', 'email.com', 'mysite.com', 'test.com',
    'schema.org', 'w3.org', 'federalcorporation.ca'
}

# System / bot email usernames & placeholders
SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies',
    'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'admin',
    'mailer-daemon', 'postmaster', 'user', 'example', 'muster', 'dpo',
    'name', 'email', 'mail', 'test'
}

PREFERRED_BIZ_USERNAMES = {
    'info', 'contact', 'hr', 'careers', 'jobs', 'recruitment', 'office',
    'admin', 'sales', 'support', 'service', 'inquiries', 'general',
    'hiring', 'employment', 'farm', 'orders', 'accounting'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-CA,en-US;q=0.9,en;q=0.8,fr-CA;q=0.7,fr;q=0.6',
}

CONTACT_PATHS = [
    '/contact', '/contact/', '/contact-us', '/contact-us/',
    '/about', '/about/', '/about-us', '/about-us/',
    '/careers', '/careers/', '/nous-joindre', '/nous-joindre/',
    '/a-propos', '/a-propos/'
]

def clean_phone_ca(phone_str):
    """
    Cleans Canadian / US phone numbers:
    - Normalizes to +1... format
    - Always prepends a single quote "'" for Google Sheets text formatting
    """
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    # Remove extensions like 'ext 123' or 'x 456'
    s = re.split(r'\b(ext|x|extension)\b', s, flags=re.IGNORECASE)[0].strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith("001") and len(digits) == 13:
        clean = f"+{digits[2:]}"
    elif digits.startswith("1") and len(digits) == 11:
        clean = f"+{digits}"
    elif len(digits) == 10:
        clean = f"+1{digits}"
    elif digits.startswith("1") and len(digits) > 11:
        clean = f"+{digits[:11]}"
    elif len(digits) > 10:
        clean = f"+1{digits[:10]}"
    else:
        clean = f"+1{digits}"
    return f"'{clean}"

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:]).strip().lower()
    except Exception:
        return ""

def extract_clean_domain(url):
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        netloc = netloc.split(':')[0].strip().rstrip('.')
        if '.' not in netloc or ' ' in netloc:
            return ""
        return netloc
    except Exception:
        return ""

def is_platform_or_aggregator(domain):
    if not domain:
        return True
    domain = domain.lower().strip()
    for plat in PLATFORM_DOMAINS:
        if domain == plat or domain.endswith('.' + plat):
            return True
    for kw in PLATFORM_KEYWORDS:
        if kw in domain:
            return True
    return False

def score_email(email, site_domain=""):
    if not email:
        return 0
    email = email.lower().strip()
    for prefix in ['u003e', 'u003c', '&lt;', '&gt;', 'mailto:', ':']:
        if email.startswith(prefix):
            email = email[len(prefix):].strip()
    if '@' not in email:
        return 0
    if any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
        return 0
    if not EMAIL_REGEX.match(email):
        return 0

    username, domain = email.split('@', 1)
    username = username.strip()
    domain = domain.strip()

    if len(username) >= 30 and re.match(r'^[0-9a-fA-F]+$', username):
        return 0

    if username in SYSTEM_USERNAMES or any(k in username or k in domain for k in ['no-reply', 'noreply', 'privacy', 'example', 'muster', 'sentry']):
        return 0

    for jd in JUNK_EMAIL_DOMAINS:
        if domain == jd or domain.endswith('.' + jd):
            return 0

    if email.startswith('federalcorporation.ca'):
        return 0

    clean_site = site_domain.lower().replace('www.', '') if site_domain else ""

    # 1. Matches site domain + preferred biz username (e.g. info@domain.com, hr@domain.ca)
    if clean_site and domain == clean_site:
        if username in PREFERRED_BIZ_USERNAMES:
            return 100
        return 90

    # 2. Site domain contains or is contained in email domain
    if clean_site and (domain.endswith(clean_site) or clean_site.endswith(domain)):
        if username in PREFERRED_BIZ_USERNAMES:
            return 95
        return 85

    # 3. Custom domain with business username
    if domain not in {'gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'icloud.com', 'live.com'}:
        if username in PREFERRED_BIZ_USERNAMES:
            return 80
        return 70

    # 4. Public webmail (gmail, outlook, etc.)
    if username in PREFERRED_BIZ_USERNAMES:
        return 45
    return 35

def extract_emails_from_html(html_text):
    found = set()
    if not html_text:
        return found

    for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_text):
        dec = decode_cloudflare_email(cf)
        if dec and '@' in dec:
            found.add(dec)

    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.lower().startswith('mailto:'):
                clean_m = href.split('?')[0].replace('mailto:', '').strip().lower()
                clean_m = clean_m.replace('u003e', '').replace('&lt;', '').replace('&gt;', '').strip()
                if EMAIL_REGEX.match(clean_m):
                    found.add(clean_m)
    except Exception:
        pass

    for em in EMAIL_REGEX.findall(html_text):
        em_lower = em.strip().lower()
        if not any(em_lower.endswith(ext) for ext in INVALID_EXTENSIONS):
            found.add(em_lower)

    for pat in OBFUSCATED_PATTERNS:
        for m in pat.finditer(html_text):
            em_dec = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower().strip()
            if not any(em_dec.endswith(ext) for ext in INVALID_EXTENSIONS):
                found.add(em_dec)

    return found

def find_candidate_contact_links(html_text, base_url):
    candidates = []
    contact_keywords = ['contact', 'about', 'career', 'nous-joindre', 'a-propos', 'joint-us', 'reach-us']
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        base_netloc = extract_clean_domain(base_url)
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            href_lower = href.lower()
            if href_lower.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            if any(k in text or k in href_lower for k in contact_keywords):
                full_url = urllib.parse.urljoin(base_url, href)
                if extract_clean_domain(full_url) == base_netloc:
                    clean_full = full_url.split('#')[0].rstrip('/')
                    if clean_full not in candidates and clean_full != base_url.rstrip('/'):
                        candidates.append(clean_full)
    except Exception:
        pass
    return candidates[:3]

def scrape_via_fast_http(url):
    site_domain = extract_clean_domain(url)
    target_url = url if url.startswith(('http://', 'https://')) else 'https://' + url
    all_emails = set()
    contact_subpages = []

    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        resp = s.get(target_url, timeout=(3.0, 4.0), verify=False)
        if resp.status_code == 200:
            extracted = extract_emails_from_html(resp.text)
            all_emails.update(extracted)
            contact_subpages = find_candidate_contact_links(resp.text, target_url)
        resp.close()
    except Exception:
        if target_url.startswith('https://'):
            http_url = 'http://' + target_url[8:]
            try:
                resp = s.get(http_url, timeout=(2.5, 3.5), verify=False)
                if resp.status_code == 200:
                    extracted = extract_emails_from_html(resp.text)
                    all_emails.update(extracted)
                    contact_subpages = find_candidate_contact_links(resp.text, http_url)
                resp.close()
            except Exception:
                pass

    has_good = any(score_email(e, site_domain) >= 70 for e in all_emails)
    if not has_good:
        if not contact_subpages:
            parsed = urllib.parse.urlparse(target_url)
            root = f"{parsed.scheme}://{parsed.netloc}"
            for p in CONTACT_PATHS[:3]:
                contact_subpages.append(root + p)

        for sub_url in contact_subpages[:2]:
            try:
                sub_resp = s.get(sub_url, timeout=(2.5, 3.5), verify=False)
                if sub_resp.status_code == 200:
                    sub_emails = extract_emails_from_html(sub_resp.text)
                    all_emails.update(sub_emails)
                    sub_resp.close()
                    if any(score_email(e, site_domain) >= 70 for e in sub_emails):
                        break
                else:
                    sub_resp.close()
            except Exception:
                pass

    try:
        s.close()
    except Exception:
        pass

    scored = []
    for em in all_emails:
        sc = score_email(em, site_domain)
        if sc > 0:
            scored.append((sc, em))

    scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return scored[0][1] if scored else ""

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def process_canada_file():
    print("=" * 70, flush=True)
    print(" [*] XU LY VA CHUAN HOA FILE COLD MAIL: CANADA (11_9)", flush=True)
    print("=" * 70, flush=True)

    if not os.path.exists(TARGET_CSV):
        print(f"[ERROR] Khong tim thay file muc tieu: {TARGET_CSV}", flush=True)
        return

    # Backup original file
    if not os.path.exists(BACKUP_CSV):
        print(f"[*] Tao ban sao luu: {BACKUP_CSV} ...", flush=True)
        shutil.copy2(TARGET_CSV, BACKUP_CSV)
        print("[+] Sao luu hoan tat.", flush=True)

    # Read original CSV
    with open(TARGET_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        orig_rows = list(reader)

    print(f"[*] Tong so ban ghi doc duoc: {len(orig_rows)}", flush=True)

    # Standardize column mapping to STANDARD_FIELDNAMES
    converted_rows = []
    for r in orig_rows:
        row_dict = {
            'No.': r.get('No.', ''),
            'Cong ty': r.get('Công ty', r.get('Cong ty', '')),
            'Chuc danh': r.get('Chức danh', r.get('Chuc danh', '')),
            'Nguoi lien he': r.get('Người liên hệ', r.get('Nguoi lien he', '')),
            'SDT': r.get('SĐT', r.get('SDT', '')),
            'Lien He': r.get('Liên Hệ', r.get('Lien He', '')),
            'Email': r.get('Email', ''),
            'Lien He mail': r.get('Liên Hệ mail', r.get('Lien He mail', '')),
            'Dia chi': r.get('Địa chỉ', r.get('Dia chi', '')),
            'Luong': r.get('Lương', r.get('Luong', '')),
            'Ngay dang': r.get('Ngày đăng', r.get('Ngay dang', '')),
            'Han tuyen': r.get('Hạn tuyển', r.get('Han tuyen', '')),
            'Check gui': r.get('Check gửi', r.get('Check gui', '')),
            'Last Subject': r.get('Last Subject', ''),
            'Last Body HTML': r.get('Last Body HTML', ''),
            'Trang thai Reply': r.get('Trạng thái Reply', r.get('Trang thai Reply', '')),
            'Lan Follow-up': r.get('Lần Follow-up', r.get('Lan Follow-up', '0')),
            'Ngay Follow-up gan nhat': r.get('Ngày Follow-up gần nhất', r.get('Ngay Follow-up gan nhat', '')),
            'Mailbox da dung': r.get('Mailbox đã dùng', r.get('Mailbox da dung', '')),
            'Category': r.get('Category', '')
        }
        converted_rows.append(row_dict)

    # Load cache
    cache = load_cache()
    print(f"[*] Da load {len(cache)} ket qua tu cache truoc do.", flush=True)

    # Step 1: Clean Phone numbers & purge junk existing emails
    urls_to_scrape = set()
    cleaned_phones_count = 0
    purged_emails_count = 0

    for r in converted_rows:
        # Clean phone
        raw_p = r['SDT']
        clean_p = clean_phone_ca(raw_p)
        if clean_p != raw_p:
            r['SDT'] = clean_p
            cleaned_phones_count += 1

        # Check existing email
        curr_email = r['Email'].strip()
        website = r['Lien He'].strip()
        domain = extract_clean_domain(website)

        if curr_email:
            if score_email(curr_email, domain) == 0:
                r['Email'] = ''
                curr_email = ''
                purged_emails_count += 1

        # Identify websites to crawl
        if not curr_email and website:
            if not is_platform_or_aggregator(domain):
                if website not in cache:
                    urls_to_scrape.add(website)

    print(f"[*] Da chuan hoa dinh dang nhay don cho {cleaned_phones_count} so dien thoai.", flush=True)
    print(f"[*] Da loc va loai bo {purged_emails_count} email rac/placeholder cu.", flush=True)
    print(f"[*] Tong so website hop le can cao bo sung: {len(urls_to_scrape)}", flush=True)

    # Step 2: Concurrently crawl candidate websites
    if urls_to_scrape:
        print(f"\n[*] BAT DAU CAO MAIL BO SUNG ({len(urls_to_scrape)} websites, 35 threads)...", flush=True)
        start_time = time.time()
        completed = 0
        total = len(urls_to_scrape)
        found_count = 0

        with ThreadPoolExecutor(max_workers=35) as executor:
            future_to_url = {executor.submit(scrape_via_fast_http, u): u for u in urls_to_scrape}
            for future in as_completed(future_to_url):
                u = future_to_url[future]
                completed += 1
                try:
                    res_email = future.result(timeout=10)
                    if res_email:
                        cache[u] = res_email
                        found_count += 1
                        print(f" [HTTP {completed}/{total}] {u} -> [+] {res_email}", flush=True)
                    else:
                        cache[u] = ""
                        print(f" [HTTP {completed}/{total}] {u} -> [-]", flush=True)
                except Exception:
                    cache[u] = ""
                    print(f" [HTTP {completed}/{total}] {u} -> [Timeout/Skip]", flush=True)

                if completed % 20 == 0 or completed == total:
                    save_cache(cache)

        elapsed = time.time() - start_time
        print(f"[+] Cao hoan tat trong {elapsed:.1f}s. Tim thay {found_count} emails moi.", flush=True)
        save_cache(cache)

    # Step 3: Apply emails, guess info@domain, set Check gui
    retained_count = 0
    scraped_count = 0
    guessed_count = 0

    for r in converted_rows:
        website = r['Lien He'].strip()
        existing_email = r['Email'].strip()
        domain = extract_clean_domain(website)

        # 1. Existing valid email
        if existing_email:
            if score_email(existing_email, domain) > 0:
                retained_count += 1
                r['Check gui'] = 'OK'
                continue
            else:
                r['Email'] = ''
                existing_email = ''

        # 2. Scraped email from cache
        scraped_email = cache.get(website, "").strip() if website else ""
        if scraped_email and score_email(scraped_email, domain) > 0:
            r['Email'] = scraped_email
            r['Check gui'] = 'OK'
            scraped_count += 1
            continue

        # 3. Guess info@domain for valid company domains (NEVER platforms)
        if domain and not is_platform_or_aggregator(domain):
            guessed_email = f"info@{domain}".lower()
            r['Email'] = guessed_email
            r['Check gui'] = 'OK'
            guessed_count += 1
            continue

        r['Check gui'] = ''

    # Step 4: Sort rows - rows with email on top
    print("\n[*] Dang sap xep: Day toan bo dong CO MAIL len tren cung...", flush=True)
    rows_with_email = [r for r in converted_rows if r.get("Email", "").strip()]
    rows_without_email = [r for r in converted_rows if not r.get("Email", "").strip()]
    sorted_rows = rows_with_email + rows_without_email

    # Re-index No. sequentially
    for idx, r in enumerate(sorted_rows, 1):
        r["No."] = str(idx)

    # Step 5: Write out to target CSV
    print(f"[*] Dang ghi de ket qua vao: {TARGET_CSV} ...", flush=True)
    with open(TARGET_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("=" * 70, flush=True)
    print(" [KET QUA XU LY FILE COLD MAIL CANADA (11_9)]", flush=True)
    print(f"  - Tong so dong: {len(sorted_rows)}", flush=True)
    print(f"  - So email cu hop le duoc giu lai: {retained_count}", flush=True)
    print(f"  - So email cào moi thanh cong: {scraped_count}", flush=True)
    print(f"  - So email doan info@domain: {guessed_count}", flush=True)
    print(f"  - TONG SO DONG CO EMAIL (Check gui = OK): {len(rows_with_email)}", flush=True)
    print(f"  - So dong khong co email: {len(rows_without_email)}", flush=True)
    print(f"  - Tat ca dong co email da duoc day len dau file.", flush=True)
    print(f"  - Tat ca so dien thoai da duoc danh dau nhay don cho Google Sheets.", flush=True)
    print(f"  - Cột du lieu da duoc dua ve dung 20 cot chuan cua mau cold mail.", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    process_canada_file()
