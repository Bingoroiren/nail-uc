# -*- coding: utf-8 -*-
"""
Script hợp nhất và khử trùng toàn diện các tệp KR_ thành đúng 3 tệp master:
1. KR_SHIP_COMB_2COL.csv (Đóng tàu: Xưởng tàu, Thầu phụ HD Hyundai, KOSIC, Xưởng tuyển thợ hàn E-7-3)
2. KR_CREW_SEAN_2COL.csv (Tàu biển tuyển thủy thủ: Hãng tàu viễn dương, Seanet, Tanker, Bulk, Tàu kéo E-10)
3. KR_AGCY_COMB_2COL.csv (Agency môi giới: Naver Maps 인력/파견 + Doanh nghiệp cấp phép MOEL)

Quy chuẩn:
- 20 cột Cold Mail chuẩn UTF-8 with BOM (utf-8-sig).
- Số điện thoại luôn có nháy đơn (').
- Lọc bỏ 100% email rác, template, regex artifacts.
- Đẩy 100% công ty có Email B2B lên đầu danh sách.
- Đánh lại No. từ 1 đến N.
"""

import sys
import io
import os
import re
import shutil
import urllib.parse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

GARBAGE_PATTERNS = [
    'react-dom', 'player-component', 'hosting@gabia.com', 'gabia.com', 'webmaster@',
    'youremail', 'your-email', 'yourname', 'yourcompany', 'someone', 'john.doe',
    'user@domain', 'name@domain', 'example.com', 'domain.com', 'email@email.com',
    'sentry.wixpress', 'sentry.io', 'wix.com', 'wordpress.com', 'no-reply',
    'donotreply', 'privacy@', 'gdpr@', 'postmaster@', 'support@wix.com', 'xeicon@2.3.3'
]

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_\[\]]', '', name)
    return n.lower()

def clean_phone(p):
    if pd.isna(p) or not str(p).strip() or str(p) == 'nan':
        return ''
    p_str = str(p).replace('\n', ' ').strip()
    p_clean = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_clean:
        return ''
    return f"'{p_clean}" if not p_clean.startswith("'") else p_clean

def clean_email(em):
    if pd.isna(em) or not str(em).strip() or str(em) == 'nan':
        return ''
    em_str = urllib.parse.unquote(str(em).strip().lower())
    for g in GARBAGE_PATTERNS:
        if g in em_str:
            return ''
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em_str):
        return ''
    if not re.search(r'\.[a-z]{2,}$', em_str):
        return ''
    return em_str

def clean_addr(a):
    if pd.isna(a) or not str(a).strip() or str(a) == 'nan':
        return ''
    return str(a).replace('\ue0c8', '').replace('\n', ' ').strip()

def merge_two_rows(r1, r2):
    """Gộp 2 dòng cùng 1 cty: ưu tiên dòng có email, sau đó dòng có sđt/web"""
    res = r1.copy()
    # Nếu r1 không có email mà r2 có -> lấy r2
    if not res['Email'] and r2['Email']:
        res['Email'] = r2['Email']
    if not res['SDT'] and r2['SDT']:
        res['SDT'] = r2['SDT']
    if (not res['Lien He'] or 'hipc' in str(res['Lien He']) or 'kosic' in str(res['Lien He'])) and r2['Lien He']:
        res['Lien He'] = r2['Lien He']
    if not res['Dia chi'] and r2['Dia chi']:
        res['Dia chi'] = r2['Dia chi']
    if not res['Nguoi lien he'] and r2['Nguoi lien he']:
        res['Nguoi lien he'] = r2['Nguoi lien he']
    # Category gộp nếu khác nhau
    c1, c2 = str(res.get('Category', '')), str(r2.get('Category', ''))
    if c1 and c2 and c1 != c2:
        if c2 not in c1:
            res['Category'] = f"{c1} | {c2}"
    return res

