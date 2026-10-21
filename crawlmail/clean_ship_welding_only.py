# -*- coding: utf-8 -*-
"""
Bộ lọc thanh lọc chuyên sâu: Giữ LẠI 100% ĐÚNG DOANH NGHIỆP ĐÓNG TÀU & THỢ HÀN TÀU (SHIP WELDERS / SHIPBUILDING)
Loại bỏ triệt để các ngành lạc đề do search engine Saramin trả về sai:
- Phụ tùng ô tô (현대자동차 1차 협력사, 자동차 부품)
- Thực phẩm / Rong biển (신안천사김, 식품, 참프레, 동서식품)
- Dược phẩm (동광제약)
- Casino / Khách sạn (엘티엔터테인먼트, 카지노, 호텔)
- Bán hàng văn phòng, bảo vệ, y tế, chung chung không liên quan đến xưởng tàu.

Giữ lại:
- Thầu phụ vỏ tàu, nội nghiệp, ngoại nghiệp trong xưởng HD Hyundai Heavy, Samsung Heavy, Hanwha Ocean.
- Thợ hàn tàu, gá lắp vỏ block tàu (취부), hàn ống tàu (배관), bắn cát & sơn tàu (도장/소지).
- Các xưởng đóng tàu vừa và nhỏ KOSIC trên toàn quốc.
- Đẩy 100% doanh nghiệp có Email lên đầu.
"""

import sys
import re
import csv
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_2COL = ROOT_DIR / "KR_SHIP_HIPC_2COL.csv"
TARGET_1ENR = ROOT_DIR / "KR_SHIP_HIPC_1ENR.csv"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

BANNED_SECTORS = [
    '자동차', '현대차', '기아', '제약', '약품', '식품', '카지노', '호텔', '반도체', 
    '의류', '화장품', '신안천사김', '사무 영업', '병원', '요양', '경비원', 
    '청소원', '패션', '닭고기', '사료', '유통', '베이커리'
]

SHIP_KEYWORDS = [
    '조선', '선박', '현대중공업', '삼성중공업', '한화오션', '대우조선', 
    '케이조선', '대한조선', 'kosic', 'hipc', '사내협력사', '선체', 
    '해양', '선박수리', '강선', '블럭', '데크하우스', '의장'
]

WELD_KEYWORDS = [
    '용접', '취부', '배관', '사상', '도장', '블라스팅', '소지', 
    '블럭', '의장', '내업', '외업', '선박', '조선소', '특수선', 
    '엔진', '선체', '가공', '철의장'
]

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\r', '').replace('\n', '').strip()
    if not p_str or p_str.lower() in ['none', 'nan']:
        return ""
    p_str = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_str:
        return ""
    if not p_str.startswith("'"):
        p_str = f"'{p_str}"
    return p_str

def is_strictly_ship_welding(row):
    comp = str(row.get('Cong ty', ''))
    title = str(row.get('Chuc danh', ''))
    cat = str(row.get('Category', ''))
    full_text = f"{comp} {title} {cat}".lower()
    
    # 1. Nếu dính từ cấm ngành khác -> LOẠI NGAY
    if any(b in full_text for b in BANNED_SECTORS):
        return False
        
    # 2. Nếu là thành viên ban đầu từ Hiệp hội xưởng tàu (HIPC hoặc KOSIC) -> CHẮC CHẮN LÀ ĐÓNG TÀU
    if 'hd현대중공업 사내협력사' in cat.lower() or '한국중소조선공업협동조합' in cat.lower() or 'kosic' in cat.lower() or 'hipc' in cat.lower():
        return True
        
    # 3. Với các tin mới từ tuyển dụng: BẮT BUỘC có yếu tố Đóng tàu/Tàu biển VÀ Hàn/Gia công vỏ tàu
    has_ship = any(s in full_text for s in SHIP_KEYWORDS)
    has_weld = any(w in full_text for w in WELD_KEYWORDS)
    
    return has_ship and has_weld

def main():
    if not TARGET_2COL.exists():
        print(f"[!] Không tìm thấy file {TARGET_2COL}")
        return

    df = pd.read_csv(TARGET_2COL, encoding='utf-8-sig').fillna('')
    total_before = len(df)
    
    # Lọc nghiêm ngặt
    mask = df.apply(is_strictly_ship_welding, axis=1)
    df_clean = df[mask].copy()
    
    # Chuẩn hóa SĐT có nháy đơn '
    df_clean['SDT'] = df_clean['SDT'].apply(clean_phone)
    
    # Đẩy 100% có Email lên đầu
    df_clean['has_email'] = df_clean['Email'].apply(lambda x: 1 if str(x).strip() and '@' in str(x) else 0)
    df_clean['has_phone'] = df_clean['SDT'].apply(lambda x: 1 if str(x).strip() else 0)
    
    df_clean = df_clean.sort_values(by=['has_email', 'has_phone'], ascending=[False, False]).reset_index(drop=True)
    df_clean = df_clean.drop(columns=['has_email', 'has_phone'])
    df_clean['No.'] = range(1, len(df_clean) + 1)
    
    # Ghi đè ra cả 2COL và 1ENR
    df_clean.to_csv(TARGET_2COL, index=False, encoding='utf-8-sig')
    df_clean.to_csv(TARGET_1ENR, index=False, encoding='utf-8-sig')
    
    total_after = len(df_clean)
    emails_count = (df_clean['Email'].str.strip() != '').sum()
    phones_count = (df_clean['SDT'].str.strip() != '').sum()
    
    print("=" * 70)
    print(" KẾT QUẢ THANH LỌC CHUẨN XÁC 100% THỢ HÀN ĐÓNG TÀU (SHIP WELDERS)")
    print(f" - Tổng trước khi lọc: {total_before} doanh nghiệp")
    print(f" - Đã loại bỏ: {total_before - total_after} công ty lạc đề (ô tô, thực phẩm, casino, dược...)")
    print(f" - Tổng số doanh nghiệp THỢ HÀN & XƯỞNG TÀU CHUẨN: {total_after}")
    print(f" - Tổng số EMAIL B2B chuẩn thợ hàn tàu: {emails_count} (ĐẨY 100% LÊN ĐẦU)")
    print(f" - Tổng số SĐT chuẩn có nháy đơn: {phones_count}")
    print("=" * 70)

if __name__ == '__main__':
    main()
