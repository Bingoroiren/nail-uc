# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU LT_AGCY_REKV_2COL.csv VỚI MAIL TRACKER VÀ LOẠI BỎ CÁC EMAIL ĐÃ GỬI / ĐÃ PHẢN HỒI
-----------------------------------------------------------------------------------
Mục tiêu:
1. Nạp toàn bộ danh sách Email, Corporate Domain và Doanh nghiệp từ 'Mail Tracker - mail.csv'.
2. So khớp đa tầng với file Lithuania Agencies (LT_AGCY_REKV_2COL.csv):
   - Tiêu chí 1: Trùng chính xác Email.
   - Tiêu chí 2: Trùng Corporate Domain của doanh nghiệp đã liên lạc.
   - Tiêu chí 3: Trùng Tên Doanh nghiệp ghi nhận trong Mail Tracker (Ví dụ: MB Vastora Baltic).
3. Tách lọc và xuất tệp lưu vết bản ghi trùng (nếu có): archive/lt_lithuania/LT_AGCY_DA_XOA_TRUNG_TRACKER.csv.
4. Đảm bảo file sạch 100% Fresh Leads:
   - Đẩy toàn bộ doanh nghiệp có Email lên đầu tệp.
   - Đánh số lại No. (1, 2, 3...).
   - Đồng bộ ra LT_AGCY_REKV_2COL.csv (gốc) và csdl_mlt/.
