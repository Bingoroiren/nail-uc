# -*- coding: utf-8 -*-
"""
Formatters: Chuẩn Hóa Dữ Liệu Nông Nghiệp Áo Sang Mẫu Cold Mail 20 Cột Chuẩn Workspace:
- Tệp nguồn: AT_AGRI_WBIO_1ENR.csv
- Tệp đích: AT_AGRI_WBIO_2COL.csv (Quy chuẩn 17 ký tự: CC_IND4_SRC4_STG4)
- Phân nhóm tối ưu:
  1. Hàng đầu tiên (Top 1): 100% doanh nghiệp có Email hợp lệ, Check gửi = 'OK', sẵn sàng gửi mail hàng loạt.
  2. Kế tiếp: Các doanh nghiệp có email nhưng lịch sử đã từng bị bounce (Check gửi = 'BOUNCE', cảnh báo tránh gửi lại).
  3. Cuối cùng: Các doanh nghiệp không có email (Check gửi = '', phục vụ telesale/liên hệ số điện thoại).
- SĐT 100% có dấu nháy đơn `'` ở đầu.
- Cột 'No.' đánh số thứ tự từ 1 đến hết.
"""

import sys
import os
import re
import csv
import urllib.parse
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "AT_AGRI_WBIO_1ENR.csv"
OUTPUT_COLDMAIL_CSV = ROOT_DIR / "AT_AGRI_WBIO_2COL.csv"

FIELDNAMES = [
    "No.",
    "Công ty",
    "Chức danh",
    "Người liên hệ",
    "SĐT",
    "Liên Hệ",
    "Email",
    "Liên Hệ mail",
    "Địa chỉ",
    "Lương",
    "Ngày đăng",
    "Hạn tuyển",
    "Check gửi",
    "Last Subject",
    "Last Body HTML",
    "Trạng thái Reply",
    "Lần Follow-up",
    "Ngày Follow-up gần nhất",
    "Mailbox đã dùng",
    "Category"
]

def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    while p.startswith("'"):
        p = p[1:].strip()
    if p:
        return f"'{p}"
    return ""

def main():
    if not INPUT_CSV.exists():
        print(f"[-] Không tìm thấy tệp nguồn: {INPUT_CSV}")
        return

    print(f"[*] Đang đọc dữ liệu từ: {INPUT_CSV.name}...")
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[*] Tổng số bản ghi ban đầu: {len(raw_rows):,}")

    valid_email_rows = []
    bounced_email_rows = []
    no_email_rows = []

    for r in raw_rows:
        company = (r.get("Công ty") or "").strip()
        email = (r.get("Email") or "").strip()
        phone = format_phone(r.get("SĐT"))
        contact = (r.get("Người liên hệ") or "").strip()
        website = (r.get("Liên Hệ") or "").strip()
        address = (r.get("Địa chỉ") or "").strip()
        reply_status = (r.get("Trạng thái Reply") or "").strip()
        category = (r.get("Category") or "").strip()
        job_title = (r.get("Chức danh") or "").strip()
        email_note = (r.get("Liên Hệ mail") or "").strip()

        # Phân loại theo email
        if email:
            if "bounce" in reply_status.lower():
                bounced_email_rows.append({
                    "company": company,
                    "job_title": job_title,
                    "contact": contact,
                    "phone": phone,
                    "website": website,
                    "email": email,
                    "email_note": email_note,
                    "address": address,
                    "check_send": "BOUNCE",
                    "reply_status": reply_status,
                    "follow_up": 0,
                    "category": category
                })
            else:
                valid_email_rows.append({
                    "company": company,
                    "job_title": job_title,
                    "contact": contact,
                    "phone": phone,
                    "website": website,
                    "email": email,
                    "email_note": email_note,
                    "address": address,
                    "check_send": "OK",
                    "reply_status": reply_status,
                    "follow_up": 0,
                    "category": category
                })
        else:
            # Nếu không có email: Chỉ giữ lại nếu có SĐT để phục vụ telesale, loại bỏ dòng không có cả mail và sđt
            if not phone:
                continue

            no_email_rows.append({
                "company": company,
                "job_title": job_title,
                "contact": contact,
                "phone": phone,
                "website": website,
                "email": "",
                "email_note": email_note,
                "address": address,
                "check_send": "",
                "reply_status": "",
                "follow_up": 0,
                "category": category
            })

    # Ghép theo thứ tự ưu tiên: Có Email hợp lệ -> Email bị bounce -> Chỉ có SĐT (không có email)
    combined_rows = valid_email_rows + bounced_email_rows + no_email_rows

    print("\n[*] Kết quả phân loại đối tượng Cold Mail:")
    print(f"    1. CÓ EMAIL HỢP LỆ (Sẵn sàng gửi ngay, Check gửi = 'OK') : {len(valid_email_rows):,} cơ sở")
    print(f"    2. EMAIL BỊ BOUNCE (Lịch sử đã bounce, Check gửi = 'BOUNCE'): {len(bounced_email_rows):,} cơ sở")
    print(f"    3. CHỈ CÓ SĐT (Dự phòng gọi điện, Check gửi = '')        : {len(no_email_rows):,} cơ sở")
    print(f"    -> Đã loại bỏ dòng không có cả Email và SĐT               : {len(raw_rows) - len(combined_rows):,} cơ sở")
    print(f"    -> Tổng cộng số dòng giữ lại                              : {len(combined_rows):,} cơ sở")

    # Xây dựng danh sách 20 cột chuẩn
    output_rows = []
    for idx, r in enumerate(combined_rows, 1):
        output_rows.append({
            "No.": idx,
            "Công ty": r["company"],
            "Chức danh": r["job_title"],
            "Người liên hệ": r["contact"],
            "SĐT": r["phone"],
            "Liên Hệ": r["website"],
            "Email": r["email"],
            "Liên Hệ mail": r["email_note"],
            "Địa chỉ": r["address"],
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": r["check_send"],
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": r["reply_status"],
            "Lần Follow-up": r["follow_up"],
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": r["category"]
        })

    # Ghi ra tệp AT_AGRI_WBIO_2COL.csv
    with open(OUTPUT_COLDMAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"\n[+] XUẤT THÀNH CÔNG: {OUTPUT_COLDMAIL_CSV.name}")
    print(f"[+] Toàn bộ {len(valid_email_rows):,} cơ sở có Email hợp lệ được đẩy lên từ dòng 1 đến dòng {len(valid_email_rows):,}!")
    print(f"[+] SĐT 100% chuẩn dấu nháy đơn `'`.")
    print(f"[+] Chuẩn mã hóa: CSV UTF-8 with BOM (utf-8-sig).")

if __name__ == '__main__':
    main()
