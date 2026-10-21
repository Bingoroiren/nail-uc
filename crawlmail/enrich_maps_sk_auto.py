# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for SK_AUTO_SLVD_0RAW.csv (Slovakia Automotive Industry - NACE 29):
1. Tra cứu Google Maps (hl=sk, headless=False) bằng Tên Công Ty + ", Slovakia".
2. So khớp tên nghiêm ngặt (Exact match, Delimiter match, Bracket match, loại bỏ legal forms s.r.o., a.s...).
3. Đối chiếu địa chỉ (Mã bưu chính 5 số, Tên thành phố, Khu vực) để tránh nhầm chi nhánh khác.
4. Bóc tách Số điện thoại (luôn có dấu nháy đơn ' ở đầu), Website chính thức.
5. Nếu Google Maps không có website -> Fallback tìm kiếm DuckDuckGo / web search.
6. Quét website tìm email B2B đa tầng:
   - mailto:, regex, Cloudflare data-cfemail, Obfuscated email.
   - Quét subpages liên hệ bản địa hóa theo độ ưu tiên (/kontakt, /kontakty, /o-nas, /kariera, /praca...).
   - Heuristic scoring B2B (HR: +50, Executive: +45, Official: +40, Domain: +50). Tuyển chọn duy nhất 1 email tốt nhất.
7. Lưu tăng dần (Incremental Auto-Save) sau mỗi 5 công ty và Checkpoint JSON (Resume 100%).
8. Xuất file chuẩn 17 ký tự: SK_AUTO_SLVD_1ENR.csv (Đẩy 100% công ty có email lên đầu danh sách).
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
INPUT_CSV = str(ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv")
OUTPUT_CSV = str(ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json")

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'spolocnost s rucenim obmedzenym', 'spoločnosť s ručením obmedzeným',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'neziskova organizacia', 'nezisková organizácia', 'n.o.', 'n. o.',
    'obcianske zdruzenie', 'občianske združenie', 'o.z.', 'o. z.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'inc.', 'inc', 'corp.', 'corp',
    'organizačná zložka', 'odštepný závod'
]

EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.sk', 'maps.google.com', 'apple.com',
    'finstat.sk', 'zrsr.sk', 'orsr.sk', 'profesia.sk', 'kariera.zoznam.sk',
    'azet.sk', 'zlatestranky.sk', 'indexpodnikatela.sk', 'foaf.sk',
    'vzdelavanie.sk', 'portal.gov.sk', 'yellowpages', 'tripadvisor',
    'slovakdata.sk', 'registeruz.sk', 'autobazar.eu', 'autovia.sk',
    'adresarfiriem.sk', 'efirma.sk', 'cybo.com', 'northdata.com',
    'opencorporates.com', 'cylex.sk', 'autoyas.com', 'doveryhodnafirma.eu',
    'search.infobelpro.com', 'memoryofnations.sk', 'motointegrator.com',
    'talentflowcorp.com', 'uvostat.sk', 'finreg.sk', 'findat.sk', 'peniaze.sk',
    'valida.sk', 'forebears.io', 'ongenealogy.com', 'emis.com', 'dnb.com', 'kompass.com',
    'orsf.sk', 'transparex.sk', 'overit.sk', 'zoznam.sk', 'mapafiriem.sk',
    'verdeholding.hu', 'firmy.sk', 'katalogfiriem.sk', 'topfiriem.sk', 'najdi.sk',
    'pindex.sk', 'databazafiriem.sk', 'edb.sk', '123dopyt.sk', 'aaadopyt.sk',
    'kariera.sk', 'mojapraca.sk', 'bazar.sk', 'bazos.sk', 'centrum.sk', 'post.sk',
    'atlas.sk', 'statnyregister.sk', 'obchodnyregister.sk', 'slovensko.sk', 'gov.sk',
    'finreg.sk', 'zoznamtovarov.sk', 'telefonny.zoznam.sk', 'firmy.zoznam.sk',
    'creditreform.sk', 'e-creditreform.sk', 'ifirmy.sk', 'emis.com', 'emis.cn'
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
    'firma.sk', 'spolocnost.sk', 'domena.sk', 'vasadomena.sk', 'verdeholding.hu',
    'transparex.sk', 'overit.sk', 'mapafiriem.sk', 'orsf.sk', 'zoznam.sk'
}

BLACKLISTED_EXACT_EMAILS = {
    'office@verdeholding.hu', 'vasa.adresa@firma.sk', 'info@transparex.sk',
    'famsitslovakia@gmail.com', 'nieco@spolocnost.sk', 'kontakt@zoznam.sk',
    'info@overit.sk', 'podpora@overit.sk', 'info@mapafiriem.sk'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'domain', 'email', 'vasa.adresa', 'vasaadresa', 'nieco'
}

DOMAIN_EMAIL_CACHE = {}

def is_domain_relevant_to_company(domain, company_name):
    """
    Kiểm tra xem tên miền có thực sự tương đồng với tên công ty hay không.
    Ngăn chặn tuyệt đối việc nhận nhầm các trang danh bạ (overit.sk, zoznam.sk, mapafiriem.sk...).
    """
    if not domain or not company_name:
        return False
    d = domain.lower().replace('www.', '').split('.')[0]
    if any(ex in domain.lower() for ex in EXCLUDED_DOMAINS):
        return False

    c_clean = clean_company_name_sk(company_name)
    words = [w for w in c_clean.split() if len(w) >= 3 and w not in {'auto', 'moto', 'servis', 'group', 'slovakia', 'slovensko', 'spol'}]
    if not words:
        words = [w for w in c_clean.split() if len(w) >= 3]

    if any(w in d or d in w for w in words):
        return True

    c_condensed = re.sub(r'[^a-z0-9]', '', c_clean)
    if len(c_condensed) >= 4 and (c_condensed in d or d in c_condensed):
        return True

    return False


def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        pattern = rf'(?:^|[\s,;]){re.escape(lf)}(?:$|[\s,;])'
        n = re.sub(pattern, ' ', n)
    n = re.sub(r'\b(s\s*r\s*o|a\s*s|k\s*s|v\s*o\s*s)\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n



def is_valid_name_match_sk(query_name, candidate_name):
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

    q_clean = clean_company_name_sk(query_name)
    c_clean = clean_company_name_sk(candidate_name)

    if q_clean and c_clean:
        if q_clean == c_clean:
            return True, "CLEAN_EXACT"

        c_clean_parts = [clean_company_name_sk(p) for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
        if any(p == q_clean for p in c_clean_parts if p):
            return True, "CLEAN_DELIMITER"

        q_words = set(q_clean.split())
        c_words = set(c_clean.split())
        if q_words and q_words.issubset(c_words) and len(q_words) >= 2:
            return True, "CLEAN_SUBSET"

    return False, "NO_MATCH"


def check_address_compatibility(file_address, gmap_address):
    if not gmap_address:
        return True, "NO_GMAP_ADDRESS"

    fa = file_address.lower()
    ga = gmap_address.lower()

    foreign_keywords = ['česko', 'czech', 'hungary', 'magyar', 'austria', 'österreich', 'poland', 'polska', 'germany', 'deutschland']
    if any(k in ga for k in foreign_keywords) and not any(k in fa for k in foreign_keywords):
        return False, "LECH_QUOC_GIA"

    # Zip code match
    f_zips = re.findall(r'\b\d{5}\b', fa.replace(' ', ''))
    g_zips = re.findall(r'\b\d{5}\b', ga.replace(' ', ''))
    if set(f_zips).intersection(set(g_zips)):
        return True, "TRUNG_MA_BUU_CHINH"

    # City / area match
    tokens = re.split(r'[,/\-\s]+', fa)
    meaningful_tokens = [
        t for t in tokens
        if len(t) >= 4 and not t.isdigit() and t not in {'slovensko', 'slovakia', 'ulica', 'trieda', 'namestie'}
    ]
    matched_tokens = [t for t in meaningful_tokens if t in ga]
    if len(matched_tokens) >= 1:
        return True, f"CUNG_KHU_VUC_{matched_tokens[0]}"

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
    e = email.strip().lower().replace('%20', '')
    if e in BLACKLISTED_EXACT_EMAILS:
        return False
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

    # HR / Recruitment: Priority 1 (+50)
    if any(k in user for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    # Executive / Management: Priority 2 (+45)
    elif any(k in user for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # Official Contact: Priority 3 (+40)
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
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=5, verify=False)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), ssl=False) as resp:
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
        clean_m = m.strip().lower().replace('%20', '').rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found.add(clean_m)

    # Obfuscated
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(html_text):
            if len(match) == 3:
                rec = f"{match[0]}@{match[1]}.{match[2]}".lower().replace('%20', '')
            elif len(match) == 2:
                rec = f"{match[0]}@{match[1]}".lower().replace('%20', '')
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

    subpaths = ["", "/kontakt", "/kontakty", "/o-nas", "/kariera", "/praca", "/contact"]
    targets = [urllib.parse.urljoin(website_url, sp) for sp in subpaths]

    try:
        tasks = [fetch_html(u, session) for u in targets]
        html_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in html_results:
            if isinstance(res, str) and res:
                emails = extract_emails_from_html(res, domain)
                all_emails.update(emails)
    except Exception:
        pass

    best_email = ""
    if all_emails:
        sorted_emails = sorted(list(all_emails), key=lambda e: score_email_b2b(e, domain), reverse=True)
        best_email = sorted_emails[0]

    DOMAIN_EMAIL_CACHE[domain] = best_email
    return best_email



async def search_duckduckgo_for_website(query_name, city, session):
    """Fallback search when Google Maps has no direct website."""
    q = f"{query_name} {city} slovakia".strip()
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(q)}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }
    try:
        html_text = ""
        if HAS_CURL_CFFI:
            resp = await session.get(search_url, headers=headers, impersonate="chrome120", timeout=10)
            if resp.status_code == 200:
                html_text = resp.text
        else:
            async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    html_text = await resp.text()

        if html_text:
            soup = BeautifulSoup(html_text, 'html.parser')
            links = soup.select('a.result__url, a.result__snippet')
            for a in links:
                raw_href = a.get('href', '')
                if 'uddg=' in raw_href:
                    actual_url = urllib.parse.unquote(raw_href.split('uddg=')[1].split('&')[0])
                else:
                    actual_url = raw_href
                if actual_url.startswith(('http://', 'https://')):
                    parsed = urllib.parse.urlparse(actual_url)
                    d = parsed.netloc.lower().replace('www.', '')
                    # Bắt buộc domain KHÔNG thuộc blacklist VÀ phải tương đồng với tên công ty
                    if not any(ex in d for ex in EXCLUDED_DOMAINS) and is_domain_relevant_to_company(d, query_name):
                        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return ""


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

    try:
        with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_rows)
    except Exception as e:
        print(f"    [!] Cảnh báo ghi file CSV: {e}")


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
        print("[!] CAPTCHA PHÁT HIỆN! Vui lòng bấm giải Captcha trên trình duyệt Chrome...")
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha đã giải xong! Tiếp tục chạy...")
                break


