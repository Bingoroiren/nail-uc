# -*- coding: utf-8 -*-
"""
Lọc trùng 100% đối với toàn bộ các chiến dịch Cold Mail Hàn Quốc đã gửi trước đó:
- KR_SHIP_ALLS_2COL.csv
- KR_SHIP_DSTU_2COL.csv
- KR_SHIP_HIPC_2COL.csv
- KR_SHIP_ALLS_1ENR.csv
- KR_SHIP_HIPC_1ENR.csv

Quy tắc khử trùng tuyệt đối:
1. Trùng Email -> LOẠI BỎ 100%.
2. Trùng Tên Công ty (sau khi chuẩn hóa khử (주), ㈜, 주식회사...) -> LOẠI BỎ 100%.
3. Trùng SĐT đối với cùng tên doanh nghiệp -> LOẠI BỎ 100%.

Đầu ra:
Chỉ giữ lại các doanh nghiệp & email MỚI TINH 100% (chưa từng được gửi bất kỳ email nào).
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

PREV_CAMPAIGN_FILES = [
    "KR_SHIP_ALLS_2COL.csv",
    "KR_SHIP_DSTU_2COL.csv",
    "KR_SHIP_HIPC_2COL.csv",
    "KR_SHIP_ALLS_1ENR.csv",
    "KR_SHIP_HIPC_1ENR.csv"
]

COLDMAIL_FIELDNAMES = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

def normalize_company(n):
    if not n:
        return ""
    n = str(n).strip()
    n = re.sub(r'[\(（].*?[\)）]', '', n)
    for drop in ['(주)', '㈜', '주식회사', '(유)', '유한회사', '사내협력사', '협동조합', '합동사무소', '사무소']:
        n = n.replace(drop, '')
    n = re.sub(r'[^a-zA-Z0-9가-힣]', '', n).lower()
    return n.strip()

def normalize_email(e):
    if not e:
        return ""
    return str(e).strip().lower().replace('%20', '')

def normalize_phone_digits(p):
    if not p:
        return ""
    return re.sub(r'\D', '', str(p))

def main():
    print("=" * 80)
    print("LỌC TRÙNG DỮ LIỆU ĐỐI VỚI TẤT CẢ CÁC FILE ĐÓNG TÀU ĐÃ GỬI TRƯỚC ĐÓ")
    print("Mục tiêu: Đảm bảo 100% người nhận MỚI TINH, không gửi lặp, không bị phàn nàn")
    print("=" * 80)

    # 1. Thu thập danh sách đen các Email, Công ty, SĐT đã gửi trong quá khứ
    sent_emails = set()
    sent_companies = set()
    sent_phones = set()

    for pfile in PREV_CAMPAIGN_FILES:
        filepath = ROOT_DIR / pfile
        if not filepath.exists():
            continue
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            count = 0
            for r in reader:
                em = normalize_email(r.get('Email', ''))
                cname = normalize_company(r.get('Cong ty') or r.get('Công ty'))
                ph = normalize_phone_digits(r.get('SDT') or r.get('SĐT'))

                if em:
                    sent_emails.add(em)
                if cname:
                    sent_companies.add(cname)
                if ph and len(ph) >= 8:
                    sent_phones.add(ph)
                count += 1
            print(f"[*] Đã nạp danh sách đã gửi từ {pfile}: {count} dòng.")

    print(f"\n[+] Tổng số Email ĐÃ TỪNG GỬI cần loại trừ: {len(sent_emails)}")
    print(f"[+] Tổng số Doanh nghiệp ĐÃ TỪNG GỬI cần loại trừ: {len(sent_companies)}")

    # 2. Đọc file Master hiện tại
    if not os.path.exists(MASTER_2COL):
        print(f"[-] Không tìm thấy {MASTER_2COL}")
        return

    with open(MASTER_2COL, 'r', encoding='utf-8-sig') as f:
        master_rows = list(csv.DictReader(f))

    print(f"\n[*] Đang quét {len(master_rows)} dòng trong file hiện tại...")

    clean_rows = []
    removed_email_count = 0
    removed_company_count = 0

    for r in master_rows:
        em = normalize_email(r.get('Email', ''))
        cname = normalize_company(r.get('Công ty', ''))
        ph = normalize_phone_digits(r.get('SĐT', ''))

        # Kiểm tra trùng Email
        if em and em in sent_emails:
            print(f"  [-] LOẠI BỎ (Trùng Email đã gửi): {r.get('Công ty')} -> {em}")
            removed_email_count += 1
            continue

        # Kiểm tra trùng Tên công ty
        if cname and cname in sent_companies:
            print(f"  [-] LOẠI BỎ (Trùng Công ty đã gửi): {r.get('Công ty')}")
            removed_company_count += 1
            continue

        clean_rows.append(r)

    print(f"\n================================================================================")
    print(f"KẾT QUẢ KHỬ TRÙNG:")
    print(f"  • Số dòng bị loại bỏ do trùng Email: {removed_email_count}")
    print(f"  • Số dòng bị loại bỏ do trùng Tên doanh nghiệp: {removed_company_count}")
    print(f"  • Số dòng SẠCH CÒN LẠI (100% CHƯA TỪNG GỬI): {len(clean_rows)}")
    print(f"================================================================================")

    # 3. Phân loại và xếp 100% CÔNG TY CÓ EMAIL LÊN ĐẦU
    with_email = [r for r in clean_rows if r.get('Email', '').strip()]
    without_email = [r for r in clean_rows if not r.get('Email', '').strip()]

    # Sắp xếp ưu tiên
    with_email.sort(key=lambda x: (1 if x.get('SĐT') else 0), reverse=True)

    final_sorted = with_email + without_email

    for idx, r in enumerate(final_sorted, 1):
        r['No.'] = str(idx)

    # 4. Xuất đè lên file Master
    for path in [MASTER_2COL, MASTER_1ENR, FMT_2COL]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(final_sorted)
        print(f"[OK] Đã cập nhật tệp sạch: {path}")

    print("\n" + "=" * 80)
    print(f"HOÀN TẤT LỌC TRÙNG 100%!")
    print(f"  • SỐ LƯỢNG EMAIL MỚI TINH ĐỂ GỬI COLD MAIL: {len(with_email)}")
    print(f"  • Toàn bộ {len(with_email)} email được xếp từ No. 1 đến No. {len(with_email)}")
    print(f"  • 0% TRÙNG LẶP với các chiến dịch tàu thuyền cũ!")
    print("=" * 80)

if __name__ == "__main__":
    main()
