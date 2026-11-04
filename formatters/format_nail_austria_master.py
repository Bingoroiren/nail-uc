# -*- coding: utf-8 -*-
"""
HỢP NHẤT SIÊU DỮ LIỆU TIỆM NAIL NƯỚC ÁO (ĐA NGUỒN WKO + HEROLD + FIRMENABC + GGMAP)
=============================================================================
Yêu cầu cốt lõi:
1. Ghép 4 nguồn: Google Maps, WKO Portal, Herold Gelbe Seiten, FirmenABC
2. Lọc trùng triệt để:
   - Trùng Tên Công Ty (Smart & Strict Normalization Rule 11)
   - Trùng Email (100% Unique Email Rule 3)
3. Hợp nhất thông tin (Coalescing):
   - Nếu công ty ở nguồn này thiếu Email/SĐT mà nguồn khác có -> Tự động bổ sung nâng cấp
4. Đầu ra chuẩn 20 cột Cold Mail:
   - AT_NAIL_ALL_2COL.csv (Toàn bộ cơ sở độc nhất, 100% email lên đầu dòng 1..N)
   - AT_NAIL_ALL_ONLY_EMAILS_READY.csv (Chỉ gồm các dòng có email sẵn sàng gửi)
   - Đồng bộ sang csdl_mlt/ và archive/at_austria/
"""

import sys
import os
import re
import csv
import unicodedata
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

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
    if not p or pd.isna(p):
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or pd.isna(email) or not isinstance(email, str):
        return ""
    em = email.strip()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()
    if re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return em
    return ""

def normalize_company_name(name):
    """
    Chuẩn hóa tên công ty thông minh & nghiêm ngặt theo Rule 11:
    - Bóc tách phần dịch/chú thích trong ngoặc (...)
    - Khử dấu Unicode NFKD (ä->a, ö->o, ü->u, ß->ss)
    - Loại bỏ legal forms (GmbH, e.U., OG, KG, Inhaber...)
    - Loại bỏ từ khóa ngành phổ biến nếu tên còn định danh riêng
    """
    if not name or pd.isna(name):
        return ""
    s = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', str(name))
    norm = unicodedata.normalize('NFKD', s).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c)).replace('ß', 'ss')
    clean = re.sub(r'[.,;:\-_/\\\"\'`´’!?*#|]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    legal_suffixes = [
        r'\bgmbh\b', r'\bgesmbh\b', r'\bm\s*b\s*h\b', r'\bag\b', r'\bkg\b', r'\bog\b',
        r'\be\s*u\b', r'\bflexco\b', r'\bco\s+kg\b', r'\binhaber\b', r'\binh\b'
    ]
    for suf in legal_suffixes:
        clean = re.sub(suf, ' ', clean)

    generic_words = [
        r'\bnagelstudio\b', r'\bnageldesign\b', r'\bfingernagel\b', r'\bnailstudio\b',
        r'\bnails\b', r'\bnail\b', r'\bdesign\b'
    ]
    temp_clean = clean
    for gw in generic_words:
        temp_clean = re.sub(gw, ' ', temp_clean)

    clean_alpha = re.sub(r'[^a-z0-9]', '', temp_clean)
    if len(clean_alpha) >= 3:
        clean = temp_clean

    clean_flat = re.sub(r'[^a-z0-9]', '', clean)
    return clean_flat if clean_flat else re.sub(r'[^a-z0-9]', '', s.lower())

def normalize_city(city):
    if not city or pd.isna(city):
        return ""
    c = unicodedata.normalize('NFKD', str(city)).lower()
    c = ''.join(ch for ch in c if not unicodedata.combining(ch)).replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]', '', c)