async def extract_details_from_panel(page):
    phone = ""
    website = ""
    address = ""

    try:
        phone_btn = page.locator('button[data-tooltip*="telefón"], button[data-item-id*="phone:tel:"]')
        if await phone_btn.count() > 0:
            raw_phone = await phone_btn.first.inner_text()
            clean_p = re.sub(r'[^\d+()\s-]', '', raw_phone).strip()
            phone = re.sub(r'\s+', ' ', clean_p)
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

    # Case 1: Direct place found
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
                "gmap_address": gmap_addr,
                "match_type": m_type,
                "addr_status": addr_reason
            }
        return None

    # Case 2: List of results
    try:
        feed_items = page.locator('div[role="feed"] > div > div[jsaction], a.hfpxzc')
        count = await feed_items.count()
        if count == 0:
            return None

        # Check top 3 items
        for i in range(min(count, 3)):
            item = feed_items.nth(i)
            aria = await item.get_attribute("aria-label")
            if not aria:
                h_name = item.locator('.qBF1Pd')
                if await h_name.count() > 0:
                    aria = await h_name.first.inner_text()

            if aria:
                valid, m_type = is_valid_name_match_sk(company_name, aria.strip())
                if valid:
                    await item.click()
                    await page.wait_for_timeout(2500)
                    phone, web, gmap_addr = await extract_details_from_panel(page)
                    addr_ok, addr_reason = check_address_compatibility(file_address, gmap_addr)
                    if not addr_ok:
                        continue
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
    print("🚀 BẮT ĐẦU QUY TRÌNH LÀM GIÀU DỮ LIỆU Ô TÔ (SK_AUTO_SLVD_0RAW -> 1ENR)")
    print("=====================================================================")

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp đầu vào: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Tổng số doanh nghiệp ô tô cần làm giàu: {len(rows):,} công ty")

    cache = load_cache()
    cached_count = len(cache)
    print(f"[*] Đã tải Cache: {cached_count:,} công ty đã có dữ liệu trước đó.")

    # Initialize output rows
    output_rows = []
    need_process = []

    for r in rows:
        ico = str(r.get('IČO', '')).strip()
        cname = str(r.get('Công ty', '')).strip()
        cache_key = ico if ico else cname.lower()
        c_data = cache.get(cache_key, {})

        if c_data.get('phone') and not r.get('SĐT'):
            r['SĐT'] = c_data['phone']
        if c_data.get('website') and not r.get('Web'):
            r['Web'] = c_data['website']
        if c_data.get('email') and not r.get('Email'):
            r['Email'] = c_data['email']

        # Nếu đã có Email B2B hoặc đã được kiểm tra Maps trước đó -> hoàn tất
        if r.get('Email') or c_data.get('gmap_checked'):
            output_rows.append(r)
        else:
            need_process.append(r)

    print(f"[*] Đã hoàn tất sẵn (Có Email hoặc đã kiểm tra): {len(output_rows):,} công ty")
    print(f"[*] Cần xử lý tiếp qua Google Maps & Web: {len(need_process):,} công ty\n")

    if not need_process:
        print("[V] Toàn bộ công ty đã được làm giàu! Đang ghi file xuất...")
        save_output_csv(output_rows, fieldnames)
        print(f"[V] Hoàn tất: {OUTPUT_CSV}")
        return

    # Start Playwright & HTTP Session
    session = AsyncSession() if HAS_CURL_CFFI else aiohttp.ClientSession()

    async with async_playwright() as p:
        # headless=False per Rule 4 and enrich-maps standard
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--window-size=1280,850"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 850},
            locale="sk-SK",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Prime Google Maps
        print("[*] Đang khởi động Google Maps...")
        try:
            await page.goto("https://www.google.com/maps?hl=sk", timeout=30000)
            await page.wait_for_timeout(2000)
            await bypass_google_consent(page)
        except Exception:
            pass

        processed_batch = 0

        for idx, r in enumerate(need_process, 1):
            ico = str(r.get('IČO', '')).strip()
            cname = str(r.get('Công ty', '')).strip()
            city = str(r.get('Thành phố', '')).strip()
            file_addr = str(r.get('Địa chỉ', '')).strip()
            cache_key = ico if ico else cname.lower()

            print(f"[{idx}/{len(need_process)}] Tra cứu: {cname} ({city}) | IČO: {ico}...")

            phone = r.get('SĐT', '')
            website = r.get('Web', '')
            gmap_res = None

            # 1. Nếu chưa có Website -> Tra cứu Google Maps
            if not website:
                gmap_res = await search_google_maps_for_company(page, cname, file_addr)
                if gmap_res:
                    if not phone:
                        phone = gmap_res.get('phone', '')
                    website = gmap_res.get('website', '')
                    print(f"    -> [Maps Khớp ({gmap_res['match_type']})] SĐT: {phone or 'N/A'} | Web: {website or 'N/A'}")
                else:
                    print(f"    -> [Maps Không tìm thấy/Không khớp]")

            # 2. Fallback to DuckDuckGo if website not found on Maps
            if not website:
                website = await search_duckduckgo_for_website(cname, city, session)
                if website:
                    print(f"    -> [Web Fallback Khớp] Web: {website}")
            else:
                if not gmap_res:
                    print(f"    -> [Đã có sẵn Website] Web: {website}")

            # 3. Crawl Website for B2B Email if website is found
            email = ""
            if website:
                email = await crawl_website_for_contacts(website, session)
                if email:
                    print(f"    -> [Email B2B Tuyển Chọn] {email}")
                else:
                    print(f"    -> [Website không có Email B2B]")

            # Phone formatting with '
            if phone:
                phone = f"'{phone}" if not phone.startswith("'") else phone

            # Update row
            if phone and not r.get('SĐT'):
                r['SĐT'] = phone
            if website and not r.get('Web'):
                r['Web'] = website
            if email and not r.get('Email'):
                r['Email'] = email

            # Update cache
            cache[cache_key] = {
                "name": cname,
                "ico": ico,
                "phone": phone,
                "website": website,
                "email": email or r.get('Email', ''),
                "gmap_checked": True,
                "updated_at": datetime.now().isoformat()
            }
            save_cache(cache)

            processed_batch += 1
            if processed_batch % 5 == 0:
                # Lưu toàn bộ 1.513 công ty để đảm bảo không mất dòng chưa duyệt
                save_output_csv(rows, fieldnames)
                count_with_email = sum(1 for x in rows if x.get('Email'))
                print(f"    [+] Auto-save checkpoint: Đã lưu {len(rows)} công ty (Hiện có {count_with_email} Email) vào {OUTPUT_CSV}")

            await asyncio.sleep(1.5)

        # Final save
        save_output_csv(rows, fieldnames)
        await browser.close()

    if not HAS_CURL_CFFI:
        await session.close()

    print("\n=====================================================================")
    print(f"🎉 HOÀN TẤT LÀM GIÀU DỮ LIỆU Ô TÔ!")
    print(f"📁 Tệp kết quả: {OUTPUT_CSV}")
    print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(run_enrichment())
