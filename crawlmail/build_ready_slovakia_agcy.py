# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU DỮ LIỆU & TẠO DANH SÁCH SỬ DỤNG NGAY CHO SLOVAKIA (AGENCY / CHO THUÊ LĐ)
Nguồn đối chiếu:
1. Mail Tracker - mail.csv (227 email đối tác đã gửi/phản hồi)
2. Slovakia - Cho thuê LĐ 02.10  - Cho thuê LĐ Cập nhật 02.10.2026.csv (Lịch sử gọi điện, WhatsApp, trao đổi của GLC)
3. SK_AGCY_ALL_2COL.csv (Tệp dữ liệu đang làm giàu từ Google Maps & Zlaté Stránky)

Đầu ra:
1. SK_AGCY_SAN_SANG_GUI.csv (Toàn bộ công ty có Email, xếp Chưa gửi lên đầu, Đã liên lạc trước xuống dưới)
2. SK_AGCY_LEAD_MOI_CHUA_GUI.csv (Chỉ chứa các doanh nghiệp MỚI 100% chưa từng liên lạc, nạp gửi ngay)
"""

import sys
import os
import re
import csv
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_CHOTHUE = ROOT_DIR / "Slovakia - Cho thuê LĐ 02.10  - Cho thuê LĐ Cập nhật 02.10.2026.csv"
FILE_MASTER = ROOT_DIR / "SK_AGCY_ALL_2COL.csv"

OUT_READY_FULL = ROOT_DIR / "SK_AGCY_SAN_SANG_GUI.csv"
OUT_FRESH_ONLY = ROOT_DIR / "SK_AGCY_LEAD_MOI_CHUA_GUI.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def norm_phone(p):
    """Chuẩn hóa số điện thoại để so khớp chính xác 9 chữ số cuối."""
    if not p:
        return ""
    d = re.sub(r'[^\d]', '', str(p))
    if d.startswith('421'):
        d = d[3:]
    if d.startswith('0'):
        d = d[1:]
    return d[-9:] if len(d) >= 9 else d

def clean_phone_display(raw):
    """Giữ nguyên nháy đơn cho SĐT."""
    if not raw:
        return ""
    s = str(raw).strip()
    return f"'{s}" if not s.startswith("'") else s

def main():
    print("=" * 80)
    print(" ĐỐI CHIẾU DỮ LIỆU & TẠO DANH SÁCH SỬ DỤNG NGAY - SLOVAKIA MANPOWER")
    print("=" * 80)

    # 1. Thu thập Email từ Mail Tracker
    tracker_emails = {}
    if FILE_TRACKER.exists():
        df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_tr.iterrows():
            nguoi_gui = str(r.get('Người gửi', '')).strip().lower()
            subject = str(r.get('Subject', '')).strip()
            tinh_trang = str(r.get('Tình trạng phản hồi', '')).strip()
            note_str = tinh_trang if tinh_trang else (subject if subject else "Đã ghi nhận trong Mail Tracker")
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', nguoi_gui):
                if 'glcquocte' not in em:
                    tracker_emails[em] = f"Mail Tracker [{note_str[:40]}]"
        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} email đối tác đã tương tác.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 2. Thu thập SĐT & Email từ file Cho thuê LĐ 02.10
    chothue_phones = {}
    chothue_emails = {}
    if FILE_CHOTHUE.exists():
        df_ct = pd.read_csv(FILE_CHOTHUE, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_ct.iterrows():
            p_raw = str(r.get('SĐT', '')).strip()
            em_raw = str(r.get('Email', '')).strip().lower()
            check_gui = str(r.get('Check gửi', '')).strip()
            tt_reply = str(r.get('Trạng thái Reply', '')).strip()
            status_note = check_gui if check_gui else (tt_reply if tt_reply else "Đã có trong file Cho thuê LĐ 02.10")
            
            # Lưu SĐT chuẩn hóa
            for p in re.findall(r'\d{8,}', re.sub(r'[^\d]', '', p_raw)):
                np = norm_phone(p)
                if len(np) >= 8:
                    chothue_phones[np] = f"Cho thuê LĐ [{status_note}]"
                    
            # Lưu Email nếu có
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', em_raw):
                chothue_emails[em] = f"Cho thuê LĐ [{status_note}]"
        print(f"[+] Đã nạp từ Cho thuê LĐ 02.10: {len(chothue_phones):,} số điện thoại & {len(chothue_emails):,} email.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_CHOTHUE}")

    # 3. Đọc dữ liệu Master SK_AGCY_ALL_2COL.csv
    if not FILE_MASTER.exists():
        print(f"[ERROR] Không tìm thấy file: {FILE_MASTER}")
        return

    df_master = pd.read_csv(FILE_MASTER, encoding='utf-8-sig', dtype=str).fillna('')
    total_all = len(df_master)
    print(f"\n[*] Đang đọc dữ liệu Master: {total_all:,} doanh nghiệp...")

    # Lọc các công ty CÓ EMAIL
    has_email_df = df_master[df_master['Email'].str.strip() != ''].copy()
    print(f"[*] Tổng số doanh nghiệp đã có Email: {len(has_email_df):,}")

    matched_records = []
    fresh_records = []

    for idx, r in has_email_df.iterrows():
        comp = str(r.get('Công ty', '')).strip()
        em = str(r.get('Email', '')).strip().lower()
        p_raw = str(r.get('SĐT', '')).strip()
        np = norm_phone(p_raw)

        is_contacted = False
        reasons = []

        # Đối chiếu Email với Mail Tracker
        if em in tracker_emails:
            is_contacted = True
            reasons.append(tracker_emails[em])

        # Đối chiếu SĐT với Cho thuê LĐ 02.10
        if len(np) >= 8 and np in chothue_phones:
            is_contacted = True
            reasons.append(chothue_phones[np])

        # Đối chiếu Email với Cho thuê LĐ 02.10
        if em in chothue_emails:
            is_contacted = True
            reasons.append(chothue_emails[em])

        row_dict = r.to_dict()
        row_dict['SĐT'] = clean_phone_display(p_raw)

        if is_contacted:
            row_dict['Check gửi'] = "Đã liên lạc trước"
            detail_history = " | ".join(dict.fromkeys(reasons)) # Khử trùng ghi chú
            current_reply = str(row_dict.get('Trạng thái Reply', '')).strip()
            if current_reply:
                row_dict['Trạng thái Reply'] = f"{current_reply} | {detail_history}"
            else:
                row_dict['Trạng thái Reply'] = detail_history
            matched_records.append(row_dict)
        else:
            row_dict['Check gửi'] = "Chưa gửi"
            fresh_records.append(row_dict)

    print("\n" + "=" * 80)
    print(f" KẾT QUẢ ĐỐI CHIẾU CHÍNH XÁC:")
    print(f" [*] ĐÃ LIÊN LẠC TRƯỚC (Trùng Email Tracker hoặc SĐT Cho thuê LĐ): {len(matched_records):,} công ty")
    print(f" [*] LEAD MỚI TINH (Chưa gửi bao giờ - Sẵn sàng gửi ngay)       : {len(fresh_records):,} công ty")
    print(f" [*] TỔNG CÔNG TY CÓ EMAIL SỬ DỤNG ĐƯỢC NGAY                      : {len(has_email_df):,} công ty")
    print("=" * 80 + "\n")

    # 4. Xuất File 1: SK_AGCY_SAN_SANG_GUI.csv (Chứa toàn bộ có Email, xếp Chưa gửi lên đầu)
    full_ready_list = fresh_records + matched_records
    for i, r in enumerate(full_ready_list, 1):
        r['No.'] = i

    df_full_ready = pd.DataFrame(full_ready_list)
    for col in COLUMNS_20:
        if col not in df_full_ready.columns:
            df_full_ready[col] = ''
    df_full_ready = df_full_ready[COLUMNS_20]
    df_full_ready.to_csv(OUT_READY_FULL, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã tạo file: {OUT_READY_FULL.name} ({len(df_full_ready):,} dòng - Đẩy {len(fresh_records):,} lead mới lên đầu)")

    # 5. Xuất File 2: SK_AGCY_LEAD_MOI_CHUA_GUI.csv (Chỉ chứa lead mới 100% chưa gửi)
    for i, r in enumerate(fresh_records, 1):
        r['No.'] = i

    df_fresh = pd.DataFrame(fresh_records)
    for col in COLUMNS_20:
        if col not in df_fresh.columns:
            df_fresh[col] = ''
    df_fresh = df_fresh[COLUMNS_20]
    df_fresh.to_csv(OUT_FRESH_ONLY, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã tạo file: {OUT_FRESH_ONLY.name} ({len(df_fresh):,} lead MỚI TINH - Sẵn sàng gửi mail)")

    # 6. Cập nhật đồng bộ ngược lại vào SK_AGCY_ALL_2COL.csv (giữ nguyên các dòng chưa có email ở cuối)
    no_email_df = df_master[df_master['Email'].str.strip() == ''].copy()
    no_email_records = no_email_df.to_dict('records')
    for r in no_email_records:
        r['SĐT'] = clean_phone_display(r.get('SĐT', ''))

    all_combined = full_ready_list + no_email_records
    for i, r in enumerate(all_combined, 1):
        r['No.'] = i

    df_master_updated = pd.DataFrame(all_combined)
    for col in COLUMNS_20:
        if col not in df_master_updated.columns:
            df_master_updated[col] = ''
    df_master_updated = df_master_updated[COLUMNS_20]
    df_master_updated.to_csv(FILE_MASTER, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã cập nhật nhãn 'Đã liên lạc trước' vào file gốc: {FILE_MASTER.name}")

if __name__ == "__main__":
    main()
