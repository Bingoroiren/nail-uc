# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for slovakiaphilip.csv (Slovakia Employers):
1. Tra cuu Google Maps (hl=sk, headless=False) theo Ten Principal tai Slovakia.
2. So khop ten nghiem ngat (Exact match, Delimiter match, Bracket match, loai bo legal forms).
3. Boc tach So dien thoai (luon co dau nhay don ' o dau), Website chinh thuc, Dia chi.
4. Quet website tim email B2B da tang:
   - mailto:, regex, Cloudflare data-cfemail, Obfuscated email.
   - Quet subpages lien he theo do uu tien (/kontakt, /kontakty, /o-nas, /kariera, /contact...).
   - Fallback cao Fanpage Facebook neu Website khong co email.
   - Heuristic scoring: uu tien email lien he B2B chinh thuc (info@, kontakt@, office@, praca@...).
5. Luu tang dan (Incremental Auto-Save) sau moi cong ty va Checkpoint JSON (Resume 100%).
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

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "slovakiaphilip.csv")
BACKUP_CSV = str(ROOT_DIR / "slovakiaphilip_backup_before_maps.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_slovakiaphilip.json")

# Danh sach hau to loai hinh doanh nghiep Slovakia
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

# Danh sach domain rac / directory loai tru
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

def score_email(email, website_domain=None):
    e = email.lower()
    score = 0
    user = e.split('@')[0]
    domain = e.split('@')[1] if '@' in e else ''
    
    if website_domain and (domain == website_domain or domain.endswith('.' + website_domain)):
        score += 50
    if domain.endswith('.sk'):
        score += 20
    elif domain.endswith('.cz') or domain.endswith('.eu'):
        score += 10
        
    priority_users = ['info', 'kontakt', 'contact', 'office', 'praca', 'kariera', 'recruitment', 'personalne', 'hr', 'jobs']
    for idx, pu in enumerate(priority_users):
        if user == pu or user.startswith(pu):
            score += (30 - idx * 2)
            break
            
    if domain in {'gmail.com', 'azet.sk', 'centrum.sk', 'zoznam.sk', 'post.sk', 'seznam.cz'}:
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
    
    # 1. Cloudflare decode
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if is_valid_b2b_email(dec, website_domain):
            found.add(dec)
            
    # 2. mailto: links
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found.add(clean_m)
            
    # 3. Regex standard
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found.add(clean_m)
            
    # 4. Obfuscated
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
        return "", ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    if domain in DOMAIN_EMAIL_CACHE:
        return DOMAIN_EMAIL_CACHE[domain].get("email", ""), DOMAIN_EMAIL_CACHE[domain].get("facebook", "")

    all_emails = set()
    fb_link = ""

    # Subpages to check
    subpaths = [
        "", "/kontakt", "/kontakty", "/contact", "/contacts",
        "/o-nas", "/about", "/about-us", "/kariera", "/praca", "/career"
    ]

    for sp in subpaths:
        target = urllib.parse.urljoin(website_url, sp)
        html_content = await fetch_html(target, session)
        if not html_content:
            continue
            
        emails = extract_emails_from_html(html_content, domain)
        all_emails.update(emails)
        
        # Check facebook fanpage
        if not fb_link:
            soup = BeautifulSoup(html_content, 'html.parser')
            for a in soup.select('a[href*="facebook.com/"], a[href*="fb.com/"]'):
                href = a.get('href', '').strip()
                if not any(b in href.lower() for b in ['sharer', 'share.php', 'plugins', 'intent', 'dialog']):
                    clean_fb = href.split('?')[0].rstrip('/')
                    if 'facebook.com' in clean_fb and len(clean_fb.split('/')) > 3:
                        fb_link = clean_fb
                        break
                        
        # If found domain-matching email, can break early
        if any(domain in e for e in all_emails):
            break

    best_email = ""
    if all_emails:
        sorted_emails = sorted(list(all_emails), key=lambda e: score_email(e, domain), reverse=True)
        best_email = sorted_emails[0]

    DOMAIN_EMAIL_CACHE[domain] = {"email": best_email, "facebook": fb_link}
    return best_email, fb_link

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

def save_csv(rows, fieldnames):
    temp = INPUT_CSV + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
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
        print("[!] CAPTCHA PHÁT HIỆN! Vui lòng giải captcha trên trình duyệt...")
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha đã giải xong! Tiếp tục chạy...")
                break

async def search_google_maps_for_company(page, company_name):
    query = f"{company_name}, Slovakia"
    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}?hl=sk"
    
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception as e:
        return None

    await handle_captcha(page)
    await bypass_google_consent(page)

    current_url = page.url

    # Case 1: Redirected directly to place
    if "/maps/place/" in current_url:
        h1 = page.locator('h1.DUwDvf')
        cand_name = (await h1.first.inner_text()).strip() if await h1.count() > 0 else ""
        valid, m_type = is_valid_name_match_sk(company_name, cand_name)
        if valid:
            phone, web, addr = await extract_details_from_panel(page)
            return {"name": cand_name, "phone": phone, "website": web, "address": addr, "match_type": m_type}
        return None

    # Case 2: Feed of search results
    link_selector = 'a.hfpxzc'
    links = page.locator(link_selector)
    count = await links.count()
    if count == 0:
        return None

    # Check top 3 results
    for i in range(min(count, 3)):
        cand_elem = links.nth(i)
        cand_aria = await cand_elem.get_attribute("aria-label") or ""
        valid, m_type = is_valid_name_match_sk(company_name, cand_aria)
        if valid:
            try:
                await cand_elem.click()
                await page.wait_for_timeout(2500)
                await handle_captcha(page)
                phone, web, addr = await extract_details_from_panel(page)
                return {"name": cand_aria, "phone": phone, "website": web, "address": addr, "match_type": m_type}
            except Exception:
                continue

    return None

