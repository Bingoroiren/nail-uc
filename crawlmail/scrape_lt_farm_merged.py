# -*- coding: utf-8 -*-
"""
HỆ THỐNG THU THẬP VÀ HỢP NHẤT DỮ LIỆU NÔNG NGHIỆP LITVA (LT_FARM_WEBD)
=======================================================================
Nguồn dữ liệu:
1. Fermos.lt: Top 100 doanh nghiệp nông nghiệp lớn nhất Litva (Doanh thu & Lợi nhuận)
   URL: https://fermos.lt/en/rankings/top-agricultural-companies
2. Firmavis.com: Danh bạ doanh nghiệp nông nghiệp & lâm nghiệp Litva (NACE 01, 02)
   URL: https://firmavis.com/industries/lt/agriculture

Quy chuẩn kỹ thuật bắt buộc theo GEMINI.md:
- Rule 1: CSV UTF-8 with BOM (utf-8-sig) ONLY. Không dùng Excel.
- Rule 2: Số điện thoại luôn có dấu nháy đơn (') ở đầu (ví dụ: '+370...).
- Rule 3: Bộ chấm điểm B2B tuyển chọn 1 email giá trị nhất, lọc sạch 100% rác/template.
          Đẩy 100% doanh nghiệp có email lên đầu danh sách (with_email + without_email).
- Rule 5: Lưu tăng dần và Checkpoint cache JSON (cache_lt_farm_merged.json).
- Rule 6: Lọc trùng lặp qua 9-digit Company Code (Įmonės kodas) và Normalized Name.
- Rule 10: Tên file cố định chuẩn 17 ký tự:
  * LT_FARM_WEBD_0RAW.csv: Dữ liệu hợp nhất thô đầy đủ thuộc tính tài chính & pháp lý.
  * LT_FARM_WEBD_2COL.csv: File chuẩn Cold Mail 20 cột, đẩy email lên đầu.
  * LT_FARM_WEBD_ONLY_EMAILS_READY.csv: Danh sách chỉ gồm các công ty có email B2B.
- Rule 12: Loại trừ danh sách đen vĩnh viễn (Scandi Standard Baltics, Biliarta, Daigre).
- Tự động đồng bộ sang csdl_mlt/ và archive/lt_lithuania/.
"""

import os
import sys
import re
import csv
import json
import time
import shutil
import random
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV_PATH = ROOT_DIR / "LT_FARM_WEBD_0RAW.csv"
COL2_CSV_PATH = ROOT_DIR / "LT_FARM_WEBD_2COL.csv"
READY_CSV_PATH = ROOT_DIR / "LT_FARM_WEBD_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_lt_farm_merged.json"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CSDL_DIR = ROOT_DIR / "csdl_mlt"

RAW_COLUMNS = [
    'No.', 'Rank_Fermos', 'Company_Code', 'Company_Name', 'Legal_Form', 'VAT_Number',
    'Municipality', 'Location', 'Full_Address', 'Sub_Industry', 'Employees',
    'Revenue_Fermos', 'Revenue_Firmavis', 'Net_Profit', 'Taxes_Paid', 'Fin_Year',
    'Average_Wage', 'Register_Status', 'Website', 'Phone', 'Email',
    'Fermos_URL', 'Firmavis_URL', 'Source_Merged'
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
    'Accept-Language': 'en-US,en;q=0.9,lt;q=0.8',
}

JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'wix.com', 'wixpress.com', 'wordpress.com', 'wordpress.org',
    'example.com', 'domain.com', 'email.com', 'yourcompany.com', 'yourdomain.com',
    'localservices.be', 'bizbook.be', 'pagesdor.be', 'goudengids.be', 'schema.org'
}

JUNK_EMAIL_PREFIXES = {
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user', 'name', 'example', 'domain', 'no-reply', 'noreply', 'donotreply',
    'privacy', 'gdpr', 'abuse', 'webmaster', 'postmaster'
}


