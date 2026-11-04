# -*- coding: utf-8 -*-
"""
BỘ CÀO & LÀM GIÀU DỮ LIỆU NÔNG NGHIỆP - TRỒNG TRỌT & CHĂN NUÔI NA UY (PROFF.NO)
-----------------------------------------------------------------------------------
Nguồn mục tiêu: https://www.proff.no/bransjes%C3%B8k?q=Jordbruk%20-%20oppdrett%20og%20husdyrhold
Quy chuẩn áp dụng:
1. Bóc tách chi tiết từng thẻ công ty (Orgnr, Tên, SĐT, Website, Email, Địa chỉ, Người quản lý, Doanh thu, Nhân sự).
2. Lưu Tag chính (Tag_Chinh), Toàn bộ Tag ngành (All_Tags) và NACE code.
3. Bộ lọc chuyên sâu loại bỏ 100% doanh nghiệp phi nông nghiệp:
   - Loại bỏ Bảo tàng & di tích (Museer og samlinger, Historiske steder og bygninger...)
   - Loại bỏ Trường học & đào tạo (Skole, Undervisning, Barnehage...)
   - Loại bỏ Dịch vụ xã hội & y tế (Sosiale tjenester, Helse, Omsorg...)
   - Loại bỏ Danh sách đen cố định (Scandi Standard, Biliarta, Daigre per GEMINI.md).
   - Chỉ giữ lại doanh nghiệp Trồng trọt (Crops) và Chăn nuôi (Livestock/Husdyrhold).
4. Tự động bóc tách và làm giàu Email B2B từ Website công ty (ưu tiên link thật trên DOM, decode Cloudflare, chấm điểm B2B).
5. Lưu tăng dần (Incremental Auto-Save) & hỗ trợ Resume 100% qua file cache JSON.
6. Xuất chuẩn tên file 17 ký tự:
   - NO_FARM_WEBD_0RAW.csv
   - NO_FARM_WEBD_2COL.csv (20 cột Cold Mail, đẩy 100% có mail lên đầu, SĐT có nháy đơn ')
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

# Tệp đầu ra theo chuẩn 17 ký tự: [CC]_[IND4]_[SRC4]_[STG4].csv
OUT_RAW_CSV = ROOT_DIR / "NO_FARM_WEBD_0RAW.csv"
OUT_2COL_CSV = ROOT_DIR / "NO_FARM_WEBD_2COL.csv"
CSDL_2COL_CSV = ROOT_DIR / "csdl_mlt" / "NO_FARM_WEBD_2COL.csv"
ARCHIVE_2COL_CSV = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_WEBD_2COL.csv"
CACHE_JSON = ROOT_DIR / "crawlmail" / "cache_proff_farm.json"

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

HEADERS_PROFF = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'nb-NO,no;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}

# Danh sách đen loại trừ triệt để loại hình phi nông nghiệp
EXCLUDED_INDUSTRIES = [
    'museer og samlinger', 'historiske steder og bygninger', 'sosiale tjenester',
    'skole', 'undervisning', 'barnehager', 'videregående', 'forskning', 'universitet',
    'helse', 'barnevern', 'omsorg', 'sykehjem',
    'hotell', 'overnatting', 'camping', 'ferie', 'reisebyrå', 'vandrerhjem',
    'teater', 'kunst', 'kultur', 'fornøyelsesparker', 'idrett', 'klubber',
    'religiøse', 'menigheter', 'kirke', 'eiendomsselskap', 'eiendomshandel',
    'eiendomsmegling', 'eiendom', 'verdipapirfond', 'bygg- og anlegg', 'anlegg',
    'konsulent', 'advokat', 'regnskap', 'revisjon'
]

EXCLUDED_NAME_KEYWORDS = [
    'museum', 'museene', 'samlinger', 'historiske', 'skole', 'videregaende',
    'barnehage', 'barnevern', 'kirke', 'menighet', 'stiftelse', 'stiftelsen',
    'eiendom', 'holding'
]

# Danh mục từ khóa hợp lệ cho Trồng trọt & Chăn nuôi
ALLOWED_AGRI_KEYWORDS = [
    # Chăn nuôi (Livestock / Husdyrhold)
    'husdyrhold', 'storfehold', 'storfe', 'melkekyr', 'kjøttfe', 'svinehold', 'svin', 'gris', 'smågris',
    'sauehold', 'sau', 'geitehold', 'geit', 'fjørfehold', 'fjørfe', 'fjorfe', 'kylling', 'kalkun',
    'eggproduksjon', 'egg', 'høns', 'rugeri', 'hestehold', 'stutteri', 'reindrift', 'biavl',
    'pelsdyr', 'kanin', 'slakteri', 'slakterier', 'avlsdyr',
    # Trồng trọt & Nông trại (Crops & Farming)
    'jordbruk', 'blandet jordbruk', 'dyrking', 'korn', 'grønnsaker', 'poteter', 'potet',
    'bær og frukt', 'fruktdyrking', 'bærdyrking', 'gartnerier', 'gartneri', 'planteskoler',
    'planteskole', 'veksthus', 'blomsterdyrking', 'fôrvekster', 'produsenter', 'kjøtt og vilt'
]

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

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
    """Chấm điểm email tối ưu theo quy chuẩn B2B Agency"""
    if not email or '@' not in email:
        return -999
    em = email.lower().strip()
    score = 0
    dom = em.split('@')[-1]
    
    # Khớp domain website (+50đ)
    if website and dom in website.lower():
        score += 50
        
    # Nhóm Nhân sự / Tuyển dụng (+50đ)
    if any(em.startswith(k) for k in ['praca@', 'kariera@', 'hr@', 'personal@', 'jobs@', 'recruitment@', 'rekruttering@', 'career@', 'jobb@']):
        score += 50
    # Nhóm Lãnh đạo điều hành / Trang trại (+45đ)
    elif any(em.startswith(k) for k in ['daglig.leder@', 'leder@', 'ceo@', 'director@', 'manager@', 'drift@', 'bonde@', 'salg@', 'sales@']):
        score += 45
    # Nhóm Liên hệ chính thức / Ban thư ký (+40đ)
    elif any(em.startswith(k) for k in ['post@', 'kontakt@', 'contact@', 'office@', 'info@', 'kontor@', 'postboks@', 'farm@', 'gard@']):
        score += 40
    # Cá nhân có tên (+25đ)
    elif '.' in em.split('@')[0]:
        score += 25
    # Webmail miễn phí (+10đ)
    elif dom in ['gmail.com', 'yahoo.com', 'hotmail.com', 'online.no']:
        score += 10
    else:
        score += 15
        
    return score

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def is_valid_agri(name, current_ind, all_tags):
    """
    Kiểm tra tính hợp lệ:
    - Loại bỏ 100% bảo tàng, trường học, dịch vụ xã hội
    - Chỉ giữ lại doanh nghiệp trồng trọt & chăn nuôi thực thụ
    """
    name_l = (name or '').lower()
    curr_l = (current_ind or '').lower()
    tags_l = ' '.join(t.lower() for t in all_tags)
    
    # 1. Hard Blacklist cố định
    if is_blacklisted_company(name):
        return False, "Hard Blacklist per GEMINI.md"
        
    # 2. Loại trừ theo ngành nghề chính (Current Industry)
    if any(ex in curr_l for ex in EXCLUDED_INDUSTRIES):
        return False, f"Loại trừ ngành chính: {current_ind}"
        
    # 3. Loại trừ theo từ khóa tên công ty
    if any(ex in name_l for ex in EXCLUDED_NAME_KEYWORDS):
        return False, f"Loại trừ tên phi nông nghiệp: {name}"
        
    # 4. Kiểm tra có ít nhất 1 tag nông nghiệp / chăn nuôi
    has_agri = any(ag in curr_l or ag in tags_l for ag in ALLOWED_AGRI_KEYWORDS)
    if not has_agri:
        return False, "Không có tag nông nghiệp/chăn nuôi phù hợp"
        
    return True, "Hợp lệ"

def decode_cloudflare_email(cf_hex):
    """Giải mã Cloudflare protected email"""
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email
    except Exception:
        return ""

def crawl_website_for_email(url):
    """Bóc tách email bản địa hóa sâu từ website công ty Na Uy"""
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
                
                # 1. Cloudflare decode
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                    em = decode_cloudflare_email(cf)
                    if em:
                        c_em = clean_email(em)
                        if c_em: found_emails.add(c_em)
                
                # 2. mailto: links trong thẻ <a>
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    if a['href'].startswith('mailto:'):
                        em = a['href'].replace('mailto:', '').split('?')[0].strip()
                        c_em = clean_email(em)
                        if c_em: found_emails.add(c_em)
                        
                # 3. Regex email
                for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html):
                    c_em = clean_email(em)
                    if c_em: found_emails.add(c_em)
                    
            if len(found_emails) >= 5:
                break
        except Exception:
            continue
            
    if not found_emails:
        return ""
        
    # Chấm điểm chọn 1 email B2B tốt nhất
    scored = sorted([(score_email_b2b(e, domain), e) for e in found_emails], key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else ""

def fetch_proff_detail(orgnr):
    """Lấy dữ liệu chi tiết công ty từ Proff.no qua API Next.js"""
    digits = re.sub(r'\D', '', str(orgnr))
    if not digits:
        return None
    url = f"https://www.proff.no/selskap/-/-/-/{digits}"
    try:
        r = requests.get(url, headers=HEADERS_PROFF, impersonate="chrome124", allow_redirects=True, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            s = soup.find('script', id='__NEXT_DATA__')
            if s:
                d = json.loads(s.string)
                c = d.get('props', {}).get('pageProps', {}).get('company', {})
                if c:
                    return c
    except Exception:
        pass
    return None

def fetch_proff_search_page(page_num):
    """Lấy danh sách thẻ công ty từ trang tìm kiếm Proff.no"""
    url = f"https://www.proff.no/bransjes%C3%B8k?q=Jordbruk%20-%20oppdrett%20og%20husdyrhold&page={page_num}"
    try:
        r = requests.get(url, headers=HEADERS_PROFF, impersonate="chrome124", timeout=12)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            s = soup.find('script', id='__NEXT_DATA__')
            if s:
                d = json.loads(s.string)
                search_store = d.get('props', {}).get('pageProps', {}).get('hydrationData', {}).get('searchStore', {})
                companies_data = search_store.get('companies', {})
                comps = companies_data.get('companies', [])
                total_pages = companies_data.get('pages', 400)
                return comps, total_pages
    except Exception as e:
        print(f"[!] Lỗi tải trang tìm kiếm {page_num}: {e}")
    return [], 400

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
    except Exception as e:
        print(f"[!] Lỗi ghi cache: {e}")

def export_cold_mail_2col(raw_records):
    """Xuất file chuẩn Cold Mail 20 cột (Đẩy 100% email lên đầu, nháy đơn SĐT)"""
    with_email = []
    without_email = []
    
    for r in raw_records:
        comp_name = r.get('Cong ty') or r.get('Ten phap ly', '')
        phone = r.get('SDT', '')
        email = r.get('Email', '')
        addr_parts = [r.get('Dia chi', ''), r.get('Ma buu dien', ''), r.get('Thanh pho', '')]
        full_addr = ', '.join([str(p).strip() for p in addr_parts if p and str(p).strip() not in ['', 'None', 'nan']])
        contact = r.get('Nguoi quan ly', '')
        role = r.get('Chuc danh', '')
        tag_main = r.get('Tag_Chinh', '')
        
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
            
    # Gộp: có Email lên trước, không có Email về sau
    final_rows = with_email + without_email
    for i, row in enumerate(final_rows, start=1):
        row['No.'] = str(i)
        
    df_out = pd.DataFrame(final_rows, columns=COLUMNS_20)
    
    # 1. Tệp gốc
    df_out.to_csv(OUT_2COL_CSV, index=False, encoding='utf-8-sig')
    
    # 2. CSDL tập trung
    CSDL_2COL_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(CSDL_2COL_CSV, index=False, encoding='utf-8-sig')
    
    # 3. Archive
    ARCHIVE_2COL_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(ARCHIVE_2COL_CSV, index=False, encoding='utf-8-sig')

def main():
    parser = argparse.ArgumentParser(description="Bộ cào & làm giàu nông nghiệp Na Uy (Proff.no)")
    parser.add_argument('--start-page', type=int, default=1, help="Trang bắt đầu (mặc định 1)")
    parser.add_argument('--max-pages', type=int, default=400, help="Số trang tối đa (mặc định 400)")
    parser.add_argument('--concurrency', type=int, default=8, help="Số luồng đồng thời (mặc định 8)")
    parser.add_argument('--enrich-web', action='store_true', default=True, help="Tự động bóc tách email từ website công ty")
    args = parser.parse_args()

    print("=" * 80)
    print(" BỘ CÀO & LÀM GIÀU DOANH NGHIỆP NÔNG NGHIỆP - TRỒNG TRỌT & CHĂN NUÔI NA UY")
    print(" NGUỒN: https://www.proff.no/bransjes%C3%B8k?q=Jordbruk%20-%20oppdrett%20og%20husdyrhold")
    print(f" THIẾT LẬP: Trang {args.start_page} -> {args.max_pages} | Luồng: {args.concurrency}")
    print("=" * 80)

    cache = load_cache()
    print(f"[+] Đã tải cache lịch sử: {len(cache):,} doanh nghiệp.")

    # Danh sách kết quả cuối cùng (được lưu tăng dần)
    saved_records = []
    seen_orgnrs = set()

    # Nạp dữ liệu cũ nếu đã tồn tại để tiếp tục
    if OUT_RAW_CSV.exists():
        try:
            df_old = pd.read_csv(OUT_RAW_CSV, encoding='utf-8-sig', dtype=str).fillna('')
            for _, r in df_old.iterrows():
                o = r.get('Orgnr', '').strip()
                if o:
                    seen_orgnrs.add(o)
                    saved_records.append(r.to_dict())
            print(f"[+] Nạp thành công {len(saved_records):,} bản ghi đã cào từ trước.")
        except Exception as e:
            print(f"[!] Lỗi đọc tệp cũ: {e}")

    total_pages = args.max_pages

    for p in range(args.start_page, total_pages + 1):
        print(f"\n--- [TRANG {p}/{total_pages}] Đang tải danh sách công ty từ Proff.no ---")
        comps, max_p = fetch_proff_search_page(p)
        if max_p and max_p < total_pages:
            total_pages = max_p

        if not comps:
            print(f"[!] Trang {p} không có kết quả hoặc gặp lỗi mạng. Thử lại sau.")
            time.sleep(2)
            continue

        print(f"[*] Trang {p}: Nhận được {len(comps)} thẻ công ty. Đang bóc tách chi tiết & lọc dữ liệu...")

        # Danh sách cần lấy chi tiết
        items_to_fetch = []
        for c in comps:
            orgnr = c.get('orgnr')
            if orgnr and orgnr not in cache:
                items_to_fetch.append(c)

        # Lấy chi tiết đồng thời với ThreadPoolExecutor
        if items_to_fetch:
            with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
                future_map = {ex.submit(fetch_proff_detail, c['orgnr']): c for c in items_to_fetch}
                for f in as_completed(future_map):
                    base_c = future_map[f]
                    orgnr = base_c['orgnr']
                    try:
                        detail = f.result()
                        if detail:
                            cache[orgnr] = detail
                        else:
                            cache[orgnr] = base_c # Fallback
                    except Exception:
                        cache[orgnr] = base_c

            save_cache(cache)

        # Xử lý & Phân loại từng công ty trên trang này
        new_valid_count = 0
        new_excluded_count = 0

        for c in comps:
            orgnr = c.get('orgnr')
            if not orgnr or orgnr in seen_orgnrs:
                continue

            info = cache.get(orgnr, c)
            name = info.get('name') or c.get('name', '')
            legal_name = info.get('legalName') or c.get('legalName', '')

            # Lấy thông tin tags & industry
            curr_ind_obj = info.get('currentIndustry') or {}
            curr_ind = curr_ind_obj.get('name', '') if isinstance(curr_ind_obj, dict) else str(curr_ind_obj)
            
            inds_list = info.get('industries') or []
            all_tags = [i.get('name') for i in inds_list if isinstance(i, dict) and i.get('name')]
            if not all_tags:
                all_tags = [curr_ind] if curr_ind else ['Jordbruk']

            nace_list = info.get('naceIndustries') or []

            # ÁP DỤNG BỘ LỌC NGHIÊM NGẶT
            is_ok, reason = is_valid_agri(name, curr_ind, all_tags)
            if not is_ok:
                new_excluded_count += 1
                # print(f"  [LOẠI] {name[:30]:<30} -> {reason}")
                continue

            # Doanh nghiệp hợp lệ -> Bóc tách đầy đủ
            phone = clean_phone_no(info.get('phone') or info.get('mobile') or c.get('phone'))
            web = str(info.get('homePage') or '').strip()
            if web.lower() in ['none', 'nan', '-']: web = ''
            
            # Email trực tiếp trên Proff
            email = clean_email(info.get('email'))
            # Nếu Proff chưa có mail mà có contactPersons -> lấy mail người liên hệ
            if not email:
                cp_list = info.get('contactPersons') or []
                for cp in cp_list:
                    if isinstance(cp, dict) and cp.get('email'):
                        em_c = clean_email(cp['email'])
                        if em_c:
                            email = em_c
                            break

            # Nếu có website mà chưa có email -> quét sâu website công ty
            if not email and web and args.enrich_web:
                web_em = crawl_website_for_email(web)
                if web_em:
                    email = web_em

            # Địa chỉ
            addr_obj = info.get('postalAddress') or info.get('visitorAddress') or c.get('postalAddress') or {}
            addr_line = str(addr_obj.get('addressLine') or '').strip() if isinstance(addr_obj, dict) else ''
            zip_code = str(addr_obj.get('zipCode') or '').strip() if isinstance(addr_obj, dict) else ''
            post_place = str(addr_obj.get('postPlace') or '').strip() if isinstance(addr_obj, dict) else ''
            
            loc_obj = info.get('location') or {}
            county = str(loc_obj.get('county') or '').strip() if isinstance(loc_obj, dict) else ''

            # Người quản lý
            cp_obj = info.get('contactPerson') or {}
            leader = cp_obj.get('name', '') if isinstance(cp_obj, dict) else ''
            role = cp_obj.get('role', '') if isinstance(cp_obj, dict) else ''

            revenue = info.get('revenue', '')
            employees = info.get('employees', '')
            found_year = info.get('foundationYear', '')

            rec = {
                'No.': str(len(saved_records) + 1),
                'Orgnr': orgnr,
                'Cong ty': name,
                'Ten phap ly': legal_name,
                'SDT': phone,
                'Email': email,
                'Website': web,
                'Dia chi': addr_line,
                'Ma buu dien': zip_code,
                'Khu vuc': county,
                'Thanh pho': post_place,
                'Tag_Chinh': curr_ind,
                'All_Tags': ' | '.join(all_tags),
                'NACE': ' | '.join(nace_list),
                'Nguoi quan ly': leader,
                'Chuc danh': role,
                'Doanh thu': revenue,
                'So nhan vien': employees,
                'Nam thanh lap': found_year,
                'Proff URL': f"https://www.proff.no/selskap/-/-/-/{orgnr}"
            }

            saved_records.append(rec)
            seen_orgnrs.add(orgnr)
            new_valid_count += 1

            status_mail = f" [MAIL: {email}]" if email else ""
            status_web = f" [WEB: {web}]" if web else ""
            print(f"  [OK] {name[:32]:<32} | Tag: {curr_ind[:20]:<20}{status_mail}{status_web}")

        print(f"[+] Hoàn tất Trang {p}: Giữ lại {new_valid_count} cty hợp lệ, Loại bỏ {new_excluded_count} cty phi nông nghiệp.")

        # LƯU TĂNG DẦN (INCREMENTAL SAVE) VÀO CẢ 2 ĐỊNH DẠNG CSV
        df_raw = pd.DataFrame(saved_records, columns=COLUMNS_RAW)
        df_raw.to_csv(OUT_RAW_CSV, index=False, encoding='utf-8-sig')
        export_cold_mail_2col(saved_records)

        time.sleep(1)

    print("\n" + "=" * 80)
    print(f" HOÀN TẤT CÀO DỮ LIỆU NÔNG NGHIỆP NA UY!")
    print(f" Tổng số doanh nghiệp đạt chuẩn (Trồng trọt & Chăn nuôi): {len(saved_records):,}")
    with_em_total = len([r for r in saved_records if r.get('Email')])
    print(f" Tổng số doanh nghiệp có Email: {with_em_total:,}")
    print(f" File RAW 17 ký tự: {OUT_RAW_CSV.name}")
    print(f" File Cold Mail 20 cột (Đã đẩy email lên đầu): {OUT_2COL_CSV.name}")
    print("=" * 80)

if __name__ == '__main__':
    main()
