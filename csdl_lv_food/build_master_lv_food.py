# -*- coding: utf-8 -*-
"""
Build Master Food Processing Database for Latvia (LV_FOOD_WEBD)
Consolidates:
- database_latvianfoods.csv
- database_traces_nt.csv
- database_1188_food.csv
- database_dnb_beverage.csv (if available)
- database_kompass_food.csv (if available)

Outputs:
1. csdl_lv_food/LV_FOOD_WEBD_0RAW.csv & root LV_FOOD_WEBD_0RAW.csv
2. csdl_lv_food/LV_FOOD_WEBD_1ENR.csv & root LV_FOOD_WEBD_1ENR.csv
3. csdl_lv_food/LV_FOOD_WEBD_2COL.csv & root LV_FOOD_WEBD_2COL.csv (20 columns, 100% Email on top, phones with single quote ')
"""

import sys
import os
import re
import csv
import unicodedata
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CSDL_DIR = ROOT_DIR / "csdl_lv_food"

# Input files
INPUT_FILES = [
    CSDL_DIR / "database_latvianfoods.csv",
    CSDL_DIR / "database_traces_nt.csv",
    CSDL_DIR / "database_1188_food.csv",
    CSDL_DIR / "database_dnb_beverage.csv",
    CSDL_DIR / "database_kompass_food.csv",
]

# Output files
OUT_0RAW_CSDL = CSDL_DIR / "LV_FOOD_WEBD_0RAW.csv"
OUT_0RAW_ROOT = ROOT_DIR / "LV_FOOD_WEBD_0RAW.csv"

OUT_1ENR_CSDL = CSDL_DIR / "LV_FOOD_WEBD_1ENR.csv"
OUT_1ENR_ROOT = ROOT_DIR / "LV_FOOD_WEBD_1ENR.csv"

OUT_2COL_CSDL = CSDL_DIR / "LV_FOOD_WEBD_2COL.csv"
OUT_2COL_ROOT = ROOT_DIR / "LV_FOOD_WEBD_2COL.csv"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule 12: Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in ['scandi standard', 'scandi-standard', 'scandi standart', 'biliarta', 'daigre'])

# Foreign countries blacklist for strict Latvia filtering
FOREIGN_COUNTRIES = [
    'lithuania', 'lietuva', 'estonia', 'eesti', 'poland', 'polska',
    'russia', 'belarus', 'germany', 'deutschland', 'france', 'italy',
    'united kingdom', 'spain', 'netherlands', 'ukraine', 'finland', 'sweden'
]

def is_foreign_company(row):
    """Kiểm tra và loại trừ nếu doanh nghiệp nằm ở quốc gia khác."""
    addr = str(row.get('Address', '')).lower()
    phone = str(row.get('Phone', '')).replace("'", "").strip()
    web = str(row.get('Website', '')).lower()
    
    # 1. Địa chỉ có chứa tên quốc gia khác (mà không chứa Latvija/Latvia)
    if 'latvia' not in addr and 'latvija' not in addr and 'lv-' not in addr and 'rīga' not in addr and 'riga' not in addr:
        for fc in FOREIGN_COUNTRIES:
            if re.search(rf"\b{re.escape(fc)}\b", addr):
                return True
                
    # 2. SĐT quốc tế khác (+370 Lithuania, +372 Estonia, +48 Poland, +7 Russia...)
    if phone.startswith('+') and not phone.startswith('+371'):
        if any(phone.startswith(prefix) for prefix in ['+370', '+372', '+48', '+7', '+49', '+33', '+44', '+380', '+358', '+46']):
            # Nếu địa chỉ cũng không có Latvia rõ ràng
            if 'latvia' not in addr and 'latvija' not in addr and 'lv-' not in addr:
                return True
                
    return False

def strip_accents(s):
    n = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in n if not unicodedata.combining(c))

