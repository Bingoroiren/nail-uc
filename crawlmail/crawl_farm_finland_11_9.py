import os
import re
import csv
import json
import time
import shutil
import urllib.parse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import urllib3
import asyncio
from playwright.async_api import async_playwright

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
TARGET_CSV = os.path.join(WORKSPACE_DIR, "(11_9) nông trại Phần Lan - Trang tính1.csv")
BACKUP_CSV = os.path.join(WORKSPACE_DIR, "(11_9) nông trại Phần Lan - Trang tính1.backup.csv")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_farm_finland_11_9.json")

# Regex patterns
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[@\]\s*([A-Za-z0-9.-]{1,255})\s*\[\.\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
]

INVALID_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
    '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf', '.eot'
)

# Finnish / International Platform & Directory domains (NEVER guess info@ for these)
PLATFORM_DOMAINS = {
    # Social media
    'facebook.com', 'm.facebook.com', 'fi-fi.facebook.com', 'nb-no.facebook.com', 'l.facebook.com',
    'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com',
    'tiktok.com', 'pinterest.com',
    # Booking & Travel aggregators
    'booking.com', 'tripadvisor.com', 'tripadvisor.fi', 'airbnb.com', 'airbnb.fi',
    'bluepillow.com', 'br.bluepillow.com', 'nettimokki.com', 'lomarengas.fi',
    'gofinland.fi', 'hotel.de', 'hotels.com', 'expedia.com', 'trivago.com', 'agoda.com',
    # Directories, Yellow Pages & Associations in Finland
    'finder.fi', 'fonecta.fi', 'asiakastieto.fi', 'yritystele.fi', 'kauppalehti.fi',
    'tori.fi', 'suomi.fi', 'is.fi', 'iltalehti.fi', 'hs.fi', 'yle.fi',
    'prisma.fi', 'k-ruoka.fi', '4h.fi', 'tampere.4h.fi',
    # Finnish Municipalities / Public portals
    'vaasa.fi', 'lahti.fi', 'ouka.fi', 'hel.fi', 'helsinki.fi', 'nuorten.hel.fi',
    'jyvaskyla.fi', 'turku.fi', 'tampere.fi', 'espoo.fi', 'vantaa.fi', 'oulu.fi',
    # Search & Maps & Tech
    'google.com', 'maps.google.com', 'sites.google.com', 'apple.com', 'bing.com',
    'wikipedia.org',
    # CMS Platforms & Free hostings
    'squarespace.com', 'webnode.fi', 'webnode.com', 'wixsite.com', 'wix.com', 'wordpress.com',
    'weebly.com', 'site123.me', 'jimdosite.com', 'webador.com', 'suntuubi.com',
    'kotisivukone.com', 'blogspot.com', 'shopify.com', 'myshopify.com'
}

PLATFORM_KEYWORDS = [
    'facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok', 'pinterest',
    'bluepillow', 'booking', 'tripadvisor', 'airbnb', 'nettimokki', 'lomarengas',
    'gofinland', 'finder.fi', 'fonecta', 'asiakastieto', 'yritystele', 'kauppalehti',
    'google', 'apple', 'bing', 'squarespace', 'webnode', 'wixsite', 'wordpress',
    'jimdo', 'weebly', 'webador', 'suntuubi', 'kotisivukone', 'blogspot'
]

# Junk / Spammer / Placeholder Email Domains
JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'squarespace.com', 'weebly.com', 'webador.com', 'one.com',
    'godaddy.com', 'wordpress.com', 'bluepillow.com', 'booking.com',
    'tripadvisor.com', 'google.com', 'facebook.com', 'instagram.com',
    'handkerchiefstudio.com', 'hervieu.me', 'example.com', 'example.org', 'example.fi',
    'domain.com', 'placeholder.com', 'email.com', 'mysite.com', 'test.com',
    'schema.org', 'w3.org', 'esimerkki.fi', 'sivusto.com', 'opencart.com',
    'istudiosg.com', 'procountor.apix.fi', 'maventa.com', 'apix.fi'
}

# System / bot email usernames & placeholders
SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies',
    'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'admin',
    'mailer-daemon', 'postmaster', 'user', 'example', 'muster', 'dpo',
    'name', 'email', 'mail', 'sinun', 'esimerkki', 'yhteydenotto'
}

