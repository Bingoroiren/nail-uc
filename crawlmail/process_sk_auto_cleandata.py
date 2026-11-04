# -*- coding: utf-8 -*-
"""
XỬ LÝ TỆP (xong 10_15) SK_AUTO_SLVD - CleanData.csv:
1. Đối chiếu Mail Tracker (Mail Tracker - mail.csv) và dữ liệu gốc.
2. Loại bỏ toàn bộ các công ty đã phản hồi (Replied) và mail lỗi (Bounced / không dùng được).
3. Cập nhật trạng thái 'Check gửi' từ 'Da_Gui_Truoc' thành 'OK' cho 100% các công ty có email hợp lệ.
4. Đẩy toàn bộ các công ty có Email lên đầu file, đánh lại số thứ tự No. từ 1 đến hết.
5. Bảo toàn chuẩn UTF-8 with BOM (utf-8-sig) và SĐT có nháy đơn '.
6. Xuất file backup và file audit các bản ghi đã loại bỏ.
"""

import sys
import re
import shutil
import pandas as pd
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_CSV = ROOT_DIR / "(xong 10_15) SK_AUTO_SLVD - CleanData.csv"
BACKUP_CSV = ROOT_DIR / "(xong 10_15) SK_AUTO_SLVD - CleanData_pre_update_backup.csv"

FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
OUT_REMOVED_CSV = ROOT_DIR / "archive" / "sk_old_industries" / "SK_AUTO_SLVD_DA_LOAI_BO_REPLY_BOUNCE.csv"
OUT_READY_CSV = ROOT_DIR / "SK_AUTO_SLVD_READY_OK.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def clean_phone(p):
    if not p or str(p).strip() == '' or str(p) == 'nan':
        return ''
    s = str(p).strip()
    return f"'{s}" if not s.startswith("'") else s

