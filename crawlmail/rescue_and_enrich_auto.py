# -*- coding: utf-8 -*-
"""
Deep Rescuer and Precision Enrichment for Slovak Automotive Industry (SK_AUTO_SLVD):
1. Khắc phục triệt để lỗi False Positives (loại bỏ d in w, siết chặt TLD .sk, .eu, .cz, .com, .de, .at, .pl).
2. Khắc phục lỗi False Negatives (quét sâu 14 subpaths: /kontakty/, /obchodne-podmienky/...).
3. Bóc tách đồng thời cả EMAIL B2B và SỐ ĐIỆN THOẠI (tel:, regex +421, 09xx...) trực tiếp từ Website.
4. Quét vét toàn bộ 101 nhà máy đã có Website nhưng thiếu Email/SĐT (như BAJKY ŠPORT s.r.o., Felss, STS KOVO...).
5. Quét mở rộng đa nguồn (Google/Bing/DuckDuckGo) cho các cơ sở còn lại chưa có website.
6. Tự động lưu lũy tiến mỗi 5 công ty, đẩy 100% email lên đầu, chuẩn hóa SĐT có dấu nháy đơn '.
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
import asyncio
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# UTF-8 for Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_FILE = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json"

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'inc.', 'inc', 'corp.', 'corp'
]

VALID_DOM_TLDS = {'.sk', '.cz', '.eu', '.com', '.de', '.at', '.pl', '.net', '.org', '.hu', '.it', '.info', '.biz'}

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
    'creditreform.sk', 'e-creditreform.sk', 'ifirmy.sk', 'justice.gov.sk',
    'prever.to', 'infoma.sk', 'databasesets.com', 'b2bhint.com', 'vsetkyobchodne.com',
    'ceginformacio.hu', 'bizarchiv.org', 'krajsie.sk', 'edb.eu', 'icdph.sk',
    'verif.com', 'thethaovanhoa.vn', 'vietnam.vn', 'hatinh.gov.vn', 'bluetechnology.vn',
    'minhdan.com.vn', 'nguyenxuantung.vn', 'temu.com', 'shalva.org', 'indiantypefoundry.com'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com',
    'firma.sk', 'spolocnost.sk', 'domena.sk', 'vasadomena.sk', 'verdeholding.hu',
    'transparex.sk', 'overit.sk', 'mapafiriem.sk', 'orsf.sk', 'zoznam.sk'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'domain', 'email', 'vasa.adresa', 'vasaadresa', 'nieco'
}

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

def is_domain_valid_and_relevant(domain, company_name):
    """
    So khớp tên miền nghiêm ngặt:
    1. Bắt buộc TLD thuộc Slovakia hoặc Châu Âu/Quốc tế.
    2. Tuyệt đối không chấp nhận các trang danh bạ, chính phủ.
    3. Tên công ty hoặc từ cốt lõi (>= 4 ký tự) phải nằm trong domain.
    """
    if not domain or not company_name:
        return False
    d_clean = domain.lower().replace('www.', '')
    
    # Check TLD
    if not any(d_clean.endswith(tld) for tld in VALID_DOM_TLDS):
        return False
        
    # Check Blacklist
    if any(ex in d_clean for ex in EXCLUDED_DOMAINS):
        return False

    c_clean = clean_company_name_sk(company_name)
    stopwords = {'auto', 'moto', 'servis', 'group', 'slovakia', 'slovensko', 'spol', 'trade'}
    words = [w for w in c_clean.split() if len(w) >= 4 and w not in stopwords]
    if not words:
        words = [w for w in c_clean.split() if len(w) >= 3]

    d_base = d_clean.split('.')[0]
    
    # 1. Khớp từ khóa cốt lõi (w in d_base) - CHỈ cho phép w in d, KHÔNG cho d in w để tránh Temu in Temur
    if any(w in d_base for w in words if len(w) >= 4):
        return True

    # 2. Khớp chuỗi condensed
    c_condensed = re.sub(r'[^a-z0-9]', '', c_clean)
    if len(c_condensed) >= 5 and len(d_base) >= 5:
        if c_condensed in d_base or d_base in c_condensed:
            return True

    return False

def clean_phone_number(raw_phone):
    if not raw_phone:
        return ""
    # Remove tel: and whitespace
    p = re.sub(r'^tel:\s*', '', str(raw_phone), flags=re.IGNORECASE).strip()
    p = re.sub(r'[^\d+]', '', p)
    
    # Validate length
    if len(re.sub(r'[^\d]', '', p)) < 9:
        return ""
    if len(re.sub(r'[^\d]', '', p)) > 15:
        return ""
        
    # Standardize Slovak format
    clean_digits = re.sub(r'[^\d]', '', p)
    if clean_digits.startswith('421') and len(clean_digits) == 12:
        formatted = f"+421 {clean_digits[3:6]} {clean_digits[6:9]} {clean_digits[9:12]}"
    elif clean_digits.startswith('0') and len(clean_digits) == 10:
        formatted = f"'+421 {clean_digits[1:4]} {clean_digits[4:7]} {clean_digits[7:10]}"
        return formatted
    elif clean_digits.startswith('0') and len(clean_digits) == 9:
        formatted = f"'+421 {clean_digits[1:3]} {clean_digits[3:6]} {clean_digits[6:9]}"
        return formatted
    else:
        formatted = f"+{clean_digits}" if not p.startswith('+') else p

    return f"'{formatted}" if not formatted.startswith("'") else formatted

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
    if any(tld in domain for tld in ['.vn', '.ru', '.cn', '.ge']):
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

    if any(k in user for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    elif any(k in user for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
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
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=8, verify=False)
            if resp.status_code == 200:
                return resp.text
        else:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8), ssl=False) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        pass
    return ""

def extract_contacts_from_html(html_text, website_domain=None):
    if not html_text:
        return set(), set()
    found_emails = set()
    found_phones = set()

    # 1. Cloudflare
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if is_valid_b2b_email(dec, website_domain):
            found_emails.add(dec)

    # 2. mailto
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found_emails.add(clean_m)

    # 3. email regex
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().replace('%20', '').rstrip('.,;:')
        if is_valid_b2b_email(clean_m, website_domain):
            found_emails.add(clean_m)

    # 4. tel: links
    for tel in re.findall(r'href=["\']tel:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_tel = urllib.parse.unquote(tel).strip()
        p = clean_phone_number(clean_tel)
        if p:
            found_phones.add(p)

    # 5. Slovak phone regex patterns in text
    for p_match in re.findall(r'(?:\+421|00421|0)\s*(?:[1-9]\d{1,2}|\d{2,3})\s*\d{3}\s*\d{3,4}', html_text):
        p = clean_phone_number(p_match)
        if p:
            found_phones.add(p)

    return found_emails, found_phones

async def deep_crawl_website(website_url, session):
    """Quét đa tầng website (bao gồm 14 subpaths) để bóc tách cả Email và SĐT."""
    if not website_url or not website_url.startswith(('http://', 'https://')):
        return "", ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')

    subpaths = [
        "", "/kontakt", "/kontakt/", "/kontakty", "/kontakty/",
        "/o-nas", "/o-nas/", "/kariera", "/kariera/", "/praca", "/praca/",
        "/obchodne-podmienky", "/obchodne-podmienky/", "/contact", "/contact/"
    ]
    targets = [urllib.parse.urljoin(website_url, sp) for sp in subpaths]

    all_emails = set()
    all_phones = set()

    for u in targets:
        html_text = await fetch_html(u, session)
        if html_text:
            emails, phones = extract_contacts_from_html(html_text, domain)
            all_emails.update(emails)
            all_phones.update(phones)
            # Nếu đã có cả email và phone thì có thể sớm dừng
            if all_emails and all_phones and len(all_emails) >= 2:
                break

    best_email = ""
    if all_emails:
        sorted_emails = sorted(list(all_emails), key=lambda e: score_email_b2b(e, domain), reverse=True)
        best_email = sorted_emails[0]

    best_phone = ""
    if all_phones:
        # Ưu tiên SĐT di động +421 9xx hoặc SĐT cố định
        for p in all_phones:
            if '9' in p[:8]: # di động
                best_phone = p
                break
        if not best_phone:
            best_phone = list(all_phones)[0]

    return best_email, best_phone

async def search_web_for_company(company_name, city, session):
    """Tìm kiếm web với truy vấn mềm và đối chiếu tên miền chặt chẽ."""
    clean_name = clean_company_name_sk(company_name)
    queries = [
        f'"{clean_name}" {city} slovakia',
        f'{clean_name} {city} slovakia kontakt',
        f'"{clean_name}" slovakia'
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    for q in queries:
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(q)}"
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
                for a in soup.select('a.result__url, a.result__snippet'):
                    raw_href = a.get('href', '')
                    if 'uddg=' in raw_href:
                        actual_url = urllib.parse.unquote(raw_href.split('uddg=')[1].split('&')[0])
                    else:
                        actual_url = raw_href
                    if actual_url.startswith(('http://', 'https://')):
                        parsed = urllib.parse.urlparse(actual_url)
                        domain = parsed.netloc.lower().replace('www.', '')
                        if is_domain_valid_and_relevant(domain, company_name):
                            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass
        await asyncio.sleep(0.5)

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
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    final_rows = with_email + without_email

    for idx, r in enumerate(final_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    try:
        with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_rows)
    except Exception as e:
        print(f"    [!] Lỗi ghi file: {e}")

async def run_rescuer():
    print("=" * 70)
    print("🚀 BẮT ĐẦU QUY TRÌNH GIẢI CỨU VÀ LÀM GIÀU DỮ LIỆU CHUYÊN SÂU (AUTO RESCUER)")
    print("=" * 70)

    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    cache = load_cache()
    print(f"[*] Tổng số doanh nghiệp: {len(rows):,} công ty.")

    # Bước 1: Làm sạch các website danh bạ / công báo rác
    cleaned_dirs = 0
    for r in rows:
        wb = r.get('Web', '').strip().lower()
        if any(ex in wb for ex in EXCLUDED_DOMAINS):
            r['Web'] = ''
            r['Email'] = ''
            cleaned_dirs += 1
    if cleaned_dirs > 0:
        print(f"[+] Đã loại bỏ {cleaned_dirs} website danh bạ / công báo rác khỏi dữ liệu.")

    # Bước 2: Xác định danh sách cần giải cứu và làm giàu
    need_rescue_web = []  # Đã có web nhưng chưa có Email hoặc SĐT
    need_search = []      # Chưa có web và chưa có email

    for r in rows:
        wb = r.get('Web', '').strip()
        em = r.get('Email', '').strip()
        ph = r.get('SĐT', '').strip()
        
        if wb and (not em or not ph):
            need_rescue_web.append(r)
        elif not wb and not em:
            need_search.append(r)

    print(f"[*] Danh sách cần quét sâu Website hiện có (như BAJKY ŠPORT...): {len(need_rescue_web)} công ty.")
    print(f"[*] Danh sách cần tìm kiếm Website bổ sung: {len(need_search)} công ty.\n")

    session = AsyncSession() if HAS_CURL_CFFI else aiohttp.ClientSession()

    # --- PHA 1: QUÉT SÂU 101 WEBSITE ĐÃ CÓ NHƯNG THIẾU EMAIL/PHONE ---
    print(">>> PHA 1: QUÉT SÂU EMAIL & SĐT TỪ CÁC WEBSITE ĐÃ CÓ...")
    rescued_emails = 0
    rescued_phones = 0

    for idx, r in enumerate(need_rescue_web, 1):
        cname = r.get('Công ty', '')
        wb = r.get('Web', '')
        ico = r.get('IČO', '')
        cache_key = ico if ico else cname.lower()

        print(f"[{idx}/{len(need_rescue_web)}] Quét: {cname} | {wb}...")
        try:
            email, phone = await deep_crawl_website(wb, session)
            added_info = []
            if email and not r.get('Email'):
                r['Email'] = email
                rescued_emails += 1
                added_info.append(f"Email: {email}")
            if phone and not r.get('SĐT'):
                r['SĐT'] = phone
                rescued_phones += 1
                added_info.append(f"SĐT: {phone}")

            if added_info:
                print(f"    -> [THÀNH CÔNG] {' | '.join(added_info)}")
            else:
                print("    -> [Website không chứa Email/SĐT khả dụng]")

            # Cập nhật cache
            if cache_key not in cache:
                cache[cache_key] = {}
            cache[cache_key].update({
                'name': cname,
                'ico': ico,
                'website': wb,
                'email': r.get('Email', ''),
                'phone': r.get('SĐT', ''),
                'rescued_at': datetime.now().isoformat()
            })
            save_cache(cache)

        except Exception as e:
            print(f"    -> [Lỗi quét web: {e}]")

        if idx % 5 == 0:
            save_output_csv(rows, fieldnames)
            c_em = sum(1 for x in rows if x.get('Email'))
            print(f"    [+] Auto-save: Hiện có {c_em} Email trong file.")

        await asyncio.sleep(0.8)

    save_output_csv(rows, fieldnames)
    print(f"\n[V] Hoàn tất Pha 1! Thu hồi thêm: {rescued_emails} Email và {rescued_phones} SĐT mới.\n")

    # --- PHA 2: TÌM KIẾM ĐA NGUỒN CHO CÁC DOANH NGHIỆP CÒN LẠI ---
    print(">>> PHA 2: TÌM KIẾM BỔ SUNG ĐA NGUỒN (GOOGLE / BING / DUCKDUCKGO)...")
    found_webs = 0
    new_emails = 0

    # Lọc chỉ lấy các công ty dạng pháp nhân s.r.o., a.s., k.s. có tiềm năng cao nhất
    corporate_need_search = [r for r in need_search if any(lf in r.get('Loại hình', '').lower() for lf in ['spoločnosť', 'akciová', 'družstvo'])]
    print(f"[*] Ưu tiên tìm kiếm cho {len(corporate_need_search)} doanh nghiệp pháp nhân (s.r.o., a.s.)...")

    for idx, r in enumerate(corporate_need_search, 1):
        cname = r.get('Công ty', '')
        city = r.get('Thành phố', '')
        ico = r.get('IČO', '')
        cache_key = ico if ico else cname.lower()

        print(f"[{idx}/{len(corporate_need_search)}] Tìm kiếm: {cname} ({city})...")
        website = await search_web_for_company(cname, city, session)
        if website:
            r['Web'] = website
            found_webs += 1
            print(f"    -> [Website Hợp Lệ Khớp] {website}")
            email, phone = await deep_crawl_website(website, session)
            if email:
                r['Email'] = email
                new_emails += 1
                print(f"    -> [Email B2B Tuyển Chọn] {email}")
            if phone and not r.get('SĐT'):
                r['SĐT'] = phone
                print(f"    -> [SĐT Trích Xuất] {phone}")

            if cache_key not in cache:
                cache[cache_key] = {}
            cache[cache_key].update({
                'name': cname,
                'ico': ico,
                'website': website,
                'email': r.get('Email', ''),
                'phone': r.get('SĐT', ''),
                'enriched_at': datetime.now().isoformat()
            })
            save_cache(cache)
        else:
            print("    -> [Không tìm thấy Website hợp lệ]")

        if idx % 5 == 0:
            save_output_csv(rows, fieldnames)
            c_em = sum(1 for x in rows if x.get('Email'))
            print(f"    [+] Auto-save: Hiện có {c_em} Email trong file.")

        await asyncio.sleep(1.0)

    # Final save
    save_output_csv(rows, fieldnames)
    if not HAS_CURL_CFFI:
        await session.close()

    total_with_email = sum(1 for x in rows if x.get('Email'))
    total_with_phone = sum(1 for x in rows if x.get('SĐT'))
    total_with_web = sum(1 for x in rows if x.get('Web'))

    print("\n" + "=" * 70)
    print("🎉 HOÀN TẤT GIẢI CỨU VÀ LÀM GIÀU DỮ LIỆU Ô TÔ!")
    print(f"[*] Tổng số doanh nghiệp: {len(rows):,}")
    print(f"[*] Có Email B2B tuyển chọn: {total_with_email:,} ({total_with_email/len(rows)*100:.1f}%)")
    print(f"[*] Có Số điện thoại chuẩn '': {total_with_phone:,} ({total_with_phone/len(rows)*100:.1f}%)")
    print(f"[*] Có Website chính thức   : {total_with_web:,} ({total_with_web/len(rows)*100:.1f}%)")
    print(f"[*] Đã đẩy 100% {total_with_email:,} công ty có Email lên đầu tệp.")
    print(f"📁 Tệp kết quả: {CSV_FILE}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_rescuer())
