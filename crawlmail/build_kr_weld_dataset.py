# -*- coding: utf-8 -*-
"""
TỔNG HỢP VÀ THIẾT LẬP DANH BẠ TOÀN DIỆN MÔI GIỚI & NHÀ THẦU THỢ HÀN ĐÓNG TÀU (E-7-3)
Tên tệp đích chuẩn 17 ký tự: KR_WELD_COMB_0RAW.csv

Các nguồn thành phần:
1. 536 Văn phòng Môi giới việc làm tại các Thủ phủ đóng tàu Hàn Quốc:
   - Ulsan Dong-gu (HD Hyundai Heavy, Hyundai Mipo)
   - Geoje (Hanwha Ocean, Samsung Heavy)
   - Yeongam & Mokpo (HD Hyundai Samho, KCN Thợ hàn Daebul)
   - Jinhae & Changwon (K Shipbuilding)
   - Tongyeong (HSG Seongdong)
   - Busan Yeongdo (HJ Shipbuilding)
2. 123 Công ty Thầu phụ Đóng tàu nội bộ xưởng HD Hyundai Heavy Industries (HIPC)
3. 293 Doanh nghiệp đang có tin tuyển dụng Thợ hàn đóng tàu thực tế trên Cổng QG Work24 & Saramin
"""

import os
import re
import sys
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

OUTPUT_FILE = "KR_WELD_COMB_0RAW.csv"

def clean_phone(p):
    if not p or str(p).lower() == 'nan':
        return ""
    p = str(p).strip().replace('\n', ' ')
    p = re.sub(r'[^\d\+\-\s\(\)]', '', p).strip()
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(e):
    if not e or str(e).lower() == 'nan':
        return ""
    e = str(e).strip().lower().replace('%20', '')
    if any(j in e for j in ['sentry', 'wix', 'bootstrap', 'example', 'domain']):
        return ""
    return e