def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def normalize_company_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    legal_terms = [
        'uzdaroji akcine bendrove', 'akcine bendrove', 'zemes ukio kooperatyvas',
        'zemes ukio bendrove', 'valstybes imone', 'private limited liability company',
        'public limited company', 'agricultural company', 'cooperative',
        'uab', 'ab', 'zub', 'vsi', 'mb', 'kb', 'zuk'
    ]
    for term in legal_terms:
        n = re.sub(r'\b' + term + r'\b', ' ', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n.strip()


def clean_phone_lt(raw_phone):
    """Chuẩn hóa số điện thoại Litva: có nháy đơn (') ở đầu, lọc bỏ rác và decode URL"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = urllib.parse.unquote(str(raw_phone)).strip()
    s = re.sub(r'^tel:\s*', '', s, flags=re.I)
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff']:
        s = s.replace(bad, ' ')
    s = s.lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''

    # Chuẩn hóa cấu trúc SĐT Litva (Lithuanian number plan)
    if digits.startswith('370'):
        if len(digits) != 11:
            return ''  # SĐT Litva quốc tế chuẩn phải đúng 11 chữ số (370 + 8 số)
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[-8:]
    elif len(digits) == 8:
        digits = '370' + digits
    else:
        return ''

    if digits.startswith('370') and len(digits) == 11:
        # Di động: +370 6xx xxxxx
        if digits[3] == '6':
            formatted = f"+370 {digits[3:6]} {digits[6:]}"
            return f"'{formatted}"
        # Cố định Vilnius: +370 5 xxx xxxx
        elif digits[3] == '5':
            formatted = f"+370 {digits[3]} {digits[4:7]} {digits[7:]}"
            return f"'{formatted}"
        # Cố định các tỉnh/vùng khác: +370 xx xxx xxx
        else:
            formatted = f"+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
            return f"'{formatted}"

    return ''


def clean_email(email):
    """Làm sạch ký tự ẩn và kiểm tra định dạng email"""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    em = em.lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    user_part, domain_part = em.split('@', 1)
    if domain_part in JUNK_EMAIL_DOMAINS or any(domain_part.endswith('.' + d) for d in JUNK_EMAIL_DOMAINS):
        return ""
    if user_part in JUNK_EMAIL_PREFIXES:
        return ""
    if any(img_ext in domain_part for img_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg']):
        return ""
    return em


def score_email_b2b(email, website_domain=""):
    """
    Chấm điểm email tuyển dụng B2B Manpower Agency theo chuẩn Rule 3:
    - Trùng domain website (+50đ)
    - Tuyển dụng / HR (+50đ)
    - Ban Lãnh đạo / Giám đốc (+45đ)
    - Liên hệ chính thức / Info (+40đ)
    - Đích danh cá nhân theo domain riêng (+25đ)
    - Webmail (+10đ)
    - Hỗ trợ / Kế toán chung (+5đ)
    """
    if not email:
        return 0
    em = clean_email(email)
    if not em:
        return 0
    
    score = 0
    user, domain = em.split('@', 1)
    
    if website_domain and website_domain in domain:
        score += 50

    # 1. HR / Tuyển dụng (Ưu tiên số 1)
    hr_kw = ['darbas', 'idarinimas', 'praca', 'kariera', 'hr', 'personalas', 'personalne', 'jobs', 'recruitment', 'nabor', 'career', 'recruiting']
    if any(k in user for k in hr_kw):
        score += 50
        return score

    # 2. Ban Lãnh đạo / Giám đốc (Ưu tiên số 2)
    exec_kw = ['vadovas', 'direktorius', 'generalinis', 'ceo', 'director', 'manager', 'vedenie', 'riaditel', 'konatel', 'sales', 'pardavimai', 'komercija']
    if any(k in user for k in exec_kw):
        score += 45
        return score

    # 3. Liên hệ chính thức / Info / Văn phòng (Ưu tiên số 3)
    info_kw = ['info', 'kontakt', 'kontaktai', 'contact', 'biuras', 'office', 'sekretoriatas', 'administracija', 'bendra', 'bendras']
    if any(k in user for k in info_kw):
        score += 40
        return score

    # 4. Cá nhân theo domain riêng
    free_webmails = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'inbox.lt', 'one.lt', 'mail.ru']
    if domain not in free_webmails and '.' in user:
        score += 25
        return score

    # 5. Webmail miễn phí
    if domain in free_webmails:
        score += 10
        return score

    # 6. Kế toán / kỹ thuật
    tech_kw = ['buhalterija', 'apskaita', 'faktura', 'support', 'admin', 'servis']
    if any(k in user for k in tech_kw):
        score += 5
        return score

    return 15


# -------------------------------------------------------------
# CRAWLERS
# -------------------------------------------------------------

def scrape_fermos_rankings():
    """Thu thập 100 doanh nghiệp hàng đầu từ Fermos.lt"""
    url = 'https://fermos.lt/en/rankings/top-agricultural-companies'
    print(f"[1/4] Dang cao Fermos.lt ranking: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        s = BeautifulSoup(r.text, 'html.parser')
        tbl = s.find('table')
        if not tbl:
            print("[!] Khong tim thay bang du lieu tren Fermos.lt")
            return []
        
        rows = []
        for tr in tbl.find_all('tr')[1:]:
            tds = tr.find_all('td')
            if len(tds) >= 6:
                rank = tds[0].get_text(strip=True).replace('.', '').strip()
                comp_a = tds[1].find('a')
                name = comp_a.get_text(strip=True) if comp_a else tds[1].get_text(strip=True)
                href = comp_a['href'] if comp_a and comp_a.has_attr('href') else ''
                if href and not href.startswith('http'):
                    href = 'https://fermos.lt' + href
                muni = tds[2].get_text(strip=True)
                fin_year = tds[3].get_text(strip=True)
                rev = tds[4].get_text(strip=True)
                profit = tds[5].get_text(strip=True)
                taxes = tds[6].get_text(strip=True) if len(tds) > 6 else ''
                
                rows.append({
                    'rank': rank,
                    'name': name,
                    'detail_url': href,
                    'municipality': muni,
                    'fin_year': fin_year,
                    'revenue': rev,
                    'net_profit': profit,
                    'taxes': taxes
                })
        print(f"[+] Da cao {len(rows)} doanh nghiep tu Fermos.lt")
        return rows
    except Exception as e:
        print(f"[!] Loi cao Fermos.lt: {e}")
        return []


def fetch_fermos_detail(item):
    """Bóc tách chi tiết từ trang hồ sơ Fermos.lt"""
    url = item.get('detail_url')
    if not url:
        return item
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            text = BeautifulSoup(res.text, 'html.parser').get_text('\n', strip=True)
            
            m_code = re.search(r'Company code\s*\n\s*(\d{7,9})', text, re.IGNORECASE)
            if m_code: item['code'] = m_code.group(1)
            
            m_vat = re.search(r'VAT registered\s*\n\s*([^\n]+)', text, re.IGNORECASE)
            if m_vat:
                vat_val = m_vat.group(1).strip()
                # Extract LT code if present inside parenthesis
                m_vcode = re.search(r'(LT\d+)', vat_val)
                item['vat'] = m_vcode.group(1) if m_vcode else vat_val
            
            m_act = re.search(r'Main activity\s*\n\s*([^\n]+)', text, re.IGNORECASE)
            if m_act: item['main_activity'] = m_act.group(1).strip()
            
            m_emp = re.search(r'Insured employees\s*(?:\([^)]+\))?\s*\n\s*([\d\s,]+)', text, re.IGNORECASE)
            if m_emp: item['employees'] = m_emp.group(1).replace(' ', '').replace(',', '').strip()
            
            m_wage = re.search(r'Average monthly wage\s*\n\s*([^\n]+)', text, re.IGNORECASE)
            if m_wage: item['avg_wage'] = m_wage.group(1).strip()
            
            m_stat = re.search(r'Register status\s*\n\s*([^\n]+)', text, re.IGNORECASE)
            if m_stat: item['reg_status'] = m_stat.group(1).strip()
    except Exception:
        pass
    return item


def scrape_firmavis_directory():
    """Thu thập toàn bộ doanh nghiệp nông nghiệp từ Firmavis.com (3 trang)"""
    print("[2/4] Dang cao Firmavis.com directory...")
    rows = []
    for p in range(1, 4):
        p_url = 'https://firmavis.com/industries/lt/agriculture' if p == 1 else f'https://firmavis.com/industries/lt/agriculture/{p}'
        try:
            r = requests.get(p_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            s = BeautifulSoup(r.text, 'html.parser')
            tbl = s.find('table')
            if not tbl:
                continue
            for tr in tbl.find_all('tr')[1:]:
                tds = tr.find_all('td')
                if not tds:
                    continue
                c_td = tds[0]
                a_tag = c_td.find('a')
                c_url = ('https://firmavis.com' + a_tag['href']) if a_tag and a_tag.has_attr('href') else ''
                c_text = c_td.get_text(' ', strip=True)
                
                code_m = re.search(r'\b(\d{7,9})\b', c_text)
                code = code_m.group(1) if code_m else ''
                name = a_tag.get_text(strip=True) if a_tag else c_text
                if code and name.endswith(code):
                    name = name[:-len(code)].strip()
                    
                location = tds[1].get_text(strip=True) if len(tds) > 1 else ''
                location = re.sub(r'[\U0001F1E6-\U0001F1FF]', '', location).strip()
                
                sub_ind = tds[2].get_text(' ', strip=True) if len(tds) > 2 else ''
                emp = tds[3].get_text(strip=True) if len(tds) > 3 else ''
                rev = tds[4].get_text(strip=True) if len(tds) > 4 else ''
                
                rows.append({
                    'name': name,
                    'code': code,
                    'detail_url': c_url,
                    'location': location,
                    'sub_industry': sub_ind,
                    'employees': emp,
                    'revenue': rev
                })
        except Exception as e:
            print(f"[!] Loi trang {p} Firmavis: {e}")
    print(f"[+] Da cao {len(rows)} doanh nghiep tu Firmavis.com")
    return rows


def fetch_firmavis_detail(item):
    """Bóc tách thông tin chi tiết từ trang hồ sơ Firmavis.com"""
    url = item.get('detail_url')
    if not url:
        return item
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            web_a = soup.find('a', href=lambda h: h and h.startswith('http') and 'firmavis' not in h)
            if web_a:
                item['website'] = web_a['href'].strip()
            
            addr_dt = soup.find(lambda e: e.name in ['dt','div','span','p'] and e.text.strip() == 'Address')
            if addr_dt and addr_dt.find_next_sibling():
                item['address'] = addr_dt.find_next_sibling().get_text(' ', strip=True)
                
            vat_dt = soup.find(lambda e: e.name in ['dt','div','span','p'] and e.text.strip() == 'VAT number')
            if vat_dt and vat_dt.find_next_sibling():
                item['vat'] = vat_dt.find_next_sibling().get_text(' ', strip=True)
                
            legal_dt = soup.find(lambda e: e.name in ['dt','div','span','p'] and e.text.strip() == 'Legal form')
            if legal_dt and legal_dt.find_next_sibling():
                item['legal_form'] = legal_dt.find_next_sibling().get_text(' ', strip=True)
    except Exception:
        pass
    return item


def discover_website_duckduckgo(company_name):
    """Tìm website chính thức cho doanh nghiệp nếu chưa có từ danh bạ"""
    if not company_name:
        return ""
    clean_name = re.sub(r'["\']', '', company_name)
    query = f'{clean_name} lietuva svetaine OR website'
    url = f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', class_='result__url'):
                href = a.get('href', '')
                m_uddg = re.search(r'uddg=([^&]+)', href)
                if m_uddg:
                    target_url = urllib.parse.unquote(m_uddg.group(1))
                    domain = urllib.parse.urlparse(target_url).netloc.lower()
                    if not any(d in domain for d in ['duckduckgo', 'rekvizitai', 'info.lt', 'firmavis', 'fermos', 'facebook', 'linkedin', 'yellowpages', 'wikipedia']):
                        return target_url
    except Exception:
        pass
    return ""


def crawl_website_contacts(website_url):
    """
    Bóc tách Email và SĐT từ website chính thức:
    - Quét trang chủ và các subpages bản địa Litva: kontaktai, apie-mus, contact...
    - Hỗ trợ decode, lọc rác và chấm điểm B2B chuẩn Rule 3.
    """
    if not website_url or not str(website_url).startswith('http'):
        return '', '', ''
    
    parsed = urllib.parse.urlparse(website_url)
    base_domain = parsed.netloc.lower()
    root_url = f"{parsed.scheme}://{parsed.netloc}"
    
    candidate_emails = []
    candidate_phones = []
    
    urls_to_visit = [
        website_url,
        f"{root_url}/kontaktai",
        f"{root_url}/kontaktai/",
        f"{root_url}/lt/kontaktai",
        f"{root_url}/apie-mus",
        f"{root_url}/contacts",
        f"{root_url}/contact"
    ]
    # Deduplicate while preserving order
    seen_urls = set()
    ordered_urls = []
    for u in urls_to_visit:
        if u not in seen_urls:
            seen_urls.add(u)
            ordered_urls.append(u)
            
    for u in ordered_urls[:4]:  # Visit max 4 key pages
        try:
            resp = requests.get(u, headers=HEADERS, verify=False, timeout=6)
            if resp.status_code == 200:
                text = resp.text
                
                # Emails via mailto:
                soup = BeautifulSoup(text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.lower().startswith('mailto:'):
                        em = clean_email(href)
                        if em:
                            candidate_emails.append(em)
                    elif href.lower().startswith('tel:'):
                        ph = clean_phone_lt(href.replace('tel:', ''))
                        if ph:
                            candidate_phones.append(ph)
                            
                # Raw text regex emails
                raw_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                for em in raw_emails:
                    cleaned = clean_email(em)
                    if cleaned:
                        candidate_emails.append(cleaned)
                        
                # Raw text phone patterns for Lithuania: +370 or 8 6...
                raw_phones = re.findall(r'(?:\+370|8)\s*\(?\d{1,3}\)?[\s-]?\d{2,3}[\s-]?\d{3,4}', text)
                for ph in raw_phones:
                    cph = clean_phone_lt(ph)
                    if cph:
                        candidate_phones.append(cph)
                        
                if candidate_emails and len(candidate_phones) > 0:
                    break  # Found both, save requests
        except Exception:
            continue
            
    # Score emails and pick the single best B2B email
    best_email = ''
    best_score = -1
    for em in set(candidate_emails):
        score = score_email_b2b(em, base_domain)
        if score > best_score:
            best_score = score
            best_email = em
            
    best_phone = candidate_phones[0] if candidate_phones else ''
    return best_email, best_phone, base_domain


# -------------------------------------------------------------
# MASTER PIPELINE
# -------------------------------------------------------------

def run_master_pipeline():
    start_time = time.time()
    print("=" * 70)
    print("  HE THONG THU THAP & HOP NHAT NONG NGHIEP LITVA (LT_FARM_WEBD)")
    print("  Tuan thu nghiem ngat GEMINI.md - Rule 1, 2, 3, 5, 6, 10, 12")
    print("=" * 70)

    # Kiem tra che do xuat nhanh tu cache
    if '--export-only' in sys.argv and CACHE_FILE.exists():
        print(f"[*] Dang tai du lieu tu cache: {CACHE_FILE}")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            master_list = json.load(f)
        with_websites = [it for it in master_list if it.get('website')]
        with_email_test = [it for it in master_list if clean_email(it.get('email', ''))]
        print(f"[+] Da tai {len(master_list)} doanh nghiep tu cache (Co web: {len(with_websites)}, Co email: {len(with_email_test)})")
        export_and_sync(master_list, start_time)
        return

    # 1. Scrape Fermos ranking
    fermos_items = scrape_fermos_rankings()

    # 2. Scrape Firmavis directory
    firmavis_items = scrape_firmavis_directory()

    # 3. Concurrent fetch detail pages
    print("\n[3/4] Dang bóc tách thông tin chi tiết (Fermos & Firmavis)...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        fermos_items = list(ex.map(fetch_fermos_detail, fermos_items))
    print(f"[+] Da cap nhat chi tiet cho {len(fermos_items)} cty Fermos")

    with ThreadPoolExecutor(max_workers=10) as ex:
        firmavis_items = list(ex.map(fetch_firmavis_detail, firmavis_items))
    print(f"[+] Da cap nhat chi tiet cho {len(firmavis_items)} cty Firmavis")

    # 4. Deduplicate and Merge
    print("\n[4/4] Dang hop nhat, loc danh sach den va lam giau Website/Email B2B...")
    
    firmavis_by_code = {item['code']: item for item in firmavis_items if item.get('code')}
    firmavis_by_norm = {normalize_company_name(item['name']): item for item in firmavis_items if normalize_company_name(item['name'])}
    
    merged_dict = {}
    blacklist_count = 0

    # Process Fermos items first (Ranked Giants)
    for f in fermos_items:
        c_name = f['name']
        if is_blacklisted_company(c_name):
            blacklist_count += 1
            print(f"[-] Rule 12 Exclusion: {c_name}")
            continue

        code = f.get('code', '')
        nkey = normalize_company_name(c_name)
        
        m_item = None
        if code and code in firmavis_by_code:
            m_item = firmavis_by_code[code]
        elif nkey and nkey in firmavis_by_norm:
            m_item = firmavis_by_norm[nkey]

        master_key = code if code else ('NAME_' + nkey)

        website = m_item.get('website', '') if m_item else ''
        address = m_item.get('address', '') if m_item else ''
        location = m_item.get('location', '') if m_item else f.get('municipality', '')
        legal_form = m_item.get('legal_form', '') if m_item else ''
        sub_industry = m_item.get('sub_industry', '') if m_item else f.get('main_activity', '')
        employees = f.get('employees', '') or (m_item.get('employees', '') if m_item else '')

        entry = {
            'rank_fermos': f.get('rank', ''),
            'company_code': code or (m_item.get('code', '') if m_item else ''),
            'company_name': c_name,
            'legal_form': legal_form,
            'vat': f.get('vat', '') or (m_item.get('vat', '') if m_item else ''),
            'municipality': f.get('municipality', ''),
            'location': location,
            'address': address,
            'sub_industry': sub_industry,
            'employees': employees,
            'revenue_fermos': f.get('revenue', ''),
            'revenue_firmavis': m_item.get('revenue', '') if m_item else '',
            'net_profit': f.get('net_profit', ''),
            'taxes_paid': f.get('taxes', ''),
            'fin_year': f.get('fin_year', ''),
            'avg_wage': f.get('avg_wage', ''),
            'reg_status': f.get('reg_status', ''),
            'website': website,
            'phone': '',
            'email': '',
            'fermos_url': f.get('detail_url', ''),
            'firmavis_url': m_item.get('detail_url', '') if m_item else '',
            'source': 'fermos.lt + firmavis.com' if m_item else 'fermos.lt'
        }
        merged_dict[master_key] = entry

    # Process Firmavis items not yet merged
    for fv in firmavis_items:
        c_name = fv['name']
        if is_blacklisted_company(c_name):
            blacklist_count += 1
            print(f"[-] Rule 12 Exclusion: {c_name}")
            continue

        code = fv.get('code', '')
        nkey = normalize_company_name(c_name)
        master_key = code if code else ('NAME_' + nkey)

        if master_key in merged_dict:
            continue
        if nkey and ('NAME_' + nkey) in merged_dict:
            continue

        entry = {
            'rank_fermos': '',
            'company_code': code,
            'company_name': c_name,
            'legal_form': fv.get('legal_form', ''),
            'vat': fv.get('vat', ''),
            'municipality': '',
            'location': fv.get('location', ''),
            'address': fv.get('address', ''),
            'sub_industry': fv.get('sub_industry', ''),
            'employees': fv.get('employees', ''),
            'revenue_fermos': '',
            'revenue_firmavis': fv.get('revenue', ''),
            'net_profit': '',
            'taxes_paid': '',
            'fin_year': '',
            'avg_wage': '',
            'reg_status': '',
            'website': fv.get('website', ''),
            'phone': '',
            'email': '',
            'fermos_url': '',
            'firmavis_url': fv.get('detail_url', ''),
            'source': 'firmavis.com'
        }
        merged_dict[master_key] = entry

    master_list = list(merged_dict.values())
    print(f"[+] Tong so doanh nghiep duy nhat sau hop nhat: {len(master_list)}")
    print(f"[+] Da loai tru {blacklist_count} doanh nghiep khoi danh sach den (Rule 12)")

    # 5. Enrich Websites for Top Fermos companies without website
    need_web_discovery = [item for item in master_list if not item.get('website') and item.get('rank_fermos')]
    print(f"[*] Dang tim website bo sung cho {len(need_web_discovery)} doanh nghiep hang dau...")
    
    def discover_one(item):
        w = discover_website_duckduckgo(item['company_name'])
        if w:
            item['website'] = w
        return item
        
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(discover_one, need_web_discovery))

    # 6. Crawl B2B Emails & Phones from Websites
    with_websites = [item for item in master_list if item.get('website')]
    print(f"[*] Dang cao Email B2B & SDT cho {len(with_websites)} doanh nghiep co website...")

    def crawl_contacts_worker(item):
        em, ph, _ = crawl_website_contacts(item['website'])
        if em:
            item['email'] = em
        if ph:
            item['phone'] = ph
        return item

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(crawl_contacts_worker, with_websites))

    # Save checkpoint JSON
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(master_list, f, ensure_ascii=False, indent=2)
    print(f"[+] Da luu checkpoint tai: {CACHE_FILE}")

    export_and_sync(master_list, start_time)


def export_and_sync(master_list, start_time):
    # 7. Generate RAW CSV (LT_FARM_WEBD_0RAW.csv)
    print(f"\n[*] Dang xuat file thô hợp nhất: {RAW_CSV_PATH}")
    with open(RAW_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(RAW_COLUMNS)
        for idx, it in enumerate(master_list, 1):
            phone = it.get('phone', '')
            if phone:
                phone = clean_phone_lt(phone)
            email = clean_email(it.get('email', ''))
            writer.writerow([
                idx,
                it.get('rank_fermos', ''),
                it.get('company_code', ''),
                it.get('company_name', ''),
                it.get('legal_form', ''),
                it.get('vat', ''),
                it.get('municipality', ''),
                it.get('location', ''),
                it.get('address', ''),
                it.get('sub_industry', ''),
                it.get('employees', ''),
                it.get('revenue_fermos', ''),
                it.get('revenue_firmavis', ''),
                it.get('net_profit', ''),
                it.get('taxes_paid', ''),
                it.get('fin_year', ''),
                it.get('avg_wage', ''),
                it.get('reg_status', ''),
                it.get('website', ''),
                phone,
                email,
                it.get('fermos_url', ''),
                it.get('firmavis_url', ''),
                it.get('source', '')
            ])

    # 8. Generate Cold Mail 20-column CSV (LT_FARM_WEBD_2COL.csv)
    # BẮT BUỘC: Đẩy 100% doanh nghiệp có email lên đầu danh sách (Rule 3)
    with_email = []
    without_email = []

    for it in master_list:
        c_name = it.get('company_name', '')
        phone = it.get('phone', '')
        if phone:
            phone = clean_phone_lt(phone)
        email = clean_email(it.get('email', ''))
        
        # Determine best address
        addr = it.get('address', '')
        if not addr:
            loc = it.get('location', '') or it.get('municipality', '')
            addr = f"{loc}, Lithuania" if loc else "Lithuania"
            
        website = it.get('website', '')
        source_link = website or it.get('fermos_url', '') or it.get('firmavis_url', '')
        category = it.get('sub_industry', '') or 'Agriculture & Farming'

        row = {
            'Công ty': c_name,
            'Chức danh': 'Vadovas / Director',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': source_link,
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': addr,
            'Lương': it.get('avg_wage', ''),
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
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

    # 9. Generate ONLY_EMAILS_READY CSV
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

    # 10. Sync to archive and csdl_mlt
    for target_dir in [ARCHIVE_DIR, CSDL_DIR]:
        if target_dir.exists():
            for p in [RAW_CSV_PATH, COL2_CSV_PATH, READY_CSV_PATH]:
                dest = target_dir / p.name
                shutil.copy2(p, dest)
            print(f"[+] Da dong bo thanh cong sang: {target_dir}")

    elapsed = round(time.time() - start_time, 1)
    with_websites_cnt = sum(1 for it in master_list if it.get('website'))
    print("\n" + "=" * 70)
    print("  HOAN THANH QUA TRINH THU THAP & HOP NHAT!")
    print(f"  Tong thoi gian chay: {elapsed} giay")
    print(f"  Tong so DN hop nhat duy nhat: {len(master_list)}")
    print(f"  Tong so DN co Website: {with_websites_cnt}")
    print(f"  Tong so DN co Email B2B: {len(with_email)} (Duoc day len dau tu dong)")
    print(f"  Tep thô: {RAW_CSV_PATH.name}")
    print(f"  Tep ColdMail: {COL2_CSV_PATH.name}")
    print(f"  Tep chi email: {READY_CSV_PATH.name}")
    print("=" * 70)


if __name__ == '__main__':
    run_master_pipeline()
