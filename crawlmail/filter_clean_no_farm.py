# -*- coding: utf-8 -*-
"""
HỆ THỐNG LÀM SẠCH VÀ LỌC BỎ CÔNG TY KHÔNG CÓ LIÊN HỆ (NO PHONE & NO EMAIL)
CHO BỘ DỮ LIỆU NÔNG NGHIỆP NA UY (NORWAY FARMING - NO_FARM)
=============================================================================
Tuân thủ đầy đủ GEMINI.md:
1. CSV ONLY - UTF-8 with BOM (utf-8-sig).
2. SĐT chuẩn hóa nháy đơn '+'47...
3. Lọc bỏ 100% công ty không có SĐT và không có Email (4,392 công ty rỗng).
4. Phân loại đẩy 100% công ty có Email lên đầu danh sách (dòng 1..583).
5. Đánh số lại thứ tự No. từ 1 đến hết.
6. Cập nhật và xuất các tệp:
   - NO_FARM_COMB_2COL.csv (4,979 công ty có liên hệ: 583 Email + 4,396 SĐT)
   - NO_FARM_GMAP_1ENR.csv (4,979 công ty)
   - NO_FARM_ONLY_EMAILS_READY.csv (583 công ty có Email gửi ngay)
   - NO_FARM_BOTH_PHONE_EMAIL.csv (568 công ty có cả SĐT và Email)
7. Tự động đồng bộ sang csdl_mlt/ và archive/no_norway/.
8. Kiểm tra Rule 12 blacklist vĩnh viễn (Scandi Standard, Biliarta, Daigre).
"""

import sys
import os
import re
import json
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

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def clean_phone(phone_str):
    if not phone_str or pd.isna(phone_str):
        return ""
    p = str(phone_str).strip()
    while p.startswith("'"):
        p = p[1:].strip()
    if not p:
        return ""
    # Chuẩn hóa số Na Uy
    p_clean = re.sub(r'[\s\-.]', '', p)
    if p_clean.startswith('0047'):
        p_clean = '+47' + p_clean[4:]
    elif p_clean.startswith('47') and len(p_clean) == 10:
        p_clean = '+47' + p_clean[2:]
    elif not p_clean.startswith('+') and len(p_clean) == 8:
        p_clean = '+47' + p_clean
    elif not p_clean.startswith('+'):
        p_clean = '+' + p_clean
    return f"'{p_clean}"

def clean_email(email_str):
    if not email_str or pd.isna(email_str):
        return ""
    em = str(email_str).strip().lower()
    # Tách query params nếu lỡ lấy từ mailto: ?subject=...
    em = em.split('?')[0].split('&')[0]
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    return em

def sync_to_dirs(df, filename):
    p_root = ROOT_DIR / filename
    p_csdl = ROOT_DIR / "csdl_mlt" / filename
    p_arch = ROOT_DIR / "archive" / "no_norway" / filename

    df.to_csv(p_root, index=False, encoding='utf-8-sig')
    p_csdl.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p_csdl, index=False, encoding='utf-8-sig')
    p_arch.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p_arch, index=False, encoding='utf-8-sig')
    print(f"  [+] Đã lưu và đồng bộ: {filename} ({len(df):,} dòng)")

