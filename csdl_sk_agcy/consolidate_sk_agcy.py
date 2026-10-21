# -*- coding: utf-8 -*-
"""
Consolidate Slovak Employment Agencies from web directories:
1. Gộp dữ liệu từ personalneagentury.sk (14) và greenpages.sk (45).
2. Khử trùng lặp theo tên công ty và tên miền website.
3. Xuất file theo quy chuẩn:
   - csdl_sk_agcy/SK_AGCY_DIR_0RAW.csv (File thô tổng hợp)
   - csdl_sk_agcy/SK_AGCY_DIR_1ENR.csv (Chuẩn 20 cột CSDL chi tiết)
   - csdl_sk_agcy/SK_AGCY_DIR_2COL.csv (Chuẩn 20 cột Cold Mail, SĐT có nháy đơn ', 100% email lên đầu)
"""

import sys
import re
import csv
import pandas as pd
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path("D:/glc/nail uc")
AGCY_DIR = ROOT_DIR / "csdl_sk_agcy"

RAW_0RAW = AGCY_DIR / "SK_AGCY_DIR_0RAW.csv"
ENR_1ENR = AGCY_DIR / "SK_AGCY_DIR_1ENR.csv"
COL_2COL = AGCY_DIR / "SK_AGCY_DIR_2COL.csv"

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def clean_phone(p):
    if not p or str(p).strip() == 'nan':
        return ''
    s = str(p).strip()
    return s if s.startswith("'") else f"'{s}"

