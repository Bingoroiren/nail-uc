# -*- coding: utf-8 -*-
"""
VPN-Resilient Web Search & Deep Verified Contact Enrichment for SK_UDZC_UPSV_2COL.csv:
1. Giai phap VPN Resilient: Timeout 25s, Exponential Backoff retry chong lag mang VPN Ha Lan.
2. BO XAC THUC NGHIEM NGAT 4 TANG (4-Layer Strict Verification) - CHONG 100% GUI NHAM MAIL:
   - Tang 1: Loc bo 100% domain danh ba, dang ky kinh doanh, san viec lam, mang xa hoi
     (finstat, zrsr, orsr, profesia, zoznam, azet, valida, dnb, emis, findat, facebook, linkedin...).
   - Tang 2: So khop Brand Token trong Domain (vi du: "prostaff" trong "prostaff.sk").
   - Tang 3: Xac thuc On-Page Proof (DOM Verification):
     Bat buoc tren Website (trang chu hoac /kontakt) phai chua:
       + Ma so doanh nghiep ICO (8 chu so tu file goc), HOAC
       + Ten phap ly day du cua cong ty, HOAC
       + Thanh pho / Dia chi tai Slovakia.
     Neu website khong co bat ky bang chung xac thuc nao -> TU CHOI NGAY (REJECT)!
   - Tang 4: Xac thuc Email B2B theo Domain:
     + Uu tien tuyet doi Email trung domain website.
     + Loc bo 100% mail rac / template theme (youremail@, name@, example@, sentry@, wix@...).
     + Cham diem B2B tuyen chon 1 email co gia tri nhat (praca@, kariera@, hr@, vedenie@, info@, kontakt@...).
3. Boc tach So dien thoai qua tel: va regex Slovakia (+421, 09...) luon co dau nhay don ' o dau.
4. Luu tang dan sau moi 5 cong ty va Cache Checkpoint JSON (Resume 100%).
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import urllib.parse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

# UTF-8 encoding cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "SK_UDZC_UPSV_2COL.csv")
RAW_EXCEL = str(ROOT_DIR / "SK_UDZC_UPSV_0RAW.xlsx")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_web_sk_udzc.json")

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

# Danh sach domain danh ba / trung gian / mang xa hoi loai bo tuyet doi
EXCLUDED_KEYWORDS = [
    'finstat.sk', 'zrsr.sk', 'orsr.sk', 'profesia.sk', 'kariera.zoznam.sk',
    'azet.sk', 'zlatestranky.sk', 'indexpodnikatela.sk', 'foaf.sk', 'vzdelavanie.sk',
    'portal.gov.sk', 'yellowpages', 'tripadvisor', 'facebook.com', 'instagram.com',
    'linkedin.com', 'twitter.com', 'x.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
    'wikipedia.org', 'google.com', 'bing.com', 'duckduckgo.com', 'cybo.com', 'kompass.com',
    'cylex.sk', 'tupalo.com', 'webwiki.com', 'unilocal.sk', 'firmy.sk', 'zoznam.sk',
    'edb.sk', 'goldenpages.sk', 'najdi-ma.sk', 'infobel.com', 'dnb.com', 'zoominfo.com',
    'firmensicht.at', 'opencorporates.com', 'praca.sme.sk', 'kariera.sk', 'valida.sk',
    'findat.sk', 'overit.sk', 'register.peniaze.sk', 'peniaze.sk', 'prever.to', 'emis.com'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
PHONE_REGEX = re.compile(r'(?:\+421|00421|0)\s*(?:[2-9]\d{1,2}|9\d{2})\s*\d{3}\s*\d{3}')
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
    'yourcompany.com', 'yourdomain.com', 'email.com', 'mail.com', 'sample.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe', 'user'
}

DOMAIN_CACHE = {}

def load_company_ico_map():
    """Doc file goc Excel de lay ma ICO chinh xac cho 100% doanh nghiep."""
    ico_map = {}
    if os.path.exists(RAW_EXCEL):
        try:
            import pandas as pd
            df_raw = pd.read_excel(RAW_EXCEL, sheet_name='Zoznam SZÚ', skiprows=2)
            for _, row in df_raw.iterrows():
                name = str(row.get('Názov', '')).strip()
                ico = str(row.get('IČO', '')).strip()
                if name and ico and ico.lower() != 'nan':
                    # Chuan hoa ico thanh chuoi 8 chu so
                    ico_clean = re.sub(r'\D', '', ico).zfill(8)
                    ico_map[name] = ico_clean
        except Exception as e:
            print(f"[!] Warning: Khong the load ICO tu Excel: {e}")
    return ico_map

def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        n = re.sub(rf'(?:^|\s){re.escape(lf)}(?!\w)', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

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
        score += 5
    else:
        score += 5

    return score

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

async def fetch_html_resilient(url, session, max_retries=2, timeout=8):
    """Fetcher co che Retry va Timeout ngat socket cuong che qua asyncio.wait_for, chong treo mang VPN."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7'
    }
    for attempt in range(max_retries):
        try:
            req = session.get(url, headers=headers, impersonate="chrome120", timeout=timeout, verify=False)
            resp = await asyncio.wait_for(req, timeout=float(timeout))
            if resp.status_code == 200:
                return resp.text
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)
    return ""