def merge_and_deduplicate():
    print("=" * 80)
    print("  HỢP NHẤT & LỌC TRÙNG SIÊU DỮ LIỆU TIỆM NAIL ÁO (WKO + HEROLD + FABC + GGMAP)")
    print("=" * 80)

    raw_records = []

    # 1. GOOGLE MAPS (AT_NAIL_GMAP_2COL.csv)
    p_gmap = ROOT_DIR / "AT_NAIL_GMAP_2COL.csv"
    if p_gmap.exists():
        df_gmap = pd.read_csv(p_gmap, encoding='utf-8-sig')
        print(f"[*] Nạp Google Maps : {len(df_gmap):,} cơ sở.")
        for _, r in df_gmap.iterrows():
            raw_records.append({
                'source': 'GGMAP',
                'name': str(r.get('Công ty', '')).strip(),
                'phone': clean_phone(r.get('SĐT', '')),
                'email': clean_email(r.get('Email', '')),
                'website': str(r.get('Liên Hệ', '')).strip(),
                'address': str(r.get('Địa chỉ', '')).strip(),
            })

    # 2. WKO PORTAL (AT_NAIL_WKOP_ONLY_EMAILS_READY.csv)
    p_wko = ROOT_DIR / "AT_NAIL_WKOP_ONLY_EMAILS_READY.csv"
    if p_wko.exists():
        df_wko = pd.read_csv(p_wko, encoding='utf-8-sig')
        print(f"[*] Nạp WKO Email   : {len(df_wko):,} cơ sở.")
        for _, r in df_wko.iterrows():
            raw_records.append({
                'source': 'WKO',
                'name': str(r.get('Công ty', '')).strip(),
                'phone': clean_phone(r.get('SĐT', '')),
                'email': clean_email(r.get('Email', '')),
                'website': str(r.get('Liên Hệ', '')).strip(),
                'address': str(r.get('Địa chỉ', '')).strip(),
            })

    # 3. HEROLD GELBE SEITEN (data/AT_NAIL_HERO_0RAW.csv)
    p_hero = ROOT_DIR / "data" / "AT_NAIL_HERO_0RAW.csv"
    if p_hero.exists():
        df_hero = pd.read_csv(p_hero, encoding='utf-8-sig')
        print(f"[*] Nạp Herold.at   : {len(df_hero):,} cơ sở.")
        for _, r in df_hero.iterrows():
            street = str(r.get('street', '')).strip() if pd.notna(r.get('street')) else ""
            plz = str(r.get('postal_code', '')).strip() if pd.notna(r.get('postal_code')) else ""
            city = str(r.get('city', '')).strip() if pd.notna(r.get('city')) else ""
            addr = ", ".join([p for p in [street, f"{plz} {city}".strip(), "Austria"] if p])
            raw_records.append({
                'source': 'HERO',
                'name': str(r.get('name', '')).strip(),
                'phone': clean_phone(r.get('phone', '')),
                'email': clean_email(r.get('email', '')),
                'website': str(r.get('website', '')).strip() or str(r.get('detail_url', '')).strip(),
                'address': addr,
            })

    # 4. FIRMENABC (data/AT_NAIL_FABC_0RAW.csv)
    p_fabc = ROOT_DIR / "data" / "AT_NAIL_FABC_0RAW.csv"
    if p_fabc.exists():
        df_fabc = pd.read_csv(p_fabc, encoding='utf-8-sig')
        print(f"[*] Nạp FirmenABC   : {len(df_fabc):,} cơ sở.")
        for _, r in df_fabc.iterrows():
            street = str(r.get('street', '')).strip() if pd.notna(r.get('street')) else ""
            plz = str(r.get('postal_code', '')).strip() if pd.notna(r.get('postal_code')) else ""
            city = str(r.get('city', '')).strip() if pd.notna(r.get('city')) else ""
            addr = ", ".join([p for p in [street, f"{plz} {city}".strip(), "Austria"] if p])
            raw_records.append({
                'source': 'FABC',
                'name': str(r.get('name', '')).strip(),
                'phone': clean_phone(r.get('phone', '')),
                'email': clean_email(r.get('email', '')),
                'website': str(r.get('website', '')).strip() or str(r.get('detail_url', '')).strip(),
                'address': addr,
            })

    print(f"\n[+] Tổng số bản ghi thô từ 4 nguồn: {len(raw_records):,} bản ghi.")

    # Lọc bỏ blacklist công ty cố định (Rule 12)
    raw_records = [r for r in raw_records if not is_blacklisted(r['name'])]

    # ================= QUY TRÌNH HỢP NHẤT & LỌC TRÙNG 2 TẦNG =================
    # TẦNG 1: Gom nhóm & Hợp nhất thông tin theo Tên Công Ty (Smart Name Match)
    # TẦNG 2: Khử trùng lặp tuyệt đối theo Email (Mỗi Email chỉ giữ 1 tiệm tối ưu nhất)

    merged_companies = {}   # comp_key -> record đầy đủ
    email_to_comp = {}      # email -> comp_key

    for rec in raw_records:
        name = rec['name']
        norm_name = normalize_company_name(name)
        if not norm_name:
            continue

        # Trích xuất thành phố từ địa chỉ
        city_m = re.search(r'\b\d{4}\s+([A-Za-zÄÖÜäöüß\s\-]+)', rec['address'])
        city_norm = normalize_city(city_m.group(1)) if city_m else ""

        # Nếu tên quá ngắn (<5 ký tự), ghép thêm thành phố để tránh gộp nhầm 2 tiệm khác tỉnh
        comp_key = norm_name if len(norm_name) >= 5 else f"{norm_name}_{city_norm}"
        email = rec['email']

        # TRƯỜNG HỢP 1: Email này đã xuất hiện trước đó ở một công ty khác
        if email and email in email_to_comp:
            existing_key = email_to_comp[email]
            target = merged_companies[existing_key]
            # Coalesce (bổ sung thông tin còn thiếu)
            if not target['SĐT'] and rec['phone']: target['SĐT'] = rec['phone']
            if not target['Liên Hệ'] and rec['website']: target['Liên Hệ'] = rec['website']
            if not target['Địa chỉ'] and rec['address']: target['Địa chỉ'] = rec['address']
            continue

        # TRƯỜNG HỢP 2: Tên công ty này đã xuất hiện trước đó
        if comp_key in merged_companies:
            target = merged_companies[comp_key]
            # Nếu bản ghi cũ chưa có email mà bản ghi mới có email -> Nâng cấp email ngay!
            if not target['Email'] and email:
                target['Email'] = email
                target['Liên Hệ mail'] = f"mailto:{email}"
                target['Check gửi'] = "Chưa gửi"
                email_to_comp[email] = comp_key
            if not target['SĐT'] and rec['phone']: target['SĐT'] = rec['phone']
            if not target['Liên Hệ'] and rec['website']: target['Liên Hệ'] = rec['website']
            if not target['Địa chỉ'] and rec['address']: target['Địa chỉ'] = rec['address']
            continue

        # TRƯỜNG HỢP 3: Công ty hoàn toàn mới
        merged_companies[comp_key] = {
            'No.': 0,
            'Công ty': name,
            'Chức danh': "",
            'Người liên hệ': "",
            'SĐT': rec['phone'],
            'Liên Hệ': rec['website'],
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else "",
            'Địa chỉ': rec['address'],
            'Lương': "",
            'Ngày đăng': "",
            'Hạn tuyển': "",
            'Check gửi': "Chưa gửi" if email else "",
            'Last Subject': "",
            'Last Body HTML': "",
            'Trạng thái Reply': "",
            'Lần Follow-up': "",
            'Ngày Follow-up gần nhất': "",
            'Mailbox đã dùng': "",
            'Category': "Tiệm làm móng (Nagelstudio)"
        }
        if email:
            email_to_comp[email] = comp_key

    # Lập danh sách kết quả cuối cùng
    final_list = list(merged_companies.values())

    # Tách nhóm có email và không có email (Rule 3: 100% email lên đầu dòng 1..N)
    with_email = [r for r in final_list if r['Email']]
    without_email = [r for r in final_list if not r['Email']]

    df_with_email = pd.DataFrame(with_email)
    df_without_email = pd.DataFrame(without_email)

    # Khử trùng lặp lần cuối trên Email
    df_with_email['clean_em'] = df_with_email['Email'].str.lower().str.strip()
    df_with_email = df_with_email.drop_duplicates(subset=['clean_em'], keep='first').copy()
    df_with_email.drop(columns=['clean_em'], inplace=True)

    # Ghép lại với nhóm có email nằm trọn vẹn ở các dòng đầu tiên
    df_sorted = pd.concat([df_with_email, df_without_email], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Bảng chỉ gồm các dòng có email sẵn sàng gửi
    df_ready = df_with_email.copy()
    df_ready['No.'] = range(1, len(df_ready) + 1)
    df_ready['Check gửi'] = "Chưa gửi"

    def safe_export(dframe, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            dframe.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"  [+] Đã xuất an toàn: {path.name}")
        except PermissionError:
            tmp = path.with_name(f"{path.stem}_updated{path.suffix}")
            dframe.to_csv(tmp, index=False, encoding="utf-8-sig")
            print(f"  [!] {path.name} đang mở trong ứng dụng khác -> Đã lưu vào {tmp.name}")

    print("\n[*] Xuất file Master 2COL (toàn bộ tiệm không trùng lặp):")
    out_master_paths = [
        ROOT_DIR / "AT_NAIL_ALL_2COL.csv",
        ROOT_DIR / "data" / "formatted" / "AT_NAIL_ALL_2COL.csv",
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_ALL_2COL.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_ALL_2COL.csv"
    ]
    for p in out_master_paths:
        safe_export(df_sorted, p)

    print("\n[*] Xuất file ONLY_EMAILS_READY (100% tiệm có email sạch gửi ngay):")
    out_ready_paths = [
        ROOT_DIR / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv",
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_ALL_ONLY_EMAILS_READY.csv"
    ]
    for p in out_ready_paths:
        safe_export(df_ready, p)

    print("\n" + "=" * 80)
    print("🏆 HOÀN TẤT HỢP NHẤT & LỌC TRÙNG SIÊU DỮ LIỆU TIỆM NAIL ÁO:")
    print(f"   - Tổng số tiệm nail ĐỘC NHẤT toàn quốc : {len(df_sorted):,} tiệm (0% trùng tên)")
    print(f"   - TỔNG SỐ TIỆM CÓ EMAIL XÁC THỰC       : {len(df_ready):,} tiệm (0% trùng email)")
    print(f"   - Tỷ lệ tiệm có email                 : {len(df_ready)/len(df_sorted)*100:.1f}%")
    print(f"   - Vị trí dòng có email                : Dòng 1 đến dòng {len(df_ready):,}")
    print(f"   - File Cold Mail sẵn sàng gửi         : AT_NAIL_ALL_ONLY_EMAILS_READY.csv")
    print(f"   - File Master 2COL toàn bộ            : AT_NAIL_ALL_2COL.csv")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    merge_and_deduplicate()
