# -*- coding: utf-8 -*-
"""
GOOGLE MAPS & B2B EMAIL DATA ENRICHMENT
Target: (xong 10_15) SK_AUTO_SLVD - CleanData.csv (Slovakia Automotive / Manufacturing)

Quy trình:
1. Nạp danh sách doanh nghiệp CHƯA CÓ EMAIL (1,374 công ty) từ (xong 10_15) SK_AUTO_SLVD - CleanData.csv.
2. Tra cứu Google Maps Slovakia (hl=sk, headless=False trực quan) bằng Tên Công Ty + Thành phố / Địa chỉ.
3. So khớp tên nghiêm ngặt (NFKD khử dấu Slovak, loại bỏ legal forms s.r.o., a.s...).
4. Bóc tách Website chính thức, Địa chỉ nhà máy, và SĐT chuẩn ('+421...).
5. Quét website tìm Email B2B đa tầng (ưu tiên thẻ <a>, subpages liên hệ bản địa, decode Cloudflare, regex).
6. Chấm điểm Heuristic B2B (Tuyển dụng +50, Lãnh đạo +45, Liên hệ +40, Domain +50), chọn 1 email giá trị nhất.
7. Cập nhật 'Check gửi' = 'OK' ngay khi tìm thấy email hợp lệ.
8. Lưu tăng dần (Incremental Checkpoint) mỗi 5 công ty vào JSON cache và CSV (100% email lên đầu tệp).
9. Đồng bộ song song ra tệp chuyên dụng SK_AUTO_SLVD_READY_OK.csv.
"""

import sys
import os
import re
import json
import time
import shutil
import asyncio
import argparse
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Đảm bảo UTF-8 cho Windows Console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV = ROOT_DIR / "(xong 10_15) SK_AUTO_SLVD - CleanData.csv"
BACKUP_CSV = ROOT_DIR / "(xong 10_15) SK_AUTO_SLVD - CleanData_enrich_backup.csv"
OUT_READY_CSV = ROOT_DIR / "SK_AUTO_SLVD_READY_OK.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto_cleandata.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "sk_auto_cleandata_profile"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    'azet.sk', 'zlatestranky.sk', 'finstat.sk', 'orsr.sk', 'zoznam.sk', 'firmy.sk',
    'registerpartnerov.sk', 'profesia.sk', 'kariera.zoznam.sk', 'aktuality.sk',
    'sme.sk', 'pravda.sk', 'hnonline.sk', 'topky.sk', 'cas.sk', 'webnoviny.sk',
    'wikipedia.org', 'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'wix.com',
    'wordpress.com', 'tet.lv', 'maptiler.com', 'openstreetmap.org', 'schema.org'
]

BLACKLIST_EMAIL_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'sentry.io', 'wixpress.com', 'wix.com',
    'wordpress.com', 'maptiler.com', 'schema.org'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

JUNK_EMAIL_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@',
    'leaflet', 'es-module-shims', 'markercluster'
]