def process_and_save(df_input, output_filename, title):
    print(f"\n--- Đang xử lý: {title} ({output_filename}) ---")
    
    # Chuẩn hóa tên cột
    rename_map = {
        'Công ty': 'Cong ty', 'Chức danh': 'Chuc danh', 'Người liên hệ': 'Nguoi lien he',
        'SĐT': 'SDT', 'Liên Hệ': 'Lien He', 'Liên Hệ mail': 'Lien He mail',
        'Địa chỉ': 'Dia chi', 'Lương': 'Luong', 'Ngày đăng': 'Ngay dang',
        'Hạn tuyển': 'Han tuyen', 'Check gửi': 'Check gui', 'Trạng thái Reply': 'Trang thai Reply',
        'Lần Follow-up': 'Lan Follow-up', 'Ngày Follow-up gần nhất': 'Ngay Follow-up gan nhat',
        'Mailbox đã dùng': 'Mailbox da dung'
    }
    df = df_input.rename(columns=rename_map).copy()
    
    for c in COLUMNS_20:
        if c not in df.columns:
            df[c] = ''
    df = df[COLUMNS_20].copy()

    # Làm sạch từng trường
    df['Email'] = df['Email'].apply(clean_email)
    df['SDT'] = df['SDT'].apply(clean_phone)
    df['Dia chi'] = df['Dia chi'].apply(clean_addr)
    df['norm'] = df['Cong ty'].apply(norm)

    # Khử trùng gộp thông tin
    merged_rows = {}
    order = []
    for _, row in df.iterrows():
        n = row['norm']
        if not n:
            continue
        if n not in merged_rows:
            merged_rows[n] = row.to_dict()
            order.append(n)
        else:
            merged_rows[n] = merge_two_rows(merged_rows[n], row.to_dict())

    clean_list = [merged_rows[n] for n in order]
    clean_df = pd.DataFrame(clean_list)
    clean_df = clean_df.drop(columns=['norm'], errors='ignore')

    # Đẩy 100% công ty có email lên đầu
    with_email = clean_df[clean_df['Email'] != ''].copy()
    without_email = clean_df[clean_df['Email'] == ''].copy()
    
    sorted_df = pd.concat([with_email, without_email], ignore_index=True)
    sorted_df['No.'] = range(1, len(sorted_df) + 1)
    sorted_df = sorted_df[COLUMNS_20]

    sorted_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
    print(f"  [V] Đã lưu {len(sorted_df)} công ty vào {output_filename}")
    print(f"      - Có Email B2B : {len(with_email)} ({len(with_email)/len(sorted_df)*100:.1f}%)")
    print(f"      - Có SĐT       : {len(sorted_df[sorted_df['SDT'] != ''])} ({len(sorted_df[sorted_df['SDT'] != ''])/len(sorted_df)*100:.1f}%)")
    return sorted_df

# ============================================================
# THỰC THI GỘP 3 NHÓM
# ============================================================

def get_file(fname):
    if os.path.exists(fname): return fname
    arc = os.path.join('archive_kr_components', fname)
    if os.path.exists(arc): return arc
    return fname

# 1. NHÓM 1: ĐÓNG TÀU & THẦU PHỤ (HIPC + WELD)
df_hipc = pd.read_csv(get_file('KR_SHIP_HIPC_2COL.csv'), encoding='utf-8-sig')
df_weld = pd.read_csv(get_file('KR_WELD_E703_2COL.csv'), encoding='utf-8-sig')
ship_combined = pd.concat([df_hipc, df_weld], ignore_index=True)
df_ship_final = process_and_save(ship_combined, 'KR_SHIP_COMB_2COL.csv', 'LĨNH VỰC 1: ĐÓNG TÀU & THẦU PHỤ E-7-3')

# 2. NHÓM 2: TÀU TUYỂN THỦY THỦ (DSTU HÃNG TÀU)
df_dstu = pd.read_csv(get_file('KR_SHIP_DSTU_2COL.csv'), encoding='utf-8-sig')
crew_dstu = df_dstu[~df_dstu['Category'].str.contains('기자재|Vật tư', na=False)].copy()
df_crew_final = process_and_save(crew_dstu, 'KR_CREW_SEAN_2COL.csv', 'LĨNH VỰC 2: TÀU BIỂN TUYỂN THỦY THỦ E-10')

# 3. NHÓM 3: AGENCY MÔI GIỚI (NVER + MOEL VEN BIỂN)
df_nver = pd.read_csv(get_file('KR_AGCY_NVER_2COL.csv'), encoding='utf-8-sig')
df_moel = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
agcy_combined = pd.concat([df_nver, df_moel], ignore_index=True)
df_agcy_final = process_and_save(agcy_combined, 'KR_AGCY_COMB_2COL.csv', 'LĨNH VỰC 3: AGENCY MÔI GIỚI & VĂN PHÒNG NHÂN LỰC')

print("\n" + "=" * 65)
print("HOÀN TẤT GỘP VÀ KHỬ TRÙNG 3 LĨNH VỰC THÀNH CÔNG!")
print("=" * 65)
