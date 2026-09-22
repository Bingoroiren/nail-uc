# -*- coding: utf-8 -*-
import sys
import pandas as pd
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

df_all = pd.read_csv('agency phần lan - tất cả chi nhánh.csv', encoding='utf-8-sig')
df_dedup = pd.read_csv('agency phần lan (đã lọc trùng).csv', encoding='utf-8-sig')

print("=" * 70)
print("             BÁO CÁO PHÂN TÍCH TỔNG QUAN DATA AGENCY PHẦN LAN")
print("=" * 70)

# 1. Thống kê số lượng bản ghi & Lọc trùng
print("\n--- 1. QUY MÔ & TỶ LỆ LỌC TRÙNG ---")
total_raw = len(df_all)
total_dedup = len(df_dedup)
dup_branches = total_raw - total_dedup
print(f"Tổng số lượt cơ sở / chi nhánh cào được : {total_raw:,} bản ghi")
print(f"Tổng số DOANH NGHIỆP DUY NHẤT (Đã lọc trùng): {total_dedup:,} doanh nghiệp")
print(f"Số chi nhánh / văn phòng phụ đã gộp      : {dup_branches:,} ({round(dup_branches/total_raw*100, 1)}%)")

# Kiểm tra tính duy nhất theo business_id (Y-tunnus)
bid_counts = df_dedup['business_id'].dropna().value_counts()
bid_unique = df_dedup['business_id'].nunique()
empty_bid = df_dedup['business_id'].isna().sum() + (df_dedup['business_id'] == '').sum()
print(f"Mã số doanh nghiệp (Y-tunnus) duy nhất  : {bid_unique:,} / {total_dedup:,}")
if empty_bid > 0:
    print(f"Số bản ghi không có business_id          : {empty_bid}")

# Kiểm tra trùng tên
name_clean = df_dedup['name'].str.lower().str.strip()
name_dup_count = total_dedup - name_clean.nunique()
print(f"Số tên doanh nghiệp duy nhất             : {name_clean.nunique():,} (Trùng tên khác Y-tunnus: {name_dup_count})")

# 2. Tỷ lệ phủ thông tin liên hệ
print("\n--- 2. CHẤT LƯỢNG THÔNG TIN LIÊN HỆ ---")
has_email = df_dedup['email'].notna() & (df_dedup['email'] != '')
has_phone = df_dedup['phone'].notna() & (df_dedup['phone'] != '')
has_web = df_dedup['website'].notna() & (df_dedup['website'] != '')
full_contact = has_email & has_phone & has_web
has_email_or_phone = has_email | has_phone

print(f"Có EMAIL                                 : {has_email.sum():,} ({round(has_email.mean()*100, 1)}%)")
print(f"Có SỐ ĐIỆN THOẠI                         : {has_phone.sum():,} ({round(has_phone.mean()*100, 1)}%)")
print(f"Có WEBSITE                               : {has_web.sum():,} ({round(has_web.mean()*100, 1)}%)")
print(f"Có CẢ 3 (Email + SĐT + Website) - VIP   : {full_contact.sum():,} ({round(full_contact.mean()*100, 1)}%)")
print(f"Có ÍT NHẤT 1 kênh liên lạc (Email/SĐT)  : {has_email_or_phone.sum():,} ({round(has_email_or_phone.mean()*100, 1)}%)")

# 3. Phân loại theo từ khóa ngành
print("\n--- 3. PHÂN BỐ THEO LĨNH VỰC HOẠT ĐỘNG ---")
kw_counts = df_dedup['keywords_found'].value_counts()
for kw, cnt in kw_counts.items():
    print(f"- {kw:40}: {cnt:,} ({round(cnt/total_dedup*100, 1)}%)")

# 4. Phân tích chi nhánh / Đa điểm
print("\n--- 4. MẠNG LƯỚI CHI NHÁNH & VĂN PHÒNG ---")
multi_offices = df_dedup[df_dedup['offices_count'] > 1]
print(f"Doanh nghiệp có từ 2 văn phòng/chi nhánh : {len(multi_offices):,} ({round(len(multi_offices)/total_dedup*100, 1)}%)")
top_multi = df_dedup.sort_values(by='offices_count', ascending=False)[['name', 'offices_count', 'cities_all']].head(5)
print("Top 5 agency có mạng lưới văn phòng lớn nhất Phần Lan:")
for _, row in top_multi.iterrows():
    print(f"  * {row['name']} : {row['offices_count']} chi nhánh (Tại: {str(row['cities_all'])[:60]}...)")

# 5. Phân bố địa lý (Top thành phố)
print("\n--- 5. TOP 10 KHU VỰC TẬP TRUNG DOANH NGHIỆP ---")
top_cities = df_dedup['city'].value_counts().head(10)
for city, cnt in top_cities.items():
    print(f"- {city:20}: {cnt:,} ({round(cnt/total_dedup*100, 1)}%)")

# 6. Phân tích email domain
print("\n--- 6. PHÂN TÍCH LOẠI EMAIL LIÊN HỆ ---")
emails = df_dedup[has_email]['email'].dropna().str.lower()
domains = emails.apply(lambda x: x.split('@')[-1] if '@' in x else '')
free_domains = {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'luukku.com', 'kolumbus.fi', 'netti.fi'}
is_free = domains.isin(free_domains)
print(f"Email tên miền doanh nghiệp riêng (Domain): {(~is_free).sum():,} ({round((~is_free).mean()*100, 1)}%)")
print(f"Email cá nhân/miễn phí (Gmail, Hotmail...): {is_free.sum():,} ({round(is_free.mean()*100, 1)}%)")

# Top email domains
print("Top 5 đuôi email phổ biến nhất:")
for dom, cnt in domains.value_counts().head(5).items():
    print(f"  * @{dom}: {cnt}")

# 7. Dữ liệu tài chính & Nhân sự
print("\n--- 7. THỐNG KÊ DOANH THU & QUY MÔ NHÂN SỰ ---")
has_turnover = df_dedup['turnover_k_eur'].notna() & (df_dedup['turnover_k_eur'] != '')
has_emp = df_dedup['employees'].notna() & (df_dedup['employees'] != '')
print(f"Số doanh nghiệp có số liệu Doanh thu      : {has_turnover.sum():,} ({round(has_turnover.mean()*100, 1)}%)")
print(f"Số doanh nghiệp có số liệu Nhân sự       : {has_emp.sum():,} ({round(has_emp.mean()*100, 1)}%)")