SK_CITIES = [
    "Bratislava", "Košice", "Kosice", "Prešov", "Presov", "Žilina", "Zilina",
    "Nitra", "Banská Bystrica", "Banska Bystrica", "Trnava", "Martin",
    "Trenčín", "Trencin", "Poprad", "Prievidza", "Zvolen", "Považská Bystrica",
    "Povazska Bystrica", "Nové Zámky", "Nove Zamky", "Michalovce", "Spišská Nová Ves",
    "Spisska Nova Ves", "Komárno", "Komarno", "Levice", "Humenné", "Humenne",
    "Bardejov", "Liptovský Mikuláš", "Liptovsky Mikulas", "Piešťany", "Piestany",
    "Ružomberok", "Ruzomberok", "Topoľčany", "Topolcany", "Lučenec", "Lucenec",
    "Čadca", "Cadca", "Dubnica nad Váhom", "Dubnica nad Vahom", "Rimavská Sobota",
    "Rimavska Sobota", "Partizánske", "Partizanske", "Šaľa", "Sala", "Dunajská Streda",
    "Dunajska Streda", "Trebišov", "Trebisov", "Vranov nad Topľou", "Vranov nad Toplou",
    "Hlohovec", "Brezno", "Senica", "Nové Mesto nad Váhom", "Nove Mesto nad Vahom",
    "Senec", "Snina", "Rožňava", "Roznava", "Žiar nad Hronom", "Ziar nad Hronom",
    "Dolný Kubín", "Dolny Kubin", "Bánovce nad Bebravou", "Banovce nad Bebravou",
    "Púchov", "Puchov", "Malacky", "Handlová", "Handlova", "Kežmarok", "Kezmarok",
    "Stará Ľubovňa", "Stara Lubovna", "Sereď", "Sered", "Kysucké Nové Mesto",
    "Kysucke Nove Mesto", "Galanta", "Skalica", "Levoča", "Levoca", "Detva",
    "Šamorín", "Samorin", "Sabinov", "Veľký Krtíš", "Velky Krtis", "Stropkov",
    "Bytča", "Bytca", "Myjava", "Zlaté Moravce", "Zlate Moravce", "Svidník", "Svidnik",
    "Nová Dubnica", "Nova Dubnica", "Štúrovo", "Sturovo", "Banská Štiavnica", "Banska Stiavnica",
    "Tornaľa", "Tornala", "Mostová", "Mostova"
]

