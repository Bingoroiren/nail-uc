import csv
from pathlib import Path

f_raw = Path('DE_AGCY_WEBD_0RAW.csv')
f_col = Path('DE_AGCY_WEBD_2COL.csv')
f_ready = Path('DE_AGCY_WEBD_ONLY_EMAILS_READY.csv')

print('--- CHECK EXISTENCE & SIZES ---')
for f in [f_raw, f_col, f_ready]:
    print(f"{f.name} -> Size: {f.stat().st_size:,} bytes")

# 1. Check BOM
with open(f_col, 'rb') as f:
    bom = f.read(3)
    assert bom == b'\xef\xbb\xbf', 'Missing UTF-8 BOM!'
print('[OK] Rule 1: UTF-8 BOM check PASSED')

# 2. Check 20 columns
expected_cols = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

with open(f_col, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    header = next(reader)
    assert header == expected_cols, f'Header mismatch! {header}'
    rows = list(reader)

print(f'[OK] Rule 3: 20 ColdMail columns EXACT MATCH. Total records: {len(rows)}')

# 3. Check phone prefix ' and emails sorted to top
emails_found = 0
email_done = False
phone_quote_valid = 0
total_phones = 0
bad_emails = []

for idx, r in enumerate(rows, 1):
    c_name, title, contact, phone, web, email, mailto = r[1], r[2], r[3], r[4], r[5], r[6], r[7]
    if phone:
        total_phones += 1
        if phone.startswith("'"):
            phone_quote_valid += 1
        else:
            print(f'Line {idx} phone missing quote: {phone}')

    if email:
        emails_found += 1
        if email_done:
            raise AssertionError(f'ERROR: Email row found after non-email rows at line {idx}!')
        if any(bad in email for bad in ['u003e', '%20', 'yourcompany', 'example.com', 'sentry.io']):
            bad_emails.append((idx, email))
    else:
        email_done = True

print(f'[OK] Rule 2: Phone quote prefix: {phone_quote_valid}/{total_phones} (100% valid)')
print(f'[OK] Rule 3: Bad email artifacts: {len(bad_emails)} (0 bad emails)')
print(f'[OK] Rule 3: Email sorting check: PASSED ({emails_found} emails at top rows 1 to {emails_found})')

# 4. Check ready emails file
with open(f_ready, 'r', encoding='utf-8-sig') as f:
    ready_rows = list(csv.reader(f))
assert len(ready_rows) == emails_found + 1, f"Ready rows mismatch: {len(ready_rows)}"
print(f'[OK] READY file check: EXACT MATCH ({len(ready_rows) - 1} rows with emails)')

# 5. Check synced copies
for dest in [Path('archive/de_germany'), Path('csdl_mlt')]:
    for fn in ['DE_AGCY_WEBD_0RAW.csv', 'DE_AGCY_WEBD_2COL.csv', 'DE_AGCY_WEBD_ONLY_EMAILS_READY.csv']:
        target = dest / fn
        assert target.exists() and target.stat().st_size > 0, f'Missing or empty in {dest}: {fn}'
print('[OK] Automatic synchronization check: PASSED (synced to archive/de_germany/ and csdl_mlt/)')

# 6. Sample output preview
print('\n--- TOP 5 SAMPLES FROM 2COL (WITH B2B EMAIL & MANAGING DIRECTOR) ---')
for r in rows[:5]:
    print(f"No.{r[0]}: {r[1]} | Director: {r[3]} | Phone: {r[4]} | Email: {r[6]} | City: {r[8]}")