"""

import sys
import os
import re
import csv
import shutil
import unicodedata
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_MASTER = ROOT_DIR / "LT_AGCY_REKV_2COL.csv"
FILE_CSDL_2COL = ROOT_DIR / "csdl_mlt" / "LT_AGCY_REKV_2COL.csv"
FILE_CSDL_1ENR = ROOT_DIR / "csdl_mlt" / "LT_AGCY_REKV_1ENR.csv"

OUT_REMOVED = ROOT_DIR / "archive" / "lt_lithuania" / "LT_AGCY_DA_XOA_TRUNG_TRACKER.csv"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email',
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi',
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up',
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'centrum.sk', 'centrum.cz', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz',
    'inbox.lt', 'inbox.lv', 'mail.ru', 'yandex.ru'
}

def normalize_comp_name(name):
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['uždaroji akcinė bendrovė', 'mažoji bendrija', 'akcinė bendrovė', 'viešoji įstaiga',
                  'uab', 'mb', 'vsi', 'všį', 'ab', 'ii', 'iį', 's.r.o.', 'a.s.', 'gmbh']:
        n_clean = re.sub(rf'\b{legal}\b', '', n_clean)
    n_clean = re.sub(r'[^a-z0-9]', ' ', n_clean)
    return ' '.join(n_clean.split())

def main():
    print("=" * 80)
    print(" ĐỐI CHIẾU & LOẠI BỎ EMAIL / DOANH NGHIỆP TRÙNG MAIL TRACKER")
    print(f" Target File  : {FILE_MASTER.name}")
    print(f" Mail Tracker : {FILE_TRACKER.name}")
    print("=" * 80)

    if not FILE_MASTER.exists():
        print(f"[ERROR] Không tìm thấy file: {FILE_MASTER}")
        return
    if not FILE_TRACKER.exists():
        print(f"[ERROR] Không tìm thấy file: {FILE_TRACKER}")
        return

    # 1. Nạp Mail Tracker
    tracker_emails = {}
    tracker_corp_domains = {}
    tracker_known_companies = {}

    df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
    for idx, r in df_tr.iterrows():
        sender = str(r.get('Người gửi', '')).strip().lower()
        subject = str(r.get('Subject', '')).strip()
        status = str(r.get('Tình trạng phản hồi', '')).strip()
        content = str(r.get('Nội dung', '')).strip()
        note = str(r.get('Note', '')).strip()
        desc = status if status else (note if note else subject[:35])

        full_text = f"{sender} {subject} {content} {note}"
        for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text.lower()):
            if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
                tracker_emails[em] = f"Trùng Email trong Mail Tracker: {em} ({desc})"
                d = em.split('@')[1]
                if d not in GENERIC_DOMAINS:
                    tracker_corp_domains[d] = f"Trùng Domain Doanh Nghiệp Tracker: @{d} ({desc})"

        # Ghi nhận tên cty từ Note/Subject (ví dụ: MB Vastora Baltic)
        if note:
            norm_n = normalize_comp_name(note)
            if len(norm_n) >= 5:
                tracker_known_companies[norm_n] = f"Trùng Tên Doanh Nghiệp trong Mail Tracker Note: '{note}' ({desc})"

    print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} email & {len(tracker_corp_domains):,} domain doanh nghiệp.")
    print(f"[+] Đã nạp ghi chú đặc biệt: {len(tracker_known_companies)} doanh nghiệp đã đối soát.")

    # 2. Đọc file Master LT_AGCY_REKV_2COL.csv
    df = pd.read_csv(FILE_MASTER, encoding='utf-8-sig', dtype=str).fillna('')
    total_initial = len(df)
    initial_with_email = len(df[df['Email'].str.strip().ne('') & df['Email'].str.contains('@', na=False)])

    print(f"\n[*] Đang kiểm tra đối chiếu {total_initial:,} doanh nghiệp ({initial_with_email:,} có email)...")

    removed_records = []
    clean_records = []

    for idx, r in df.iterrows():
        comp = str(r.get('Công ty', '')).strip()
        comp_norm = normalize_comp_name(comp)
        em = str(r.get('Email', '')).strip().lower()

        match_reason = None

        # Tiêu chí 1: Trùng email trực tiếp
        if em and em in tracker_emails:
            match_reason = tracker_emails[em]
        # Tiêu chí 2: Trùng corporate domain
        elif em and '@' in em:
            d = em.split('@')[1]
            if d in tracker_corp_domains:
                match_reason = tracker_corp_domains[d]
        # Tiêu chí 3: Trùng tên cty đối soát trong Mail Tracker
        if not match_reason and len(comp_norm) >= 5:
            for t_comp, t_reason in tracker_known_companies.items():
                if comp_norm == t_comp or comp_norm in t_comp or t_comp in comp_norm:
                    match_reason = t_reason
                    break

        row_dict = r.to_dict()
        if match_reason:
            row_dict['Lý do xoá'] = match_reason
            removed_records.append(row_dict)
            print(f"  [XÓA TRÙNG TRACKER] Row {r.get('No.')}: '{comp}' | Mail: '{em}' -> {match_reason}")
        else:
            clean_records.append(row_dict)

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐỐI SOÁT & LÀM SẠCH")
    print("=" * 80)
    print(f"[*] Tổng số doanh nghiệp ban đầu : {total_initial:,}")
    print(f"[*] Số doanh nghiệp bị loại bỏ    : {len(removed_records):,}")
    print(f"[*] Số doanh nghiệp sạch giữ lại  : {len(clean_records):,}")

    # 3. Xuất file lưu vết đã xóa (nếu có bản ghi bị xóa)
    OUT_REMOVED.parent.mkdir(parents=True, exist_ok=True)
    if removed_records:
        df_removed = pd.DataFrame(removed_records)
        df_removed.to_csv(OUT_REMOVED, index=False, encoding='utf-8-sig')
        print(f"[✔] Đã lưu danh sách loại bỏ vào: {OUT_REMOVED}")
    else:
        print(f"[✔] 100% doanh nghiệp không trùng bất kỳ email/domain nào trong Mail Tracker!")

    # 4. Sắp xếp lại file sạch: 100% Email lên đầu danh sách & đánh lại No.
    df_clean = pd.DataFrame(clean_records)
    has_em = df_clean[df_clean['Email'].str.strip().ne('') & df_clean['Email'].str.contains('@', na=False)].copy()
    no_em = df_clean[~df_clean.index.isin(has_em.index)].copy()

    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    for col in COLDMAIL_COLUMNS:
        if col not in df_sorted.columns:
            df_sorted[col] = ''
    df_sorted = df_sorted[COLDMAIL_COLUMNS]

    # Đồng bộ lưu tệp
    df_sorted.to_csv(FILE_MASTER, index=False, encoding='utf-8-sig')
    if FILE_CSDL_2COL.parent.exists():
        df_sorted.to_csv(FILE_CSDL_2COL, index=False, encoding='utf-8-sig')
        df_sorted.to_csv(FILE_CSDL_1ENR, index=False, encoding='utf-8-sig')

    final_has_em = len(has_em)
    print(f"[✔] Đã lưu đồng bộ thành công vào:")
    print(f"    1. {FILE_MASTER}")
    print(f"    2. {FILE_CSDL_2COL}")
    print(f"    3. {FILE_CSDL_1ENR}")
    print(f"[✔] Sẵn sàng gửi: {final_has_em:,} email sạch 100% (xếp toàn bộ từ No. 1 đến No. {final_has_em:,})")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()
