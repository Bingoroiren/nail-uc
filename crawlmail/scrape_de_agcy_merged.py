# -*- coding: utf-8 -*-
"""
HỆ THỐNG THU THẬP VÀ HỢP NHẤT DỮ LIỆU CÔNG TY VIỆC LÀM & ZEITARBEIT ĐỨC (DE_AGCY_WEBD)
======================================================================================
Nguồn dữ liệu mục tiêu:
1. Wer-zu-wem.de: Top 20 tập đoàn nhân sự & Zeitarbeit lớn nhất nước Đức
   URL: https://www.wer-zu-wem.de/dienstleister/zeitarbeitsfirmen.html
2. GelbeSeiten.de (Personalvermittlung & Zeitarbeit):
   - Tuyển dụng & Môi giới (Personalvermittlung): https://www.gelbeseiten.de/branchen/personalvermittlung/berlin
   - Cho thuê lao động & Phái cử (Zeitarbeit): https://www.gelbeseiten.de/branchen/zeitarbeit/berlin
   - Cơ chế cào mở rộng toàn bộ các vùng/thành phố kinh tế trọng điểm nước Đức tránh bỏ sót data.

Quy chuẩn kỹ thuật bắt buộc theo GEMINI.md:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY. Không bao giờ xuất Excel.
- Rule 2: Số điện thoại luôn có dấu nháy đơn (') ở đầu (ví dụ: '+49 30 88922480).
- Rule 3: Bộ chấm điểm B2B tối ưu tuyển dụng (Bewerbung +50, Geschäftsführung +45, Info +40),
          lọc sạch 100% mail rác/template. ĐẨY 100% CTY CÓ EMAIL LÊN ĐẦU DANH SÁCH.
- Rule 5: Lưu tăng dần và Checkpoint cache JSON (cache_de_agcy_merged.json) cho phép Resume 100%.
- Rule 8: File launcher .bat thuần ASCII, không dấu tiếng Việt, không dùng ký tự '&' trần.
- Rule 9: Cung cấp đầy đủ câu lệnh Terminal cho người dùng IDE (PowerShell, CMD, Python).
- Rule 10: Tên file cố định chuẩn 17 ký tự (DE_AGCY_WEBD_0RAW.csv / DE_AGCY_WEBD_2COL.csv).
- Rule 11: So khớp tên thông minh & nghiêm ngặt (NFKD Unicode, làm sạch pháp nhân GmbH, AG, UG, e.K.).
- Rule 12: Loại trừ 100% danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre).
- Tự động đồng bộ sang csdl_mlt/ và archive/de_germany/.
"""

import sys
import os
import re
import csv
import json
import time
import shutil
import base64
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import requests
import urllib3
import warnings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# UTF-8 Output cho Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# PATH CONSTANTS (Rule 10: 17 characters fixed)
# ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_0RAW.csv"
COL2_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_2COL.csv"
READY_CSV_PATH = ROOT_DIR / "DE_AGCY_WEBD_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_de_agcy_merged.json"
DOMAIN_CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_domain_contacts_de.json"
ARCHIVE_DIR = ROOT_DIR / "archive" / "de_germany"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

RAW_COLUMNS = [
    'No.', 'Company_Name', 'Legal_Name', 'Category', 'Branch', 'City', 'Region',
    'Street', 'Zipcode', 'Full_Address', 'Phone', 'Email', 'Website',
    'Managing_Director', 'Employees', 'Revenue_Class', 'Detail_URL',
    'Source_Primary', 'All_Sources'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule 12: Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

# Danh bạ các thành phố kinh tế trọng điểm nước Đức (Regional Hubs)
DEFAULT_GERMAN_CITIES = [
    'berlin',               # Thủ đô & Trọng điểm
    'hamburg',              # Cảng & Logistics quốc tế
    'muenchen',             # Thủ phủ công nghiệp Nam Đức
    'koeln',                # Trung tâm Tây Đức
    'frankfurt-am-main',    # Thủ đô tài chính châu Âu
    'stuttgart',            # Trung tâm cơ khí ô tô
    'duesseldorf',          # Thủ phủ NRW & Thương mại
    'leipzig',              # Logistics & Sản xuất Đông Đức
    'dortmund',             # Vùng Ruhr công nghiệp
    'essen',                # Vùng Ruhr
    'bremen',               # Cảng biển Bắc Đức
    'dresden',              # Công nghệ & Chế tạo
    'hannover',             # Hội chợ & Công nghiệp
    'nuernberg',            # Trung tâm Zeitarbeit miền Nam
    'duisburg', 'bochum', 'wuppertal', 'bielefeld', 'bonn', 'muenster',
    'karlsruhe', 'mannheim', 'augsburg', 'wiesbaden'
]

# Từ khóa trang liên hệ bản địa Đức (Skill crawl-mail)
DE_PRIORITY_KEYWORDS = [
    'impressum', 'kontakt', 'karriere', 'jobs', 'standorte', 'ansprechpartner',
    'team', 'ueber-uns', 'uber-uns', 'contact', 'about'
]

DE_GUESS_SUBPATHS = [
    '/impressum', '/impressum/', '/impressum.html', '/impressum.php',
    '/kontakt', '/kontakt/', '/kontakt.html', '/kontakt.php',
    '/karriere', '/karriere/', '/jobs', '/jobs/',
    '/standorte', '/ansprechpartner',
    '/contact', '/contact-us', '/about'
]

JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'wix.com', 'wixpress.com', 'wordpress.com', 'wordpress.org',
    'example.com', 'domain.com', 'email.com', 'yourcompany.com', 'yourdomain.com',
    'gelbeseiten.de', 'wer-zu-wem.de', 'facebook.com', 'instagram.com', 'linkedin.com',
    'schema.org', 'google.com'
}

