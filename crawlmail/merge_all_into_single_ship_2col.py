# -*- coding: utf-8 -*-
"""
Hợp nhất toàn bộ dữ liệu Môi giới & Tuyển dụng Đóng tàu vào DUY NHẤT 1 TỆP CHỦ:
D:\glc\nail uc\KR_AGCY_SHIP_2COL.csv

Mục tiêu cốt lõi:
- TỐI ĐA HÓA CỘT EMAIL CHO CHIẾN DỊCH COLD MAIL B2B.
- Không tách file rời rạc.
- ĐẨY 100% CÁC CÔNG TY CÓ EMAIL LÊN ĐẦU DANH SÁCH (No. 1, 2, 3...).
- Giữ nguyên các hàng còn lại phía dưới.
- Chuẩn CSV UTF-8 with BOM (utf-8-sig), SĐT có nháy đơn '.
"""

import sys
import os
import re
import csv
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_2COL = str(ROOT_DIR / "KR_AGCY_SHIP_2COL.csv")
MASTER_1ENR = str(ROOT_DIR / "KR_AGCY_SHIP_1ENR.csv")
FMT_2COL = str(ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv")

CACHE_RECRUITERS = str(ROOT_DIR / "crawlmail" / "cache_ship_recruiters.json")
RECR_CSV = str(ROOT_DIR / "KR_AGCY_RECR_2COL.csv")

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

def clean_email(e):
    if not e:
        return ""
    return str(e).strip().lower().replace('%20', '')

def main():
    print("=" * 80)
    print("HỢP NHẤT TOÀN DIỆN VÀO DUY NHẤT 1 FILE MASTER: KR_AGCY_SHIP_2COL.csv")
    print("Tập trung tối đa hóa EMAIL - Đẩy 100% dòng có Email lên đầu")
    print("=" * 80)

    # 1. Đọc tệp Master 980 hiện có
    existing_rows = []
    seen_companies = set()
    seen_emails = set()

    if os.path.exists(MASTER_2COL):
        with open(MASTER_2COL, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                cname = r.get('Công ty', '').strip()
                em = clean_email(r.get('Email', ''))
                if em:
                    seen_emails.add(em)
                if cname:
                    seen_companies.add(cname)
                existing_rows.append(r)
        print(f"[*] Đã nạp tệp hiện có: {len(existing_rows)} đơn vị.")

    # 2. Đọc tệp tuyển dụng & visa có email (281 đơn vị)
    new_email_rows = []
    if os.path.exists(RECR_CSV):
        with open(RECR_CSV, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                em = clean_email(r.get('Email', ''))
                cname = r.get('Công ty', '').strip()
                if em and em not in seen_emails:
                    seen_emails.add(em)
                    new_email_rows.append(r)
        print(f"[+] Đã trích xuất thêm {len(new_email_rows)} đơn vị có 100% EMAIL THẬT từ dữ liệu tuyển dụng & visa!")

    # 3. Gộp toàn bộ vào 1 danh sách
    all_combined = new_email_rows + existing_rows

    # Khử trùng lặp theo Email (nếu trùng email thì giữ 1 bản ghi đầy đủ nhất)
    unique_rows = []
    email_tracker = set()
    company_tracker = set()

    for r in all_combined:
        em = clean_email(r.get('Email', ''))
        cname = r.get('Công ty', '').strip()

        if em:
            if em in email_tracker:
                continue
            email_tracker.add(em)
        else:
            if cname in company_tracker:
                continue
            company_tracker.add(cname)

        r['Email'] = em
        r['SĐT'] = clean_phone(r.get('SĐT', ''))
        unique_rows.append(r)

    # 4. QUY CHUẨN CỐT LÕI: ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU DANH SÁCH
    with_email = [r for r in unique_rows if r.get('Email')]
    without_email = [r for r in unique_rows if not r.get('Email')]

    # Sắp xếp trong nhóm with_email: ưu tiên đơn vị có cả SĐT lên trước
    with_email.sort(key=lambda x: (1 if x.get('SĐT') else 0), reverse=True)

    final_master_rows = with_email + without_email

    for idx, r in enumerate(final_master_rows, 1):
        r['No.'] = str(idx)

    # 5. Xuất đồng bộ ra các file Master
    for path in [MASTER_2COL, MASTER_1ENR, FMT_2COL]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(final_master_rows)
        print(f"[OK] Đã cập nhật tệp Master: {path}")

    # Xóa tệp phụ để tránh người dùng bị rối
    if os.path.exists(RECR_CSV):
        try:
            os.remove(RECR_CSV)
            print(f"[INFO] Đã xóa tệp phụ {RECR_CSV} để gom trọn gói vào 1 file duy nhất.")
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("TỔNG KẾT TỆP DUY NHẤT: KR_AGCY_SHIP_2COL.csv")
    print(f"  • Tổng số doanh nghiệp: {len(final_master_rows)}")
    print(f"  • SỐ CÔNG TY CÓ EMAIL (XẾP 100% LÊN ĐẦU TỆP): {len(with_email)}")
    print(f"  • Số công ty còn lại (có SĐT/Địa chỉ): {len(without_email)}")
    print("=" * 80)

if __name__ == "__main__":
    main()