def normalize_company_name(name):
    """Chuẩn hóa tên để đối soát và khử trùng lặp chính xác."""
    if not name:
        return ""
    t = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    # Loại bỏ loại hình pháp lý
    legal_forms = [
        r'\bsabiedrība ar ierobežotu atbildību\b',
        r'\bakciju sabiedrība\b',
        r'\bindividuālais komersants\b',
        r'\bpašvaldības aģentūra\b',
        r'\bsia\b', r'\bas\b', r'\ba/s\b', r'\bik\b', r'\bps\b', r'\bks\b'
    ]
    for lf in legal_forms:
        t = re.sub(lf, '', t, flags=re.I).strip()
    t = re.sub(r'\s+', ' ', t).strip(' ,.-')
    return strip_accents(t)

def clean_phone(phone_str):
    if not phone_str or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip().lstrip("'")
    p = re.sub(r'^(?:Tel|T\.|Tālr\.|Tālrunis)[:\s]*', '', p, flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+'):
        return f"'{digits}"
    elif digits.startswith('371'):
        return f"'+{digits}"
    elif (digits.startswith('6') or digits.startswith('2')) and len(digits) == 8:
        return f"'+371{digits}"
    return f"'+{digits}" if not digits.startswith('+') else f"'{digits}"

def clean_email(email_str):
    if not email_str or str(email_str) == 'nan':
        return ""
    e = str(email_str).lower().strip().replace('%20', '').strip('.,;:()[]"\'')
    e = re.sub(r'^(?:e-mail\.|email\.|mailto:)', '', e)
    if '@' not in e or len(e) < 6:
        return ""
    return e

def build_master_lv_food():
    print("=" * 75)
    print(" XÂY DỰNG CƠ SỞ DỮ LIỆU CHẾ BIẾN THỰC PHẨM LATVIA (LV_FOOD_WEBD)")
    print("=" * 75)

    all_records = []
    
    # 1. Đọc và gộp các database nguồn
    for fpath in INPUT_FILES:
        if not fpath.exists():
            print(f"[-] Bỏ qua tệp chưa tồn tại: {fpath.name}")
            continue
            
        try:
            df_in = pd.read_csv(fpath, encoding='utf-8-sig', dtype=str).fillna('')
            print(f"[+] Nạp {len(df_in):,} bản ghi từ {fpath.name}")
            for _, r in df_in.iterrows():
                all_records.append(dict(r))
        except Exception as e:
            print(f"[!] Lỗi đọc {fpath.name}: {e}")
            
    print(f"\n[*] Tổng số bản ghi thô thu thập được: {len(all_records):,}")

    # 2. Lọc danh sách đen cố định và loại bỏ công ty nước ngoài
    valid_records = []
    skipped_bl = 0
    skipped_foreign = 0

    for r in all_records:
        comp = r.get('Company', '').strip()
        if not comp:
            continue
        if is_blacklisted_company(comp):
            skipped_bl += 1
            continue
        if is_foreign_company(r):
            skipped_foreign += 1
            continue
        valid_records.append(r)

    print(f"[*] Đã lọc bỏ công ty thuộc Blacklist: {skipped_bl}")
    print(f"[*] Đã lọc bỏ công ty ngoại quốc (không thuộc Latvia): {skipped_foreign}")
    print(f"[*] Số bản ghi hợp lệ tại Latvia: {len(valid_records):,}")

    # 3. Hợp nhất và khử trùng lặp (Merge & Deduplication)
    merged_map = {}
    
    for r in valid_records:
        comp = r.get('Company', '').strip()
        norm_key = normalize_company_name(comp)
        if not norm_key or len(norm_key) < 2:
            norm_key = comp.lower().strip()

        # Kiểm tra xem có trùng với key đã có
        matched_key = None
        if norm_key in merged_map:
            matched_key = norm_key
        else:
            # So khớp con nếu độ dài hợp lý
            for existing_key in merged_map.keys():
                if len(norm_key) >= 5 and (norm_key == existing_key or norm_key in existing_key or existing_key in norm_key):
                    matched_key = existing_key
                    break

        if not matched_key:
            merged_map[norm_key] = {
                'Company': comp,
                'Website': r.get('Website', '').strip(),
                'Phone': clean_phone(r.get('Phone', '')),
                'Email': clean_email(r.get('Email', '')),
                'Address': r.get('Address', '').strip(),
                'Category': r.get('Category', '').strip(),
                'Source': r.get('Source', '').strip(),
                'Profile_URL': r.get('Profile_URL', '').strip()
            }
        else:
            # Hợp nhất thông tin bổ sung
            curr = merged_map[matched_key]
            if not curr['Website'] and r.get('Website', '').strip():
                curr['Website'] = r.get('Website', '').strip()
            if not curr['Phone'] and r.get('Phone', ''):
                curr['Phone'] = clean_phone(r.get('Phone', ''))
            if not curr['Email'] and r.get('Email', ''):
                curr['Email'] = clean_email(r.get('Email', ''))
            if (not curr['Address'] or curr['Address'] == 'Latvia') and r.get('Address', '').strip():
                curr['Address'] = r.get('Address', '').strip()
            if r.get('Category', '') and r['Category'] not in curr['Category']:
                curr['Category'] += f", {r['Category']}"
            if r.get('Source', '') and r['Source'] not in curr['Source']:
                curr['Source'] += f" + {r['Source']}"

    deduped_list = list(merged_map.values())
    print(f"\n[✔] Số lượng doanh nghiệp thực phẩm Latvia sau khử trùng lặp: {len(deduped_list):,}")

    # Đếm số lượng có Phone, Website, Email
    has_web = sum(1 for x in deduped_list if x['Website'])
    has_phone = sum(1 for x in deduped_list if x['Phone'])
    has_email = sum(1 for x in deduped_list if x['Email'])
    print(f"[*] Có Website : {has_web:,} ({has_web/len(deduped_list)*100:.1f}%)")
    print(f"[*] Có SĐT     : {has_phone:,} ({has_phone/len(deduped_list)*100:.1f}%)")
    print(f"[*] Có Email   : {has_email:,} ({has_email/len(deduped_list)*100:.1f}%)")

    # 4. Xuất file 0RAW
    df_raw = pd.DataFrame(deduped_list)
    df_raw.to_csv(OUT_0RAW_CSDL, index=False, encoding='utf-8-sig')
    df_raw.to_csv(OUT_0RAW_ROOT, index=False, encoding='utf-8-sig')
    print(f"\n[✔] Đã lưu 0RAW: {OUT_0RAW_CSDL}")

    # 5. Xuất file 1ENR
    df_1enr = df_raw.copy()
    df_1enr['Chức danh'] = 'Food processing / Manufacturing'
    df_1enr['Người liên hệ'] = ''
    df_1enr['Liên Hệ'] = df_1enr['Website']
    df_1enr['SĐT'] = df_1enr['Phone']
    df_1enr['Liên Hệ mail'] = df_1enr['Email'].apply(lambda e: f"mailto:{e}" if e else "")
    df_1enr['Địa chỉ'] = df_1enr['Address']
    
    cols_1enr = ['Company', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 'Liên Hệ mail', 'Địa chỉ', 'Category', 'Source', 'Profile_URL']
    for c in cols_1enr:
        if c not in df_1enr.columns:
            df_1enr[c] = ''
    df_1enr = df_1enr[cols_1enr].rename(columns={'Company': 'Công ty'})
    df_1enr.to_csv(OUT_1ENR_CSDL, index=False, encoding='utf-8-sig')
    df_1enr.to_csv(OUT_1ENR_ROOT, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã lưu 1ENR: {OUT_1ENR_CSDL}")

    # 6. Xuất file chuẩn Cold Mail 20 cột (2COL) - 100% Email lên đầu
    df_2col = df_1enr.copy()
    for col in COLDMAIL_COLUMNS:
        if col not in df_2col.columns:
            df_2col[col] = ''
    df_2col = df_2col[COLDMAIL_COLUMNS]

    # Phân loại có email và không có email để đẩy 100% email lên đầu
    has_em = df_2col[df_2col['Email'].notna() & (df_2col['Email'].astype(str).str.strip() != '')].copy()
    no_em = df_2col[df_2col['Email'].isna() | (df_2col['Email'].astype(str).str.strip() == '')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(OUT_2COL_CSDL, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(OUT_2COL_ROOT, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã lưu 2COL (100% Email lên đầu): {OUT_2COL_CSDL}")
    print(f"[✔] Đã đồng bộ sang thư mục gốc: {OUT_2COL_ROOT}")
    print("=" * 75)

    return len(df_sorted), len(has_em)

if __name__ == '__main__':
    build_master_lv_food()
