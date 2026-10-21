# -*- coding: utf-8 -*-
"""
Chuẩn hóa và đồng bộ KR_SHIP_DSTU_2COL.csv ra root workspace:
- 20 cột chuẩn Cold Mail UTF-8 with BOM (utf-8-sig)
- 963 công ty (Hãng tàu, Đại lý tàu biển, Công ty Vật tư & Thiết bị đóng tàu)
- 614 Email B2B sạch 100%
- Đẩy 100% doanh nghiệp có Email lên đầu tệp
- SĐT luôn có nháy đơn '
"""

import re
import sys
import pandas as pd

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

INPUT_FILE = "archive_kr_components/KR_SHIP_DSTU_2COL.csv"
OUTPUT_FILE = "KR_SHIP_DSTU_2COL.csv"

def clean_phone(p):
    if not p or str(p).lower() == 'nan':
        return ""
    p = str(p).strip().replace('\n', ' ')
    p = re.sub(r'[^\d\+\-\s\(\)]', '', p).strip()
    if not p:
        return ""
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(e):
    if not e or str(e).lower() == 'nan':
        return ""
    e = str(e).strip().lower().replace('%20', '')
    if any(j in e for j in ['sentry', 'wix', 'bootstrap', 'example', 'domain', 'test@test', 'email@email']):
        return ""
    if '@' not in e or '.' not in e:
        return ""
    return e

df = pd.read_csv(INPUT_FILE, encoding='utf-8-sig')
df.columns = COLUMNS_20

df['SDT'] = df['SDT'].apply(clean_phone)
df['Email'] = df['Email'].apply(clean_email)

# Sắp xếp đẩy 100% có Email lên đầu
df['has_email'] = df['Email'].apply(lambda x: 1 if str(x).strip() and '@' in str(x) else 0)
df['has_phone'] = df['SDT'].apply(lambda x: 1 if str(x).strip() else 0)
df = df.sort_values(by=['has_email', 'has_phone'], ascending=[False, False]).reset_index(drop=True)
df = df.drop(columns=['has_email', 'has_phone'])
df['No.'] = range(1, len(df) + 1)

df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')

has_em = df['Email'].dropna().apply(lambda x: str(x).strip() != '').sum()
has_ph = df['SDT'].dropna().apply(lambda x: str(x).strip() != '').sum()

print("=" * 70)
print(f"CHUAN HOA THANH CONG: {OUTPUT_FILE}")
print(f"Total rows: {len(df)}")
print(f"With Email (100% on top): {has_em}")
print(f"With Phone: {has_ph}")
print("=" * 70)