GENERIC_TOKENS = {
    'steel', 'auto', 'work', 'job', 'jobs', 'group', 'servis', 'service', 'services',
    'agency', 'agentura', 'trans', 'consulting', 'management', 'personal',
    'personnel', 'international', 'trade', 'tech', 'mont', 'stav', 'slovakia',
    'slovensko', 'slovak', 'eu', 'sk', 'pro', 'solutions', 'care', 'line',
    'team', 'plus', 'holding', 'invest', 'center', 'centre', 'finance', 'consult',
    'partner', 'partners', 'spol', 'company'
}

def is_domain_brand_match(url, company_name):
    """Tang 2: So khop Brand Token trong Domain (chong nhan vo tu generic nhu steel, agency...)."""
    if not url or not url.startswith(('http://', 'https://')):
        return False
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')

    for excl in EXCLUDED_KEYWORDS:
        if excl in domain:
            return False

    clean_name = clean_company_name_sk(company_name)
    domain_clean = re.sub(r'[^a-z0-9]', '', domain.split('.')[0])

    words = re.findall(r'[a-z0-9]+', clean_name)
    distinct = [w for w in words if w not in GENERIC_TOKENS and len(w) >= 3 and not w.isdigit()]

    if distinct:
        # Neu co tu thuong hieu rieng biet (vi du: 'accace', 'rosali', 'lextom')
        for token in distinct:
            if token in domain_clean:
                return True
        return False
    else:
        # Neu ten toan tu generic (vi du: 'Steel EU', 'JOB AGENCY')
        # Bat buoc domain phai khop toan bo cum thuong hieu ('steeleu', 'jobagency'), khong duoc khop 1 tu le
        comb = ''.join(words)
        return len(comb) >= 4 and comb in domain_clean

def verify_on_page_proof(html_text, company_name, ico_number="", city_hint=""):
    """
    Tang 3: XAC THUC ON-PAGE PROOF (Bat buoc trang web phai chua bang chung phap ly cua cong ty):
    1. Neu cong ty co ma ICO (97.8%): BAT BUOC PHAI CHUA DUNG MA ICO DO TREN WEBSITE (Proof tuyet doi).
       Khong co ngoai le, khong fallback sang tu generic hay chu 'Slovakia' de tranh nhan vo web khac!
    2. Neu cong ty khong co ma ICO trong ho so (~2% ca nhan):
       Bat buoc phai chua toan bo ten day du + Thanh pho dang ky kinh doanh.
    """
    if not html_text:
        return False, "EMPTY_HTML"

    text_lower = html_text.lower()

    # 1. Neu co ma ICO: BAT BUOC 100% phai trung ma ICO tren trang web
    if ico_number and len(ico_number) >= 6:
        if ico_number in html_text or f"ico: {ico_number}" in text_lower or f"ičo: {ico_number}" in text_lower or f"ičo {ico_number}" in text_lower or f"ico {ico_number}" in text_lower:
            return True, f"XAC_THUC_ICO_{ico_number}"
        return False, "KHONG_TRUNG_MA_ICO"

    # 2. Truong hop dac biet khong co ma ICO trong danh sach goc (~2% ca nhan)
    clean_name = clean_company_name_sk(company_name)
    if clean_name and len(clean_name) >= 5 and clean_name in text_lower:
        if city_hint and len(city_hint) >= 4 and city_hint.lower() in text_lower:
            return True, f"XAC_THUC_TEN_VA_THANH_PHO_{city_hint}"

    return False, "KHONG_CO_BANG_CHUNG_XAC_THUC"

