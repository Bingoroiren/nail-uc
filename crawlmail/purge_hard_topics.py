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

# 22 Hard Purge Emails (Non-labor / non-visa / land / drunk driving / school violence / software procurement)
HARD_PURGE_EMAILS = {
    'brainservice1@naver.com',
    'hanvisanet@naver.com',
    'luce617@naver.com',
    'ngh2369@naver.com',
    '39jjyoung@naver.com',
    'inmec365@naver.com',
    'jobploy@naver.com',
    'da_dream_11@naver.com',
    'yjhan0414@naver.com',
    'seol6403@naver.com',
    'cjminwon@naver.com',
    'nohdaehwan@naver.com',
    'duath1031@naver.com',
    'bluebinis@naver.com',
    'attorney_jean@naver.com',
    'joonyjoony1004@naver.com',
    'yonseibeobhyeon@naver.com',
    'minwon21daa@naver.com',
    'taebaek2022@naver.com',
    'ksc4780@naver.com',
    'ahj2012@naver.com',
    'jiroin6469@naver.com'
}

bulletproof_clean = []
purged_hard = []

for r in email_rows:
    em = r['Email'].strip().lower()
    if em in HARD_PURGE_EMAILS:
        purged_hard.append((r['Công ty'], em))
    else:
        bulletproof_clean.append(r)

print(f"Total input email rows: {len(email_rows)}")
print(f"Purged in hard topic pass: {len(purged_hard)}")
print(f"REMAINING BULLETPROOF AGENCIES: {len(bulletproof_clean)}")

for c, em in purged_hard:
    print(f"  [-] PURGED: {c} | {em}")

# Sort bulletproof_clean by Category, Company
bulletproof_clean.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))

# Combine with no_email_rows
combined = bulletproof_clean + no_email_rows

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
print(f"HOÀN TẤT RÀ SOÁT LẦN 6: Đã chốt ĐÚNG {len(bulletproof_clean)} AGENCY SIÊU TINH HOA B2B (Hàng 1 đến Hàng {len(bulletproof_clean)})!")
print("=" * 80)