def main():
    print("=" * 70)
    print(" BẮT ĐẦU XÂY DỰNG TẬP DỮ LIỆU MÔI GIỚI & THẦU PHỤ THỢ HÀN TÀU (KR_WELD_COMB)")
    print("=" * 70)

    combined_rows = []
    seen_names = set()

    # -------------------------------------------------------------------------
    # NGUỒN 1: Các tin tuyển dụng thợ hàn thực tế từ Work24 & Saramin (Đã có sẵn)
    # -------------------------------------------------------------------------
    weld_e703_path = "archive_kr_components/KR_WELD_E703_2COL.csv"
    if os.path.exists(weld_e703_path):
        df_e703 = pd.read_csv(weld_e703_path, encoding='utf-8-sig')
        print(f"[Nguồn 1] Tuyển dụng Thợ hàn thực tế (Work24 & Saramin): {len(df_e703)} bản ghi")
        for _, r in df_e703.iterrows():
            cname = str(r['Cong ty']).strip()
            if not cname or cname == 'nan':
                continue
            norm_name = re.sub(r'[\s\(\)주식회사]', '', cname)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            combined_rows.append({
                'Cong ty': cname,
                'Chuc danh': str(r.get('Chuc danh', 'Đang tuyển Thợ hàn vỏ tàu / đường ống E-7-3')),
                'Nguoi lien he': str(r.get('Nguoi lien he', 'Phòng Tuyển Dụng / Nhân Sự')),
                'SDT': clean_phone(r.get('SDT', '')),
                'Lien He': str(r.get('Lien He', '')),
                'Email': clean_email(r.get('Email', '')),
                'Lien He mail': str(r.get('Lien He mail', '')),
                'Dia chi': str(r.get('Dia chi', '')),
                'Luong': str(r.get('Luong', 'Thỏa thuận theo bậc tay nghề E-7-3')),
                'Ngay dang': str(r.get('Ngay dang', '2026-10-06')),
                'Han tuyen': str(r.get('Han tuyen', 'Tuyển liên tục')),
                'Category': str(r.get('Category', 'Tuyển dụng Thợ hàn đóng tàu (E-7-3)'))
            })

    # -------------------------------------------------------------------------
    # NGUỒN 2: 123 Công ty Thầu phụ Đóng tàu HD Hyundai Heavy Industries (HIPC)
    # -------------------------------------------------------------------------
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from extract_hipc_subcontractors import HIPC_DATA
        print(f"[Nguồn 2] Thầu phụ nội bộ xưởng HD Hyundai Heavy (HIPC): {len(HIPC_DATA)} công ty")
        for item in HIPC_DATA:
            cname = str(item['cty']).strip()
            norm_name = re.sub(r'[\s\(\)주식회사]', '', cname)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            combined_rows.append({
                'Cong ty': cname,
                'Chuc danh': f"Nhà thầu phụ nội bộ xưởng HD Hyundai Heavy ({item.get('mảng', 'Hàn kết cấu & Vỏ tàu')})",
                'Nguoi lien he': str(item.get('đại_diện', 'Phòng Nhân Sự')),
                'SDT': '',
                'Lien He': 'http://www.hipc.or.kr',
                'Email': '',
                'Lien He mail': '',
                'Dia chi': '대한민국 울산광역시 동구 방어진순환도로 1000 (HD현대중공업 내)',
                'Luong': 'Lương thợ hàn E-7-3 theo quy chuẩn Bộ Lao động Hàn Quốc',
                'Ngay dang': '2026-10-06',
                'Han tuyen': 'Tuyển liên tục',
                'Category': 'Thầu phụ xưởng HD Hyundai Heavy (사내협력사 - 용접/취부)'
            })
    except Exception as e:
        print(f"[!] Lỗi nạp HIPC: {e}")

    # -------------------------------------------------------------------------
    # NGUỒN 3: 536 Văn phòng Môi giới Việc làm tại các Thủ phủ đóng tàu (MOEL)
    # -------------------------------------------------------------------------
    moel_path = "KR_AGCY_MOEL_0RAW.csv"
    if os.path.exists(moel_path):
        df_moel = pd.read_csv(moel_path, encoding='utf-8-sig')
        shipyard_keywords = ['거제', '동구', '영암', '목포', '진해', '영도', '통영', '대불', '녹산', '온산']
        reg_pattern = '|'.join(shipyard_keywords)
        mask = df_moel['Dia chi'].str.contains(reg_pattern, regex=True, na=False) | df_moel['Cong ty'].str.contains(r'조선|용접|선박|해양', regex=True, na=False)
        moel_shipyard = df_moel[mask]
        print(f"[Nguồn 3] Môi giới việc làm tại các Thủ phủ Đóng tàu (MOEL): {len(moel_shipyard)} văn phòng")
        
        for _, r in moel_shipyard.iterrows():
            cname = str(r['Cong ty']).strip()
            norm_name = re.sub(r'[\s\(\)주식회사]', '', cname)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            combined_rows.append({
                'Cong ty': cname,
                'Chuc danh': 'Văn phòng Môi giới & Cung ứng Lao động Thủ phủ Đóng tàu',
                'Nguoi lien he': str(r.get('Nguoi lien he', 'Người đại diện văn phòng')),
                'SDT': clean_phone(r.get('SDT', '')),
                'Lien He': str(r.get('Lien He', '')),
                'Email': clean_email(r.get('Email', '')),
                'Lien He mail': str(r.get('Lien He mail', '')),
                'Dia chi': str(r.get('Dia chi', '')),
                'Luong': 'Theo thỏa thuận cung ứng lao động xưởng đóng tàu',
                'Ngay dang': '2026-10-06',
                'Han tuyen': 'Thường trực',
                'Category': 'Văn phòng việc làm thủ phủ đóng tàu (거제/울산/영암/목포/진해)'
            })

    # Tạo DataFrame chuẩn 20 cột
    df_out = pd.DataFrame(combined_rows)
    for col in COLUMNS_20:
        if col not in df_out.columns:
            df_out[col] = ''
    
    df_out = df_out[COLUMNS_20]
    df_out['No.'] = range(1, len(df_out) + 1)
    
    # Sắp xếp ưu tiên các bản ghi đã có Email hoặc SĐT lên đầu
    df_out['has_email'] = df_out['Email'].apply(lambda x: 1 if str(x).strip() and '@' in str(x) else 0)
    df_out['has_phone'] = df_out['SDT'].apply(lambda x: 1 if str(x).strip() else 0)
    df_out = df_out.sort_values(by=['has_email', 'has_phone'], ascending=[False, False]).reset_index(drop=True)
    df_out = df_out.drop(columns=['has_email', 'has_phone'])
    df_out['No.'] = range(1, len(df_out) + 1)

    df_out.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    
    has_em = df_out['Email'].dropna().apply(lambda x: str(x).strip() != '').sum()
    has_ph = df_out['SDT'].dropna().apply(lambda x: str(x).strip() != '').sum()

    print("\n" + "=" * 70)
    print(f"THIẾT LẬP THÀNH CÔNG TỆP GỐC: {OUTPUT_FILE}")
    print(f"Tổng số doanh nghiệp Thợ hàn đóng tàu: {len(df_out)}")
    print(f" - Đã có sẵn Email: {has_em}")
    print(f" - Đã có sẵn SĐT: {has_ph}")
    print("=" * 70)

if __name__ == '__main__':
    main()
