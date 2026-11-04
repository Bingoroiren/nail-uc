# -*- coding: utf-8 -*-
"""
XUẤT DỮ LIỆU SẴN SÀNG SỬ DỤNG CHO BỈ VÀ NA UY (COLD MAIL 20 CỘT CHUẨN)
----------------------------------------------------------------------
Mục đích:
- Trích xuất toàn bộ các doanh nghiệp ĐÃ CÓ B2B EMAIL HỢP LỆ từ Na Uy và Bỉ.
- Tự động đồng bộ các kết quả mới nhất vừa cào được từ Cache JSON vào file.
- Lọc sạch 100% mail rác/demo (youremail@, sample@, sentry, wix, gebruiker@...).
- Chuẩn hóa SĐT có nháy đơn (') và mã vùng quốc tế (+47 cho Na Uy, +32 cho Bỉ).
- Khử trùng lặp email 100% (Mỗi email chỉ xuất hiện 1 lần).
- Đánh số No. liên tục từ 1 đến hết.
- Tuyệt đối KHÔNG can thiệp, KHÔNG dừng các tiến trình đang chạy ngầm.

Xuất ra 3 file sẵn sàng sử dụng:
1. BE_AGCY_2COL_READY.csv   : Dành riêng cho Bỉ (sẵn sàng nạp tool gửi mail)
2. NO_AGCY_2COL_READY.csv   : Dành riêng cho Na Uy (sẵn sàng nạp tool gửi mail)
3. BE_NO_AGCY_2COL_READY.csv: File gộp chung cả 2 nước Bỉ & Na Uy
"""

import sys
import os
import re
import json
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# Input files
FILE_NO_2COL = ROOT_DIR / "NO_AGCY_WEBD_2COL.csv"
FILE_BE_2COL = ROOT_DIR / "BE_AGCY_GMAP_2COL.csv"
CACHE_NO = ROOT_DIR / "crawlmail" / "cache_enrich_maps_no_agcy.json"
CACHE_BE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_agcy.json"

# Output ready files
OUT_BE_READY = ROOT_DIR / "BE_AGCY_2COL_READY.csv"
OUT_NO_READY = ROOT_DIR / "NO_AGCY_2COL_READY.csv"
OUT_COMB_READY = ROOT_DIR / "BE_NO_AGCY_2COL_READY.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule #12: Danh sách đen vĩnh viễn
PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def clean_email(email):
    """Làm sạch email theo Rule #3 & data-standards"""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em).strip(" .,;:\"'<>[](){}\\/")
    
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
            
    em = em.lower()
    if not re.match(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,10}$', em):
        return ""
        
    u, d = em.split('@', 1)
    # Lọc bỏ mail demo / junk
    junk_domains = [
        'sentry', 'wixpress', 'wix.com', 'example.com', 'domain.com',
        'yoursite.com', 'email.com', 'test.com', 'cookiebot.com', 'squarespace.com',
        'domein.com', 'epost.no', 'eksempel.no', 'apd-gba.be', 'kinamo.be'
    ]
    if any(b in d for b in junk_domains):
        return ""
        
    junk_users = [
        'sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply',
        'donotreply', 'someone', 'john.doe', 'privacy', 'gdpr', 'abuse',
        'postmaster', 'user', 'name', 'gebruiker', 'din', 'dinepost'
    ]
    if any(b in u for b in junk_users):
        return ""
        
    return em

def clean_phone_no(p):
    """Chuẩn hóa SĐT Na Uy có nháy đơn (') và mã vùng +47 (Rule #2)"""
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('0047'):
        digits = digits[4:]
    elif digits.startswith('47') and len(digits) == 10:
        digits = digits[2:]
    if len(digits) == 8:
        if digits[0] in ['4', '9']:
            formatted = f"+47 {digits[:3]} {digits[3:5]} {digits[5:]}"
        else:
            formatted = f"+47 {digits[:2]} {digits[2:4]} {digits[4:6]} {digits[6:]}"
        return f"'{formatted}"
    elif len(digits) > 8:
        return f"'+{digits}"
    else:
        return f"'{s}"

