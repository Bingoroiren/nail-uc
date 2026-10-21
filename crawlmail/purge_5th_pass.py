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

# 5 specific diaspora/student/inland agencies to purge
PURGE_EMAILS_5TH = {
    'ilgajan@naver.com',
    'yongman007@naver.com',
    'student388@naver.com',
    'xiexiewo@naver.com',
    'lijing30@naver.com'
}

flawless_clean = []
purged_5th = []

for r in email_rows:
    em = r['Email'].strip().lower()
    if em in PURGE_EMAILS_5TH:
        purged_5th.append((r['Công ty'], em))
    else:
        flawless_clean.append(r)

print(f"Total input email rows: {len(email_rows)}")
print(f"Purged in 5th pass: {len(purged_5th)}")
print(f"REMAINING FLAWLESS AGENCIES: {len(flawless_clean)}")

for c, em in purged_5th:
    print(f"  [-] PURGED: {c} | {em}")

# Sort flawless_clean by Category, Company
flawless_clean.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))

# Combine with no_email_rows
combined = flawless_clean + no_email_rows

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
print(f"HOÀN TẤT RÀ SOÁT LẦN 5: Đã chốt ĐÚNG {len(flawless_clean)} AGENCY SIÊU TINH KHIẾT B2B (Hàng 1 đến Hàng {len(flawless_clean)})!")
print("=" * 80)
