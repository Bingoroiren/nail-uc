# -*- coding: utf-8 -*-
"""
BỘ CÀO & LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP NA UY QUA GULESIDER (JORDBRUK)
-----------------------------------------------------------------------------------
Nguồn: https://www.gulesider.no/jordbruk/bedrifter
Quy chuẩn áp dụng:
1. Bóc tách chi tiết từng thẻ công ty (/bedrift), nhấn nút hộp thư để lấy email trực tiếp.
2. Lưu đầy đủ Tag/Categories ngành, bộ lọc nghiêm ngặt giữ lại TRỒNG TRỌT & CHĂN NUÔI.
3. Loại bỏ 100% doanh nghiệp phi nông nghiệp:
   - Bảo tàng & di tích (Museum, samling, historisk...)
   - Trường học & giáo dục (Skole, undervisning, barnehage...)
   - Y tế & dịch vụ xã hội (Helse, omsorg, sykehus...)
   - Bất động sản, cho thuê nhà, lưu trú, cắm trại (Eiendom, boligutleie, camping...)
   - Cửa hàng đồ gỗ, thiết bị cabin cá nhân (Hyttesenter, byggevare...)
   - Danh sách đen vĩnh viễn (Scandi Standard, Biliarta, Daigre per GEMINI.md).
4. Đối chiếu thông minh (Smart Matching) với NO_FARM_WEBD_0RAW.csv qua Orgnr & Tên chuẩn hóa NFKD:
   - Làm giàu Email, Website, SĐT cho công ty đã có.
   - Thêm mới công ty trồng trọt/chăn nuôi chưa có vào danh sách.
5. Lưu tăng dần (Incremental Auto-Save) sau mỗi trang cào & hỗ trợ Resume qua cache JSON.
6. Xuất chuẩn tên file 17 ký tự:
   - NO_FARM_WEBD_0RAW.csv (UTF-8 with BOM)
   - NO_FARM_WEBD_2COL.csv (20 cột Cold Mail, đẩy 100% có email lên đầu, SĐT có nháy đơn ')
"""

import sys
import os
import re
import json
import time
import shutil
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd

# Cấu hình UTF-8 console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# Đường dẫn tệp đầu ra cố định 17 ký tự: [CC]_[IND4]_[SRC4]_[STG4].csv
OUT_RAW_CSV = ROOT_DIR / "NO_FARM_GULE_0RAW.csv"
OUT_2COL_CSV = ROOT_DIR / "NO_FARM_GULE_2COL.csv"
CSDL_2COL_CSV = ROOT_DIR / "csdl_mlt" / "NO_FARM_GULE_2COL.csv"
ARCHIVE_2COL_CSV = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_GULE_2COL.csv"
PROFF_RAW_CSV = ROOT_DIR / "NO_FARM_WEBD_0RAW.csv"
COMB_2COL_CSV = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
CACHE_JSON = ROOT_DIR / "crawlmail" / "cache_gulesider_farm.json"