async def extract_details_from_panel(page):
    phone = ""
    website = ""
    address = ""

    # Phone
    try:
        p_btn = page.locator('button[data-item-id^="phone:tel:"]')
        if await p_btn.count() > 0:
            phone_raw = (await p_btn.first.inner_text()).strip()
            phone = re.sub(r'[^\d+]', '', phone_raw)
            if phone and not phone.startswith("'"):
                phone = f"'{phone}"
    except Exception:
        pass

    # Website
    try:
        w_btn = page.locator('a[data-item-id="authority"]')
        if await w_btn.count() > 0:
            website_raw = (await w_btn.first.get_attribute("href") or "").strip()
            # Verify not excluded
            p = urllib.parse.urlparse(website_raw)
            d = p.netloc.lower().replace('www.', '')
            if not any(ex in d for ex in EXCLUDED_DOMAINS):
                website = website_raw
    except Exception:
        pass

    # Address
    try:
        a_btn = page.locator('button[data-item-id^="address"]')
        if await a_btn.count() > 0:
            address = (await a_btn.first.inner_text()).strip()
    except Exception:
        pass

    return phone, website, address

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay {INPUT_CSV}")
        return

    # Backup
    import shutil
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    print(f"[*] Da sao luu {INPUT_CSV} sang {BACKUP_CSV}")

    cache = load_cache()

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    print("=" * 75)
    print("LAM GIAU DU LIEU GOOGLE MAPS & DEEP WEB CHO SLOVAKIAPHILIP.CSV")
    print(f"Tong so doanh nghiep: {len(rows)}")
    print("=" * 75)

    session = AsyncSession(verify=False) if HAS_CURL_CFFI else aiohttp.ClientSession()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="sk-SK",
            geolocation={"latitude": 48.1447, "longitude": 17.1128},
            permissions=["geolocation"]
        )
        page = await context.new_page()

        enriched_count = 0
        for idx, row in enumerate(rows):
            principal = row.get("Principal", "").strip()
            curr_phone = row.get("Phone", "").strip()
            curr_email = row.get("Email", "").strip()
            curr_web = row.get("Website", "").strip()
            curr_source = row.get("Data_Source", "")

            # Check if needs enrichment
            needs_phone = not curr_phone
            needs_web = not curr_web
            needs_email = not curr_email

            if not (needs_phone or needs_web or needs_email):
                print(f"[{idx+1}/{len(rows)}] [OK] {principal} -> Da co du Phone, Email, Website.")
                continue

            print(f"\n[{idx+1}/{len(rows)}] [*] Dang tim kiem Google Maps: '{principal}'...")

            # 1. Search Google Maps
            cache_key = principal.upper()
            maps_res = cache.get(cache_key)
            if not maps_res:
                maps_res = await search_google_maps_for_company(page, principal)
                cache[cache_key] = maps_res if maps_res else {"not_found": True}
                save_cache(cache)
                await asyncio.sleep(1.0)

            updated = False
            if maps_res and not maps_res.get("not_found"):
                m_phone = maps_res.get("phone", "")
                m_web = maps_res.get("website", "")
                m_addr = maps_res.get("address", "")
                m_type = maps_res.get("match_type", "")

                print(f"    [Maps Found] '{maps_res.get('name')}' ({m_type})")
                if m_phone:
                    print(f"       Phone  : {m_phone}")
                if m_web:
                    print(f"       Website: {m_web}")
                if m_addr:
                    print(f"       Address: {m_addr}")

                if needs_phone and m_phone:
                    row["Phone"] = m_phone
                    updated = True
                if needs_web and m_web:
                    row["Website"] = m_web
                    updated = True
                if not row.get("Address") and m_addr:
                    row["Address"] = m_addr
                    updated = True
                if updated:
                    row["Data_Source"] = "Google Maps"

            # 2. Deep Web Crawl if Website is available and Email is missing
            effective_web = row.get("Website", "").strip()
            if not row.get("Email") and effective_web:
                print(f"    [*] Dang quet sau Website tim Email B2B: {effective_web}...")
                found_email, fb = await crawl_website_for_contacts(effective_web, session)
                if found_email:
                    row["Email"] = found_email
                    row["Data_Source"] = f"{row.get('Data_Source', '')} + Website".strip(" +")
                    print(f"       [Web Email]: {found_email}")
                    updated = True

            if updated:
                enriched_count += 1
                save_csv(rows, fieldnames)
                print(f"    [+] CAP NHAT THANH CONG: {principal}")
            else:
                print(f"    [-] Khong tim thay thong tin bo sung moi cho: {principal}")

        await browser.close()

    if not HAS_CURL_CFFI:
        await session.close()

    save_csv(rows, fieldnames)
    print("\n" + "=" * 75)
    print("HOAN TAT LAM GIAU DU LIEU GOOGLE MAPS!")
    print(f"Tong so doanh nghiep duoc bo sung thong tin: {enriched_count}")
    print(f"File ket qua: {INPUT_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
