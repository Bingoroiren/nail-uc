# -*- coding: utf-8 -*-
"""
Script Chuẩn Hóa Dữ Liệu Nhà Máy Điện Tử Đài Loan Sang Template Cold Mail Tiêu Chuẩn Workspace:
Header chuẩn 20 cột:
['No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
 'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
 'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
 'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category']
"""

import sys
import os
import re
import csv
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_factories_hr_enriched.csv")
OUTPUT_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_factories_coldmail_formatted.csv")

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

def parse_num(v):
    if not v:
        return 0
    clean = re.sub(r'[^\d]', '', str(v))
    return int(clean) if clean else 0

def format_coldmail():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp nguồn: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    print(f"[*] Đọc thành công {len(rows)} nhà máy từ file enriched.")

    # Tách nhóm có Email lên trước, nhóm không có Email ra sau
    # Trong từng nhóm, sắp xếp giảm dần theo Quy mô nhân viên (Employees) -> Vốn (Capital)
    with_email = []
    without_email = []

    for r in rows:
        email = (r.get('HR_Email') or '').strip()
        if email:
            with_email.append(r)
        else:
            without_email.append(r)

    with_email.sort(key=lambda x: (parse_num(x.get('Employees')), parse_num(x.get('Capital'))), reverse=True)
    without_email.sort(key=lambda x: (parse_num(x.get('Employees')), parse_num(x.get('Capital'))), reverse=True)

    sorted_total = with_email + without_email
    print(f"[*] Phân loại: {len(with_email)} nhà máy CÓ EMAIL (Ưu tiên gửi trước), {len(without_email)} nhà máy dự phòng.")

    output_rows = []
    for idx, r in enumerate(sorted_total, 1):
        # Tên công ty kết hợp song ngữ: Tiếng Trung (Tiếng Anh)
        cname_zh = (r.get('Company_Name_ZH') or '').strip()
        cname_en = (r.get('Company_Name_EN') or '').strip()
        if cname_zh and cname_en and cname_zh != cname_en:
            company_display = f"{cname_zh} ({cname_en})"
        else:
            company_display = cname_zh or cname_en

        # Số điện thoại chuẩn hóa có ' ở đầu
        phone = (r.get('HR_Phone') or r.get('Company_Phone') or '').strip()
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"

        # Địa chỉ ưu tiên tiếng Trung cho bưu điện Đài Loan, kèm tiếng Anh
        addr_zh = (r.get('Address_ZH') or '').strip()
        addr_en = (r.get('Address_EN') or '').strip()
        address_display = addr_zh if addr_zh else addr_en

        # Category: Sản phẩm nhà máy / Nhóm ngành
        prod = (r.get('Plant_Products') or r.get('Keyword_Groups') or 'Nhà máy Sản xuất Điện tử / Linh kiện').strip()

        out = {
            "No.": idx,
            "Công ty": company_display,
            "Chức danh": (r.get('HR_Contact_Title') or '').strip(),
            "Người liên hệ": (r.get('HR_Contact_Name') or '').strip(),
            "SĐT": phone,
            "Liên Hệ": (r.get('Website') or '').strip(),
            "Email": (r.get('HR_Email') or '').strip(),
            "Liên Hệ mail": (r.get('Careers_URL') or '').strip(),
            "Địa chỉ": address_display,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": prod
        }
        output_rows.append(out)

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"[+] XUẤT THÀNH CÔNG: {OUTPUT_CSV}")
    print(f"[+] Tổng số dòng: {len(output_rows)} (Chuẩn 20 cột Cold Mail Workspace)")

if __name__ == '__main__':
    format_coldmail()
