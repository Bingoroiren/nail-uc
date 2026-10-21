# -*- coding: utf-8 -*-
"""
Trích xuất tệp KR_AGCY_MOEL_0RAW.xlsx sang KR_AGCY_MOEL_0RAW.csv
Quy chuẩn:
- 20 cột chuẩn Cold Mail UTF-8 with BOM (utf-8-sig)
- Lọc bỏ dòng rỗng, chuẩn hóa tên công ty, người đại diện, địa phương
- Điền đầy đủ thông tin phân loại doanh nghiệp (Cá nhân / Pháp nhân) và mốc cấp phép của Bộ Lao động MOEL
"""

import sys
import io
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

INPUT_XLSX = "KR_AGCY_MOEL_0RAW.xlsx"
OUTPUT_CSV = "KR_AGCY_MOEL_0RAW.csv"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

print(f"Đang đọc tệp {INPUT_XLSX}...")
df_raw = pd.read_excel(INPUT_XLSX, skiprows=2)

if 'Unnamed: 0' in df_raw.columns:
    df_raw = df_raw.drop(columns=['Unnamed: 0'])

df_raw = df_raw.dropna(subset=['사업장명'])
print(f"Số lượng cơ sở giới thiệu việc làm hợp lệ: {len(df_raw)}")

rows_20 = []
for idx, (_, r) in enumerate(df_raw.iterrows(), 1):
    comp_name = str(r['사업장명']).strip()
    business_type = str(r.get('사업자구분(개인/법인)', '')).strip()
    rep = str(r.get('대표자', '')).strip() if pd.notna(r.get('대표자')) else ''
    location = str(r.get('소재지', '')).strip() if pd.notna(r.get('소재지')) else ''
    
    desc = f"Văn phòng Giới thiệu Việc làm ({business_type}) - Giấy phép Bộ Lao động Hàn Quốc (MOEL)"
    category = f"Bộ Lao động Hàn Quốc (MOEL - 국내유료직업소개소 {business_type})"
    
    row = {
        'No.': idx,
        'Cong ty': comp_name,
        'Chuc danh': desc,
        'Nguoi lien he': rep,
        'SDT': '',
        'Lien He': 'http://www.moel.go.kr',
        'Email': '',
        'Lien He mail': '',
        'Dia chi': location,
        'Luong': '',
        'Ngay dang': '2026-08-10',
        'Han tuyen': '',
        'Check gui': '',
        'Last Subject': '',
        'Last Body HTML': '',
        'Trang thai Reply': '',
        'Lan Follow-up': '',
        'Ngay Follow-up gan nhat': '',
        'Mailbox da dung': '',
        'Category': category
    }
    rows_20.append(row)

df_out = pd.DataFrame(rows_20, columns=COLUMNS_20)
df_out.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

print(f"Đã xuất thành công sang {OUTPUT_CSV} với {len(df_out)} dòng theo chuẩn UTF-8 with BOM (utf-8-sig)!")
print("\n5 dòng đầu tiên:")
print(df_out[['No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'Dia chi']].head())
