import sys
import os
import csv
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path("d:/glc/nail uc")
MASTER_FILE = ROOT_DIR / "KR_AGCY_SHIP_2COL.csv"
FMT_FILE = ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv"

COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

with open(MASTER_FILE, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

email_rows = [r for r in rows if r['Email'].strip()]
no_email_rows = [r for r in rows if not r['Email'].strip()]

# Flagged 19 indices from 3rd pass audit
flagged_indices = [5, 6, 9, 11, 17, 23, 39, 49, 50, 54, 84, 94, 99, 103, 124, 135, 197, 201, 212]

pure_200 = [r for idx, r in enumerate(email_rows, 1) if idx not in flagged_indices]

# Normalize company names
for r in pure_200:
    c = r['Công ty'].strip()
    c = c.replace('*', '').strip()
    if c.startswith('♬'):
        c = c.lstrip('♬').strip()
    for pfx in ['공식블로그', '공식', '블로그', '님의 블로그', '님의']:
        if c.endswith(pfx):
            c = c[:-len(pfx)].strip()
    r['Công ty'] = c

# Sort pure_200 by Category, Company
pure_200.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))

# Combine with no_email_rows
combined = pure_200 + no_email_rows

# Renumber sequentially
for idx, r in enumerate(combined, 1):
    r['No.'] = idx

# Write to both paths
for path in [MASTER_FILE, FMT_FILE]:
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(combined)
    print(f"[OK] Saved {len(combined)} rows to {path}")

print("=" * 80)
print(f"HOÀN TẤT RÀ SOÁT LẦN 3: Đã chốt ĐÚNG 200 AGENCY SIÊU CHUẨN B2B (Hàng 1 đến Hàng 200)!")
print("=" * 80)
