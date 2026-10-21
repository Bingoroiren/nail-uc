# -*- coding: utf-8 -*-
"""
Bing Web Search & Deep Email/Phone Enrichment for SK_UDZC_UPSV_2COL.csv (Slovakia SZU Employment Agencies):
1. Tim kiem Website chinh thuc cua doanh nghiep qua Bing Search theo Ten Thuong Hieu tai Slovakia.
2. SO KHOP BRAND & DOMAIN NGHIEM NGAT:
   - Loc bo 100% domain danh ba, dang ky kinh doanh, so vang, mang xa hoi (finstat, zrsr, orsr, azet, zlatestranky, profesia...).
   - So khop Brand Token trong Domain hoac Tieu de ket qua tim kiem.
3. Quet website tim Email B2B va So dien thoai (tel:):
   - Uu tien the <a> thuc te tren DOM menu (Priority 10: /kontakt, /kontakty, /o-nas, /kariera, /praca...).
   - Giai ma Cloudflare data-cfemail, mailto:, regex obfuscation.
   - Cham diem B2B tuyen chon 1 email co gia tri nhat (HR/Tuyen dung: praca@, kariera@, hr@; Lanh dao: vedenie@, riaditel@; Lien he: info@, kontakt@).
   - Boc tach So dien thoai (luon co dau nhay don ' o dau).
4. Luu tang dan (Incremental Auto-Save) sau moi 5 cong ty va Cache Checkpoint JSON (Resume 100%).
"""

import sys
import os
import re
import csv
import json
import time
import base64
import asyncio
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

# UTF-8 encoding for Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_bing_sk_udzc.json")

# Hau to phap ly Slovakia
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

# Bo loc loai bo domain danh ba / dang ky kinh doanh / review / mang xa hoi
EXCLUDED_KEYWORDS = [
    'finstat.sk', 'zrsr.sk', 'orsr.sk', 'profesia.sk', 'kariera.zoznam.sk',
    'azet.sk', 'zlatestranky.sk', 'indexpodnikatela.sk', 'foaf.sk', 'vzdelavanie.sk',
    'portal.gov.sk', 'yellowpages', 'tripadvisor', 'facebook', 'instagram',
    'linkedin', 'twitter', 'x.com', 'youtube', 'tiktok', 'pinterest', 'wikipedia',
    'google', 'bing.com', 'cybo.com', 'kompass', 'cylex', 'tupalo', 'webwiki',
    'unilocal', 'firmy.sk', 'zoznam.sk', 'edb.sk', 'goldenpages', 'najdi-ma.sk',
    'infobel', 'dnb.com', 'zoominfo', 'firmensicht', 'opencorporates'
]

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

DOMAIN_CACHE = {}

def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def decode_bing_url(href):
    """Giai ma link redirect b_algo cua Bing ve URL that voi base64 padding chuan."""
    if not href:
        return ""
    if '/ck/a?' in href:
        try:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            u = p.get('u', [''])[0]
            if u.startswith('a1'):
                b64 = u[2:]
                padding = (4 - len(b64) % 4) % 4
                padded_b64 = b64 + '=' * padding
                return base64.urlsafe_b64decode(padded_b64.encode('ascii')).decode('utf-8', errors='ignore')
        except Exception:
            return ""
    return href

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email.strip().lower()
    except Exception:
        return ""

def score_email_b2b(email, website_domain=""):
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

    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe']):
        return -1

    score = 10

    # Trung domain website (+50d)
    if website_domain and (d == website_domain or d.endswith('.' + website_domain)):
        score += 50
    if d.endswith('.sk'):
        score += 20
    elif d.endswith('.cz') or d.endswith('.eu'):
        score += 10

    # Uu tien 1: Nhan su / Tuyen dung (+50d)
    if any(k in u for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    # Uu tien 2: Ban Giam doc / Lanh dao (+45d)
    elif any(k in u for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # Uu tien 3: Cong lien he chinh thuc (+40d)
    elif any(k in u for k in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria']):
        score += 40
    elif '.' in u:
        score += 25
    elif d in {'gmail.com', 'azet.sk', 'centrum.sk', 'zoznam.sk', 'post.sk', 'seznam.cz'}:
        score += 10
    else:
        score += 5

    return score

async def fetch_html_resilient(url, session, max_retries=2):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7'
    }
    for attempt in range(max_retries):
        try:
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=12, verify=False)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)
    return ""

