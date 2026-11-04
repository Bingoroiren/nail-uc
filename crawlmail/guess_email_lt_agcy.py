# -*- coding: utf-8 -*-
"""
THỰC HIỆN BƯỚC ĐOÁN EMAIL DOANH NGHIỆP DỰA TRÊN TIỀN TỐ PHỔ BIẾN NHẤT
Dataset: LT_AGCY_REKV_2COL.csv (Lithuania Employment & Recruitment Agencies)

Nguyên tắc hoạt động:
1. Thống kê toàn bộ các tiền tố trước dấu '@' (local part) từ các email hiện có trong tệp.
2. Tự động chọn ra tiền tố có tần suất xuất hiện cao nhất (ví dụ: info@, cv@, contact@...).
3. Quét các công ty CHƯA CÓ EMAIL nhưng CÓ WEBSITE hợp lệ trong cột 'Liên Hệ'.
4. Trích xuất root domain sạch (loại trừ mạng xã hội, thư bạ, web cá cược casino và blacklist).
5. Ghép email theo công thức: <tiền tố phổ biến nhất>@[domain].
6. Đẩy 100% doanh nghiệp có Email (cả mail thực tế + mail vừa đoán) lên đầu tệp CSV.
7. Đồng bộ ra cả 3 tệp dữ liệu:
   - LT_AGCY_REKV_2COL.csv (Thư mục gốc)
   - csdl_mlt/LT_AGCY_REKV_2COL.csv
   - csdl_mlt/LT_AGCY_REKV_1ENR.csv
"""

import sys
import os
import re
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN TỆP & CẤU HÌNH
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_CSV_ROOT = BASE_DIR / "LT_AGCY_REKV_2COL.csv"
TARGET_CSV_CSDL = BASE_DIR / "csdl_mlt" / "LT_AGCY_REKV_2COL.csv"
TARGET_1ENR_CSDL = BASE_DIR / "csdl_mlt" / "LT_AGCY_REKV_1ENR.csv"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email',
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi',
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up',
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule #12: Danh sách đen doanh nghiệp cố định
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigrė'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in ['scandi standard', 'scandi-standard', 'scandi standart', 'biliarta', 'daigre'])

BLACKLIST_DOMAINS = [
    'rekvizitai.vz.lt', 'rekvizitai.lt', 'vz.lt', 'facebook.com', 'linkedin.com',
    'instagram.com', 'google.com', 'youtube.com', 'twitter.com', 'x.com',
    'cvbankas.lt', 'cvonline.lt', 'cvmarket.lt', 'rekv.lt', 'lovejob.lt',
    'tinklalapiai.lt', 'proton.me', 'gmail.com', 'yahoo.com', 'hotmail.com'
]

GAMBLING_KEYWORDS = [
    'casino', 'kazino', 'ggbet', 'vulkan', 'betting', 'lažybos', 'lazybos',
    'poker', 'slots', 'jackpot', 'roulette', 'bukmeker', 'gambling', 'guarana.lt'
]

def clean_phone_lt(phone):
    """Chuẩn hóa số điện thoại Lithuania và luôn có dấu nháy đơn đầu dòng (Rule #2)."""
    if not phone or pd.isna(phone):
        return ""
    p = str(phone).strip()
    if not p or p.lower() in ['nan', 'none', '']:
        return ""
    p = re.sub(r'[^\d+]', '', p)
    if p.startswith('86') and len(p) == 9:
        p = '+3706' + p[2:]
    elif p.startswith('370') and not p.startswith('+370'):
        p = '+' + p
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def get_clean_domain(url):
    """Trích xuất root domain sạch, loại trừ blacklist mạng xã hội và web cờ bạc."""
    if not url or pd.isna(url):
        return None
    u = str(url).strip().lower()
    if not u or u in ['nan', 'none', '']:
        return None
    if not u.startswith(('http://', 'https://')):
        u = 'http://' + u
    try:
        parsed = urllib.parse.urlparse(u)
        netloc = parsed.netloc
        if not netloc:
            return None
        # Bỏ port
        netloc = netloc.split(':')[0]
        # Bỏ www.
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        # Loại trừ domain blacklist và mạng xã hội
        if any(b in netloc for b in BLACKLIST_DOMAINS):
            return None
        # Loại trừ domain cờ bạc
        if any(g in netloc for g in GAMBLING_KEYWORDS):
            return None
        # Kiểm tra tính hợp lệ domain
        parts = netloc.split('.')
        if len(parts) < 2 or len(parts[-1]) < 2:
            return None
        return netloc
    except Exception:
        return None