# Finnish business preferred usernames
PREFERRED_BIZ_USERNAMES = {
    'info', 'asiakaspalvelu', 'myynti', 'posti', 'toimisto', 'yhteys',
    'tilaus', 'tilaukset', 'contact', 'office', 'postia', 'tila',
    'farm', 'palvelu', 'myyntipalvelu', 'varaukset', 'hallinto',
    'puutarha', 'marjat', 'tilapuoti'
}

FINNISH_ISP_DOMAINS = {
    'kolumbus.fi', 'elisanet.fi', 'saunalahti.fi', 'dnainternet.net',
    'netti.fi', 'sci.fi', 'pp.inet.fi', 'luukku.com', 'suomi24.fi', 'surffi.net'
}

FREE_EMAIL_DOMAINS = {
    'gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'icloud.com', 'live.com'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7',
}

FINNISH_CONTACT_KEYWORDS = [
    'yhteystiedot', 'yhteys', 'ota-yhteytta', 'ota yhteytta', 'ota yhteyttä',
    'yhteystieto', 'asiakaspalvelu', 'tietoa-meista', 'tietoa meistä',
    'yhteystietomme', 'contact', 'info', 'about', 'yritys', 'meistä', 'meista'
]

COMMON_CONTACT_PATHS = [
    '/yhteystiedot/', '/yhteystiedot', '/yhteys/', '/yhteys',
    '/ota-yhteytta/', '/ota-yhteytta', '/ota-yhteytta/yhteystiedot',
    '/contact/', '/contact', '/info/', '/info',
    '/yritys/', '/yritys', '/about/', '/about'
]

def clean_phone(phone_str):
    """
    Cleans phone number:
    - Removes strange characters, spaces, dashes
    - Normalizes country code (+358)
    - Always prepends a single quote "'" for Google Sheets text formatting
    """
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    has_plus = '+' in s
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if has_plus:
        clean = f"+{digits}"
    elif digits.startswith("00"):
        clean = f"+{digits[2:]}"
    elif digits.startswith("358"):
        clean = f"+{digits}"
    else:
        clean = digits
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
    """
    Scores email quality from 0 (junk/invalid) to 100 (best business email).
    """
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

    # Reject hex hash usernames
    if len(username) >= 30 and re.match(r'^[0-9a-fA-F]+$', username):
        return 0

    if username in SYSTEM_USERNAMES or any(k in username or k in domain for k in ['no-reply', 'noreply', 'privacy', 'example', 'muster', 'sinun', 'esimerkki', 'sivusto', 'opencart']):
        return 0

    # Reject junk domains
    for jd in JUNK_EMAIL_DOMAINS:
        if domain == jd or domain.endswith('.' + jd):
            return 0

    clean_site = site_domain.lower().replace('www.', '') if site_domain else ""

    # 1. Matches site domain + Finnish preferred biz username (e.g. info@domain.fi)
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
    if domain not in FINNISH_ISP_DOMAINS and domain not in FREE_EMAIL_DOMAINS:
        if username in PREFERRED_BIZ_USERNAMES:
            return 80
        return 70

    # 4. Finnish ISP (elisanet.fi, kolumbus.fi, saunalahti.fi, dnainternet.net, etc.)
    if domain in FINNISH_ISP_DOMAINS:
        if username in PREFERRED_BIZ_USERNAMES:
            return 65
        return 55

    # 5. Free public email (gmail, outlook, hotmail)
    if domain in FREE_EMAIL_DOMAINS:
        if username in PREFERRED_BIZ_USERNAMES:
            return 45
        return 35

    return 20

# ----------------- STAGE 1: ULTRA-FAST HTTP REQUEST CRAWLER -----------------

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