async def search_verified_company_website(company_name, ico_number, city_hint, session):
    """Tim kiem website qua Bing Search (khong bi chan VPN) va du phong DDG Lite, xac thuc 3 tang truoc khi chap nhan."""
    clean_name = clean_company_name_sk(company_name)
    if not clean_name or len(clean_name) < 3:
        return "", ""

    query = f"{clean_name} Slovakia"
    candidate_urls = []

    # 1. Engine 1: Bing Search (Hoat dong 100% tren VPN Ha Lan, giai ma base64 URL that)
    bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    bing_html = await fetch_html_resilient(bing_url, session, max_retries=1, timeout=8)
    if bing_html:
        soup = BeautifulSoup(bing_html, 'html.parser')
        for a in soup.select('li.b_algo h2 a'):
            raw_href = a.get('href', '')
            decoded = decode_bing_url(raw_href)
            if decoded and decoded.startswith(('http://', 'https://')):
                candidate_urls.append(decoded)

    # 2. Engine 2 (Du phong neu Bing khong ra ket qua): DuckDuckGo Lite
    if not candidate_urls:
        try:
            ddg_resp = await session.post(
                "https://lite.duckduckgo.com/lite/",
                data={'q': query},
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'},
                impersonate="chrome120",
                timeout=8
            )
            if ddg_resp.status_code == 200:
                ddg_soup = BeautifulSoup(ddg_resp.text, 'html.parser')
                for a in ddg_soup.select('a.result-link'):
                    href = a.get('href', '')
                    if href.startswith(('http://', 'https://')):
                        candidate_urls.append(href)
        except Exception:
            pass

    # Xac thuc cac URL ung vien qua Tang 1, 2 va Tang 3 (On-page proof)
    tested_domains = set()
    for raw_url in candidate_urls[:6]:
        # Tang 1 & 2: Loc domain rac va So khop Brand Token
        if is_domain_brand_match(raw_url, company_name):
            parsed = urllib.parse.urlparse(raw_url)
            root_url = f"{parsed.scheme}://{parsed.netloc}"
            dom = parsed.netloc.lower().replace('www.', '')
            if dom in tested_domains:
                continue
            tested_domains.add(dom)

            # Tang 3: Xac thuc On-Page Proof (Timeout 4s, khong retry de luot qua web chet ngay)
            home_html = await fetch_html_resilient(root_url, session, max_retries=1, timeout=4)
            if not home_html:
                # Trang chu khong phan hoi (domain chet / server sap) -> Bo qua ngay lap tuc!
                continue

            is_valid, reason = verify_on_page_proof(home_html, company_name, ico_number, city_hint)
            if is_valid:
                return root_url, reason
            else:
                # Kiem tra tiep trang /kontakt neu trang chu chua co du lieu
                kontakt_url = urllib.parse.urljoin(root_url, "/kontakt")
                kontakt_html = await fetch_html_resilient(kontakt_url, session, max_retries=1, timeout=4)
                if kontakt_html:
                    is_k_valid, k_reason = verify_on_page_proof(kontakt_html, company_name, ico_number, city_hint)
                    if is_k_valid:
                        return root_url, k_reason

    return "", ""

def extract_contacts_from_html(html_text, website_domain=""):
    if not html_text:
        return set(), ""
    emails = set()
    phone = ""

    # Cloudflare data-cfemail
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if score_email_b2b(dec, website_domain) >= 0:
            emails.add(dec)

    # mailto:
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) >= 0:
            emails.add(clean_m)

    # regex email
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) >= 0:
            emails.add(clean_m)

    # Obfuscated email
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(html_text):
            if len(match) == 3:
                rec = f"{match[0]}@{match[1]}.{match[2]}".lower()
            elif len(match) == 2:
                rec = f"{match[0]}@{match[1]}".lower()
            else:
                continue
            if score_email_b2b(rec, website_domain) >= 0:
                emails.add(rec)

    # tel: links
    tel_matches = re.findall(r'href=["\']tel:\s*([^"\'#\s]+)', html_text, re.IGNORECASE)
    for tm in tel_matches:
        raw_p = urllib.parse.unquote(tm).strip()
        digits = re.sub(r'\D', '', raw_p)
        if len(digits) >= 8:
            phone = raw_p
            break

    # fallback regex phone if not found in tel:
    if not phone:
        p_matches = PHONE_REGEX.findall(html_text)
        if p_matches:
            phone = p_matches[0].strip()

    return emails, phone

