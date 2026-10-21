# -*- coding: utf-8 -*-
"""
Google Maps & Deep Web Enrichment for AT_AGCY_SHET_0RAW.csv (Austria Manpower & Recruitment Agencies):
1. Tra cuu Google Maps (hl=de, headless=False) theo Ten Cong ty tai Ao (Austria).
2. So khop ten nghiem ngat (Exact match, Delimiter match, Bracket match, loai bo legal forms Ao: GmbH, AG, e.U., KG, OG, GesmbH...).
3. Boc tach So dien thoai (luon co dau nhay don ' o dau), Website chinh thuc, Dia chi.
4. Quet website tim email B2B da tang:
   - mailto: (giai ma %20), regex, Cloudflare data-cfemail, Obfuscated email.
   - Uu tien the <a> thuc te tren DOM menu (Priority 10: /kontakt, /impressum, /ueber-uns, /karriere, /jobs...).
   - Doan mo ban dia Ao/Duc (Priority 2) sau khi het link DOM.
   - Fallback Fanpage Facebook neu Website khong co email truc tiep tren web.
   - Heuristic scoring: Tuyen chon DUY NHAT 1 email B2B co gia tri nhat (uu tien HR/Tuyendung, Lanh dao, Cổng liên hệ chính thức).
5. Luu tang dan (Incremental Auto-Save) sau moi cong ty va Checkpoint JSON (Resume 100%).
6. Dau ra tieu chuan: AT_AGCY_SHET_1ENR.csv (tuan thu quy chuan dat ten 17 ky tu).
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
INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
BACKUP_CSV = str(ROOT_DIR / "AT_AGCY_SHET_0RAW_backup.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_at_agcy_shet.json")

# Danh sach hau to loai hinh doanh nghiep Ao (Austria Legal Forms)
LEGAL_FORMS_AT = [
    'gesellschaft mit beschränkter haftung', 'gesellschaft mit beschrankter haftung',
    'gmbh & co. kg', 'gmbh & co kg', 'gmbh & co.kg', 'gmbh & co',
    'gesellschaft m.b.h.', 'gesellschaft mbh', 'ges.m.b.h.', 'gesmbh', 'ges. mbh',
    'gmbh', 'g.m.b.h.',
    'aktiengesellschaft', 'ag', 'a.g.',
    'offene gesellschaft', 'og', 'o.g.',
    'kommanditgesellschaft', 'kg', 'k.g.',
    'eingetragenes einzelunternehmen', 'eingetragene unternehmerin', 'e.u.', 'eu',
    'societas europaea', 'se',
    'genossenschaft', 'egen', 'e.gen.',
    'holding', 'group', 'gruppe'
]

# Danh sach domain rac / directory loai tru
EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'google.com', 'google.at', 'maps.google.com', 'apple.com',
    'firmenabc.at', 'wko.at', 'herold.at', 'docfinder.at', 'karriere.at',
    'stepstone.at', 'monster.at', 'willhaben.at', 'gelbeseiten.de',
    'gelbeseiten.at', 'yellowpages', 'tripadvisor'
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
    'yourcompany.com', 'yourdomain.com', 'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe', 'user'
}

TEMPLATE_USERNAMES = {'info@yourcompany.com', 'email@example.com'}

DOMAIN_EMAIL_CACHE = {}

def clean_company_name_at(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_AT, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def is_valid_name_match_at(query_name, candidate_name):
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

    q_clean = clean_company_name_at(query_name)
    c_clean = clean_company_name_at(candidate_name)
    if len(q_clean) >= 3 and q_clean == c_clean:
        return True, "EXACT_CORE"

    c_nobrackets_clean = clean_company_name_at(c_nobrackets)
    if len(q_clean) >= 3 and q_clean == c_nobrackets_clean:
        return True, "BRACKET_CORE"

    parts_clean = [clean_company_name_at(p) for p in parts if clean_company_name_at(p)]
    if len(q_clean) >= 3 and any(p == q_clean for p in parts_clean):
        return True, "DELIMITER_CORE"

    return False, "NO_MATCH"

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email.strip().lower()
    except Exception:
        return ""

def score_email_b2b(email, website_domain=""):
    """
    Cham diem email B2B cho Agency Manpower / Recruitment tai Ao.
    Tuyen chon duy nhat 1 email co gia tri nhat, loai bo 100% email rac/template.
    """
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1
        
    parts = e.split('@')
    if len(parts) != 2:
        return -1
    u, d = parts[0], parts[1]

    # 1. Loc bo rac he thong & template demo
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe']):
        return -1
    if u in ['email', 'mail'] and d in ['email.com', 'mail.com', 'domain.com', 'company.com']:
        return -1

    score = 10

    # 2. Trung domain website (+50d)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50
    elif d.endswith('.at'):
        score += 20
    elif d.endswith('.de') or d.endswith('.eu'):
        score += 10

    # 3. UU TIEN SO 1: Bo phan Nhan su / Tuyen dung / Viec lam (+50d)
    # Dat muc tieu tiep can truc tiep nguoi phu trach cung ung / tuyen dung lao dong
    hr_keywords = [
        'karriere', 'jobs', 'bewerbung', 'recruiting', 'recruitment', 'hr', 'personal',
        'personalne', 'praca', 'talent', 'people', 'career', 'careers', 'hiring'
    ]
    if any(u == k or u.startswith(k) for k in hr_keywords):
        score += 50
    # 4. UU TIEN SO 2: Ban Giam Doc / Lanh dao dieu hanh (+45d)
    elif any(u == k or u.startswith(k) for k in ['geschaeftsfuehrung', 'leitung', 'ceo', 'director', 'manager', 'vertrieb', 'sales', 'management', 'inhaber', 'vorstand']):
        score += 45
    # 5. UU TIEN SO 3: Cong lien he chinh thuc / Van phong B2B (+40d)
    elif any(u == k or u.startswith(k) for k in ['office', 'kontakt', 'contact', 'info', 'zentrale', 'empfang', 'sekretariat', 'kaufmaennisch', 'mail', 'post']):
        score += 40
    # 6. Email ca nhan theo domain rieng (+25d)
    elif '.' in u and score >= 60:
        score += 25
    # 7. Webmail mien phi (+10d)
    elif d in ['gmail.com', 'gmx.at', 'aon.at', 'chello.at', 'web.de', 'yahoo.com']:
        score += 10
    # 8. Email ky thuat / ke toan (+5d)
    elif any(u == k or u.startswith(k) for k in ['support', 'admin', 'hilfe', 'service', 'buchhaltung', 'rechnung', 'faktury']):
        score += 5

    return score

def select_best_email(found_emails, website_domain=""):
    valid_emails = [e for e in set(found_emails) if score_email_b2b(e, website_domain) > 0]
    if not valid_emails:
        return ""
    return max(valid_emails, key=lambda e: score_email_b2b(e, website_domain))

async def fetch_html(url, session):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }
    try:
        if HAS_CURL_CFFI:
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=12, verify=False)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12), ssl=False) as resp:
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
        if score_email_b2b(dec, website_domain) > 0:
            found.add(dec)

    # 2. mailto: links (loai bo %20 va query)
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) > 0:
            found.add(clean_m)

    # 3. Regex standard
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) > 0:
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
            if score_email_b2b(rec, website_domain) > 0:
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

    # Fetch Trang chu
    home_html = await fetch_html(website_url, session)
    if home_html:
        emails = extract_emails_from_html(home_html, domain)
        all_emails.update(emails)

    # Priority 10: Tim link that tren Menu / DOM Trang Chu
    candidate_links = []
    if home_html:
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                text = (a.get_text() or "").strip().lower()
                href_lower = href.lower()

                # Facebook detection
                if not fb_link and any(fb in href_lower for fb in ['facebook.com/', 'fb.com/']):
                    if not any(x in href_lower for x in ['sharer', 'share.php', 'plugins', 'intent', 'dialog']):
                        clean_fb = href.split('?')[0].rstrip('/')
                        if len(clean_fb.split('/')) > 3:
                            fb_link = clean_fb

                full_url = urllib.parse.urljoin(website_url, href)
                parsed_cand = urllib.parse.urlparse(full_url)
                if parsed_cand.netloc.replace('www.', '') == domain:
                    clean_cand = full_url.split('#')[0]
                    priority = 1
                    # Priority 10: Ban dia hoa Ao/Duc cho Nhan su va Lien he
                    if any(k in text or k in href_lower for k in [
                        'kontakt', 'impressum', 'karriere', 'jobs', 'bewerbung',
                        'ueber-uns', 'wir-ueber-uns', 'anfahrt', 'team', 'standort', 'contact'
                    ]):
                        priority = 10
                    elif any(k in text or k in href_lower for k in ['uber-uns', 'about', 'dienstleistungen', 'service']):
                        priority = 5
                    candidate_links.append((priority, clean_cand))
        except Exception:
            pass

    # Priority 2: Guess paths ban dia Ao/Duc
    parsed_base = urllib.parse.urlparse(website_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    guess_paths = [
        '/kontakt', '/kontakt.html', '/kontakt.php',
        '/impressum', '/impressum.html', '/impressum.php',
        '/karriere', '/karriere.html', '/jobs',
        '/ueber-uns', '/ueber-uns.html', '/contact'
    ]
    for gp in guess_paths:
        candidate_links.append((2, base_origin + gp))

    # Sap xep theo priority giam dan
    candidate_links.sort(key=lambda x: x[0], reverse=True)
    unique_sub_urls = []
    for prio, sub_url in candidate_links:
        clean_sub = sub_url.rstrip('/')
        if clean_sub not in [u.rstrip('/') for u in unique_sub_urls] and clean_sub != website_url.rstrip('/'):
            unique_sub_urls.append(sub_url)

    # Quet toi da 8 subpages
    for sub_url in unique_sub_urls[:8]:
        sub_html = await fetch_html(sub_url, session)
        if not sub_html:
            continue
        sub_emails = extract_emails_from_html(sub_html, domain)
        all_emails.update(sub_emails)

        # Neu tim thay email trung domain co diem so cao, dung som
        best_cand = select_best_email(all_emails, domain)
        if best_cand and score_email_b2b(best_cand, domain) >= 60:
            break

    # Fallback Facebook Fanpage neu website khong co email
    best_email = select_best_email(all_emails, domain)
    if not best_email and fb_link:
        fb_about = fb_link + "/about"
        fb_html = await fetch_html(fb_about, session)
        if fb_html:
            fb_emails = extract_emails_from_html(fb_html, domain)
            all_emails.update(fb_emails)
            best_email = select_best_email(all_emails, domain)

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

def save_csv(rows, fieldnames, filepath):
    temp = filepath + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
    os.rename(temp, filepath)

async def bypass_google_consent(page):
    try:
        btns = page.locator(
            'button:has-text("Alle akzeptieren"), button:has-text("Ich stimme zu"), '
            'button:has-text("Accept all"), button:has-text("I agree"), '
            'form:has(button) button:has-text("Alle akzeptieren")'
        )
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
        print("[!] CAPTCHA PHÁT HIỆN TRÊN GOOGLE MAPS! Vui lòng giải captcha trên trình duyệt...")
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

async def search_google_maps_for_company(page, company_name):
    clean_name = re.sub(r'["\'„“”«»]', '', company_name).strip()
    query = f"{clean_name}, Austria"
    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}?hl=de"

    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception:
        return None

    await handle_captcha(page)
    await bypass_google_consent(page)

    current_url = page.url

    # Case 1: Direct place panel
    if "/maps/place/" in current_url:
        h1 = page.locator('h1.DUwDvf')
        cand_name = (await h1.first.inner_text()).strip() if await h1.count() > 0 else ""
        valid, m_type = is_valid_name_match_at(clean_name, cand_name)
        if valid:
            phone, web, addr = await extract_details_from_panel(page)
            return {"name": cand_name, "phone": phone, "website": web, "address": addr, "match_type": m_type}
        return None

    # Case 2: Search feed
    link_selector = 'a.hfpxzc'
    links = page.locator(link_selector)
    count = await links.count()
    if count == 0:
        return None

    for i in range(min(count, 3)):
        cand_elem = links.nth(i)
        cand_aria = await cand_elem.get_attribute("aria-label") or ""
        valid, m_type = is_valid_name_match_at(clean_name, cand_aria)
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

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay file nguon: {INPUT_CSV}")
        return

    # Sao luu file truoc khi xu ly
    import shutil
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[*] Da sao luu {INPUT_CSV} sang {BACKUP_CSV}")

    cache = load_cache()

    # Resume: Neu OUTPUT_CSV da ton tai, tiep tuc tu OUTPUT_CSV
    read_file = OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV
    print(f"[*] Dang doc du lieu tu: {read_file}")

    with open(read_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # Chuan hoa SĐT co dau nhay don ' cho tat ca cac dong hien co
    for r in rows:
        p = r.get("SĐT", "").strip()
        if p and not p.startswith("'"):
            r["SĐT"] = f"'{p}"

    total_rows = len(rows)
    print("=" * 80)
    print("LAM GIAU DU LIEU GOOGLE MAPS & DEEP WEB CHO AT_AGCY_SHET_0RAW.CSV")
    print(f"Tong so doanh nghiep: {total_rows}")
    print(f"File xuat chuan: {OUTPUT_CSV}")
    print("=" * 80)

    session = AsyncSession(verify=False) if HAS_CURL_CFFI else aiohttp.ClientSession()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="de-AT",
            geolocation={"latitude": 48.2082, "longitude": 16.3738},
            permissions=["geolocation"]
        )
        page = await context.new_page()

        enriched_count = 0
        for idx, row in enumerate(rows):
            company = row.get("Công ty", "").strip()
            curr_phone = row.get("SĐT", "").strip()
            curr_web = row.get("Liên Hệ", "").strip()
            curr_email = row.get("Email", "").strip()

            needs_phone = not curr_phone
            needs_web = not curr_web
            needs_email = not curr_email

            # Neu da du thong tin: bo qua
            if not needs_phone and not needs_web and not needs_email:
                continue

            print(f"\n[{idx+1}/{total_rows}] [*] Doanh nghiep: '{company}'")

            updated = False

            # Buoc 1: Neu da co Website nhung thieu Email -> Quet Website truoc
            if not curr_email and curr_web:
                print(f"    [*] Da co Website: {curr_web} -> Dang quet tim Email B2B...")
                found_email, fb = await crawl_website_for_contacts(curr_web, session)
                if found_email:
                    row["Email"] = found_email
                    print(f"       [+] Web Email B2B tim thay: {found_email}")
                    updated = True
                    needs_email = False

            # Buoc 2: Neu van con thieu Website hoac Phone -> Tim kiem tren Google Maps
            if needs_web or needs_phone:
                print(f"    [*] Tra cuu Google Maps cho: '{company}'...")
                cache_key = company.upper()
                maps_res = cache.get(cache_key)
                if not maps_res:
                    maps_res = await search_google_maps_for_company(page, company)
                    cache[cache_key] = maps_res if maps_res else {"not_found": True}
                    save_cache(cache)
                    await asyncio.sleep(1.0)

                if maps_res and not maps_res.get("not_found"):
                    m_phone = maps_res.get("phone", "")
                    m_web = maps_res.get("website", "")
                    m_addr = maps_res.get("address", "")
                    m_type = maps_res.get("match_type", "")

                    print(f"    [Maps Found] '{maps_res.get('name')}' ({m_type})")
                    if m_phone and needs_phone:
                        row["SĐT"] = m_phone
                        print(f"       Phone  : {m_phone}")
                        updated = True
                    if m_web and needs_web:
                        row["Liên Hệ"] = m_web
                        print(f"       Website: {m_web}")
                        updated = True
                    if m_addr and not row.get("Địa chỉ", "").strip():
                        row["Địa chỉ"] = m_addr
                        print(f"       Address: {m_addr}")
                        updated = True

                    # Buoc 3: Neu vua tim thay Website moi tu Maps va van thieu Email -> Quet Website
                    effective_web = row.get("Liên Hệ", "").strip()
                    if needs_email and effective_web:
                        print(f"    [*] Dang quet sau Website moi tim Email B2B: {effective_web}...")
                        found_email, fb = await crawl_website_for_contacts(effective_web, session)
                        if found_email:
                            row["Email"] = found_email
                            print(f"       [+] Maps Web Email tim thay: {found_email}")
                            updated = True

            if updated:
                enriched_count += 1
                save_csv(rows, fieldnames, OUTPUT_CSV)
                print(f"    [+] CAP NHAT THANH CONG: {company}")
            else:
                print(f"    [-] Khong tim thay them thong tin moi.")

            # Dinh ky luu checkpoint
            if (idx + 1) % 5 == 0:
                save_csv(rows, fieldnames, OUTPUT_CSV)

        await browser.close()

    if not HAS_CURL_CFFI:
        await session.close()

    save_csv(rows, fieldnames, OUTPUT_CSV)
    print("\n" + "=" * 80)
    print("HOAN TAT LAM GIAU DU LIEU GOOGLE MAPS & DEEP WEB!")
    print(f"Tong so doanh nghiep duoc bo sung thong tin: {enriched_count}")
    print(f"Tep xuat: {OUTPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
