# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU FILE TỔNG SK_AGCY_ALL_2COL VỚI MAIL TRACKER VÀ XOÁ KHỎI DANH SÁCH
-------------------------------------------------------------------------
Nhiệm vụ:
1. Đọc Mail Tracker - mail.csv để thu thập toàn bộ Email & Domain doanh nghiệp đã liên lạc/phản hồi.
2. Đối chiếu với file Master hoàn thiện: SK_AGCY_ALL_2COL.csv (3,845 cty, 1,402 email).
3. XOÁ HOÀN TOÀN các doanh nghiệp trùng lặp ra khỏi danh sách.
4. Xuất file backup và file audit các bản ghi đã xoá: SK_AGCY_DA_XOA_TRUNG_TRACKER.csv.
5. Tạo lại trọn bộ các danh sách sạch 100% chuẩn bị cho chiến dịch:
   - SK_AGCY_ALL_2COL.csv: File tổng sạch, đánh lại No.
   - SK_AGCY_SAN_SANG_GUI.csv: Toàn bộ cty có email (đã loại bỏ trùng tracker, xếp lead mới lên đầu).
   - SK_AGCY_LEAD_MOI_CHUA_GUI.csv: Chỉ chứa lead MỚI TINH (Chưa gửi), sẵn sàng import gửi ngay.
