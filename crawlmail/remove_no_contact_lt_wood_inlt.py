# -*- coding: utf-8 -*-
"""
LOẠI BỎ CÁC CÔNG TY HOÀN TOÀN KHÔNG CÓ SĐT VÀ EMAIL TRONG LT_WOOD_INLT_2COL.csv
=============================================================================
Yêu cầu người dùng: Xóa các công ty không có cả SĐT lẫn Email (23 công ty rỗng liên hệ).
Giữ lại: 2,592 công ty có ít nhất SĐT hoặc Email:
- 1,429 công ty có Email (xếp ở các dòng 1..1,429 trên cùng).
- 1,163 công ty chỉ có SĐT (xếp ở các dòng 1,430..2,592).
Đồng bộ:
- LT_WOOD_INLT_2COL.csv
- csdl_mlt/LT_WOOD_INLT_2COL.csv
- archive/lt_lithuania/LT_WOOD_INLT_2COL.csv
- Ghi nhật ký audit: archive/lt_lithuania/LT_WOOD_INLT_DA_LOAI_BO_KHONG_SDT_EMAIL.csv
"""

import sys
import shutil
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV = ROOT_DIR / "LT_WOOD_INLT_2COL.csv"
BACKUP_CSV = ROOT_DIR / "LT_WOOD_INLT_2COL_pre_remove_empty_contact_backup.csv"

OUT_REMOVED_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_INLT_DA_LOAI_BO_KHONG_SDT_EMAIL.csv"

SYNC_2COL_CSDL = ROOT_DIR / "csdl_mlt" / "LT_WOOD_INLT_2COL.csv"
SYNC_2COL_ARCHIVE = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WOOD_INLT_2COL.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def main():
    print("=" * 80)
    print(" 🚀 TIẾN HÀNH LOẠI BỎ DOANH NGHIỆP KHÔNG CÓ CẢ SĐT LẪN EMAIL")
    print("    Tệp nguồn: LT_WOOD_INLT_2COL.csv")
    print("=" * 80)

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy file: {TARGET_CSV}")
        return

    # 1. Backup
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo backup: {BACKUP_CSV.name}")

    # 2. Đọc dữ liệu
    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_before = len(df)
    print(f"[*] Tổng số doanh nghiệp trước khi lọc: {total_before:,}")

    # 3. Phân loại
    has_contact = []
    removed_no_contact = []

    for idx, r in df.iterrows():
        phone = r.get('SĐT', '').strip()
        email = r.get('Email', '').strip()
        row_dict = {col: r.get(col, '') for col in COLUMNS_20}

        if not phone and not email:
            log_row = dict(row_dict)
            log_row['Lý do loại bỏ'] = 'Rỗng hoàn toàn cả SĐT lẫn Email (Không thể liên hệ)'
            removed_no_contact.append(log_row)
        else:
            has_contact.append(row_dict)

    print(f"[*] Số doanh nghiệp bị loại bỏ (không có SĐT & Email): {len(removed_no_contact)}")
    print(f"[*] Số doanh nghiệp giữ lại (có SĐT hoặc Email)      : {len(has_contact)}")

    # 4. Sắp xếp: Với Email lên đầu (1..1429), Chỉ có SĐT xếp sau (1430..2592)
    with_email = [r for r in has_contact if r.get('Email', '').strip()]
    phone_only = [r for r in has_contact if not r.get('Email', '').strip()]

    print(f"    - Có Email (xếp dòng 1..{len(with_email)})      : {len(with_email):,}")
    print(f"    - Chỉ có SĐT (xếp dòng {len(with_email)+1}..{len(has_contact)}) : {len(phone_only):,}")

    sorted_all = with_email + phone_only
    for i, r in enumerate(sorted_all, 1):
        r['No.'] = str(i)

    df_clean = pd.DataFrame(sorted_all, columns=COLUMNS_20)

    # 5. Lưu đè file chính
    df_clean.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[✓] Đã cập nhật file chính: {TARGET_CSV.name} ({len(df_clean):,} dòng)")

    # 6. Đồng bộ sang csdl_mlt và archive
    if SYNC_2COL_CSDL.parent.exists():
        df_clean.to_csv(SYNC_2COL_CSDL, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ sang: {SYNC_2COL_CSDL}")
    if SYNC_2COL_ARCHIVE.parent.exists():
        df_clean.to_csv(SYNC_2COL_ARCHIVE, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã đồng bộ sang: {SYNC_2COL_ARCHIVE}")

    # 7. Lưu audit danh sách bị loại bỏ
    if removed_no_contact:
        OUT_REMOVED_CSV.parent.mkdir(parents=True, exist_ok=True)
        cols_log = COLUMNS_20 + ['Lý do loại bỏ']
        df_removed = pd.DataFrame(removed_no_contact, columns=cols_log)
        df_removed.to_csv(OUT_REMOVED_CSV, index=False, encoding='utf-8-sig')
        print(f"[✓] Đã lưu tệp audit loại bỏ tại: {OUT_REMOVED_CSV.name} ({len(removed_no_contact)} bản ghi)")

    print("\n" + "=" * 80)
    print("🎉 HOÀN THÀNH LOẠI BỎ DOANH NGHIỆP RỖNG LIÊN HỆ!")
    print(f"    - File chính: LT_WOOD_INLT_2COL.csv ({len(df_clean):,} doanh nghiệp có thể liên hệ)")
    print("=" * 80)

if __name__ == "__main__":
    main()