def analyze_and_guess_emails(df, force_prefix=None):
    """
    1. Thống kê tiền tố email trước @
    2. Chọn tiền tố phổ biến nhất
    3. Đoán ghép với các website chưa có email
    """
    print("=" * 80)
    print(" BƯỚC 1: THỐNG KÊ TIỀN TỐ EMAIL TRƯỚC @ (LOCAL PART)")
    print("=" * 80)

    email_col = 'Email'
    web_col = 'Liên Hệ'

    # Lọc email hiện có hợp lệ
    existing_emails = []
    prefix_counts = {}

    for idx in df.index:
        em = str(df.at[idx, email_col]).strip().lower()
        if em and em != 'nan' and '@' in em and '.' in em:
            existing_emails.append(em)
            prefix = em.split('@')[0].strip()
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    total_existing = len(existing_emails)
    print(f"[*] Tổng số email hiện có trong tệp: {total_existing:,}")

    sorted_prefixes = sorted(prefix_counts.items(), key=lambda x: x[1], reverse=True)
    print("\n[*] TOP 10 TIỀN TỐ PHỔ BIẾN NHẤT:")
    for rank, (pref, count) in enumerate(sorted_prefixes[:10], 1):
        pct = (count / total_existing * 100) if total_existing else 0
        print(f"    {rank:02d}. {pref:<18} : {count:>4} lần ({pct:>5.1f}%)")

    if force_prefix:
        chosen_prefix = force_prefix.strip().lower()
        print(f"\n[!] Sử dụng tiền tố được chỉ định thủ công: '{chosen_prefix}'")
    else:
        chosen_prefix = sorted_prefixes[0][0] if sorted_prefixes else 'info'
        print(f"\n[✔] Tiền tố phổ biến nhất được chọn tự động: '{chosen_prefix}'")

    print("\n" + "=" * 80)
    print(f" BƯỚC 2: TIẾN HÀNH ĐOÁN GHÉP CÔNG THỨC: {chosen_prefix}@[domain]")
    print("=" * 80)

    guessed_records = []
    df_result = df.copy()

    for idx in df_result.index:
        comp = str(df_result.at[idx, 'Công ty']).strip()
        if is_blacklisted_company(comp):
            continue

        em = str(df_result.at[idx, email_col]).strip()
        # Nếu chưa có email
        if not em or em.lower() == 'nan' or '@' not in em:
            web = df_result.at[idx, web_col]
            domain = get_clean_domain(web)
            if domain:
                guessed_email = f"{chosen_prefix}@{domain}"
                df_result.at[idx, email_col] = guessed_email
                df_result.at[idx, 'Liên Hệ mail'] = f"mailto:{guessed_email}"
                guessed_records.append((comp, domain, guessed_email))

    print(f"[*] Số lượng email vừa đoán ghép thành công: +{len(guessed_records):,} email mới!")
    print("\n[*] DANH SÁCH 15 CÔNG TY TIÊU BIỂU ĐƯỢC BỔ SUNG EMAIL:")
    for comp, dom, g_em in guessed_records[:15]:
        print(f"    - {comp[:30]:<30} | {dom:<25} -> {g_em}")

    # BƯỚC 3: ĐỒNG BỘ VÀ ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU DANH SÁCH (RULE #3)
    print("\n" + "=" * 80)
    print(" BƯỚC 3: SẮP XẾP ĐẨY 100% DOANH NGHIỆP CÓ EMAIL LÊN ĐẦU & LƯU TỆP")
    print("=" * 80)

    if 'SĐT' in df_result.columns:
        df_result['SĐT'] = df_result['SĐT'].apply(clean_phone_lt)

    # Loại bỏ doanh nghiệp blacklist cố định
    if 'Công ty' in df_result.columns:
        df_result = df_result[
            ~df_result['Công ty'].astype(str).apply(is_blacklisted_company)
        ].reset_index(drop=True)

    has_em = df_result[df_result[email_col].notna() & (df_result[email_col].astype(str).str.strip() != '') & (df_result[email_col].astype(str).str.strip() != 'nan')].copy()
    no_em = df_result[df_result[email_col].isna() | (df_result[email_col].astype(str).str.strip() == '') | (df_result[email_col].astype(str).str.strip() == 'nan')].copy()

    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    # Đảm bảo đủ các cột chuẩn
    for col in COLDMAIL_COLUMNS:
        if col not in df_sorted.columns:
            df_sorted[col] = ''
    df_sorted = df_sorted[COLDMAIL_COLUMNS]

    # Lưu đồng bộ
    TARGET_CSV_ROOT.parent.mkdir(parents=True, exist_ok=True)
    TARGET_CSV_CSDL.parent.mkdir(parents=True, exist_ok=True)

    df_sorted.to_csv(TARGET_CSV_ROOT, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(TARGET_CSV_CSDL, index=False, encoding='utf-8-sig')
    df_sorted.to_csv(TARGET_1ENR_CSDL, index=False, encoding='utf-8-sig')

    total_all = len(df_sorted)
    total_has_email = len(has_em)

    print(f"[✔] Tổng doanh nghiệp trong tệp: {total_all:,}")
    print(f"[✔] Email ban đầu (quét web/maps): {total_existing:,}")
    print(f"[✔] Email đoán thêm từ domain   : +{len(guessed_records):,}")
    print(f"[✔] TỔNG CỘNG EMAIL HIỆN CÓ      : {total_has_email:,} / {total_all:,} ({total_has_email/total_all*100:.1f}%)")
    print(f"[✔] Đã lưu và đồng bộ thành công vào:")
    print(f"    1. {TARGET_CSV_ROOT}")
    print(f"    2. {TARGET_CSV_CSDL}")
    print(f"    3. {TARGET_1ENR_CSDL}")
    print("=" * 80 + "\n")

    return df_sorted

def main():
    if not TARGET_CSV_ROOT.exists():
        print(f"[ERROR] Không tìm thấy tệp mục tiêu: {TARGET_CSV_ROOT}")
        sys.exit(1)

    df = pd.read_csv(TARGET_CSV_ROOT, encoding='utf-8-sig', dtype=str).fillna('')
    analyze_and_guess_emails(df)

if __name__ == '__main__':
    main()
