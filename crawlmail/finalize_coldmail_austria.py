# -*- coding: utf-8 -*-
"""
Chuan hoa file Cold Mail 20 cot chuan cho Agency Ao:
- Dau vao: AT_AGCY_COMB_2COL.csv (da duoc loc qua Mail Tracker & WKOS CleanData)
- Chi giu lai 2,038 cong ty CO EMAIL de san sang import gui mail ngay
- Chuan hoa 20 cot tieng Viet chuan:
  No., Cong ty, Chuc danh, Nguoi lien he, SDT, Lien He, Email, Lien He mail, Dia chi,
  Luong, Ngay dang, Han tuyen, Check gui, Last Subject, Last Body HTML, Trang thai Reply,
  Lan Follow-up, Ngay Follow-up gan nhat, Mailbox da dung, Category
- Dau ra: duy nhat 1 file AT_AGCY_COMB_2COL.csv tai thu muc goc
- Xoa bo cac file trung lap va file tam sau xu ly
"""

import os
import sys
import csv
from pathlib import Path

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_COMB = ROOT_DIR / "AT_AGCY_COMB_2COL.csv"
FINAL_FILE = ROOT_DIR / "AT_AGCY_COMB_2COL.csv"

# Cac file sau xu ly can xoa
FILES_TO_DELETE = [
    ROOT_DIR / "AT_AGCY_GMAP_2COL.csv",
    ROOT_DIR / "data" / "AT_AGCY_COMB_2COL.csv",
    ROOT_DIR / "data" / "AT_AGCY_COMB_2COL_pre_filter_backup.csv",
    ROOT_DIR / "data" / "AT_AGCY_REMOVED_TRACKER_BOUNCE.csv",
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def main():
    print("=" * 80)
    print("BAT DAU CHUAN HOA FILE COLD MAIL 20 COT & DON DEP DU LIEU")
    print("=" * 80)

    if not INPUT_COMB.exists():
        print(f"[-] Khong tim thay file: {INPUT_COMB}")
        return

    with open(INPUT_COMB, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[*] Tong so ban ghi doc duoc: {len(rows):,}")

    # Chỉ giữ các công ty CÓ EMAIL
    email_rows = [r for r in rows if r.get('Email', '').strip()]
    print(f"[*] So ban ghi CO EMAIL: {len(email_rows):,}")

    # Sắp xếp giảm dần theo Lead_Score (nếu có)
    try:
        email_rows.sort(key=lambda x: float(x.get('Lead_Score', 0) or 0), reverse=True)
    except Exception:
        pass

    final_rows = []
    for idx, r in enumerate(email_rows, start=1):
        company = r.get('Company', '').strip()
        email = r.get('Email', '').strip().lower()
        phone = r.get('Phone', '').strip()
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"

        website = r.get('Website', '').strip()
        addr = r.get('Address', '').strip()
        if not addr:
            pcode = r.get('Postal_Code', '').strip()
            city = r.get('City', '').strip()
            country = r.get('Country', '').strip() or 'Áo (Austria)'
            parts = [p for p in [pcode, city] if p]
            addr = ' '.join(parts) + (f", {country}" if country else "")

        cat = r.get('Category', '').strip()
        if not cat or cat.lower() in ['employment agency', 'personaldienstleister', 'austria agency']:
            cat = 'Cung ứng lao động Áo (Arbeitskräfteüberlassung)'

        legal = r.get('Legal_Form', '').strip()
        contact = r.get('Contact_Person', '').strip()

        final_rows.append({
            'No.': str(idx),
            'Công ty': company,
            'Chức danh': legal,
            'Người liên hệ': contact,
            'SĐT': phone,
            'Liên Hệ': website,
            'Email': email,
            'Liên Hệ mail': f"mailto:{email}" if email else '',
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat
        })

    # Ghi đè file chuẩn duy nhất
    with open(FINAL_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS_20)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"[OK] Da tao thanh cong file Cold Mail chuan duy nhat: {FINAL_FILE}")
    print(f"     -> Tong so dong: {len(final_rows):,} cong ty (100% CO EMAIL)")
    print(f"     -> 20 cot chuan Cold Mail tieng Viet")

    # Xoá các file sau xử lý
    print("\n[*] Dang xoa cac file sau khi xu ly...")
    for fpath in FILES_TO_DELETE:
        if fpath.exists():
            try:
                fpath.unlink()
                print(f"  [DELETED] {fpath.name}")
            except Exception as e:
                print(f"  [ERROR] Khong the xoa {fpath.name}: {e}")
        else:
            print(f"  [SKIP] Khong ton tai: {fpath.name}")

    print("\n🎉 HOAN TAT! Chi giu lai duy nhat 1 file chuan AT_AGCY_COMB_2COL.csv de gui mail.")

if __name__ == '__main__':
    main()