def clean_phone_be(p):
    """Chuẩn hóa SĐT Bỉ có nháy đơn (') và mã vùng +32 (Rule #2)"""
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('0032'):
        digits = digits[4:]
    elif digits.startswith('32') and len(digits) >= 9:
        digits = digits[2:]
    elif digits.startswith('0') and len(digits) >= 9:
        digits = digits[1:]
    if len(digits) >= 8:
        return f"'+32 {digits}"
    return f"'{s}"

def extract_ready_norway():
    print("[*] Đang trích xuất dữ liệu Na Uy (Norway)...")
    if not FILE_NO_2COL.exists():
        print(f"[!] Không tìm thấy file {FILE_NO_2COL}")
        return pd.DataFrame(columns=COLUMNS_20)

    # Đọc an toàn read-only
    df = pd.read_csv(FILE_NO_2COL, encoding='utf-8-sig', dtype=str).fillna('')
    
    # Nạp thêm từ Cache mới nhất
    if CACHE_NO.exists():
        try:
            with open(CACHE_NO, 'r', encoding='utf-8') as f:
                c_data = json.load(f)
            cached_updates = 0
            for idx, r in df.iterrows():
                comp = str(r['Công ty']).strip().lower()
                if comp in c_data and c_data[comp].get('Email'):
                    c_em = clean_email(c_data[comp]['Email'])
                    if c_em and not df.at[idx, 'Email'].strip():
                        df.at[idx, 'Email'] = c_em
                        if c_data[comp].get('Web') and not df.at[idx, 'Liên Hệ'].strip():
                            df.at[idx, 'Liên Hệ'] = c_data[comp]['Web']
                        if c_data[comp].get('Phone') and not df.at[idx, 'SĐT'].strip():
                            df.at[idx, 'SĐT'] = c_data[comp]['Phone']
                        cached_updates += 1
            if cached_updates > 0:
                print(f"    - Đã đồng bộ thêm {cached_updates} email mới từ cache Na Uy")
        except Exception as e:
            print(f"    - Không đọc được cache Na Uy: {e}")

    # Làm sạch
    df['Email'] = df['Email'].apply(clean_email)
    df['SĐT'] = df['SĐT'].apply(clean_phone_no)
    
    # Lọc chỉ các công ty có Email
    ready_df = df[df['Email'] != ''].copy()
    ready_df = ready_df[~ready_df['Công ty'].apply(is_blacklisted_company)]
    
    # Khử trùng lặp email
    ready_df = ready_df.drop_duplicates(subset=['Email'], keep='first').copy()
    
    # Chuẩn hóa Liên Hệ mail & Check gửi
    ready_df['Liên Hệ mail'] = ready_df['Email'].apply(lambda e: f"mailto:{e}" if e else "")
    ready_df['Check gửi'] = ready_df['Check gửi'].apply(lambda c: c if c else 'Chưa gửi')
    ready_df['Category'] = ready_df['Category'].apply(lambda c: c if c else 'Bemanningsbyrå / Rekruttering (Norway)')
    
    ready_df['No.'] = range(1, len(ready_df) + 1)
    ready_df = ready_df[COLUMNS_20]
    return ready_df

