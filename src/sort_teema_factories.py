# -*- coding: utf-8 -*-
"""
Script Sắp Xếp Dữ Liệu Nhà Máy TEEMA Theo Quy Mô Nhân Sự & Vốn:
- Ưu tiên 1: Sắp xếp giảm dần theo Số lượng nhân viên (Employees).
- Ưu tiên 2: Sắp xếp giảm dần theo Vốn điều lệ (Capital).
- Xuất file CSV UTF-8 with BOM chuẩn: data/formatted/teema_taiwan_electronics_factories_sorted.csv
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
RAW_CSV = str(ROOT_DIR / "data" / "raw" / "teema_taiwan_electronics_factories.csv")
SORTED_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_electronics_factories_sorted.csv")

os.makedirs(os.path.dirname(SORTED_CSV), exist_ok=True)

def parse_number(val):
    """Chuyển chuỗi số có dấu phẩy hoặc ký tự lạ thành số nguyên an toàn."""
    if not val:
        return 0
    clean = re.sub(r'[^\d]', '', str(val))
    return int(clean) if clean else 0

def sort_teema_data():
    if not os.path.exists(RAW_CSV):
        print(f"[-] Không tìm thấy tệp {RAW_CSV}")
        return

    with open(RAW_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        print("[!] Tệp CSV hiện chưa có dữ liệu.")
        return

    print(f"[*] Đang sắp xếp và lọc {len(rows)} công ty...")

    # Lọc bỏ các công ty dưới 10 nhân sự (văn phòng/thương mại/cửa hàng)
    filtered_rows = [r for r in rows if parse_number(r.get("Employees", 0)) >= 10]
    removed = len(rows) - len(filtered_rows)
    print(f"[*] Đã loại bỏ: {removed} công ty có dưới 10 nhân sự.")
    print(f"[*] Còn lại: {len(filtered_rows)} nhà máy đạt chuẩn (>= 10 nhân sự).")

    # Sắp xếp 2 cấp độ: Employees giảm dần -> Capital giảm dần
    sorted_rows = sorted(
        filtered_rows,
        key=lambda r: (parse_number(r.get("Employees", 0)), parse_number(r.get("Capital", 0))),
        reverse=True
    )

    # Ghi ra tệp formatted đã sắp xếp
    QUALIFIED_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_factories_ge_10_employees.csv")
    with open(QUALIFIED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    try:
        with open(SORTED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_rows)
    except PermissionError:
        pass

    print(f"[✓] Đã xuất file sắp xếp thành công: {SORTED_CSV}")
    print("\n--- TOP 5 NHÀ MÁY LỚN NHẤT HIỆN TẠI ---")
    for idx, r in enumerate(sorted_rows[:5], 1):
        emp = r.get("Employees", "0")
        cap = r.get("Capital", "0")
        print(f"  {idx}. {r.get('Company_Name')}")
        print(f"     👥 Lao động: {emp} người | 💰 Vốn: {cap} NTD | 📞 SĐT: {r.get('Phone')}")

if __name__ == "__main__":
    sort_teema_data()