def is_valid_company_website(url, company_name):
    if not url or not url.startswith(('http://', 'https://')):
        return False
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    # Loc bo domain danh ba
    for excl in EXCLUDED_KEYWORDS:
        if excl in domain:
            return False

    clean_name = clean_company_name_sk(company_name)
    tokens = [t for t in clean_name.split() if len(t) >= 4 and not t.isdigit()]
    if not tokens:
        tokens = [clean_name] if len(clean_name) >= 3 else []

    # So khop Brand Token trong Domain
    # Vi du: "synergie" trong "synergie.sk"
    domain_clean = re.sub(r'[^a-z0-9]', '', domain.split('.')[0])
    for token in tokens:
        tok_clean = re.sub(r'[^a-z0-9]', '', token)
        if len(tok_clean) >= 4 and tok_clean in domain_clean:
            return True

    # Neu domain .sk va chua ten viet lien
    clean_combined = re.sub(r'[^a-z0-9]', '', clean_name)
    if len(clean_combined) >= 5 and clean_combined[:10] in domain_clean:
        return True

    return False

async def search_bing_for_company_website(company_name, city, session):
    clean_name = clean_company_name_sk(company_name)
    if not clean_name or len(clean_name) < 3:
        return ""

    query = f'"{clean_name}" Slovakia'
    bing_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&setlang=sk"

    html = await fetch_html_resilient(bing_url, session)
    if not html:
        return ""

    soup = BeautifulSoup(html, 'html.parser')
    results = soup.select('li.b_algo h2 a')

    for a in results[:5]:
        raw_href = a.get('href', '')
        real_url = decode_bing_url(raw_href)
        if real_url and is_valid_company_website(real_url, company_name):
            parsed = urllib.parse.urlparse(real_url)
            root_url = f"{parsed.scheme}://{parsed.netloc}"
            return root_url

    return ""

def extract_contacts_from_html(html_text, website_domain=""):
    if not html_text:
        return set(), ""
    emails = set()
    phone = ""

    # Cloudflare
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if score_email_b2b(dec, website_domain) >= 0:
            emails.add(dec)

    # mailto:
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) >= 0:
            emails.add(clean_m)

    # regex
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) >= 0:
            emails.add(clean_m)

    # tel: links
    tel_matches = re.findall(r'href=["\']tel:\s*([^"\'#\s]+)', html_text, re.IGNORECASE)
    for tm in tel_matches:
        raw_p = urllib.parse.unquote(tm).strip()
        digits = re.sub(r'\D', '', raw_p)
        if len(digits) >= 8:
            phone = raw_p
            break

    return emails, phone

async def crawl_website(website_url, session):
    if not website_url or not website_url.startswith(('http://', 'https://')):
        return "", ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')

    if domain in DOMAIN_CACHE:
        return DOMAIN_CACHE[domain].get("email", ""), DOMAIN_CACHE[domain].get("phone", "")

    all_emails = set()
    found_phone = ""

    subpaths = [
        "", "/kontakt", "/kontakty", "/kontakt.html", "/kontakty.html",
        "/o-nas", "/o-nas.html", "/onas", "/kariera", "/praca", "/contact"
    ]

    for sp in subpaths:
        target = urllib.parse.urljoin(website_url, sp)
        html_content = await fetch_html_resilient(target, session)
        if not html_content:
            continue

        ems, ph = extract_contacts_from_html(html_content, domain)
        all_emails.update(ems)
        if ph and not found_phone:
            found_phone = ph

        if any(domain in e for e in all_emails):
            break

    best_email = ""
    if all_emails:
        sorted_emails = sorted(list(all_emails), key=lambda e: score_email_b2b(e, domain), reverse=True)
        best_email = sorted_emails[0]

    DOMAIN_CACHE[domain] = {"email": best_email, "phone": found_phone}
    return best_email, found_phone

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