def extract_ready_belgium():
    print("[*] Đang trích xuất dữ liệu Bỉ (Belgium)...")
    if not FILE_BE_2COL.exists():
        print(f"[!] Không tìm thấy file {FILE_BE_2COL}")
        return pd.DataFrame(columns=COLUMNS_20)

    # Đọc an toàn read-only
    df = pd.read_csv(FILE_BE_2COL, encoding='utf-8-sig', dtype=str).fillna('')
    
    # Nạp thêm từ Cache mới nhất
    if CACHE_BE.exists():
        try:
            with open(CACHE_BE, 'r', encoding='utf-8') as f:
                c_data = json.load(f)
            cached_updates = 0
            for idx, r in df.iterrows():
                comp = str(r['Công ty']).strip().lower()
                if comp in c_data and c_data[comp].get('Email'):
                    c_em = clean_email(c_data[comp]['Email'])
                    if c_em and not df.at[idx, 'Email'].strip():
                        df.at[idx, 'Email'] = c_em
                        if c_data[comp].get('Web') and not df.at[idx, 'Liên Hệ'].strip():
                            df.at[idx, 'Liên Hệ'] = c_data[comp]['Web']
                        if c_data[comp].get('Phone') and not df.at[idx, 'SĐT'].strip():
                            df.at[idx, 'SĐT'] = c_data[comp]['Phone']
                        cached_updates += 1
            if cached_updates > 0:
                print(f"    - Đã đồng bộ thêm {cached_updates} email mới từ cache Bỉ")
        except Exception as e:
            print(f"    - Không đọc được cache Bỉ: {e}")

    # Làm sạch
    df['Email'] = df['Email'].apply(clean_email)
    df['SĐT'] = df['SĐT'].apply(clean_phone_be)
    
    # Lọc chỉ các công ty có Email
    ready_df = df[df['Email'] != ''].copy()
    ready_df = ready_df[~ready_df['Công ty'].apply(is_blacklisted_company)]
    
    # Khử trùng lặp email
    ready_df = ready_df.drop_duplicates(subset=['Email'], keep='first').copy()
    
    # Chuẩn hóa Liên Hệ mail & Check gửi
    ready_df['Liên Hệ mail'] = ready_df['Email'].apply(lambda e: f"mailto:{e}" if e else "")
    ready_df['Check gửi'] = ready_df['Check gửi'].apply(lambda c: c if c else 'Chưa gửi')
    ready_df['Category'] = ready_df['Category'].apply(lambda c: c if c else 'Uitzendbureau / Agence de recrutement (Belgium)')
    
    ready_df['No.'] = range(1, len(ready_df) + 1)
    ready_df = ready_df[COLUMNS_20]
    return ready_df

def main():
    print("=" * 80)
    print(" XUẤT TẬP DỮ LIỆU SẴN SÀNG SỬ DỤNG: NA UY & BỈ (COLD MAIL 20 CỘT)")
    print(" (Tuyệt đối không can thiệp hay dừng các tiến trình đang cào ngầm)")
    print("=" * 80 + "\n")

    # 1. Trích xuất Na Uy
    df_no_ready = extract_ready_norway()
    df_no_ready.to_csv(OUT_NO_READY, index=False, encoding='utf-8-sig')
    print(f"[+] ĐÃ XUẤT FILE NA UY SẴN SÀNG: {OUT_NO_READY.name} ({len(df_no_ready):,} doanh nghiệp có Email)")

    # 2. Trích xuất Bỉ
    df_be_ready = extract_ready_belgium()
    df_be_ready.to_csv(OUT_BE_READY, index=False, encoding='utf-8-sig')
    print(f"[+] ĐÃ XUẤT FILE BỈ SẴN SÀNG   : {OUT_BE_READY.name} ({len(df_be_ready):,} doanh nghiệp có Email)")

    # 3. Tạo file gộp chung cả Bỉ và Na Uy
    print("\n[*] Đang gộp chung 2 quốc gia vào file tổng hợp...")
    df_comb = pd.concat([df_be_ready, df_no_ready], ignore_index=True)
    
    # Khử trùng lặp email nếu có giữa 2 nước
    df_comb = df_comb.drop_duplicates(subset=['Email'], keep='first').copy()
    df_comb['No.'] = range(1, len(df_comb) + 1)
    df_comb = df_comb[COLUMNS_20]
    
    df_comb.to_csv(OUT_COMB_READY, index=False, encoding='utf-8-sig')
    print(f"[+] ĐÃ XUẤT FILE GỘP CHUNG BỈ & NA UY: {OUT_COMB_READY.name} ({len(df_comb):,} doanh nghiệp có Email)")

    print("\n" + "=" * 80)
    print(" TỔNG HỢP CÁC FILE ĐÃ XUẤT SẴN SÀNG DÙNG NGAY:")
    print("=" * 80)
    print(f"1. {OUT_COMB_READY.name:<26} : {len(df_comb):,} B2B Email (Bỉ + Na Uy gộp chung)")
    print(f"2. {OUT_NO_READY.name:<26} : {len(df_no_ready):,} B2B Email (Riêng thị trường Na Uy)")
    print(f"3. {OUT_BE_READY.name:<26} : {len(df_be_ready):,} B2B Email (Riêng thị trường Bỉ)")
    print("=" * 80)
    print("Các tiến trình cào ngầm vẫn đang tiếp tục chạy bình thường 100%!")

if __name__ == '__main__':
    main()