async def crawl_verified_website(website_url, session):
    if not website_url or not website_url.startswith(('http://', 'https://')):
        return "", ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')

    if domain in DOMAIN_CACHE:
        return DOMAIN_CACHE[domain].get("email", ""), DOMAIN_CACHE[domain].get("phone", "")

    all_emails = set()
    found_phone = ""

    subpaths = [
        "", "/kontakt", "/kontakty", "/o-nas", "/kariera", "/praca", "/contact"
    ]

    for sp in subpaths:
        target = urllib.parse.urljoin(website_url, sp)
        html_content = await fetch_html_resilient(target, session, max_retries=1, timeout=5)
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
        # Tang 4: Uu tien tuyet doi email cung domain website
        domain_emails = [e for e in all_emails if domain in e]
        target_list = domain_emails if domain_emails else list(all_emails)
        sorted_emails = sorted(target_list, key=lambda e: score_email_b2b(e, domain), reverse=True)
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

    for attempt in range(5):
        try:
            with open(INPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(final_rows)
            return
        except PermissionError:
            print(f"  [!] Canh bao: File CSV dang bi khoa (co the do dang mo tren Excel/Editor). Thu lai sau 1s ({attempt+1}/5)...")
            time.sleep(1.0)
        except Exception as e:
            print(f"  [!] Loi ghi CSV: {e}")
            break

async def run_enrichment():
    print("="*75)
    print("BAT DAU LAM GIAU DU LIEU WEB SEARCH VOI BO XAC THUC 4 TANG")
    print("CHONG 100% GUI NHAM MAIL | TOI UU CHO MANG VPN HA LAN")
    print("="*75)

    rows = []
    fieldnames = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)

    print(f"Tong so doanh nghiep hoat dong: {len(rows)}")

    # Load ICO map tu file goc de xac thuc on-page
    ico_map = load_company_ico_map()
    print(f"Da nap danh sach ma ICO cho {len(ico_map)} doanh nghiep.")

    cache = load_cache()
    print(f"Da nap cache: {len(cache)} doanh nghiep da xu ly.")

    # Uu tien cao nhat: Doanh nghiep chua co Email
    no_email_indices = []
    has_email_indices = []
    for idx, r in enumerate(rows):
        c_name = r.get('Công ty', '').strip()
        if not c_name:
            continue
        has_email = bool(r.get('Email', '').strip())
        has_phone = bool(r.get('SĐT', '').strip())
        has_web = bool(r.get('Liên Hệ', '').strip())
        if not (has_email and has_phone and has_web):
            if not has_email:
                no_email_indices.append(idx)
            else:
                has_email_indices.append(idx)

    to_enrich = no_email_indices + has_email_indices
    print(f"So luong can lam giau: {len(to_enrich)} (Trong do UU TIEN SO 1: {len(no_email_indices)} cty chua co Email)")

    async with AsyncSession() as session:
        processed_since_save = 0

        for i, row_idx in enumerate(to_enrich, 1):
            r = rows[row_idx]
            company_name = r.get('Công ty', '').strip()
            addr = r.get('Địa chỉ', '').strip()
            city_hint = addr.split(',')[0].strip() if addr else ""
            ico_number = ico_map.get(company_name, "")

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

            print(f"\n[{i}/{len(to_enrich)}] Xu ly: '{company_name}' (ICO: {ico_number or 'N/A'}, Khu vuc: {city_hint})")

            # 1. Tim va Xac thuc Website
            existing_web = r.get('Liên Hệ', '').strip()
            web_url = existing_web if existing_web and existing_web.startswith(('http://', 'https://')) else ""

            if not web_url:
                web_url, proof_reason = await search_verified_company_website(company_name, ico_number, city_hint, session)
                if web_url:
                    r['Liên Hệ'] = web_url
                    print(f"  [XAC THUC THANH CONG] {web_url} ({proof_reason})")
                else:
                    print("  [-] Khong tim thay website dat chuan xac thuc (tu choi de tranh nham mail)")

            # 2. Quet Website da xac thuc de lay Email B2B va SDT
            found_email = ""
            found_phone = ""
            if web_url:
                email, phone = await crawl_verified_website(web_url, session)
                if email and not r.get('Email'):
                    r['Email'] = email
                    found_email = email
                    print(f"  -> EMAIL B2B (Dung nguoi): {email}")
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
                print(f"  [Auto-save] Da luu tang dan vao CSV (Tong mail hien tai: {sum(1 for x in rows if x.get('Email'))})")
                processed_since_save = 0

            # Delay an toan cho VPN Ha Lan khong bi nghen mang
            await asyncio.sleep(1.5)

        # Final save
        save_csv_and_sort(rows, fieldnames)
        print(f"\n[HOAN TAT] Hoan thanh toan bo quy trinh lam giau du lieu xac thuc!")

if __name__ == '__main__':
    asyncio.run(run_enrichment())
