import sys
import os
import csv
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_FILE = ROOT_DIR / "KR_AGCY_SHIP_2COL.csv"
FMT_FILE = ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv"
VETTED_FILE = ROOT_DIR / "data" / "cache" / "vetted_new_agencies.json"

COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

# 1. Read existing master rows
existing_rows = []
existing_emails = set()
if MASTER_FILE.exists():
    with open(MASTER_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            em = r.get('Email', '').strip().lower()
            if em:
                existing_emails.add(em)
            existing_rows.append(r)

print(f"[*] Current Master rows: {len(existing_rows)}")
print(f"[*] Current Master emails: {len(existing_emails)}")

# 2. Read vetted new agencies
with open(VETTED_FILE, 'r', encoding='utf-8') as f:
    new_vetted = json.load(f)

added_count = 0
for v in new_vetted:
    em = v.get('Email', '').strip().lower()
    if em and em not in existing_emails:
        existing_emails.add(em)
        phone = v.get('SĐT', '').strip()
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"
        row_dict = {
            "No.": "",
            "Công ty": v.get('Công ty', '').strip(),
            "Chức danh": v.get('Chức danh', 'Giám đốc / Đại diện pháp lý'),
            "Người liên hệ": v.get('Người liên hệ', 'Quản lý tuyển dụng'),
            "SĐT": phone,
            "Liên Hệ": phone,
            "Email": em,
            "Liên Hệ mail": em,
            "Địa chỉ": v.get('Địa chỉ', 'Hàn Quốc'),
            "Lương": "Thỏa thuận theo HĐ B2B",
            "Ngày đăng": "",
            "Hạn tuyển": "Thường xuyên",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": v.get('Category', 'Shipyard / Seafarer Agency')
        }
        existing_rows.append(row_dict)
        added_count += 1

print(f"[*] Added {added_count} completely new, unique vetted agencies.")

# 3. Sort: All rows with Email at the top!
with_email = []
without_email = []

for r in existing_rows:
    em = r.get('Email', '').strip()
    if em:
        with_email.append(r)
    else:
        without_email.append(r)

# Sort with_email by Category / Company for clean organization
with_email.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))
combined = with_email + without_email

# 4. Renumber No. sequentially
for idx, r in enumerate(combined, 1):
    r['No.'] = idx

print(f"[*] Total final rows: {len(combined)}")
print(f"[*] Total verified B2B emails at the top: {len(with_email)} (Rows 1 to {len(with_email)})")

# 5. Save to MASTER_FILE and FMT_FILE
FMT_FILE.parent.mkdir(parents=True, exist_ok=True)

for target_path in [MASTER_FILE, FMT_FILE]:
    with open(target_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(combined)
    print(f"[OK] Saved {len(combined)} rows to {target_path}")

print("=" * 80)
print(f"THÀNH CÔNG: Đã tích hợp {len(with_email)} Email môi giới sạch vào file chuẩn duy nhất!")
print("=" * 80)
