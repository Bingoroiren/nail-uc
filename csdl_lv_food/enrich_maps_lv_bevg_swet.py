"""
HỆ THỐNG LÀM GIÀU DỮ LIỆU ĐA TẦNG (HYBRID ENRICHMENT) - BÁNH KẸO & NƯỚC NGỌT LATVIA
================================================================================
Pipeline:
  Tier 1: Google Maps Trực quan (Headless=False) với thuật toán làm sạch tên tiếng Anh
          (loại bỏ triệt để 'Limited liability company', 'Joint-stock company', 'SIA', 'AS'...)
  Tier 2: Mở rộng bộ selector Google Maps (Website, Phone, Address) và tăng thời gian đợi sidebar
  Tier 3: Web Search Fallback (DuckDuckGo / Firmas.lv) khi Maps báo 'No match'
  Tier 4: Deep Multi-path Crawler bóc tách Email & SĐT tiếng Latvia (/kontakti, /contacts, /par-mums...)
  Tier 5: B2B Heuristic Scoring chấm điểm email tuyển dụng/lãnh đạo/chính thức, lọc 100% mail rác
  Tier 6: Checkpoint Cache & Incremental Save, đẩy 100% doanh nghiệp có email lên đầu tệp CSV
"""

import sys
import os
import re
import json
import asyncio
import unicodedata
import urllib.parse
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from curl_cffi import requests as c_requests

# Thiết lập stdout UTF-8 tránh lỗi cp1252 trên Windows CMD
sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(r"d:\glc\nail uc")
CSDL_DIR = ROOT_DIR / "csdl_lv_food"

TARGET_CSV_ROOT = ROOT_DIR / "LV_SWET_WEBD_2COL.csv"
TARGET_CSV_CSDL = CSDL_DIR / "LV_SWET_WEBD_2COL.csv"
CACHE_PATH = CSDL_DIR / "cache_enrich_maps_lv_bevg_swet.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "lv_bevg_swet_maps_profile"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no',
    '1188.lv', 'viss.lv', 'crediweb.lv', 'crefocert.lv', 'lursoft.lv', 'firmas.lv',
    'ss.lv', 'ss.com', 'visasdarbavietas.lv', 'katalogs.lv',
    'zl.lv', 'zo.lv', 'latvijasbizness.lv', 'pilseta24.lv', 'vietas.lv',
    'wikipedia.org', 'delfi.lv', 'tvnet.lv', 'apollo.lv', 'lsm.lv', 'jauns.lv',
    'okredo.com', 'scamvn.com', 'sentry.io', 'wixpress.com', 'wix.com', 'wordpress.com',
    'tet.lv', 'maptiler.com', 'openstreetmap.org', 'schema.org',
    'flashscore', 'chefspencil', 'spamcalls', 'mofa.go.jp', 'usembassy', 'state.gov',
    'railbaltica.org', 'ur.gov.lv', 'nva.gov.lv', 'liaa.gov.lv', 'daba.gov.lv',
    'cvk.lv', 'km.gov.lv', 'latvija.lv', 'vraa.gov.lv', 'yourwebsite.com',
    'superalko.lv', 'alkoutlet.lv', 'depo.lv', 'schwenk', 'travelart.lv',
    'rigaslifti.lv', 'ldz.lv', 'lvvignette.eu', 'ziemellatvija.lv', 'raw-tech.lv',
    'aaru.com', 'keystonecollection.com', 'estatelatvia.com', 'dojuslatvija.lv',
    'motivs.lv', 'waterro.eu', 'concordiaclinic.lv', 'glslatvija.lv',
    'latagro.lv', 'euroflizes.lv', 'zum1.lv', 'e-lats.lv', 'heidelberg.com', 'kpmg.com',
    'livoniaprint.lv', 'amis.lv', 'mustangs.lv', 'spilves.lv', 'pumpursmaja.lv',
    'seklas.lv', 'jewishgen.org', 'president.lv', 'draugiem.lv', 'steamcommunity.com',
    'pasts.lv', 'baltezers.lv', 'veclaicene.lv', 'eraser.lv'
]

GLOBAL_GIANT_DOMAINS = [
    'apple.com', 'google.com', 'amazon.com', 'microsoft.com',
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'youtube.com', 'linkedin.com', 'tiktok.com', 'steamcommunity.com',
    'draugiem.lv', 'flashscore.com', 'flashscore.lv', 'chefspencil.com',
    'wikipedia.org', 'delfi.lv', 'tvnet.lv', 'apollo.lv', 'lsm.lv', 'jauns.lv',
    'livoniaprint.lv', 'amis.lv', 'mustangs.lv', 'spilves.lv', 'pumpursmaja.lv',
    'seklas.lv', 'concordiaclinic.lv', 'kpmg.com', 'glslatvija.lv'
]

VERIFIED_BRAND_DOMAINS = {
    'tukuma': ['baltais.lv'],
    'pernes': ['longchips.eu', 'longchips.com'],
    'saldus gotina': ['saldusgotina.lv'],
    'saldus partikas kombinats': ['saldusgotina.lv'],
    'dziru kalve': ['kalvecoffee.com'],
    'amber latvijas balzams': ['amberlb.lv', 'amberbev.com', 'lb.lv'],
    'amber distribution': ['amberdistribution.lv', 'amberbev.com'],
    'uzavas alus': ['uzavasalus.eu', 'uzavasalus.lv'],
    'rezeknes bruveris': ['rezeknesbruveris.lv'],
    'turkalnes muiza': ['turkalnesmuiza.lv'],
    'nurme': ['nurmebeer.com'],
    '885': ['water885.com'],
    'snowflake': ['snowflake.club'],
    'unisel': ['uniselco.com', 'unisel.lv'],
    'eurobaltic water': ['balticwater.lv']
}