def save_csv_and_sort(rows, fieldnames):
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

    temp = INPUT_CSV + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
    if os.path.exists(INPUT_CSV):
        os.remove(INPUT_CSV)
    os.rename(temp, INPUT_CSV)

async def run_enrichment():
    print("="*75)
    print("BAT DAU LAM GIAU DU LIEU BING SEARCH + DEEP WEB CHO SK_UDZC_UPSV_2COL.CSV")
    print("NGUON TIM KIEM: BING WEB SEARCH (TIM WEBSITE CHINH THUC -> QUET CONTACT)")
    print("="*75)

    rows = []
    fieldnames = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)

    print(f"Tong so doanh nghiep hoat dong: {len(rows)}")

    cache = load_cache()
    print(f"Da nap cache: {len(cache)} doanh nghiep da xu ly.")

    # Identify rows to enrich: no email or no phone/web
    to_enrich = []
    for idx, r in enumerate(rows):
        c_name = r.get('Công ty', '').strip()
        if not c_name:
            continue
        has_email = bool(r.get('Email', '').strip())
        has_phone = bool(r.get('SĐT', '').strip())
        has_web = bool(r.get('Liên Hệ', '').strip())
        if not (has_email and has_phone and has_web):
            to_enrich.append(idx)

    print(f"So luong doanh nghiep can lam giau: {len(to_enrich)}")

    async with AsyncSession() as session:
        processed_since_save = 0

        for i, row_idx in enumerate(to_enrich, 1):
            r = rows[row_idx]
            company_name = r.get('Công ty', '').strip()
            addr = r.get('Địa chỉ', '').strip()
            city = addr.split(',')[0].strip() if addr else ""

            if company_name in cache:
                c_data = cache[company_name]
                if c_data.get('phone') and not r.get('SĐT'):
                    p_val = c_data['phone']
                    r['SĐT'] = f"'{p_val}" if not p_val.startswith("'") else p_val
                if c_data.get('website') and not r.get('Liên Hệ'):
                    r['Liên Hệ'] = c_data['website']
                if c_data.get('email') and not r.get('Email'):
                    r['Email'] = c_data['email']
                continue

            print(f"\n[{i}/{len(to_enrich)}] Tim kiem Web: '{company_name}' ({city})")

            # 1. Tim Website
            existing_web = r.get('Liên Hệ', '').strip()
            web_url = existing_web if existing_web and existing_web.startswith(('http://', 'https://')) else ""

            if not web_url:
                web_url = await search_bing_for_company_website(company_name, city, session)
                if web_url:
                    r['Liên Hệ'] = web_url
                    print(f"  [+] TIM THAY WEB CHINH THUC: {web_url}")
                else:
                    print("  [-] Khong tim thay website phu hop")

            # 2. Quet Website de lay Email va SDT
            found_email = ""
            found_phone = ""
            if web_url:
                email, phone = await crawl_website(web_url, session)
                if email and not r.get('Email'):
                    r['Email'] = email
                    found_email = email
                    print(f"  -> EMAIL B2B: {email}")
                if phone and not r.get('SĐT'):
                    p_val = phone
                    r['SĐT'] = f"'{p_val}" if not p_val.startswith("'") else p_val
                    found_phone = p_val
                    print(f"  -> SDT: {p_val}")

            cache[company_name] = {
                "website": r.get('Liên Hệ', ''),
                "email": r.get('Email', ''),
                "phone": r.get('SĐT', ''),
                "timestamp": datetime.now().isoformat()
            }
            save_cache(cache)

            processed_since_save += 1
            if processed_since_save >= 5:
                save_csv_and_sort(rows, fieldnames)
                print(f"  [Auto-save] Da luu tang dan vao CSV.")
                processed_since_save = 0

            await asyncio.sleep(1.0)

        # Final save
        save_csv_and_sort(rows, fieldnames)
        print(f"\n[HOAN TAT] Hoan thanh toan bo quy trinh lam giau du lieu!")

if __name__ == '__main__':
    asyncio.run(run_enrichment())