def find_candidate_contact_links_soup(html_text, base_url):
    candidates = []
    try:
        soup = BeautifulSoup(html_text, 'html.parser')
        base_netloc = extract_clean_domain(base_url)
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text().strip().lower()
            href_lower = href.lower()
            if href_lower.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            if any(k in text or k in href_lower for k in FINNISH_CONTACT_KEYWORDS):
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
            contact_subpages = find_candidate_contact_links_soup(resp.text, target_url)
        resp.close()
    except Exception:
        if target_url.startswith('https://'):
            http_url = 'http://' + target_url[8:]
            try:
                resp = s.get(http_url, timeout=(2.5, 3.5), verify=False)
                if resp.status_code == 200:
                    extracted = extract_emails_from_html(resp.text)
                    all_emails.update(extracted)
                    contact_subpages = find_candidate_contact_links_soup(resp.text, http_url)
                resp.close()
            except Exception:
                pass

    has_good = any(score_email(e, site_domain) >= 70 for e in all_emails)
    if not has_good:
        if not contact_subpages:
            parsed = urllib.parse.urlparse(target_url)
            root = f"{parsed.scheme}://{parsed.netloc}"
            for p in COMMON_CONTACT_PATHS[:3]:
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

# ----------------- STAGE 2: PLAYWRIGHT CHROMIUM BROWSER CRAWLER -----------------

async def setup_speed_route(page):
    async def route_handler(route):
        if route.request.resource_type in ["image", "media", "font"]:
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route("**/*", route_handler)
    except Exception:
        pass

async def extract_emails_from_playwright_page(page):
    emails = set()
    try:
        mailto_links = await page.locator('a[href^="mailto:"]').all()
        for link in mailto_links:
            href = await link.get_attribute('href')
            if href:
                clean_m = href.split('?')[0].replace('mailto:', '').strip().lower()
                clean_m = clean_m.replace('u003e', '').replace('&lt;', '').replace('&gt;', '').strip()
                if EMAIL_REGEX.match(clean_m):
                    emails.add(clean_m)
    except Exception:
        pass

    try:
        body_text = await page.locator('body').inner_text()
        for em in EMAIL_REGEX.findall(body_text):
            em_clean = em.strip().lower()
            if not any(em_clean.endswith(ext) for ext in INVALID_EXTENSIONS):
                emails.add(em_clean)
        for pat in OBFUSCATED_PATTERNS:
            for m in pat.finditer(body_text):
                em_dec = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower().strip()
                emails.add(em_dec)
    except Exception:
        pass

    try:
        html = await page.content()
        for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
            dec = decode_cloudflare_email(cf)
            if dec and '@' in dec:
                emails.add(dec)
        for em in EMAIL_REGEX.findall(html):
            em_clean = em.strip().lower()
            if not any(em_clean.endswith(ext) for ext in INVALID_EXTENSIONS):
                emails.add(em_clean)
    except Exception:
        pass

    return emails

async def crawl_site_with_playwright(page, url):
    site_domain = extract_clean_domain(url)
    target_url = url if url.startswith(('http://', 'https://')) else 'https://' + url
    all_emails = set()

    try:
        await page.goto(target_url, timeout=11000, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)
        except Exception:
            pass

        homepage_emails = await extract_emails_from_playwright_page(page)
        all_emails.update(homepage_emails)
    except Exception:
        if target_url.startswith('https://'):
            http_url = 'http://' + target_url[8:]
            try:
                await page.goto(http_url, timeout=9000, wait_until="domcontentloaded")
                await page.wait_for_timeout(800)
                homepage_emails = await extract_emails_from_playwright_page(page)
                all_emails.update(homepage_emails)
            except Exception:
                pass

    has_good_email = any(score_email(e, site_domain) >= 70 for e in all_emails)

    if not has_good_email:
        candidate_subpages = []
        try:
            links = await page.locator('a[href]').all()
            for link in links:
                href = await link.get_attribute('href')
                text = (await link.inner_text() or '').lower().strip()
                if href:
                    href_lower = href.lower()
                    if href_lower.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                        continue
                    if any(k in text or k in href_lower for k in FINNISH_CONTACT_KEYWORDS):
                        full_url = urllib.parse.urljoin(target_url, href)
                        if extract_clean_domain(full_url) == site_domain:
                            clean_u = full_url.split('#')[0].rstrip('/')
                            if clean_u not in candidate_subpages and clean_u != target_url.rstrip('/'):
                                candidate_subpages.append(clean_u)
        except Exception:
            pass

        parsed = urllib.parse.urlparse(target_url)
        root_origin = f"{parsed.scheme}://{parsed.netloc}"
        for guess in COMMON_CONTACT_PATHS[:3]:
            g_url = (root_origin + guess).rstrip('/')
            if g_url not in candidate_subpages and g_url != target_url.rstrip('/'):
                candidate_subpages.append(g_url)

        for sub_url in candidate_subpages[:2]:
            try:
                await page.goto(sub_url, timeout=8000, wait_until="domcontentloaded")
                await page.wait_for_timeout(600)
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(400)
                except Exception:
                    pass
                sub_emails = await extract_emails_from_playwright_page(page)
                all_emails.update(sub_emails)
                if any(score_email(e, site_domain) >= 70 for e in sub_emails):
                    break
            except Exception:
                pass

    scored_emails = []
    for em in all_emails:
        sc = score_email(em, site_domain)
        if sc > 0:
            scored_emails.append((sc, em))

    scored_emails.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return scored_emails[0][1] if scored_emails else ""

