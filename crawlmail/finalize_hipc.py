# -*- coding: utf-8 -*-
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

CSV_1ENR = "KR_SHIP_HIPC_1ENR.csv"
CSV_2COL = "KR_SHIP_HIPC_2COL.csv"

# 1. Đọc file
df = pd.read_csv(CSV_1ENR, encoding='utf-8-sig')
print(f"Tổng số doanh nghiệp: {len(df)}")

# 2. Làm sạch email rác & regex artifacts (ví dụ xeicon@2.3.3)
GARBAGE_EMAILS = ['xeicon@2.3.3', 'react-dom@', 'player-component@', 'hosting@gabia.com']

def clean_email(em):
    if pd.isna(em) or not str(em).strip() or str(em) == 'nan':
        return ''
    em_str = str(em).strip().lower()
    for g in GARBAGE_EMAILS:
        if g in em_str:
            return ''
    # Email phải có domain hợp lệ (.com, .net, .kr, .org, .co.kr...)
    if not re.search(r'\.[a-z]{2,}$', em_str):
        return ''
    return em_str

df['Email'] = df['Email'].apply(clean_email)

# 3. Làm sạch SĐT (luôn có nháy đơn, loại bỏ ký tự lạ)
def clean_phone(p):
    if pd.isna(p) or not str(p).strip() or str(p) == 'nan':
        return ''
    p_str = str(p).replace('\n', ' ').strip()
    p_clean = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_clean:
        return ''
    return f"'{p_clean}" if not p_clean.startswith("'") else p_clean

df['SDT'] = df['SDT'].apply(clean_phone)

# 4. Làm sạch Địa chỉ (loại bỏ ký tự icon map \ue0c8)
def clean_addr(a):
    if pd.isna(a) or not str(a).strip() or str(a) == 'nan':
        return ''
    return str(a).replace('\ue0c8', '').replace('\n', ' ').strip()

df['Dia chi'] = df['Dia chi'].apply(clean_addr)

# 5. Lưu lại 1ENR
df['No.'] = range(1, len(df) + 1)
df.to_csv(CSV_1ENR, index=False, encoding='utf-8-sig')

# 6. Sắp xếp 100% doanh nghiệp có email lên đầu danh sách cho 2COL
has_email = df[df['Email'] != ''].copy()
no_email = df[df['Email'] == ''].copy()
sorted_df = pd.concat([has_email, no_email], ignore_index=True)
sorted_df['No.'] = range(1, len(sorted_df) + 1)
sorted_df.to_csv(CSV_2COL, index=False, encoding='utf-8-sig')

# 7. Thống kê
print("=" * 65)
print("THỐNG KÊ LÀM GIÀU DỮ LIỆU KR_SHIP_HIPC")
print("=" * 65)
print(f"Tổng số công ty: {len(sorted_df)}")
print(f"Số công ty có Email B2B xác thực: {len(has_email)} ({len(has_email)/len(sorted_df)*100:.1f}%)")
print(f"Số công ty có SĐT: {len(sorted_df[sorted_df['SDT'] != ''])} ({len(sorted_df[sorted_df['SDT'] != ''])/len(sorted_df)*100:.1f}%)")
print(f"Số công ty có Website chính thức: {len(sorted_df[sorted_df['Lien He'].str.startswith('http') & (~sorted_df['Lien He'].str.contains('hipc.or.kr|kosic.or.kr'))])}")

print("\nDanh sách các công ty có Email B2B tiêu biểu:")
for idx, r in has_email.head(15).iterrows():
    c = r['Cong ty']
    sdt = r['SDT']
    em = r['Email']
    web = str(r['Lien He'])[:35]
    print(f"  {idx+1:2d}. {c:20} | SĐT: {sdt:18} | Email: {em:25} | Web: {web}")
