# -*- coding: utf-8 -*-
"""
TÁCH VÀ THIẾT LẬP TỆP CHUYÊN BIỆT: MÔI GIỚI VIỆC LÀM THỢ HÀN ĐÓNG TÀU (AGENCY ONLY)
Tên tệp đích: KR_AGCY_WELD_0RAW.csv (17 ký tự chuẩn)

Đặc điểm:
- 100% là các Công ty Môi giới Việc làm / Văn phòng Giới thiệu Việc làm (직업소개소 / 인력개발 / 채용대행사)
- Đóng tại các "Thủ phủ Đóng tàu" lớn nhất Hàn Quốc:
  * Ulsan Dong-gu (Quanh xưởng HD Hyundai Heavy Industries & Hyundai Mipo)
  * Geoje (Quanh xưởng Hanwha Ocean & Samsung Heavy Industries)
  * Yeongam & Mokpo (Quanh xưởng HD Hyundai Samho & KCN Thợ hàn Daebul)
  * Jinhae & Changwon (Quanh xưởng K Shipbuilding)
  * Tongyeong (Quanh xưởng HSG Seongdong Shipbuilding)
  * Busan Yeongdo (Quanh xưởng HJ Shipbuilding & sửa chữa tàu)
- TUYỆT ĐỐI KHÔNG TRỘN LẪN xưởng đóng tàu hay nhà thầu phụ cơ khí vào tệp này.
"""

import os
import re
import sys
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

INPUT_MOEL = "KR_AGCY_MOEL_0RAW.csv"
OUTPUT_AGCY = "KR_AGCY_WELD_0RAW.csv"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

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
    print(" THIẾT LẬP TỆP CHUYÊN BIỆT: MÔI GIỚI VIỆC LÀM THỢ HÀN ĐÓNG TÀU (AGENCY ONLY)")
    print("=" * 70)

    if not os.path.exists(INPUT_MOEL):
        print(f"[!] Không tìm thấy tệp {INPUT_MOEL}")
        return

    df = pd.read_csv(INPUT_MOEL, encoding='utf-8-sig')
    print(f"Tổng số văn phòng MOEL ban đầu: {len(df)}")

    # Lọc các văn phòng môi giới tại các thủ phủ đóng tàu
    shipyard_regions = [
        '거제',    # Geoje (Samsung, Hanwha Ocean)
        '동구',    # Ulsan Dong-gu (HD Hyundai Heavy, Mipo)
        '영암',    # Yeongam (Hyundai Samho, Daebul)
        '목포',    # Mokpo (Daebul hub)
        '진해',    # Jinhae (K Shipbuilding)
        '영도',    # Yeongdo (HJ Shipbuilding)
        '통영',    # Tongyeong (HSG Seongdong)
        '대불',    # Daebul National Industrial Complex
        '녹산',    # Noksan Shipyard Marine Industrial Complex
        '온산'     # Onsan Shipyard Heavy Complex
    ]

    reg_pattern = '|'.join(shipyard_regions)
    mask = df['Dia chi'].str.contains(reg_pattern, regex=True, na=False) | df['Cong ty'].str.contains(r'조선|용접|선박|해양', regex=True, na=False)

    df_weld_agcy = df[mask].copy().reset_index(drop=True)
    print(f"Số lượng Văn phòng Môi giới việc làm tại các Thủ phủ Đóng tàu: {len(df_weld_agcy)}")

    rows = []
    for idx, r in df_weld_agcy.iterrows():
        cname = str(r['Cong ty']).strip()
        addr = str(r.get('Dia chi', '')).strip()
        rep = str(r.get('Nguoi lien he', 'Người đại diện văn phòng')).strip()
        
        # Xác định thủ phủ đóng tàu
        hub_name = "Thủ phủ Đóng tàu"
        if '거제' in addr: hub_name = "Geoje (Hanwha Ocean / Samsung Heavy)"
        elif '동구' in addr: hub_name = "Ulsan Dong-gu (HD Hyundai Heavy / Mipo)"
        elif '영암' in addr or '대불' in addr: hub_name = "Yeongam / Daebul (Hyundai Samho)"
        elif '목포' in addr: hub_name = "Mokpo (Cụm KCN Thợ hàn Daebul)"
        elif '진해' in addr: hub_name = "Jinhae (K Shipbuilding)"
        elif '영도' in addr: hub_name = "Busan Yeongdo (HJ Shipbuilding)"
        elif '통영' in addr: hub_name = "Tongyeong (HSG Seongdong)"

        rows.append({
            'No.': idx + 1,
            'Cong ty': cname,
            'Chuc danh': f"Môi giới & Giới thiệu Lao động ({hub_name})",
            'Nguoi lien he': rep,
            'SDT': clean_phone(r.get('SDT', '')),
            'Lien He': str(r.get('Lien He', 'http://www.moel.go.kr')),
            'Email': clean_email(r.get('Email', '')),
            'Lien He mail': str(r.get('Lien He mail', '')),
            'Dia chi': addr,
            'Luong': 'Thỏa thuận theo hợp đồng cung ứng thợ hàn E-7-3',
            'Ngay dang': '2026-10-06',
            'Han tuyen': 'Thường trực',
            'Check gui': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trang thai Reply': '',
            'Lan Follow-up': '',
            'Ngay Follow-up gan nhat': '',
            'Mailbox da dung': '',
            'Category': f"Agency Môi giới Thủ phủ Đóng tàu ({hub_name})"
        })

    df_out = pd.DataFrame(rows)
    for col in COLUMNS_20:
        if col not in df_out.columns:
            df_out[col] = ''
    df_out = df_out[COLUMNS_20]

    # Đẩy các dòng đã có SĐT hoặc Email lên đầu
    df_out['has_email'] = df_out['Email'].apply(lambda x: 1 if str(x).strip() and '@' in str(x) else 0)
    df_out['has_phone'] = df_out['SDT'].apply(lambda x: 1 if str(x).strip() else 0)
    df_out = df_out.sort_values(by=['has_email', 'has_phone'], ascending=[False, False]).reset_index(drop=True)
    df_out = df_out.drop(columns=['has_email', 'has_phone'])
    df_out['No.'] = range(1, len(df_out) + 1)

    df_out.to_csv(OUTPUT_AGCY, index=False, encoding='utf-8-sig')

    has_em = df_out['Email'].dropna().apply(lambda x: str(x).strip() != '').sum()
    has_ph = df_out['SDT'].dropna().apply(lambda x: str(x).strip() != '').sum()

    print("\n" + "=" * 70)
    print(f"XUẤT THÀNH CÔNG: {OUTPUT_AGCY}")
    print(f"Tổng số Agency Môi giới Việc làm Thủ phủ Đóng tàu: {len(df_out)}")
    print(f" - Đã có sẵn SĐT: {has_ph}")
    print(f" - Đã có sẵn Email: {has_em}")
    print("=" * 70)

if __name__ == '__main__':
    main()