async def crawl_remaining_with_playwright(urls_to_crawl, cache):
    print(f"\n[*] GIAI DOAN 2: Cao bang Playwright Chromium ({len(urls_to_crawl)} website con lai, 6 tabs dong thoi)...")
    print(f"[*] Co che: Cuon trang xuong footer + Tim trang Lien he (Yhteystiedot) + Chay day du JS.")
    total = len(urls_to_crawl)
    completed = 0
    start_time = time.time()
    sem = asyncio.Semaphore(6)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7"}
        )

        async def worker(u):
            nonlocal completed
            async with sem:
                res_email = ""
                page = None
                try:
                    page = await context.new_page()
                    await setup_speed_route(page)
                    res_email = await asyncio.wait_for(crawl_site_with_playwright(page, u), timeout=18.0)
                except Exception:
                    res_email = ""
                finally:
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            pass

                completed += 1
                cache[u] = res_email
                if res_email:
                    print(f" [Playwright {completed}/{total}] {u} -> [+] {res_email}", flush=True)
                else:
                    print(f" [Playwright {completed}/{total}] {u} -> [-]", flush=True)

                if completed % 5 == 0 or completed == total:
                    save_cache(cache)

        tasks = [worker(u) for u in urls_to_crawl]
        await asyncio.gather(*tasks)
        await browser.close()

    elapsed = time.time() - start_time
    print(f"[+] Giai doan 2 (Playwright) hoan tat trong {elapsed:.1f} giay.")
    save_cache(cache)

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