def main():
    print("=" * 70)
    print(" TỔNG HỢP VÀ CHUẨN HÓA CSDL MÔI GIỚI LAO ĐỘNG SLOVAKIA")
    print("=" * 70)

    f_pagent = AGCY_DIR / "personalneagentury_database.csv"
    f_green = AGCY_DIR / "greenpages_agcy_database.csv"

    records = []
    seen = {}

    # 1. Đọc personalneagentury
    if f_pagent.exists():
        df_pa = pd.read_csv(f_pagent, dtype=str).fillna('')
        print(f"[*] Đọc personalneagentury.sk: {len(df_pa)} bản ghi.")
        for _, r in df_pa.iterrows():
            cname = r.get('Name', '').strip()
            key = re.sub(r'[^a-zA-Z0-9]', '', cname).lower()
            if not key:
                continue
            item = {
                'Name': cname,
                'Address': r.get('Address', ''),
                'City': r.get('City', ''),
                'Postal_Code': '',
                'Phone': r.get('Phone', ''),
                'Email': r.get('Email', ''),
                'Web': r.get('Web', ''),
                'Director': '',
                'Category': r.get('Category', 'Personálne agentúry'),
                'Source': 'personalneagentury.sk',
                'Detail_URL': r.get('Detail_URL', '')
            }
            seen[key] = item
            records.append(item)

    # 2. Đọc greenpages
    if f_green.exists():
        df_gp = pd.read_csv(f_green, dtype=str).fillna('')
        print(f"[*] Đọc greenpages.sk: {len(df_gp)} bản ghi.")
        for _, r in df_gp.iterrows():
            cname = r.get('Name', '').strip()
            key = re.sub(r'[^a-zA-Z0-9]', '', cname).lower()
            if not key:
                continue

            if key in seen:
                # Bổ sung thông tin nếu thiếu
                prev = seen[key]
                if not prev['Director'] and r.get('Director'):
                    prev['Director'] = r.get('Director')
                if not prev['Phone'] and r.get('Phone'):
                    prev['Phone'] = r.get('Phone')
                if not prev['Email'] and r.get('Email'):
                    prev['Email'] = r.get('Email')
                if not prev['Web'] and r.get('Web'):
                    prev['Web'] = r.get('Web')
                prev['Source'] = f"{prev['Source']} + greenpages.sk"
            else:
                item = {
                    'Name': cname,
                    'Address': r.get('Address', ''),
                    'City': r.get('City', ''),
                    'Postal_Code': r.get('Postal_Code', ''),
                    'Phone': r.get('Phone', ''),
                    'Email': r.get('Email', ''),
                    'Web': r.get('Web', ''),
                    'Director': r.get('Director', ''),
                    'Category': r.get('Category', 'Dočasné zamestnávanie'),
                    'Source': 'greenpages.sk',
                    'Detail_URL': r.get('Detail_URL', '')
                }
                seen[key] = item
                records.append(item)

    unique_list = list(seen.values())
    print(f"\n[+] Tổng số cơ sở dữ liệu sau khử trùng: {len(unique_list)} đại lý.")

    # Xuất 0RAW
    keys_0raw = ['Name', 'Address', 'City', 'Postal_Code', 'Phone', 'Email', 'Web', 'Director', 'Category', 'Source', 'Detail_URL']
    with open(RAW_0RAW, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys_0raw)
        w.writeheader()
        w.writerows(unique_list)
    print(f"[✓] Đã tạo file thô 0RAW: {RAW_0RAW.name}")

    # Xuất 1ENR (Chuẩn 20 cột CSDL doanh nghiệp)
    enr_headers = [
        'No.', 'Công ty', 'IČO', 'SĐT', 'Web', 'Email', 'Địa chỉ', 'Thành phố', 
        'Mã bưu điện', 'NACE', 'NACE Popis', 'Loại hình', 'Quy mô nhân sự', 
        'Doanh thu (EUR)', 'Lợi nhuận (EUR)', 'Năm tài chính', 'Ngày thành lập', 
        'Độ uy tín thuế', 'Category', 'Source'
    ]
    enr_rows = []
    for idx, it in enumerate(unique_list, 1):
        enr_rows.append({
            'No.': idx,
            'Công ty': it['Name'],
            'IČO': '',
            'SĐT': clean_phone(it['Phone']),
            'Web': it['Web'],
            'Email': it['Email'],
            'Địa chỉ': it['Address'],
            'Thành phố': it['City'],
            'Mã bưu điện': it['Postal_Code'],
            'NACE': '78.20',
            'NACE Popis': it['Category'],
            'Loại hình': 's.r.o. / a.s.',
            'Quy mô nhân sự': '',
            'Doanh thu (EUR)': '',
            'Lợi nhuận (EUR)': '',
            'Năm tài chính': '',
            'Ngày thành lập': '',
            'Độ uy tín thuế': '',
            'Category': it['Category'],
            'Source': it['Source']
        })

    with open(ENR_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=enr_headers)
        w.writeheader()
        w.writerows(enr_rows)
    print(f"[✓] Đã tạo file 1ENR: {ENR_1ENR.name}")

    # Xuất 2COL (Chuẩn 20 cột Cold Mail: 100% email lên đầu)
    with_email = []
    without_email = []

    for it in unique_list:
        row_2col = {
            'No.': '',
            'Công ty': it['Name'],
            'Chức danh': 'Employment & Staffing Agency',
            'Người liên hệ': it['Director'],
            'SĐT': clean_phone(it['Phone']),
            'Liên Hệ': it['Web'] or it['Detail_URL'],
            'Email': it['Email'],
            'Liên Hệ mail': it['Web'] or it['Detail_URL'],
            'Địa chỉ': it['Address'],
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': it['Category']
        }
        if it['Email']:
            with_email.append(row_2col)
        else:
            without_email.append(row_2col)

    final_2col = with_email + without_email
    for i, r in enumerate(final_2col, 1):
        r['No.'] = i

    with open(COL_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COL_20_HEADERS)
        w.writeheader()
        w.writerows(final_2col)

    print(f"[✓] Đã tạo file 2COL: {COL_2COL.name}")
    print("\n" + "=" * 70)
    print(f" HOÀN TẤT! CSDL MÔI GIỚI LAO ĐỘNG SLOVAKIA:")
    print(f"  - Thư mục CSDL:    {AGCY_DIR}")
    print(f"  - Tổng số đại lý:  {len(final_2col)}")
    print(f"  - Đại lý có Email: {len(with_email)} (100% đẩy lên đầu file 2COL)")
    print("=" * 70)

if __name__ == '__main__':
    main()
