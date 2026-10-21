# -*- coding: utf-8 -*-
"""
Smart Enrichment Pipeline for Slovak Automotive Factories (SK_AUTO_SLVD):
Giai đoạn 1: Làm giàu chéo đa nguồn (Cross-Source Enrichment) từ toàn bộ dữ liệu sẵn có trong workspace:
  - Khớp theo IČO (độ tin cậy 100%).
  - Khớp theo Tên doanh nghiệp chuẩn hóa (loại bỏ legal forms s.r.o., a.s., k.s. và dấu tiếng Slovak) + Thành phố.
  - Phân tích chấm điểm Heuristic B2B (score_email_b2b) chọn duy nhất 1 email có giá trị cao nhất cho tuyển dụng / môi giới lao động.
  - Chuẩn hóa SĐT với dấu nháy đơn `'`.
Giai đoạn 2: Quét Google Maps & Deep Web cho các nhà máy còn lại chưa có thông tin:
  - headless=False để theo dõi trực quan.
  - Tự động bóc tách SĐT, Website, quét subpages (/kontakt, /kariera, /o-nas...).
  - Checkpoint JSON liên tục (Resume 100%).
"""

import sys
import os
import re
import csv
import json
import glob
import urllib.parse
import unicodedata
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
SLVD_RAW_CSV = ROOT_DIR / "SK_AUTO_SLVD_0RAW.csv"
SLVD_ENR_CSV = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
CACHE_JSON = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json"

LEGAL_FORMS = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'inc.', 'v likvidacii', 'v konkurze'
]

GARBAGE_EMAILS = {
    'example@example.com', 'domain@domain.com', 'email@email.com',
    'admin@admin.com', 'test@test.com', 'info@domain.com',
    'kontakt@domain.com', 'office@domain.com', 'yourname@domain.com',
    'youremail@domain.com', 'someone@domain.com', 'john.doe@domain.com',
    'name@domain.com', 'sentry@wix.com', 'user@domain.com'
}