"""

import sys
import os
import re
import shutil
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_CHOTHUE = ROOT_DIR / "Slovakia - Cho thuê LĐ 02.10  - Cho thuê LĐ Cập nhật 02.10.2026.csv"
FILE_MASTER = ROOT_DIR / "SK_AGCY_ALL_2COL.csv"

OUT_DELETED = ROOT_DIR / "SK_AGCY_DA_XOA_TRUNG_TRACKER.csv"
OUT_READY_FULL = ROOT_DIR / "SK_AGCY_SAN_SANG_GUI.csv"
OUT_FRESH_ONLY = ROOT_DIR / "SK_AGCY_LEAD_MOI_CHUA_GUI.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'centrum.sk', 'centrum.cz', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz'
}

def norm_phone(p):
    if not p:
        return ""
    d = re.sub(r'[^\d]', '', str(p))
    if d.startswith('421'):
        d = d[3:]
    if d.startswith('0'):
        d = d[1:]
    return d[-9:] if len(d) >= 9 else d

def clean_phone_display(raw):
    if not raw:
        return ""
    s = str(raw).strip()
    return f"'{s}" if not s.startswith("'") else s

def main():
    print("=" * 80)
    print(" ĐỐI CHIẾU SK_AGCY_ALL_2COL VỚI MAIL TRACKER & XOÁ KHỎI DANH SÁCH")
    print("=" * 80)

    # 1. Đọc Mail Tracker
    tracker_emails = {}
    tracker_corp_domains = {}
    if FILE_TRACKER.exists():
        df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_tr.iterrows():
            nguoi_gui = str(r.get('Người gửi', '')).strip().lower()
            subject = str(r.get('Subject', '')).strip()
            tinh_trang = str(r.get('Tình trạng phản hồi', '')).strip()
            note_str = tinh_trang if tinh_trang else (subject if subject else "Ghi nhận trong Mail Tracker")
            
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', nguoi_gui):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
                    tracker_emails[em] = f"Trùng Email Tracker: {em} ({note_str[:35]})"
                    d = em.split('@')[1]
                    if d not in GENERIC_DOMAINS:
                        tracker_corp_domains[d] = f"Trùng Domain Doanh Nghiệp Tracker: @{d} ({note_str[:35]})"
        tracker_base_domains = {}
        for d, note in tracker_corp_domains.items():
            base = d.split('.')[0]
            if len(base) >= 5 and base not in ['gmail', 'yahoo', 'hotmail', 'outlook', 'centrum', 'zoznam', 'post', 'azet', 'seznam', 'inbox']:
                tracker_base_domains[base] = (d, note)
                
        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} email & {len(tracker_corp_domains):,} tên miền doanh nghiệp.")
    else:
        tracker_base_domains = {}
        print(f"[!] Không tìm thấy: {FILE_TRACKER}")

    # 2. Đọc file Cho thuê LĐ 02.10 (phục vụ phân loại lead mới vs đã gọi SĐT)
    chothue_phones = {}
    chothue_emails = {}
    if FILE_CHOTHUE.exists():
        df_ct = pd.read_csv(FILE_CHOTHUE, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_ct.iterrows():
            p_raw = str(r.get('SĐT', '')).strip()
            em_raw = str(r.get('Email', '')).strip().lower()
            check_gui = str(r.get('Check gửi', '')).strip()
            tt_reply = str(r.get('Trạng thái Reply', '')).strip()
            status_note = check_gui if check_gui else (tt_reply if tt_reply else "Cho thuê LĐ 02.10")
            
            for p in re.findall(r'\d{8,}', re.sub(r'[^\d]', '', p_raw)):
                np = norm_phone(p)
                if len(np) >= 8:
                    chothue_phones[np] = f"Cho thuê LĐ [{status_note}]"
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', em_raw):
                chothue_emails[em] = f"Cho thuê LĐ [{status_note}]"
        print(f"[+] Đã nạp từ Cho thuê LĐ 02.10: {len(chothue_phones):,} SĐT & {len(chothue_emails):,} Email.")

    # 3. Đọc dữ liệu Master SK_AGCY_ALL_2COL.csv
    if not FILE_MASTER.exists():
        print(f"[ERROR] Không tìm thấy file: {FILE_MASTER}")
        return

    df_master = pd.read_csv(FILE_MASTER, encoding='utf-8-sig', dtype=str).fillna('')
    total_master = len(df_master)
    print(f"\n[*] Đang nạp dữ liệu Master: {total_master:,} doanh nghiệp...")

    # Backup file gốc trước khi xoá
    backup_file = ROOT_DIR / "SK_AGCY_ALL_2COL_BACKUP_BEFORE_DEDUP.csv"
    shutil.copy2(FILE_MASTER, backup_file)
    print(f"[+] Đã tạo file Backup an toàn: {backup_file.name}")

    # 4. Kiểm tra đối chiếu và tách lọc
    deleted_records = []
    clean_records = []

    for idx, r in df_master.iterrows():
        comp = str(r.get('Công ty', '')).strip()
        em = str(r.get('Email', '')).strip().lower()
        p_raw = str(r.get('SĐT', '')).strip()
        np = norm_phone(p_raw)

        # Kiểm tra trùng với Mail Tracker
        is_tracker_duplicate = False
        del_reason = ""

        if em and em in tracker_emails:
            is_tracker_duplicate = True
            del_reason = tracker_emails[em]
        elif em and '@' in em:
            d = em.split('@')[1]
            if d in tracker_corp_domains:
                is_tracker_duplicate = True
                del_reason = tracker_corp_domains[d]
            else:
                base = d.split('.')[0]
                if base in tracker_base_domains:
                    orig_d, note = tracker_base_domains[base]
                    is_tracker_duplicate = True
                    del_reason = f"Trùng thương hiệu/hệ sinh thái Tracker: @{d} (từ {orig_d} - {note[:30]})"

        row_dict = r.to_dict()
        row_dict['SĐT'] = clean_phone_display(p_raw)

        if is_tracker_duplicate:
            row_dict['Lý do xoá'] = del_reason
            deleted_records.append(row_dict)
        else:
            # Kiểm tra trạng thái với Cho thuê LĐ
            is_contacted_phone = False
            reasons = []
            if len(np) >= 8 and np in chothue_phones:
                is_contacted_phone = True
                reasons.append(chothue_phones[np])
            if em and em in chothue_emails:
                is_contacted_phone = True
                reasons.append(chothue_emails[em])

            if is_contacted_phone:
                row_dict['Check gửi'] = "Đã liên lạc trước"
                detail_history = " | ".join(dict.fromkeys(reasons))
                current_reply = str(row_dict.get('Trạng thái Reply', '')).strip()
                if current_reply:
                    row_dict['Trạng thái Reply'] = f"{current_reply} | {detail_history}"
                else:
                    row_dict['Trạng thái Reply'] = detail_history
            else:
                row_dict['Check gửi'] = "Chưa gửi"
                
            clean_records.append(row_dict)

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐỐI CHIẾU & XOÁ TRÙNG MAIL TRACKER:")
    print(f" [*] Tổng số bản ghi ban đầu              : {total_master:,} công ty")
    print(f" [*] ĐÃ XOÁ KHỎI DANH SÁCH (Trùng Tracker): {len(deleted_records):,} công ty")
    print(f" [*] SỐ DOANH NGHIỆP CÒN LẠI SAU KHI XOÁ   : {len(clean_records):,} công ty")
    print("=" * 80)

    # 5. Xuất file các bản ghi ĐÃ XOÁ để kiểm tra (Audit File)
    if deleted_records:
        df_del = pd.DataFrame(deleted_records)
        df_del.to_csv(OUT_DELETED, index=False, encoding='utf-8-sig')
        print(f"\n[✔] Đã lưu danh sách các công ty bị xoá vào: {OUT_DELETED.name}")
        for r in deleted_records:
            print(f"   -> [XOÁ] {r.get('Công ty')} | {r.get('Email')} | {r.get('Lý do xoá')}")

    # 6. Cập nhật lại Master SK_AGCY_ALL_2COL.csv (Đã xoá bỏ hoàn toàn trùng tracker)
    for i, r in enumerate(clean_records, 1):
        r['No.'] = i

    df_clean_master = pd.DataFrame(clean_records)
    for col in COLUMNS_20:
        if col not in df_clean_master.columns:
            df_clean_master[col] = ''
    df_clean_master = df_clean_master[COLUMNS_20]
    df_clean_master.to_csv(FILE_MASTER, index=False, encoding='utf-8-sig')
    print(f"\n[✔] Đã cập nhật file Master: {FILE_MASTER.name} ({len(df_clean_master):,} công ty - Đã loại bỏ 100% trùng tracker)")

    # 7. Phân tách danh sách có Email
    df_clean_has_email = df_clean_master[df_clean_master['Email'].str.strip() != ''].copy()
    print(f"[*] Tổng số doanh nghiệp CÓ EMAIL sau khi xoá: {len(df_clean_has_email):,} công ty")

    fresh_email_records = df_clean_has_email[df_clean_has_email['Check gửi'] == 'Chưa gửi'].to_dict('records')
    contacted_email_records = df_clean_has_email[df_clean_has_email['Check gửi'] == 'Đã liên lạc trước'].to_dict('records')

    print(f"   - Lead MỚI TINH (Chưa gửi - Sẵn sàng gửi ngay)       : {len(fresh_email_records):,} công ty")
    print(f"   - Lead đã liên lạc trước (Trùng SĐT Cho thuê LĐ 02.10): {len(contacted_email_records):,} công ty")

    # 8. Xuất File SẴN SÀNG GỬI (SK_AGCY_SAN_SANG_GUI.csv)
    # Xếp lead mới lên đầu, lead đã gọi xuống cuối
    full_ready = fresh_email_records + contacted_email_records
    for i, r in enumerate(full_ready, 1):
        r['No.'] = i

    df_ready = pd.DataFrame(full_ready)[COLUMNS_20]
    df_ready.to_csv(OUT_READY_FULL, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã tạo file: {OUT_READY_FULL.name} ({len(df_ready):,} dòng - Đẩy {len(fresh_email_records):,} lead mới lên đầu)")

    # 9. Xuất File CHỈ CHỨA LEAD MỚI (SK_AGCY_LEAD_MOI_CHUA_GUI.csv)
    for i, r in enumerate(fresh_email_records, 1):
        r['No.'] = i

    df_fresh = pd.DataFrame(fresh_email_records)[COLUMNS_20]
    df_fresh.to_csv(OUT_FRESH_ONLY, index=False, encoding='utf-8-sig')
    print(f"[✔] Đã tạo file: {OUT_FRESH_ONLY.name} ({len(df_fresh):,} lead MỚI TINH - 100% sạch, sẵn sàng gửi ngay)")
    print("\n" + "=" * 80)
    print(" HOÀN TẤT TOÀN DIỆN!")
    print("=" * 80)

if __name__ == "__main__":
    main()