COLUMNS_RAW = [
    'No.', 'Orgnr', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'NACE', 'Nguoi quan ly', 'Chuc danh',
    'Doanh thu', 'So nhan vien', 'Nam thanh lap', 'Proff URL'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Danh mục ngành nghề & từ khóa loại trừ
EXCLUDED_CATEGORIES = [
    'museum', 'samling', 'historisk', 'kultur', 'kunst', 'teater', 'attraksjon',
    'skole', 'undervisning', 'barnehage', 'opplæring', 'universitet',
    'helse', 'omsorg', 'sykehus', 'sykehjem', 'lege', 'terapi', 'sosial',
    'eiendom', 'bolig', 'utleie', 'hotell', 'overnatting', 'camping',
    'kirke', 'menighet', 'religiøs', 'advokat', 'regnskap', 'revisjon', 'finans',
    'hytteutstyr', 'byggevare', 'trelast', 'engroshandel'
]

EXCLUDED_NAMES = [
    'museum', 'samling', 'historisk', 'skole', 'barnehage', 'kirke', 'menighet',
    'stiftelse', 'eiendom', 'holding', 'hyttesenter', 'byggevare'
]

ALLOWED_PRIMARY = [
    # Chăn nuôi (Livestock / Husdyrhold)
    'husdyr', 'husdyrhold', 'husdyravl', 'storfe', 'melk', 'melkekyr', 'kjøttfe',
    'svin', 'svinehold', 'gris', 'utegris', 'smågris', 'sau', 'sauehold', 'geit',
    'fjørfe', 'kylling', 'høns', 'egg', 'kalkun', 'hestehold', 'stutteri', 'reindrift',
    'biavl', 'birøkt', 'kanin', 'slakteri', 'avlsdyr', 'dyreavl',
    # Trồng trọt (Crops / Horticulture / Farming)
    'jordbruk', 'blandet jordbruk', 'dyrking', 'korn', 'grønnsaker', 'potet', 'poteter',
    'bær', 'frukt', 'gartneri', 'planteskole', 'veksthus', 'blomsterdyrking',
    'fôrvekster', 'gras', 'gård', 'gardsbruk', 'landbrukstjeneste',
    'gårdsbestyrelse', 'landbruksentreprenør', 'produsenter'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

LEGAL_FORMS = [
    r'\baksjeselskap\b', r'\bas\b', r'\bans\b', r'\benk\b', r'\bda\b',
    r'\bsa\b', r'\bba\b', r'\bnuf\b', r'\bks\b', r'\bhf\b'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def normalize_comp_name(name):
    if not name:
        return ""
    n = re.sub(r'\(.*?\)|\[.*?\]', '', str(name))
    n = unicodedata.normalize('NFKD', n).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    for lf in LEGAL_FORMS:
        n = re.sub(lf, ' ', n)
    n = re.sub(r'[^a-z0-9]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def is_valid_agri_company(name, categories, desc=""):
    name_l = name.lower()
    cats_str = " | ".join(categories).lower()
    desc_l = desc.lower()
    
    # 1. Hard blacklist
    if is_blacklisted_company(name):
        return False, "Doanh nghiệp trong danh sách đen GEMINI.md"
        
    # 2. Loại trừ theo từ khóa tên
    for ex in EXCLUDED_NAMES:
        if ex in name_l:
            return False, f"Tên chứa từ loại trừ: '{ex}'"
            
    # 3. Loại trừ theo ngành nghề phi nông nghiệp
    for ex in EXCLUDED_CATEGORIES:
        if any(ex in c.lower() for c in categories):
            has_primary = any(p in cats_str for p in ALLOWED_PRIMARY) or any(p in desc_l for p in ALLOWED_PRIMARY)
            if not has_primary:
                return False, f"Ngành nghề loại trừ: '{ex}'"
                
    # 4. Phải có ít nhất 1 dấu hiệu trồng trọt hoặc chăn nuôi
    has_agri = any(ag in cats_str for ag in ALLOWED_PRIMARY) or \
               any(ag in desc_l for ag in ALLOWED_PRIMARY) or \
               any(ag in name_l for ag in ['landbruk', 'gard', 'gård', 'utegris', 'kylling', 'egg', 'storfe', 'sau', 'melk'])
               
    if not has_agri:
        return False, f"Không có hoạt động trồng trọt hoặc chăn nuôi: '{cats_str}'"
        
    return True, "Hợp lệ"

def clean_phone_no(raw_phone):
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ''
    s = str(raw_phone).strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('0047'):
        digits = digits[4:]
    elif digits.startswith('47') and len(digits) >= 10:
        digits = digits[2:]
    
    if len(digits) == 8:
        return f"'+47{digits}"
    return f"'+{digits}"

def clean_email(email_raw):
    if not email_raw or str(email_raw).strip() in ['', 'None', 'nan']:
        return ""
    em = str(email_raw).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    if any(k in em for k in ['sentry', 'wix', 'wordpress', 'no-reply', 'donotreply', 'privacy', 'gdpr']):
        return ""
    return em

def score_email_b2b(email, website=''):
    if not email or '@' not in email:
        return -999
    em = email.lower().strip()
    score = 0
    dom = em.split('@')[-1]
    
    if website and dom in website.lower():
        score += 50
        
    if any(em.startswith(k) for k in ['praca@', 'kariera@', 'hr@', 'personal@', 'jobs@', 'recruitment@', 'rekruttering@', 'career@', 'jobb@']):
        score += 50
    elif any(em.startswith(k) for k in ['daglig.leder@', 'leder@', 'ceo@', 'director@', 'manager@', 'drift@', 'bonde@', 'salg@', 'sales@']):
        score += 45
    elif any(em.startswith(k) for k in ['post@', 'kontakt@', 'contact@', 'office@', 'info@', 'kontor@', 'postboks@', 'farm@', 'gard@']):
        score += 40
    elif '.' in em.split('@')[0]:
        score += 25
    elif dom in ['gmail.com', 'yahoo.com', 'hotmail.com', 'online.no', 'outlook.com']:
        score += 10
    else:
        score += 15
    return score

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email
    except Exception:
        return ""

def crawl_website_for_email(url):
    if not url or not url.startswith('http'):
        return ""
    found_emails = set()
    domain = urllib.parse.urlparse(url).netloc.lower()
    
    subpaths = [
        "", "/kontakt", "/kontakt-oss", "/om-oss", "/kontakt.html",
        "/om-oss.html", "/contact", "/about", "/om", "/ansatte"
    ]
    
    for sub in subpaths:
        target_url = urllib.parse.urljoin(url, sub)
        try:
            r = requests.get(target_url, timeout=5, impersonate="chrome124", allow_redirects=True)
            if r.status_code == 200:
                html = r.text
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                    em = decode_cloudflare_email(cf)
                    if em:
                        c_em = clean_email(em)
                        if c_em: found_emails.add(c_em)
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    if a['href'].startswith('mailto:'):
                        em = a['href'].replace('mailto:', '').split('?')[0].strip()
                        c_em = clean_email(em)
                        if c_em: found_emails.add(c_em)
                for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html):
                    c_em = clean_email(em)
                    if c_em: found_emails.add(c_em)
            if len(found_emails) >= 5:
                break
        except Exception:
            continue
            
    if not found_emails:
        return ""
    scored = sorted([(score_email_b2b(e, domain), e) for e in found_emails], key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else ""

def parse_gule_company(html, rel_url):
    name = ""
    orgnr = ""
    email = ""
    web = ""
    phone = ""
    street = ""
    zipcode = ""
    city = ""
    categories = []
    
    # 1. Company Name
    comp_matches = re.findall(r'\\"companyName\\":\s*\\"([^\\"]+)\\"', html) + re.findall(r'"companyName":\s*"([^"]+)"', html)
    real_names = [c for c in comp_matches if c != 'Ditt firmanavn her' and not c.startswith('Robin')]
    if real_names: 
        name = real_names[0]
    
    # Fallback 1: Trích xuất từ thẻ <title> hoặc <h1>
    if not name:
        title_m = re.search(r'<title>([^<,|]+)', html)
        if title_m and 'gulesider' not in title_m.group(1).lower() and 'just a moment' not in title_m.group(1).lower():
            name = title_m.group(1).strip()

    # Fallback 2: Trích xuất từ URL slug và giải mã unquote_plus
    if not name and rel_url:
        slug = rel_url.strip('/').split('/')[0]
        unquoted_slug = urllib.parse.unquote(urllib.parse.unquote_plus(slug))
        name = ' '.join(unquoted_slug.split('+')).title()
        
    # Luôn làm sạch mã hóa URL cho tên
    if name and '%' in name:
        name = urllib.parse.unquote(urllib.parse.unquote_plus(name))
    
    # 2. Orgnr (9 digits)
    org_m = re.findall(r'\\"(?:orgNr|orgnr)\\":\s*\\"(\d{9})\\"', html) + re.findall(r'"(?:orgNr|orgnr)":\s*"(\d{9})"', html)
    if org_m: orgnr = org_m[0]
    
    # 3. Email (B2B mailbox on card / detail)
    email_m = re.findall(r'\\"email\\":\s*\\"([^\\"]+)\\"', html) + re.findall(r'"email":\s*"([^"]+)"', html)
    real_emails = [e for e in email_m if '@' in e and not any(x in e.lower() for x in ['eniro', 'sentry', 'example', 'domain.com', 'dittfirma'])]
    if real_emails:
        email = real_emails[0]
    else:
        raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html)
        clean = [e for e in raw_emails if not any(x in e.lower() for x in ['.png', '.jpg', 'eniro.com', 'sentry', 'wix', 'cloudflare'])]
        if clean: email = clean[0]
        
    # 4. Website
    web_m = re.findall(r'\\"website\\":\s*\\"([^\\"]+)\\"', html) + re.findall(r'"website":\s*"([^"]+)"', html)
    real_webs = [w for w in web_m if w.startswith('http') and not any(x in w.lower() for x in ['gulesider', 'eniro', 'teamrobin'])]
    if real_webs: web = real_webs[0]
    
    # 5. Phone
    phone_m = re.findall(r'\\"number\\":\s*\\"([^\\"]+)\\"', html) + re.findall(r'"number":\s*"([^"]+)"', html)
    real_phones = [p for p in phone_m if any(c.isdigit() for c in p)]
    if real_phones: phone = real_phones[0]
    
    # 6. Address
    postal_addr_m = re.search(r'\\"@type\\":\s*\\"PostalAddress\\",\\"streetAddress\\":\s*\\"([^\\"]+)\\",\\"postalCode\\":\s*\\"([^\\"]+)\\",\\"addressLocality\\":\s*\\"([^\\"]+)\\"', html)
    if postal_addr_m:
        street = postal_addr_m.group(1)
        zipcode = postal_addr_m.group(2)
        city = postal_addr_m.group(3)
    else:
        s_m = re.findall(r'\\"streetAddress\\":\s*\\"([^\\"]+)\\"', html)
        if s_m: street = s_m[0]
        z_m = re.findall(r'\\"postalCode\\":\s*\\"([^\\"]+)\\"', html)
        if z_m:
            filtered_z = [z for z in z_m if z != 'Postnummer']
            if filtered_z: zipcode = filtered_z[0]
        c_m = re.findall(r'\\"addressLocality\\":\s*\\"([^\\"]+)\\"', html)
        if c_m: city = c_m[0]
        
    # 7. Categories / Tags
    cat_m = re.findall(r'\\"categories\\":\s*(\[[^\]]+\])', html)
    if cat_m:
        try:
            raw = cat_m[0].replace('\\"', '"')
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                categories = [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
            
    return {
        'name': name.strip(),
        'orgnr': orgnr.strip(),
        'email': clean_email(email),
        'web': web.strip(),
        'phone': phone.strip(),
        'street': street.strip(),
        'zipcode': zipcode.strip(),
        'city': city.strip(),
        'categories': categories,
        'url': f"https://www.gulesider.no{rel_url}" if rel_url.startswith('/') else rel_url
    }

def export_cold_mail_2col(records):
    """Xuất file chuẩn Cold Mail 20 cột, đẩy 100% doanh nghiệp có Email lên đầu danh sách"""
    with_email = []
    without_email = []
    
    for r in records:
        email = clean_email(r.get('Email', ''))
        phone = clean_phone_no(r.get('SDT', ''))
        comp_name = r.get('Cong ty') or r.get('Ten phap ly', '')
        contact = r.get('Nguoi quan ly', '')
        role = r.get('Chuc danh', '')
        addr = r.get('Dia chi', '')
        zip_code = r.get('Ma buu dien', '')
        city = r.get('Thanh pho', '')
        full_addr = ', '.join([p for p in [addr, f"{zip_code} {city}".strip()] if p])
        tag_main = r.get('Tag_Chinh') or 'Jordbruk'
        
        row_dict = {
            'No.': '',
            'Công ty': comp_name,
            'Chức danh': role,
            'Người liên hệ': contact,
            'SĐT': phone,
            'Liên Hệ': '',
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': tag_main
        }
        
        if email and '@' in email:
            with_email.append(row_dict)
        else:
            without_email.append(row_dict)
            
    final_rows = with_email + without_email
    for i, row in enumerate(final_rows, start=1):
        row['No.'] = str(i)
        
    df_out = pd.DataFrame(final_rows, columns=COLUMNS_20)
    
    # 1. Root CSV
    df_out.to_csv(OUT_2COL_CSV, index=False, encoding='utf-8-sig')
    # 2. CSDL mlt
    CSDL_2COL_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(CSDL_2COL_CSV, index=False, encoding='utf-8-sig')
    # 3. Archive
    ARCHIVE_2COL_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(ARCHIVE_2COL_CSV, index=False, encoding='utf-8-sig')

    # 4. Tạo tệp gộp NO_FARM_COMB_2COL.csv (Gulesider + Proff) đẩy 100% email lên đầu
    try:
        proff_2col_path = ROOT_DIR / "NO_FARM_WEBD_2COL.csv"
        all_comb = [dict(r) for r in final_rows]
        seen_names = {normalize_comp_name(r.get('Công ty', '')): True for r in final_rows if r.get('Công ty')}
        
        if proff_2col_path.exists():
            df_p2 = pd.read_csv(proff_2col_path, encoding='utf-8-sig', dtype=str).fillna('')
            for _, pr in df_p2.iterrows():
                pr_dict = pr.to_dict()
                p_name = normalize_comp_name(pr_dict.get('Công ty', ''))
                if p_name and p_name not in seen_names:
                    seen_names[p_name] = True
                    all_comb.append(pr_dict)
                    
        comb_with = [r for r in all_comb if clean_email(r.get('Email', '')) and '@' in r.get('Email', '')]
        comb_without = [r for r in all_comb if not clean_email(r.get('Email', '')) or '@' not in r.get('Email', '')]
        comb_final = comb_with + comb_without
        for i, row in enumerate(comb_final, start=1):
            row['No.'] = str(i)
        pd.DataFrame(comb_final, columns=COLUMNS_20).to_csv(COMB_2COL_CSV, index=False, encoding='utf-8-sig')
    except Exception:
        pass

def load_cache():
    if CACHE_JSON.exists():
        try:
            with open(CACHE_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_JSON, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def warm_up_session():
    """Khởi tạo session safari17_0 và lấy cookie Cloudflare từ trang chủ Gulesider"""
    s = requests.Session(impersonate="safari17_0")
    h = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'nb-NO,no;q=0.9,en;q=0.8',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        r = s.get('https://www.gulesider.no/jordbruk/bedrifter', headers=h, timeout=15)
        if r.status_code == 200:
            return s
    except Exception as e:
        print(f"[!] Lỗi kết nối khởi tạo session: {e}")
    return s

def main():
    parser = argparse.ArgumentParser(description="Bộ làm giàu nông nghiệp Na Uy qua Gulesider (Jordbruk)")
    parser.add_argument('--start-page', type=int, default=1, help="Trang bắt đầu (mặc định 1)")
    parser.add_argument('--max-pages', type=int, default=48, help="Số trang tối đa (mặc định 48)")
    parser.add_argument('--concurrency', type=int, default=4, help="Số luồng chi tiết đồng thời (mặc định 4)")
    parser.add_argument('--enrich-web', action='store_true', default=True, help="Quét website bóc tách thêm email")
    args = parser.parse_args()

    print("=" * 80)
    print(" BỘ CÀO & LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP NA UY (GULESIDER)")
    print(" NGUỒN: https://www.gulesider.no/jordbruk/bedrifter")
    print(f" CẤU HÌNH: Trang {args.start_page} -> {args.max_pages} | Luồng: {args.concurrency}")
    print("=" * 80)

    # 1. Tải cache
    cache = load_cache()
    print(f"[+] Đã nạp cache lịch sử: {len(cache):,} thẻ công ty.")

    # 2. Nạp dữ liệu hiện tại từ NO_FARM_GULE_0RAW.csv để tiếp tục
    saved_records = []
    orgnr_to_idx = {}
    name_to_idx = {}

    if OUT_RAW_CSV.exists():
        try:
            df_old = pd.read_csv(OUT_RAW_CSV, encoding='utf-8-sig', dtype=str).fillna('')
            for idx, r in df_old.iterrows():
                rec = r.to_dict()
                saved_records.append(rec)
                o = rec.get('Orgnr', '').strip()
                if o and len(o) == 9:
                    orgnr_to_idx[o] = len(saved_records) - 1
                c_name = normalize_comp_name(rec.get('Cong ty', ''))
                if c_name:
                    name_to_idx[c_name] = len(saved_records) - 1
            print(f"[+] Nạp thành công {len(saved_records):,} bản ghi từ {OUT_RAW_CSV.name}.")
        except Exception as e:
            print(f"[!] Lỗi đọc {OUT_RAW_CSV.name}: {e}")

    # Nạp dữ liệu đối chiếu từ Proff.no (NO_FARM_WEBD_0RAW.csv) ở chế độ READ-ONLY
    proff_lookup = {}
    if PROFF_RAW_CSV.exists():
        try:
            df_proff = pd.read_csv(PROFF_RAW_CSV, encoding='utf-8-sig', dtype=str).fillna('')
            for _, r in df_proff.iterrows():
                p_rec = r.to_dict()
                p_org = str(p_rec.get('Orgnr', '')).strip()
                if p_org and len(p_org) == 9:
                    proff_lookup[p_org] = p_rec
                p_name = normalize_comp_name(p_rec.get('Cong ty', ''))
                if p_name:
                    proff_lookup[p_name] = p_rec
            print(f"[*] Nạp đối chiếu {len(df_proff):,} bản ghi Proff từ {PROFF_RAW_CSV.name}.")
        except Exception as e:
            print(f"[!] Không thể nạp đối chiếu Proff: {e}")

    # 3. Khởi tạo session Gulesider
    print("[*] Đang khởi tạo phiên kết nối vượt Cloudflare...")
    main_session = warm_up_session()

    headers_search = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'nb-NO,no;q=0.9,en;q=0.8',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Referer': 'https://www.gulesider.no/jordbruk/bedrifter',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }

    total_enriched = 0
    total_added = 0
    total_excluded = 0

    for page_num in range(args.start_page, args.max_pages + 1):
        page_url = 'https://www.gulesider.no/jordbruk/bedrifter' if page_num == 1 else f'https://www.gulesider.no/jordbruk/bedrifter/{page_num}'
        print(f"\n--- [TRANG {page_num}/{args.max_pages}] Đang tải danh sách công ty: {page_url} ---")
        
        try:
            r = main_session.get(page_url, headers=headers_search, timeout=15)
            if r.status_code == 403:
                print("[!] Bị chặn 403, đang tạo phiên kết nối mới...")
                main_session = warm_up_session()
                r = main_session.get(page_url, headers=headers_search, timeout=15)
        except Exception as e:
            print(f"[!] Lỗi tải trang {page_num}: {e}")
            time.sleep(2)
            continue

        if r.status_code != 200:
            print(f"[!] Không thể tải trang {page_num} (Status: {r.status_code}).")
            time.sleep(2)
            continue

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Bóc tách các thẻ công ty trên trang và description của từng thẻ
        card_urls = []
        card_desc_map = {}
        
        for h2 in soup.find_all('h2'):
            c_name = h2.get_text(strip=True)
            p = h2.parent
            while p and len(p.find_all('h2')) <= 1 and p.name not in ['body', 'html']:
                parent = p
                p = p.parent
            desc_text = ' '.join(parent.stripped_strings) if parent else ''
            
            # Tìm link /bedrift trong card này
            a_link = parent.find('a', href=re.compile(r'^/[^/]+/\d+/bedrift')) if parent else None
            if not a_link:
                a_link = h2.find_parent('a', href=re.compile(r'^/[^/]+/\d+/bedrift'))
            if a_link:
                href = a_link['href']
                if href not in card_urls:
                    card_urls.append(href)
                    card_desc_map[href] = desc_text
                    
        # Fallback: Quét toàn bộ link /bedrift nếu thẻ phức tạp
        for a in soup.find_all('a', href=re.compile(r'^/[^/]+/\d+/bedrift')):
            href = a['href']
            if href not in card_urls:
                card_urls.append(href)
                card_desc_map[href] = card_desc_map.get(href, '')

        print(f"[*] Nhận diện {len(card_urls)} doanh nghiệp trên trang {page_num}.")
        if not card_urls:
            print("[*] Không còn công ty nào trên trang này. Dừng cào.")
            break

        # Tải chi tiết các công ty chưa có trong cache
        to_fetch = [u for u in card_urls if u not in cache]
        if to_fetch:
            print(f"[*] Đang tải chi tiết {len(to_fetch)} công ty mới...")
            
            def fetch_detail_worker(rel_u):
                s = requests.Session(impersonate="safari17_0")
                s.cookies.update(main_session.cookies)
                f_url = f"https://www.gulesider.no{rel_u}"
                try:
                    res = s.get(f_url, headers=headers_search, timeout=12)
                    if res.status_code == 200:
                        parsed = parse_gule_company(res.text, rel_u)
                        parsed['desc'] = card_desc_map.get(rel_u, '')
                        return rel_u, parsed
                except Exception:
                    pass
                return rel_u, None

            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                future_map = {executor.submit(fetch_detail_worker, u): u for u in to_fetch}
                for f in as_completed(future_map):
                    rel_u, data = f.result()
                    if data:
                        cache[rel_u] = data

            save_cache(cache)

        # Xử lý & Phân loại từng công ty
        page_enriched = 0
        page_added = 0
        page_excluded = 0

        for rel_u in card_urls:
            c_info = cache.get(rel_u)
            if not c_info:
                continue

            name = c_info.get('name', '')
            orgnr = c_info.get('orgnr', '')
            email = clean_email(c_info.get('email', ''))
            web = c_info.get('web', '')
            phone = clean_phone_no(c_info.get('phone', ''))
            street = c_info.get('street', '')
            zipcode = c_info.get('zipcode', '')
            city = c_info.get('city', '')
            cats = c_info.get('categories', [])
            desc = c_info.get('desc', '') or card_desc_map.get(rel_u, '')

            # 1. BỘ LỌC NGHIÊM NGẶT (TRỒNG TRỌT & CHĂN NUÔI)
            is_valid, reason = is_valid_agri_company(name, cats, desc)
            if not is_valid:
                page_excluded += 1
                total_excluded += 1
                continue

            # 2. Nếu có web mà chưa có mail -> Quét website
            if not email and web and args.enrich_web:
                web_em = crawl_website_for_email(web)
                if web_em:
                    email = web_em
                    c_info['email'] = email

            tag_main = cats[0] if cats else 'Jordbruk'
            all_tags_str = ' | '.join(cats) if cats else 'Jordbruk'

            # 3. SO KHỚP VỚI CƠ SỞ DỮ LIỆU HIỆN CÓ
            target_idx = None
            if orgnr and orgnr in orgnr_to_idx:
                target_idx = orgnr_to_idx[orgnr]
            else:
                norm_n = normalize_comp_name(name)
                if norm_n and norm_n in name_to_idx:
                    target_idx = name_to_idx[norm_n]

            if target_idx is not None:
                # LÀM GIÀU BẢN GHI ĐÃ CÓ
                old_rec = saved_records[target_idx]
                updated = False
                
                # Bổ sung email nếu cũ trống hoặc điểm cao hơn
                if email and (not old_rec.get('Email') or old_rec.get('Email') in ['', 'None', 'nan']):
                    old_rec['Email'] = email
                    updated = True
                # Bổ sung website nếu cũ trống
                if web and (not old_rec.get('Website') or old_rec.get('Website') in ['', 'None', 'nan']):
                    old_rec['Website'] = web
                    updated = True
                # Bổ sung SĐT nếu cũ trống
                if phone and (not old_rec.get('SDT') or old_rec.get('SDT') in ['', 'None', 'nan']):
                    old_rec['SDT'] = phone
                    updated = True
                # Bổ sung địa chỉ nếu cũ trống
                if street and not old_rec.get('Dia chi'):
                    old_rec['Dia chi'] = street
                    updated = True
                if zipcode and not old_rec.get('Ma buu dien'):
                    old_rec['Ma buu dien'] = zipcode
                    updated = True
                if city and not old_rec.get('Thanh pho'):
                    old_rec['Thanh pho'] = city
                    updated = True
                # Bổ sung Tags
                existing_tags = old_rec.get('All_Tags', '')
                for ct in cats:
                    if ct not in existing_tags:
                        existing_tags = f"{existing_tags} | {ct}".strip(' |')
                        updated = True
                old_rec['All_Tags'] = existing_tags

                if updated:
                    page_enriched += 1
                    total_enriched += 1
                    status_em = f" [MAIL: {email}]" if email else ""
                    print(f"  [LÀM GIÀU] {name[:30]:<30} | Orgnr: {orgnr or 'Khớp tên':<10}{status_em}")

            else:
                # THÊM MỚI BẢN GHI ĐẠT CHUẨN
                proff_match = proff_lookup.get(orgnr) or proff_lookup.get(normalize_comp_name(name))
                leader = proff_match.get('Nguoi quan ly', '') if proff_match else ''
                role = proff_match.get('Chuc danh', '') if proff_match else ''
                rev = proff_match.get('Doanh thu', '') if proff_match else ''
                emp = proff_match.get('So nhan vien', '') if proff_match else ''
                found_yr = proff_match.get('Nam thanh lap', '') if proff_match else ''
                nace = proff_match.get('NACE', '01.1 / 01.4 Gulesider Jordbruk') if proff_match else '01.1 / 01.4 Gulesider Jordbruk'
                county = proff_match.get('Khu vuc', '') if proff_match else ''

                new_no = str(len(saved_records) + 1)
                new_rec = {
                    'No.': new_no,
                    'Orgnr': orgnr,
                    'Cong ty': name,
                    'Ten phap ly': name,
                    'SDT': phone,
                    'Email': email,
                    'Website': web,
                    'Dia chi': street,
                    'Ma buu dien': zipcode,
                    'Khu vuc': county,
                    'Thanh pho': city,
                    'Tag_Chinh': tag_main,
                    'All_Tags': all_tags_str,
                    'NACE': nace,
                    'Nguoi quan ly': leader,
                    'Chuc danh': role,
                    'Doanh thu': rev,
                    'So nhan vien': emp,
                    'Nam thanh lap': found_yr,
                    'Proff URL': c_info.get('url', '')
                }
                saved_records.append(new_rec)
                idx = len(saved_records) - 1
                if orgnr:
                    orgnr_to_idx[orgnr] = idx
                norm_n = normalize_comp_name(name)
                if norm_n:
                    name_to_idx[norm_n] = idx

                page_added += 1
                total_added += 1
                status_em = f" [MAIL: {email}]" if email else ""
                print(f"  [THÊM MỚI] {name[:30]:<30} | Tag: {tag_main[:15]:<15}{status_em}")

        print(f"[+] Trang {page_num}: Làm giàu {page_enriched} cty, Thêm mới {page_added} cty, Loại {page_excluded} phi nông nghiệp.")

        # LƯU TĂNG DẦN (INCREMENTAL SAVE)
        df_raw = pd.DataFrame(saved_records, columns=COLUMNS_RAW)
        df_raw.to_csv(OUT_RAW_CSV, index=False, encoding='utf-8-sig')
        export_cold_mail_2col(saved_records)

        time.sleep(1)

    print("\n" + "=" * 80)
    print(" HOÀN TẤT LÀM GIÀU NÔNG NGHIỆP NA UY QUA GULESIDER!")
    print(f" Tổng số doanh nghiệp trong danh mục: {len(saved_records):,}")
    print(f" Số doanh nghiệp được làm giàu thêm thông tin: {total_enriched:,}")
    print(f" Số doanh nghiệp trồng trọt/chăn nuôi mới bổ sung: {total_added:,}")
    print(f" Số doanh nghiệp phi nông nghiệp bị loại bỏ: {total_excluded:,}")
    with_em = len([r for r in saved_records if clean_email(r.get('Email'))])
    print(f" TỔNG DOANH NGHIỆP CÓ EMAIL: {with_em:,}")
    print(f" File RAW 17 ký tự: {OUT_RAW_CSV.name}")
    print(f" File Cold Mail 20 cột (Đã đẩy 100% email lên đầu): {OUT_2COL_CSV.name}")
    print("=" * 80)

if __name__ == '__main__':
    main()