def process_farm_finland():
    print("=" * 68)
    print(" [*] BAT DAU XU LY FILE: (11_9) nông trại Phần Lan - Trang tính1.csv")
    print("=" * 68)

    if "--reset" in sys.argv:
        if os.path.exists(CACHE_FILE):
            try:
                os.remove(CACHE_FILE)
                print("[*] Da xoa cache cu. Bat dau cao moi hoan toan tu dau.")
            except Exception:
                pass

    if not os.path.exists(TARGET_CSV):
        print(f"[ERROR] Khong tim thay file muc tieu: {TARGET_CSV}")
        return

    # Backup original file
    print(f"[*] Tao ban sao luu: {BACKUP_CSV} ...")
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print("[+] Sao luu hoan tat.")

    # Read rows
    with open(TARGET_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    print(f"[*] Tong so dong doc duoc: {len(rows)}")

    cache = load_cache()
    print(f"[*] Da load {len(cache)} ket qua tu cache truoc do.")

    # Format Phone numbers & identify URLs to scrape
    urls_to_scrape = set()
    phone_cleaned_count = 0

    for r in rows:
        # Clean phone numbers
        raw_phone = r.get("SDT", "")
        clean_p = clean_phone(raw_phone)
        if clean_p != raw_phone:
            r["SDT"] = clean_p
            phone_cleaned_count += 1

        website = r.get("Lien He", "").strip()
        existing_email = r.get("Email", "").strip()
        domain = extract_clean_domain(website)

        # Discard junk existing emails
        if existing_email:
            if score_email(existing_email, domain) == 0:
                r["Email"] = ""
                existing_email = ""

        # Gather target URLs
        if not existing_email and website:
            if not is_platform_or_aggregator(domain):
                if website not in cache:
                    urls_to_scrape.add(website)

    print(f"[*] Da format sach va danh dau nhay cho {phone_cleaned_count} so dien thoai.")
    print(f"[*] Tong so website hop le can cao: {len(urls_to_scrape)}")

    # GIAI DOAN 1: Fast HTTP Concurrency (30 threads)
    if urls_to_scrape:
        print(f"\n[*] GIAI DOAN 1: Quet sieu toc bang HTTP Requests (30 luong song song)...", flush=True)

        start_time = time.time()
        completed = 0
        total = len(urls_to_scrape)
        found_in_phase1 = 0
        still_empty = []

        with ThreadPoolExecutor(max_workers=30) as executor:
            future_to_url = {executor.submit(scrape_via_fast_http, u): u for u in urls_to_scrape}
            for future in as_completed(future_to_url):
                u = future_to_url[future]
                completed += 1
                try:
                    res_email = future.result(timeout=12)
                    if res_email:
                        cache[u] = res_email
                        found_in_phase1 += 1
                        print(f" [HTTP {completed}/{total}] {u} -> [+] {res_email}", flush=True)
                    else:
                        still_empty.append(u)
                        print(f" [HTTP {completed}/{total}] {u} -> [-]", flush=True)
                except Exception:
                    still_empty.append(u)
                    print(f" [HTTP {completed}/{total}] {u} -> [Timeout/Skip]", flush=True)

                if completed % 5 == 0 or completed == total:
                    save_cache(cache)

        elapsed = time.time() - start_time
        print(f"[+] Giai doan 1 hoan tat trong {elapsed:.1f}s. Tim thay: {found_in_phase1} emails.", flush=True)
        print(f"[*] Con lai {len(still_empty)} trang can quet sau bang Playwright Chromium.", flush=True)
        save_cache(cache)

        # GIAI DOAN 2: Playwright Chromium Deep Crawler
        if still_empty:
            asyncio.run(crawl_remaining_with_playwright(still_empty, cache))

    # Apply emails, info@domain guessing, and Check gui
    total_emails_before = 0
    scraped_count = 0
    guessed_count = 0
    retained_count = 0

    for r in rows:
        website = r.get("Lien He", "").strip()
        existing_email = r.get("Email", "").strip()
        domain = extract_clean_domain(website)

        # Ensure phone has single quote
        if r.get("SDT"):
            r["SDT"] = clean_phone(r["SDT"])

        # Check existing email
        if existing_email:
            total_emails_before += 1
            if score_email(existing_email, domain) > 0:
                retained_count += 1
                r["Check gui"] = "OK"
                continue
            else:
                existing_email = ""
                r["Email"] = ""

        # Check scraped email
        scraped_email = cache.get(website, "").strip() if website else ""
        if scraped_email and score_email(scraped_email, domain) > 0:
            r["Email"] = scraped_email
            r["Check gui"] = "OK"
            scraped_count += 1
            continue

        # Guess info@domain for valid private company domains (NEVER platforms)
        if domain and not is_platform_or_aggregator(domain):
            guessed_email = f"info@{domain}".lower()
            r["Email"] = guessed_email
            r["Check gui"] = "OK"
            guessed_count += 1
            continue

        r["Check gui"] = ""

    # Sort rows: "dòng có mail thì đẩy lên trên"
    print("\n[*] Dang sap xep: Day toan bo dong CO MAIL len tren cung...")
    rows_with_email = [r for r in rows if r.get("Email", "").strip()]
    rows_without_email = [r for r in rows if not r.get("Email", "").strip()]
    sorted_rows = rows_with_email + rows_without_email

    # Re-index No.
    for idx, r in enumerate(sorted_rows, 1):
        r["No."] = str(idx)

    # Write back to CSV
    print(f"[*] Dang ghi de ket qua vao: {TARGET_CSV} ...")
    with open(TARGET_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("=" * 68)
    print(" [KET QUA XU LY FILE (11_9) NÔNG TRẠI PHẦN LAN]")
    print(f"  - Tong so dong trong file: {len(sorted_rows)}")
    print(f"  - So mail cu hop le duoc giu lai: {retained_count}")
    print(f"  - So mail cao moi thanh cong: {scraped_count}")
    print(f"  - So mail doan bang info@domain: {guessed_count}")
    print(f"  - TONG SO HANG CO MAIL HIEN TAI (Check gui = OK): {len(rows_with_email)}")
    print(f"  - So hang khong co mail (Check gui trong): {len(rows_without_email)}")
    print(f"  - Tat ca dong co mail da duoc sap xep len tren dau file.")
    print("=" * 68)

if __name__ == "__main__":
    process_farm_finland()
