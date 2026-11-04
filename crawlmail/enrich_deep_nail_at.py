# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO SÂU & LÀM GIÀU EMAIL CHUYÊN BIỆT CHO TIỆM NAIL ÁO (AT_NAIL)
=============================================================================
Thị trường: Áo (Austria - AT)
Mục tiêu: Cào kĩ hơn toàn bộ các tiệm nail chưa có email trong AT_NAIL_GMAP_2COL.csv

Kiến trúc bóc tách 3 tầng chuyên sâu:
1. TẦNG 1: Quét sâu Website chính thức (Deep Website Crawling):
   - Ưu tiên bóc tách các trang pháp lý bắt buộc của Áo (§ 5 ECG):
     /impressum, /impressum/, /kontakt, /kontakt/, /contact, /ueber-uns, /ueber-mich, /team...
   - Giải mã Cloudflare Email Protection (data-cfemail).
   - Giải mã Obfuscated Email (info [at] domain [dot] at).
   - Bóc tách toàn diện thẻ <a href="mailto:..."> và Regex trong toàn bộ DOM.
   - Lọc bỏ 100% email rác, demo, hosting (webador, beispiel, ivof, chilly, netports...).
   - Chấm điểm chọn DUY NHẤT 1 email tối ưu nhất (ưu tiên @domain.at, office@, info@, kontakt@...).
2. TẦNG 2: Khám phá Website tự động (Strict Web Discovery Search):
   - Đối với các tiệm thiếu website trên Google Maps hoặc chỉ có link MXH, tìm kiếm trên DuckDuckGo.
   - So khớp tên nghiêm ngặt (Rule 11): Chỉ chấp nhận tên miền trùng ít nhất 1 từ định danh riêng của tiệm.
   - Lọc bỏ danh bạ trung gian (treatwell, herold, firmenabc, wko, gelbeseiten, yelp...).
   - Quét trang chủ và trang Impressum của website vừa tìm được để lấy email.
