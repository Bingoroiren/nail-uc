# -*- coding: utf-8 -*-
"""
Script lọc trùng và lọc các công ty không liên quan cho KR_SHIP_HIPC_0RAW.csv:
1. Loại bỏ 5 công ty cano du thuyền giải trí / thể thao cá nhân (không phải xưởng đóng tàu thép/gia công tuyển thợ hàn/thợ đóng tàu).
2. Tích hợp sẵn thông tin SĐT, Website, Email đã xác minh từ KR_SHIP_DSTU_2COL.csv cho 30 công ty KOSIC.
3. Chuẩn hóa lại 20 cột, đánh lại số thứ tự No. từ 1 đến N.
4. Ghi đè vào KR_SHIP_HIPC_0RAW.csv với mã hóa utf-8-sig.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import re
import pandas as pd

INPUT_FILE = "KR_SHIP_HIPC_0RAW.csv"
DSTU_FILE = "KR_SHIP_DSTU_2COL.csv"

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_]', '', name)
    return n.lower()

# Đọc file gốc
df = pd.read_csv(INPUT_FILE, encoding='utf-8-sig')
print(f"Tổng số dòng ban đầu: {len(df)}")

# Danh sách từ khóa không liên quan (cano nước, thuyền lướt sóng cá nhân, thuyền buồm thể thao)
EXCLUDE_KEYWORDS = [
    '웨이크서핑보트', # Wakesurfing
    '수상레저보트',   # Water leisure
    '오락및스포츠용 보트', # Recreational sports boat
    '세일링요트',     # Sailing yacht
]

# Kiểm tra địa chỉ Yangpyeong RIB boat nội địa
def is_irrelevant(row):
    desc = str(row.get('Chuc danh', ''))
    addr = str(row.get('Dia chi', ''))
    cname = str(row.get('Cong ty', ''))
    
    # 1. Các keyword cano thể thao lướt sóng giải trí
    for kw in EXCLUDE_KEYWORDS:
        if kw in desc:
            return True, f"Thuyền/Cano giải trí thể thao cá nhân ({kw})"
            
    # 2. Xưởng xuồng hơi RIB vùng hồ núi Yangpyeong (không phải xưởng đóng tàu ven biển)
    if 'RIB보트' in desc and '양평' in addr:
        return True, "Xuồng hơi RIB cứu hộ vùng nội địa hồ sông Yangpyeong"
        
    return False, ""

# Tiến hành lọc
filtered_rows = []
removed_rows = []

for idx, row in df.iterrows():
    irr, reason = is_irrelevant(row)
    if irr:
        removed_rows.append((row['Cong ty'], reason))
    else:
        filtered_rows.append(row)

df_clean = pd.DataFrame(filtered_rows)
print(f"Đã loại bỏ {len(removed_rows)} công ty không liên quan:")
for c, r in removed_rows:
    print(f"  [-] {c:20} -> {r}")

print(f"Số công ty còn lại sau khi lọc: {len(df_clean)}")

# Đọc DSTU_FILE để map thông tin có sẵn nếu có
dstu = pd.read_csv(DSTU_FILE, encoding='utf-8-sig')
dstu['norm'] = dstu['Công ty'].apply(norm)
dstu_dict = {}
for _, r in dstu.iterrows():
    dstu_dict[r['norm']] = {
        'SDT': r.get('SĐT', ''),
        'Lien He': r.get('Liên Hệ', ''),
        'Email': r.get('Email', ''),
        'Dia chi': r.get('Địa chỉ', '')
    }

# Điền dữ liệu từ DSTU nếu cột trống
mapped_count = 0
for idx in df_clean.index:
    c_norm = norm(df_clean.at[idx, 'Cong ty'])
    if c_norm in dstu_dict:
        d = dstu_dict[c_norm]
        if pd.isna(df_clean.at[idx, 'Email']) or str(df_clean.at[idx, 'Email']).strip() == '':
            if pd.notna(d['Email']) and str(d['Email']).strip() != '' and str(d['Email']) != 'nan':
                df_clean.at[idx, 'Email'] = str(d['Email']).strip()
                mapped_count += 1
        if pd.isna(df_clean.at[idx, 'SDT']) or str(df_clean.at[idx, 'SDT']).strip() == '':
            if pd.notna(d['SDT']) and str(d['SDT']).strip() != '' and str(d['SDT']) != 'nan':
                phone = str(d['SDT']).strip()
                df_clean.at[idx, 'SDT'] = f"'{phone}" if not phone.startswith("'") else phone

print(f"Đã đối soát và tích hợp dữ liệu sẵn có cho {mapped_count} công ty từ KR_SHIP_DSTU_2COL.csv")

# Chuẩn hóa lại 20 cột chuẩn
COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

for col in COLUMNS_20:
    if col not in df_clean.columns:
        df_clean[col] = ''

df_clean = df_clean[COLUMNS_20]
df_clean['No.'] = range(1, len(df_clean) + 1)

# Format SĐT luôn có nháy đơn
def format_phone(p):
    if pd.isna(p) or not str(p).strip() or str(p) == 'nan':
        return ''
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

df_clean['SDT'] = df_clean['SDT'].apply(format_phone)

# Lưu lại file 0RAW đã sạch
df_clean.to_csv(INPUT_FILE, index=False, encoding='utf-8-sig')
print(f"Đã lưu thành công {len(df_clean)} công ty sạch vào {INPUT_FILE}")
