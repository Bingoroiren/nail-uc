# -*- coding: utf-8 -*-
"""
LÀM SẠCH TRIỆT ĐỂ: LOẠI BỎ 100% CÁC BLOG / CÔNG TY KHÔNG LIÊN QUAN
Chỉ giữ lại duy nhất:
1. Các Đại lý Visa E-7-3 / E-9 & Văn phòng Hành chính Di trú xưởng tàu (출입국 / 행정사 / 비자).
2. Các Công ty / Văn phòng Môi giới Nhân lực, Cung ứng thợ hàn, thầu phụ xưởng tàu (인력 / 직업소개 / 사내협력사 / 용접 / 취업).
3. Loại bỏ 100% các blog cá nhân, trường học, bất động sản, tin tức, sửa chữa gia dụng.
"""

import sys
import os
import re
import csv
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_2COL = str(ROOT_DIR / "KR_AGCY_SHIP_2COL.csv")
MASTER_1ENR = str(ROOT_DIR / "KR_AGCY_SHIP_1ENR.csv")
FMT_2COL = str(ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv")

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

KEEP_KEYWORDS = [
    '행정사', '인력', '취업', '채용', '소개', '협력사', '용접', '비자', 'e7', 'e-7', 'e9', 'e-9',
    '조선소', '선박', '해양', '도급', '파견', '아웃소싱', '노무', '노동', '에이전시', '헤드헌팅',
    '맨파워', '구인', '일자리', '기능인력', '외국인', '배관', '취부', '직업소개', '직업능력', '사내협력',
    '플랜트', '임가공', '조선', '기술단', '산업인력', '일다방', '일가자', '출입국', '취업정보', '일자리'
]

DROP_KEYWORDS = [
    '공인중개사', '부동산', '인테리어', '맛집', '영화', '주식', '차트', '가치투자', '의회', '군청',
    '보건복지부', '수학', '체대', '화물', '용달', '소화용구', '베개', '서평', '책', '패션', '보험',
    '어린이집', '치과', '에어컨', '철물', '고양이', '유튜브', '뉴스', '신문', '다이어트', '누수',
    '동포', '안전보건교육', '일상', '일기', '이야기', '작가', '취미', '육아', '서핑', '여행', '음악',
    '영어', '피아노', '뷰티', '미용', '헤어', '네일', '카페', '음식', '요리', '식당', '재테크',
    '세무', '회계', '님의 블로그', '님의블로그', '블로그', '동행', '산줄기'
]

def main():
    print("=" * 80)
    print("LÀM SẠCH TRIỆT ĐỂ KR_AGCY_SHIP_2COL.csv: LOẠI BỎ 100% ĐƠN VỊ NGOÀI NGÀNH")
    print("=" * 80)

    with open(MASTER_2COL, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]

    print(f"[*] Tổng số dòng có email trước khi lọc: {len(with_email)}")
    print(f"[*] Tổng số dòng không có email (dữ liệu MOEL & KNESA): {len(without_email)}")

    pure_email_rows = []
    dropped_count = 0

    for r in with_email:
        cname = r.get('Công ty', '').strip()
        cat = r.get('Category', '').strip()
        full_info = f"{cname}".lower()

        # Kiểm tra token rác
        has_drop = any(d in full_info for d in DROP_KEYWORDS)
        has_keep = any(k in full_info for k in KEEP_KEYWORDS)

        # Nếu có từ rác mà không có từ khóa nghiệp vụ mạnh -> LOẠI
        if has_drop and not any(strong in full_info for strong in ['행정사', '인력', '조선소', '용접', '협력사', '맨파워', '직업소개', '출입국']):
            dropped_count += 1
            continue

        if not has_keep:
            dropped_count += 1
            continue

        pure_email_rows.append(r)

    print(f"[+] ĐÃ LOẠI BỎ {dropped_count} ĐƠN VỊ RÁC / KHÔNG LIÊN QUAN ĐẾN AGENCY HÀN TÀU!")
    print(f"[+] SỐ EMAIL CHUẨN AGENCY & E-7-3 CÒN LẠI: {len(pure_email_rows)}")

    # Xếp 100% email lên đầu
    pure_email_rows.sort(key=lambda x: (1 if x.get('SĐT') else 0), reverse=True)
    final_master_rows = pure_email_rows + without_email

    for idx, r in enumerate(final_master_rows, 1):
        r['No.'] = str(idx)

    # Ghi đè cập nhật
    for path in [MASTER_2COL, MASTER_1ENR, FMT_2COL]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(final_master_rows)
        print(f"[OK] Đã ghi đè file sạch: {path}")

    print("\n" + "=" * 80)
    print("HOÀN TẤT LÀM SẠCH CHUYÊN SÂU!")
    print(f"  • Số lượng Email MỚI TINH, CHUẨN 100% AGENCY & ĐÓNG TÀU: {len(pure_email_rows)} (No. 1 đến No. {len(pure_email_rows)})")
    print(f"  • Tổng số dòng trong tệp duy nhất: {len(final_master_rows)}")
    print("=" * 80)

if __name__ == "__main__":
    main()