3. QUY CHUẨN AN TOÀN & BẢN QUYỀN:
   - Giữ nguyên 100% các email đã có hợp lệ từ trước.
   - SĐT luôn có dấu nháy đơn ('+43...).
   - Lưu tăng dần (Incremental Checkpoint) sau mỗi 5 công ty & Cache JSON để Resume 100%.
   - Luôn đẩy 100% tiệm có email lên các dòng đầu tiên (dòng 1..N).
   - Xuất đồng bộ ra cả AT_NAIL_GMAP_2COL.csv và AT_NAIL_ONLY_EMAILS_READY.csv.
   - Rule 12: Loại trừ vĩnh viễn blacklist companies.
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
import curl_cffi.requests as requests
import pandas as pd

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_MASTER_CSV = ROOT_DIR / "AT_NAIL_GMAP_2COL.csv"
OUTPUT_READY_CSV = ROOT_DIR / "AT_NAIL_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_deep_nail_at.json"

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico', '.mp4')

JUNK_EMAIL_DOMAINS = {
    'example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io',
    'wixpress.com', 'wordpress.com', 'webador.de', 'webador.com', 'beispiel.de',
    'ivof.com', 'chilly.domains', 'netports.at', 'jimdofree.com', 'squarespace.com',
    'world4you.com', 'ionos.de', 'strato.de'
}

JUNK_USERNAMES = {
    'support', 'webador', 'mustermann', 'example', 'sample', 'youremail',
    'your-email', 'someone', 'nobody', 'user', 'name', 'john.doe', 'privacy',
    'gdpr', 'abuse', 'postmaster', 'hostmaster', 'admin', 'mailer-daemon',
    'datenschutz', 'noreply', 'no-reply', 'donotreply'
}

AGGREGATOR_DOMAINS = {
    'treatwell', 'facebook.com', 'fb.com', 'instagram.com', 'herold.at', 'firmenabc.at', 'wko.at',
    'gelbeseiten', 'yelp', 'cylex', 'tupalo', 'fyle', 'google.com', 'youtube.com',
    'linkedin.com', 'pinterest.com', 'tiktok.com', 'twitter.com', 'x.com', 'ivof.com', 'tripadvisor',
    'firmania.at', 'sabisu.org', 'findglocal.com', 'beautynailhairsalons.com', 'cybo.com',
    'infobel.com', 'stadtbranchenbuch.at', 'yellowmap.at'
}

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigrė'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()

    # Cắt phần nối chuỗi website/SĐT dính liền
    em = re.sub(r'(\.[a-z]{2,6})www\..*$', r'\1', em, flags=re.I)
    em = re.sub(r'(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$', r'\1', em, flags=re.I)

    if not re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""

    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return ""
    if u in JUNK_USERNAMES or any(k in u for k in ['mustermann', 'youremail', 'your-email']):
        return ""
    if any(em.endswith(ext) for ext in INVALID_EXTS):
        return ""

    return em

def decode_cloudflare(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return clean_email(email)
    except Exception:
        return ""

def score_email_at(email, domain=""):
    e = clean_email(email)
    if not e:
        return -1
    u, d = e.split('@', 1)
    score = 10

    clean_dom = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50
    elif d.endswith('.at'):
        score += 25
    elif d.endswith('.de') or d.endswith('.eu'):
        score += 15

    # Ưu tiên các hộp thư đại diện & điều hành chính thức của salon
    if any(u == k or u.startswith(k) for k in ['office', 'kontakt', 'contact', 'info', 'salon', 'studio', 'termin', 'termine', 'buchung', 'anfrage', 'nail', 'nagel']):
        score += 40
    elif any(u == k or u.startswith(k) for k in ['chefin', 'inhaber', 'geschäftsführung', 'geschaeftsfuehrung', 'leitung', 'management', 'direktion']):
        score += 45
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'gmx.at', 'aon.at', 'yahoo.de', 'hotmail.com']:
        score += 10

    return score

def select_best_email(emails, domain=""):
    valid = [clean_email(e) for e in emails if clean_email(e)]
    valid = [e for e in set(valid) if score_email_at(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_at(e, domain))

def fetch_html(url, timeout=4):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }
    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=timeout, verify=False, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

def extract_emails_from_page(html_text, domain=""):
    found = set()
    if not html_text:
        return found

    # 1. Cloudflare decode
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare(cf)
        if dec:
            found.add(dec)

    # 2. mailto: links
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = clean_email(m)
        if clean_m:
            found.add(clean_m)

    # 3. Standard Regex
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = clean_email(m)
        if clean_m:
            found.add(clean_m)

    # 4. Obfuscated patterns (info [at] domain.at / info(at)domain.at / &#64;)
    obf_patterns = [
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*(?:\[at\]|\(at\)|\s+at\s+)\s*([a-zA-Z0-9.-]{1,50})\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*([a-zA-Z]{2,10})', re.I),
        re.compile(r'([a-zA-Z0-9._%+-]{1,50})\s*&#64;\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,10})', re.I)
    ]
    for pat in obf_patterns:
        for match in pat.findall(html_text):
            if len(match) == 3:
                cand = clean_email(f"{match[0]}@{match[1]}.{match[2]}")
                if cand:
                    found.add(cand)
            elif len(match) == 2:
                cand = clean_email(f"{match[0]}@{match[1]}")
                if cand:
                    found.add(cand)

    return found

def crawl_salon_website(website_url):
    """Quét trang chủ và các trang con trọng điểm (/impressum, /kontakt...) của tiệm nail Áo"""
    if not website_url or not isinstance(website_url, str):
        return ""
    u_str = website_url.strip()
    if not u_str.startswith(('http://', 'https://')):
        u_str = 'https://' + u_str

    try:
        domain_parsed = urllib.parse.urlparse(u_str)
        base_origin = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
        domain = domain_parsed.netloc.lower().replace('www.', '')
    except Exception:
        return ""

    if any(ag in domain for ag in AGGREGATOR_DOMAINS):
        return ""

    all_emails = set()

    # 1. Quét trang chủ (Fast failover nếu chết)
    home_html = fetch_html(u_str, timeout=4)
    if not home_html:
        # Thử đổi http sang https hoặc ngược lại
        alt_url = u_str.replace('http://', 'https://') if u_str.startswith('http://') else u_str.replace('https://', 'http://')
        home_html = fetch_html(alt_url, timeout=3)
        if home_html:
            u_str = alt_url
            domain_parsed = urllib.parse.urlparse(u_str)
            base_origin = f"{domain_parsed.scheme}://{domain_parsed.netloc}"
        else:
            # Domain chết hoàn toàn -> Bỏ qua ngay lập tức để tiết kiệm 30s
            return ""

    all_emails.update(extract_emails_from_page(home_html, domain))
    best = select_best_email(all_emails, domain)
    # Nếu homepage đã có email domain riêng chuẩn -> chỉ quét thêm Impressum nếu cần
    if best and score_email_at(best, domain) >= 60:
        return best

    # 2. Tìm link thật trên DOM menu (Priority 10)
    candidate_links = []
    sub_keywords = [
        'impressum', 'kontakt', 'contact', 'ueber-uns', 'ueber-mich',
        'uber-uns', 'team', 'about', 'termine', 'buchung'
    ]

    try:
        soup = BeautifulSoup(home_html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            href_lower = href.lower()
            text_lower = (a.get_text() or "").strip().lower()

            if any(k in href_lower or k in text_lower for k in sub_keywords):
                full_url = urllib.parse.urljoin(u_str, href).split('#')[0]
                if urllib.parse.urlparse(full_url).netloc == domain_parsed.netloc:
                    candidate_links.append((10, full_url))
    except Exception:
        pass

    # 3. Đoán đường dẫn pháp lý bắt buộc của Áo (§ 5 ECG) (Priority 5)
    guess_paths = [
        '/impressum', '/impressum/', '/impressum.html',
        '/kontakt', '/kontakt/', '/kontakt.html', '/contact'
    ]
    for gp in guess_paths:
        candidate_links.append((5, f"{base_origin.rstrip('/')}{gp}"))

    # Sắp xếp và lấy tối đa 5 trang con duy nhất
    candidate_links.sort(key=lambda x: x[0], reverse=True)
    unique_subs = []
    seen_subs = {u_str.rstrip('/')}
    for prio, s_url in candidate_links:
        clean_s = s_url.rstrip('/')
        if clean_s not in seen_subs:
            seen_subs.add(clean_s)
            unique_subs.append(s_url)
            if len(unique_subs) >= 5:
                break

    # Quét từng trang con
    for sub_url in unique_subs:
        sub_html = fetch_html(sub_url, timeout=3)
        if sub_html:
            emails = extract_emails_from_page(sub_html, domain)
            all_emails.update(emails)
            best = select_best_email(all_emails, domain)
            if best and score_email_at(best, domain) >= 60:
                return best

    return select_best_email(all_emails, domain)

def is_domain_matching_salon(domain, salon_name):
    """
    So khớp thông minh & nghiêm ngặt (Rule 11):
    Chỉ chấp nhận website khám phá nếu tên miền chứa từ khóa định danh riêng của tiệm.
    """
    if not domain or not salon_name:
        return False
    norm_name = unicodedata.normalize('NFKD', salon_name).lower()
    clean_name = ''.join(c for c in norm_name if not unicodedata.combining(c))
    
    # Loại bỏ các từ chung phổ biến
    stop_words = {
        'nagelstudio', 'nageldesign', 'nagel', 'studio', 'nails', 'nail', 'beauty',
        'austria', 'wien', 'linz', 'graz', 'salzburg', 'innsbruck', 'klagenfurt',
        'villach', 'wels', 'st', 'pölten', 'dornbirn', 'und', '&', 'by', 'art',
        'wellness', 'kosmetik', 'cosmetics', 'lounge', 'bar'
    }
    tokens = [w for w in re.split(r'[\s\-_.,/()]+', clean_name) if len(w) >= 3 and w not in stop_words]
    
    clean_dom = domain.lower().replace('www.', '').split('.')[0]
    # Kiểm tra xem có token riêng nào xuất hiện trong domain không
    return any(tok in clean_dom for tok in tokens)

def search_website_duckduckgo(company_name, city=""):
    """Tìm website chính thức qua DuckDuckGo kèm kiểm tra trùng khớp tên nghiêm ngặt"""
    clean_name = re.sub(r'["\'„“”«»]', '', company_name).strip()
    query = f"{clean_name} {city} Nagelstudio Austria"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

    html = fetch_html(url, timeout=5)
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', class_='result__url')[:5]:
            raw_link = a.get_text().strip()
            if not raw_link.startswith(('http://', 'https://')):
                raw_link = 'https://' + raw_link

            domain = urllib.parse.urlparse(raw_link).netloc.lower().replace('www.', '')
            if any(ag in domain for ag in AGGREGATOR_DOMAINS):
                continue
            
            # Rule 11: So khớp nghiêm ngặt
            if is_domain_matching_salon(domain, company_name):
                return raw_link
    except Exception:
        pass

    return ""

def safe_to_csv(df, target_path, encoding="utf-8-sig"):
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(target_path, index=False, encoding=encoding)
    except PermissionError:
        tmp_path = target_path.with_name(f"{target_path.stem}_updated{target_path.suffix}")
        try:
            df.to_csv(tmp_path, index=False, encoding=encoding)
            print(f"  [!] Lưu ý: {target_path.name} đang mở bởi ứng dụng khác. Đã lưu bản mới nhất vào {tmp_path.name}")
        except Exception:
            pass
    except Exception as e:
        print(f"[-] Lỗi ghi file {target_path.name}: {e}")

def save_all_destinations(df_current):
    """Lưu tăng dần và tự động phân loại đẩy 100% email lên dòng đầu tiên"""
    # Lọc bỏ blacklist (Rule 12)
    df_current = df_current[~df_current['Công ty'].apply(is_blacklisted)].copy()

    has_em = df_current[df_current['Email'].str.contains('@', na=False)].copy()
    no_em = df_current[~df_current['Email'].str.contains('@', na=False)].copy()

    # Chuẩn hóa SĐT luôn có dấu nháy đơn
    has_em['SĐT'] = has_em['SĐT'].apply(clean_phone)
    no_em['SĐT'] = no_em['SĐT'].apply(clean_phone)

    # Khử trùng email trên tập có email (giữ dòng đầu tiên)
    has_em['clean_em'] = has_em['Email'].str.lower().str.strip()
    has_em = has_em.drop_duplicates(subset=['clean_em'], keep='first').copy()
    has_em.drop(columns=['clean_em'], inplace=True, errors='ignore')

    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted['Check gửi'] = df_sorted['Email'].apply(lambda x: 'Chưa gửi' if x else '')
    df_sorted['Liên Hệ mail'] = df_sorted['Email'].apply(lambda x: f"mailto:{x}" if x else '')

    # 1. Xuất AT_NAIL_ONLY_EMAILS_READY.csv (chỉ gồm các dòng có email)
    ready_df = has_em.copy()
    ready_df['No.'] = range(1, len(ready_df) + 1)
    ready_df['Check gửi'] = 'Chưa gửi'
    ready_df['Liên Hệ mail'] = ready_df['Email'].apply(lambda x: f"mailto:{x}" if x else '')

    ready_paths = [
        OUTPUT_READY_CSV,
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_ONLY_EMAILS_READY.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_ONLY_EMAILS_READY.csv"
    ]
    for rp in ready_paths:
        safe_to_csv(ready_df, rp, encoding="utf-8-sig")

    # 2. Xuất AT_NAIL_GMAP_2COL.csv (tổng thể)
    master_paths = [
        INPUT_MASTER_CSV,
        ROOT_DIR / "data" / "formatted" / "AT_NAIL_GMAP_2COL.csv",
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_GMAP_2COL.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_GMAP_2COL.csv"
    ]
    for mp in master_paths:
        safe_to_csv(df_sorted, mp, encoding="utf-8-sig")

    return len(ready_df)

def run_deep_enrichment(limit=0):
    print("=" * 75)
    print("  KHỞI ĐỘNG HỆ THỐNG CÀO SÂU & LÀM GIÀU EMAIL TIỆM NAIL ÁO (AT_NAIL)")
    print(f"  Tệp nguồn: {INPUT_MASTER_CSV.name}")
    print("=" * 75)

    if not INPUT_MASTER_CSV.exists():
        print(f"[!] Lỗi: Không tìm thấy file {INPUT_MASTER_CSV}!")
        return

    # Đọc tệp master hiện có
    with open(INPUT_MASTER_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Đã nạp {len(rows):,} tiệm nail từ tệp master.")

    # Đọc cache checkpoint JSON
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp checkpoint cache: {len(cache):,} tiệm đã xử lý từ trước.")
        except Exception as e:
            print(f"[-] Lỗi nạp cache: {e}")

    initial_email_count = sum(1 for r in rows if r.get('Email', '').strip())
    print(f"[*] Số tiệm đã có Email hợp lệ ban đầu: {initial_email_count:,}")

    # Lọc danh sách cần quét sâu (chỉ quét các tiệm CHƯA CÓ EMAIL)
    # Ưu tiên các tiệm đã có website trực tiếp trước!
    direct_web_indices = []
    other_indices = []

    for idx, r in enumerate(rows):
        if not r.get('Email', '').strip():
            web = r.get('Liên Hệ', '').strip().lower()
            if web.startswith('http') and not any(ag in web for ag in AGGREGATOR_DOMAINS):
                direct_web_indices.append(idx)
            else:
                other_indices.append(idx)

    # Ghép danh sách: Quét 199 tiệm có sẵn website trước, sau đó quét các tiệm còn lại
    to_scan_indices = direct_web_indices + other_indices

    print(f"[*] Số tiệm có Website riêng cần cào sâu: {len(direct_web_indices):,}")
    print(f"[*] Số tiệm chưa có website cần khám phá: {len(other_indices):,}")
    print(f"[*] Tổng số tiệm cần cào: {len(to_scan_indices):,}")

    if limit > 0:
        to_scan_indices = to_scan_indices[:limit]
        print(f"[*] Giới hạn quét: {len(to_scan_indices)} tiệm.")

    new_emails_found = 0
    new_webs_found = 0
    processed_count = 0

    for step_num, idx in enumerate(to_scan_indices, 1):
        row = rows[idx]
        company = row.get('Công ty', '').strip()
        address = row.get('Địa chỉ', '').strip()
        website = row.get('Liên Hệ', '').strip()
        phone = row.get('SĐT', '').strip()

        # Trích xuất thành phố từ địa chỉ nếu có
        city_match = re.search(r'\b\d{4}\s+([A-Za-zÄÖÜäöüß\s\-]+)', address)
        city = city_match.group(1).strip() if city_match else ""

        cache_key = f"{company.lower()}_{city.lower()}".strip("_")

        # 1. Kiểm tra cache
        if cache_key in cache:
            cached_data = cache[cache_key]
            c_email = cached_data.get('email', '')
            c_web = cached_data.get('website', '')
            if c_email and not row.get('Email'):
                row['Email'] = c_email
                new_emails_found += 1
            if c_web and not row.get('Liên Hệ'):
                row['Liên Hệ'] = c_web
            processed_count += 1
            continue

        found_email = ""
        found_website = ""

        # TẦNG 1: Quét sâu Website nếu tiệm đã có link web riêng
        if website and not any(ag in website.lower() for ag in AGGREGATOR_DOMAINS):
            found_email = crawl_salon_website(website)

        # TẦNG 2: Nếu chưa có website hoặc chưa tìm thấy email -> Tìm kiếm qua DuckDuckGo kèm đối chiếu tên
        if not found_email and (not website or any(ag in website.lower() for ag in AGGREGATOR_DOMAINS)):
            discovered_web = search_website_duckduckgo(company, city)
            if discovered_web:
                found_website = discovered_web
                found_email = crawl_salon_website(discovered_web)

        # Cập nhật kết quả vào bản ghi
        if found_email:
            row['Email'] = found_email
            new_emails_found += 1
            log_em = f"✨ {found_email}"
        else:
            log_em = "Không có"

        if found_website and not row.get('Liên Hệ'):
            row['Liên Hệ'] = found_website
            new_webs_found += 1
            log_wb = f"Web mới: {found_website[:25]}"
        else:
            log_wb = f"Web: {website[:25]}" if website else "Web: -"

        # Lưu cache
        cache[cache_key] = {
            'email': found_email,
            'website': found_website or website,
            'updated_at': time.strftime("%Y-%m-%d %H:%M:%S")
        }

        processed_count += 1
        print(f"[{processed_count:03d}/{len(to_scan_indices):03d}] {company[:26]:<26} | {city[:12]:<12} | {log_em:<35} | {log_wb}", flush=True)

        # Tự động lưu tăng dần mỗi 5 tiệm (Rule 5)
        if processed_count % 5 == 0:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            
            df_temp = pd.DataFrame(rows)
            cur_ready = save_all_destinations(df_temp)
            print(f"  >>> [AUTO-SAVE] Checkpoint đã lưu: Hiện có {cur_ready:,} tiệm có email trên dòng 1..N.", flush=True)

        time.sleep(0.1)

    # Lưu lần cuối
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    df_final = pd.DataFrame(rows)
    final_ready = save_all_destinations(df_final)

    print("\n" + "=" * 75)
    print("  HOÀN THÀNH CHIẾN DỊCH CÀO SÂU EMAIL TIỆM NAIL ÁO!")
    print(f"  - Số tiệm đã xử lý đợt này      : {processed_count:,}")
    print(f"  - EMAIL B2B MỚI BỔ SUNG        : +{new_emails_found:,}")
    print(f"  - Website mới khám phá         : +{new_webs_found:,}")
    print(f"  - TỔNG SỐ TIỆM CÓ EMAIL ĐẦY ĐỦ : {final_ready:,} (Tăng từ {initial_email_count:,})")
    print(f"  - File Cold Mail sẵn sàng gửi  : {OUTPUT_READY_CSV.name}")
    print(f"  - File Master 2COL cập nhật    : {INPUT_MASTER_CSV.name}")
    print("=" * 75 + "\n")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Deep Email Scraper for Austria Nail Salons")
    parser.add_argument('--limit', type=int, default=0, help="Giới hạn số tiệm quét (0 = toàn bộ)")
    args = parser.parse_args()

    run_deep_enrichment(limit=args.limit)