def main():
    print("=" * 80)
    print(" XỬ LÝ (xong 10_15) SK_AUTO_SLVD - CleanData.csv")
    print(" ĐỐI CHIẾU TRACKER, LOẠI BỎ REPLY/BOUNCE & CẬP NHẬT 'Check gửi' = 'OK'")
    print("=" * 80)

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy file: {TARGET_CSV}")
        return

    # 1. Đọc Mail Tracker
    tracker_emails = {}
    tracker_domains = {}
    GENERIC_DOMS = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'centrum.sk', 'zoznam.sk', 'post.sk', 'azet.sk', 'seznam.cz', 'inbox.lv', 'email.cz'}

    if FILE_TRACKER.exists():
        df_tr = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df_tr.iterrows():
            sender = r.get('Người gửi', '').strip().lower()
            content = r.get('Nội dung', '')
            status = r.get('Tình trạng phản hồi', '').strip()
            subj = r.get('Subject', '').strip()
            note = status if status else (subj if subj else 'Mail Tracker')
            
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', f"{sender} {subj} {content}".lower()):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
                    tracker_emails[em] = note
                    d = em.split('@')[-1]
                    if d not in GENERIC_DOMS:
                        tracker_domains[d] = note
        print(f"[+] Đã nạp từ Mail Tracker: {len(tracker_emails):,} emails & {len(tracker_domains):,} corporate domains.")
    else:
        print(f"[!] Không tìm thấy file: {FILE_TRACKER}")

    # 2. Tạo bản sao lưu an toàn
    shutil.copy2(TARGET_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo backup an toàn tại: {BACKUP_CSV.name}")

    # 3. Đọc dữ liệu CleanData
    df = pd.read_csv(TARGET_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total_initial = len(df)
    initial_with_email = len([1 for _, r in df.iterrows() if r.get('Email', '').strip() and r.get('Email', '').strip() != 'nan'])
    print(f"[*] Tổng số dòng ban đầu: {total_initial:,} (Trong đó có Email: {initial_with_email:,})\n")

    # 4. Phân loại và lọc
    valid_with_email = []
    valid_without_email = []
    removed_records = []

    for idx, r in df.iterrows():
        comp = r.get('Công ty', '').strip()
        em = r.get('Email', '').strip().lower()
        rep = r.get('Trạng thái Reply', '').strip()
        chk = r.get('Check gửi', '').strip()
        phone = clean_phone(r.get('SĐT', ''))
        
        row_dict = {col: r.get(col, '') for col in COLUMNS_20}
        row_dict['SĐT'] = phone

        if not em or em == 'nan':
            # Dòng không có email -> giữ lại ở phần dưới, Check gửi để trống
            row_dict['Check gửi'] = ''
            row_dict['Trạng thái Reply'] = ''
            valid_without_email.append(row_dict)
            continue

        # Có email: kiểm tra xem có thuộc diện bị loại bỏ không
        remove_reason = None
        dom = em.split('@')[-1] if '@' in em else ''

        # A. Đã phản hồi
        if 'reply' in rep.lower() or 'phản hồi' in rep.lower():
            remove_reason = f"Đã phản hồi (Ghi nhận: {rep})"
        elif em in tracker_emails:
            remove_reason = f"Đã phản hồi trong Mail Tracker: {tracker_emails[em]}"
        elif dom in tracker_domains:
            remove_reason = f"Domain doanh nghiệp đã phản hồi trong Mail Tracker: @{dom} ({tracker_domains[dom]})"
        # B. Mail lỗi / bounce
        elif any(k in rep.lower() for k in ['bounce', 'không dùng được', 'khong dung duoc', 'lỗi', 'loi']):
            remove_reason = f"Mail lỗi / Bounce: {rep}"
        # C. Lỗi cú pháp / rác
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
            remove_reason = f"Mail lỗi cú pháp / npm string: {em}"
        elif any(bad in em for bad in ['leaflet', 'sentry', 'wixpress', 'wordpress', 'example', 'youremail', 'your-email']):
            remove_reason = f"Mail rác / placeholder: {em}"

        if remove_reason:
            log_row = dict(row_dict)
            log_row['Lý do loại bỏ'] = remove_reason
            removed_records.append(log_row)
        else:
            # Hợp lệ -> Chuyển Check gửi từ Da_Gui_Truoc thành OK!
            row_dict['Check gửi'] = 'OK'
            row_dict['Trạng thái Reply'] = ''  # Xóa sạch trạng thái lỗi/reply vì đã loại bỏ
            valid_with_email.append(row_dict)

    print(f"[✔] Số công ty có Email hợp lệ (sẵn sàng gửi 'OK'): {len(valid_with_email):,}")
    print(f"[✔] Số công ty chưa có Email (giữ lại ở phần dưới): {len(valid_without_email):,}")
    print(f"[✖] Số công ty đã bị loại bỏ (Reply + Bounced): {len(removed_records):,}")

    # Đánh lại số thứ tự No.
    final_rows = []
    current_no = 1
    for row in valid_with_email:
        row['No.'] = str(current_no)
        final_rows.append(row)
        current_no += 1

    for row in valid_without_email:
        row['No.'] = str(current_no)
        final_rows.append(row)
        current_no += 1

    # 5. Ghi đè vào file đích chính
    df_final = pd.DataFrame(final_rows, columns=COLUMNS_20)
    df_final.to_csv(TARGET_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[+] Đã cập nhật tệp mục tiêu: {TARGET_CSV.name} ({len(df_final):,} dòng)")

    # 6. Xuất tệp chuyên dụng READY TO SEND (chỉ 100% dòng có Email hợp lệ, Check gửi = OK)
    df_ready = pd.DataFrame(valid_with_email, columns=COLUMNS_20)
    df_ready.to_csv(OUT_READY_CSV, index=False, encoding='utf-8-sig')
    print(f"[+] Đã xuất tệp sẵn sàng gửi: {OUT_READY_CSV.name} ({len(df_ready):,} dòng)")

    # 7. Xuất tệp Audit các bản ghi đã loại bỏ
    if removed_records:
        OUT_REMOVED_CSV.parent.mkdir(parents=True, exist_ok=True)
        audit_cols = list(COLUMNS_20) + ['Lý do loại bỏ']
        df_removed = pd.DataFrame(removed_records, columns=audit_cols)
        df_removed.to_csv(OUT_REMOVED_CSV, index=False, encoding='utf-8-sig')
        print(f"[+] Đã xuất nhật ký loại bỏ: {OUT_REMOVED_CSV.name} ({len(df_removed):,} dòng)")

    print("\n" + "=" * 80)
    print(" HOÀN TẤT XỬ LÝ DỮ LIỆU SK_AUTO_SLVD - CleanData.csv THÀNH CÔNG!")
    print(f" [*] Đã loại bỏ 100% công ty Reply & Mail lỗi: {len(removed_records):,} công ty")
    print(f" [*] Đã cập nhật Check gửi 'Da_Gui_Truoc' -> 'OK': {len(valid_with_email):,} công ty")
    print(f" [*] Đẩy 100% công ty có Email lên đầu tệp CSV")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()
