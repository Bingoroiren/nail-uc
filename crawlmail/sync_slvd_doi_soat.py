# -*- coding: utf-8 -*-
"""
Sync đối soát data from 'SK_AUTO_SLVD - đối soát.csv' into 'SK_MANU_SLVD_2COL.csv'.
1. Đối chiếu theo Tên công ty và Email để phát hiện các email đã gửi trước.
2. Đánh dấu 'Check gửi' = 'Da_Gui_Truoc', 'Liên Hệ mail' = 'đã gửi mail ngày 14/10'.
3. Đồng bộ đầy đủ lịch sử: 'Last Subject', 'Last Body HTML', 'Trạng thái Reply' (bao gồm 96 bounce), 'Mailbox đã dùng', 'Lần Follow-up'.
4. Giữ nguyên 661 email mới (chưa gửi) để sẵn sàng chạy chiến dịch tiếp theo.
5. Bảo toàn định dạng SĐT có nháy đơn ' và chuẩn UTF-8 with BOM (utf-8-sig).
"""

import sys
import shutil
import pandas as pd
from pathlib import Path

# Fix encoding on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DOI_SOAT_CSV = ROOT_DIR / "SK_AUTO_SLVD - đối soát.csv"
TARGET_CSV = ROOT_DIR / "SK_MANU_SLVD_2COL.csv"
BACKUP_CSV = ROOT_DIR / "SK_MANU_SLVD_2COL_backup_before_sync.csv"

def main():
    print("=" * 70)
    print(" ĐỐI CHIẾU VÀ ĐÁNH DẤU EMAIL ĐÃ GỬI TỪ FILE ĐỐI SOÁT")
    print("=" * 70)

    if not DOI_SOAT_CSV.exists():
        print(f"[-] Không tìm thấy file đối soát: {DOI_SOAT_CSV}")
        return

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy file đích: {TARGET_CSV}")
        return

    # Backup trước khi ghi đè
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo bản backup an toàn tại: {BACKUP_CSV.name}")

    # Đọc 2 file
    df_ds = pd.read_csv(DOI_SOAT_CSV, dtype=str)
    df_manu = pd.read_csv(TARGET_CSV, dtype=str)

    # Lọc các dòng đã gửi thực tế trong file đối soát
    ds_sent = df_ds[df_ds['Check gửi'] == 'Da_Gui_Truoc'].copy()
    print(f"[*] Số lượng bản ghi đã gửi trong file đối soát: {len(ds_sent)}")

    # Xây dựng bảng tra cứu
    by_comp = {}
    by_email = {}
    for idx, r in ds_sent.iterrows():
        c_name = str(r.get('Công ty') or '').strip().lower()
        em = str(r.get('Email') or '').strip().lower()
        if c_name:
            by_comp[c_name] = r
        if em and em != 'nan':
            by_email[em] = r

    matched_comp = 0
    matched_email_only = 0
    total_matched = 0

    # Duyệt qua từng dòng của SK_MANU_SLVD_2COL.csv
    for idx, row in df_manu.iterrows():
        c_name = str(row.get('Công ty') or '').strip().lower()
        em = str(row.get('Email') or '').strip().lower()

        match = None
        if c_name in by_comp:
            match = by_comp[c_name]
            matched_comp += 1
        elif em and em != 'nan' and em in by_email:
            match = by_email[em]
            matched_email_only += 1

        if match is not None:
            total_matched += 1
            # Đánh dấu đã gửi
            df_manu.at[idx, 'Check gửi'] = 'Da_Gui_Truoc'
            df_manu.at[idx, 'Liên Hệ mail'] = match.get('Liên Hệ mail') or 'đã gửi mail ngày 14/10'
            df_manu.at[idx, 'Ngày đăng'] = match.get('Ngày đăng') or '14/10/2026'
            df_manu.at[idx, 'Last Subject'] = match.get('Last Subject') or ''
            df_manu.at[idx, 'Last Body HTML'] = match.get('Last Body HTML') or ''
            
            # Cập nhật trạng thái phản hồi / bounce
            reply_val = match.get('Trạng thái Reply')
            if pd.notna(reply_val) and str(reply_val).strip() and str(reply_val).strip() != 'nan':
                df_manu.at[idx, 'Trạng thái Reply'] = str(reply_val).strip()
            
            # Cập nhật thông tin gửi
            df_manu.at[idx, 'Lần Follow-up'] = match.get('Lần Follow-up') or '0.0'
            df_manu.at[idx, 'Mailbox đã dùng'] = match.get('Mailbox đã dùng') or ''

    # Chuẩn hóa SĐT có nháy đơn '
    def format_phone(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip() == 'nan':
            return ""
        s = str(val).strip()
        return s if s.startswith("'") else f"'{s}"

    df_manu['SĐT'] = df_manu['SĐT'].apply(format_phone)

    # Thống kê
    total_rows = len(df_manu)
    total_with_email = df_manu['Email'].notna().sum()
    unsent_emails = total_with_email - total_matched

    print("\n" + "-" * 50)
    print(" KẾT QUẢ ĐỐI SOÁT VÀ ĐỒNG BỘ:")
    print(f"  - Tổng số doanh nghiệp trong file: {total_rows:,}")
    print(f"  - Tổng số doanh nghiệp có Email:   {total_with_email:,}")
    print(f"  - ĐÃ GỬI TRƯỚC (Da_Gui_Truoc):     {total_matched:,}")
    print(f"      + Khớp theo Tên công ty:       {matched_comp:,}")
    print(f"      + Khớp theo Email phụ:         {matched_email_only:,}")
    print(f"  - CHƯA GỬI (Email mới sẵn sàng):   {unsent_emails:,}")
    bounces = df_manu['Trạng thái Reply'].notna().sum()
    print(f"  - Email lỗi / Bounce đã lưu vết:   {bounces:,}")
    print("-" * 50)

    # Lưu lại file theo chuẩn utf-8-sig
    df_manu.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"[✓] Đã ghi đè cập nhật vào file: {TARGET_CSV.name}")
    print("=" * 70)

if __name__ == '__main__':
    main()