def remove_accents(s):
    if not s:
        return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def clean_company_name(n):
    if not n:
        return ''
    n = remove_accents(n).lower()
    n = re.sub(r'[\"\'„“”«»]', '', n).strip()
    for lf in sorted(LEGAL_FORMS, key=len, reverse=True):
        pattern = rf'(?:^|[\s,;]){re.escape(lf)}(?:$|[\s,;])'
        n = re.sub(pattern, ' ', n)
    n = re.sub(r'\b(s\s*r\s*o|a\s*s|k\s*s|v\s*o\s*s)\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

def clean_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    # Lọc bỏ unicode icon glyphs và newline
    p = re.sub(r'[\ue000-\uf8ff\r\n\t]', ' ', p)
    p = re.sub(r'\s+', ' ', p).strip()
    p = p.lstrip("'").strip()
    if p:
        return f"'{p}"
    return ""

def score_email_b2b(email, website=""):
    """
    Chấm điểm email tối ưu cho B2B Manpower Agency (Cung ứng lao động):
    - HR / Tuyển dụng: +50
    - Ban Giám Đốc / Lãnh đạo: +45
    - Cổng liên hệ chính thức: +40
    - Trùng domain website: +50
    - Loại bỏ tuyệt đối email rác/template.
    """
    if not email or '@' not in email:
        return 0
    em = email.strip().lower()
    if em in GARBAGE_EMAILS:
        return 0

    parts = em.split('@')
    if len(parts) != 2:
        return 0
    u, d = parts

    # Bỏ qua các email developer, theme, no-reply
    if any(k in em for k in ['no-reply', 'noreply', 'donotreply', 'privacy@', 'gdpr@', 'wixpress', 'sentry']):
        return 0
    if any(k in em for k in ['example.com', 'wix.com', 'squarespace.com', 'wordpress.org']):
        return 0

    score = 10

    # Khớp domain
    if website:
        parsed = urllib.parse.urlparse(website)
        w_domain = parsed.netloc.lower().replace('www.', '')
        if w_domain and (w_domain in d or d in w_domain):
            score += 50

    # 1. Nhân sự / Tuyển dụng (+50đ)
    if any(k in u for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']):
        score += 50
    # 2. Ban giám đốc / Quản lý (+45đ)
    elif any(k in u for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # 3. Cổng thông tin chính thức (+40đ)
    elif any(k in u for k in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia']):
        score += 40
    # 4. Email đích danh cá nhân theo domain riêng (+25đ)
    elif '.' in u and d not in ['gmail.com', 'azet.sk', 'zoznam.sk', 'centrum.sk', 'post.sk']:
        score += 25
    # 5. Webmail miễn phí (+10đ)
    elif d in ['gmail.com', 'azet.sk', 'zoznam.sk', 'centrum.sk', 'post.sk']:
        score += 10
    # 6. Kỹ thuật / Kế toán (+5đ)
    elif any(k in u for k in ['support', 'admin', 'servis', 'faktury']):
        score += 5

    return score

def select_best_email(email_candidates, website=""):
    valid = []
    for em in email_candidates:
        if not em:
            continue
        # Tách nhiều email nếu có dấu phẩy hoặc chấm phẩy
        spl = re.split(r'[,;\s]+', str(em))
        for item in spl:
            item = item.strip().strip("'\"<>").lower()
            sc = score_email_b2b(item, website)
            if sc > 0:
                valid.append((item, sc))
    if not valid:
        return ""
    # Trả về email có điểm số cao nhất
    valid.sort(key=lambda x: x[1], reverse=True)
    return valid[0][0]

def cross_enrich():
    print("=" * 70)
    print(" BƯỚC 1: LÀM GIÀU CHÉO TỪ TOÀN BỘ CÁC NGUỒN CÓ SẴN TRONG WORKSPACE")
    print("=" * 70)

    with open(SLVD_RAW_CSV, 'r', encoding='utf-8-sig') as f:
        slvd_rows = list(csv.DictReader(f))

    print(f"[*] Đã tải danh sách gốc: {len(slvd_rows):,} nhà máy sản xuất ô tô (NACE 29).")

    # Tải cache hiện tại
    cache_data = {}
    if CACHE_JSON.exists():
        try:
            with open(CACHE_JSON, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            print(f"[*] Đã tải bộ nhớ đệm cache_enrich_maps_sk_auto.json ({len(cache_data):,} bản ghi).")
        except Exception:
            cache_data = {}

    # Lập chỉ mục SLVD theo IČO và Tên sạch
    slvd_by_ico = {}
    slvd_by_clean_name = {}
    for r in slvd_rows:
        ico = (r.get('IČO') or '').strip()
        cname = clean_company_name(r.get('Công ty', ''))
        city = remove_accents(r.get('Thành phố', '')).lower().strip()
        entry = {
            'row': r,
            'ico': ico,
            'clean_name': cname,
            'city': city,
            'emails': [],
            'phones': [],
            'websites': []
        }
        if ico:
            slvd_by_ico[ico] = entry
        if cname:
            slvd_by_clean_name[cname] = entry

    # Nạp dữ liệu có sẵn từ cache_data
    for k, val in cache_data.items():
        ico = str(val.get('ico') or k).strip()
        name = clean_company_name(val.get('name', ''))
        target = slvd_by_ico.get(ico) or slvd_by_clean_name.get(name)
        if target:
            if val.get('email'): target['emails'].append(val['email'])
            if val.get('phone'): target['phones'].append(val['phone'])
            if val.get('website'): target['websites'].append(val['website'])

    # Quét tất cả các file CSV trong workspace
    candidate_files = [
        'SK_AUTO_ZLAT_1ENR.csv',
        'SK_AUTO_ZLAT_2COL.csv',
        'SK_AUTO_GMAP_2COL.csv',
        'SK_MANU_ZLAT_2COL.csv',
        'SK_MANU_ZLAT_0RAW.csv',
        'SK_MECH_SLVD_0RAW.csv',
        'SK_MTAL_SLVD_0RAW.csv',
        'SK_ADZC_UPSV_2COL.csv',
        'SK_UDZC_UPSV_2COL.csv',
        'SK_AGCY_WEBD_2COL.csv'
    ]

    matched_from_files = 0
    for fname in candidate_files:
        fpath = ROOT_DIR / fname
        if not fpath.exists():
            continue

        try:
            with open(fpath, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []
                
                # Tìm cột
                ico_col = next((c for c in fields if c.lower() in ['ico', 'ičo']), None)
                name_col = next((c for c in fields if any(k in c.lower() for k in ['công ty', 'company', 'name'])), None)
                web_col = next((c for c in fields if any(k in c.lower() for k in ['website', 'liên hệ', 'web'])), None)
                mail_col = next((c for c in fields if any(k in c.lower() for k in ['email', 'mail'])), None)
                phone_col = next((c for c in fields if any(k in c.lower() for k in ['sđt', 'phone', 'tel'])), None)
                city_col = next((c for c in fields if any(k in c.lower() for k in ['thành phố', 'city'])), None)

                file_matches = 0
                for row in reader:
                    row_ico = (row.get(ico_col) or '').strip() if ico_col else ''
                    row_name = (row.get(name_col) or '').strip() if name_col else ''
                    row_clean_name = clean_company_name(row_name)
                    row_city = remove_accents(row.get(city_col) or '').lower().strip() if city_col else ''

                    target = None
                    if row_ico and row_ico in slvd_by_ico:
                        target = slvd_by_ico[row_ico]
                    elif row_clean_name and len(row_clean_name) >= 4:
                        if row_clean_name in slvd_by_clean_name:
                            target = slvd_by_clean_name[row_clean_name]
                        else:
                            # Thử khớp nếu có cùng thành phố
                            for sc_name, sc_entry in slvd_by_clean_name.items():
                                if len(sc_name) >= 6 and (row_clean_name in sc_name or sc_name in row_clean_name):
                                    if not row_city or not sc_entry['city'] or row_city in sc_entry['city'] or sc_entry['city'] in row_city:
                                        target = sc_entry
                                        break

                    if target:
                        em = (row.get(mail_col) or '').strip() if mail_col else ''
                        ph = (row.get(phone_col) or '').strip() if phone_col else ''
                        wb = (row.get(web_col) or '').strip() if web_col else ''

                        added = False
                        if em and em not in target['emails']:
                            target['emails'].append(em)
                            added = True
                        if ph and ph not in target['phones']:
                            target['phones'].append(ph)
                            added = True
                        if wb and wb not in target['websites']:
                            target['websites'].append(wb)
                            added = True
                        if added:
                            file_matches += 1

                if file_matches > 0:
                    print(f"  [+] {fname:<25}: Bổ sung dữ liệu cho {file_matches:>3} nhà máy.")
                    matched_from_files += file_matches

        except Exception as e:
            pass

    # Đồng bộ hóa kết quả và chọn email/phone tốt nhất
    enriched_count_email = 0
    enriched_count_phone = 0
    enriched_count_web = 0

    enriched_rows = []
    for r in slvd_rows:
        ico = (r.get('IČO') or '').strip()
        cname = clean_company_name(r.get('Công ty', ''))
        entry = slvd_by_ico.get(ico) or slvd_by_clean_name.get(cname)

        current_email = (r.get('Email') or '').strip()
        current_phone = (r.get('SĐT') or '').strip()
        current_web = (r.get('Web') or '').strip()

        if entry:
            # Chọn website
            if not current_web and entry['websites']:
                current_web = entry['websites'][0]

            # Chọn SĐT tốt nhất
            if not current_phone and entry['phones']:
                for p in entry['phones']:
                    cp = clean_phone(p)
                    if cp:
                        current_phone = cp
                        break

            # Chọn Email B2B tốt nhất
            all_email_candidates = ([current_email] if current_email else []) + entry['emails']
            best_email = select_best_email(all_email_candidates, current_web)
            if best_email:
                current_email = best_email

        # Lưu lại cache
        if ico:
            if ico not in cache_data:
                cache_data[ico] = {}
            cache_data[ico].update({
                'name': r.get('Công ty', ''),
                'ico': ico,
                'phone': clean_phone(current_phone),
                'website': current_web,
                'email': current_email
            })

        new_row = dict(r)
        new_row['Email'] = current_email
        new_row['SĐT'] = clean_phone(current_phone)
        new_row['Web'] = current_web
        enriched_rows.append(new_row)

        if current_email: enriched_count_email += 1
        if current_phone: enriched_count_phone += 1
        if current_web: enriched_count_web += 1

    # Lưu cache JSON
    with open(CACHE_JSON, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    # Đẩy các dòng có Email lên đầu bảng
    rows_with_email = [r for r in enriched_rows if r.get('Email', '').strip()]
    rows_without_email = [r for r in enriched_rows if not r.get('Email', '').strip()]
    sorted_rows = rows_with_email + rows_without_email

    for idx, r in enumerate(sorted_rows, 1):
        r['No.'] = idx

    # Ghi ra SK_AUTO_SLVD_1ENR.csv
    fieldnames = list(slvd_rows[0].keys())
    with open(SLVD_ENR_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("\n" + "=" * 70)
    print(" KẾT QUẢ SAU KHI LÀM GIÀU CHÉO (CROSS-ENRICHMENT):")
    print("=" * 70)
    print(f"[*] Tổng số nhà máy ô tô: {len(sorted_rows):,}")
    print(f"[*] Có Email B2B tuyển chọn: {enriched_count_email:,} ({enriched_count_email/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Có Số điện thoại chuẩn '': {enriched_count_phone:,} ({enriched_count_phone/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Có Website chính thức   : {enriched_count_web:,} ({enriched_count_web/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Đã đẩy 100% {enriched_count_email:,} cơ sở có Email lên từ dòng 1 đến {enriched_count_email:,}.")
    print(f"[*] Bộ nhớ đệm Cache lưu tại: {CACHE_JSON.name} ({len(cache_data):,} cty).")

    return sorted_rows

if __name__ == '__main__':
    cross_enrich()