SK_SUBPATHS = [
    "/kontakt", "/kontakty", "/kontakt.html", "/kontakty.html", "/kontakt.php",
    "/o-nas", "/o-spolocnosti", "/o-nas.html",
    "/kariera", "/praca", "/volne-pracovne-miesta", "/kariera.html", "/praca.html",
    "/contact", "/contact-us", "/about-us", "/about",
    "/impressum"
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_sk(phone_str):
    if not phone_str or str(phone_str).strip() == '' or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip().lstrip("'")
    p = re.sub(r'^(?:Tel|T\.|Tālr\.|Mobil)[:\s]*', '', p, flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('421'):
        return f"'+{digits}"
    elif digits.startswith('0'):
        return f"'+421{digits[1:]}"
    elif len(digits) == 9:
        return f"'+421{digits}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"

def strip_accents(s):
    if not s:
        return ""
    n = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in n if not unicodedata.combining(c))

def normalize_text_core(text):
    if not text:
        return ""
    t = re.sub(r'["\'„“”«»]', '', str(text)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    
    legal_forms = [
        r'\bspoločnosť s ručením obmedzeným\b', r'\bspolocnost s rucenim obmedzenym\b',
        r'\bakciová spoločnosť\b', r'\bakciova spolocnost\b',
        r'\bspol\.\s*s\s*r\.?\s*o\.?\b', r'\bs\.?\s*r\.?\s*o\.?\b', r'\bsro\b',
        r'\ba\.?\s*s\.?\b', r'\bas\b',
        r'\bk\.?\s*s\.?\b', r'\bv\.?\s*o\.?\s*s\.?\b',
        r'\bdružstvo\b', r'\bdruzstvo\b',
        r'\bkomanditná spoločnosť\b', r'\bverejná obchodná spoločnosť\b',
        r'\bgmbh\b', r'\bltd\b', r'\binc\b', r'\bcorp\b'
    ]
    for lf in legal_forms:
        t = re.sub(lf, '', t, flags=re.I).strip()
        
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return strip_accents(t)

def clean_company_name_for_search(name):
    t = re.sub(r'["\'„“”«»]', '', str(name)).strip()
    legal_forms = [r'\bspol\.\s*s\s*r\.?\s*o\.?\b', r'\bs\.?\s*r\.?\s*o\.?\b', r'\ba\.?\s*s\.?\b', r'\bk\.?\s*s\.?\b', r'\bv\.?\s*o\.?\s*s\.?\b']
    for lf in legal_forms:
        t = re.sub(lf, '', t, flags=re.I).strip(' ,.-')
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return t

def extract_city_sk(comp_name, addr):
    c_name = str(comp_name or "")
    for city in SK_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", c_name, re.IGNORECASE):
            return city
            
    if addr and isinstance(addr, str):
        # Mã bưu chính 5 số: 98201 Tornaľa
        m_post = re.search(r"\b\d{3}\s?\d{2}\s+([A-Za-zÁ-ž]+)", addr)
        if m_post:
            c = m_post.group(1).strip()
            if c:
                return c
        for city in SK_CITIES:
            if re.search(rf"\b{re.escape(city)}\b", addr, re.IGNORECASE):
                return city
    return ""

def is_valid_name_match(query_name, candidate_name):
    if not query_name or not candidate_name:
        return False, "EMPTY"
        
    q = normalize_text_core(query_name)
    c = normalize_text_core(candidate_name)
    
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    parts = [strip_accents(p.strip()) for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    for p in parts:
        pn = normalize_text_core(p)
        if pn and (pn == q or (len(q) >= 4 and pn in q) or (len(pn) >= 4 and q in pn)):
            return True, "DELIMITER_MATCH"
            
    if len(q) >= 4 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if q_tokens and (q_tokens.issubset(c_tokens) or c_tokens.issubset(q_tokens)):
        return True, "TOKEN_SET_MATCH"
        
    return False, "NO_MATCH"

def is_valid_website(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.replace('www.', '').lower()
        if not domain or '.' not in domain or len(domain) < 4:
            return False
        if any(bad in domain for bad in BLACKLIST_DOMAINS):
            return False
        return True
    except Exception:
        return False

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    # Loại bỏ triệt để \u00a0, \xa0, &nbsp;, %20, zero-width và khoảng trắng lạ
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    return em.lower()

def is_valid_email(email):
    if not email or not isinstance(email, str):
        return False
    e = clean_email(email)
    if not e or '@' not in e:
        return False
    if any(bad in e for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ', '\t', '\n', '\r']):
        return False
    if len(e) < 6 or len(e) > 80:
        return False
    if any(jp in e for jp in JUNK_EMAIL_PARTS):
        return False
    if any(bad in e.split('@')[-1] for bad in BLACKLIST_EMAIL_DOMAINS):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', e):
        return False
    ext = e.split('.')[-1]
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf', 'ico']:
        return False
    return True

def score_email_b2b(email, website_domain=""):
    if not is_valid_email(email):
        return 0
    e = email.lower().strip()
    score = 10
    prefix = e.split('@')[0]
    email_domain = e.split('@')[1]
    
    # 1. Trùng domain website (+50đ)
    if website_domain and website_domain in email_domain:
        score += 50
    elif any(email_domain.endswith(free) for free in ['gmail.com', 'zoznam.sk', 'seznam.cz', 'centrum.sk', 'azet.sk', 'post.sk']):
        score += 10
        
    # 2. Đuôi .sk bản địa Slovakia (+30đ)
    if email_domain.endswith('.sk'):
        score += 30
        
    # 3. Nhân sự / Tuyển dụng / Việc làm (+50đ)
    if any(k in prefix for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    # 4. Ban Giám Đốc / Lãnh đạo / Kinh doanh (+45đ)
    elif any(k in prefix for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # 5. Cổng liên hệ chính thức (+40đ)
    elif any(k in prefix for k in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria']):
        score += 40
    # 6. Email cá nhân theo domain riêng (+25đ)
    elif '.' in prefix or '_' in prefix:
        score += 25
    else:
        score += 15
        
    return score

def decode_cf(email_code):
    try:
        r = int(email_code[:2], 16)
        email = ''.join([chr(int(email_code[i:i+2], 16) ^ r) for i in range(2, len(email_code), 2)])
        return email.strip().lower()
    except Exception:
        return ""

async def crawl_site_for_email(page, web_url):
    if not is_valid_website(web_url):
        return ""
    web_url = web_url.strip()
    if not web_url.startswith("http"):
        web_url = "https://" + web_url
        
    try:
        parsed_init = urllib.parse.urlparse(web_url)
        initial_domain = parsed_init.netloc.replace('www.', '').lower()
        if not initial_domain or len(initial_domain) < 4:
            return ""
    except Exception:
        return ""
        
    domain = initial_domain
    root = f"{parsed_init.scheme}://{parsed_init.netloc}"
    found_emails = set()
    
    try:
        await page.goto(web_url, wait_until='domcontentloaded', timeout=14000)
        await asyncio.sleep(1.0)
        
        actual_url = page.url or web_url
        try:
            parsed_act = urllib.parse.urlparse(actual_url)
            act_dom = parsed_act.netloc.replace('www.', '').lower()
            if act_dom and '.' in act_dom and not any(bad in act_dom for bad in BLACKLIST_DOMAINS):
                domain = act_dom
                root = f"{parsed_act.scheme}://{parsed_act.netloc}"
        except Exception:
            pass

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Cloudflare data-cfemail
        for cf in soup.select('[data-cfemail]'):
            dec = decode_cf(cf.get('data-cfemail', ''))
            if is_valid_email(dec):
                found_emails.add(dec)

        # mailto:
        for a in soup.select('a[href^="mailto:"]'):
            href = a.get('href', '')
            clean_m = href.replace('mailto:', '').split('?')[0].strip().lower()
            clean_m = urllib.parse.unquote(clean_m)
            if is_valid_email(clean_m):
                found_emails.add(clean_m)

        # Regex trên HTML
        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', content):
            em_clean = em.lower().strip()
            if is_valid_email(em_clean):
                found_emails.add(em_clean)

        # Thu thập các trang con liên hệ thực tế từ DOM menu (Priority 10)
        candidate_links = []
        for a in soup.find_all('a', href=True):
            h = a['href'].strip()
            t = a.get_text(separator=' ', strip=True).lower()
            if not h or h.startswith('#') or h.startswith('javascript:'):
                continue

            full_u = urllib.parse.urljoin(root, h)
            if not is_valid_website(full_u):
                continue
            try:
                p_u = urllib.parse.urlparse(full_u)
                if p_u.netloc.replace('www.', '').lower() != domain:
                    continue
            except Exception:
                continue

            path_l = p_u.path.lower()
            is_match = False
            for kw in ['kontakt', 'contact', 'karier', 'praca', 'o-nas', 'impressum', 'about']:
                if kw in path_l or kw in t:
                    is_match = True
                    break
            if is_match and full_u not in candidate_links and full_u != actual_url:
                candidate_links.append((full_u, 10))

        # Thêm các subpath đoán mò (Priority 2)
        for sp in SK_SUBPATHS:
            g_url = f"{root}{sp}"
            if not any(g_url == cl[0] for cl in candidate_links):
                candidate_links.append((g_url, 2))

        # Sắp xếp duyệt theo độ ưu tiên
        candidate_links.sort(key=lambda x: x[1], reverse=True)
        visited = {actual_url}

        for sub_url, prio in candidate_links[:8]:
            if sub_url in visited:
                continue
            visited.add(sub_url)

            # Nếu đã có email HR / Lãnh đạo hoặc trùng domain thì dừng sớm
            if found_emails and any(score_email_b2b(e, domain) >= 90 for e in found_emails):
                break

            try:
                await page.goto(sub_url, wait_until='domcontentloaded', timeout=10000)
                await asyncio.sleep(0.8)
                sub_content = await page.content()
                sub_soup = BeautifulSoup(sub_content, 'html.parser')

                for cf in sub_soup.select('[data-cfemail]'):
                    dec = decode_cf(cf.get('data-cfemail', ''))
                    if is_valid_email(dec):
                        found_emails.add(dec)

                for a in sub_soup.select('a[href^="mailto:"]'):
                    href = a.get('href', '')
                    clean_m = href.replace('mailto:', '').split('?')[0].strip().lower()
                    clean_m = urllib.parse.unquote(clean_m)
                    if is_valid_email(clean_m):
                        found_emails.add(clean_m)

                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', sub_content):
                    em_clean = em.lower().strip()
                    if is_valid_email(em_clean):
                        found_emails.add(em_clean)
            except Exception:
                pass

    except Exception:
        pass

    if not found_emails:
        return ""

    # Chấm điểm B2B để chọn 1 email tốt nhất
    scored = [(em, score_email_b2b(em, domain)) for em in found_emails]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_email, best_score = scored[0]
    return best_email if best_score > 0 else ""

def save_and_reorder_master(df):
    """
    Sắp xếp 100% doanh nghiệp có Email lên đầu file.
    Đánh lại số thứ tự No. từ 1 đến hết.
    Lưu đồng bộ vào TARGET_CSV và OUT_READY_CSV.
    """
    with_email = []
    without_email = []

    for idx, row in df.iterrows():
        em = str(row.get('Email') or '').strip().lower()
        r_dict = {c: str(row.get(c) or '') for c in COLUMNS_20}
        r_dict['SĐT'] = clean_phone_sk(r_dict.get('SĐT', ''))

        if em and em != 'nan' and is_valid_email(em):
            r_dict['Check gửi'] = 'OK'
            r_dict['Trạng thái Reply'] = ''
            with_email.append(r_dict)
        else:
            r_dict['Check gửi'] = ''
            r_dict['Trạng thái Reply'] = ''
            without_email.append(r_dict)

    current_no = 1
    final_rows = []
    for r in with_email:
        r['No.'] = str(current_no)
        final_rows.append(r)
        current_no += 1

    for r in without_email:
        r['No.'] = str(current_no)
        final_rows.append(r)
        current_no += 1

    df_final = pd.DataFrame(final_rows, columns=COLUMNS_20)
    df_final.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')

    # Xuất tệp chuyên dụng READY TO SEND (chỉ 100% dòng có Email, Check gửi = OK)
    if with_email:
        df_ready = pd.DataFrame(with_email, columns=COLUMNS_20)
        df_ready.to_csv(OUT_READY_CSV, index=False, encoding='utf-8-sig')

    return len(with_email)

async def run_enrichment(headless=False, limit=0):
    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU GOOGLE MAPS - SK_AUTO_SLVD CleanData")
    print("=" * 85)
    print(f"[*] File mục tiêu chính : {TARGET_CSV}")
    print(f"[*] Tệp sẵn sàng gửi    : {OUT_READY_CSV}")
    print(f"[*] Cache Checkpoint    : {CACHE_PATH}")
    print(f"[*] Trình duyệt Chrome  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False)'}")
    print("=" * 85 + "\n")

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy file mục tiêu: {TARGET_CSV}")
        return

    # Backup trước khi chạy
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo backup an toàn: {BACKUP_CSV.name}\n")

    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_companies = len(df)

    # Nạp cache
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache Checkpoint: {len(cache):,} công ty đã kiểm tra từ trước.")
        except Exception:
            cache = {}

    # Lọc các công ty CẦN TIẾP TỤC LÀM GIÀU (chưa có email)
    unprocessed_indices = []
    for idx in df.index:
        comp = str(df.at[idx, 'Công ty']).strip()
        if is_blacklisted_company(comp):
            continue

        c_key = comp.lower()
        if c_key in cache:
            cached_item = cache[c_key]
            if cached_item.get('Email'):
                df.at[idx, 'Email'] = cached_item['Email']
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{cached_item['Email']}"
                df.at[idx, 'Check gửi'] = 'OK'
            if cached_item.get('Web') and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = cached_item['Web']
            if cached_item.get('Phone') and not str(df.at[idx, 'SĐT']).strip():
                df.at[idx, 'SĐT'] = clean_phone_sk(cached_item['Phone'])
            if cached_item.get('Address') and not str(df.at[idx, 'Địa chỉ']).strip():
                df.at[idx, 'Địa chỉ'] = cached_item['Address']
            continue

        em = str(df.at[idx, 'Email']).strip()
        if em and em != 'nan' and is_valid_email(em):
            continue

        unprocessed_indices.append(idx)

    already_has = sum(1 for idx in df.index if str(df.at[idx, 'Email']).strip() and str(df.at[idx, 'Email']).strip() != 'nan')
    print(f"[*] Tổng số doanh nghiệp trong tệp : {total_companies:,}")
    print(f"[*] Đã có Email xác thực           : {already_has:,} ({already_has/total_companies*100:.1f}%)")
    print(f"[*] Đã kiểm tra & lưu Cache        : {len(cache):,} công ty")
    print(f"[*] CẦN TIẾP TỤC LÀM GIÀU          : {len(unprocessed_indices):,} công ty\n")

    if not unprocessed_indices:
        print("[✔] 100% công ty trong danh sách đã được làm giàu đầy đủ!")
        save_and_reorder_master(df)
        return

    target_list = unprocessed_indices if limit == 0 else unprocessed_indices[:limit]

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            locale="sk-SK",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )

        await browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        await browser.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])

        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed = 0
        new_emails_found = 0
        new_webs_found = 0
        new_phones_found = 0

        for idx in target_list:
            if page.is_closed():
                try:
                    page = await browser.new_page()
                except Exception:
                    pass

            comp = str(df.at[idx, 'Công ty']).strip()
            curr_phone = str(df.at[idx, 'SĐT']).strip()
            curr_web = str(df.at[idx, 'Liên Hệ']).strip()
            curr_addr = str(df.at[idx, 'Địa chỉ']).strip()
            city = extract_city_sk(comp, curr_addr)
            cache_key = comp.lower()

            found_email = ""
            gmap_web = None
            gmap_phone = None
            gmap_addr = None

            print(f"[{processed+1:04d}/{len(target_list):04d}] {comp[:35]:<35} | ", end="", flush=True)

            # BƯỚC 1: Nếu đã có website nhưng chưa có email
            if curr_web and is_valid_website(curr_web):
                found_email = await crawl_site_for_email(page, curr_web)
                if found_email:
                    print(f"WEB CÓ SẴN: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    new_emails_found += 1

            # BƯỚC 2: Tìm kiếm trên Google Maps
            if not found_email:
                search_comp = clean_company_name_for_search(comp)
                queries = []
                if city:
                    queries.append(f"{search_comp} {city}")
                    queries.append(f"{search_comp} Slovensko")
                    queries.append(f"{search_comp}")
                else:
                    queries.append(f"{search_comp} Slovensko")
                    queries.append(f"{search_comp} Slovakia")
                    queries.append(f"{search_comp}")

                matched = False
                for q_term in queries:
                    if matched:
                        break
                    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=sk"

                    for attempt in range(2):
                        try:
                            if page.is_closed():
                                page = await browser.new_page()

                            await page.goto(url, wait_until='domcontentloaded', timeout=18000)

                            try:
                                consent_btn = await page.query_selector(
                                    'button:has-text("Prijať všetko"), button:has-text("Prijať"), '
                                    'button:has-text("Accept all"), button[aria-label*="Accept all"], '
                                    'form[action*="consent"] button'
                                )
                                if consent_btn:
                                    await consent_btn.click()
                                    await asyncio.sleep(0.5)
                            except Exception:
                                pass

                            await asyncio.sleep(1.2)

                            page_title = await page.title()
                            if "Google Maps" not in page_title and ("Robot" in page_title or "unusual traffic" in page_title):
                                print("\n\a" + "!" * 70)
                                print("[!] CAPTCHA DETECTED: Vui lòng giải Captcha trên cửa sổ Chrome!")
                                print("!" * 70)
                                for _ in range(60):
                                    if "Google Maps" in await page.title():
                                        break
                                    await asyncio.sleep(2.0)

                            # Phân tích kết quả Maps
                            first_card = await page.query_selector('a.hfpxzc')
                            if first_card:
                                c_aria = await first_card.get_attribute('aria-label') or ""
                                is_ok, _ = is_valid_name_match(comp, c_aria)
                                if is_ok:
                                    matched = True
                                    await first_card.click()
                                    await asyncio.sleep(1.8)
                            else:
                                title_elem = await page.query_selector('h1.DUwDvf')
                                if title_elem:
                                    t_text = await title_elem.inner_text()
                                    is_ok, _ = is_valid_name_match(comp, t_text)
                                    matched = is_ok

                            if matched:
                                web_btn = await page.query_selector('a[data-item-id="authority"]')
                                if web_btn:
                                    cand_web = await web_btn.get_attribute('href')
                                    if cand_web and is_valid_website(cand_web):
                                        gmap_web = cand_web

                                phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                                if phone_btn:
                                    p_attr = await phone_btn.get_attribute('data-item-id')
                                    if p_attr and p_attr.startswith('phone:tel:'):
                                        gmap_phone = p_attr.replace('phone:tel:', '').strip()
                                    else:
                                        p_txt = await phone_btn.inner_text()
                                        if re.search(r'\d{3,}', p_txt):
                                            gmap_phone = p_txt.strip()

                                addr_btn = await page.query_selector('button[data-item-id="address"]')
                                if addr_btn:
                                    cand_addr = await addr_btn.get_attribute('aria-label') or await addr_btn.inner_text()
                                    cand_addr = re.sub(r'^(?:Adresa|Address)[:\s]*', '', cand_addr, flags=re.I).strip()
                                    if cand_addr and len(cand_addr) > 5:
                                        gmap_addr = cand_addr

                                break
                        except Exception:
                            if attempt == 0:
                                await asyncio.sleep(2.0)

                if gmap_web and not curr_web:
                    df.at[idx, 'Liên Hệ'] = gmap_web
                    curr_web = gmap_web
                    new_webs_found += 1

                if gmap_phone and not curr_phone:
                    df.at[idx, 'SĐT'] = clean_phone_sk(gmap_phone)
                    curr_phone = df.at[idx, 'SĐT']
                    new_phones_found += 1

                if gmap_addr and not curr_addr:
                    df.at[idx, 'Địa chỉ'] = gmap_addr
                    curr_addr = gmap_addr

                if curr_web and is_valid_website(curr_web):
                    found_email = await crawl_site_for_email(page, curr_web)
                    if found_email:
                        new_emails_found += 1
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | EMAIL: {found_email}")
                    else:
                        print(f"GMAP->WEB: {curr_web[:22]:<22} | (Chưa thấy mail)")
                elif matched and gmap_phone:
                    print(f"GMAP: {clean_phone_sk(gmap_phone):<20} | (Khớp Maps - Có SĐT)")
                elif matched:
                    print(f"GMAP | (Khớp địa điểm - Không có web)")
                else:
                    print(f"No match | (Không tìm thấy trên Maps)")

            if found_email:
                df.at[idx, 'Email'] = found_email
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{found_email}"
                df.at[idx, 'Check gửi'] = 'OK'

            cache[cache_key] = {
                'Web': curr_web,
                'Email': found_email,
                'Phone': curr_phone,
                'Address': curr_addr,
                'Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed += 1

            # Lưu tăng dần mỗi 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                curr_total_emails = save_and_reorder_master(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {curr_total_emails:,}/{total_companies:,} công ty có Email được đưa lên đầu file CSV.")

        # Lưu checkpoint cuối
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        final_emails = save_and_reorder_master(df)

        print("\n" + "=" * 85)
        print(" HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
        print(f" [*] Tổng số công ty          : {total_companies:,}")
        print(f" [*] Đã bóc tách được Email   : {final_emails:,} / {total_companies:,} ({(final_emails/total_companies)*100:.1f}%)")
        print(f" [*] Email mới tìm thấy thêm  : +{new_emails_found:,}")
        print(f" [*] Website mới tìm thấy thêm: +{new_webs_found:,}")
        print(f" [*] SĐT mới tìm thấy thêm    : +{new_phones_found:,}")
        print(f" [*] Đã lưu đồng bộ ra các tệp:")
        print(f"     - {TARGET_CSV.name} (Tệp mục tiêu chính - 100% Email lên đầu)")
        print(f"     - {OUT_READY_CSV.name} (Tệp chuyên dụng sẵn sàng gửi)")
        print("=" * 85 + "\n")

        await browser.close()

def main():
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for SK_AUTO CleanData")
    parser.add_argument("--headless", action="store_true", help="Chạy ngầm không mở cửa sổ (mặc định mở trực quan)")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số công ty xử lý (0 = toàn bộ)")
    args = parser.parse_args()

    asyncio.run(run_enrichment(headless=args.headless, limit=args.limit))

if __name__ == '__main__':
    main()
