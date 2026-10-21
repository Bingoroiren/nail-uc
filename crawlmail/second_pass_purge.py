import sys
import csv
import re
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

# Thorough Second-Pass Purge List
PURGE_TERMS = [
    '번역', 'honyaku', '통역', '탐정', '경찰', '수사관', '사고감정', '교통사고',
    '프랜차이즈', '가맹거래', '순직', '공무상요양', '학교폭력', '소셜연금', 'f-4',
    '밀리터리소설', '반도체', '화재감시', 'yna.co.kr', 'k-aia.or.kr', '청년취업끝까지',
    '필리핀', 'hire_philippines'
]

clean_approved = []
purged_records = []

for r in email_rows:
    cname = r['Công ty'].strip()
    em = r['Email'].strip().lower()
    cat = r['Category'].strip()
    
    # Check purge terms
    matched_term = None
    for pt in PURGE_TERMS:
        if pt in cname.lower() or pt in em.lower():
            matched_term = pt
            break
            
    if matched_term:
        purged_records.append((cname, em, f"Matched purge: {matched_term}"))
    else:
        clean_approved.append(r)

print(f"Total input email rows: {len(email_rows)}")
print(f"Purged rows in 2nd pass: {len(purged_records)}")
print(f"REMAINING 100% PURE ROWS: {len(clean_approved)}")

for c, em, reason in purged_records:
    print(f"  [-] PURGED: {c} | {em} | {reason}")

# Clean company names
for r in clean_approved:
    c = r['Công ty'].strip()
    c = c.replace('*', '').strip()
    if c.startswith('♬'):
        c = c.lstrip('♬').strip()
    # Normalize trailing prefixes
    for pfx in ['공식블로그', '공식', '블로그', '님의 블로그', '님의']:
        if c.endswith(pfx):
            c = c[:-len(pfx)].strip()
    r['Công ty'] = c

# Sort clean_approved by Category, Company
clean_approved.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))

# Renumber
combined = clean_approved + no_email_rows
for idx, r in enumerate(combined, 1):
    r['No.'] = idx

# Write to both files
for path in [MASTER_FILE, FMT_FILE]:
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(combined)
    print(f"[OK] Saved {len(combined)} rows to {path}")

print("=" * 80)
print(f"THÀNH CÔNG: Giữ lại chính xác {len(clean_approved)} Agency chuẩn 100%!")
print("=" * 80)