JUNK_EMAIL_PREFIXES = {
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'example', 'domain', 'no-reply', 'noreply', 'donotreply',
    'privacy', 'gdpr', 'abuse', 'webmaster', 'postmaster', 'datenschutz'
}


# ----------------------------------------------------------------------
# HELPER FUNCTIONS: NORMALIZATION, VALIDATION, SCORING
# ----------------------------------------------------------------------
def is_blacklisted_company(name):
    """Rule 12: Permanent company blacklist exclusion."""
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def normalize_company_name(name):
    """Chuẩn hóa tên công ty loại bỏ pháp nhân Đức (GmbH, AG, e.K., UG, KG...)."""
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    legal_terms = [
        'gmbh & co. kg', 'gmbh & co kg', 'gmbh & co.', 'gmbh & co',
        'gmbh', 'ag', 'ug (haftungsbeschrankt)', 'ug', 'e.k.', 'ek',
        'ohg', 'kg', 'se', 'kgaa', 'personaldienstleistungen',
        'personaldienstleister', 'personalservice', 'zeitarbeit',
        'personalvermittlung', 'management'
    ]
    for term in legal_terms:
        n = re.sub(r'\b' + term + r'\b', ' ', n)
    n = re.sub(r'["\'„“”«»\[\]\(\)]', ' ', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n.strip()


def clean_phone_de(raw_phone):
    """Chuẩn hóa số điện thoại Đức theo chuẩn Rule 2: có nháy đơn (') ở đầu (+49...)"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = urllib.parse.unquote(str(raw_phone)).strip()
    s = re.sub(r'^tel:\s*', '', s, flags=re.I)
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff']:
        s = s.replace(bad, ' ')
    s = s.lstrip("'").strip()
    
    # Bỏ (0) trong +49 (0) 30...
    s = re.sub(r'\(\s*0\s*\)', '', s)
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''

    if digits.startswith('49'):
        pass
    elif digits.startswith('0'):
        digits = '49' + digits[1:]
    else:
        digits = '49' + digits

    if len(digits) < 9 or len(digits) > 15:
        return ''

    # Format chuẩn quốc tế Đức
    # Mã vùng 2 số: 30 (Berlin), 40 (Hamburg), 89 (Munich)
    if digits.startswith('4930') and len(digits) > 4:
        formatted = f"+49 30 {digits[4:]}"
    elif digits.startswith('4940') and len(digits) > 4:
        formatted = f"+49 40 {digits[4:]}"
    elif digits.startswith('4989') and len(digits) > 4:
        formatted = f"+49 89 {digits[4:]}"
    elif len(digits) >= 6:
        formatted = f"+49 {digits[2:5]} {digits[5:]}"
    else:
        formatted = f"+{digits}"

    return f"'{formatted}"


def clean_email(email):
    """Làm sạch ký tự ẩn (%20, non-breaking space, u003e) và loại bỏ email template."""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'^(?:u003e|u003c|&gt;|&lt;|>|<)+', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    em = em.lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""
    user, domain = em.split('@', 1)
    if domain in JUNK_EMAIL_DOMAINS or any(domain.endswith('.' + d) for d in JUNK_EMAIL_DOMAINS):
        return ""
    if user in JUNK_EMAIL_PREFIXES:
        return ""
    return em


def score_email_b2b_de(email, website_domain=""):
    """
    Chấm điểm email tuyển dụng B2B Manpower Agency theo chuẩn Rule 3 (Đức):
    - Trùng domain website (+50đ)
    - Tuyển dụng / Nhân sự / Bewerbung (+50đ)
    - Ban Giám đốc / Lãnh đạo / Geschäftsführung (+45đ)
    - Liên hệ chính thức / Info / Kontakt (+40đ)
    - Đích danh cá nhân domain riêng (+25đ)
    - Webmail miễn phí (+10đ)
    - Kỹ thuật / Kế toán (+5đ)
    """
    if not email:
        return 0
    em = clean_email(email)
    if not em:
        return 0

    user, domain = em.split('@', 1)
    score = 0

    if website_domain and website_domain in domain:
        score += 50

    # 1. Tuyển dụng / Việc làm (Ưu tiên số 1)
    hr_kw = ['bewerbung', 'jobs', 'karriere', 'recruiting', 'personal', 'job', 'work', 'disposition', 'hr', 'career']
    if any(k in user for k in hr_kw):
        return score + 50

    # 2. Ban Lãnh đạo / Giám đốc (Ưu tiên số 2)
    exec_kw = ['geschaeftsfuehrung', 'gf', 'leitung', 'vorstand', 'direktion', 'ceo', 'director', 'manager', 'geschaeftsleitung']
    if any(k in user for k in exec_kw):
        return score + 45

    # 3. Liên hệ chính thức / Info (Ưu tiên số 3)
    info_kw = ['info', 'kontakt', 'contact', 'zentrale', 'office', 'empfang', 'service', 'berlin']
    if any(k in user for k in info_kw):
        return score + 40

    # 4. Cá nhân theo domain riêng
    free_webmails = ['gmail.com', 'yahoo.de', 'web.de', 'gmx.de', 't-online.de', 'freenet.de', 'hotmail.com', 'outlook.de']
    if domain not in free_webmails and '.' in user:
        return score + 25

    # 5. Webmail miễn phí
    if domain in free_webmails:
        return score + 10

    # 6. Kế toán / kỹ thuật
    tech_kw = ['buchhaltung', 'rechnung', 'faktura', 'support', 'admin', 'it']
    if any(k in user for k in tech_kw):
        return score + 5

    return score + 15


def is_valid_website(url):
    """Kiểm tra URL hợp lệ và loại bỏ mạng xã hội / sàn danh bạ."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not (u.startswith('http://') or u.startswith('https://')):
        return False
    parsed = urllib.parse.urlparse(u)
    domain = parsed.netloc.lower()
    if not domain or '.' not in domain:
        return False
    if any(b in domain for b in ['facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'gelbeseiten.de', 'wer-zu-wem.de', 'google.com', 'wikipedia.org']):
        return False
    return True


# -------------------------------------------------------------
# SOURCE 1: WER-ZU-WEM.DE CRAWLER (All 43 Pages ~327 Companies)
# -------------------------------------------------------------
def scrape_wer_zu_wem():
    """Cào toàn bộ danh bạ các công ty Zeitarbeit trên 43 trang của wer-zu-wem.de"""
    print(f"\n[1/3] Dang cao toan bo 43 trang Zeitarbeit tu wer-zu-wem.de...")

    def fetch_wzw_page(p):
        url = 'https://www.wer-zu-wem.de/dienstleister/zeitarbeitsfirmen.html' if p == 1 else f'https://www.wer-zu-wem.de/dienstleister/zeitarbeitsfirmen-seite-{p}.html'
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                return p, []
            s = BeautifulSoup(r.text, 'html.parser')
            tbl = s.find('table')
            if not tbl:
                return p, []
            page_items = []
            for tr in tbl.find_all('tr')[1:]:
                td = tr.find('td')
                if not td:
                    continue

                text_block = td.get_text(' | ', strip=True)
                a_tags = td.find_all('a', href=True)
                detail_link = ''
                for a in a_tags:
                    if '/firma/' in a['href']:
                        detail_link = a['href']
                        break
                if detail_link and not detail_link.startswith('http'):
                    detail_link = 'https://www.wer-zu-wem.de' + detail_link

                parts = [part.strip() for part in text_block.split('|') if part.strip()]
                c_name = parts[1] if len(parts) > 1 else ''
                loc_str = parts[2] if len(parts) > 2 else ''

                zipcode = ''
                city = loc_str
                m_zip = re.search(r'\b(\d{5})\s+(.*)', loc_str)
                if m_zip:
                    zipcode = m_zip.group(1)
                    city = m_zip.group(2).strip()

                emp_str = ''
                for part in parts:
                    if 'mitarbeiter' in part.lower():
                        emp_str = part
                        break

                if c_name:
                    page_items.append({
                        'name': c_name,
                        'legal_name': c_name,
                        'city': city,
                        'zipcode': zipcode,
                        'employees': emp_str,
                        'detail_url': detail_link,
                        'category': 'Zeitarbeit / Personaldienstleister',
                        'branch': 'zeitarbeit',
                        'source': 'wer-zu-wem.de'
                    })
            return p, page_items
        except Exception:
            return p, []

    items = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(fetch_wzw_page, range(1, 44)))
        for p, p_items in sorted(results, key=lambda x: x[0]):
            items.extend(p_items)

    print(f"[+] Da trich xuat tong cong {len(items)} doanh nghiep Zeitarbeit tren 43 trang wer-zu-wem.de")

    # Bóc tách chi tiết từng công ty (Website, Phone, Geschäftsführer)
    def fetch_wzw_detail(it):
        d_url = it.get('detail_url')
        if not d_url:
            return it
        try:
            res = requests.get(d_url, headers=HEADERS, timeout=12)
            if res.status_code == 200:
                sp = BeautifulSoup(res.text, 'html.parser')

                # 1. Legal Name
                leg_el = sp.find(attrs={'itemprop': 'legalName'}) or sp.find(class_='wzw-legal-name')
                if leg_el:
                    it['legal_name'] = leg_el.get_text(strip=True)
                elif sp.find('h1'):
                    h1_txt = sp.find('h1').get_text(strip=True)
                    if h1_txt and '410' not in h1_txt:
                        it['legal_name'] = h1_txt

                # 2. Address
                street_el = sp.find(attrs={'itemprop': 'streetAddress'})
                if street_el:
                    it['street'] = street_el.get_text(strip=True)
                zip_el = sp.find(attrs={'itemprop': 'postalCode'})
                if zip_el:
                    it['zipcode'] = zip_el.get_text(strip=True)
                city_el = sp.find(attrs={'itemprop': 'addressLocality'})
                if city_el:
                    it['city'] = city_el.get_text(strip=True)

                if it.get('street') or it.get('zipcode') or it.get('city'):
                    it['address'] = f"{it.get('street', '')}, {it.get('zipcode', '')} {it.get('city', '')}".strip(', ')

                # 3. Phone & Web
                tel_el = sp.find(attrs={'itemprop': 'telephone'}) or sp.find('a', href=lambda h: h and h.startswith('tel:'))
                if tel_el and not it.get('phone'):
                    raw_tel = tel_el['href'].replace('tel:', '').strip() if tel_el.get('href') else tel_el.get_text(strip=True)
                    it['phone'] = raw_tel

                web_el = sp.find('a', attrs={'itemprop': 'url'})
                if web_el and web_el.get('href'):
                    h = web_el['href'].strip()
                    if h.startswith('http') and not any(k in h for k in ['wer-zu-wem', 'infofy', 'dein-ausbildungsplatz', 'autohaendler']):
                        it['website'] = h
                if not it.get('website'):
                    for a in sp.find_all('a', href=True):
                        h = a['href']
                        if h.startswith('http') and not any(k in h for k in ['wer-zu-wem', 'infofy', 'dein-ausbildungsplatz', 'autohaendler']):
                            it['website'] = h.strip()
                            break

                # 4. Managing Director (Geschäftsführung)
                gf_sec = sp.find(lambda e: e.name in ['div', 'section'] and 'Geschäftsführung' in e.text)
                gf_names = []
                if gf_sec:
                    for tr in gf_sec.find_all('tr', attrs={'itemscope': True}):
                        n_tag = tr.find(attrs={'itemprop': 'name'})
                        if n_tag:
                            name_clean = n_tag.get_text(strip=True)
                            if name_clean and name_clean not in gf_names:
                                gf_names.append(name_clean)
                    if not gf_names:
                        m_names = re.findall(r'([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)+)\s+Geschäftsführer', gf_sec.get_text(' ', strip=True))
                        for m in m_names:
                            if not any(k in m for k in ['Name', 'Funktion', 'Telefon', 'Randstad', 'Adecco', 'Firmenprofil', 'Mitbewerber']):
                                gf_names.append(m)
                if gf_names:
                    it['managing_director'] = ', '.join(dict.fromkeys(gf_names))

                # 5. Employees & Revenue
                m_emp = re.search(r'Mitarbeiter:\s*([^\n\r<]+)', sp.text)
                if m_emp:
                    it['employees'] = m_emp.group(1).strip()
                m_rev = re.search(r'Umsatzklasse:\s*([^\n\r<]+)', sp.text)
                if m_rev:
                    it['revenue_class'] = m_rev.group(1).strip()
        except Exception:
            pass
        return it

    print("  [*] Dang boc tach chi tiet Profile, Website & Giam doc tren wer-zu-wem.de...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        items = list(ex.map(fetch_wzw_detail, items))

    return items


# -------------------------------------------------------------
# SOURCE 2: GELBESEITEN.DE CRAWLER (All Regions & Branches)
# -------------------------------------------------------------
def parse_gelbeseiten_article(art, region="Berlin", branch="zeitarbeit"):
    """Bóc tách chính xác toàn bộ trường dữ liệu của 1 thẻ doanh nghiệp GelbeSeiten."""
    real_id = art.get('data-realid') or art.get('data-teilnehmerid') or ''

    # 1. Company Name
    name_el = art.find(['h2', 'h1'])
    name = name_el.get_text(strip=True) if name_el else ''

    # 2. Category
    cat_el = art.find(class_=lambda c: c and 'bestebranche' in str(c).lower())
    category = cat_el.get_text(strip=True) if cat_el else ('Zeitarbeit' if branch == 'zeitarbeit' else 'Personalvermittlung')

    # 3. Detail URL
    det_a = art.find('a', href=lambda h: h and '/gsbiz/' in h)
    detail_url = det_a['href'] if det_a else ''

    # 4. Extract from chatwerk data-parameters JSON
    email = ''
    phone = ''
    street = ''
    zipcode = ''
    city = ''

    chat_btn = art.find('button', attrs={'data-parameters': True})
    if chat_btn:
        try:
            params = json.loads(chat_btn['data-parameters'])
            gen = params.get('organizationQuery', {}).get('generic', {})
            email = gen.get('email', '') or ''
            phones = gen.get('phones', [])
            if phones:
                phone = phones[0]
            street = gen.get('street', '')
            zipcode = gen.get('zip', '')
            city = gen.get('city', '')
        except Exception:
            pass

    # 5. Extract Phone from data-prg base64
    if not phone:
        p_el = art.find('a', attrs={'data-prg': True})
        if p_el:
            try:
                phone = base64.b64decode(p_el['data-prg']).decode('utf-8', errors='ignore').strip()
            except Exception:
                pass

    # 6. Extract Website from data-webseitelink base64
    website = ''
    w_el = art.find(attrs={'data-webseitelink': True})
    if w_el:
        try:
            raw_w = base64.b64decode(w_el['data-webseitelink']).decode('utf-8', errors='ignore').strip()
            parsed_w = urllib.parse.urlparse(raw_w)
            website = f"{parsed_w.scheme}://{parsed_w.netloc}{parsed_w.path}".rstrip('/')
            if not website or website == '://':
                website = raw_w
        except Exception:
            pass

    # 7. Address fallback from <address>
    if not street or not city:
        addr_el = art.find('address')
        if addr_el:
            addr_text = addr_el.get_text(' ', strip=True)
            addr_text = re.sub(r'\s*\d+[\d\.,]*\s*(?:km|m)\b', '', addr_text).strip()
            m_zip = re.search(r'\b(\d{5})\s+([^,]+)', addr_text)
            if m_zip:
                zipcode = m_zip.group(1)
                city = m_zip.group(2).strip()
                street = addr_text[:m_zip.start()].strip().rstrip(',')
            else:
                street = addr_text
                city = region.capitalize()

    full_address = f"{street}, {zipcode} {city}".strip(', ') if (street or zipcode or city) else region.capitalize()

    return {
        'id': real_id,
        'name': name,
        'legal_name': name,
        'category': category,
        'branch': branch,
        'phone': phone,
        'website': website,
        'email': email,
        'street': street,
        'zipcode': zipcode,
        'city': city or region.capitalize(),
        'region': region.capitalize(),
        'address': full_address,
        'detail_url': detail_url,
        'managing_director': '',
        'employees': '',
        'revenue_class': '',
        'source': f"gelbeseiten.de ({branch} - {region.capitalize()})"
    }


def scrape_gelbeseiten_city_branch(city, branch, max_pages=10):
    """
    Cào toàn bộ danh sách phân trang cho 1 thành phố và 1 ngành trên GelbeSeiten.
    Tự động dừng khi hết kết quả hoặc phát hiện vòng lặp trang.
    """
    url_base = f"https://www.gelbeseiten.de/branchen/{branch}/{urllib.parse.quote(city)}"
    items = []
    seen_ids = set()

    for p in range(1, max_pages + 1):
        page_url = f"{url_base}?seite={p}"
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                break
            sp = BeautifulSoup(r.text, 'html.parser')
            arts = sp.find_all('article')
            if not arts:
                break

            # Kiểm tra lặp trang (khi GelbeSeiten wrap vòng lại trang 1)
            new_in_page = 0
            for art in arts:
                parsed = parse_gelbeseiten_article(art, region=city, branch=branch)
                comp_name = parsed['name']
                comp_id = parsed['id'] or (comp_name + parsed['city'])

                if comp_id in seen_ids or not comp_name:
                    continue

                seen_ids.add(comp_id)
                items.append(parsed)
                new_in_page += 1

            if new_in_page == 0:
                # Đã duyệt hết tất cả doanh nghiệp của thành phố này
                break

            # Kiểm tra tổng số Treffer trên trang đầu để dừng sớm
            if p == 1:
                m_hits = re.search(r'([\d\.\,]+)\s*(?:Treffer|Ergebnisse)', sp.text)
                if m_hits:
                    total_hits = int(m_hits.group(1).replace('.', '').replace(',', ''))
                    calculated_pages = (total_hits + 49) // 50
                    if calculated_pages < max_pages:
                        max_pages = calculated_pages

        except Exception:
            break

    return items


def scrape_gelbeseiten_all_regions(cities=None, branches=None):
    """
    Cào đa luồng tất cả các vùng của GelbeSeiten theo yêu cầu tránh bỏ sót data.
    Mặc định quét Berlin (trọng tâm) + Top các đại đô thị kinh tế Đức.
    """
    if not cities:
        cities = DEFAULT_GERMAN_CITIES
    if not branches:
        branches = ['personalvermittlung', 'zeitarbeit']

    print(f"\n[2/3] Dang cao GelbeSeiten tren {len(cities)} thanh pho/vung (Nganh: {', '.join(branches)})...")
    tasks = []
    for city in cities:
        for branch in branches:
            tasks.append((city, branch))

    all_results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(scrape_gelbeseiten_city_branch, city, branch): (city, branch) for city, branch in tasks}
        for fut in as_completed(futures):
            city, branch = futures[fut]
            completed += 1
            try:
                res = fut.result()
                all_results.extend(res)
                print(f"  [{completed}/{len(tasks)}] [+] GelbeSeiten {branch.capitalize()} -> {city.capitalize()}: {len(res)} doanh nghiep")
            except Exception as e:
                print(f"  [{completed}/{len(tasks)}] [!] Loi {city} ({branch}): {e}")

    print(f"[+] Tong so records thu thap tu GelbeSeiten: {len(all_results)}")
    return all_results


# -------------------------------------------------------------
# B2B EMAIL & CONTACTS CRAWLER (Skill crawl-mail)
# -------------------------------------------------------------
domain_cache = {}
if DOMAIN_CACHE_FILE.exists():
    try:
        with open(DOMAIN_CACHE_FILE, 'r', encoding='utf-8') as f:
            domain_cache = json.load(f)
    except Exception:
        domain_cache = {}


def detect_client_redirect(html_content, base_url):
    """
    Tự động phát hiện chuyển hướng trang phía client (Client-side Redirect):
    1. Thẻ Meta Refresh: <meta http-equiv="refresh" content="5; url=https://promedis24.de">
    2. JavaScript location: window.location.href, location.replace, location.assign
    3. Biến config JavaScript: CONFIG.targetDomain, targetDomain, redirectUrl, redirectTo
    4. Nút bấm redirect / splash link trên landing page
    -> Lấy ngay URL đích trong 0.001s mà KHÔNG CẦN CHỜ (sleep 5s), giúp tăng tốc độ cào gấp hàng chục lần!
    """
    if not html_content:
        return None

    # 1. Meta refresh
    m_meta = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'](?:\d+\s*;\s*url=)?([^"\']+)["\']', html_content, re.I)
    if m_meta:
        target = m_meta.group(1).strip().strip("'\"")
        if target:
            return urllib.parse.urljoin(base_url, target)

    # 2. JavaScript location assignment / Config target
    patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*["\'](https?://[^"\']+)["\']',
        r'(?:window\.)?location\.replace\(["\'](https?://[^"\']+)["\']\)',
        r'(?:window\.)?location\.assign\(["\'](https?://[^"\']+)["\']\)',
        r'targetDomain\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'redirectUrl\s*[:=]\s*["\'](https?://[^"\']+)["\']',
        r'redirectTo\s*[:=]\s*["\'](https?://[^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html_content, re.I)
        if m:
            target = m.group(1).strip()
            if target != base_url and not target.endswith(urllib.parse.urlparse(base_url).netloc):
                return urllib.parse.urljoin(base_url, target)

    # 3. Nút bấm redirect hoặc link chuyển tiếp trên splash page
    m_btn = re.search(r'<a[^>]+(?:id=["\']redirectButton["\']|class=["\'][^"\']*(?:redirect|forward)[^"\']*["\'])[^>]+href=["\']([^"\']+)["\']', html_content, re.I)
    if m_btn:
        target = m_btn.group(1).strip()
        if target.startswith('http'):
            return target

    return None


def crawl_website_contacts(web_url):
    """
    Bóc tách Email & SĐT đa tầng từ website chính thức doanh nghiệp Đức:
    - Tra cứu domain cache trước để tránh crawl lại
    - Quét trang chủ, bóc tách thẻ <a> thực tế trên DOM (Priority 10)
    - Quét /impressum, /kontakt, /karriere, /jobs
    - Giải mã Cloudflare data-cfemail, regex chuẩn
    - Chấm điểm B2B tuyển dụng chuẩn Rule 3 (Bewerbung, GF, Info)
    """
    if not is_valid_website(web_url):
        return '', '', ''

    if not web_url.startswith('http'):
        web_url = 'https://' + web_url

    parsed = urllib.parse.urlparse(web_url)
    root_domain = parsed.netloc.lower()
    root_domain = re.sub(r'^www\.', '', root_domain)
    root_url = f"{parsed.scheme}://{parsed.netloc}"

    if root_domain in domain_cache:
        c = domain_cache[root_domain]
        return c.get('email', ''), c.get('phone', ''), root_domain

    candidate_emails = []
    candidate_phones = []

    urls_to_visit = [
        web_url,
        f"{root_url}/impressum",
        f"{root_url}/impressum/",
        f"{root_url}/kontakt",
        f"{root_url}/karriere",
        f"{root_url}/jobs"
    ]
    seen_urls = set()
    ordered_urls = []
    for u in urls_to_visit:
        if u not in seen_urls:
            seen_urls.add(u)
            ordered_urls.append(u)

    scanned_count = 0
    max_scan = 4
    idx = 0

    while idx < len(ordered_urls) and scanned_count < max_scan:
        u = ordered_urls[idx]
        idx += 1
        scanned_count += 1
        try:
            resp = requests.get(u, headers=HEADERS, verify=False, timeout=4)
            if resp.status_code == 200:
                text = resp.text
                sp = BeautifulSoup(text, 'html.parser')

                # Ưu tiên số 1: Tự động nhận diện Client-side redirect & link DOM menu thực tế
                if scanned_count == 1:
                    redir_u = detect_client_redirect(text, u)
                    if redir_u and redir_u not in seen_urls:
                        seen_urls.add(redir_u)
                        ordered_urls.insert(idx, redir_u)

                    for a in sp.find_all('a', href=True):
                        h = a['href'].strip()
                        txt = a.get_text(' ', strip=True).lower()
                        if any(k in h.lower() or k in txt for k in DE_PRIORITY_KEYWORDS):
                            full_u = urllib.parse.urljoin(root_url, h)
                            if full_u.startswith(root_url) and full_u not in seen_urls:
                                seen_urls.add(full_u)
                                ordered_urls.insert(idx, full_u)

                # 1. Mailto links
                for a in sp.find_all('a', href=True):
                    h = a['href']
                    if h.lower().startswith('mailto:'):
                        em = clean_email(h)
                        if em:
                            candidate_emails.append(em)
                    elif h.lower().startswith('tel:'):
                        ph = clean_phone_de(h.replace('tel:', ''))
                        if ph:
                            candidate_phones.append(ph)

                # 2. Cloudflare XOR decode
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', text):
                    try:
                        r = int(cf[:2], 16)
                        dec = ''.join([chr(int(cf[i:i+2], 16) ^ r) for i in range(2, len(cf), 2)])
                        c_dec = clean_email(dec)
                        if c_dec:
                            candidate_emails.append(c_dec)
                    except Exception:
                        pass

                # 3. Direct Regex Email
                raw_emails = re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', text)
                for em in raw_emails:
                    c_em = clean_email(em)
                    if c_em and score_email_b2b_de(c_em, root_domain) > 0:
                        candidate_emails.append(c_em)

                # 4. Direct Regex Phone Germany
                raw_phones = re.findall(r'(?:\+49|0049|0)\s*(?:\([0-9]+\)|[0-9]+)[\s\/\-]?[0-9]{2,4}[\s\-]?[0-9]{3,8}', text)
                for ph in raw_phones:
                    c_ph = clean_phone_de(ph)
                    if c_ph:
                        candidate_phones.append(c_ph)

                if candidate_emails and any(score_email_b2b_de(e, root_domain) >= 40 for e in candidate_emails):
                    break
        except Exception:
            continue

    # Chọn duy nhất 1 email có điểm B2B cao nhất
    best_email = ''
    best_score = -1
    for em in set(candidate_emails):
        sc = score_email_b2b_de(em, root_domain)
        if sc > best_score:
            best_score = sc
            best_email = em

    best_phone = candidate_phones[0] if candidate_phones else ''
    domain_cache[root_domain] = {'email': best_email, 'phone': best_phone}
    return best_email, best_phone, root_domain


# -------------------------------------------------------------
# MASTER DEDUPLICATION & MERGE PIPELINE
# -------------------------------------------------------------
def run_master_pipeline(cities=None, only_berlin=False, export_only=False, refresh_gs=False):
    start_time = time.time()
    print("=" * 80)
    print("  HE THONG THU THAP & HOP NHAT NGANH NHAN SU & ZEITARBEIT DUC (DE_AGCY_WEBD)")
    print("  Nguon: wer-zu-wem.de (43 trang, ~327 tap doan) + gelbeseiten.de (24 dai do thi)")
    print("  Tuan thu: GEMINI.md - Rule 1, 2, 3, 5, 8, 9, 10, 11, 12")
    print("=" * 80)

    # Kiểm tra cờ xuất nhanh từ Cache
    if (export_only or '--export-only' in sys.argv) and CACHE_FILE.exists():
        print(f"[*] Dang tai du lieu tu cache: {CACHE_FILE}")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            master_list = json.load(f)
        export_and_sync(master_list, start_time)
        return

    # 1. Scrape wer-zu-wem.de (toàn bộ 43 trang, 327 tập đoàn)
    wzw_items = scrape_wer_zu_wem()

    # 2. GelbeSeiten.de records: load từ cache nếu đã cào trước đó tránh quét lại lâu
    cached_gs = []
    if CACHE_FILE.exists() and not refresh_gs:
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                prev_cache = json.load(f)
            cached_gs = [d for d in prev_cache if 'gelbeseiten' in d.get('all_sources', '').lower()]
            if cached_gs:
                print(f"\n[2/3] [+] Da tai san {len(cached_gs)} records GelbeSeiten tu checkpoint cache!")
        except Exception:
            cached_gs = []

    if cached_gs and not refresh_gs:
        gs_items = cached_gs
    else:
        if only_berlin:
            target_cities = ['berlin']
        elif cities:
            target_cities = cities
        else:
            target_cities = DEFAULT_GERMAN_CITIES
        gs_items = scrape_gelbeseiten_all_regions(cities=target_cities)

    # 3. Deduplication & Merge across all sources
    print("\n[3/3] Dang hop nhat, loc danh sach den va lam giau Email B2B...")
    merged_dict = {}
    blacklist_count = 0

    # Hàm tạo key định danh
    def make_comp_key(item):
        web = item.get('website', '')
        if web and is_valid_website(web):
            try:
                domain = urllib.parse.urlparse(web).netloc.lower()
                domain = re.sub(r'^www\.', '', domain)
                if domain:
                    return f"DOM_{domain}"
            except Exception:
                pass
        c_name = item.get('name') or item.get('company_name', '')
        norm_n = normalize_company_name(c_name)
        norm_city = normalize_company_name(item.get('city', ''))
        return f"NAME_{norm_n}_{norm_city}"

    # Merge wer-zu-wem items first (Top Giants)
    for it in wzw_items:
        c_name = it.get('name', '')
        if is_blacklisted_company(c_name):
            blacklist_count += 1
            print(f"[-] Rule 12 Exclusion: {c_name}")
            continue

        key = make_comp_key(it)
        merged_dict[key] = {
            'company_name': c_name,
            'legal_name': it.get('legal_name', c_name),
            'category': it.get('category', 'Zeitarbeit / Personaldienstleister'),
            'branch': it.get('branch', 'zeitarbeit'),
            'city': it.get('city', ''),
            'region': it.get('city', ''),
            'street': it.get('street', ''),
            'zipcode': it.get('zipcode', ''),
            'address': f"{it.get('street', '')}, {it.get('zipcode', '')} {it.get('city', '')}".strip(', '),
            'phone': it.get('phone', ''),
            'email': it.get('email', ''),
            'website': it.get('website', ''),
            'managing_director': it.get('managing_director', ''),
            'employees': it.get('employees', ''),
            'revenue_class': it.get('revenue_class', ''),
            'detail_url': it.get('detail_url', ''),
            'source_primary': 'wer-zu-wem.de',
            'all_sources': 'wer-zu-wem.de'
        }

    # Merge GelbeSeiten items
    for gs in gs_items:
        c_name = gs.get('name') or gs.get('company_name', '')
        if is_blacklisted_company(c_name):
            blacklist_count += 1
            print(f"[-] Rule 12 Exclusion: {c_name}")
            continue

        key = make_comp_key(gs)
        if key in merged_dict:
            # Update fields if missing
            exist = merged_dict[key]
            if not exist.get('website') and gs.get('website'):
                exist['website'] = gs.get('website')
            if not exist.get('phone') and gs.get('phone'):
                exist['phone'] = gs.get('phone')
            if not exist.get('email') and gs.get('email'):
                exist['email'] = gs.get('email')
            if not exist.get('address') and gs.get('address'):
                exist['address'] = gs.get('address')
            if not exist.get('managing_director') and gs.get('managing_director'):
                exist['managing_director'] = gs.get('managing_director')
            if not exist.get('employees') and gs.get('employees'):
                exist['employees'] = gs.get('employees')
            gs_src = gs.get('source_primary') or gs.get('source', 'gelbeseiten.de')
            if 'gelbeseiten' not in exist['all_sources']:
                exist['all_sources'] += ' + ' + gs_src
        else:
            merged_dict[key] = {
                'company_name': c_name,
                'legal_name': gs.get('legal_name', c_name),
                'category': gs.get('category', 'Zeitarbeit / Personalvermittlung'),
                'branch': gs.get('branch', ''),
                'city': gs.get('city', ''),
                'region': gs.get('region', ''),
                'street': gs.get('street', ''),
                'zipcode': gs.get('zipcode', ''),
                'address': gs.get('address', ''),
                'phone': gs.get('phone', ''),
                'email': gs.get('email', ''),
                'website': gs.get('website', ''),
                'managing_director': gs.get('managing_director', ''),
                'employees': gs.get('employees', ''),
                'revenue_class': gs.get('revenue_class', ''),
                'detail_url': gs.get('detail_url', ''),
                'source_primary': gs.get('source_primary', gs.get('source', 'gelbeseiten.de')),
                'all_sources': gs.get('all_sources', gs.get('source', 'gelbeseiten.de'))
            }

    master_list = list(merged_dict.values())
    print(f"\n[+] Tong so doanh nghiep duy nhat sau hop nhat: {len(master_list)}")
    print(f"[+] Da loai tru {blacklist_count} doanh nghiep khoi danh sach den (Rule 12)")

    # 4. Crawl B2B Emails & Phones from Websites (if missing email)
    need_email_crawl = [it for it in master_list if it.get('website') and not it.get('email')]
    print(f"[*] Dang quet bóc tách Email B2B cho {len(need_email_crawl)} website doanh nghiep...")

    def email_worker(it):
        w = it.get('website')
        if not w:
            return it
        em, ph, _ = crawl_website_contacts(w)
        if em and not it.get('email'):
            it['email'] = em
        if ph and not it.get('phone'):
            it['phone'] = ph
        return it

    with ThreadPoolExecutor(max_workers=15) as ex:
        list(ex.map(email_worker, need_email_crawl))

    # Save domain cache
    try:
        with open(DOMAIN_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(domain_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Save Checkpoint Cache JSON
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(master_list, f, ensure_ascii=False, indent=2)
    print(f"[+] Da luu checkpoint tai: {CACHE_FILE}")

    # 5. Export and Sync
    export_and_sync(master_list, start_time)


def export_and_sync(master_list, start_time):
    """Xuất file 0RAW, 2COL và ONLY_EMAILS_READY chuẩn Rule 1, 2, 3, 10."""
    print(f"\n[*] Dang xuat file thô hợp nhất 24 cot: {RAW_CSV_PATH}")
    with open(RAW_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(RAW_COLUMNS)
        for idx, it in enumerate(master_list, 1):
            phone = clean_phone_de(it.get('phone', ''))
            email = clean_email(it.get('email', ''))
            writer.writerow([
                idx,
                it.get('company_name', ''),
                it.get('legal_name', ''),
                it.get('category', ''),
                it.get('branch', ''),
                it.get('city', ''),
                it.get('region', ''),
                it.get('street', ''),
                it.get('zipcode', ''),
                it.get('address', ''),
                phone,
                email,
                it.get('website', ''),
                it.get('managing_director', ''),
                it.get('employees', ''),
                it.get('revenue_class', ''),
                it.get('detail_url', ''),
                it.get('source_primary', ''),
                it.get('all_sources', '')
            ])

    # Chuẩn hóa file Cold Mail 20 cột (ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU)
    with_email = []
    without_email = []

    for it in master_list:
        c_name = it.get('company_name', '')
        phone = clean_phone_de(it.get('phone', ''))
        email = clean_email(it.get('email', ''))

        manager = it.get('managing_director', '').strip()
        title = 'Geschäftsführer / Managing Director' if manager else 'Director / Geschaeftsfuehrer'

        website = it.get('website', '')
        source_link = website or it.get('detail_url', '')
        category = it.get('category', '') or 'Personalvermittlung / Zeitarbeit'

        addr = it.get('address', '').strip()
        if not addr:
            loc = it.get('city', '') or it.get('region', '')
            addr = f"{loc}, Germany" if loc else "Germany"

        row = {
            'Công ty': c_name,
            'Chức danh': title,
            'Người liên hệ': manager,
            'SĐT': phone,
            'Liên Hệ': source_link,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else source_link,
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': category
        }

        if email:
            with_email.append(row)
        else:
            without_email.append(row)

    ordered_coldmail = with_email + without_email

    print(f"[*] Dang xuat file chuan Cold Mail 20 cot: {COL2_CSV_PATH}")
    with open(COL2_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS_20)
        for idx, row in enumerate(ordered_coldmail, 1):
            writer.writerow([
                idx,
                row['Công ty'],
                row['Chức danh'],
                row['Người liên hệ'],
                row['SĐT'],
                row['Liên Hệ'],
                row['Email'],
                row['Liên Hệ mail'],
                row['Địa chỉ'],
                row['Lương'],
                row['Ngày đăng'],
                row['Hạn tuyển'],
                row['Check gửi'],
                row['Last Subject'],
                row['Last Body HTML'],
                row['Trạng thái Reply'],
                row['Lần Follow-up'],
                row['Ngày Follow-up gần nhất'],
                row['Mailbox đã dùng'],
                row['Category']
            ])

    # Xuất file rút gọn chỉ chứa các công ty có Email
    print(f"[*] Dang xuat file rut gon email: {READY_CSV_PATH}")
    with open(READY_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS_20)
        for idx, row in enumerate(with_email, 1):
            writer.writerow([
                idx,
                row['Công ty'],
                row['Chức danh'],
                row['Người liên hệ'],
                row['SĐT'],
                row['Liên Hệ'],
                row['Email'],
                row['Liên Hệ mail'],
                row['Địa chỉ'],
                row['Lương'],
                row['Ngày đăng'],
                row['Hạn tuyển'],
                row['Check gửi'],
                row['Last Subject'],
                row['Last Body HTML'],
                row['Trạng thái Reply'],
                row['Lần Follow-up'],
                row['Ngày Follow-up gần nhất'],
                row['Mailbox đã dùng'],
                row['Category']
            ])

    # Đồng bộ sang archive và csdl_mlt
    for target_dir in [ARCHIVE_DIR, CSDL_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        for p in [RAW_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH]:
            dest = target_dir / p.name
            shutil.copy2(p, dest)
        print(f"[+] Da dong bo thanh cong sang: {target_dir}")

    elapsed = round(time.time() - start_time, 1)
    with_web_cnt = sum(1 for it in master_list if it.get('website'))
    print("\n" + "=" * 80)
    print("  HOAN THANH QUA TRINH THU THAP & HOP NHAT NGANH NHAN SU DUC!")
    print(f"  Tong thoi gian chay: {elapsed} giay")
    print(f"  Tong so DN hop nhat duy nhat: {len(master_list)}")
    print(f"  Tong so DN co Website: {with_web_cnt}")
    print(f"  Tong so DN co Email B2B: {len(with_email)} (Duoc day len dau tu dong)")
    print(f"  Tep thô: {RAW_CSV_PATH.name}")
    print(f"  Tep ColdMail: {COL2_CSV_PATH.name}")
    print(f"  Tep chi email: {READY_CSV_PATH.name}")
    print("=" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Scrape and merge German Staffing & Recruitment Agencies")
    parser.add_argument('--berlin-only', action='store_true', help="Scrape only Berlin region")
    parser.add_argument('--cities', type=str, default=None, help="Comma-separated list of German cities")
    parser.add_argument('--export-only', action='store_true', help="Regenerate CSVs from existing cache")
    parser.add_argument('--refresh-gs', action='store_true', help="Force re-scraping GelbeSeiten instead of loading cached GelbeSeiten records")

    args = parser.parse_args()
    city_list = [c.strip().lower() for c in args.cities.split(',') if c.strip()] if args.cities else None

    run_master_pipeline(
        cities=city_list,
        only_berlin=args.berlin_only,
        export_only=args.export_only,
        refresh_gs=args.refresh_gs
    )