def process():
    print("=" * 80)
    print(" LỌC VÀ LÀM SẠCH DỮ LIỆU NÔNG NGHIỆP NA UY (NO_FARM)")
    print("=" * 80)

    src_2col = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
    src_1enr = ROOT_DIR / "NO_FARM_GMAP_1ENR.csv"
    cache_path = ROOT_DIR / "crawlmail" / "cache_enrich_maps_no_farm.json"

    if not src_2col.exists():
        print(f"[ERROR] Không tìm thấy file nguồn: {src_2col}")
        return

    df2 = pd.read_csv(src_2col, encoding='utf-8-sig', dtype=str).fillna('')
    total_raw = len(df2)
    print(f"[*] Tổng số bản ghi ban đầu: {total_raw:,}")

    # Nạp cache để đảm bảo không bỏ sót bất kỳ email/phone nào được bóc tách
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp cache: {len(cache):,} bản ghi.")
        except Exception as e:
            print(f"[!] Không thể đọc cache: {e}")

    # Làm sạch số điện thoại và email
    df2['SĐT'] = df2['SĐT'].apply(clean_phone)
    df2['Email'] = df2['Email'].apply(clean_email)

    # Khôi phục email từ cache nếu có
    for idx, r in df2.iterrows():
        cname = r['Công ty'].strip().lower()
        cached = cache.get(cname)
        if cached:
            cached_em = clean_email(cached.get('Email', ''))
            if cached_em and not df2.at[idx, 'Email']:
                df2.at[idx, 'Email'] = cached_em
            cached_ph = clean_phone(cached.get('Phone', ''))
            if cached_ph and not df2.at[idx, 'SĐT']:
                df2.at[idx, 'SĐT'] = cached_ph

    df2['Liên Hệ mail'] = df2['Email'].apply(lambda e: f"mailto:{e}" if e else "")
    df2['Check gửi'] = df2['Email'].apply(lambda e: 'OK' if e else "")

    # Lọc bỏ blacklist Rule 12
    mask_not_blacklisted = ~df2['Công ty'].apply(is_blacklisted)
    df2 = df2[mask_not_blacklisted].copy()
    print(f"[*] Sau khi loại bỏ blacklist: {len(df2):,} công ty")

    # LỌC BỎ CÔNG TY KHÔNG CÓ SĐT VÀ KHÔNG CÓ EMAIL
    has_phone = df2['SĐT'].str.strip() != ''
    has_email = df2['Email'].str.strip() != ''
    
    # Điều kiện giữ lại: CÓ SĐT HOẶC CÓ EMAIL (không được rỗng cả 2)
    has_contact = has_phone | has_email
    empty_contact = (~has_phone) & (~has_email)

    empty_count = empty_contact.sum()
    print(f"[-] Số lượng công ty KHÔNG CÓ SĐT và KHÔNG CÓ EMAIL bị loại bỏ: {empty_count:,}")

    df_clean = df2[has_contact].copy()
    print(f"[+] Số lượng công ty sạch có liên hệ giữ lại: {len(df_clean):,}")

    # Phân loại: Có Email lên đầu (dòng 1..N), kế tiếp là các công ty chỉ có SĐT
    with_email = df_clean[df_clean['Email'].str.strip() != ''].copy()
    without_email = df_clean[df_clean['Email'].str.strip() == ''].copy()

    print(f"    - Doanh nghiệp có Email (xếp hàng đầu): {len(with_email):,}")
    print(f"    - Doanh nghiệp có SĐT (xếp tiếp theo): {len(without_email):,}")

    # Gộp theo thứ tự chuẩn Rule 3
    df_final_2col = pd.concat([with_email, without_email], ignore_index=True)
    df_final_2col['No.'] = range(1, len(df_final_2col) + 1)

    # Đảm bảo đúng 20 cột
    for col in COL_20_HEADERS:
        if col not in df_final_2col.columns:
            df_final_2col[col] = ''
    df_final_2col = df_final_2col[COL_20_HEADERS]

    # 1. Cập nhật file Master 2COL: NO_FARM_COMB_2COL.csv
    sync_to_dirs(df_final_2col, "NO_FARM_COMB_2COL.csv")

    # 2. Cập nhật file Email Only: NO_FARM_ONLY_EMAILS_READY.csv
    df_email_only = with_email.copy().reset_index(drop=True)
    df_email_only['No.'] = range(1, len(df_email_only) + 1)
    df_email_only = df_email_only[COL_20_HEADERS]
    sync_to_dirs(df_email_only, "NO_FARM_ONLY_EMAILS_READY.csv")

    # 3. Tạo file lọc nghiêm ngặt: Có cả SĐT và Email
    both_phone_email = df_clean[(df_clean['SĐT'].str.strip() != '') & (df_clean['Email'].str.strip() != '')].copy().reset_index(drop=True)
    both_phone_email['No.'] = range(1, len(both_phone_email) + 1)
    both_phone_email = both_phone_email[COL_20_HEADERS]
    sync_to_dirs(both_phone_email, "NO_FARM_BOTH_PHONE_EMAIL.csv")

    # 4. Cập nhật file làm giàu 1ENR: NO_FARM_GMAP_1ENR.csv nếu có
    if src_1enr.exists():
        df1 = pd.read_csv(src_1enr, encoding='utf-8-sig', dtype=str).fillna('')
        df1['SĐT'] = df1['SĐT'].apply(clean_phone)
        df1['Email'] = df1['Email'].apply(clean_email)

        for idx, r in df1.iterrows():
            cname = r['Công ty'].strip().lower()
            cached = cache.get(cname)
            if cached:
                cached_em = clean_email(cached.get('Email', ''))
                if cached_em and not df1.at[idx, 'Email']:
                    df1.at[idx, 'Email'] = cached_em
                cached_ph = clean_phone(cached.get('Phone', ''))
                if cached_ph and not df1.at[idx, 'SĐT']:
                    df1.at[idx, 'SĐT'] = cached_ph
        
        has_phone_1 = df1['SĐT'].str.strip() != ''
        has_email_1 = df1['Email'].str.strip() != ''
        has_contact_1 = has_phone_1 | has_email_1
        
        df1_clean = df1[has_contact_1 & ~df1['Công ty'].apply(is_blacklisted)].copy()
        with_em_1 = df1_clean[df1_clean['Email'].str.strip() != ''].copy()
        without_em_1 = df1_clean[df1_clean['Email'].str.strip() == ''].copy()
        df1_final = pd.concat([with_em_1, without_em_1], ignore_index=True)
        df1_final['No.'] = range(1, len(df1_final) + 1)
        
        df1_final.to_csv(src_1enr, index=False, encoding='utf-8-sig')
        print(f"  [+] Đã cập nhật NO_FARM_GMAP_1ENR.csv ({len(df1_final):,} dòng)")

    print("\n" + "=" * 80)
    print(" XỬ LÝ HOÀN TẤT THÀNH CÔNG!")
    print(f" - Tổng ban đầu                             : {total_raw:,} công ty")
    print(f" - Bị loại bỏ (hoàn toàn không SĐT & Email) : {empty_count:,} công ty")
    print(f" - Danh sách sạch giữ lại                   : {len(df_final_2col):,} công ty")
    print(f"   * Trong đó có Email (xếp dòng 1..{len(with_email)}): {len(with_email):,} công ty")
    print(f"   * Trong đó có SĐT (xếp dòng {len(with_email)+1}..{len(df_final_2col)}): {len(without_email):,} công ty")
    print(f"   * Có đầy đủ cả SĐT và Email              : {len(both_phone_email):,} công ty")
    print("=" * 80)

if __name__ == '__main__':
    process()