BANNED_CATEGORIES_AND_WORDS = [
    'clinic', 'klīnika', 'klinika', 'slimnīca', 'slimnica', 'ārsts', 'arsts', 'veselība', 'veseliba', 'medicīn', 'medicin', 'hospital',
    'autoskola', 'driving', 'auto remonts', 'autoserviss', 'transports', 'loģistika', 'logistika', 'pārvadājumi',
    'drukas', 'iespiešana', 'iespiesana', 'tipogrāfija', 'tipografija', 'poligrāfija', 'poligrafija', 'printing', 'copy shop',
    'viesnīca', 'viesnica', 'hotel', 'brīvdienu māja', 'brivdienu maja', 'apartamenti', 'naktsmītne', 'naktsmitne', 'kempings',
    'nekustamie īpašumi', 'nekustamie ipasumi', 'real estate', 'advokāts', 'advokats', 'juridiskie', 'grāmatvedība', 'gramatvediba', 'audits',
    'valsts', 'ministrija', 'aģentūra', 'agentura', 'vēstniecība', 'vestnieciba', 'policija', 'tiesa', 'pašvaldība',
    'skola', 'universitāte', 'universitate', 'bērnudārzs', 'sporta klubs', 'fitnesa', 'frizētava', 'skaistumkopšana'
]

BLACKLIST_EMAIL_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'sentry.io', 'wixpress.com', 'wix.com',
    'wordpress.com', 'maptiler.com', 'schema.org',
    'flashscore.com', 'chefspencil.com', 'spamcalls.net', 'mofa.go.jp', 'state.gov',
    'ur.gov.lv', 'nva.gov.lv', 'liaa.gov.lv', 'daba.gov.lv', 'cvk.lv', 'km.gov.lv',
    'railbaltica.org', 'yourwebsite.com', 'kpmg.com', 'heidelberg.com', 'schwenk.com',
    'livoniaprint.lv', 'amis.lv', 'mustangs.lv', 'spilves.lv', 'pumpursmaja.lv',
    'seklas.lv', 'concordiaclinic.lv', 'glslatvija.lv', 'draugiem.lv', 'president.lv',
    'jewishgen.org', 'pasts.lv', 'apple.com'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

JUNK_EMAIL_PARTS = [
    'sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail',
    'your-email', 'someone', 'john.doe', 'user@domain', 'name@domain',
    'email@email', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'abuse',
    'postmaster', 'hostmaster', 'mailer-daemon', 'test@', 'demo@'
]

LV_CITIES = [
    "Rīga", "Riga", "Daugavpils", "Liepāja", "Liepaja", "Jelgava", "Jūrmala", "Jurmala",
    "Ventspils", "Rēzekne", "Rezekne", "Valmiera", "Jēkabpils", "Jekabpils", "Ogre",
    "Salaspils", "Tukums", "Cēsis", "Cesis", "Sigulda", "Olaine", "Kuldīga", "Kuldiga",
    "Saldus", "Talsi", "Dobele", "Krāslava", "Kraslava", "Bauska", "Ludza", "Līvāni", "Livani",
    "Gulbene", "Madona", "Alūksne", "Aluksne", "Aizkraukle", "Balvi", "Limbaži", "Limbazi",
    "Preiļi", "Preili", "Valka", "Smiltene", "Viļāni", "Vilani", "Iecava", "Baloži", "Balozi"
]

HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_lv(phone_str):
    if not phone_str or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip().lstrip("'")
    p = re.sub(r'[^\d+]', '', p)
    if not p:
        return ""
    if re.match(r'^(?:2|6)\d{7}$', p):
        p = f"+371{p}"
    elif p.startswith("371") and len(p) == 11:
        p = f"+{p}"
    elif p.startswith("00371"):
        p = f"+{p[2:]}"
    return f"'{p}" if not p.startswith("'") else p

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
    em = clean_email(email)
    if not em or '@' not in em:
        return False
    # Tuyệt đối không để lẫn \u00a0, khoảng trắng hay %20
    if any(bad in em for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', ' ', '\t', '\n', '\r']):
        return False
    if any(em.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css']):
        return False
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return False
    for bad in JUNK_EMAIL_PARTS:
        if bad in em:
            return False
    domain = em.split('@')[-1]
    if any(b == domain or domain.endswith('.' + b) for b in BLACKLIST_EMAIL_DOMAINS):
        return False
    return True

def score_email_b2b(email, website_domain=""):
    if not is_valid_email(email):
        return 0
    em = email.lower()
    prefix = em.split('@')[0]
    domain = em.split('@')[1]
    score = 10

    if website_domain and (domain in website_domain or website_domain in domain):
        score += 50

    # Ưu tiên Tuyển dụng / HR
    if any(k in prefix for k in ['vakances', 'darbs', 'personals', 'kariera', 'hr', 'jobs', 'recruitment', 'career']):
        score += 50
    # Ưu tiên Lãnh đạo điều hành
    elif any(k in prefix for k in ['valde', 'direktors', 'vadiba', 'ceo', 'director', 'manager', 'obchod', 'sales', 'eksports', 'export']):
        score += 45
    # Cổng thông tin / liên hệ chính thức
    elif any(k in prefix for k in ['info', 'birojs', 'office', 'kontakt', 'kontakti', 'contact', 'kanceleja', 'sekretariat']):
        score += 40
    # Đích danh cá nhân
    elif '.' in prefix or '_' in prefix:
        score += 25
    # Webmail phổ biến Latvia (inbox.lv, gmail.com)
    elif domain in ['inbox.lv', 'gmail.com', 'mail.lv', 'apollo.lv']:
        score += 15

    return score

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email.strip().lower()
    except Exception:
        return ""

def strip_accents(text):
    if not text:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

def normalize_text_core(text):
    if not text:
        return ""
    t = re.sub(r'["\'„“”«»]', '', str(text)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()

    legal_forms = [
        r'\bsabiedrība ar ierobežotu atbildību\b', r'\bakciju sabiedrība\b',
        r'\bindividuālais komersants\b',
        r'\blimited liability company\b', r'\bjoint-stock company\b',
        r'\blimited liability comp\w*\b', r'\blimited liabili\w*\b',
        r'\bjoint-stock comp\w*\b',
        r'\bsia\b', r'\bas\b', r'\ba/s\b', r'\bik\b', r'\bps\b', r'\bks\b',
        r'\bltd\b', r'\bllc\b'
    ]
    for lf in legal_forms:
        t = re.sub(lf, '', t, flags=re.I).strip()

    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return strip_accents(t)

def clean_company_name_for_search(name):
    t = re.sub(r'["\'„“”«»]', '', str(name)).strip()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    
    # Loại bỏ triệt để các hậu tố tiếng Anh và loại hình doanh nghiệp
    remove_patterns = [
        r'\b(?:Limited liability company|Joint-stock company|Limited liability comp\w*|Limited liabili\w*|Joint-stock comp\w*)\b',
        r'\b(?:SIA|AS|A/S|IK|PS|KS|LTD|LLC)\b'
    ]
    for p in remove_patterns:
        t = re.sub(p, '', t, flags=re.I).strip(' ,.-')
        
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return t

def extract_city_lv(comp_name, addr):
    c_name = str(comp_name or "")
    for city in LV_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", c_name, re.IGNORECASE):
            return city

    if addr and isinstance(addr, str):
        m_post = re.search(r"LV-\d{4}\s+([A-Za-zĀ-ž]+)", addr)
        if m_post:
            c = m_post.group(1).strip()
            if c:
                return c
        for city in LV_CITIES:
            if re.search(rf"\b{re.escape(city)}\b", addr, re.IGNORECASE):
                return city
    return ""

GENERIC_INDUSTRY_WORDS = {
    'alus', 'vins', 'vīns', 'dzerieni', 'dzērieni', 'razosana', 'ražošana', 'partika',
    'pārtika', 'tirdznieciba', 'tirdzniecība', 'daritava', 'darītava', 'bruzis', 'brūzis',
    'group', 'grupa', 'holding', 'latvia', 'latvija', 'baltic', 'baltics', 'baltija',
    'serviss', 'projekti', 'services', 'food', 'foods', 'company', 'international',
    'nordic', 'europe', 'management', 'solutions', 'factory', 'manufaktura',
    'distillery', 'brewery', 'winery', 'cider', 'spirits', 'beer', 'wine', 'water',
    'craft', 'artisanal', 'kombinats', 'kombināts', 'rupnica', 'rūpnīca',
    'darbnica', 'darbnīca', 'komercfirma', 'komercija', 'veikals', 'sabiedriba', 'akciju'
}

def get_distinctive_tokens(name):
    t = normalize_text_core(name)
    tokens = [re.sub(r'[^\w]', '', w) for w in re.split(r'[\s,.-]+', t) if len(w) >= 3 and w not in GENERIC_INDUSTRY_WORDS]
    return tokens if tokens else [w for w in re.split(r'[\s,.-]+', t) if len(w) >= 3]

def is_valid_name_match(query_name, candidate_name, candidate_category=""):
    """So khớp tên cực gắt: Ngăn chặn 100% việc gán nhầm đối thủ cạnh tranh hoặc ngành cấm"""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    # 1. Kiểm tra Category của địa điểm trên Google Maps nếu có
    if candidate_category:
        norm_cat = strip_accents(candidate_category).lower()
        for bad_cat in BANNED_CATEGORIES_AND_WORDS:
            if bad_cat in norm_cat:
                return False, f"BANNED_CATEGORY ({candidate_category})"

    q = normalize_text_core(query_name)
    c = normalize_text_core(candidate_name)

    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"

    # 2. Kiểm tra từ khóa cấm trong tên địa điểm
    for bad_w in ['clinic', 'klinika', 'autoskola', 'tipograf', 'poligraf', 'brivdienu maja', 'apartament', 'naktsmitne', 'real estate', 'advokat', 'audits']:
        if bad_w in c and bad_w not in q:
            return False, f"BANNED_WORD_IN_CANDIDATE ({bad_w})"

    # 3. Khớp chính xác hoàn toàn
    if q == c:
        return True, "EXACT"

    # 4. Tên ngắn (Acronym < 4 ký tự như DRU, GRP, VOL, KZ) -> BẮT BUỘC KHỚP TUYỆT ĐỐI
    if len(q) < 4:
        return q == c, "SHORT_ACRONYM"

    q_dist = get_distinctive_tokens(query_name)
    c_dist = get_distinctive_tokens(candidate_name)

    if not q_dist or not c_dist:
        return False, "NO_DISTINCTIVE_TOKENS"

    # 5. Phân tách theo dấu delimiter (-, |, /)
    parts = [strip_accents(p.strip()) for p in re.split(r'[-–—|/:,]', candidate_name) if p.strip()]
    for p in parts:
        pn = normalize_text_core(p)
        if pn == q:
            return True, "DELIMITER_EXACT"

    # 6. So khớp tokens đặc trưng
    matched_tokens = set(q_dist).intersection(set(c_dist))

    # Nếu chỉ có 1 từ đặc trưng (ví dụ: 'ranzen', 'matilde', 'liduma', 'pescado', 'konkordijas'):
    # Từ đặc trưng đó BẮT BUỘC phải xuất hiện trong tên địa điểm
    if len(q_dist) == 1:
        if q_dist[0] in c_dist or any(q_dist[0] in cd for cd in c_dist):
            return True, f"SINGLE_TOKEN_EXACT ({q_dist[0]})"
        return False, f"SINGLE_TOKEN_MISMATCH (Expected {q_dist[0]})"

    # Nếu có nhiều từ đặc trưng (ví dụ: 'talavas kenina', 'sparkling apple'):
    # Bắt buộc khớp ít nhất 70% số từ đặc trưng
    if len(matched_tokens) >= len(q_dist) * 0.7:
        return True, f"TOKEN_MATCH ({matched_tokens})"

    # 7. Substring match chỉ chấp nhận nếu ứng viên chứa toàn bộ tên query
    if q in c and len(c) <= len(q) * 2.5:
        return True, "QUERY_IN_CANDIDATE"

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
        if any(bad in domain for bad in GLOBAL_GIANT_DOMAINS):
            return False
        if any(domain.endswith(tld) or ('.' + tld + '.') in ('.' + domain + '.') for tld in ['gov', 'gov.lv', 'mil', 'edu', 'edu.lv', 'mofa.go.jp', 'state.gov']):
            return False
        return True
    except Exception:
        return False

def is_domain_strictly_matching(company_name, web_url):
    """Kiểm tra khắt khe: Tên miền BẮT BUỘC phải liên quan trực tiếp đến tên công ty"""
    if not web_url or not company_name:
        return False, "EMPTY"
    u = web_url.strip().lower()
    if not u.startswith('http'):
        u = 'https://' + u
    try:
        parsed = urllib.parse.urlparse(u)
        dom = parsed.netloc.replace('www.', '').lower()
    except Exception:
        return False, "INVALID_URL"

    # Loại bỏ TLD chính phủ, giáo dục, quân sự
    if any(dom.endswith(tld) or ('.' + tld + '.') in ('.' + dom + '.') for tld in ['gov', 'gov.lv', 'mil', 'edu', 'edu.lv']):
        return False, f"GOV_DOMAIN ({dom})"

    # Loại bỏ tên miền khổng lồ / mạng xã hội / blog
    for bad_dom in GLOBAL_GIANT_DOMAINS:
        if dom == bad_dom or dom.endswith('.' + bad_dom):
            return False, f"GIANT_DOMAIN ({dom})"

    # Loại bỏ tên miền chứa ngành cấm
    for bad_w in ['clinic', 'klinika', 'autoskola', 'print', 'tipograf', 'poligraf', 'travel', 'hotel', 'brivdienu', 'apartament', 'estate', 'advokat', 'audit', 'army']:
        if bad_w in dom:
            return False, f"BANNED_INDUSTRY_DOMAIN ({bad_w})"

    domain_label = dom.split('.')[0]
    domain_label_clean = strip_accents(domain_label)

    # Kiểm tra Brand Dictionary ngoại lệ đã kiểm chứng
    clean_c = normalize_text_core(company_name)
    for brand, allowed_doms in VERIFIED_BRAND_DOMAINS.items():
        if brand in clean_c:
            if any(ad in dom for ad in allowed_doms):
                return True, f"VERIFIED_BRAND_DICT ({brand})"

    dist_tokens = get_distinctive_tokens(company_name)
    if not dist_tokens:
        return False, "NO_DIST_TOKENS"

    def match_tok_in_dom(t, d):
        if not t or not d:
            return False
        if t in d or (len(d) >= 4 and d in t):
            return True
        # Stemming đuôi biến cách tiếng Latvia (ví dụ: zakumuizas -> zakumuiz, valmiermuizas -> valmiermuiz)
        stem = t
        if len(t) >= 6 and t.endswith(('as', 'es', 'is', 'os', 'us')):
            stem = t[:-2]
        elif len(t) >= 5 and t.endswith(('a', 'e', 'i', 'u')):
            stem = t[:-1]
        if len(stem) >= 4 and stem in d:
            return True
        return False

    # Nếu chỉ có 1 từ đặc trưng (ví dụ: 'ranzen', 'matilde', 'liduma', 'pescado'):
    # Từ đó BẮT BUỘC phải nằm trong tên miền
    if len(dist_tokens) == 1:
        tok = dist_tokens[0]
        if match_tok_in_dom(tok, domain_label_clean):
            return True, f"SINGLE_TOKEN_DOMAIN ({tok})"
        return False, f"DOMAIN_LACKS_TOKEN ({tok} not in {dom})"

    # Nếu có nhiều từ đặc trưng (ví dụ: 'sparkling apple', 'duna brewery'):
    matched_toks = [tok for tok in dist_tokens if match_tok_in_dom(tok, domain_label_clean)]
    
    # Tuyệt đối không cho phép từ tiếng Anh quá thông dụng ('apple', 'sun', 'star') khớp đơn lẻ nếu không có từ đi kèm
    if set(matched_toks) == {'apple'}:
        return False, f"GENERIC_ENGLISH_WORD_ONLY ({dom})"

    if len(matched_toks) >= 1 and (len(dist_tokens) <= 2 or len(matched_toks) >= len(dist_tokens) * 0.5):
        return True, f"MULTI_TOKEN_DOMAIN ({matched_toks})"

    # Kiểm tra acronym viết tắt (ví dụ: prp -> prp.lv, rkf valezs -> valezs.lv)
    if len(dist_tokens) >= 2:
        acronym = ''.join(tok[0] for tok in dist_tokens)
        if len(acronym) >= 2 and acronym == domain_label_clean:
            return True, f"ACRONYM_DOMAIN ({acronym})"
        first_tok = dist_tokens[0]
        if len(first_tok) >= 2 and first_tok == domain_label_clean:
            return True, f"FIRST_TOKEN_ACRONYM ({first_tok})"

    return False, f"DOMAIN_UNRELATED ({dom})"

def is_email_strictly_matching(company_name, web_url, email):
    """Kiểm tra khắt khe: Email BẮT BUỘC phải là mail chính thức của doanh nghiệp"""
    if not email or '@' not in email:
        return False, "EMPTY"
    em = email.strip().lower()
    prefix = em.split('@')[0]
    dom = em.split('@')[1]

    # Nếu email trùng domain website đã xác thực hoặc cùng brand slug (.lv và .com/.ee) -> 100% HỢP LỆ
    if web_url:
        try:
            w_parsed = urllib.parse.urlparse(web_url if web_url.startswith('http') else 'http://' + web_url)
            w_dom = w_parsed.netloc.replace('www.', '').lower()
            if dom in w_dom or w_dom in dom:
                return True, "DOMAIN_MATCH"
            # Cùng brand slug (ví dụ: puratos.lv và puratos.com, liviko.lv và liviko.ee)
            w_brand = w_dom.split('.')[0]
            m_brand = dom.split('.')[0]
            if len(w_brand) >= 4 and (w_brand in m_brand or m_brand in w_brand):
                return True, f"BRAND_SLUG_MATCH ({w_brand})"
        except Exception:
            pass

    # Kiểm tra ngoại lệ trong VERIFIED_BRAND_DOMAINS
    clean_c = normalize_text_core(company_name)
    for brand, allowed_doms in VERIFIED_BRAND_DOMAINS.items():
        if brand in clean_c:
            if any(ad in dom or dom in ad for ad in allowed_doms):
                return True, f"VERIFIED_BRAND_MAIL ({brand})"

    # Nếu là Webmail (gmail.com, inbox.lv): BẮT BUỘC PREFIX PHẢI CHỨA TỪ KHÓA THƯƠNG HIỆU
    if dom in ['gmail.com', 'inbox.lv', 'mail.lv']:
        dist_tokens = get_distinctive_tokens(company_name)
        for tok in dist_tokens:
            if len(tok) >= 3 and tok in prefix:
                return True, f"WEBMAIL_BRAND_MATCH ({tok})"
        return False, f"WEBMAIL_LACKS_BRAND ({prefix})"

    return False, f"EMAIL_DOMAIN_MISMATCH ({dom})"

# ==============================================================================
# TẦNG 4: BÓC TÁCH EMAIL & SĐT TRÊN WEBSITE (HTTP FAST SCAN + PLAYWRIGHT FALLBACK)
# ==============================================================================
def fast_scan_website_emails(target_url):
    """Quét cực nhanh các trang con liên hệ bằng HTTP không cần render JS nặng"""
    found_emails = set()
    found_phone = ""
    if not is_valid_website(target_url):
        return "", ""

    target_url = target_url.strip()
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    try:
        p = urllib.parse.urlparse(target_url)
        domain = p.netloc.replace('www.', '').lower()
        root = f"{p.scheme}://{p.netloc}"

        subpaths_to_check = [
            target_url,
            f"{root}/kontakti", f"{root}/contacts", f"{root}/kontakt",
            f"{root}/lv/kontakti", f"{root}/en/contacts", f"{root}/par-mums",
            f"{root}/kontakti/", f"{root}/contacts/", f"{root}/vakances",
            f"{root}/darbs", f"{root}/about"
        ]

        # Kiểm tra trang chủ trước
        try:
            r = c_requests.get(target_url, headers=HTTP_HEADERS, impersonate="chrome120", timeout=6)
            content = r.text
            soup = BeautifulSoup(content, 'html.parser')

            # CF email
            for cf in soup.select('[data-cfemail]'):
                dec = decode_cf(cf.get('data-cfemail', ''))
                if is_valid_email(dec):
                    found_emails.add(dec)

            # Mailto
            for a in soup.select('a[href^="mailto:"]'):
                m = a['href'].replace('mailto:', '').split('?')[0].strip().lower()
                m = urllib.parse.unquote(m)
                if is_valid_email(m):
                    found_emails.add(m)

            # Regex mail
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', content):
                em_l = em.lower().strip()
                if is_valid_email(em_l):
                    found_emails.add(em_l)

            # SĐT trên trang chủ
            for a in soup.select('a[href^="tel:"]'):
                ph = clean_phone_lv(a['href'].replace('tel:', ''))
                if ph and not found_phone:
                    found_phone = ph

            # Tìm thêm link liên hệ từ DOM menu
            for a in soup.find_all('a', href=True):
                h = a['href'].strip()
                txt = a.get_text(separator=' ', strip=True).lower()
                if any(k in h.lower() or k in txt for k in ['kontakt', 'contact', 'par-mums', 'about', 'info', 'vakances', 'darbs']):
                    full_u = urllib.parse.urljoin(target_url, h)
                    try:
                        if urllib.parse.urlparse(full_u).netloc.replace('www.', '').lower() == domain:
                            if full_u not in subpaths_to_check:
                                subpaths_to_check.insert(1, full_u)
                    except Exception:
                        pass
        except Exception:
            pass

        # Quét tiếp các trang con (tối đa 5 trang có triển vọng nhất)
        visited = {target_url}
        for sub_u in subpaths_to_check[:6]:
            if sub_u in visited:
                continue
            visited.add(sub_u)

            if found_emails and any(score_email_b2b(e, domain) >= 90 for e in found_emails):
                break

            try:
                r_sub = c_requests.get(sub_u, headers=HTTP_HEADERS, impersonate="chrome120", timeout=5)
                sub_content = r_sub.text
                sub_soup = BeautifulSoup(sub_content, 'html.parser')

                for cf in sub_soup.select('[data-cfemail]'):
                    dec = decode_cf(cf.get('data-cfemail', ''))
                    if is_valid_email(dec):
                        found_emails.add(dec)

                for a in sub_soup.select('a[href^="mailto:"]'):
                    m = a['href'].replace('mailto:', '').split('?')[0].strip().lower()
                    m = urllib.parse.unquote(m)
                    if is_valid_email(m):
                        found_emails.add(m)

                for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', sub_content):
                    em_l = em.lower().strip()
                    if is_valid_email(em_l):
                        found_emails.add(em_l)

                if not found_phone:
                    for a in sub_soup.select('a[href^="tel:"]'):
                        ph = clean_phone_lv(a['href'].replace('tel:', ''))
                        if ph:
                            found_phone = ph
                            break
            except Exception:
                pass

    except Exception:
        pass

    best_email = ""
    if found_emails:
        scored = [(em, score_email_b2b(em, domain)) for em in found_emails]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_email = scored[0][0] if scored[0][1] > 0 else ""

    return best_email, found_phone

async def playwright_crawl_site_for_email(page, target_url):
    """Fallback dùng Playwright bóc tách trang động JS nếu HTTP chưa ra mail"""
    found_emails = set()
    found_phone = ""
    try:
        p = urllib.parse.urlparse(target_url)
        domain = p.netloc.replace('www.', '').lower()

        await page.goto(target_url, wait_until='domcontentloaded', timeout=12000)
        await asyncio.sleep(1.0)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        for cf in soup.select('[data-cfemail]'):
            dec = decode_cf(cf.get('data-cfemail', ''))
            if is_valid_email(dec):
                found_emails.add(dec)

        for a in soup.select('a[href^="mailto:"]'):
            clean_m = a.get('href', '').replace('mailto:', '').split('?')[0].strip().lower()
            clean_m = urllib.parse.unquote(clean_m)
            if is_valid_email(clean_m):
                found_emails.add(clean_m)

        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}', content):
            em_clean = em.lower().strip()
            if is_valid_email(em_clean):
                found_emails.add(em_clean)

        for a in soup.select('a[href^="tel:"]'):
            ph = clean_phone_lv(a.get('href', '').replace('tel:', ''))
            if ph and not found_phone:
                found_phone = ph

    except Exception:
        pass

    best_email = ""
    if found_emails:
        scored = [(em, score_email_b2b(em, domain)) for em in found_emails]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_email = scored[0][0] if scored[0][1] > 0 else ""

    return best_email, found_phone

# ==============================================================================
# TẦNG 3: WEB SEARCH FALLBACK (DUCKDUCKGO HTML / FIRMAS.LV)
# ==============================================================================
def search_web_fallback(company_name, city=""):
    """Tìm kiếm web bổ trợ khi Google Maps không ra kết quả"""
    clean_name = clean_company_name_for_search(company_name)
    query = f"{clean_name} Latvia (kontakti OR epasts OR talrunis)"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

    found_web = ""
    found_phone = ""

    try:
        r = c_requests.get(url, headers=HTTP_HEADERS, impersonate="chrome120", timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')

        for item in soup.select('.result__body'):
            link = item.select_one('a.result__url')
            snippet = item.select_one('.result__snippet')
            snippet_text = snippet.get_text(separator=' ', strip=True) if snippet else ""

            if link:
                href = link.get('href', '')
                # Unquote duckduckgo redirect link
                m_uddg = re.search(r'uddg=([^&]+)', href)
                target_site = urllib.parse.unquote(m_uddg.group(1)) if m_uddg else href.strip()

                if is_valid_website(target_site) and not found_web:
                    found_web = target_site

            # Tìm số điện thoại trong snippet (vd: tālrunis 67844565 hoặc 29xxxxxx)
            if not found_phone and snippet_text:
                m_ph = re.search(r'(?:\+?371\s*)?[26]\d{7}', snippet_text)
                if m_ph:
                    found_phone = clean_phone_lv(m_ph.group(0))

            if found_web:
                break
    except Exception:
        pass

    return found_web, found_phone

# ==============================================================================
# LƯU DỮ LIỆU ĐỒNG BỘ & ĐẨY 100% EMAIL LÊN ĐẦU
# ==============================================================================
def save_and_reorder_master(df):
    with_email = []
    without_email = []

    for idx, row in df.iterrows():
        em = str(row.get('Email') or '').strip().lower()
        r_dict = {c: str(row.get(c) or '') for c in COLUMNS_20}
        r_dict['SĐT'] = clean_phone_lv(r_dict.get('SĐT', ''))

        if em and em != 'nan' and is_valid_email(em):
            r_dict['Check gửi'] = 'OK'
            r_dict['Email'] = em
            r_dict['Liên Hệ mail'] = f"mailto:{em}"
            with_email.append(r_dict)
        else:
            r_dict['Check gửi'] = ''
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

    out_df = pd.DataFrame(final_rows)
    TARGET_CSV_ROOT.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(TARGET_CSV_ROOT, index=False, encoding='utf-8-sig')

    TARGET_CSV_CSDL.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(TARGET_CSV_CSDL, index=False, encoding='utf-8-sig')

    stage1_file = CSDL_DIR / "LV_SWET_WEBD_1ENR.csv"
    out_df.to_csv(stage1_file, index=False, encoding='utf-8-sig')

    return len(with_email), len(final_rows)

# ==============================================================================
# HÀM ĐIỀU HÀNH CHÍNH (TIER 1 -> TIER 5)
# ==============================================================================
async def run_hybrid_enrichment(headless=False, limit=0):
    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU ĐA TẦNG - BÁNH KẸO & NƯỚC NGỌT LATVIA")
    print(f"[*] File mục tiêu chính : {TARGET_CSV_ROOT}")
    print(f"[*] Cache Checkpoint    : {CACHE_PATH}")
    print(f"[*] Trình duyệt Chrome  : {'Chạy ngầm (Headless)' if headless else 'Trực quan (Headless=False)'}")
    print("=" * 85 + "\n")

    target_file = TARGET_CSV_ROOT if TARGET_CSV_ROOT.exists() else TARGET_CSV_CSDL
    if not target_file.exists():
        print(f"[-] Không tìm thấy file: {target_file}")
        return

    df = pd.read_csv(target_file, encoding='utf-8-sig', dtype=str).fillna('')
    total_companies = len(df)

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache Checkpoint: {len(cache):,} công ty đã kiểm tra từ trước.")
        except Exception:
            cache = {}

    # Xác định danh sách cần làm giàu:
    # 1. Các công ty đã có email hợp lệ -> giữ nguyên và skip
    # 2. Các công ty CHƯA CÓ EMAIL -> đưa vào hàng đợi làm giàu chuyên sâu (dù trong cache có hay chưa có)
    target_indices = []
    already_has = 0

    for idx in df.index:
        comp = str(df.at[idx, 'Công ty']).strip()
        if is_blacklisted_company(comp):
            continue

        c_key = comp.lower()
        em = str(df.at[idx, 'Email']).strip()

        # Kiểm tra nếu trong cache đã tìm được email trước đó
        if c_key in cache and cache[c_key].get('Email'):
            cached_item = cache[c_key]
            df.at[idx, 'Email'] = cached_item['Email']
            df.at[idx, 'Liên Hệ mail'] = f"mailto:{cached_item['Email']}"
            df.at[idx, 'Check gửi'] = 'OK'
            if cached_item.get('Web') and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = cached_item['Web']
            if cached_item.get('Phone') and not str(df.at[idx, 'SĐT']).strip():
                df.at[idx, 'SĐT'] = clean_phone_lv(cached_item['Phone'])
            already_has += 1
            continue

        if em and em != 'nan' and is_valid_email(em):
            already_has += 1
            continue

        target_indices.append(idx)

    print(f"[*] Tổng số doanh nghiệp trong tệp : {total_companies:,}")
    print(f"[*] Đã có Email B2B xác thực       : {already_has:,} ({already_has/total_companies*100:.1f}%)")
    print(f"[*] CẦN TIẾP TỤC LÀM GIÀU CHUYÊN SÂU: {len(target_indices):,} công ty\n")

    if not target_indices:
        print("[✔] 100% công ty trong danh sách đã có Email đầy đủ!")
        save_and_reorder_master(df)
        return

    work_list = target_indices if limit == 0 else target_indices[:limit]
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------------------
    # BƯỚC 1: QUÉT NHANH TOÀN BỘ WEBSITE ĐÃ CÓ TRƯỚC ĐÓ ĐỂ LẤY MAIL
    # --------------------------------------------------------------------------
    print("--- [BƯỚC 1] Quét nhanh Email trên tất cả các Website đã có sẵn ---")
    step1_found = 0
    remaining_work_list = []

    for idx in work_list:
        comp = str(df.at[idx, 'Công ty']).strip()
        curr_web = str(df.at[idx, 'Liên Hệ']).strip()
        c_key = comp.lower()

        # Kiểm tra nếu trong cache có web
        if not curr_web and c_key in cache and cache[c_key].get('Web'):
            curr_web = cache[c_key]['Web']
            df.at[idx, 'Liên Hệ'] = curr_web

        if curr_web and is_valid_website(curr_web):
            dom_ok, _ = is_domain_strictly_matching(comp, curr_web)
            if not dom_ok:
                curr_web = ""
                df.at[idx, 'Liên Hệ'] = ""
                if c_key in cache:
                    cache[c_key]['Web'] = ""
                    cache[c_key]['Email'] = ""

        if curr_web and is_valid_website(curr_web):
            best_mail, best_ph = fast_scan_website_emails(curr_web)
            if best_mail:
                ok_m, _ = is_email_strictly_matching(comp, curr_web, best_mail)
                if not ok_m:
                    best_mail = ""
            if best_mail and not any(b in best_mail for b in BLACKLIST_EMAIL_DOMAINS):
                df.at[idx, 'Email'] = best_mail
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{best_mail}"
                df.at[idx, 'Check gửi'] = 'OK'
                if best_ph and not str(df.at[idx, 'SĐT']).strip():
                    df.at[idx, 'SĐT'] = clean_phone_lv(best_ph)

                # Cập nhật Cache
                if c_key not in cache:
                    cache[c_key] = {}
                cache[c_key]['Email'] = best_mail
                cache[c_key]['Web'] = curr_web
                if best_ph:
                    cache[c_key]['Phone'] = clean_phone_lv(best_ph)

                step1_found += 1
                print(f"  [WEB->EMAIL] {comp[:32]:<32} | {curr_web[:25]:<25} | EMAIL: {best_mail}")
                continue
            else:
                # Nếu mail không hợp lệ hoặc blacklist, xóa khỏi cache
                if c_key in cache:
                    cache[c_key]['Email'] = ""

        remaining_work_list.append(idx)

    print(f"[*] Bước 1 hoàn tất: Tìm thấy thêm +{step1_found} Email từ các Website có sẵn!")
    print(f"[*] Còn lại {len(remaining_work_list):,} công ty cần tra cứu Google Maps & Web Search.\n")

    # Lưu checkpoint Bước 1
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    save_and_reorder_master(df)

    if not remaining_work_list:
        print("[✔] Hoàn tất quá trình làm giàu dữ liệu!")
        return

    # --------------------------------------------------------------------------
    # BƯỚC 2: KHỞI ĐỘNG GOOGLE MAPS TRỰC QUAN + DUCKDUCKGO FALLBACK
    # --------------------------------------------------------------------------
    print("--- [BƯỚC 2] Google Maps Trực Quan & Web Search Fallback ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 800},
            locale="lv-LV",
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed = 0
        new_emails_gmap = 0
        new_webs_gmap = 0
        new_phones_gmap = 0

        for idx in remaining_work_list:
            if page.is_closed():
                try:
                    page = await browser.new_page()
                except Exception:
                    pass

            processed += 1
            comp = str(df.at[idx, 'Công ty']).strip()
            addr = str(df.at[idx, 'Địa chỉ']).strip()
            city = extract_city_lv(comp, addr)
            c_key = comp.lower()

            gmap_web = None
            gmap_phone = None
            gmap_addr = None
            found_email = ""

            print(f"[{processed:03d}/{len(remaining_work_list):03d}] {comp[:35]:<35} | ", end="", flush=True)

            search_comp = clean_company_name_for_search(comp)
            queries = []
            if city:
                queries.append(f"{search_comp} {city}")
                queries.append(f"{search_comp} Latvija")
            else:
                queries.append(f"{search_comp} Latvija")
                queries.append(f"{search_comp} Riga")

            matched = False
            for q_term in queries:
                if matched:
                    break
                url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=lv"

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=16000)

                    # Bỏ qua Consent modal
                    try:
                        consent_btn = await page.query_selector(
                            'button:has-text("Pieņemt visu"), button:has-text("Piekrītu"), '
                            'button:has-text("Accept all"), form[action*="consent"] button'
                        )
                        if consent_btn:
                            await consent_btn.click()
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    await asyncio.sleep(1.2)

                    # Kiểm tra xem Maps có mở trực tiếp trang chi tiết không
                    if "/maps/place/" in page.url:
                        h1_elem = await page.query_selector('h1.DUwDvf, h1')
                        if h1_elem:
                            t_text = await h1_elem.inner_text()
                            cat_elem = await page.query_selector('button[jsaction*="category"], button.DkEaL, .fontBodyMedium button, span.YhemCb')
                            cat_text = await cat_elem.inner_text() if cat_elem else ""
                            is_ok, _ = is_valid_name_match(comp, t_text, cat_text)
                            matched = is_ok
                    else:
                        first_card = await page.query_selector('a.hfpxzc')
                        if first_card:
                            c_aria = await first_card.get_attribute('aria-label') or ""
                            is_ok, _ = is_valid_name_match(comp, c_aria)
                            if is_ok:
                                await first_card.click()
                                await asyncio.sleep(2.0)
                                cat_elem = await page.query_selector('button[jsaction*="category"], button.DkEaL, .fontBodyMedium button, span.YhemCb')
                                cat_text = await cat_elem.inner_text() if cat_elem else ""
                                is_ok2, _ = is_valid_name_match(comp, c_aria, cat_text)
                                matched = is_ok2

                    if matched:
                        # Trích xuất Website (Đa dạng bộ chọn)
                        for sel in [
                            'a[data-item-id="authority"]',
                            'a[aria-label*="Mājaslapa"]',
                            'a[aria-label*="vietne"]',
                            'a[aria-label*="Website"]',
                            'a[data-tooltip*="vietne"]',
                            'a[data-tooltip*="Website"]'
                        ]:
                            web_btn = await page.query_selector(sel)
                            if web_btn:
                                cand_web = await web_btn.get_attribute('href')
                                if cand_web and is_valid_website(cand_web):
                                    dom_ok, _ = is_domain_strictly_matching(comp, cand_web)
                                    if dom_ok:
                                        gmap_web = cand_web
                                        break

                        # Trích xuất SĐT
                        for sel in [
                            'button[data-item-id^="phone:"]',
                            'button[aria-label*="Tālrunis"]',
                            'button[aria-label*="Phone"]',
                            'button[data-tooltip*="Tālrunis"]'
                        ]:
                            ph_btn = await page.query_selector(sel)
                            if ph_btn:
                                p_attr = await ph_btn.get_attribute('data-item-id')
                                if p_attr and p_attr.startswith('phone:tel:'):
                                    gmap_phone = p_attr.replace('phone:tel:', '').strip()
                                else:
                                    p_txt = await ph_btn.inner_text()
                                    if re.search(r'\d{3,}', p_txt):
                                        gmap_phone = p_txt.strip()
                                if gmap_phone:
                                    break

                        # Trích xuất Địa chỉ
                        addr_btn = await page.query_selector('button[data-item-id="address"]')
                        if addr_btn:
                            gmap_addr = await addr_btn.inner_text()

                except Exception:
                    pass

            # Chỉ chấp nhận website và SĐT trực tiếp từ địa điểm Google Maps đã xác thực
            # Tuyệt đối không dùng search engine đoán mò để tránh nhầm sang flashscore, chefspencil, web chính phủ...

            # ------------------------------------------------------------------
            # NẾU CÓ WEBSITE -> QUÉT EMAIL & SĐT NGAY
            # ------------------------------------------------------------------
            if gmap_web:
                # Dùng fast scan trước
                found_email, sub_phone = fast_scan_website_emails(gmap_web)
                if not found_email:
                    # Dùng Playwright quét sâu nếu fast scan chưa ra
                    found_email, sub_phone = await playwright_crawl_site_for_email(page, gmap_web)

                if found_email:
                    ok_m, _ = is_email_strictly_matching(comp, gmap_web, found_email)
                    if not ok_m:
                        found_email = ""

                if found_email and any(b in found_email for b in BLACKLIST_EMAIL_DOMAINS):
                    found_email = ""

                if sub_phone and not gmap_phone:
                    gmap_phone = sub_phone

            # Cập nhật kết quả vào DataFrame
            if gmap_web and not str(df.at[idx, 'Liên Hệ']).strip():
                df.at[idx, 'Liên Hệ'] = gmap_web
                new_webs_gmap += 1

            if gmap_phone and not str(df.at[idx, 'SĐT']).strip():
                clean_ph = clean_phone_lv(gmap_phone)
                df.at[idx, 'SĐT'] = clean_ph
                new_phones_gmap += 1

            if gmap_addr and not str(df.at[idx, 'Địa chỉ']).strip():
                df.at[idx, 'Địa chỉ'] = gmap_addr.strip()

            if found_email:
                df.at[idx, 'Email'] = found_email
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{found_email}"
                df.at[idx, 'Check gửi'] = 'OK'
                new_emails_gmap += 1
                print(f"GMAP->WEB: {gmap_web[:22]:<22} | EMAIL: {found_email}")
            elif gmap_web:
                print(f"GMAP->WEB: {gmap_web[:22]:<22} | (Chưa thấy mail)")
            elif gmap_phone:
                print(f"GMAP: {clean_phone_lv(gmap_phone):<22} | (Khớp Maps - Có SĐT)")
            elif matched:
                print(f"GMAP | (Khớp địa điểm - Không có web)")
            else:
                print(f"No match | (Không tìm thấy trên Maps/Web)")

            # Lưu vào Cache
            cache[c_key] = {
                "Web": gmap_web or (cache.get(c_key, {}).get('Web', '')),
                "Email": found_email or (cache.get(c_key, {}).get('Email', '')),
                "Phone": clean_phone_lv(gmap_phone or cache.get(c_key, {}).get('Phone', '')),
                "Address": gmap_addr or (cache.get(c_key, {}).get('Address', df.at[idx, 'Địa chỉ'])),
                "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # Lưu tăng dần sau mỗi 5 công ty
            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_mail, cur_tot = save_and_reorder_master(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {cur_mail:,}/{cur_tot:,} công ty có Email được đưa lên đầu file CSV.")

        await browser.close()

    # Lưu lần cuối cùng
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    final_emails, final_total = save_and_reorder_master(df)

    print("\n" + "=" * 85)
    print(" HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU ĐA TẦNG!")
    print(f" [*] Tổng số công ty          : {final_total:,}")
    print(f" [*] Đã bóc tách được Email   : {final_emails:,} / {final_total:,} ({final_emails/final_total*100:.1f}%)")
    print(f" [*] Email mới tìm thấy thêm  : +{step1_found + new_emails_gmap}")
    print(f" [*] Website mới tìm thấy thêm: +{new_webs_gmap}")
    print(f" [*] SĐT mới tìm thấy thêm    : +{new_phones_gmap}")
    print(f" [*] Đã lưu đồng bộ ra các tệp:")
    print(f"     - {TARGET_CSV_ROOT} (Thư mục gốc - 100% Email lên đầu)")
    print(f"     - {TARGET_CSV_CSDL}")
    print("=" * 85 + "\n")

if __name__ == '__main__':
    headless_mode = False
    limit_cnt = 0

    if len(sys.argv) > 1:
        if sys.argv[1].lower() in ['--headless', '-h', 'headless']:
            headless_mode = True
        elif sys.argv[1].isdigit():
            limit_cnt = int(sys.argv[1])

    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        limit_cnt = int(sys.argv[2])

    asyncio.run(run_hybrid_enrichment(headless=headless_mode, limit=limit_cnt))
